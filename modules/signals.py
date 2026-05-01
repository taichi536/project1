import pandas as pd


def _latest(df: pd.DataFrame, col: str):
    return df[col].dropna().iloc[-1] if col in df.columns else None


def evaluate_signals(df: pd.DataFrame, sma_short: int = 25, sma_long: int = 75) -> list[dict]:
    signals = []
    row = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else row

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
                judge, score = "買い", 2
            elif dead:
                judge, score = "売り", -2
            elif sma_s > sma_l:
                judge, score = "強気", 1
            else:
                judge, score = "弱気", -1
        else:
            judge, score = "中立", 0
        signals.append({
            "指標": f"移動平均 (SMA{sma_short}/SMA{sma_long})",
            "値": f"{sma_s:.1f} / {sma_l:.1f}",
            "判定": judge,
            "スコア": score,
        })

    # --- RSI ---
    rsi = _latest(df, "RSI")
    if rsi is not None:
        if rsi < 30:
            judge, score = "買われすぎ（逆張り買い）", 2
        elif rsi < 40:
            judge, score = "やや売られすぎ", 1
        elif rsi > 70:
            judge, score = "売られすぎ（逆張り売り）", -2
        elif rsi > 60:
            judge, score = "やや買われすぎ", -1
        else:
            judge, score = "中立", 0
        signals.append({"指標": "RSI (14)", "値": f"{rsi:.1f}", "判定": judge, "スコア": score})

    # --- MACD ---
    macd = _latest(df, "MACD")
    macd_sig = _latest(df, "MACD_signal")
    macd_hist = _latest(df, "MACD_hist")
    prev_hist = df["MACD_hist"].dropna().iloc[-2] if "MACD_hist" in df.columns and len(df) >= 2 else None
    if macd is not None and macd_sig is not None:
        if macd > macd_sig and prev_hist is not None and prev_hist < 0 and macd_hist > 0:
            judge, score = "ゴールデンクロス（買い）", 2
        elif macd < macd_sig and prev_hist is not None and prev_hist > 0 and macd_hist < 0:
            judge, score = "デッドクロス（売り）", -2
        elif macd > macd_sig:
            judge, score = "上昇トレンド", 1
        else:
            judge, score = "下降トレンド", -1
        signals.append({
            "指標": "MACD",
            "値": f"{macd:.3f} / シグナル {macd_sig:.3f}",
            "判定": judge,
            "スコア": score,
        })

    # --- ボリンジャーバンド ---
    bb_pct = _latest(df, "BB_pct")
    if bb_pct is not None:
        if bb_pct < 0:
            judge, score = "下限突破（反発期待）", 2
        elif bb_pct < 0.2:
            judge, score = "下限付近", 1
        elif bb_pct > 1:
            judge, score = "上限突破（過熱）", -2
        elif bb_pct > 0.8:
            judge, score = "上限付近", -1
        else:
            judge, score = "中央帯", 0
        signals.append({
            "指標": "ボリンジャーバンド",
            "値": f"{bb_pct * 100:.1f}%位置",
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
            judge, score = "雲の上（強気）", 1
        elif close < cloud_bot:
            judge, score = "雲の下（弱気）", -1
        else:
            judge, score = "雲の中（揉み合い）", 0
        signals.append({
            "指標": "一目均衡表（雲）",
            "値": f"株価 {close:.1f} / 雲 {cloud_bot:.1f}〜{cloud_top:.1f}",
            "判定": judge,
            "スコア": score,
        })

    # --- ストキャスティクス ---
    stk = _latest(df, "Stoch_K")
    std = _latest(df, "Stoch_D")
    if stk is not None and std is not None:
        if stk < 20 and stk > std:
            judge, score = "売られすぎ＋反転シグナル", 2
        elif stk < 20:
            judge, score = "売られすぎ圏", 1
        elif stk > 80 and stk < std:
            judge, score = "買われすぎ＋反転シグナル", -2
        elif stk > 80:
            judge, score = "買われすぎ圏", -1
        else:
            judge, score = "中立", 0
        signals.append({
            "指標": "ストキャスティクス",
            "値": f"%K {stk:.1f} / %D {std:.1f}",
            "判定": judge,
            "スコア": score,
        })

    return signals


def overall_signal(signals: list[dict]) -> tuple[str, int]:
    total = sum(s["スコア"] for s in signals)
    max_score = len(signals) * 2
    pct = total / max_score if max_score > 0 else 0
    if pct >= 0.4:
        return "買い", total
    elif pct <= -0.4:
        return "売り", total
    else:
        return "様子見", total
