"""
金融工学リスク指標モジュール

【各手法の有効性と限界】

VaR（バリュー・アット・リスク）:
  有効: 損失リスクを一つの数値で把握できる。損切り幅・ポジションサイズ決定の根拠になる
  限界: 過去の分布が未来も続くと仮定。暴落（テールリスク）を過小評価しやすい
  → CVaRで補完することで実用性が上がる

モンテカルロシミュレーション（幾何ブラウン運動）:
  有効: 「未来は1つではなく幅がある」ことを可視化。過信を防ぐ効果がある
  限界: リターン・ボラティリティが一定と仮定。急変動（決算・ショック）は捉えられない
  → 予測ツールではなくリスク把握ツールとして使う

ボラティリティレジーム:
  有効: 「今は激しい時期か穏やかな時期か」を客観的に判定。ポジションサイズ調整に直結
  限界: 過去のボラティリティが未来を保証しない
  → 最も実用的。エントリー判断の補助に積極的に使える
"""
import numpy as np
import pandas as pd


def calc_var(df: pd.DataFrame) -> dict | None:
    """
    ヒストリカルシミュレーション法によるVaR / CVaR計算

    ヒストリカル法を選ぶ理由:
    正規分布を仮定するパラメトリック法より、実際の分布（裾が厚い）を
    そのまま使うため、より現実的なリスク推定になる。
    """
    returns = df["Close"].pct_change().dropna()
    if len(returns) < 30:
        return None

    price = df["Close"].iloc[-1]

    results = {}
    for cl, label in [(0.95, "95"), (0.99, "99")]:
        var_1d_pct = float(np.percentile(returns, (1 - cl) * 100))
        var_5d_pct = var_1d_pct * np.sqrt(5)
        var_20d_pct = var_1d_pct * np.sqrt(20)
        results[f"var_{label}_1d_pct"] = var_1d_pct
        results[f"var_{label}_5d_pct"] = var_5d_pct
        results[f"var_{label}_20d_pct"] = var_20d_pct
        results[f"var_{label}_1d_yen"] = price * abs(var_1d_pct)
        results[f"var_{label}_5d_yen"] = price * abs(var_5d_pct)

    # CVaR（VaRを超えた損失の平均 = 真のテールリスク）
    threshold_95 = np.percentile(returns, 5)
    tail_returns = returns[returns <= threshold_95]
    results["cvar_95_pct"] = float(tail_returns.mean()) if len(tail_returns) > 0 else results["var_95_1d_pct"]
    results["cvar_95_yen"] = price * abs(results["cvar_95_pct"])

    # 最大ドローダウン（参考）
    cumulative = (1 + returns).cumprod()
    rolling_max = cumulative.cummax()
    drawdown = (cumulative - rolling_max) / rolling_max
    results["max_drawdown"] = float(drawdown.min())

    # 年率シャープレシオ
    ann_return = returns.mean() * 252
    ann_vol = returns.std() * np.sqrt(252)
    results["sharpe"] = float(ann_return / ann_vol) if ann_vol > 0 else 0.0
    results["ann_return"] = float(ann_return)
    results["ann_vol"] = float(ann_vol)
    results["price"] = float(price)

    return results


def monte_carlo(
    df: pd.DataFrame,
    n_simulations: int = 300,
    horizon: int = 30,
) -> dict | None:
    """
    幾何ブラウン運動（GBM）によるモンテカルロシミュレーション

    GBMを選ぶ理由:
    「株価はランダムウォーク + ドリフト」という最もシンプルな仮定。
    より複雑なモデル（GARCH、ジャンプ拡散等）は精度が上がるが、
    パラメータ推定の不確実性も大きくなるため、この規模では GBM が適切。
    """
    returns = df["Close"].pct_change().dropna()
    if len(returns) < 30:
        return None

    mu = float(returns.mean())
    sigma = float(returns.std())
    S0 = float(df["Close"].iloc[-1])

    # GBM: S(t+1) = S(t) * exp((μ - σ²/2)*dt + σ*ε*√dt)
    rng = np.random.default_rng()  # シードなし（毎回異なる結果）
    z = rng.standard_normal((n_simulations, horizon))
    log_returns = (mu - 0.5 * sigma ** 2) + sigma * z
    paths = S0 * np.exp(np.cumsum(log_returns, axis=1))
    # 現在価格を先頭に追加
    paths = np.hstack([np.full((n_simulations, 1), S0), paths])

    final = paths[:, -1]
    pct_profit = float((final > S0).mean())

    return {
        "paths": paths,
        "S0": S0,
        "horizon": horizon,
        "n_simulations": n_simulations,
        "p5":  np.percentile(paths, 5,  axis=0),
        "p25": np.percentile(paths, 25, axis=0),
        "p50": np.percentile(paths, 50, axis=0),
        "p75": np.percentile(paths, 75, axis=0),
        "p95": np.percentile(paths, 95, axis=0),
        "final_p5":    float(np.percentile(final, 5)),
        "final_p25":   float(np.percentile(final, 25)),
        "final_median":float(np.median(final)),
        "final_p75":   float(np.percentile(final, 75)),
        "final_p95":   float(np.percentile(final, 95)),
        "prob_profit": pct_profit,
        "mu_annual":   mu * 252,
        "sigma_annual":sigma * np.sqrt(252),
    }


def volatility_regime(df: pd.DataFrame, lookback: int = 252) -> dict | None:
    """
    現在のボラティリティが過去と比べてどのレベルにあるかを判定

    ボラティリティレジームが重要な理由:
    高ボラティリティ期は同じシグナルでも損失リスクが大きい。
    低ボラティリティ期に積極的、高ボラティリティ期に慎重にすることで
    長期的なリスク調整後リターンが改善する（実証的に支持されている）。
    """
    returns = df["Close"].pct_change().dropna()
    rolling_vol = returns.rolling(20).std() * np.sqrt(252) * 100  # 年率%
    rolling_vol = rolling_vol.dropna()
    if len(rolling_vol) < 20:
        return None

    current_vol = float(rolling_vol.iloc[-1])
    hist = rolling_vol.iloc[-lookback:] if len(rolling_vol) >= lookback else rolling_vol
    pct_rank = float((hist < current_vol).mean() * 100)

    if pct_rank < 25:
        regime = "低ボラティリティ（安定期）"
        color = "#26a69a"
        emoji = "🟢"
        ps = 1.0   # ポジションサイズ係数
        advice = "価格変動が少ない安定期。トレンドが出やすく、シグナルの信頼性が高い時期です。"
        action = "通常サイズでエントリー可。損切り幅は狭めに設定できます。"
    elif pct_rank < 75:
        regime = "通常ボラティリティ"
        color = "#ffd54f"
        emoji = "🟡"
        ps = 0.8
        advice = "標準的な市場環境。通常の判断基準で問題ありません。"
        action = "標準的なポジションサイズ。特別な調整は不要です。"
    elif pct_rank < 90:
        regime = "高ボラティリティ（警戒期）"
        color = "#ff7043"
        emoji = "🟠"
        ps = 0.5
        advice = "値動きが大きい時期。同じシグナルでも損失額が通常の2倍以上になりえます。"
        action = "ポジションを通常の50%以下に抑えることを推奨。損切り幅を広げてください。"
    else:
        regime = "極高ボラティリティ（危険期）"
        color = "#ef5350"
        emoji = "🔴"
        ps = 0.25
        advice = "市場が混乱状態。予測不能な急変動が起きやすい局面です。"
        action = "新規エントリーは控える。既存ポジションのリスク管理を最優先にしてください。"

    return {
        "current_vol": current_vol,
        "pct_rank": pct_rank,
        "regime": regime,
        "color": color,
        "emoji": emoji,
        "position_size_factor": ps,
        "advice": advice,
        "action": action,
        "rolling_vol": rolling_vol,
        "vol_p25": float(hist.quantile(0.25)),
        "vol_p50": float(hist.quantile(0.50)),
        "vol_p75": float(hist.quantile(0.75)),
        "vol_p90": float(hist.quantile(0.90)),
    }
