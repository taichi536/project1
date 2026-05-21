import pandas as pd
import numpy as np
from modules.technical import compute_all
from concurrent.futures import ThreadPoolExecutor, as_completed
from modules.signals import evaluate_signals, overall_signal


def _sma_crossover_signals(df: pd.DataFrame, short: int, long: int) -> pd.Series:
    s = df[f"SMA{short}"]
    l = df[f"SMA{long}"]
    signal = pd.Series(0, index=df.index)
    signal[s > l] = 1
    signal[s <= l] = -1
    # エントリーはクロス時のみ
    position = signal.diff().fillna(0)
    result = pd.Series(0, index=df.index)
    result[position > 0] = 1   # ゴールデンクロス → 買い
    result[position < 0] = -1  # デッドクロス → 売り
    return result


def _rsi_signals(df: pd.DataFrame, buy_th: float, sell_th: float) -> pd.Series:
    rsi = df["RSI"]
    signal = pd.Series(0, index=df.index)
    signal[rsi < buy_th] = 1
    signal[rsi > sell_th] = -1
    return signal


def _macd_signals(df: pd.DataFrame) -> pd.Series:
    hist = df["MACD_hist"]
    signal = pd.Series(0, index=df.index)
    signal[hist > 0] = 1
    signal[hist < 0] = -1
    position = signal.diff().fillna(0)
    result = pd.Series(0, index=df.index)
    result[position > 0] = 1
    result[position < 0] = -1
    return result


def _combined_signals(df: pd.DataFrame, short: int, long: int) -> pd.Series:
    sma_s = df[f"SMA{short}"]
    sma_l = df[f"SMA{long}"]
    rsi = df["RSI"]
    hist = df["MACD_hist"]

    score = pd.Series(0.0, index=df.index)
    score += (sma_s > sma_l).astype(float)
    score -= (sma_s <= sma_l).astype(float)
    score += (rsi < 40).astype(float)
    score -= (rsi > 60).astype(float)
    score += (hist > 0).astype(float)
    score -= (hist < 0).astype(float)

    signal = pd.Series(0, index=df.index)
    signal[score >= 2] = 1
    signal[score <= -2] = -1
    return signal


def _actual_signals(df: pd.DataFrame, sma_short: int, sma_long: int) -> pd.Series:
    """
    実際の自動売買ロジック（overall_signal）と同じシグナルでバックテスト。
    各時点で「その日までのデータのみ」を使ってシグナルを計算する。
    インジケーターはrolling/ewmなので先読みなし。
    """
    result = pd.Series(0, index=df.index)
    min_rows = sma_long + 10  # 長期MAが安定するまでの最低行数
    for i in range(len(df)):
        if i < min_rows:
            continue
        slice_df = df.iloc[: i + 1]
        try:
            sigs = evaluate_signals(slice_df, sma_short=sma_short, sma_long=sma_long)
            verdict, _ = overall_signal(sigs, df=slice_df, sma_long=sma_long)
            if verdict == "買い":
                result.iloc[i] = 1
            elif verdict == "売り":
                result.iloc[i] = -1
        except Exception:
            pass
    return result


STRATEGIES = {
    "実際のシグナル（overall_signal）": "actual",
    "複合シグナル（推奨）": "combined",
    "ゴールデンクロス（移動平均）": "sma",
    "RSI逆張り": "rsi",
    "MACDクロス": "macd",
}


def run_backtest(
    df_raw: pd.DataFrame,
    strategy: str = "combined",
    sma_short: int = 25,
    sma_long: int = 75,
    rsi_buy: float = 35,
    rsi_sell: float = 65,
    initial_cash: float = 1_000_000,
    stop_loss_atr: float = 2.0,
) -> dict:
    df = compute_all(df_raw.copy(), sma_short=sma_short, sma_long=sma_long)
    df = df.dropna()

    if strategy == "actual":
        raw_signals = _actual_signals(df, sma_short, sma_long)
    elif strategy == "sma":
        raw_signals = _sma_crossover_signals(df, sma_short, sma_long)
    elif strategy == "rsi":
        raw_signals = _rsi_signals(df, rsi_buy, rsi_sell)
    elif strategy == "macd":
        raw_signals = _macd_signals(df)
    else:
        raw_signals = _combined_signals(df, sma_short, sma_long)

    fee_rate = 0.001  # 片道0.1%の取引手数料

    cash = initial_cash
    shares = 0
    entry_price = 0.0
    stop_price = 0.0
    entry_cost = 0.0  # 買い時の手数料込みコスト（損益計算用）

    portfolio_values = []
    trades = []
    position = 0  # 0=なし, 1=保有

    for i, (date, row) in enumerate(df.iterrows()):
        price = row["Close"]
        atr = row["ATR"] if "ATR" in row else price * 0.02
        sig = raw_signals.iloc[i]

        # 損切りチェック
        if position == 1 and price <= stop_price:
            proceeds = shares * price * (1 - fee_rate)
            # 損益 = 売却額 - 取得コスト（手数料込み）
            pnl = proceeds - entry_cost
            trades.append({
                "日付": date, "種別": "損切り売",
                "価格": round(price, 2), "株数": shares,
                "損益": round(pnl, 0),
            })
            cash += proceeds
            shares = 0
            position = 0

        # 買いシグナル
        if sig == 1 and position == 0 and cash > price:
            shares = int(cash * 0.95 / (price * (1 + fee_rate)))
            if shares > 0:
                entry_cost = shares * price * (1 + fee_rate)  # 手数料込み取得コスト
                entry_price = price
                stop_price = price - stop_loss_atr * atr
                cash -= entry_cost
                trades.append({
                    "日付": date, "種別": "買い",
                    "価格": round(price, 2), "株数": shares,
                    "損益": 0,
                })
                position = 1

        # 売りシグナル
        elif sig == -1 and position == 1:
            proceeds = shares * price * (1 - fee_rate)
            # 損益 = 売却額 - 取得コスト（手数料込み）
            pnl = proceeds - entry_cost
            trades.append({
                "日付": date, "種別": "売り",
                "価格": round(price, 2), "株数": shares,
                "損益": round(pnl, 0),
            })
            cash += proceeds
            shares = 0
            position = 0

        total_value = cash + shares * price
        portfolio_values.append({"日付": date, "総資産": total_value, "株価": price})

    pv = pd.DataFrame(portfolio_values).set_index("日付")
    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()

    # パフォーマンス指標
    final_value = pv["総資産"].iloc[-1]
    total_return = (final_value - initial_cash) / initial_cash * 100

    # Buy & Hold比較（初期購入手数料を考慮）
    bh_buy_price = df["Close"].iloc[0] * (1 + fee_rate)
    bh_shares = int(initial_cash / bh_buy_price)
    bh_proceeds = bh_shares * df["Close"].iloc[-1] * (1 - fee_rate)
    bh_remaining_cash = initial_cash - bh_shares * bh_buy_price
    bh_final = bh_proceeds + bh_remaining_cash
    bh_return = (bh_final - initial_cash) / initial_cash * 100

    # ドローダウン
    rolling_max = pv["総資産"].cummax()
    drawdown = (pv["総資産"] - rolling_max) / rolling_max * 100
    max_drawdown = drawdown.min()

    # シャープレシオ
    daily_returns = pv["総資産"].pct_change().dropna()
    sharpe = (daily_returns.mean() / daily_returns.std() * np.sqrt(252)) if daily_returns.std() > 0 else 0

    # 勝率
    if not trades_df.empty:
        sell_trades = trades_df[trades_df["種別"].isin(["売り", "損切り売"])]
        win_rate = (sell_trades["損益"] > 0).mean() * 100 if len(sell_trades) > 0 else 0
        total_trades = len(sell_trades)
    else:
        win_rate = 0
        total_trades = 0

    pv["ドローダウン(%)"] = drawdown
    pv["Buy&Hold"] = [
        (initial_cash - bh_shares * df["Close"].iloc[0]) + bh_shares * p
        for p in pv["株価"]
    ]

    return {
        "portfolio": pv,
        "trades": trades_df,
        "metrics": {
            "最終資産": round(final_value, 0),
            "総リターン(%)": round(total_return, 2),
            "B&Hリターン(%)": round(bh_return, 2),
            "最大ドローダウン(%)": round(max_drawdown, 2),
            "シャープレシオ": round(sharpe, 2),
            "総取引回数": total_trades,
            "勝率(%)": round(win_rate, 1),
            "初期資産": initial_cash,
        },
    }


def run_batch_backtest(
    tickers: list[str],
    fetch_fn,
    strategy: str = "combined",
    period: str = "2y",
    sma_short: int = 25,
    sma_long: int = 75,
    rsi_buy: float = 35,
    rsi_sell: float = 65,
    initial_cash: float = 1_000_000,
    stop_loss_atr: float = 2.0,
    max_workers: int = 4,
) -> dict:
    """
    複数銘柄を並列でバックテストし集計結果を返す。
    fetch_fn(ticker, period) -> DataFrame
    """
    rows = []
    errors = []

    def _run_one(ticker):
        try:
            df_raw = fetch_fn(ticker, period=period)
            result = run_backtest(
                df_raw,
                strategy=strategy,
                sma_short=sma_short,
                sma_long=sma_long,
                rsi_buy=rsi_buy,
                rsi_sell=rsi_sell,
                initial_cash=initial_cash,
                stop_loss_atr=stop_loss_atr,
            )
            m = result["metrics"]
            return {
                "銘柄": ticker,
                "総リターン(%)": m["総リターン(%)"],
                "B&Hリターン(%)": m["B&Hリターン(%)"],
                "最大DD(%)": m["最大ドローダウン(%)"],
                "シャープ": m["シャープレシオ"],
                "取引回数": m["総取引回数"],
                "勝率(%)": m["勝率(%)"],
                "戦略優位": m["総リターン(%)"] > m["B&Hリターン(%)"],
            }, None
        except Exception as e:
            return None, (ticker, str(e))

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_run_one, t): t for t in tickers}
        for fut in as_completed(futures):
            row, err = fut.result()
            if row:
                rows.append(row)
            if err:
                errors.append(err)

    if not rows:
        return {"summary": pd.DataFrame(), "rows": pd.DataFrame(), "errors": errors}

    df_rows = pd.DataFrame(rows).sort_values("総リターン(%)", ascending=False).reset_index(drop=True)

    summary = {
        "対象銘柄数": len(rows),
        "平均リターン(%)": round(df_rows["総リターン(%)"].mean(), 2),
        "中央値リターン(%)": round(df_rows["総リターン(%)"].median(), 2),
        "平均B&Hリターン(%)": round(df_rows["B&Hリターン(%)"].mean(), 2),
        "平均最大DD(%)": round(df_rows["最大DD(%)"].mean(), 2),
        "平均シャープ": round(df_rows["シャープ"].mean(), 2),
        "平均勝率(%)": round(df_rows["勝率(%)"].mean(), 1),
        "戦略優位銘柄数": int(df_rows["戦略優位"].sum()),
        "戦略優位率(%)": round(df_rows["戦略優位"].mean() * 100, 1),
    }

    return {"summary": summary, "rows": df_rows, "errors": errors}
