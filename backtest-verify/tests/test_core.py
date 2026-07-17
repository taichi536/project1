"""Tests: the checker must fail pure noise AND pass genuine alpha."""

import numpy as np
import pandas as pd
import pytest

from backtest_verify import compute_pbo, deflated_sharpe_ratio, verify


@pytest.fixture
def rng():
    return np.random.default_rng(42)


def test_noise_is_flagged(rng):
    """100 zero-edge strategies: DSR must be ~0, PBO elevated."""
    df = pd.DataFrame(rng.normal(0.004, 0.04, (120, 100)))
    res = verify(df)
    assert res["dsr"] < 0.5
    assert res["best_sharpe"] < res["expected_max_sharpe"]
    assert res["pbo_analysis"]["pbo"] > 0.2


def test_genuine_alpha_passes(rng):
    """A planted true-alpha strategy among noise must pass."""
    T = 240
    data = {f"noise_{i}": rng.normal(0.003, 0.04, T) for i in range(19)}
    data["real"] = rng.normal(3.5 / np.sqrt(12) * 0.04, 0.04, T)
    res = verify(pd.DataFrame(data))
    assert res["best_strategy"] == "real"
    assert res["dsr"] >= 0.95
    assert res["pbo_analysis"]["pbo"] < 0.2


def test_single_column_skips_pbo(rng):
    df = pd.DataFrame({"only": rng.normal(0.01, 0.03, 120)})
    res = verify(df, n_trials=50)
    assert "pbo_analysis" not in res
    assert res["n_trials"] == 50


def test_dsr_monotonic_in_trials():
    """More trials -> harder to pass (lower DSR)."""
    d1, _ = deflated_sharpe_ratio(2.0, n_trials=10, n_obs=120)
    d2, _ = deflated_sharpe_ratio(2.0, n_trials=10_000, n_obs=120)
    assert d1 > d2


def test_expected_max_grows_with_trials():
    _, e1 = deflated_sharpe_ratio(1.0, n_trials=10, n_obs=120)
    _, e2 = deflated_sharpe_ratio(1.0, n_trials=1000, n_obs=120)
    assert e2 > e1 > 0


def test_pbo_insufficient_data():
    res = compute_pbo(np.zeros((10, 5)))
    assert "error" in res


def test_dsr_edge_cases():
    assert deflated_sharpe_ratio(1.0, n_trials=1, n_obs=120) == (0.0, 0.0)
    assert deflated_sharpe_ratio(1.0, n_trials=100, n_obs=1) == (0.0, 0.0)
