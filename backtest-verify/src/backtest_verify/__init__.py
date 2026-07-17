"""backtest-verify: statistical overfitting detection for trading strategy backtests."""

from .core import compute_pbo, deflated_sharpe_ratio, verify

__version__ = "0.1.0"
__all__ = ["verify", "deflated_sharpe_ratio", "compute_pbo", "__version__"]
