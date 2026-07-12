"""
ウォークフォワード最適化モジュール
- マルチアセット・モメンタム戦略のパラメータを訓練期間で最適化
- テスト期間でアウトオブサンプル検証
- 時系列を前から後ろにスライドして繰り返す
"""

import pandas as pd
import numpy as np
from itertools import product
import yfinance as yf

MULTI_ASSET_UNIVERSE = {
    "日本株":   "1306.T",
    "米国株":   "2558.T",
    "先進国株": "1657.T",
    "新興国株": "1658.T",
    "金":       "1540.T",
    "J-REIT":   "1343.T",
    "米国債":   "1482.T",
    "先進国債": "2511.T",
    "ドル円":   "USDJPY=X",
}

PARAM_GRID = {
    "lookback_months": [3, 6, 9, 12, 18],
    "top_n":           [1, 2, 3],
    "skip_days":       [0, 21],
}


def _fetch_prices(start: str, end: str) -> pd.DataFrame:
    tickers = list(MULTI_ASSET_UNIVERSE.values())
    prices = {}
    for ticker in tickers:
        try:
            df = yf.download(ticker, start=start, end=end,
                             interval="1d", auto_adjust=True, progress=False)
            if df is not None and not df.empty:
                prices[ticker] = df["Close"].squeeze()
        except Exception:
            pass
    return pd.DataFrame(prices).ffill().dropna(how="all") if prices else pd.DataFrame()


def _simulate(price_df: pd.DataFrame, lookback_months: int, top_n: int,
              skip_days: int, fee_rate: float = 0.001) -> float:
    """指定パラメータでモメンタム戦略をシミュレートし、シャープレシオを返す。"""
    labels = {v: k for k, v in MULTI_ASSET_UNIVERSE.items()}
    available = list(price_df.columns)
    lookback_days = lookback_months * 21

    rebal_dates = []
    for d in price_df.resample("MS").first().index:
        mask = price_df.index >= d
        if mask.any():
            rebal_dates.append(price_df.index[mask][0])

    cash = 1_000_000.0
    holdings: dict = {}
    records = []

    for rd in rebal_dates:
        idx = price_df.index.get_loc(rd)
        if idx < lookback_days + skip_days:
            continue

        cur = price_df.iloc[idx]
        past = price_df.iloc[idx - lookback_days - skip_days]
        recent = price_df.iloc[idx - skip_days] if skip_days > 0 else cur

        momentum = {}
        for t in available:
            if float(past[t]) > 0 and float(recent[t]) > 0:
                momentum[t] = (float(recent[t]) / float(past[t]) - 1) * 100

        ranked = sorted(momentum.items(), key=lambda x: x[1], reverse=True)
        selected = [t for t, m in ranked[:top_n] if m > 0]

        pv = cash + sum(
            holdings.get(t, 0) * float(cur[t])
            for t in holdings if t in cur.index
        )

        for t in list(holdings.keys()):
            if t not in selected:
                price = float(cur[t]) if t in cur.index else 0
                if price > 0:
                    cash += holdings[t] * price * (1 - fee_rate)
                del holdings[t]

        if selected:
            per = pv / len(selected)
            for t in selected:
                if t not in holdings and t in cur.index:
                    price = float(cur[t])
                    if price > 0:
                        buy_amt = min(per, cash)
                        holdings[t] = buy_amt * (1 - fee_rate) / price
                        cash -= buy_amt

        records.append({"日付": rd, "総資産": pv})

    if len(records) < 3:
        return -999.0

    pv_series = pd.DataFrame(records).set_index("日付")["総資産"]
    monthly_ret = pv_series.pct_change().dropna()
    if monthly_ret.std() == 0:
        return 0.0
    sharpe = monthly_ret.mean() / monthly_ret.std() * (12 ** 0.5)
    return float(sharpe)


def _simulate_with_equity(price_df: pd.DataFrame, lookback_months: int, top_n: int,
                          skip_days: int, fee_rate: float = 0.001,
                          initial_cash: float = 1_000_000.0) -> tuple:
    """シャープと資産推移を返す。"""
    available = list(price_df.columns)
    lookback_days = lookback_months * 21

    rebal_dates = []
    for d in price_df.resample("MS").first().index:
        mask = price_df.index >= d
        if mask.any():
            rebal_dates.append(price_df.index[mask][0])

    cash = initial_cash
    holdings: dict = {}
    records = []

    for rd in rebal_dates:
        idx = price_df.index.get_loc(rd)
        if idx < lookback_days + skip_days:
            continue

        cur = price_df.iloc[idx]
        past = price_df.iloc[idx - lookback_days - skip_days]
        recent = price_df.iloc[idx - skip_days] if skip_days > 0 else cur

        momentum = {}
        for t in available:
            if float(past[t]) > 0 and float(recent[t]) > 0:
                momentum[t] = (float(recent[t]) / float(past[t]) - 1) * 100

        ranked = sorted(momentum.items(), key=lambda x: x[1], reverse=True)
        selected = [t for t, m in ranked[:top_n] if m > 0]

        pv = cash + sum(
            holdings.get(t, 0) * float(cur[t])
            for t in holdings if t in cur.index
        )

        for t in list(holdings.keys()):
            if t not in selected:
                price = float(cur[t]) if t in cur.index else 0
                if price > 0:
                    cash += holdings[t] * price * (1 - fee_rate)
                del holdings[t]

        if selected:
            per = pv / len(selected)
            for t in selected:
                if t not in holdings and t in cur.index:
                    price = float(cur[t])
                    if price > 0:
                        buy_amt = min(per, cash)
                        holdings[t] = buy_amt * (1 - fee_rate) / price
                        cash -= buy_amt

        records.append({"日付": rd, "総資産": pv})

    if not records:
        return -999.0, pd.DataFrame()

    pv_df = pd.DataFrame(records).set_index("日付")
    monthly_ret = pv_df["総資産"].pct_change().dropna()
    sharpe = float(
        monthly_ret.mean() / monthly_ret.std() * (12 ** 0.5)
    ) if monthly_ret.std() > 0 else 0.0
    return sharpe, pv_df


def run_grid_search(price_df: pd.DataFrame,
                    param_grid: dict = None) -> pd.DataFrame:
    """全パラメータ組み合わせを評価してスコア表を返す。"""
    if param_grid is None:
        param_grid = PARAM_GRID

    keys = list(param_grid.keys())
    combos = list(product(*[param_grid[k] for k in keys]))

    rows = []
    for combo in combos:
        params = dict(zip(keys, combo))
        sharpe = _simulate(
            price_df,
            lookback_months=params["lookback_months"],
            top_n=params["top_n"],
            skip_days=params["skip_days"],
        )
        rows.append({**params, "シャープ": round(sharpe, 3)})

    return pd.DataFrame(rows).sort_values("シャープ", ascending=False).reset_index(drop=True)


def run_walk_forward(
    full_price_df: pd.DataFrame,
    train_years: int = 3,
    test_years: int = 1,
    param_grid: dict = None,
    fee_rate: float = 0.001,
    progress_callback=None,
) -> dict:
    """
    ウォークフォワード最適化。
    - 訓練: train_years 年でベストパラメータ探索
    - テスト: 続く test_years 年でアウトオブサンプル評価
    - 時間窓をずらして繰り返す
    """
    if param_grid is None:
        param_grid = PARAM_GRID

    keys = list(param_grid.keys())
    combos = list(product(*[param_grid[k] for k in keys]))

    train_days = train_years * 252
    test_days = test_years * 252
    step_days = test_days  # 重複しないようにテスト期間分ずらす

    n = len(full_price_df)
    window_starts = list(range(0, n - train_days - test_days + 1, step_days))

    windows = []
    all_oos_equity = []
    best_params_history = []

    total = len(window_starts)
    for wi, ws in enumerate(window_starts):
        train_end = ws + train_days
        test_end = train_end + test_days

        if test_end > n:
            break

        train_df = full_price_df.iloc[ws:train_end]
        test_df = full_price_df.iloc[train_end:test_end]

        if progress_callback:
            progress_callback(wi, total, train_df.index[0], test_df.index[-1])

        # 訓練期間でグリッドサーチ
        best_sharpe = -999.0
        best_params = None
        for combo in combos:
            params = dict(zip(keys, combo))
            try:
                sharpe = _simulate(train_df, **params, fee_rate=fee_rate)
            except Exception:
                continue
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_params = params

        if best_params is None:
            continue

        # テスト期間でOOS評価
        try:
            oos_sharpe, oos_eq = _simulate_with_equity(test_df, **best_params, fee_rate=fee_rate)
        except Exception:
            continue

        period_label = f"{test_df.index[0].strftime('%Y/%m')}〜{test_df.index[-1].strftime('%Y/%m')}"
        windows.append({
            "テスト期間":        period_label,
            "最適lookback(月)": best_params["lookback_months"],
            "最適top_n":        best_params["top_n"],
            "最適skip(日)":     best_params["skip_days"],
            "訓練Sharpe":       round(best_sharpe, 3),
            "OOSシャープ":      round(oos_sharpe, 3),
        })
        best_params_history.append(best_params)

        if not oos_eq.empty:
            all_oos_equity.append(oos_eq)

    if not windows:
        return {"error": "有効な時間窓が見つかりませんでした（データ不足の可能性）"}

    windows_df = pd.DataFrame(windows)

    # OOS資産推移を結合（各窓の初期を前窓末尾に接続）
    if all_oos_equity:
        equity_parts = []
        running_value = 1_000_000.0
        for eq in all_oos_equity:
            pv = eq["総資産"]
            scale = running_value / float(pv.iloc[0])
            scaled = pv * scale
            equity_parts.append(scaled)
            running_value = float(scaled.iloc[-1])
        combined_equity = pd.concat(equity_parts)
        combined_equity = combined_equity[~combined_equity.index.duplicated(keep="last")]
        combined_equity = combined_equity.sort_index()
    else:
        combined_equity = pd.Series(dtype=float)

    # 固定パラメータ（デフォルト: lookback=12, top_n=1, skip=21）でのOOS比較
    fixed_equity_parts = []
    running_fixed = 1_000_000.0
    for oos_df_raw in [full_price_df.iloc[w + train_days: w + train_days + test_days]
                       for w in window_starts
                       if w + train_days + test_days <= n]:
        try:
            _, eq_fixed = _simulate_with_equity(
                oos_df_raw,
                lookback_months=12, top_n=1, skip_days=21,
                fee_rate=fee_rate,
            )
            if not eq_fixed.empty:
                pv = eq_fixed["総資産"]
                scale = running_fixed / float(pv.iloc[0])
                scaled = pv * scale
                fixed_equity_parts.append(scaled)
                running_fixed = float(scaled.iloc[-1])
        except Exception:
            pass

    if fixed_equity_parts:
        fixed_equity = pd.concat(fixed_equity_parts)
        fixed_equity = fixed_equity[~fixed_equity.index.duplicated(keep="last")].sort_index()
    else:
        fixed_equity = pd.Series(dtype=float)

    avg_oos_sharpe = float(windows_df["OOSシャープ"].mean())
    avg_train_sharpe = float(windows_df["訓練Sharpe"].mean())
    n_windows = len(windows_df)

    return {
        "windows": windows_df,
        "oos_equity": combined_equity,
        "fixed_equity": fixed_equity,
        "summary": {
            "時間窓数":         n_windows,
            "平均OOSシャープ":  round(avg_oos_sharpe, 3),
            "平均訓練Sharpe":   round(avg_train_sharpe, 3),
            "過学習比率":       round(avg_oos_sharpe / avg_train_sharpe, 2) if avg_train_sharpe > 0 else "N/A",
            "最終OOS資産":      round(float(combined_equity.iloc[-1])) if not combined_equity.empty else 0,
            "最終固定資産":     round(float(fixed_equity.iloc[-1])) if not fixed_equity.empty else 0,
        },
        "best_params_history": best_params_history,
    }


def fetch_and_optimize(
    start: str,
    end: str,
    train_years: int = 3,
    test_years: int = 1,
    param_grid: dict = None,
    progress_callback=None,
) -> dict:
    """データ取得〜ウォークフォワード最適化を一括実行。"""
    price_df = _fetch_prices(start, end)
    if price_df.empty:
        return {"error": "価格データの取得に失敗しました"}
    if len(price_df) < (train_years + test_years) * 252:
        return {"error": f"データが不足しています（{len(price_df)}日）。{train_years + test_years}年以上の期間を指定してください。"}

    return run_walk_forward(
        price_df,
        train_years=train_years,
        test_years=test_years,
        param_grid=param_grid,
        progress_callback=progress_callback,
    )
