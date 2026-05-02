import pandas as pd
import numpy as np


def _latest(df: pd.DataFrame, col: str):
    return df[col].dropna().iloc[-1] if col in df.columns else None


def evaluate_signals(df: pd.DataFrame, sma_short: int = 25, sma_long: int = 75) -> list[dict]:
    signals = []
    row = df.iloc[-1]

    # --- 移動平均 ---
    sma_s = _latest(df, f"SMA{sma_short}")
    sma_l = _latest(df, f"SMA{sma_long}")
    if sma_s is not None and sma_l is not None:
        prev_s = df[f"SMA{sma_short}"].dropna().iloc[-2] if len(df) >= 2 else None
        prev_l = df[f"SMA{sma_long}"].dropna().iloc[-2] if len(df) >= 2 else None
        if prev_s is not None and prev_l is not None:
            golden = prev_s < prev_l and sma_s >= sma_l
            dead = prev_s > prev_l and sma_s <= sma_l
            if golden:
                judge, score = "ゴールデンクロス（強い買いサイン）", 2
            elif dead:
                judge, score = "デッドクロス（強い売りサイン）", -2
            elif sma_s > sma_l:
                judge, score = "短期線が長期線の上（上昇局面）", 1
            else:
                judge, score = "短期線が長期線の下（下落局面）", -1
        else:
            judge, score = "計算中", 0
        signals.append({
            "指標": f"移動平均線",
            "値": f"短期 {sma_s:.0f} / 長期 {sma_l:.0f}",
            "判定": judge,
            "スコア": score,
        })

    # --- RSI ---
    rsi = _latest(df, "RSI")
    if rsi is not None:
        if rsi < 25:
            judge, score = "かなり売られすぎ → 反発しやすい", 2
        elif rsi < 40:
            judge, score = "売られすぎ気味 → 買い候補", 1
        elif rsi > 75:
            judge, score = "かなり買われすぎ → 下落しやすい", -2
        elif rsi > 60:
            judge, score = "買われすぎ気味 → 注意", -1
        else:
            judge, score = "中立域（40〜60）", 0
        signals.append({"指標": "RSI（売買過熱感）", "値": f"{rsi:.1f}", "判定": judge, "スコア": score})

    # --- MACD ---
    macd = _latest(df, "MACD")
    macd_sig = _latest(df, "MACD_signal")
    macd_hist = _latest(df, "MACD_hist")
    prev_hist = df["MACD_hist"].dropna().iloc[-2] if "MACD_hist" in df.columns and len(df) >= 2 else None
    if macd is not None and macd_sig is not None:
        if macd > macd_sig and prev_hist is not None and prev_hist < 0 and macd_hist > 0:
            judge, score = "上昇転換シグナル（買い）", 2
        elif macd < macd_sig and prev_hist is not None and prev_hist > 0 and macd_hist < 0:
            judge, score = "下落転換シグナル（売り）", -2
        elif macd > macd_sig:
            judge, score = "上昇の勢いあり", 1
        else:
            judge, score = "下落の勢いあり", -1
        signals.append({
            "指標": "MACD（勢い）",
            "値": f"{macd:.2f} / シグナル {macd_sig:.2f}",
            "判定": judge,
            "スコア": score,
        })

    # --- ボリンジャーバンド ---
    bb_pct = _latest(df, "BB_pct")
    if bb_pct is not None:
        if bb_pct < 0:
            judge, score = "下限を突破 → 強い売られすぎ", 2
        elif bb_pct < 0.2:
            judge, score = "下限付近 → 反発しやすい", 1
        elif bb_pct > 1:
            judge, score = "上限を突破 → 強い買われすぎ", -2
        elif bb_pct > 0.8:
            judge, score = "上限付近 → 下落しやすい", -1
        else:
            judge, score = "中央帯（方向感なし）", 0
        signals.append({
            "指標": "ボリンジャーバンド",
            "値": f"上下帯の{bb_pct * 100:.0f}%位置",
            "判定": judge,
            "スコア": score,
        })

    # --- 一目均衡表（雲） ---
    sa = _latest(df, "Ichimoku_senkou_a")
    sb = _latest(df, "Ichimoku_senkou_b")
    close = row["Close"]
    if sa is not None and sb is not None:
        cloud_top = max(sa, sb)
        cloud_bot = min(sa, sb)
        if close > cloud_top:
            judge, score = "雲の上 → 強い上昇トレンド", 1
        elif close < cloud_bot:
            judge, score = "雲の下 → 強い下落トレンド", -1
        else:
            judge, score = "雲の中 → 方向感なし", 0
        signals.append({
            "指標": "一目均衡表（雲）",
            "値": f"雲 {cloud_bot:.0f}〜{cloud_top:.0f} / 現在値 {close:.0f}",
            "判定": judge,
            "スコア": score,
        })

    # --- ストキャスティクス ---
    stk = _latest(df, "Stoch_K")
    std = _latest(df, "Stoch_D")
    if stk is not None and std is not None:
        if stk < 20 and stk > std:
            judge, score = "売られすぎ＋上昇転換", 2
        elif stk < 20:
            judge, score = "売られすぎ圏", 1
        elif stk > 80 and stk < std:
            judge, score = "買われすぎ＋下落転換", -2
        elif stk > 80:
            judge, score = "買われすぎ圏", -1
        else:
            judge, score = "中立", 0
        signals.append({
            "指標": "ストキャスティクス",
            "値": f"%K {stk:.0f} / %D {std:.0f}",
            "判定": judge,
            "スコア": score,
        })

    return signals


def overall_signal(signals: list[dict]) -> tuple[str, int]:
    total = sum(s["スコア"] for s in signals)
    max_score = len(signals) * 2
    pct = total / max_score if max_score > 0 else 0
    # 閾値を30%に下げて感度を上げる
    if pct >= 0.3:
        return "買い", total
    elif pct <= -0.3:
        return "売り", total
    else:
        return "様子見", total


def generate_action_plan(
    df: pd.DataFrame,
    signals: list[dict],
    verdict: str,
    ticker: str,
) -> dict:
    """初心者向けの具体的な投資プランを生成"""
    close = df["Close"].iloc[-1]
    atr = df["ATR"].dropna().iloc[-1] if "ATR" in df.columns else close * 0.02
    rsi = df["RSI"].dropna().iloc[-1] if "RSI" in df.columns else 50

    # 直近の抵抗線・支持線（簡易：20日高値・安値）
    recent = df.tail(20)
    resistance = recent["High"].max()
    support = recent["Low"].min()

    # エントリー価格
    entry = close

    # 利確ライン（抵抗線 or ATR×3）
    target1 = min(resistance, close + atr * 2)
    target2 = close + atr * 4

    # 損切りライン（支持線 or ATR×1.5）
    stop = max(support, close - atr * 1.5)

    # リスクリワード比
    risk = close - stop
    reward = target1 - close
    rr = reward / risk if risk > 0 else 0

    # 推奨タイミング
    if verdict == "買い":
        timing = "✅ 今が買いのタイミングです"
        timing_detail = "複数の指標が上昇を示しています。エントリーを検討してください。"
    elif verdict == "売り":
        timing = "⚠️ 今は買わずに待ちましょう"
        timing_detail = "下落サインが出ています。保有中なら売りを検討してください。"
    else:
        # 様子見でも「次にどうなったら動くか」を示す
        timing = "⏳ 様子見 — 次のサインを待ちましょう"
        if rsi < 45:
            timing_detail = f"RSIが{rsi:.0f}で低め。このまま下落が続けば買い候補になります。"
        elif rsi > 55:
            timing_detail = f"RSIが{rsi:.0f}で高め。もう少し下がってから買う方が安全です。"
        else:
            timing_detail = "明確なトレンドが出るまで待つのが賢明です。急がないことが大切です。"

    # 「様子見」のときのトリガー条件
    buy_trigger = f"RSIが35以下 かつ 株価が{support:.0f}円付近で反発したとき"
    sell_trigger = f"RSIが70以上 または 株価が{stop:.0f}円を割ったとき"

    return {
        "timing": timing,
        "timing_detail": timing_detail,
        "entry_price": round(entry, 1),
        "target1": round(target1, 1),
        "target2": round(target2, 1),
        "stop_loss": round(stop, 1),
        "risk_reward": round(rr, 2),
        "support": round(support, 1),
        "resistance": round(resistance, 1),
        "buy_trigger": buy_trigger,
        "sell_trigger": sell_trigger,
        "atr": round(atr, 1),
    }
