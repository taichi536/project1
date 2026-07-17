"""Command-line interface for backtest-verify."""

import argparse
import sys

import numpy as np
import pandas as pd

from .core import verify


def print_report(res: dict):
    print("\n" + "=" * 62)
    print("  backtest-verify : overfitting check report")
    print("=" * 62)
    print(f"  Data:              {res['n_periods']} periods x {res['n_strategies']} strategies")
    print(f"  Declared trials:   {res['n_trials']:,}")
    print(f"  Best strategy:     {res['best_strategy']} (Sharpe {res['best_sharpe']})")
    print()
    dsr, e_max = res["dsr"], res["expected_max_sharpe"]
    verdict = "PASS  (statistically significant)" if dsr >= 0.95 else \
              "WARN  (borderline)" if dsr >= 0.80 else \
              "FAIL  (indistinguishable from noise)"
    print(f"  -- DSR (Deflated Sharpe Ratio) ------------------------")
    print(f"  DSR:               {dsr:.4f}  {verdict}")
    print(f"  Noise ceiling:     Sharpe {e_max:.3f} "
          f"(what pure luck yields as the best of {res['n_trials']:,} trials)")

    pbo_res = res.get("pbo_analysis")
    if pbo_res and "error" not in pbo_res:
        pbo = pbo_res["pbo"]
        verdict2 = "PASS  (low overfitting risk)" if pbo < 0.2 else \
                   "WARN  (borderline)" if pbo < 0.5 else \
                   "FAIL  (likely overfit)"
        print()
        print(f"  -- PBO / CSCV ({pbo_res['n_splits']} pseudo-history splits) ------")
        print(f"  PBO:               {pbo:.3f}  {verdict2}")
        print(f"     -> probability the in-sample winner falls into the")
        print(f"        bottom half out-of-sample")
        slope = pbo_res["is_oos_slope"]
        print(f"  IS->OOS slope:     {slope:+.3f}  "
              f"{'(healthy)' if slope > 0 else '(better in-sample => worse out-of-sample)'}")
        print(f"  OOS Sharpe of IS best: {pbo_res['mean_oos_sharpe_of_is_best']:+.3f}")
    elif pbo_res:
        print(f"\n  PBO: not computed ({pbo_res['error']})")
    else:
        print(f"\n  PBO: skipped for a single strategy "
              f"(pass the full parameter-sweep matrix to enable it)")
    print("=" * 62)
    print("  This tool performs statistical verification only.")
    print("  It is not investment advice.")
    print("=" * 62 + "\n")


def run_demo():
    """Generate 100 zero-edge random strategies and show they get flagged."""
    print("\nDemo: generating 100 random strategies with ZERO real edge")
    print("(10 years of monthly returns). A correct checker must FAIL them.")
    rng = np.random.default_rng(42)
    df = pd.DataFrame(rng.normal(0.004, 0.04, (120, 100)),
                      columns=[f"strategy_{i}" for i in range(100)])
    res = verify(df)
    print_report(res)
    print(f"  Takeaway: try 100 parameter sets on real markets and pure luck")
    print(f"  will hand you a Sharpe of ~{res['expected_max_sharpe']}.")
    print(f"  Does your backtest clear that bar?\n")


def main():
    p = argparse.ArgumentParser(
        prog="backtest-verify",
        description="Statistical overfitting detection for trading strategy backtests",
    )
    p.add_argument("csv", nargs="?",
                   help="CSV of returns (rows = periods, columns = strategies)")
    p.add_argument("--trials", type=int, default=None,
                   help="total number of strategies/parameter sets tried "
                        "(be honest - the verdict depends on it)")
    p.add_argument("--equity", action="store_true",
                   help="input is an equity curve (converted to returns)")
    p.add_argument("--freq", choices=["monthly", "daily", "weekly"],
                   default="monthly", help="data frequency (default: monthly)")
    p.add_argument("--demo", action="store_true",
                   help="run the random-strategy demo")
    args = p.parse_args()

    if args.demo:
        run_demo()
        return
    if not args.csv:
        p.print_help()
        sys.exit(1)

    df = pd.read_csv(args.csv)
    first = df.columns[0]
    if df[first].dtype == object:
        try:
            df[first] = pd.to_datetime(df[first])
            df = df.set_index(first)
        except (ValueError, TypeError):
            pass
    df = df.apply(pd.to_numeric, errors="coerce").dropna(how="all")
    df = df.dropna(axis=1, how="all")

    if args.equity:
        df = df.pct_change().dropna(how="all")

    ppy = {"monthly": 12, "daily": 252, "weekly": 52}[args.freq]
    res = verify(df, n_trials=args.trials, periods_per_year=ppy)
    print_report(res)


if __name__ == "__main__":
    main()
