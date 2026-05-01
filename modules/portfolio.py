import numpy as np
import pandas as pd
from scipy.optimize import minimize


def fetch_returns(tickers_df_map: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """複数銘柄の終値からリターン系列を生成"""
    closes = {}
    for ticker, df in tickers_df_map.items():
        closes[ticker] = df["Close"]
    prices = pd.DataFrame(closes).dropna()
    return prices.pct_change().dropna()


def correlation_matrix(returns: pd.DataFrame) -> pd.DataFrame:
    return returns.corr()


def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Kelly基準: f = (bp - q) / b
      b = 平均利益/平均損失
      p = 勝率
      q = 1 - p
    """
    if avg_loss == 0:
        return 0.0
    b = avg_win / abs(avg_loss)
    p = win_rate / 100
    q = 1 - p
    f = (b * p - q) / b
    return max(0.0, min(f, 1.0))


def min_variance_weights(returns: pd.DataFrame) -> np.ndarray:
    """最小分散ポートフォリオ（等リスク近似）"""
    n = len(returns.columns)
    cov = returns.cov().values * 252

    def portfolio_variance(w):
        return w @ cov @ w

    constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1}
    bounds = [(0.0, 1.0)] * n
    w0 = np.ones(n) / n
    result = minimize(portfolio_variance, w0, method="SLSQP",
                      bounds=bounds, constraints=constraints)
    return result.x if result.success else w0


def portfolio_stats(weights: np.ndarray, returns: pd.DataFrame) -> dict:
    ann_returns = returns.mean() * 252
    cov = returns.cov() * 252
    port_return = weights @ ann_returns.values
    port_vol = np.sqrt(weights @ cov.values @ weights)
    sharpe = port_return / port_vol if port_vol > 0 else 0
    return {
        "期待リターン(%)": round(port_return * 100, 2),
        "リスク（年率ボラ%）": round(port_vol * 100, 2),
        "シャープレシオ": round(sharpe, 2),
    }


def build_portfolio_summary(
    tickers: list[str],
    tickers_df_map: dict[str, pd.DataFrame],
    trade_history_df: pd.DataFrame | None = None,
) -> dict:
    returns = fetch_returns(tickers_df_map)
    if returns.empty or len(returns.columns) < 2:
        return {"error": "2銘柄以上のデータが必要です"}

    corr = correlation_matrix(returns)
    weights_mv = min_variance_weights(returns)
    weights_eq = np.ones(len(tickers)) / len(tickers)

    stats_mv = portfolio_stats(weights_mv, returns)
    stats_eq = portfolio_stats(weights_eq, returns)

    # ケリー基準（取引履歴があれば計算）
    kelly_results = {}
    if trade_history_df is not None and not trade_history_df.empty:
        for ticker in tickers:
            t_df = trade_history_df[trade_history_df["ticker"] == ticker]
            sells = t_df[t_df["action"].isin(["売り"])]
            if not sells.empty and "損益" in sells.columns:
                wins = sells[sells["損益"] > 0]["損益"]
                losses = sells[sells["損益"] <= 0]["損益"]
                if len(sells) > 0:
                    wr = len(wins) / len(sells) * 100
                    avg_w = wins.mean() if len(wins) > 0 else 0
                    avg_l = losses.mean() if len(losses) > 0 else 0
                    kelly_results[ticker] = kelly_fraction(wr, avg_w, abs(avg_l))

    return {
        "returns": returns,
        "corr": corr,
        "tickers": list(returns.columns),
        "weights_min_var": dict(zip(returns.columns, [round(w, 4) for w in weights_mv])),
        "weights_equal": dict(zip(returns.columns, [round(w, 4) for w in weights_eq])),
        "stats_min_var": stats_mv,
        "stats_equal": stats_eq,
        "kelly": kelly_results,
    }
