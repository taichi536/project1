# backtest-verify

**Is your backtest real, or did you just get lucky?**

`backtest-verify` is a statistical overfitting checker for trading strategy
backtests. Feed it your strategy returns and it tells you whether the results
are distinguishable from noise — using the methods quantitative finance
actually uses:

- **DSR — Deflated Sharpe Ratio** (Bailey & López de Prado, 2014):
  corrects the Sharpe ratio for how many strategies you tried before
  finding this one.
- **PBO — Probability of Backtest Overfitting via CSCV** (Bailey, Borwein,
  López de Prado & Zhu, 2015): splits history into 924 pseudo-paths and
  measures how often your in-sample winner collapses out-of-sample.

## Why

Try 100 parameter combinations on random data and the best one will show a
Sharpe ratio around **2.5 — with zero real edge**. Most published backtests
never account for this. This tool does.

```
$ backtest-verify --demo

  Data:              120 periods x 100 strategies
  Best strategy:     strategy_57 (Sharpe 0.974)
  DSR:               0.0000  FAIL  (indistinguishable from noise)
  Noise ceiling:     Sharpe 2.531 (what pure luck yields as the best of 100 trials)
  PBO:               0.344   WARN  (borderline)
  IS->OOS slope:     -0.624  (better in-sample => worse out-of-sample)
```

It is calibrated in both directions: pure noise fails, while a strategy with
genuine alpha passes (DSR 1.0, PBO 0.0) — verified in the test suite.

## Install

```bash
pip install .          # from a local clone
```

## Usage

```bash
# Best: verify the FULL parameter sweep (each column = one combination)
backtest-verify returns_matrix.csv

# Single strategy: declare how many things you tried before settling on it
backtest-verify my_strategy.csv --trials 100

# Equity curves (account values) instead of returns
backtest-verify equity.csv --equity

# Daily data
backtest-verify returns.csv --freq daily
```

Or from Python:

```python
import pandas as pd
from backtest_verify import verify

returns = pd.read_csv("returns_matrix.csv", index_col=0)
result = verify(returns, periods_per_year=12)
print(result["dsr"], result["pbo_analysis"]["pbo"])
```

## Reading the verdict

| Metric | Pass | Borderline | Fail |
|---|---|---|---|
| DSR | ≥ 0.95 | 0.80–0.95 | < 0.80 |
| PBO | < 0.2 | 0.2–0.5 | > 0.5 |
| IS→OOS slope | > 0 | — | < 0 |

**Honesty matters**: the DSR verdict depends on `--trials`. If you tested
500 parameter combinations and only report the winner with `--trials 1`,
the tool cannot save you.

## Disclaimer

This tool performs statistical verification only. It is **not investment
advice** and does not recommend buying or selling any financial instrument.

---

## 日本語

**あなたのバックテスト、本物ですか？それともただの運ですか？**

`backtest-verify` は投資戦略バックテストの過学習を統計的に検出するツールです。

- **DSR（偏向シャープ比）**: 「何通り試したか」を考慮してシャープ比を補正
- **PBO（バックテスト過学習確率）**: 歴史を924通りに分割し、訓練期の勝者が
  テスト期に崩れる確率を測定

ランダムなデータでも100回パラメータを試せば、シャープ比2.5程度の「見かけの
勝者」が運だけで生まれます。本ツールはその水準（ノイズ天井）とあなたの結果を
比較します。

```bash
backtest-verify returns_matrix.csv           # パラメータ探索の全結果（推奨）
backtest-verify my_strategy.csv --trials 100 # 単一戦略（試行数を正直に申告）
backtest-verify equity.csv --equity          # 資産曲線でもOK
backtest-verify --demo                       # デモ実行
```

**免責**: 本ツールは統計的検証の道具であり、投資助言ではありません。
特定の金融商品の売買を推奨するものではありません。
