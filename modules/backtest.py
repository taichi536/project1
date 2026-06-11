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


def _trend_follow_signals(df: pd.DataFrame, long: int) -> pd.Series:
    """長期MAクロスのみのシンプルなトレンドフォロー戦略"""
    ma_col = f"SMA{long}"
    if ma_col not in df.columns:
        return pd.Series(0, index=df.index)
    close = df["Close"]
    ma = df[ma_col]
    above = close > ma
    signal = pd.Series(0, index=df.index)
    signal[above & ~above.shift(1).fillna(False)] = 1   # 上抜け: 買い
    signal[~above & above.shift(1).fillna(True)] = -1   # 下抜け: 売り
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
        # OBVは直近10行以上が必要（len(obv_series) >= 10 ガード）。
        # 15行渡すことでOBVを含む全指標を正しく評価しつつ O(n) を維持する。
        slice_df = df.iloc[max(0, i - 14): i + 1]
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
    "トレンドフォロー（MA上抜け/下抜け）": "trend_follow",
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
    take_profit_atr: float = 0.0,   # 0=利確なし、2.5=ATR×2.5で利確
    position_pct: float = 0.95,     # 1トレードに使う資金比率
    fee_rate: float = 0.002,
) -> dict:
    df = compute_all(df_raw.copy(), sma_short=sma_short, sma_long=sma_long)
    df = df.dropna()
    if df.empty:
        raise ValueError("指標計算後にデータが空になりました。期間を長くするか別の銘柄を試してください。")

    if strategy == "actual":
        raw_signals = _actual_signals(df, sma_short, sma_long)
    elif strategy == "sma":
        raw_signals = _sma_crossover_signals(df, sma_short, sma_long)
    elif strategy == "rsi":
        raw_signals = _rsi_signals(df, rsi_buy, rsi_sell)
    elif strategy == "macd":
        raw_signals = _macd_signals(df)
    elif strategy == "trend_follow":
        raw_signals = _trend_follow_signals(df, sma_long)
    else:
        raw_signals = _combined_signals(df, sma_short, sma_long)


    cash = initial_cash
    shares = 0
    entry_price = 0.0
    stop_price = 0.0
    take_price = 0.0   # 利確ターゲット価格
    entry_cost = 0.0   # 買い時の手数料込みコスト（損益計算用）

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
            pnl = proceeds - entry_cost
            trades.append({
                "日付": date, "種別": "損切り売",
                "価格": round(price, 2), "株数": shares,
                "損益": round(pnl, 0),
            })
            cash += proceeds
            shares = 0
            position = 0

        # 利確チェック（take_profit_atr > 0 の場合のみ）
        elif position == 1 and take_profit_atr > 0 and price >= take_price:
            proceeds = shares * price * (1 - fee_rate)
            pnl = proceeds - entry_cost
            trades.append({
                "日付": date, "種別": "利確売",
                "価格": round(price, 2), "株数": shares,
                "損益": round(pnl, 0),
            })
            cash += proceeds
            shares = 0
            position = 0

        # 買いシグナル（損切り・利確直後の同バー再エントリーを防ぐため elif）
        elif sig == 1 and position == 0 and cash > price * (1 + fee_rate):
            shares = int(cash * position_pct / (price * (1 + fee_rate)))
            if shares > 0:
                entry_cost = shares * price * (1 + fee_rate)
                entry_price = price
                stop_price = price - stop_loss_atr * atr
                take_price = price + take_profit_atr * atr if take_profit_atr > 0 else float("inf")
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
        sell_trades = trades_df[trades_df["種別"].isin(["売り", "損切り売", "利確売"])]
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
    take_profit_atr: float = 0.0,
    position_pct: float = 0.95,
    max_workers: int = 4,
    fee_rate: float = 0.002,
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
                take_profit_atr=take_profit_atr,
                position_pct=position_pct,
                fee_rate=fee_rate,
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


def run_momentum_portfolio_backtest(
    tickers: list[str],
    fetch_fn,
    initial_cash: float = 1_000_000,
    top_n: int = 10,
    lookback_months: int = 12,
    skip_recent_days: int = 21,
    ma_period: int = 200,
    corr_threshold: float = 0.55,
    use_regime_filter: bool = True,
    use_vol_weight: bool = True,
    min_weight: float = 0.05,
    max_weight: float = 0.20,
    fee_rate: float = 0.002,
    period: str = "5y",
) -> dict:
    """
    改善版モメンタムポートフォリオバックテスト。
    直近1ヶ月除外・品質フィルター・レジームフィルター・相関フィルター・ボラ逆数加重。
    """
    import yfinance as yf

    all_dfs = {}
    errors = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch_fn, t, period): t for t in tickers}
        for fut in as_completed(futures):
            t = futures[fut]
            try:
                df = fut.result()
                if df is not None and not df.empty and len(df) > ma_period:
                    all_dfs[t] = df[["Close"]].copy()
            except Exception as e:
                errors.append((t, str(e)))

    if len(all_dfs) < 2:
        raise ValueError("十分なデータを取得できませんでした")

    prices = pd.DataFrame({t: df["Close"].squeeze() for t, df in all_dfs.items()})
    prices = prices.sort_index().ffill()

    # 日経225レジームデータ取得
    regime_series = None
    if use_regime_filter:
        try:
            import io, contextlib, logging
            _yfl = logging.getLogger("yfinance")
            _yfl.setLevel(logging.CRITICAL)
            with contextlib.redirect_stderr(io.StringIO()):
                n225 = yf.download("^N225", period=period, interval="1d",
                                   auto_adjust=True, progress=False)
            _yfl.setLevel(logging.WARNING)
            if not n225.empty:
                regime_series = n225["Close"].squeeze()
                regime_series.index = pd.to_datetime(regime_series.index).tz_localize(None)
        except Exception:
            pass

    lookback_days = lookback_months * 21
    quality_lookback = 63  # 3ヶ月品質フィルター

    rebalance_dates = prices.resample("ME").last().index
    cash = initial_cash
    holdings: dict[str, float] = {}
    pv_records = []
    trades_log = []
    monthly_holdings = []

    for rb_date in rebalance_dates:
        hist = prices.loc[:rb_date].dropna(how="all")
        if len(hist) < lookback_days + skip_recent_days + 20:
            continue

        cur = hist.iloc[-1]
        n = len(hist)
        past_long = hist.iloc[max(0, n - lookback_days - skip_recent_days)]
        past_recent = hist.iloc[max(0, n - skip_recent_days)]
        past_quality = hist.iloc[max(0, n - quality_lookback - skip_recent_days)]

        momentum = ((past_recent / past_long) - 1) * 100
        momentum_3m = ((past_recent / past_quality) - 1) * 100

        # レジームフィルター（弱気相場は全売り・現金保有）
        if use_regime_filter and regime_series is not None:
            try:
                reg_hist = regime_series.loc[:rb_date]
                if len(reg_hist) >= ma_period:
                    if float(reg_hist.iloc[-1]) < float(reg_hist.tail(ma_period).mean()):
                        pv = cash + sum(holdings.get(t, 0) * cur.get(t, 0) for t in holdings)
                        for t in list(holdings.keys()):
                            price = cur.get(t)
                            if price and not pd.isna(price) and holdings[t] > 0:
                                cash += holdings[t] * price * (1 - fee_rate)
                                trades_log.append({"日付": rb_date, "銘柄": t, "種別": "売り(レジーム)",
                                                   "価格": round(price, 2), "モメンタム(%)": 0})
                            del holdings[t]
                        pv_records.append({"日付": rb_date, "総資産": cash})
                        monthly_holdings.append({"日付": rb_date, "保有銘柄": []})
                        continue
            except Exception:
                pass

        # 200日MA + 品質フィルター
        ma = hist.tail(ma_period).mean()
        combined = (cur > ma) & (momentum > 0) & (momentum_3m > 0)
        qualified = momentum[combined].dropna().sort_values(ascending=False)

        # 相関フィルター
        returns_hist = hist.pct_change().dropna()
        new_top = []
        for t in qualified.index:
            if len(new_top) >= top_n:
                break
            if not new_top or t not in returns_hist.columns:
                new_top.append(t)
                continue
            ret_t = returns_hist[t].tail(126)
            too_corr = any(
                len(common := ret_t.index.intersection(returns_hist[s].tail(126).index)) > 30
                and ret_t.loc[common].corr(returns_hist[s].tail(126).loc[common]) > corr_threshold
                for s in new_top if s in returns_hist.columns
            )
            if not too_corr:
                new_top.append(t)

        # ボラティリティ逆数加重
        if use_vol_weight and new_top:
            vols = {t: returns_hist[t].tail(60).std() * np.sqrt(252)
                    for t in new_top if t in returns_hist.columns
                    and returns_hist[t].tail(60).std() > 0}
            if vols:
                inv = {t: 1.0 / v for t, v in vols.items()}
                total = sum(inv.values())
                raw_w = {t: iv / total for t, iv in inv.items()}
                clipped = {t: max(min_weight, min(max_weight, w)) for t, w in raw_w.items()}
                total_c = sum(clipped.values())
                weights = {t: w / total_c for t, w in clipped.items()}
            else:
                eq = 1.0 / len(new_top)
                weights = {t: eq for t in new_top}
        else:
            eq = 1.0 / len(new_top) if new_top else 0
            weights = {t: eq for t in new_top}

        pv = cash + sum(holdings.get(t, 0) * cur.get(t, 0) for t in holdings)

        for t in list(holdings.keys()):
            if t not in new_top:
                price = cur.get(t)
                if price and not pd.isna(price) and holdings[t] > 0:
                    cash += holdings[t] * price * (1 - fee_rate)
                    trades_log.append({"日付": rb_date, "銘柄": t, "種別": "売り",
                                       "価格": round(price, 2), "モメンタム(%)": round(momentum.get(t, 0), 1)})
                del holdings[t]

        for t in new_top:
            if t not in holdings:
                price = cur.get(t)
                if price and not pd.isna(price) and cash > price:
                    alloc = pv * weights.get(t, 1.0 / len(new_top))
                    shares = min(alloc, cash * 0.99) / (price * (1 + fee_rate))
                    if shares > 0:
                        cash -= shares * price * (1 + fee_rate)
                        holdings[t] = shares
                        trades_log.append({"日付": rb_date, "銘柄": t, "種別": "買い",
                                           "価格": round(price, 2), "モメンタム(%)": round(momentum.get(t, 0), 1)})

        pv_after = cash + sum(holdings.get(t, 0) * cur.get(t, 0) for t in holdings)
        pv_records.append({"日付": rb_date, "総資産": pv_after})
        monthly_holdings.append({"日付": rb_date, "保有銘柄": list(holdings.keys())})

    if not pv_records:
        raise ValueError("シミュレーションデータが不足しています")

    pv_df = pd.DataFrame(pv_records).set_index("日付")

    # B&H比較（ユニバース全銘柄均等投資）
    first_prices = prices.iloc[0].dropna()
    shares_bh = (initial_cash / len(first_prices)) / first_prices
    bh_final = (shares_bh * prices.iloc[-1].reindex(first_prices.index).fillna(prices.iloc[-1])).sum()
    bh_return = (bh_final - initial_cash) / initial_cash * 100

    final_value = pv_df["総資産"].iloc[-1]
    total_return = (final_value - initial_cash) / initial_cash * 100

    rolling_max = pv_df["総資産"].cummax()
    drawdown = (pv_df["総資産"] - rolling_max) / rolling_max * 100
    max_dd = drawdown.min()

    monthly_ret = pv_df["総資産"].pct_change().dropna()
    sharpe = (monthly_ret.mean() / monthly_ret.std() * (12 ** 0.5)) if monthly_ret.std() > 0 else 0

    # 現在のランキング（最新月末時点）
    latest = prices.iloc[-1]
    n_last = len(prices)
    past_l = prices.iloc[max(0, n_last - lookback_days - skip_recent_days)]
    past_r = prices.iloc[max(0, n_last - skip_recent_days)]
    mom_latest = ((past_r / past_l) - 1) * 100
    ma_latest = prices.tail(ma_period).mean()
    qualified_now = mom_latest[latest > ma_latest].dropna().sort_values(ascending=False)
    ranking_df = pd.DataFrame({
        "銘柄": qualified_now.index,
        "モメンタム(%)": qualified_now.values.round(1),
        "推奨": ["✅ 買い" if i < top_n else "" for i in range(len(qualified_now))],
    }).reset_index(drop=True)

    return {
        "portfolio": pv_df,
        "trades": pd.DataFrame(trades_log) if trades_log else pd.DataFrame(),
        "monthly_holdings": monthly_holdings,
        "ranking": ranking_df,
        "errors": errors,
        "metrics": {
            "最終資産": round(final_value, 0),
            "総リターン(%)": round(total_return, 2),
            "B&Hリターン(%)": round(bh_return, 2),
            "最大ドローダウン(%)": round(max_dd, 2),
            "シャープレシオ": round(sharpe, 2),
            "総取引回数": len(trades_log),
            "リバランス回数": len(pv_records),
            "保有銘柄数": top_n,
        },
    }


MULTI_ASSET_UNIVERSE = {
    "日本株":    "1306.T",
    "米国株":    "2558.T",
    "先進国株":  "1657.T",
    "新興国株":  "1658.T",
    "金":        "1540.T",
    "J-REIT":    "1343.T",
    "米国債":    "1482.T",
    "先進国債":  "2511.T",
}


def run_multi_asset_backtest(
    initial_cash: float = 1_000_000,
    top_n: int = 1,
    lookback_months: int = 12,
    skip_recent_days: int = 21,
    fee_rate: float = 0.001,
    period: str = "5y",
    start_date: str = None,
    end_date: str = None,
    stop_loss_pct: float = 0.0,
) -> dict:
    """マルチアセット・モメンタム バックテスト
    日本株・米国株・金・J-REIT・米国債のETFを毎月モメンタムでローテーション。
    全て東証上場・NISA成長投資枠対応。
    """
    import yfinance as yf

    assets = MULTI_ASSET_UNIVERSE
    tickers = list(assets.values())
    labels = {v: k for k, v in assets.items()}

    prices = {}
    for ticker in tickers:
        try:
            if start_date and end_date:
                df = yf.download(ticker, start=start_date, end=end_date,
                                 interval="1d", auto_adjust=True, progress=False)
            else:
                df = yf.download(ticker, period=period, interval="1d",
                                 auto_adjust=True, progress=False)
            if df is not None and not df.empty:
                prices[ticker] = df["Close"].squeeze()
        except Exception:
            pass

    if len(prices) < 2:
        return {"error": "データ取得失敗（2銘柄未満）"}

    price_df = pd.DataFrame(prices).ffill().dropna(how="all")
    available = list(price_df.columns)

    lookback_days = lookback_months * 21

    rebal_dates = []
    for d in price_df.resample("MS").first().index:
        mask = price_df.index >= d
        if mask.any():
            rebal_dates.append(price_df.index[mask][0])

    cash = initial_cash
    holdings: dict[str, float] = {}
    entry_prices: dict[str, float] = {}
    records = []
    trades_log = []

    for i_rd, rd in enumerate(rebal_dates):
        idx = price_df.index.get_loc(rd)
        if idx < lookback_days + skip_recent_days:
            continue

        # ── 日次ストップロスチェック（前回リバランス〜今回リバランスの間）
        if stop_loss_pct > 0 and holdings and i_rd > 0:
            prev_rd = rebal_dates[i_rd - 1]
            prev_idx = price_df.index.get_loc(prev_rd)
            for day_idx in range(prev_idx + 1, idx):
                day_price = price_df.iloc[day_idx]
                day_date = price_df.index[day_idx]
                for t in list(holdings.keys()):
                    if t not in day_price.index or t not in entry_prices:
                        continue
                    current_p = float(day_price[t])
                    entry_p = entry_prices[t]
                    if entry_p > 0 and (current_p / entry_p - 1) <= -stop_loss_pct:
                        cash += holdings[t] * current_p * (1 - fee_rate)
                        trades_log.append({
                            "日付": day_date,
                            "銘柄": labels.get(t, t),
                            "売買": "売(SL)",
                            "価格": current_p,
                        })
                        del holdings[t]
                        del entry_prices[t]

        cur = price_df.iloc[idx]
        past = price_df.iloc[idx - lookback_days - skip_recent_days]
        recent = price_df.iloc[idx - skip_recent_days]

        momentum = {}
        for t in available:
            if past[t] > 0 and recent[t] > 0:
                momentum[t] = (recent[t] / past[t] - 1) * 100

        ranked = sorted(momentum.items(), key=lambda x: x[1], reverse=True)
        selected = [t for t, m in ranked[:top_n] if m > 0]

        pv = cash + sum(holdings.get(t, 0) * float(cur[t]) for t in holdings if t in cur.index)

        for t in list(holdings.keys()):
            if t not in selected:
                price = float(cur[t]) if t in cur.index else 0
                if price > 0:
                    cash += holdings[t] * price * (1 - fee_rate)
                    trades_log.append({"日付": rd, "銘柄": labels.get(t, t), "売買": "売", "価格": price})
                del holdings[t]
                entry_prices.pop(t, None)

        if selected:
            per = pv / len(selected)
            for t in selected:
                if t not in holdings and t in cur.index:
                    price = float(cur[t])
                    if price > 0:
                        buy_amt = min(per, cash)
                        holdings[t] = buy_amt * (1 - fee_rate) / price
                        entry_prices[t] = price
                        cash -= buy_amt
                        trades_log.append({"日付": rd, "銘柄": labels.get(t, t), "売買": "買", "価格": price})

        records.append({
            "日付": rd,
            "総資産": pv,
            "保有": "/".join(labels.get(t, t) for t in selected) if selected else "現金",
        })

    final_price = price_df.iloc[-1]
    final_value = cash + sum(
        holdings.get(t, 0) * float(final_price[t])
        for t in holdings if t in final_price.index
    )
    records.append({"日付": price_df.index[-1], "総資産": final_value, "保有": ""})

    pv_df = pd.DataFrame(records).set_index("日付")

    first_valid = price_df.dropna().iloc[0]
    bh_shares = {t: (initial_cash / len(available)) / float(first_valid[t])
                 for t in available if float(first_valid[t]) > 0}
    bh_final = sum(bh_shares[t] * float(final_price[t])
                   for t in bh_shares if t in final_price.index)
    bh_return = (bh_final / initial_cash - 1) * 100
    total_return = (final_value / initial_cash - 1) * 100

    rolling_max = pv_df["総資産"].cummax()
    max_dd = ((pv_df["総資産"] - rolling_max) / rolling_max * 100).min()
    monthly_ret = pv_df["総資産"].pct_change().dropna()
    sharpe = (monthly_ret.mean() / monthly_ret.std() * (12 ** 0.5)) if monthly_ret.std() > 0 else 0

    n = len(price_df)
    cur_mom = {}
    for t in available:
        p = price_df.iloc[max(0, n - lookback_days - skip_recent_days)]
        r = price_df.iloc[max(0, n - skip_recent_days)]
        if p[t] > 0 and r[t] > 0:
            cur_mom[t] = (r[t] / p[t] - 1) * 100

    ranking = pd.DataFrame([
        {"資産": labels.get(t, t), "モメンタム(%)": round(m, 1),
         "推奨": "✅ 買い" if i < top_n and m > 0 else ("⚠️ 絶対モメンタム負" if m <= 0 else "")}
        for i, (t, m) in enumerate(sorted(cur_mom.items(), key=lambda x: x[1], reverse=True))
    ])

    return {
        "portfolio": pv_df,
        "trades": pd.DataFrame(trades_log) if trades_log else pd.DataFrame(),
        "ranking": ranking,
        "metrics": {
            "最終資産": round(final_value, 0),
            "総リターン(%)": round(total_return, 2),
            "B&Hリターン(%)": round(bh_return, 2),
            "最大ドローダウン(%)": round(max_dd, 2),
            "シャープレシオ": round(sharpe, 2),
            "総リバランス回数": len(records) - 1,
        },
    }


def run_crypto_backtest(
    initial_cash: float = 1_000_000,
    period: str = "5y",
    start_date: str = None,
    end_date: str = None,
) -> dict:
    """暗号資産4戦略バックテスト比較
    
    戦略:
    1. BTC買い持ち（ベンチマーク）
    2. 200日移動平均フィルター
    3. BTC/ETH モメンタムローテーション（月次）
    4. マルチアセット（BTC+Gold+SP500、月次モメンタム）
    """
    import yfinance as yf

    TICKERS = {
        "BTC": "BTC-USD",
        "ETH": "ETH-USD",
        "Gold": "GLD",
        "SP500": "SPY",
    }

    # データ取得
    prices = {}
    for label, ticker in TICKERS.items():
        try:
            if start_date and end_date:
                df = yf.download(ticker, start=start_date, end=end_date,
                                 interval="1d", auto_adjust=True, progress=False)
            else:
                df = yf.download(ticker, period=period, interval="1d",
                                 auto_adjust=True, progress=False)
            if df is not None and not df.empty:
                prices[label] = df["Close"].squeeze()
        except Exception:
            pass

    if "BTC" not in prices:
        return {"error": "BTCデータ取得失敗"}

    price_df = pd.DataFrame(prices).ffill().dropna(how="all")

    results = {}

    # ── 戦略1: BTC買い持ち
    btc = price_df["BTC"].dropna()
    bh_shares = initial_cash / float(btc.iloc[0])
    bh_values = btc * bh_shares
    results["BTC買い持ち"] = bh_values

    # ── 戦略2: 200日移動平均フィルター
    ma200 = btc.rolling(200).mean()
    cash2 = initial_cash
    shares2 = 0.0
    vals2 = []
    for i, (date, price) in enumerate(btc.items()):
        ma = ma200.iloc[i] if i < len(ma200) else float("nan")
        if pd.isna(ma):
            vals2.append(cash2)
            continue
        if price > ma and shares2 == 0:
            shares2 = cash2 / float(price) * 0.999
            cash2 = 0.0
        elif price <= ma and shares2 > 0:
            cash2 = shares2 * float(price) * 0.999
            shares2 = 0.0
        vals2.append(cash2 + shares2 * float(price))
    results["200日MAフィルター"] = pd.Series(vals2, index=btc.index)

    # ── 戦略3: BTC/ETH モメンタムローテーション（月次）
    if "ETH" in price_df.columns:
        LOOKBACK = 252
        SKIP = 21
        cash3 = initial_cash
        holding3 = None
        shares3 = 0.0
        vals3_dict = {}

        rebal_dates = []
        for d in price_df.resample("MS").first().index:
            mask = price_df.index >= d
            if mask.any():
                rebal_dates.append(price_df.index[mask][0])

        for rd in rebal_dates:
            idx = price_df.index.get_loc(rd)
            if idx < LOOKBACK + SKIP:
                continue
            cur = price_df.iloc[idx]
            past = price_df.iloc[idx - LOOKBACK - SKIP]
            recent = price_df.iloc[idx - SKIP]

            mom = {}
            for asset in ["BTC", "ETH"]:
                if asset in price_df.columns and past[asset] > 0 and recent[asset] > 0:
                    mom[asset] = (recent[asset] / past[asset] - 1)

            if not mom:
                continue
            best = max(mom, key=mom.get)
            best_mom = mom[best]
            pv = cash3 + (shares3 * float(cur[holding3]) if holding3 and holding3 in cur.index else 0)

            if best_mom > 0:
                if holding3 != best:
                    if holding3 and holding3 in cur.index:
                        cash3 = shares3 * float(cur[holding3]) * 0.999
                        shares3 = 0.0
                    shares3 = pv * 0.999 / float(cur[best])
                    cash3 = 0.0
                    holding3 = best
            else:
                if holding3:
                    cash3 = shares3 * float(cur[holding3]) * 0.999
                    shares3 = 0.0
                    holding3 = None
            vals3_dict[rd] = pv

        if vals3_dict:
            s3 = pd.Series(vals3_dict)
            s3 = s3.reindex(btc.index).ffill().bfill()
            results["BTC/ETHローテーション"] = s3

    # ── 戦略4: マルチアセット（BTC+Gold+SP500、月次モメンタム）
    multi_assets = [k for k in ["BTC", "Gold", "SP500"] if k in price_df.columns]
    if len(multi_assets) >= 2:
        LOOKBACK = 252
        SKIP = 21
        cash4 = initial_cash
        holdings4 = {}
        entry4 = {}
        vals4_dict = {}

        rebal_dates4 = []
        for d in price_df.resample("MS").first().index:
            mask = price_df.index >= d
            if mask.any():
                rebal_dates4.append(price_df.index[mask][0])

        for rd in rebal_dates4:
            idx = price_df.index.get_loc(rd)
            if idx < LOOKBACK + SKIP:
                continue
            cur = price_df.iloc[idx]
            past = price_df.iloc[idx - LOOKBACK - SKIP]
            recent = price_df.iloc[idx - SKIP]

            mom = {}
            for asset in multi_assets:
                if past[asset] > 0 and recent[asset] > 0:
                    mom[asset] = (recent[asset] / past[asset] - 1)

            ranked = sorted(mom.items(), key=lambda x: x[1], reverse=True)
            selected = [a for a, m in ranked[:1] if m > 0]

            pv = cash4 + sum(holdings4.get(a, 0) * float(cur[a]) for a in holdings4 if a in cur.index)

            for a in list(holdings4.keys()):
                if a not in selected:
                    cash4 += holdings4[a] * float(cur[a]) * 0.999
                    del holdings4[a]

            if selected:
                a = selected[0]
                if a not in holdings4:
                    holdings4[a] = pv * 0.999 / float(cur[a])
                    cash4 = 0.0

            vals4_dict[rd] = pv

        if vals4_dict:
            s4 = pd.Series(vals4_dict)
            s4 = s4.reindex(btc.index).ffill().bfill()
            results["マルチアセット(BTC+金+株)"] = s4

    if not results:
        return {"error": "バックテスト計算失敗"}

    # ── 指標計算
    metrics = {}
    for name, series in results.items():
        series = series.dropna()
        if len(series) < 2:
            continue
        total_ret = (series.iloc[-1] / series.iloc[0] - 1) * 100
        daily_ret = series.pct_change().dropna()
        sharpe = (daily_ret.mean() / daily_ret.std() * (252 ** 0.5)) if daily_ret.std() > 0 else 0
        rolling_max = series.cummax()
        max_dd = ((series - rolling_max) / rolling_max * 100).min()
        metrics[name] = {
            "総リターン(%)": round(total_ret, 1),
            "最大ドローダウン(%)": round(max_dd, 1),
            "シャープレシオ": round(sharpe, 2),
        }

    result_df = pd.DataFrame(metrics).T.reset_index().rename(columns={"index": "戦略"})

    portfolio_df = pd.DataFrame(
        {k: v / v.iloc[0] * initial_cash for k, v in results.items()}
    )

    return {
        "portfolio": portfolio_df,
        "metrics": result_df,
    }


def run_crypto_backtest(
    initial_cash: float = 1_000_000,
    period: str = "5y",
    start_date: str = None,
    end_date: str = None,
) -> dict:
    """暗号資産4戦略バックテスト比較

    戦略:
    1. BTC買い持ち（ベンチマーク）
    2. 200日移動平均フィルター
    3. BTC/ETH モメンタムローテーション（月次）
    4. マルチアセット（BTC+Gold+SP500、月次モメンタム）
    """
    import yfinance as yf

    TICKERS = {
        "BTC": "BTC-USD",
        "ETH": "ETH-USD",
        "Gold": "GLD",
        "SP500": "SPY",
    }

    # データ取得
    prices = {}
    for label, ticker in TICKERS.items():
        try:
            if start_date and end_date:
                df = yf.download(ticker, start=start_date, end=end_date,
                                 interval="1d", auto_adjust=True, progress=False)
            else:
                df = yf.download(ticker, period=period, interval="1d",
                                 auto_adjust=True, progress=False)
            if df is not None and not df.empty:
                prices[label] = df["Close"].squeeze()
        except Exception:
            pass

    if "BTC" not in prices:
        return {"error": "BTCデータ取得失敗"}

    price_df = pd.DataFrame(prices).ffill().dropna(how="all")

    results = {}

    # ── 戦略1: BTC買い持ち
    btc = price_df["BTC"].dropna()
    bh_shares = initial_cash / float(btc.iloc[0])
    bh_values = btc * bh_shares
    results["BTC買い持ち"] = bh_values

    # ── 戦略2: 200日移動平均フィルター
    ma200 = btc.rolling(200).mean()
    cash2 = initial_cash
    shares2 = 0.0
    vals2 = []
    for i, (date, price) in enumerate(btc.items()):
        ma = ma200.iloc[i] if i < len(ma200) else float("nan")
        if pd.isna(ma):
            vals2.append(cash2)
            continue
        if price > ma and shares2 == 0:
            shares2 = cash2 / float(price) * 0.999
            cash2 = 0.0
        elif price <= ma and shares2 > 0:
            cash2 = shares2 * float(price) * 0.999
            shares2 = 0.0
        vals2.append(cash2 + shares2 * float(price))
    results["200日MAフィルター"] = pd.Series(vals2, index=btc.index)

    # ── 戦略3: BTC/ETH モメンタムローテーション（月次）
    if "ETH" in price_df.columns:
        LOOKBACK = 252
        SKIP = 21
        cash3 = initial_cash
        holding3 = None
        shares3 = 0.0
        vals3_dict = {}

        rebal_dates = []
        for d in price_df.resample("MS").first().index:
            mask = price_df.index >= d
            if mask.any():
                rebal_dates.append(price_df.index[mask][0])

        for rd in rebal_dates:
            idx = price_df.index.get_loc(rd)
            if idx < LOOKBACK + SKIP:
                continue
            cur = price_df.iloc[idx]
            past = price_df.iloc[idx - LOOKBACK - SKIP]
            recent = price_df.iloc[idx - SKIP]

            mom = {}
            for asset in ["BTC", "ETH"]:
                if asset in price_df.columns and past[asset] > 0 and recent[asset] > 0:
                    mom[asset] = (recent[asset] / past[asset] - 1)

            if not mom:
                continue
            best = max(mom, key=mom.get)
            best_mom = mom[best]
            pv = cash3 + (shares3 * float(cur[holding3]) if holding3 and holding3 in cur.index else 0)

            if best_mom > 0:
                if holding3 != best:
                    if holding3 and holding3 in cur.index:
                        cash3 = shares3 * float(cur[holding3]) * 0.999
                        shares3 = 0.0
                    shares3 = pv * 0.999 / float(cur[best])
                    cash3 = 0.0
                    holding3 = best
            else:
                if holding3:
                    cash3 = shares3 * float(cur[holding3]) * 0.999
                    shares3 = 0.0
                    holding3 = None
            vals3_dict[rd] = pv

        if vals3_dict:
            s3 = pd.Series(vals3_dict)
            s3 = s3.reindex(btc.index).ffill().bfill()
            results["BTC/ETHローテーション"] = s3

    # ── 戦略4: マルチアセット（BTC+Gold+SP500、月次モメンタム）
    multi_assets = [k for k in ["BTC", "Gold", "SP500"] if k in price_df.columns]
    if len(multi_assets) >= 2:
        LOOKBACK = 252
        SKIP = 21
        cash4 = initial_cash
        holdings4 = {}
        entry4 = {}
        vals4_dict = {}

        rebal_dates4 = []
        for d in price_df.resample("MS").first().index:
            mask = price_df.index >= d
            if mask.any():
                rebal_dates4.append(price_df.index[mask][0])

        for rd in rebal_dates4:
            idx = price_df.index.get_loc(rd)
            if idx < LOOKBACK + SKIP:
                continue
            cur = price_df.iloc[idx]
            past = price_df.iloc[idx - LOOKBACK - SKIP]
            recent = price_df.iloc[idx - SKIP]

            mom = {}
            for asset in multi_assets:
                if past[asset] > 0 and recent[asset] > 0:
                    mom[asset] = (recent[asset] / past[asset] - 1)

            ranked = sorted(mom.items(), key=lambda x: x[1], reverse=True)
            selected = [a for a, m in ranked[:1] if m > 0]

            pv = cash4 + sum(holdings4.get(a, 0) * float(cur[a]) for a in holdings4 if a in cur.index)

            for a in list(holdings4.keys()):
                if a not in selected:
                    cash4 += holdings4[a] * float(cur[a]) * 0.999
                    del holdings4[a]

            if selected:
                a = selected[0]
                if a not in holdings4:
                    holdings4[a] = pv * 0.999 / float(cur[a])
                    cash4 = 0.0

            vals4_dict[rd] = pv

        if vals4_dict:
            s4 = pd.Series(vals4_dict)
            s4 = s4.reindex(btc.index).ffill().bfill()
            results["マルチアセット(BTC+金+株)"] = s4

    if not results:
        return {"error": "バックテスト計算失敗"}

    # ── 指標計算
    metrics = {}
    for name, series in results.items():
        series = series.dropna()
        if len(series) < 2:
            continue
        total_ret = (series.iloc[-1] / series.iloc[0] - 1) * 100
        daily_ret = series.pct_change().dropna()
        sharpe = (daily_ret.mean() / daily_ret.std() * (252 ** 0.5)) if daily_ret.std() > 0 else 0
        rolling_max = series.cummax()
        max_dd = ((series - rolling_max) / rolling_max * 100).min()
        metrics[name] = {
            "総リターン(%)": round(total_ret, 1),
            "最大ドローダウン(%)": round(max_dd, 1),
            "シャープレシオ": round(sharpe, 2),
        }

    result_df = pd.DataFrame(metrics).T.reset_index().rename(columns={"index": "戦略"})

    portfolio_df = pd.DataFrame(
        {k: v / v.iloc[0] * initial_cash for k, v in results.items()}
    )

    return {
        "portfolio": portfolio_df,
        "metrics": result_df,
    }
