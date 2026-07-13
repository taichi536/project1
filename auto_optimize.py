"""
auto_optimize.py  ─  マルチアセット・モメンタム戦略 全自動最適化
======================================================================
実行: python auto_optimize.py
結果: results/ フォルダに CSV・グラフ・サマリーを保存

【評価の仕組み】
  - 訓練3年でグリッドサーチ → ベストパラメータを選択
  - 続く1年（未来データ）でアウトオブサンプル（OOS）評価
  - 半年ずつスライドしてカバー（2010〜2025、約23窓）
  - 総評価回数: 624組み合わせ × 約23窓 ≈ 14,000回以上
"""

import os
import sys
import warnings
import time
from datetime import datetime
from itertools import product

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ── 設定 ────────────────────────────────────────────────────────────────────
DATA_START   = "2010-01-01"
DATA_END     = "2025-12-31"
TRAIN_DAYS   = 3 * 252        # 訓練期間（3年）
TEST_DAYS    = 1 * 252        # テスト期間（1年）
STEP_DAYS    = 126            # スライド幅（半年）
FEE_RATE     = 0.001
INITIAL_CASH = 1_000_000.0
OUTPUT_DIR   = "results"

UNIVERSE = {
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
    "lookback_months":    [1, 2, 3, 4, 5, 6, 8, 9, 10, 12, 15, 18, 24],  # 13個
    "top_n":              [1, 2, 3, 4],                                     # 4個
    "skip_days":          [0, 5, 10, 15, 21, 42],                          # 6個
    "mom_threshold_pct":  [0.0, -5.0],                                     # 2個
}
# 合計: 13 × 4 × 6 × 2 = 624 組み合わせ


# ── データ取得 ───────────────────────────────────────────────────────────────
def fetch_prices() -> pd.DataFrame:
    print("📡 価格データを取得中...")
    tickers = list(UNIVERSE.values())
    prices = {}
    for ticker in tickers:
        label = [k for k, v in UNIVERSE.items() if v == ticker][0]
        sys.stdout.write(f"  {label} ({ticker})... ")
        sys.stdout.flush()
        for attempt in range(3):
            try:
                df = yf.download(
                    ticker, start=DATA_START, end=DATA_END,
                    interval="1d", auto_adjust=True, progress=False,
                )
                if df is not None and not df.empty:
                    prices[ticker] = df["Close"].squeeze()
                    print(f"✅ {len(df)}日")
                    break
            except Exception as e:
                if attempt == 2:
                    print(f"⚠️  取得失敗: {e}")
                time.sleep(1)
    price_df = pd.DataFrame(prices).ffill().dropna(how="all")
    print(f"  → 合計 {len(price_df)} 日分のデータ（{price_df.index[0].date()} 〜 {price_df.index[-1].date()}）\n")
    return price_df


# ── シミュレーション（コア） ──────────────────────────────────────────────────
def simulate(price_df: pd.DataFrame,
             lookback_months: int,
             top_n: int,
             skip_days: int,
             mom_threshold_pct: float) -> tuple[float, float, pd.Series]:
    """
    パラメータでモメンタム戦略を評価。
    returns: (sharpe, total_return_pct, portfolio_series)
    """
    lookback_days = lookback_months * 21
    available = list(price_df.columns)

    # 月初リバランス日を列挙
    rebal_dates = []
    for d in price_df.resample("MS").first().index:
        mask = price_df.index >= d
        if mask.any():
            rebal_dates.append(price_df.index[mask][0])

    cash = INITIAL_CASH
    holdings: dict = {}
    records = []

    for rd in rebal_dates:
        idx = price_df.index.get_loc(rd)
        required = lookback_days + skip_days + 1
        if idx < required:
            continue

        cur    = price_df.iloc[idx]
        past   = price_df.iloc[idx - lookback_days - skip_days]
        recent = price_df.iloc[idx - skip_days] if skip_days > 0 else cur

        momentum = {}
        for t in available:
            p, r = float(past[t]), float(recent[t])
            if p > 0 and r > 0:
                momentum[t] = (r / p - 1) * 100

        ranked   = sorted(momentum.items(), key=lambda x: x[1], reverse=True)
        selected = [t for t, m in ranked[:top_n] if m > mom_threshold_pct]

        pv = cash + sum(
            holdings.get(t, 0) * float(cur[t])
            for t in holdings if t in cur.index
        )

        for t in list(holdings.keys()):
            if t not in selected:
                price = float(cur[t]) if t in cur.index else 0
                if price > 0:
                    cash += holdings[t] * price * (1 - FEE_RATE)
                del holdings[t]

        if selected:
            per = pv / len(selected)
            for t in selected:
                if t not in holdings and t in cur.index:
                    price = float(cur[t])
                    if price > 0:
                        buy_amt = min(per, cash)
                        holdings[t] = buy_amt * (1 - FEE_RATE) / price
                        cash -= buy_amt

        records.append({"日付": rd, "総資産": pv})

    if len(records) < 3:
        return -999.0, -999.0, pd.Series(dtype=float)

    pv_series = pd.DataFrame(records).set_index("日付")["総資産"]
    monthly_ret = pv_series.pct_change().dropna()
    sharpe = float(monthly_ret.mean() / monthly_ret.std() * (12 ** 0.5)) if monthly_ret.std() > 0 else 0.0
    total_ret = float((pv_series.iloc[-1] / INITIAL_CASH - 1) * 100)
    return sharpe, total_ret, pv_series


# ── ウォークフォワード最適化 ─────────────────────────────────────────────────
def walk_forward(price_df: pd.DataFrame) -> dict:
    keys  = list(PARAM_GRID.keys())
    combos = list(product(*[PARAM_GRID[k] for k in keys]))
    n_combos = len(combos)

    n = len(price_df)
    window_starts = list(range(0, n - TRAIN_DAYS - TEST_DAYS + 1, STEP_DAYS))
    n_windows = len(window_starts)

    total_evals = n_combos * n_windows
    print(f"🔬 最適化開始")
    print(f"   パラメータ組み合わせ: {n_combos:,} 通り")
    print(f"   時間窓: {n_windows} 個（{price_df.index[TRAIN_DAYS].date()} 〜 {price_df.index[min(TRAIN_DAYS + TEST_DAYS, n-1)].date()} etc.）")
    print(f"   総評価回数: {total_evals:,} 回\n")

    all_window_results = []
    oos_equity_parts   = []
    fixed_equity_parts = []
    running_oos   = INITIAL_CASH
    running_fixed = INITIAL_CASH
    best_params_history = []

    t_start = time.time()

    for wi, ws in enumerate(window_starts):
        train_end = ws + TRAIN_DAYS
        test_end  = train_end + TEST_DAYS
        if test_end > n:
            break

        train_df = price_df.iloc[ws:train_end]
        test_df  = price_df.iloc[train_end:test_end]

        if len(train_df) < 100 or len(test_df) < 20:
            continue

        # ── 訓練期間でグリッドサーチ ──
        best_train_sharpe = -999.0
        best_params       = None
        for combo in combos:
            params = dict(zip(keys, combo))
            try:
                sharpe, _, _ = simulate(train_df, **params)
            except Exception:
                continue
            if sharpe > best_train_sharpe:
                best_train_sharpe = sharpe
                best_params       = params

        if best_params is None:
            continue

        # ── テスト期間（OOS）評価 ──
        try:
            oos_sharpe, oos_ret, oos_eq = simulate(test_df, **best_params)
        except Exception:
            continue

        # ── 固定パラメータ（デフォルト）での評価 ──
        try:
            fix_sharpe, fix_ret, fix_eq = simulate(
                test_df,
                lookback_months=12, top_n=1,
                skip_days=21, mom_threshold_pct=0.0,
            )
        except Exception:
            fix_sharpe, fix_ret, fix_eq = -999.0, -999.0, pd.Series(dtype=float)

        # -999 はデータ不足のセンチネル値 → その窓はスキップ
        if oos_sharpe <= -100:
            continue

        # ── OOS資産推移を接続 ──
        if not oos_eq.empty:
            scale = running_oos / float(oos_eq.iloc[0])
            oos_equity_parts.append(oos_eq * scale)
            running_oos = float((oos_eq * scale).iloc[-1])

        valid_fix_sharpe = fix_sharpe if fix_sharpe > -100 else None
        if not fix_eq.empty and valid_fix_sharpe is not None:
            scale = running_fixed / float(fix_eq.iloc[0])
            fixed_equity_parts.append(fix_eq * scale)
            running_fixed = float((fix_eq * scale).iloc[-1])

        period = (
            f"{test_df.index[0].strftime('%Y/%m')}"
            f"〜{test_df.index[-1].strftime('%Y/%m')}"
        )
        all_window_results.append({
            "テスト期間":           period,
            "lookback_months":      best_params["lookback_months"],
            "top_n":                best_params["top_n"],
            "skip_days":            best_params["skip_days"],
            "mom_threshold":        best_params["mom_threshold_pct"],
            "訓練Sharpe":           round(best_train_sharpe, 3),
            "OOSシャープ":          round(oos_sharpe, 3),
            "OOSリターン(%)":       round(oos_ret, 2),
            "固定Sharpe":           round(valid_fix_sharpe, 3) if valid_fix_sharpe is not None else None,
            "固定リターン(%)":      round(fix_ret, 2) if fix_ret > -100 else None,
            "最適化優位":           oos_sharpe > fix_sharpe if valid_fix_sharpe is not None else True,
        })
        best_params_history.append(best_params)

        # 進捗表示
        elapsed = time.time() - t_start
        done    = wi + 1
        eta     = elapsed / done * (n_windows - done) if done > 0 else 0
        bar     = "█" * int(done / n_windows * 30) + "░" * (30 - int(done / n_windows * 30))
        sys.stdout.write(
            f"\r  [{bar}] {done}/{n_windows}窓  "
            f"OOS Sharpe: {oos_sharpe:.2f}  "
            f"ETA: {int(eta)}s   "
        )
        sys.stdout.flush()

    print("\n")

    if not all_window_results:
        return {"error": "有効な結果がありませんでした"}

    windows_df = pd.DataFrame(all_window_results)

    # OOS資産推移の結合
    oos_eq_full   = _concat_equity(oos_equity_parts)
    fixed_eq_full = _concat_equity(fixed_equity_parts)

    # パラメータ別集計（平均OOSシャープで順位付け）
    param_summary = _aggregate_params(all_window_results, keys)

    return {
        "windows":       windows_df,
        "oos_equity":    oos_eq_full,
        "fixed_equity":  fixed_eq_full,
        "param_summary": param_summary,
        "best_params_history": best_params_history,
        "summary": {
            "総評価回数":         total_evals,
            "有効窓数":           len(windows_df),
            "平均OOSシャープ":    round(windows_df["OOSシャープ"].mean(), 3),
            "平均固定Sharpe":     round(windows_df["固定Sharpe"].dropna().mean(), 3),
            "最適化優位率(%)":    round(windows_df["最適化優位"].mean() * 100, 1),
            "過学習比率":         round(
                windows_df["OOSシャープ"].mean() /
                windows_df["訓練Sharpe"].mean(), 3
            ) if windows_df["訓練Sharpe"].mean() > 0 else "N/A",
            "最終OOS資産":        round(running_oos),
            "最終固定資産":       round(running_fixed),
        },
    }


def _concat_equity(parts: list) -> pd.Series:
    if not parts:
        return pd.Series(dtype=float)
    combined = pd.concat(parts)
    return combined[~combined.index.duplicated(keep="last")].sort_index()


def _aggregate_params(results: list, keys: list) -> pd.DataFrame:
    """パラメータ組み合わせごとに平均OOSシャープを集計。-999は除外済みの前提。"""
    rows = []
    for r in results:
        rows.append({
            k: r[k] for k in ["lookback_months", "top_n", "skip_days", "mom_threshold",
                               "OOSシャープ", "OOSリターン(%)"]
        })
    df = pd.DataFrame(rows)
    df = df[df["OOSシャープ"] > -100]  # 念のため再フィルタ
    agg = (
        df.groupby(["lookback_months", "top_n", "skip_days", "mom_threshold"])
        .agg(
            平均OOSシャープ=("OOSシャープ", "mean"),
            平均OOSリターン=("OOSリターン(%)", "mean"),
            採用回数=("OOSシャープ", "count"),
        )
        .reset_index()
        .sort_values("平均OOSシャープ", ascending=False)
        .reset_index(drop=True)
    )
    agg["平均OOSシャープ"] = agg["平均OOSシャープ"].round(3)
    agg["平均OOSリターン"] = agg["平均OOSリターン"].round(2)
    return agg


# ── 結果保存 ──────────────────────────────────────────────────────────────────
def save_results(result: dict, price_df: pd.DataFrame):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d_%H%M")

    # 1. 時間窓別 CSV
    csv_windows = os.path.join(OUTPUT_DIR, f"windows_{today}.csv")
    result["windows"].to_csv(csv_windows, index=False, encoding="utf-8-sig")
    print(f"  📄 時間窓別結果: {csv_windows}")

    # 2. パラメータ別集計 CSV（上位50件）
    csv_params = os.path.join(OUTPUT_DIR, f"best_params_{today}.csv")
    result["param_summary"].head(50).to_csv(csv_params, index=False, encoding="utf-8-sig")
    print(f"  📄 パラメータ集計: {csv_params}")

    # 3. グラフ（matplotlib）
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates

        fig, axes = plt.subplots(2, 1, figsize=(14, 10))
        fig.suptitle("マルチアセット・モメンタム ウォークフォワード最適化", fontsize=14, fontweight="bold")

        # 上段: OOS資産推移
        ax1 = axes[0]
        if not result["oos_equity"].empty:
            ax1.plot(result["oos_equity"].index, result["oos_equity"].values,
                     label="最適化パラメータ", color="#00b4d8", linewidth=2)
        if not result["fixed_equity"].empty:
            ax1.plot(result["fixed_equity"].index, result["fixed_equity"].values,
                     label="固定パラメータ(12m/1銘柄)", color="#999999",
                     linewidth=1.5, linestyle="--")
        ax1.yaxis.set_major_formatter(
            matplotlib.ticker.FuncFormatter(lambda x, _: f"¥{x:,.0f}")
        )
        ax1.set_title("OOS資産推移（アウトオブサンプル）")
        ax1.legend(loc="upper left")
        ax1.grid(True, alpha=0.3)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

        # 下段: OOSシャープの推移（窓ごと）
        ax2 = axes[1]
        w = result["windows"]
        colors = ["#2ecc71" if v else "#e74c3c" for v in w["最適化優位"]]
        ax2.bar(range(len(w)), w["OOSシャープ"], color=colors, alpha=0.8, label="OOSシャープ")
        ax2.bar(range(len(w)), w["固定Sharpe"], color="#999999", alpha=0.4,
                label="固定Sharpe", width=0.4)
        ax2.axhline(0, color="black", linewidth=0.8)
        ax2.set_xticks(range(len(w)))
        ax2.set_xticklabels(w["テスト期間"], rotation=45, ha="right", fontsize=7)
        ax2.set_title("時間窓別 OOSシャープ（緑=最適化優位、赤=固定優位）")
        ax2.legend()
        ax2.grid(True, alpha=0.3, axis="y")

        plt.tight_layout()
        png_path = os.path.join(OUTPUT_DIR, f"equity_{today}.png")
        plt.savefig(png_path, dpi=120, bbox_inches="tight")
        plt.close()
        print(f"  📈 グラフ: {png_path}")
    except Exception as e:
        print(f"  ⚠️  グラフ生成スキップ: {e}")

    return today


# ── 推奨パラメータを表示 ──────────────────────────────────────────────────────
def print_recommendation(result: dict):
    s = result["summary"]
    ps = result["param_summary"]
    bph = result["best_params_history"]

    print("\n" + "=" * 60)
    print("  📊 最適化サマリー")
    print("=" * 60)
    print(f"  総評価回数:        {s['総評価回数']:,} 回")
    print(f"  有効時間窓:        {s['有効窓数']} 窓")
    print(f"  平均OOSシャープ:   {s['平均OOSシャープ']}")
    print(f"  平均固定Sharpe:    {s['平均固定Sharpe']}")
    print(f"  最適化優位率:      {s['最適化優位率(%)']:.1f}%（この割合で固定より良かった）")
    print(f"  過学習比率:        {s['過学習比率']}  ← 1.0が理想、0.7以上で実用的")
    print(f"  最終OOS資産:       ¥{s['最終OOS資産']:,}")
    print(f"  最終固定資産:      ¥{s['最終固定資産']:,}")

    print("\n" + "-" * 60)
    print("  🏆 OOSシャープ TOP 10 パラメータ")
    print("-" * 60)
    top10 = ps.head(10)
    for i, row in top10.iterrows():
        print(
            f"  #{i+1:2d}  lookback={int(row['lookback_months']):2d}m  "
            f"top_n={int(row['top_n'])}  "
            f"skip={int(row['skip_days']):2d}d  "
            f"threshold={row['mom_threshold']:+.0f}%  "
            f"→ OOS Sharpe: {row['平均OOSシャープ']:.3f}  "
            f"リターン: {row['平均OOSリターン']:+.1f}%"
        )

    # 最多採用パラメータ
    import collections
    best = ps.iloc[0]
    print("\n" + "-" * 60)
    print("  ✅ 推奨パラメータ（平均OOSシャープ最高）")
    print("-" * 60)
    print(f"  lookback_months:  {int(best['lookback_months'])} ヶ月")
    print(f"  top_n:            {int(best['top_n'])} 銘柄")
    print(f"  skip_days:        {int(best['skip_days'])} 日")
    print(f"  mom_threshold:    {best['mom_threshold']:+.0f}%")
    print(f"  平均OOSシャープ:  {best['平均OOSシャープ']:.3f}")

    print("\n  💡 使い方: アプリの「マルチアセット」タブで上記を入力してバックテスト")
    print("=" * 60 + "\n")


# ── メイン ────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 60)
    print("  🔬 マルチアセット・モメンタム 全自動最適化")
    print(f"  パラメータ組み合わせ: {13*4*6*2:,} 通り")
    print(f"  データ期間: {DATA_START} 〜 {DATA_END}")
    print(f"  訓練: {TRAIN_DAYS//252}年  テスト: {TEST_DAYS//252}年  スライド: {STEP_DAYS}日（半年）")
    print("=" * 60 + "\n")

    t0 = time.time()

    # データ取得
    price_df = fetch_prices()
    if price_df.empty:
        print("❌ データ取得に失敗しました")
        sys.exit(1)

    # ウォークフォワード最適化
    result = walk_forward(price_df)

    if "error" in result:
        print(f"❌ エラー: {result['error']}")
        sys.exit(1)

    # 結果保存
    print("💾 結果を保存中...")
    save_results(result, price_df)

    # 推奨パラメータを表示
    print_recommendation(result)

    elapsed = time.time() - t0
    print(f"  ⏱  総実行時間: {elapsed:.0f} 秒（{elapsed/60:.1f} 分）\n")


if __name__ == "__main__":
    main()
