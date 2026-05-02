import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score
import warnings
warnings.filterwarnings("ignore")


def _build_features(df: pd.DataFrame) -> pd.DataFrame:
    """テクニカル指標からMLの特徴量を生成"""
    feat = pd.DataFrame(index=df.index)

    # モメンタム系
    feat["rsi"] = df.get("RSI", np.nan)
    feat["stoch_k"] = df.get("Stoch_K", np.nan)
    feat["stoch_d"] = df.get("Stoch_D", np.nan)

    # トレンド系
    for col in ["SMA25", "SMA75"]:
        if col in df.columns:
            feat[f"{col}_ratio"] = df["Close"] / df[col] - 1  # 乖離率

    # MACD
    if "MACD_hist" in df.columns:
        feat["macd_hist"] = df["MACD_hist"]
        feat["macd_hist_diff"] = df["MACD_hist"].diff()

    # ボリンジャーバンド
    if "BB_pct" in df.columns:
        feat["bb_pct"] = df["BB_pct"]

    # ボラティリティ
    if "ATR" in df.columns:
        feat["atr_ratio"] = df["ATR"] / df["Close"]  # ATR÷価格

    # 出来高変化
    if "Volume" in df.columns:
        feat["volume_ratio"] = df["Volume"] / df["Volume"].rolling(20).mean()

    # 価格モメンタム（1/3/5日リターン）
    for d in [1, 3, 5]:
        feat[f"ret_{d}d"] = df["Close"].pct_change(d)

    # 一目均衡表（雲との位置関係）
    if "Ichimoku_senkou_a" in df.columns and "Ichimoku_senkou_b" in df.columns:
        cloud_top = df[["Ichimoku_senkou_a", "Ichimoku_senkou_b"]].max(axis=1)
        cloud_bot = df[["Ichimoku_senkou_a", "Ichimoku_senkou_b"]].min(axis=1)
        feat["above_cloud"] = (df["Close"] > cloud_top).astype(float)
        feat["cloud_dist"] = (df["Close"] - cloud_top) / df["Close"]

    return feat.ffill().bfill()


def _build_target(df: pd.DataFrame, horizon: int = 5) -> pd.Series:
    """N日後のリターンが正なら1、負なら0"""
    future_ret = df["Close"].pct_change(horizon).shift(-horizon)
    return (future_ret > 0).astype(int)


def train_model(df: pd.DataFrame, horizon: int = 5) -> dict:
    """
    RandomForest + GradientBoosting のアンサンブルを時系列交差検証で学習
    Returns: モデル情報・精度・特徴量重要度
    """
    features = _build_features(df)
    target = _build_target(df, horizon)

    # NaN除去・整合
    combined = pd.concat([features, target.rename("target")], axis=1).dropna()
    if len(combined) < 60:
        return {"error": "データが少なすぎます（最低60日分必要）"}

    X = combined.drop("target", axis=1).values
    y = combined["target"].values
    feat_names = combined.drop("target", axis=1).columns.tolist()

    # 時系列分割（最後の20%をテスト）
    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    # モデル学習
    rf = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42, n_jobs=-1)
    gb = GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=42)

    rf.fit(X_train_s, y_train)
    gb.fit(X_train_s, y_train)

    rf_acc = accuracy_score(y_test, rf.predict(X_test_s))
    gb_acc = accuracy_score(y_test, gb.predict(X_test_s))

    # アンサンブル予測（最新データ）
    X_latest = scaler.transform(X[-1:])
    rf_prob = rf.predict_proba(X_latest)[0][1]
    gb_prob = gb.predict_proba(X_latest)[0][1]
    ensemble_prob = (rf_prob + gb_prob) / 2

    # 信頼度換算（50%を中心にして0-100%スケールに変換）
    confidence = abs(ensemble_prob - 0.5) * 200  # 0〜100%

    if ensemble_prob >= 0.55:
        ml_verdict = "上昇傾向"
        ml_color = "#26a69a"
    elif ensemble_prob <= 0.45:
        ml_verdict = "下落傾向"
        ml_color = "#ef5350"
    else:
        ml_verdict = "方向感なし"
        ml_color = "#ffd54f"

    # 特徴量重要度（RFとGBの平均）
    importance = (rf.feature_importances_ + gb.feature_importances_) / 2
    feat_importance = pd.Series(importance, index=feat_names).sort_values(ascending=False)

    return {
        "ml_verdict": ml_verdict,
        "ml_color": ml_color,
        "up_probability": round(ensemble_prob * 100, 1),
        "confidence": round(confidence, 1),
        "rf_accuracy": round(rf_acc * 100, 1),
        "gb_accuracy": round(gb_acc * 100, 1),
        "ensemble_accuracy": round((rf_acc + gb_acc) / 2 * 100, 1),
        "horizon_days": horizon,
        "feature_importance": feat_importance.head(8),
        "error": None,
    }


def trend_regression(df: pd.DataFrame, window: int = 20) -> dict:
    """直近N日の価格トレンドを線形回帰で定量化"""
    prices = df["Close"].tail(window).values
    x = np.arange(len(prices)).reshape(-1, 1)

    reg = LinearRegression()
    reg.fit(x, prices)

    slope = reg.coef_[0]
    r2 = reg.score(x, prices)

    # 傾きを日次変化率に変換
    slope_pct = slope / prices[0] * 100

    if slope_pct > 0.3 and r2 > 0.5:
        trend = "強い上昇トレンド"
        trend_color = "#26a69a"
    elif slope_pct > 0 and r2 > 0.3:
        trend = "緩やかな上昇"
        trend_color = "#80cbc4"
    elif slope_pct < -0.3 and r2 > 0.5:
        trend = "強い下落トレンド"
        trend_color = "#ef5350"
    elif slope_pct < 0 and r2 > 0.3:
        trend = "緩やかな下落"
        trend_color = "#ef9a9a"
    else:
        trend = "横ばい（トレンドなし）"
        trend_color = "#ffd54f"

    # 回帰ラインの予測値（チャート用）
    predicted = reg.predict(x)

    return {
        "trend": trend,
        "trend_color": trend_color,
        "slope_pct_per_day": round(slope_pct, 3),
        "r2": round(r2, 3),
        "predicted": predicted,
        "window": window,
    }


def detect_candlestick_patterns(df: pd.DataFrame) -> list[dict]:
    """主要なローソク足パターンを検出"""
    patterns = []
    if len(df) < 3:
        return patterns

    o, h, l, c = df["Open"], df["High"], df["Low"], df["Close"]

    # 直近3本を使用
    for i in range(-3, 0):
        idx = df.index[i]
        body = abs(c.iloc[i] - o.iloc[i])
        upper_shadow = h.iloc[i] - max(c.iloc[i], o.iloc[i])
        lower_shadow = min(c.iloc[i], o.iloc[i]) - l.iloc[i]
        total_range = h.iloc[i] - l.iloc[i]
        if total_range == 0:
            continue

        # ハンマー（下ヒゲが長い → 反転上昇シグナル）
        if lower_shadow > body * 2 and upper_shadow < body * 0.5:
            patterns.append({
                "パターン": "🔨 ハンマー",
                "日付": str(idx)[:10],
                "意味": "下落後の反転上昇シグナル",
                "方向": "買い"
            })

        # 流れ星（上ヒゲが長い → 反転下落シグナル）
        if upper_shadow > body * 2 and lower_shadow < body * 0.5:
            patterns.append({
                "パターン": "⭐ 流れ星",
                "日付": str(idx)[:10],
                "意味": "上昇後の反転下落シグナル",
                "方向": "売り"
            })

        # 十字線（ドージ: 迷い → トレンド転換の可能性）
        if body < total_range * 0.1:
            patterns.append({
                "パターン": "✚ 十字線（ドージ）",
                "日付": str(idx)[:10],
                "意味": "売買が拮抗、トレンド転換の可能性",
                "方向": "中立"
            })

    # 包み足（直近2本）
    if len(df) >= 2:
        if (o.iloc[-1] < c.iloc[-2] and c.iloc[-1] > o.iloc[-2] and
                c.iloc[-1] > o.iloc[-1]):
            patterns.append({
                "パターン": "📈 陽の包み足",
                "日付": str(df.index[-1])[:10],
                "意味": "前日を完全に包む上昇、強い買いシグナル",
                "方向": "買い"
            })
        if (o.iloc[-1] > c.iloc[-2] and c.iloc[-1] < o.iloc[-2] and
                c.iloc[-1] < o.iloc[-1]):
            patterns.append({
                "パターン": "📉 陰の包み足",
                "日付": str(df.index[-1])[:10],
                "意味": "前日を完全に包む下落、強い売りシグナル",
                "方向": "売り"
            })

    return patterns
