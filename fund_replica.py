"""
fund_replica.py ─ 流動性のある部品でファンドを複製できるか検証する
====================================================================
グローバル・サプライチェーン・ファンド（ヘッジなし）の収益源は
  ① 米短期金利  ② 信用スプレッド  ③ ドル円の為替
の3部品である（fund_check.py の分解より）。

このスクリプトは、誰でも買える上場ETFで同じ部品を組んだ
「複製ポートフォリオ」を作り、ファンドの実績と比較する:

  複製A（現金型）  : BIL（米国1-3ヶ月T-Bill ETF）を円換算 ＝ ①+③のみ
  複製B（信用型）  : BIL 50% + BKLN（シニアローンETF）50% を円換算 ＝ ①+②+③

比較期間: 2018/10〜2026/4（ファンドの公表実績と同じ）
判定基準:
  - 相関: ファンドの月次リターンと複製の月次リターンは似た動きか
  - 累積: 最終リターンの差＝「非流動・不透明を受け入れる対価」はいくらか

実行: python3 fund_replica.py   （yfinanceでETFデータを取得します）
※ 投資助言ではない。構造理解のための検証である。
"""

import numpy as np
import pandas as pd
import yfinance as yf

from fund_check import UNHEDGED, stats, print_stats_block

START, END = "2018-09-01", "2026-05-01"
FUND_START = "2018-10"          # ファンド実績の開始月

REPLICAS = {
    "複製A: 米T-Bill100%（円換算）":   {"BIL": 1.0},
    "複製B: T-Bill50%+ｼﾆｱﾛｰﾝ50%（円換算）": {"BIL": 0.5, "BKLN": 0.5},
    "複製C: ｼﾆｱﾛｰﾝ100%（円換算）":     {"BKLN": 1.0},
}


def fetch_monthly_jpy_returns() -> pd.DataFrame:
    """ETFのドル建てトータルリターンを円換算した月次リターンを返す。"""
    tickers = ["BIL", "BKLN", "JPY=X"]
    raw = yf.download(tickers, start=START, end=END,
                      interval="1d", auto_adjust=True, progress=False)["Close"]
    close = raw if isinstance(raw, pd.DataFrame) else raw.to_frame()
    close = close.ffill().dropna()

    # 月末値 → 月次リターン
    monthly = close.resample("ME").last()
    usdjpy = monthly["JPY=X"]
    out = {}
    for t in ("BIL", "BKLN"):
        jpy_value = monthly[t] * usdjpy          # 円換算価値
        out[t] = jpy_value.pct_change()
    df = pd.DataFrame(out).dropna()
    df.index = df.index.to_period("M")
    return df


def main():
    print("\n" + "=" * 66)
    print("  🧪 複製検証: サプライチェーン・ファンド(ヘッジなし) vs 上場ETF")
    print("=" * 66 + "\n")

    print("📡 ETFデータ取得中（BIL / BKLN / ドル円）...")
    etf = fetch_monthly_jpy_returns()

    # ファンド実績と期間を揃える
    fund_idx = pd.period_range(FUND_START, periods=len(UNHEDGED), freq="M")
    fund = pd.Series(np.array(UNHEDGED) / 100, index=fund_idx, name="fund")
    common = fund.index.intersection(etf.index)
    fund = fund[common]
    etf = etf.loc[common]
    print(f"   比較期間: {common[0]} 〜 {common[-1]}（{len(common)}ヶ月）\n")

    s_fund = stats((fund * 100).tolist())
    print_stats_block("ファンド実績（ヘッジなし）", s_fund)
    fund_cum = float(np.prod(1 + fund) - 1) * 100

    print()
    results = []
    for label, weights in REPLICAS.items():
        rep = sum(etf[t] * w for t, w in weights.items())
        s = stats((rep * 100).tolist())
        corr = float(np.corrcoef(fund, rep)[0, 1])
        cum = float(np.prod(1 + rep) - 1) * 100
        results.append((label, s, corr, cum))
        print_stats_block(label, s)
        print(f"  ファンドとの相関: {corr:+.2f}   累積: {cum:+.1f}%"
              f"（ファンド {fund_cum:+.1f}%との差 {fund_cum - cum:+.1f}pt）")
        print()

    # ── 総括 ───────────────────────────────────────────────────────────
    best = max(results, key=lambda x: x[2])
    print("-" * 66)
    print("  📊 総括")
    print("-" * 66)
    print(f"  最も動きが似た複製: {best[0]}（相関{best[2]:+.2f}）")
    gap = fund_cum - best[3]
    years = len(common) / 12
    print(f"  累積リターン差: {gap:+.1f}pt / {years:.1f}年 ＝ 年率約{gap / years:+.1f}pt")
    print()
    print(f"  → この年率差が「ファンドでしか取れない部分」の実測値。")
    print(f"    その対価として受け入れるもの: 月次でしか解約できない流動性、")
    print(f"    保有債権が見えない不透明性、Greensill型テールリスク、信託報酬。")
    print(f"  → 差が小さければ、流動性のあるETFの組み合わせで十分という結論になる。")
    print("=" * 66 + "\n")


if __name__ == "__main__":
    main()
