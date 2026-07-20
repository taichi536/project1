"""Selection verification: must fail lucky winners AND pass real ones."""

import numpy as np
import pandas as pd
import pytest

from backtest_verify import verify_selection


@pytest.fixture
def rng():
    return np.random.default_rng(7)


def test_no_difference_candidates_fail(rng):
    """50 hyperparameter configs with identical true performance:
    the apparent winner must be flagged as luck."""
    scores = pd.DataFrame(rng.normal(0.80, 0.03, (10, 50)),
                          columns=[f"cfg_{i}" for i in range(50)])
    res = verify_selection(scores)
    assert res["selection_p_value"] > 0.20


def test_genuinely_better_model_passes(rng):
    """One model 5 points better than the rest across 20 folds."""
    scores = {f"cfg_{i}": rng.normal(0.80, 0.02, 20) for i in range(19)}
    scores["good"] = rng.normal(0.85, 0.02, 20)
    res = verify_selection(pd.DataFrame(scores))
    assert res["best_candidate"] == "good"
    assert res["selection_p_value"] < 0.05
    assert res["pbo"] is not None and res["pbo"] < 0.2


def test_lower_is_better(rng):
    """Loss metric: the LOWEST-loss model must be picked as winner."""
    scores = {f"cfg_{i}": rng.normal(0.50, 0.02, 20) for i in range(10)}
    scores["good"] = rng.normal(0.40, 0.02, 20)
    res = verify_selection(pd.DataFrame(scores), higher_is_better=False)
    assert res["best_candidate"] == "good"
    assert res["selection_p_value"] < 0.05
    assert res["best_mean"] == pytest.approx(0.40, abs=0.02)


def test_reproducible(rng):
    scores = pd.DataFrame(rng.normal(0, 1, (12, 8)))
    r1 = verify_selection(scores, seed=42)
    r2 = verify_selection(scores, seed=42)
    assert r1["selection_p_value"] == r2["selection_p_value"]


def test_insufficient_data():
    assert "error" in verify_selection(pd.DataFrame(np.zeros((2, 5))))
    assert "error" in verify_selection(pd.DataFrame(np.zeros((10, 1))))
