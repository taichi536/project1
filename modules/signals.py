import pandas as pd
import numpy as np


def _latest(df: pd.DataFrame, col: str):
    if col not in df.columns:
        return None
    s = df[col].dropna()
    return s.iloc[-1] if len(s) > 0 else None


def evaluate_signals(df: pd.DataFrame, sma_short: int = 25, sma_long: int = 75) -> list[dict]:
    signals = []
    row = df.iloc[-1]
    close = row["Close"]

    # --- 移動平均（トレンド方向） ---
    sma_s = _latest(df, f"SMA{sma_short}")
    sma_l = _latest(df, f"SMA{sma_long}")
    if sma_s is not None and sma_l is not None:
        _s_series = df[f"SMA{sma_short}"].dropna()
        _l_series = df[f"SMA{sma_long}"].dropna()
        prev_s = _s_series.iloc[-2] if len(_s_series) >= 2 else None
        prev_l = _l_series.iloc[-2] if len(_l_series) >= 2 else None
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
        if rsi < 20:
            judge, score = "極度の売られすぎ → 強い反発期待", 2
        elif rsi < 35:
            judge, score = "売られすぎ気味 → 買い候補", 1
        elif rsi > 80:
            judge, score = "かなり買われすぎ → 下落しやすい", -2
        elif rsi > 70:
            judge, score = "買われすぎ気味 → 利確検討", -1
        else:
            judge, score = "中立域（35〜70）", 0
        signals.append({"指標": "RSI（売買過熱感）", "値": f"{rsi:.1f}", "判定": judge, "スコア": score})

    # --- MACD（モメンタム変化） ---
    macd = _latest(df, "MACD")
    macd_sig = _latest(df, "MACD_signal")
    macd_hist = _latest(df, "MACD_hist")
    _hist_series = df["MACD_hist"].dropna() if "MACD_hist" in df.columns else pd.Series(dtype=float)
    prev_hist = _hist_series.iloc[-2] if len(_hist_series) >= 2 else None
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
        cloud_thickness = (cloud_top - cloud_bot) / abs(cloud_bot) * 100 if cloud_bot != 0 else 0
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

    # --- ADX（トレンド強度）: 横ばい相場でのシグナルを除外 ---
    adx = _latest(df, "ADX")
    di_plus = _latest(df, "DI_plus")
    di_minus = _latest(df, "DI_minus")
    if adx is not None and di_plus is not None and di_minus is not None:
        if adx >= 25 and di_plus > di_minus:
            judge, score = f"強い上昇トレンド（ADX {adx:.0f}）→ シグナル信頼性高", 2
        elif adx >= 25 and di_minus > di_plus:
            judge, score = f"強い下落トレンド（ADX {adx:.0f}）→ 下落圧力が強い", -2
        elif adx >= 20 and di_plus > di_minus:
            judge, score = f"上昇トレンド中（ADX {adx:.0f}）→ 追い風あり", 1
        elif adx >= 20 and di_minus > di_plus:
            judge, score = f"下落トレンド中（ADX {adx:.0f}）→ 慎重に", -1
        else:
            judge, score = f"横ばい相場（ADX {adx:.0f}）→ シグナルの信頼性低下", 0
        signals.append({
            "指標": "ADX（トレンド強度）",
            "値": f"ADX {adx:.1f} / DI+ {di_plus:.1f} / DI- {di_minus:.1f}",
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
    if vwap is not None and vwap != 0:
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


# ── 指標の重み定義 ──────────────────────────────────────────────────────────────
# スイングトレードにおける各指標の重要度
# ★★★ トレンド系（最重要）: 大局の方向が間違うと全て無駄になる
# ★★☆ モメンタム系（重要）: エントリータイミングを絞り込む
# ★☆☆ 補助系（参考）: 補強材料として使う
INDICATOR_WEIGHTS: dict[str, float] = {
    "移動平均線":              3.0,   # ★★★ トレンドの大局。最も重要
    "ADX（トレンド強度）":     3.0,   # ★★★ 「動ける相場か」の判定。横ばいでは他全指標が無効化
    "一目均衡表（雲）":        2.0,   # ★★☆ 複合トレンド指標。雲の上/下は強いサイン
    "MACD（勢い）":            2.0,   # ★★☆ モメンタム転換の早期検知。タイミングに有効
    "RSI（売買過熱感）":       1.0,   # ★☆☆ 過熱感の確認。単独では誤シグナルが多い
    "出来高トレンド（OBV）":   2.0,   # ★★☆ 大口の動き確認。出来高なき上昇は信頼できない
    "ボリンジャーバンド":      1.0,   # ★☆☆ レンジ相場で有効。トレンド相場では弱い
    "VWAP（機関投資家の基準価格）": 1.0,  # ★☆☆ 機関投資家の基準。参考程度
}


def calc_signal_confidence(signals: list[dict], verdict: str) -> int:
    """
    重み付きシグナル一致率を返す（0〜100%）。
    重要度の高い指標がverdictと一致しているほど高くなる。
    """
    if not signals:
        return 0
    total_weight = sum(INDICATOR_WEIGHTS.get(s["指標"], 1.0) for s in signals)
    if total_weight == 0:
        return 0
    if verdict == "買い":
        agree_weight = sum(
            INDICATOR_WEIGHTS.get(s["指標"], 1.0) for s in signals if s["スコア"] > 0
        )
    elif verdict == "売り":
        agree_weight = sum(
            INDICATOR_WEIGHTS.get(s["指標"], 1.0) for s in signals if s["スコア"] < 0
        )
    else:
        agree_weight = sum(
            INDICATOR_WEIGHTS.get(s["指標"], 1.0) for s in signals if s["スコア"] == 0
        )
    return round(agree_weight / total_weight * 100)


def signal_grade(weighted_pct: float, verdict: str, adx_confirmed_down: bool, sideways: bool) -> tuple[str, str]:
    """
    シグナルの質をグレード判定する。
    Returns: (grade_label, grade_color)

    S: 全条件が揃った最高シグナル → 通常サイズでエントリー
    A: 主要指標が一致した強いシグナル → 通常エントリー
    B: 条件が一部揃い始めた弱いシグナル → 小さめポジションで様子見
    """
    if verdict == "買い":
        if weighted_pct >= 0.55 and not sideways:
            return "S級シグナル", "#26a69a"
        elif weighted_pct >= 0.40:
            return "A級シグナル", "#4caf50"
        else:
            return "B級シグナル", "#ffd54f"
    elif verdict == "売り":
        if weighted_pct <= -0.55:
            return "S級シグナル", "#ef5350"
        elif weighted_pct <= -0.40:
            return "A級シグナル", "#ff7043"
        else:
            return "B級シグナル", "#ffd54f"
    return "", "#888"


def _calc_weighted_context(
    signals: list[dict],
    df: pd.DataFrame = None,
    sma_long: int = 75,
) -> tuple[float, bool, bool]:
    """
    重み付きスコアとADX/SMAコンテキストを計算する共通ヘルパー。
    Returns: (weighted_pct, adx_confirmed_down, sideways_market)
    """
    weighted_total = sum(
        s["スコア"] * INDICATOR_WEIGHTS.get(s["指標"], 1.0) for s in signals
    )
    max_weighted = sum(
        INDICATOR_WEIGHTS.get(s["指標"], 1.0) * 2 for s in signals
    )
    if max_weighted == 0:
        return 0.0, False, False

    adx_confirmed_down = False
    sideways_market = False

    if df is not None:
        sma_col = f"SMA{sma_long}"
        _sma = df[sma_col].dropna() if sma_col in df.columns else pd.Series(dtype=float)
        if len(_sma) > 0 and _sma.iloc[-1] != 0:
            _gap = (df["Close"].iloc[-1] - _sma.iloc[-1]) / _sma.iloc[-1]
            if _gap < -0.07:
                weighted_total -= 3.0
            elif _gap < -0.03:
                weighted_total -= 1.5
            elif _gap > 0.07:
                weighted_total += 1.5

        _adx = df["ADX"].dropna() if "ADX" in df.columns else pd.Series(dtype=float)
        _dip = df["DI_plus"].dropna() if "DI_plus" in df.columns else pd.Series(dtype=float)
        _dim = df["DI_minus"].dropna() if "DI_minus" in df.columns else pd.Series(dtype=float)
        if len(_adx) > 0 and len(_dip) > 0 and len(_dim) > 0:
            adx_val = _adx.iloc[-1]
            if adx_val >= 25 and _dim.iloc[-1] > _dip.iloc[-1]:
                adx_confirmed_down = True
                weighted_total -= 4.0
            elif adx_val < 20:
                sideways_market = True

    return weighted_total / max_weighted, adx_confirmed_down, sideways_market


def overall_signal(
    signals: list[dict],
    df: pd.DataFrame = None,
    sma_long: int = 75,
) -> tuple[str, int]:
    """
    重み付き総合判定。

    判定ロジック:
    1. 重み付きスコア計算: 移動平均・ADXは3倍、MACD・一目は2倍、他は1倍
    2. 必須条件ゲート:
       - 買いの場合: 株価がSMA75より上であること（下ならペナルティ）
       - ADXが強い下落トレンドを確認している場合: 買い禁止
    3. 横ばい相場(ADX<20): 閾値を引き上げて誤シグナルを抑制
    """
    if not signals:
        return "様子見", 0

    raw_total = sum(s["スコア"] for s in signals)
    pct, adx_confirmed_down, sideways_market = _calc_weighted_context(signals, df, sma_long)

    threshold = 0.52 if sideways_market else 0.40

    if pct >= threshold and not adx_confirmed_down:
        return "買い", raw_total
    elif pct <= -threshold:
        return "売り", raw_total
    else:
        return "様子見", raw_total


def get_signal_detail(
    signals: list[dict],
    verdict: str,
    df: pd.DataFrame = None,
    sma_long: int = 75,
) -> dict:
    """
    overall_signalの内部計算結果を詳細で返す（UI表示用）。
    """
    if not signals:
        return {"grade": "", "grade_color": "#888", "weighted_pct": 0, "confidence": 0}

    pct, adx_confirmed_down, sideways_market = _calc_weighted_context(signals, df, sma_long)
    grade_label, grade_color = signal_grade(pct, verdict, adx_confirmed_down, sideways_market)
    confidence = calc_signal_confidence(signals, verdict)

    return {
        "grade": grade_label,
        "grade_color": grade_color,
        "weighted_pct": round(pct * 100, 1),
        "confidence": confidence,
        "sideways": sideways_market,
        "adx_down": adx_confirmed_down,
    }


def _atr_fallback(df: pd.DataFrame, close: float) -> float:
    """ATRが計算できない場合の代替: 直近20日の価格変動標準偏差を使用"""
    if "ATR" in df.columns:
        atr_s = df["ATR"].dropna()
        if len(atr_s) > 0:
            return float(atr_s.iloc[-1])
    std = df["Close"].pct_change().tail(20).std()
    return std * close if not np.isnan(std) and std > 0 else close * 0.02


def generate_action_plan(
    df: pd.DataFrame,
    signals: list[dict],
    verdict: str,
    ticker: str,
) -> dict:
    """初心者向けの具体的な投資プランを生成"""
    close = df["Close"].iloc[-1]
    atr = _atr_fallback(df, close)
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
    atr = _atr_fallback(df, close)
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


def evaluate_watch_signal(df: pd.DataFrame, sma_long: int = 75) -> dict:
    """
    下降トレンド中の銘柄を「いつ買えるか」監視している人向けの判定。

    「まだ買うな」「そろそろ準備」「今がエントリーチャンス」を段階的に提示する。
    保有継続判定とは逆の視点（下から上を狙う）で評価する。
    """
    close = df["Close"].iloc[-1]
    atr = _atr_fallback(df, close)
    rsi = df["RSI"].dropna().iloc[-1] if "RSI" in df.columns else 50
    macd_hist = _latest(df, "MACD_hist")
    bb_pct = _latest(df, "BB_pct")

    sma_col = f"SMA{sma_long}"
    sma_l = _latest(df, sma_col)
    sma_s = _latest(df, "SMA25")

    recent60 = df.tail(60)
    recent20 = df.tail(20)
    support_60 = recent60["Low"].min()
    support_20 = recent20["Low"].min()
    resistance_20 = recent20["High"].max()

    # OBV反転チェック
    obv_series = df["OBV"].dropna() if "OBV" in df.columns else pd.Series(dtype=float)
    obv_rising = False
    if len(obv_series) >= 10:
        obv_recent = obv_series.iloc[-5:].mean()
        obv_prev = obv_series.iloc[-10:-5].mean()
        obv_rising = obv_recent > obv_prev * 1.03

    # ── 各条件をチェック ──────────────────────────────────
    conditions_met = []       # 買い条件が揃ってきた根拠
    conditions_missing = []   # まだ足りない条件
    watch_score = 0

    # 1. 長期MAとの位置（最重要）
    if sma_l:
        gap_pct = (close - sma_l) / sma_l * 100
        if close < sma_l:
            if gap_pct < -15:
                conditions_met.append(f"📉 長期MAより{abs(gap_pct):.1f}%下: 大幅な売られすぎ圏（反発バーゲンゾーン）")
                watch_score += 1
            else:
                conditions_missing.append(f"📉 まだ長期MAの下（{gap_pct:.1f}%）: 下落トレンド継続中")
                watch_score -= 1
        else:
            conditions_met.append(f"✅ 長期MAを上抜け({gap_pct:+.1f}%): トレンド転換の可能性")
            watch_score += 2

    # 2. 短期MAが長期MAを上抜けたか
    if sma_s and sma_l:
        if sma_s > sma_l:
            conditions_met.append("✅ 短期MAが長期MAを上抜け（ゴールデンクロス）: 買いサイン")
            watch_score += 2
        else:
            conditions_missing.append("⏳ 短期MAがまだ長期MAの下: クロスを待っている状態")

    # 3. RSI（売られすぎからの反発を狙う）
    if rsi < 30:
        conditions_met.append(f"✅ RSI {rsi:.0f}: 売られすぎ圏 → 反発が近い可能性")
        watch_score += 2
    elif rsi < 40:
        conditions_met.append(f"🟡 RSI {rsi:.0f}: やや売られすぎ → 底値圏に近づいている")
        watch_score += 1
    elif rsi > 50:
        conditions_missing.append(f"⏳ RSI {rsi:.0f}: まだ高め → もう少し下がってから買う方が安全")
        watch_score -= 1

    # 4. ボリンジャーバンド下限タッチ
    if bb_pct is not None:
        if bb_pct < 0:
            conditions_met.append("✅ ボリンジャー下限を突破: 統計的に売られすぎの極限")
            watch_score += 2
        elif bb_pct < 0.2:
            conditions_met.append("🟡 ボリンジャー下限付近: 反発しやすいゾーン")
            watch_score += 1
        else:
            conditions_missing.append("⏳ ボリンジャー帯の中央以上: まだ割安水準ではない")

    # 5. MACDのゼロライン接近（モメンタム転換の兆候）
    if macd_hist is not None:
        prev_hist = df["MACD_hist"].dropna().iloc[-2] if len(df) >= 2 else macd_hist
        if macd_hist < 0 and macd_hist > prev_hist:
            conditions_met.append("🟡 MACDヒストグラムが縮小中: 下落の勢いが鈍化している")
            watch_score += 1
        elif macd_hist > 0:
            conditions_met.append("✅ MACDがプラス転換: モメンタムが上向きに")
            watch_score += 1
        else:
            conditions_missing.append("⏳ MACDはまだマイナス圏で拡大中: 下落モメンタム継続")

    # 6. 出来高（大口の買い集め）
    if obv_rising:
        conditions_met.append("✅ OBVが上昇中: 下落中でも大口が買い集めている可能性")
        watch_score += 1
    else:
        conditions_missing.append("⏳ OBV（出来高）は上昇していない: 大口の買いがまだ入っていない")

    # 7. 直近安値からの距離（二番底チェック）
    dist_from_support = (close - support_60) / support_60 * 100 if support_60 != 0 else 0
    if abs(dist_from_support) < 3:
        conditions_met.append(f"✅ 直近安値（{support_60:,.0f}）付近: 二番底の可能性あり")
        watch_score += 1
    elif close < support_60:
        conditions_missing.append(f"⚠️ 直近安値（{support_60:,.0f}）を更新中: まだ底打ちしていない")
        watch_score -= 2

    # ── 総合判定 ──────────────────────────────────────────
    if watch_score >= 6:
        verdict = "🎯 今がエントリーチャンス"
        detail = "底打ちの複数のサインが確認できます。リスク管理しながらエントリーを検討してください。"
        color = "#26a69a"
        action = f"エントリー候補: {close:,.0f}円付近。損切りラインは直近安値（{support_20:,.0f}円）の少し下に設定。"
    elif watch_score >= 3:
        verdict = "🔔 そろそろ準備を始めよう"
        detail = "底打ちの兆候が出てきています。まだ確定ではないので、一部だけ試しに入るか、完全な反転確認を待つかを判断してください。"
        color = "#ffd54f"
        action = f"もう少し待ってRSIが30以下、またはMACD転換を確認してからエントリーが安全。"
    elif watch_score >= 0:
        verdict = "👀 引き続き監視中"
        detail = "下落の勢いがやや鈍化してきましたが、まだ買いのサインは出ていません。条件が揃うのを待ちましょう。"
        color = "#7e57c2"
        action = "慌ててエントリーせず、ゴールデンクロスかRSI30以下の売られすぎサインを待ちましょう。"
    else:
        verdict = "🚫 まだ買うのは早い"
        detail = "下落トレンドが継続中です。「落ちるナイフをつかむ」リスクがあります。まだ待ってください。"
        color = "#ef5350"
        _sma_str = f"{sma_l:,.0f}円" if sma_l is not None else "長期MA"
        action = f"長期MA（現在 {_sma_str}）を株価が上回るまで、または大幅な売られすぎサインが出るまで待機。"

    # エントリーチェックリスト
    checklist = []
    for c in conditions_met:
        checklist.append({"status": "✅", "text": c.lstrip("✅🟡📉⏳⚠️").strip()})
    for c in conditions_missing:
        checklist.append({"status": "⏳", "text": c.lstrip("✅🟡📉⏳⚠️").strip()})

    return {
        "verdict": verdict,
        "detail": detail,
        "action": action,
        "color": color,
        "watch_score": watch_score,
        "conditions_met": conditions_met,
        "conditions_missing": conditions_missing,
        "support": round(support_60, 1),
        "support_20": round(support_20, 1),
        "resistance": round(resistance_20, 1),
        "rsi": round(rsi, 1),
        "entry_price": round(close, 1),
        "stop_loss": round(support_20 * 0.97, 1),
    }


def detect_breakout(df: pd.DataFrame) -> dict | None:
    """
    ブレイクアウト（抵抗線を突破した瞬間）と出来高急増を検出する。

    ブレイクアウトは最も信頼性の高いエントリーサインの一つ。
    ただし出来高の裏付けがないと「騙し」になりやすい。
    """
    if len(df) < 20:
        return None

    close = df["Close"].iloc[-1]
    prev_close = df["Close"].iloc[-2]
    recent = df.tail(20)
    prior = df.tail(60).head(40)  # 直近20日より前の40日

    # 抵抗線 = 過去40日の高値
    resistance = prior["High"].max()
    support = prior["Low"].min()

    # 出来高急増チェック
    vol_today = df["Volume"].iloc[-1]
    vol_avg = df["Volume"].tail(20).mean()
    vol_ratio = vol_today / vol_avg if vol_avg > 0 else 1.0

    alerts = []

    # 上方ブレイクアウト（抵抗線を出来高急増で突破）
    if close > resistance and prev_close <= resistance:
        strength = "強い" if vol_ratio >= 1.5 else "弱い（出来高不足）"
        alerts.append({
            "type": "breakout_up",
            "emoji": "🚀",
            "title": f"上方ブレイクアウト！（{strength}）",
            "detail": f"過去40日の高値 {resistance:,.0f} を突破。出来高は平均の{vol_ratio:.1f}倍。",
            "color": "#26a69a",
            "reliable": vol_ratio >= 1.5,
        })

    # 下方ブレイクアウト（サポートを割り込む）
    if close < support and prev_close >= support:
        alerts.append({
            "type": "breakout_down",
            "emoji": "💥",
            "title": "サポート割り込み警告",
            "detail": f"過去40日の安値 {support:,.0f} を下抜け。保有中なら損切りを検討。",
            "color": "#ef5350",
            "reliable": True,
        })

    # 出来高急増（価格変化なしでも大口の動き）
    price_chg = (close - prev_close) / prev_close * 100
    if vol_ratio >= 2.0 and abs(price_chg) < 2:
        alerts.append({
            "type": "volume_surge",
            "emoji": "📊",
            "title": f"出来高急増（平均の{vol_ratio:.1f}倍）",
            "detail": f"価格変化{price_chg:+.1f}%に対して出来高が急増。大口の動きの可能性。方向感が出る前兆のことが多い。",
            "color": "#7e57c2",
            "reliable": True,
        })

    if not alerts:
        return None

    return {
        "alerts": alerts,
        "resistance": round(resistance, 1),
        "support": round(support, 1),
        "vol_ratio": round(vol_ratio, 2),
        "price_chg_pct": round(price_chg, 2),
    }


def calc_signal_accuracy(df: pd.DataFrame, sma_short: int = 25, sma_long: int = 75) -> dict | None:
    """
    過去データでシグナルの的中率を高速計算する。
    「RSI<45 かつ 長期MAの上 かつ MACDプラス」の日の翌5/10/20日後の上昇確率を算出。
    完全なシグナル評価を毎日再計算するのは遅すぎるため、主要3条件で近似する。
    """
    sma_l_col = f"SMA{sma_long}"
    required = ["RSI", "MACD_hist", sma_l_col]
    if len(df) < 80 or any(c not in df.columns for c in required):
        return None

    cond = (
        (df["RSI"] < 45) &
        (df["Close"] > df[sma_l_col]) &
        (df["MACD_hist"] > 0)
    ).fillna(False)

    wins_5, wins_10, wins_20 = [], [], []
    idxs = [i for i in range(len(df)) if cond.iloc[i]]

    for i in idxs:
        price = df["Close"].iloc[i]
        for horizon, wins in [(5, wins_5), (10, wins_10), (20, wins_20)]:
            if i + horizon < len(df):
                wins.append(df["Close"].iloc[i + horizon] > price)

    if len(wins_10) < 5:
        return None

    return {
        "signal_count": len(idxs),
        "win_rate_5d":  round(sum(wins_5)  / len(wins_5)  * 100, 1) if wins_5  else None,
        "win_rate_10d": round(sum(wins_10) / len(wins_10) * 100, 1) if wins_10 else None,
        "win_rate_20d": round(sum(wins_20) / len(wins_20) * 100, 1) if wins_20 else None,
    }


def multi_timeframe_signal(ticker: str, sma_short: int = 25, sma_long: int = 75) -> list[dict]:
    """
    週足・日足・1時間足の3つのタイムフレームでシグナルを同時評価する。
    3つが一致するほど信頼性が高い。
    """
    from modules.data_fetcher import fetch_ohlcv
    from modules.technical import compute_all

    timeframes = [
        ("週足（大局）", "1wk", "2y"),
        ("日足（中期）", "1d", "6mo"),
        ("1時間足（短期）", "1h", "60d"),
    ]
    results = []
    for label, interval, period in timeframes:
        try:
            df = fetch_ohlcv(ticker, period=period, interval=interval)
            df = compute_all(df, sma_short=sma_short, sma_long=sma_long)
            sigs = evaluate_signals(df, sma_short=sma_short, sma_long=sma_long)
            verdict, score = overall_signal(sigs, df=df, sma_long=sma_long)
            rsi = float(df["RSI"].dropna().iloc[-1]) if "RSI" in df.columns else None
            ma_col = f"SMA{sma_long}"
            ma = float(df[ma_col].dropna().iloc[-1]) if ma_col in df.columns else None
            close = float(df["Close"].iloc[-1])
            trend = "上昇" if (ma and close > ma) else "下落"
            results.append({
                "timeframe": label,
                "verdict": verdict,
                "score": score,
                "rsi": round(rsi, 1) if rsi else None,
                "trend": trend,
                "close": round(close, 2),
            })
        except Exception as e:
            results.append({
                "timeframe": label,
                "verdict": "取得失敗",
                "score": 0,
                "rsi": None,
                "trend": "-",
                "close": None,
            })
    return results
