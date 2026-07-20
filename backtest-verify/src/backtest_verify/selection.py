"""
Model / variant selection verification (the ML generalization).

The finance-specific question "is the best backtest real?" generalizes to:
"we evaluated N candidates (models, hyperparameters, ad variants, ...) on T
independent units (CV folds, time blocks, batches) and picked the winner -
is the winner actually better, or just the luckiest of N?"

Methods:
- Permutation luck test: shuffle candidate labels within each row to build
  the null distribution of "best mean score", giving a selection p-value.
- CSCV rank test (Bailey et al. 2015, metric-agnostic form): split rows
  into blocks; over all half/half splits, check whether the in-sample
  winner stays in the top half out-of-sample.
"""

from itertools import combinations

import numpy as np
import pandas as pd


def verify_selection(scores_df: pd.DataFrame,
                     higher_is_better: bool = True,
                     n_blocks: int = None,
                     n_permutations: int = 2000,
                     seed: int = 0) -> dict:
    """
    Verify that the best of N candidates is genuinely better.

    Parameters
    ----------
    scores_df : rows = independent evaluation units (CV folds, time blocks,
        batches, days), columns = candidates. Values = the metric.
    higher_is_better : False for losses/error metrics (RMSE, logloss...)
    n_blocks : CSCV block count; default min(12, n_rows) (>= 6 required)
    n_permutations : permutation-test resamples
    seed : RNG seed for the permutation test (results are reproducible)

    Returns
    -------
    dict with best candidate, selection p-value, PBO, and split stats.
    """
    df = scores_df.apply(pd.to_numeric, errors="coerce").dropna(axis=1, how="all")
    M = df.to_numpy(dtype=float)
    M = M[~np.isnan(M).all(axis=1)]
    if not higher_is_better:
        M = -M
    T, N = M.shape
    if T < 4 or N < 2:
        return {"error": f"insufficient data ({T} units x {N} candidates; "
                         f"need >= 4 units and >= 2 candidates)"}

    col_means = np.nanmean(M, axis=0)
    best_i = int(np.argmax(col_means))
    best_mean = float(col_means[best_i])
    others_mean = float(np.nanmean(np.delete(col_means, best_i)))

    # ── Permutation luck test ────────────────────────────────────────────
    # Null: candidate labels are exchangeable within each row (no candidate
    # is truly better; row-to-row difficulty differences are preserved).
    rng = np.random.default_rng(seed)
    filled = np.where(np.isnan(M), np.nanmean(M), M)
    count = 0
    for _ in range(n_permutations):
        perm = filled.copy()
        for i in range(T):
            rng.shuffle(perm[i])
        if perm.mean(axis=0).max() >= best_mean:
            count += 1
    p_value = (count + 1) / (n_permutations + 1)

    result = {
        "n_units": T,
        "n_candidates": N,
        "best_candidate": str(df.columns[best_i]),
        "best_mean": round(best_mean if higher_is_better else -best_mean, 6),
        "others_mean": round(others_mean if higher_is_better else -others_mean, 6),
        "selection_p_value": round(float(p_value), 4),
    }

    # ── CSCV rank test（metric-agnostic PBO）────────────────────────────
    nb = n_blocks or min(12, T)
    if nb % 2 == 1:
        nb -= 1
    if nb >= 6 and T >= nb:
        bounds = np.linspace(0, T, nb + 1, dtype=int)
        blocks = [np.arange(bounds[b], bounds[b + 1]) for b in range(nb)]

        def _means(rows):
            return np.nanmean(M[rows], axis=0)

        below = 0
        splits = list(combinations(range(nb), nb // 2))
        for is_blk in splits:
            oos_blk = [b for b in range(nb) if b not in is_blk]
            m_is = _means(np.concatenate([blocks[b] for b in is_blk]))
            m_oos = _means(np.concatenate([blocks[b] for b in oos_blk]))
            b = int(np.argmax(m_is))
            if float(np.mean(m_oos <= m_oos[b])) <= 0.5:
                below += 1
        result["pbo"] = round(below / len(splits), 4)
        result["n_splits"] = len(splits)
    else:
        result["pbo"] = None
        result["n_splits"] = 0

    return result
