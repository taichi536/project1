"""
verify_backtest.py ─ バックテスト過学習チェッカー
====================================================================
どんな投資戦略のバックテストでも、過学習（オーバーフィッティング）の
兆候を統計的に検出する独立ツール。戦略の中身は問わない。

使い方:
  1) パラメータ探索の全結果を検証（推奨・最も強力）
     各列 = 1パラメータ組み合わせの月次リターン、行 = 月
     python3 verify_backtest.py returns_matrix.csv

  2) 単一戦略のリターン系列を検証
     python3 verify_backtest.py my_strategy.csv --trials 100
     （--trials: この戦略に至るまでに試した戦略・パラメータの総数。
       正直に申告するほど判定は正確になる）

  3) 資産曲線（金額）で渡す場合
     python3 verify_backtest.py equity.csv --equity

  4) デモ（ランダム戦略を生成して「ノイズを正しく検出できるか」を実演）
     python3 verify_backtest.py --demo

出力の見方:
  DSR  ≥ 0.95        統計的に有意（多重テスト補正後も本物の可能性が高い）
  PBO  < 0.2         過学習リスク低い
  IS→OOSスロープ > 0  訓練で良い戦略はテストでも良い（健全）

実装している手法:
  - DSR: Bailey & Lopez de Prado (2014) "The Deflated Sharpe Ratio"
  - PBO/CSCV: Bailey, Borwein, Lopez de Prado & Zhu (2015)
    "The Probability of Backtest Overfitting"

【免責】本ツールは統計的検証の道具であり、投資助言ではありません。
特定の金融商品の売買を推奨するものではありません。
"""

import argparse
import sys
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats


# ── DSR（偏向シャープ比）────────────────────────────────────────────────────
def deflated_sharpe_ratio(sr_annualized: float, n_trials: int, n_obs: int,
                          periods_per_year: int = 12,
                          skew: float = 0.0, excess_kurt: float = 0.0) -> tuple:
    """
    多重テスト補正後の「真のシャープ比が0を超える確率」を返す。
    returns: (dsr, expected_max_sharpe)
    """
    if n_trials <= 1 or n_obs <= 1:
        return 0.0, 0.0

    e_max_sr = (
        (1 - np.euler_gamma) * stats.norm.ppf(1 - 1.0 / n_trials)
        + np.euler_gamma * stats.norm.ppf(1 - 1.0 / (n_trials * np.e))
    )

    k = np.sqrt(periods_per_year)
    sr_p = sr_annualized / k
    e_max_p = e_max_sr / k
    variance = (1 - skew * sr_p + (excess_kurt / 4) * sr_p ** 2) / max(n_obs - 1, 1)
    sigma = np.sqrt(max(variance, 1e-12))
    z = (sr_p - e_max_p) / sigma
    return float(stats.norm.cdf(z)), float(e_max_sr)


# ── PBO / CSCV ───────────────────────────────────────────────────────────────
def compute_pbo(returns: np.ndarray, n_blocks: int = 12,
                periods_per_year: int = 12) -> dict:
    """
    CSCV法によるPBO。returns は T×N 行列（T期間 × N戦略）。
    """
    T, N = returns.shape
    if T < n_blocks * 2 or N < 2:
        return {"error": f"データ不足（{T}期間×{N}戦略、最低{n_blocks * 2}期間×2戦略必要）"}

    bounds = np.linspace(0, T, n_blocks + 1, dtype=int)
    blocks = [np.arange(bounds[b], bounds[b + 1]) for b in range(n_blocks)]

    def _sharpe(rows):
        sub = returns[rows]
        mu, sd = sub.mean(axis=0), sub.std(axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(sd > 0, mu / sd * np.sqrt(periods_per_year), -np.inf)

    n_below, pairs = 0, []
    splits = list(combinations(range(n_blocks), n_blocks // 2))
    for is_blk in splits:
        oos_blk = [b for b in range(n_blocks) if b not in is_blk]
        sr_is = _sharpe(np.concatenate([blocks[b] for b in is_blk]))
        sr_oos = _sharpe(np.concatenate([blocks[b] for b in oos_blk]))
        best = int(np.argmax(sr_is))
        if float(np.mean(sr_oos <= sr_oos[best])) <= 0.5:
            n_below += 1
        pairs.append((sr_is[best], sr_oos[best]))

    pairs = np.array(pairs)
    finite = np.isfinite(pairs).all(axis=1)
    slope = float(np.polyfit(pairs[finite, 0], pairs[finite, 1], 1)[0]) \
        if finite.sum() > 2 else float("nan")

    return {
        "pbo": n_below / len(splits),
        "n_splits": len(splits),
        "is_oos_slope": slope,
        "mean_oos_sharpe_of_is_best": float(np.nanmean(pairs[finite, 1])) if finite.any() else float("nan"),
    }


# ── レポート ─────────────────────────────────────────────────────────────────
def verify(returns_df: pd.DataFrame, n_trials: int = None,
           periods_per_year: int = 12) -> dict:
    """
    検証本体。returns_df: 行=期間、列=戦略（1列でも可）のリターン。
    """
    R = returns_df.to_numpy(dtype=float)
    R = R[~np.isnan(R).all(axis=1)]
    T, N = R.shape
    trials = n_trials if n_trials else N

    # 最良列（全期間シャープ最大）のDSR
    mu, sd = np.nanmean(R, axis=0), np.nanstd(R, axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        sharpes = np.where(sd > 0, mu / sd * np.sqrt(periods_per_year), -np.inf)
    best_i = int(np.argmax(sharpes))
    best_sr = float(sharpes[best_i])
    best_col = returns_df.columns[best_i]

    r_best = R[:, best_i]
    r_best = r_best[~np.isnan(r_best)]
    skew = float(stats.skew(r_best)) if len(r_best) > 3 else 0.0
    ekurt = float(stats.kurtosis(r_best)) if len(r_best) > 3 else 0.0

    dsr, e_max = deflated_sharpe_ratio(best_sr, trials, len(r_best),
                                       periods_per_year, skew, ekurt)

    result = {
        "n_periods": T, "n_strategies": N, "n_trials": trials,
        "best_strategy": str(best_col), "best_sharpe": round(best_sr, 3),
        "dsr": round(dsr, 4), "expected_max_sharpe": round(e_max, 3),
    }
    if N >= 2:
        result["pbo_analysis"] = compute_pbo(R, periods_per_year=periods_per_year)
    return result


def print_report(res: dict):
    print("\n" + "=" * 62)
    print("  🔍 バックテスト過学習チェック結果")
    print("=" * 62)
    print(f"  データ:          {res['n_periods']} 期間 × {res['n_strategies']} 戦略")
    print(f"  申告試行数:      {res['n_trials']:,}")
    print(f"  最良戦略:        {res['best_strategy']}（シャープ {res['best_sharpe']}）")
    print()
    dsr, e_max = res["dsr"], res["expected_max_sharpe"]
    verdict = "✅ 統計的に有意" if dsr >= 0.95 else \
              "⚠️  境界的" if dsr >= 0.80 else \
              "❌ ノイズと区別できない"
    print(f"  ── DSR（多重テスト補正後の有意性）──────────────")
    print(f"  DSR:             {dsr:.4f}  {verdict}")
    print(f"  ノイズ期待最大:  シャープ {e_max:.3f}"
          f"（{res['n_trials']:,}回試せば運だけでここまで出る）")

    pbo_res = res.get("pbo_analysis")
    if pbo_res and "error" not in pbo_res:
        pbo = pbo_res["pbo"]
        verdict2 = "✅ 過学習リスク低い" if pbo < 0.2 else \
                   "⚠️  境界的" if pbo < 0.5 else \
                   "❌ 過学習の可能性大"
        print()
        print(f"  ── PBO / CSCV（{pbo_res['n_splits']}通りの擬似歴史パス）────────")
        print(f"  PBO:             {pbo:.3f}  {verdict2}")
        print(f"     → 訓練1位の戦略がテストで下位半分に落ちる確率")
        print(f"  IS→OOSスロープ:  {pbo_res['is_oos_slope']:+.3f}"
              f"  {'✅ 健全' if pbo_res['is_oos_slope'] > 0 else '❌ 訓練で良いほどテストで悪い'}")
        print(f"  IS最良のOOSシャープ: {pbo_res['mean_oos_sharpe_of_is_best']:+.3f}")
    elif pbo_res:
        print(f"\n  PBO: 計算不可（{pbo_res['error']}）")
    else:
        print(f"\n  PBO: 単一戦略のためスキップ（パラメータ探索の全結果を渡すと計算できます）")
    print("=" * 62)
    print("  ※ 本ツールは統計的検証の道具であり、投資助言ではありません。")
    print("=" * 62 + "\n")


# ── デモ ─────────────────────────────────────────────────────────────────────
def run_demo():
    """優位性ゼロのランダム戦略100個を生成し、正しく「ノイズ」と判定されるか実演。"""
    print("\n📊 デモ: 優位性ゼロのランダム戦略100個（月次10年分）を生成します。")
    print("   正しく動いていれば「❌ ノイズ」と判定されるはずです。")
    rng = np.random.default_rng(42)
    df = pd.DataFrame(rng.normal(0.004, 0.04, (120, 100)),
                      columns=[f"strategy_{i}" for i in range(100)])
    res = verify(df)
    print_report(res)
    print("  💡 実際の相場でも、100回パラメータを試せばシャープ"
          f"{res['expected_max_sharpe']}程度の「見かけの勝者」が運だけで生まれます。")
    print("     あなたのバックテストの数字は、この水準を超えていますか？\n")


# ── メイン ───────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description="バックテスト過学習チェッカー")
    p.add_argument("csv", nargs="?", help="リターン行列CSV（行=期間、列=戦略）")
    p.add_argument("--trials", type=int, default=None,
                   help="試した戦略・パラメータの総数（単一列のとき必須級）")
    p.add_argument("--equity", action="store_true",
                   help="CSVが資産曲線（金額）の場合に指定（リターンに変換）")
    p.add_argument("--freq", choices=["monthly", "daily", "weekly"], default="monthly",
                   help="データの頻度（年率換算に使用。デフォルト: monthly）")
    p.add_argument("--demo", action="store_true", help="ランダム戦略でのデモ実行")
    args = p.parse_args()

    if args.demo:
        run_demo()
        return
    if not args.csv:
        p.print_help()
        sys.exit(1)

    df = pd.read_csv(args.csv)
    # 先頭列が日付らしければインデックスへ
    first = df.columns[0]
    if df[first].dtype == object:
        try:
            df[first] = pd.to_datetime(df[first])
            df = df.set_index(first)
        except (ValueError, TypeError):
            pass
    df = df.apply(pd.to_numeric, errors="coerce").dropna(how="all")
    df = df.dropna(axis=1, how="all")   # 数値化できなかった列（日付の残骸など）を除去

    if args.equity:
        df = df.pct_change().dropna(how="all")

    ppy = {"monthly": 12, "daily": 252, "weekly": 52}[args.freq]
    res = verify(df, n_trials=args.trials, periods_per_year=ppy)
    print_report(res)


if __name__ == "__main__":
    main()
