"""
Core statistical methods for backtest overfitting detection.

Implements:
- Deflated Sharpe Ratio (DSR):
    Bailey & Lopez de Prado (2014), "The Deflated Sharpe Ratio:
    Correcting for Selection Bias, Backtest Overfitting and Non-Normality"
- Probability of Backtest Overfitting (PBO) via CSCV:
    Bailey, Borwein, Lopez de Prado & Zhu (2015),
    "The Probability of Backtest Overfitting"
"""

from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats


def deflated_sharpe_ratio(sr_annualized: float, n_trials: int, n_obs: int,
                          periods_per_year: int = 12,
                          skew: float = 0.0, excess_kurt: float = 0.0) -> tuple:
    """
    Probability that the true Sharpe ratio exceeds zero, after correcting
    for the number of strategies tried (multiple testing).

    Parameters
    ----------
    sr_annualized : annualized Sharpe ratio of the best strategy
    n_trials : total number of strategy/parameter combinations tried
    n_obs : number of return observations for the best strategy
    periods_per_year : 12 for monthly, 252 for daily, 52 for weekly
    skew, excess_kurt : higher moments of the return series

    Returns
    -------
    (dsr, expected_max_sharpe)
        dsr >= 0.95 is the conventional significance threshold.
        expected_max_sharpe is the annualized Sharpe that pure noise is
        expected to produce as the best of n_trials attempts.
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


def compute_pbo(returns: np.ndarray, n_blocks: int = 12,
                periods_per_year: int = 12) -> dict:
    """
    Probability of Backtest Overfitting via Combinatorially Symmetric
    Cross-Validation (CSCV).

    Parameters
    ----------
    returns : T x N array (T periods, N strategies)
    n_blocks : number of time blocks (default 12 -> C(12,6)=924 splits)

    Returns
    -------
    dict with keys: pbo, n_splits, is_oos_slope, mean_oos_sharpe_of_is_best
    or {"error": str} if the input is too small.
    """
    T, N = returns.shape
    if T < n_blocks * 2 or N < 2:
        return {"error": f"insufficient data ({T} periods x {N} strategies; "
                         f"need >= {n_blocks * 2} periods and >= 2 strategies)"}

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
        "mean_oos_sharpe_of_is_best":
            float(np.nanmean(pairs[finite, 1])) if finite.any() else float("nan"),
    }


def verify(returns_df: pd.DataFrame, n_trials: int = None,
           periods_per_year: int = 12) -> dict:
    """
    Run the full verification battery on a returns DataFrame.

    Parameters
    ----------
    returns_df : rows = periods, columns = strategies (1 column allowed)
    n_trials : total number of strategies tried; defaults to column count
    periods_per_year : 12 monthly / 252 daily / 52 weekly

    Returns
    -------
    dict with best-strategy stats, DSR, expected max Sharpe, and (when
    2+ columns are given) a "pbo_analysis" sub-dict.
    """
    R = returns_df.to_numpy(dtype=float)
    R = R[~np.isnan(R).all(axis=1)]
    T, N = R.shape
    trials = n_trials if n_trials else N

    mu, sd = np.nanmean(R, axis=0), np.nanstd(R, axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        sharpes = np.where(sd > 0, mu / sd * np.sqrt(periods_per_year), -np.inf)
    best_i = int(np.argmax(sharpes))
    best_sr = float(sharpes[best_i])

    r_best = R[:, best_i]
    r_best = r_best[~np.isnan(r_best)]
    skew = float(stats.skew(r_best)) if len(r_best) > 3 else 0.0
    ekurt = float(stats.kurtosis(r_best)) if len(r_best) > 3 else 0.0

    dsr, e_max = deflated_sharpe_ratio(best_sr, trials, len(r_best),
                                       periods_per_year, skew, ekurt)

    result = {
        "n_periods": T,
        "n_strategies": N,
        "n_trials": trials,
        "best_strategy": str(returns_df.columns[best_i]),
        "best_sharpe": round(best_sr, 3),
        "dsr": round(dsr, 4),
        "expected_max_sharpe": round(e_max, 3),
    }
    if N >= 2:
        result["pbo_analysis"] = compute_pbo(R, periods_per_year=periods_per_year)
    return result
