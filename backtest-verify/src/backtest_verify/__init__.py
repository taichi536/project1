"""backtest-verify: statistical overfitting detection for backtests and model selection."""

from .core import compute_pbo, deflated_sharpe_ratio, verify
from .selection import verify_selection

__version__ = "0.2.0"
__all__ = ["verify", "deflated_sharpe_ratio", "compute_pbo",
           "verify_selection", "__version__"]
