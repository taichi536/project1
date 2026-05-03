import pandas as pd
import numpy as np


def _latest(df: pd.DataFrame, col: str):
    return df[col].dropna().iloc[-1] if col in df.columns else None


def evaluate_signals(df: pd.DataFrame, sma_short: int = 25, sma_long: int = 75) -> list[dict]:
    signals = []
    row = df.iloc[-1]
    close = row["Close"]

    # --- 移動平均（トレンド方向） ---
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
            "指標": "移動平均線",
            "値": f"短期 {sma_s:.0f} / 長期 {sma_l:.0f}",
            "判定": judge,
            "スコア": score,
        })

    # --- RSI（売買過熱感） ---
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

    # --- MACD（モメンタム変化） ---
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

    # --- ボリンジャーバンド（過熱・反転ゾーン） ---
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

    # --- 一目均衡表（雲）: トレンド強度の確認 ---
    sa = _latest(df, "Ichimoku_senkou_a")
    sb = _latest(df, "Ichimoku_senkou_b")
    if sa is not None and sb is not None:
        cloud_top = max(sa, sb)
        cloud_bot = min(sa, sb)
        cloud_thickness = (cloud_top - cloud_bot) / cloud_bot * 100 if cloud_bot > 0 else 0
        if close > cloud_top:
            judge = f"雲の上 → 強い上昇トレンド（雲厚 {cloud_thickness:.1f}%）"
            score = 2 if cloud_thickness > 3 else 1
        elif close < cloud_bot:
            judge = f"雲の下 → 強い下落トレンド（雲厚 {cloud_thickness:.1f}%）"
            score = -2 if cloud_thickness > 3 else -1
        else:
            judge, score = "雲の中 → 方向感なし（トレンド転換期）", 0
        signals.append({
            "指標": "一目均衡表（雲）",
            "値": f"雲 {cloud_bot:.0f}〜{cloud_top:.0f} / 現在値 {close:.0f}",
            "判定": judge,
            "スコア": score,
        })

    # --- 出来高トレンド（OBV）: ストキャスティクスを置き換え ---
    # ストキャスティクスはRSIと同じ「過熱感」を測定するため重複。
    # OBVは「出来高が価格変動を支持しているか」という独立した情報を提供する。
    obv_series = df["OBV"].dropna() if "OBV" in df.columns else pd.Series(dtype=float)
    if len(obv_series) >= 10:
        obv_recent = obv_series.iloc[-5:].mean()
        obv_prev = obv_series.iloc[-10:-5].mean()
        obv_chg = (obv_recent - obv_prev) / abs(obv_prev) * 100 if obv_prev != 0 else 0
        if obv_chg > 10:
            judge, score = "大口が買い積み増し中 → 強い買い圧力", 2
        elif obv_chg > 3:
            judge, score = "出来高が上昇をサポート → 信頼性高い上昇", 1
        elif obv_chg < -10:
            judge, score = "大口が売り急ぎ中 → 強い売り圧力", -2
        elif obv_chg < -3:
            judge, score = "出来高が下落をサポート → 信頼性高い下落", -1
        else:
            judge, score = "出来高変化なし → 信頼性に欠ける動き", 0
        signals.append({
            "指標": "出来高トレンド（OBV）",
            "値": f"5日平均変化 {obv_chg:+.1f}%",
            "判定": judge,
            "スコア": score,
        })

    # --- VWAP（出来高加重平均: 機関投資家の基準価格） ---
    vwap = _latest(df, "VWAP")
    if vwap is not None:
        pct = (close - vwap) / vwap * 100
        if close > vwap * 1.03:
            judge, score = "VWAPより3%以上高い → 過熱・反落注意", -2
        elif close > vwap * 1.01:
            judge, score = "VWAPより上 → 上昇モメンタム継続", 1
        elif close < vwap * 0.97:
            judge, score = "VWAPより3%以上低い → 割安・反発期待", 2
        elif close < vwap * 0.99:
            judge, score = "VWAPより下 → 下落モメンタム", -1
        else:
            judge, score = "VWAP付近 → 均衡状態", 0
        signals.append({
            "指標": "VWAP（機関投資家の基準価格）",
            "値": f"VWAP {vwap:.1f} / 現在値との乖離 {pct:+.1f}%",
            "判定": judge,
            "スコア": score,
        })

    return signals


def overall_signal(
    signals: list[dict],
    df: pd.DataFrame = None,
    sma_long: int = 75,
) -> tuple[str, int]:
    """
    シグナルを総合判定する。
    dfを渡すとトレンドフィルターが有効になる。

    トレンドフィルターの役割:
    長期移動平均より大幅に下にある銘柄（下落トレンド）で買いシグナルが出ても、
    それは「落ちるナイフをつかむ」リスクが高い。スコアにペナルティを加える。
    """
    total = sum(s["スコア"] for s in signals)
    max_score = len(signals) * 2
    if max_score == 0:
        return "様子見", 0

    # トレンドフィルター
    trend_adj = 0
    if df is not None:
        sma_col = f"SMA{sma_long}"
        _sma = df[sma_col].dropna() if sma_col in df.columns else pd.Series(dtype=float)
        if len(_sma) > 0:
            _gap = (df["Close"].iloc[-1] - _sma.iloc[-1]) / _sma.iloc[-1]
            if _gap < -0.07:
                # 長期MAより7%以上下: 下落トレンド確認 → 買いシグナルに厳しくする
                trend_adj = -2
            elif _gap < -0.03:
                trend_adj = -1
            elif _gap > 0.07:
                # 長期MAより7%以上上: 上昇トレンド確認 → 押し目買いを支持
                trend_adj = 1

    pct = (total + trend_adj) / max_score

    if pct >= 0.30:
        return "買い", total
    elif pct <= -0.30:
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

    recent = df.tail(20)
    resistance = recent["High"].max()
    support = recent["Low"].min()

    entry = close
    target1 = min(resistance, close + atr * 2)
    target2 = close + atr * 4
    stop = max(support, close - atr * 1.5)

    risk = close - stop
    reward = target1 - close
    rr = reward / risk if risk > 0 else 0

    if verdict == "買い":
        timing = "✅ 今が買いのタイミングです"
        timing_detail = "複数の指標が上昇を示しています。エントリーを検討してください。"
    elif verdict == "売り":
        timing = "⚠️ 今は買わずに待ちましょう"
        timing_detail = "下落サインが出ています。保有中なら売りを検討してください。"
    else:
        timing = "⏳ 様子見 — 次のサインを待ちましょう"
        if rsi < 45:
            timing_detail = f"RSIが{rsi:.0f}で低め。このまま下落が続けば買い候補になります。"
        elif rsi > 55:
            timing_detail = f"RSIが{rsi:.0f}で高め。もう少し下がってから買う方が安全です。"
        else:
            timing_detail = "明確なトレンドが出るまで待つのが賢明です。急がないことが大切です。"

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


def evaluate_hold_signal(df: pd.DataFrame, signals: list[dict], verdict: str, sma_long: int = 75) -> dict:
    """
    すでに保有している銘柄に対して「継続保有 or 利確 or 損切り」を判定する。

    新規エントリー判定（overall_signal）とは視点が異なる:
    - 上昇トレンド中でもRSIが高くなければ「まだ伸びる余地あり」と判定
    - 損切りラインを下回った場合は即座に警告
    - 利確ラインに近づいたら段階的な利確を促す
    """
    close = df["Close"].iloc[-1]
    atr = df["ATR"].dropna().iloc[-1] if "ATR" in df.columns else close * 0.02
    rsi = df["RSI"].dropna().iloc[-1] if "RSI" in df.columns else 50
    macd_hist = _latest(df, "MACD_hist")

    sma_col = f"SMA{sma_long}"
    sma_l = _latest(df, sma_col)
    sma_s = _latest(df, "SMA25")

    recent = df.tail(60)
    resistance = recent["High"].max()
    support = recent["Low"].min()

    # ── トレンド強度の評価 ──────────────────────────────
    reasons = []
    hold_score = 0  # +がポジティブ、-がネガティブ

    # 1. 長期MAとの位置関係（最重要）
    if sma_l and close > sma_l:
        gap_pct = (close - sma_l) / sma_l * 100
        if gap_pct > 10:
            reasons.append(f"📈 長期MAより{gap_pct:.1f}%上: 強い上昇トレンド継続中")
            hold_score += 2
        else:
            reasons.append(f"📈 長期MAより上({gap_pct:.1f}%): 上昇トレンド継続")
            hold_score += 1
    elif sma_l and close < sma_l:
        gap_pct = (sma_l - close) / sma_l * 100
        reasons.append(f"📉 長期MAを下回る({gap_pct:.1f}%下): トレンド悪化")
        hold_score -= 2

    # 2. 短期MAが長期MAの上（上昇継続サイン）
    if sma_s and sma_l:
        if sma_s > sma_l:
            reasons.append("✅ 短期MAが長期MAの上: 上昇モメンタム維持")
            hold_score += 1
        else:
            reasons.append("⚠️ 短期MAが長期MAを下抜け: モメンタム低下")
            hold_score -= 1

    # 3. RSI（過熱感チェック）
    if rsi >= 80:
        reasons.append(f"🔥 RSI {rsi:.0f}: かなり買われすぎ → 一部利確を検討")
        hold_score -= 2
    elif rsi >= 70:
        reasons.append(f"⚠️ RSI {rsi:.0f}: 買われすぎ圏 → 利確ゾーンが近い")
        hold_score -= 1
    elif rsi >= 50:
        reasons.append(f"🟢 RSI {rsi:.0f}: 適正水準 → まだ上昇余地あり")
        hold_score += 1
    else:
        reasons.append(f"🟡 RSI {rsi:.0f}: 低め → 短期調整の可能性")
        hold_score -= 1

    # 4. MACDの向き（勢いの継続確認）
    if macd_hist is not None:
        prev_hist = df["MACD_hist"].dropna().iloc[-2] if len(df) >= 2 else macd_hist
        if macd_hist > 0 and macd_hist >= prev_hist:
            reasons.append("📊 MACDヒストグラム拡大中: 上昇勢いが加速")
            hold_score += 1
        elif macd_hist > 0 and macd_hist < prev_hist:
            reasons.append("📊 MACDヒストグラム縮小中: 上昇勢いがやや鈍化")
        elif macd_hist < 0:
            reasons.append("📊 MACDがマイナス圏: 下落モメンタムに注意")
            hold_score -= 1

    # 5. 高値への距離（利確タイミング判定）
    dist_to_res = (resistance - close) / close * 100
    if dist_to_res < 2:
        reasons.append(f"🎯 直近高値（{resistance:,.0f}）まで残り{dist_to_res:.1f}% → 利確検討タイミング")
        hold_score -= 1
    elif dist_to_res < 5:
        reasons.append(f"🎯 直近高値（{resistance:,.0f}）まで{dist_to_res:.1f}%: 上値余地あり")
    else:
        reasons.append(f"🚀 直近高値まで{dist_to_res:.1f}%: 十分な上値余地")
        hold_score += 1

    # ── 総合判定 ──────────────────────────────────────
    if hold_score >= 4:
        hold_verdict = "💎 強く保有継続"
        hold_detail = "トレンドは非常に強く、まだ上昇余地があります。あわてて売る必要はありません。"
        color = "#26a69a"
        emoji = "💎"
    elif hold_score >= 2:
        hold_verdict = "✅ 保有継続"
        hold_detail = "上昇トレンドが続いています。損切りラインを守りながら保有継続が基本方針です。"
        color = "#4caf50"
        emoji = "✅"
    elif hold_score >= 0:
        hold_verdict = "🟡 様子見で保有"
        hold_detail = "トレンドはまだ崩れていませんが、勢いがやや鈍化。高値圏なら一部利確も選択肢です。"
        color = "#ffd54f"
        emoji = "🟡"
    elif hold_score >= -2:
        hold_verdict = "⚠️ 一部利確を検討"
        hold_detail = "上昇の勢いが落ちてきました。利益が出ている場合は一部売却して利益確定を検討してください。"
        color = "#ff7043"
        emoji = "⚠️"
    else:
        hold_verdict = "🚨 損切り・撤退を検討"
        hold_detail = "トレンドが崩れているサインが複数出ています。損失を最小限にするため売却を検討してください。"
        color = "#ef5350"
        emoji = "🚨"

    # 次のアクション提案
    target_next = close + atr * 3
    stop_line = close - atr * 2
    if stop_line < support:
        stop_line = support

    return {
        "hold_verdict": hold_verdict,
        "hold_detail": hold_detail,
        "hold_score": hold_score,
        "color": color,
        "emoji": emoji,
        "reasons": reasons,
        "resistance": round(resistance, 1),
        "support": round(support, 1),
        "dist_to_resistance_pct": round(dist_to_res, 1),
        "next_target": round(target_next, 1),
        "hold_stop": round(stop_line, 1),
        "rsi": round(rsi, 1),
    }
