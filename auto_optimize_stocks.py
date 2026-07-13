"""
auto_optimize_stocks.py  ─  日経225 個別株モメンタム戦略 全自動最適化
======================================================================
実行: python3 auto_optimize_stocks.py
結果: results/ フォルダに CSV・サマリーを保存

【戦略】
  日経225主要60銘柄から、毎月モメンタム上位N銘柄を選択して保有
  全銘柄がマイナスモメンタム → 現金待機（絶対モメンタムフィルター）

【注意】
  バックテストは現在の構成銘柄を使用するため「生存者バイアス」があります
  （倒産・上場廃止した銘柄が除外される）。実際の成績は過大評価の可能性あり。

【パラメータ最適化】
  lookback_months × top_n × skip_days の組み合わせを
  ウォークフォワードで評価（訓練3年→テスト1年→半年スライド）
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
TRAIN_DAYS   = 3 * 252
TEST_DAYS    = 1 * 252
STEP_DAYS    = 126            # 半年スライド
FEE_RATE     = 0.001          # 往復0.2%（ネット証券想定）
INITIAL_CASH = 1_000_000.0
OUTPUT_DIR   = "results"
MIN_STOCKS   = 10             # データ取得できる最低銘柄数

# ── 日経225 主要60銘柄 ────────────────────────────────────────────────────────
NIKKEI_UNIVERSE = {
    "トヨタ":         "7203.T",
    "ソフトバンクG":  "9984.T",
    "ソニーG":        "6758.T",
    "NTT":           "9432.T",
    "三菱UFJ":        "8306.T",
    "任天堂":         "7974.T",
    "信越化学":       "4063.T",
    "キーエンス":     "6861.T",
    "KDDI":          "9433.T",
    "リクルート":     "6098.T",
    "東京エレクトロン": "8035.T",
    "中外製薬":       "4519.T",
    "ファナック":     "6954.T",
    "ホンダ":         "7267.T",
    "JR東日本":       "9020.T",
    "武田薬品":       "4502.T",
    "日立":           "6501.T",
    "ブリヂストン":   "5108.T",
    "三井物産":       "8031.T",
    "キヤノン":       "7751.T",
    "JR東海":         "9022.T",
    "塩野義製薬":     "4507.T",
    "三菱商事":       "8058.T",
    "オリエンタルランド": "4661.T",
    "富士通":         "6702.T",
    "三菱重工":       "7011.T",
    "JT":            "2914.T",
    "富士フイルム":   "4901.T",
    "アドバンテスト": "6857.T",
    "ファーストリテイリング": "9983.T",
    "三井住友FG":     "8316.T",
    "セブン&アイ":    "3382.T",
    "JR西日本":       "9021.T",
    "アステラス製薬": "4503.T",
    "パナソニック":   "6752.T",
    "日本製鉄":       "5401.T",
    "三菱地所":       "8802.T",
    "日本郵船":       "9101.T",
    "スズキ":         "7269.T",
    "資生堂":         "4911.T",
    "川崎汽船":       "9107.T",
    "ダイキン":       "6367.T",
    "オリンパス":     "7733.T",
    "第一三共":       "4568.T",
    "コマツ":         "6301.T",
    "伊藤忠商事":     "8001.T",
    "日産自動車":     "7201.T",
    "みずほFG":       "8411.T",
    "東京海上":       "8766.T",
    "三菱電機":       "6503.T",
    "テルモ":         "4543.T",
    "住友商事":       "8053.T",
    "マツダ":         "7261.T",
    "京セラ":         "6971.T",
    "野村HD":         "8604.T",
    "MS&AD":          "8725.T",
    "東レ":           "3401.T",
    "SCREENホールディングス": "7735.T",
    "エーザイ":       "4523.T",
    "東京電力HD":     "9501.T",
}

# ── パラメータグリッド ──────────────────────────────────────────────────────
PARAM_GRID = {
    "lookback_months": [1, 2, 3, 4, 5, 6, 8, 9, 10, 12],  # 10個
    "top_n":           [3, 5, 7, 10, 15, 20],               # 6個（保有銘柄数）
    "skip_days":       [0, 5, 10, 21],                       # 4個
}
# 合計: 10 × 6 × 4 = 240 組み合わせ


# ── データ取得 ────────────────────────────────────────────────────────────────
def fetch_prices() -> pd.DataFrame:
    print("📡 日経225主要銘柄の価格データを取得中...")
    print(f"   対象: {len(NIKKEI_UNIVERSE)} 銘柄")
    prices = {}
    failed = []

    tickers = list(NIKKEI_UNIVERSE.values())
    labels  = {v: k for k, v in NIKKEI_UNIVERSE.items()}

    # まとめてダウンロード（高速）
    try:
        raw = yf.download(
            tickers, start=DATA_START, end=DATA_END,
            interval="1d", auto_adjust=True, progress=False,
        )
        if "Close" in raw.columns:
            close = raw["Close"]
        else:
            close = raw

        for ticker in tickers:
            if ticker in close.columns:
                s = close[ticker].dropna()
                if len(s) > 200:
                    prices[ticker] = s
                else:
                    failed.append(labels.get(ticker, ticker))
            else:
                failed.append(labels.get(ticker, ticker))
    except Exception as e:
        print(f"  ⚠️  一括取得失敗: {e}、個別取得に切り替えます...")
        for ticker in tickers:
            label = labels.get(ticker, ticker)
            try:
                df = yf.download(ticker, start=DATA_START, end=DATA_END,
                                 interval="1d", auto_adjust=True, progress=False)
                if df is not None and len(df) > 200:
                    prices[ticker] = df["Close"].squeeze()
                else:
                    failed.append(label)
            except Exception:
                failed.append(label)

    if failed:
        print(f"  ⚠️  取得失敗 ({len(failed)}銘柄): {', '.join(failed[:10])}{'...' if len(failed) > 10 else ''}")

    price_df = pd.DataFrame(prices).ffill().dropna(how="all")
    n_ok = len(price_df.columns)
    print(f"  → {n_ok} 銘柄取得成功（{price_df.index[0].date()} 〜 {price_df.index[-1].date()}）\n")

    if n_ok < MIN_STOCKS:
        print(f"❌ 取得できた銘柄が少なすぎます（{n_ok} < {MIN_STOCKS}）")
        sys.exit(1)

    return price_df


# ── シミュレーション ──────────────────────────────────────────────────────────
def simulate(price_df: pd.DataFrame,
             lookback_months: int,
             top_n: int,
             skip_days: int) -> tuple[float, float, pd.Series]:
    """
    クロスセクショナル・モメンタム戦略をシミュレート。
    毎月リバランス、等金額配分、上位top_n銘柄を保有。
    returns: (sharpe, total_return_pct, portfolio_series)
    """
    lookback_days = lookback_months * 21
    available = list(price_df.columns)
    actual_top_n = min(top_n, len(available))

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

        # 各銘柄のモメンタム計算
        # ★ 生存者バイアス対策: ルックバック開始時点でデータが存在する銘柄のみ対象
        lookback_start_idx = idx - lookback_days - skip_days
        momentum = {}
        for t in available:
            # ルックバック開始時点より前に上場していること（NaNでないこと）を確認
            if pd.isna(price_df[t].iloc[lookback_start_idx]):
                continue
            p = float(past[t]) if not pd.isna(past[t]) else 0
            r = float(recent[t]) if not pd.isna(recent[t]) else 0
            c = float(cur[t]) if not pd.isna(cur[t]) else 0
            if p > 0 and r > 0 and c > 0:
                momentum[t] = (r / p - 1) * 100

        if not momentum:
            continue

        ranked   = sorted(momentum.items(), key=lambda x: x[1], reverse=True)
        # 絶対モメンタムフィルター: 上位銘柄でもマイナスなら現金
        selected = [t for t, m in ranked[:actual_top_n] if m > 0]

        # 現在の総資産
        pv = cash + sum(
            holdings.get(t, 0) * float(cur[t])
            for t in holdings
            if t in cur.index and not pd.isna(cur[t])
        )

        # 不要銘柄を売却
        for t in list(holdings.keys()):
            if t not in selected:
                price = float(cur[t]) if t in cur.index and not pd.isna(cur[t]) else 0
                if price > 0:
                    cash += holdings[t] * price * (1 - FEE_RATE)
                del holdings[t]

        # 選択銘柄を等金額で購入
        if selected:
            per = pv / len(selected)
            for t in selected:
                if t not in holdings:
                    price = float(cur[t]) if not pd.isna(cur[t]) else 0
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
    keys   = list(PARAM_GRID.keys())
    combos = list(product(*[PARAM_GRID[k] for k in keys]))
    n_combos = len(combos)

    n = len(price_df)
    window_starts = list(range(0, n - TRAIN_DAYS - TEST_DAYS + 1, STEP_DAYS))
    n_windows = len(window_starts)
    total_evals = n_combos * n_windows

    print(f"🔬 最適化開始（日経225個別株モメンタム）")
    print(f"   対象銘柄数: {len(price_df.columns)} 銘柄")
    print(f"   パラメータ組み合わせ: {n_combos:,} 通り")
    print(f"   時間窓: {n_windows} 個")
    print(f"   総評価回数: {total_evals:,} 回\n")

    all_results = []
    oos_parts   = []
    fix_parts   = []
    running_oos = INITIAL_CASH
    running_fix = INITIAL_CASH
    best_history = []

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

        # 訓練期間でグリッドサーチ
        best_train_sharpe = -999.0
        best_params = None
        for combo in combos:
            params = dict(zip(keys, combo))
            try:
                sharpe, _, _ = simulate(train_df, **params)
            except Exception:
                continue
            if sharpe > best_train_sharpe:
                best_train_sharpe = sharpe
                best_params = params

        if best_params is None:
            continue

        # テスト期間（OOS）評価
        try:
            oos_sharpe, oos_ret, oos_eq = simulate(test_df, **best_params)
        except Exception:
            continue

        if oos_sharpe <= -100:
            continue

        # 固定パラメータ（lookback=12m, top_n=10, skip=21d）との比較
        try:
            fix_sharpe, fix_ret, fix_eq = simulate(
                test_df, lookback_months=12, top_n=10, skip_days=21
            )
        except Exception:
            fix_sharpe, fix_ret, fix_eq = -999.0, -999.0, pd.Series(dtype=float)

        # 資産推移の接続
        if not oos_eq.empty:
            scale = running_oos / float(oos_eq.iloc[0])
            oos_parts.append(oos_eq * scale)
            running_oos = float((oos_eq * scale).iloc[-1])

        if not fix_eq.empty and fix_sharpe > -100:
            scale = running_fix / float(fix_eq.iloc[0])
            fix_parts.append(fix_eq * scale)
            running_fix = float((fix_eq * scale).iloc[-1])

        period = (f"{test_df.index[0].strftime('%Y/%m')}"
                  f"〜{test_df.index[-1].strftime('%Y/%m')}")
        all_results.append({
            "テスト期間":       period,
            "lookback_months":  best_params["lookback_months"],
            "top_n":            best_params["top_n"],
            "skip_days":        best_params["skip_days"],
            "訓練Sharpe":       round(best_train_sharpe, 3),
            "OOSシャープ":      round(oos_sharpe, 3),
            "OOSリターン(%)":   round(oos_ret, 2),
            "固定Sharpe":       round(fix_sharpe, 3) if fix_sharpe > -100 else None,
            "固定リターン(%)":  round(fix_ret, 2) if fix_ret > -100 else None,
            "最適化優位":       oos_sharpe > fix_sharpe if fix_sharpe > -100 else True,
        })
        best_history.append(best_params)

        elapsed = time.time() - t_start
        done = wi + 1
        eta  = elapsed / done * (n_windows - done)
        bar  = "█" * int(done / n_windows * 30) + "░" * (30 - int(done / n_windows * 30))
        sys.stdout.write(
            f"\r  [{bar}] {done}/{n_windows}窓  "
            f"OOS Sharpe: {oos_sharpe:.2f}  ETA: {int(eta)}s   "
        )
        sys.stdout.flush()

    print("\n")

    if not all_results:
        return {"error": "有効な結果がありませんでした"}

    windows_df = pd.DataFrame(all_results)

    # パラメータ別集計
    param_rows = []
    for r in all_results:
        param_rows.append({
            "lookback_months": r["lookback_months"],
            "top_n":           r["top_n"],
            "skip_days":       r["skip_days"],
            "OOSシャープ":     r["OOSシャープ"],
            "OOSリターン(%)":  r["OOSリターン(%)"],
        })
    param_df = pd.DataFrame(param_rows)
    param_summary = (
        param_df.groupby(["lookback_months", "top_n", "skip_days"])
        .agg(平均OOSシャープ=("OOSシャープ", "mean"),
             平均OOSリターン=("OOSリターン(%)", "mean"),
             採用回数=("OOSシャープ", "count"))
        .reset_index()
        .sort_values("平均OOSシャープ", ascending=False)
        .reset_index(drop=True)
    )

    def _concat(parts):
        if not parts:
            return pd.Series(dtype=float)
        c = pd.concat(parts)
        return c[~c.index.duplicated(keep="last")].sort_index()

    return {
        "windows":       windows_df,
        "oos_equity":    _concat(oos_parts),
        "fixed_equity":  _concat(fix_parts),
        "param_summary": param_summary,
        "best_history":  best_history,
        "summary": {
            "総評価回数":         total_evals,
            "有効窓数":           len(windows_df),
            "平均OOSシャープ":    round(windows_df["OOSシャープ"].mean(), 3),
            "平均固定Sharpe":     round(windows_df["固定Sharpe"].dropna().mean(), 3),
            "最適化優位率(%)":    round(windows_df["最適化優位"].mean() * 100, 1),
            "過学習比率":         round(
                windows_df["OOSシャープ"].mean() / windows_df["訓練Sharpe"].mean(), 3
            ) if windows_df["訓練Sharpe"].mean() > 0 else "N/A",
            "最終OOS資産":        round(running_oos),
            "最終固定資産":       round(running_fix),
        },
    }


# ── 結果保存 ──────────────────────────────────────────────────────────────────
def save_results(result: dict):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d_%H%M")

    csv1 = os.path.join(OUTPUT_DIR, f"stocks_windows_{today}.csv")
    result["windows"].to_csv(csv1, index=False, encoding="utf-8-sig")
    print(f"  📄 時間窓別結果: {csv1}")

    csv2 = os.path.join(OUTPUT_DIR, f"stocks_best_params_{today}.csv")
    result["param_summary"].head(30).to_csv(csv2, index=False, encoding="utf-8-sig")
    print(f"  📄 パラメータ集計: {csv2}")


# ── 推奨パラメータを表示 ──────────────────────────────────────────────────────
def print_recommendation(result: dict):
    s  = result["summary"]
    ps = result["param_summary"]

    print("\n" + "=" * 60)
    print("  📊 最適化サマリー（日経225 個別株モメンタム）")
    print("=" * 60)
    print(f"  総評価回数:        {s['総評価回数']:,} 回")
    print(f"  有効時間窓:        {s['有効窓数']} 窓")
    print(f"  平均OOSシャープ:   {s['平均OOSシャープ']}")
    print(f"  平均固定Sharpe:    {s['平均固定Sharpe']}")
    print(f"  最適化優位率:      {s['最適化優位率(%)']:.1f}%")
    print(f"  過学習比率:        {s['過学習比率']}  ← 1.0が理想")
    print(f"  最終OOS資産:       ¥{s['最終OOS資産']:,}")
    print(f"  最終固定資産:      ¥{s['最終固定資産']:,}")

    print("\n" + "-" * 60)
    print("  🏆 OOSシャープ TOP 10 パラメータ")
    print("-" * 60)
    for i, row in ps.head(10).iterrows():
        print(
            f"  #{i+1:2d}  lookback={int(row['lookback_months']):2d}m  "
            f"top_n={int(row['top_n']):2d}銘柄  "
            f"skip={int(row['skip_days']):2d}d  "
            f"→ OOS Sharpe: {row['平均OOSシャープ']:.3f}  "
            f"リターン: {row['平均OOSリターン']:+.1f}%"
        )

    best = ps.iloc[0]
    print("\n" + "-" * 60)
    print("  ✅ 推奨パラメータ")
    print("-" * 60)
    print(f"  lookback_months:  {int(best['lookback_months'])} ヶ月")
    print(f"  top_n:            {int(best['top_n'])} 銘柄を保有")
    print(f"  skip_days:        {int(best['skip_days'])} 日")
    print(f"  平均OOSシャープ:  {best['平均OOSシャープ']:.3f}")
    print(f"\n  ⚠️  注意: 生存者バイアス対策済み（ルックバック開始時に上場していた銘柄のみ対象）")
    print(f"         ただし上場廃止・倒産銘柄は含まれないため過大評価の可能性あり")
    print("=" * 60 + "\n")


# ── メイン ────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 60)
    print("  🎯 日経225 個別株モメンタム戦略 全自動最適化")
    print(f"  対象銘柄: 日経225主要 {len(NIKKEI_UNIVERSE)} 銘柄")
    print(f"  データ期間: {DATA_START} 〜 {DATA_END}")
    print(f"  訓練: {TRAIN_DAYS//252}年  テスト: {TEST_DAYS//252}年  スライド: {STEP_DAYS}日")
    print("=" * 60 + "\n")

    t0 = time.time()

    price_df = fetch_prices()
    result = walk_forward(price_df)

    if "error" in result:
        print(f"❌ {result['error']}")
        sys.exit(1)

    print("💾 結果を保存中...")
    save_results(result)
    print_recommendation(result)

    # ── B: top_n=3 vs top_n=10 詳細比較 ──────────────────────────────────────
    print("\n" + "=" * 60)
    print("  📊 top_n=3銘柄 vs top_n=10銘柄 比較（lookback=2m, skip=21d）")
    print("=" * 60)

    price_df_full = fetch_prices()  # 全期間のデータで比較
    configs = [
        {"label": "集中型（3銘柄）", "top_n": 3,  "lookback_months": 2, "skip_days": 21},
        {"label": "分散型（10銘柄）", "top_n": 10, "lookback_months": 2, "skip_days": 21},
        {"label": "TOP2位（10銘柄/5m）","top_n": 10, "lookback_months": 5, "skip_days": 21},
    ]
    for cfg in configs:
        label = cfg.pop("label")
        sharpe, ret, _ = simulate(price_df_full, **cfg)
        print(f"  {label:20s}  Sharpe: {sharpe:+.3f}  全期間リターン: {ret:+.1f}%")
        cfg["label"] = label  # 戻す

    print()
    print("  💡 Sharpeが高い = リスク対比のリターンが良い")
    print("     全期間リターンが高い ≠ 必ずしも良い（リスクが高い可能性）")
    print("=" * 60 + "\n")

    print(f"  ⏱  総実行時間: {time.time()-t0:.0f} 秒（{(time.time()-t0)/60:.1f} 分）\n")


if __name__ == "__main__":
    main()
