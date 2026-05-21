import numpy as np
import pandas as pd


def assess_signal_risk(
    ticker: str,
    df: pd.DataFrame,
    earnings_days: int | None = None,
    vix_level: float | None = None,
) -> dict:
    """
    シグナルのリスクを評価し、エントリー可否を判定する。

    Args:
        ticker:        銘柄コード（ログ用）
        df:            OHLCV + テクニカル指標のDataFrame
        earnings_days: 決算まで残り日数（None = 不明）
        vix_level:     現在のVIX水準（None = 不使用）

    Returns:
        {
            "risk_level":      "LOW" | "MEDIUM" | "HIGH",
            "risk_score":      int,    # 0-10
            "reasons":         list[str],
            "entry_limit_pct": float,  # 現値から何%上まで追いかけ許容
            "should_skip":     bool,   # True = エントリー見送り推奨
        }
    """
    risk_score = 0
    reasons: list[str] = []
    force_skip = False

    # ── 1. 決算近接リスク ──────────────────────────────────────────
    if earnings_days is not None:
        n = int(earnings_days)
        if n < 5:
            risk_score += 4
            force_skip = True
            reasons.append(f"決算まで{n}日 → 見送り推奨")
        elif n < 15:
            risk_score += 2
            reasons.append(f"決算まで{n}日 → ポジションを小さく")

    # ── 2. 直近ボラティリティ（ATR/Close比） ──────────────────────
    if "ATR" in df.columns and "Close" in df.columns and len(df) > 0:
        latest_close = df["Close"].iloc[-1]
        latest_atr = df["ATR"].iloc[-1]
        if latest_close > 0 and not np.isnan(latest_atr):
            atr_pct = latest_atr / latest_close * 100
            if atr_pct > 5:
                risk_score += 3
                reasons.append(f"ボラティリティ高すぎ（ATR {atr_pct:.1f}%）→ 損切り幅が大きくなる")
            elif atr_pct > 3:
                risk_score += 1
                reasons.append("ボラティリティやや高め")

    # ── 3. 窓開けリスク（当日Open vs 前日Close） ──────────────────
    if "Open" in df.columns and "Close" in df.columns and len(df) >= 2:
        today_open = df["Open"].iloc[-1]
        prev_close = df["Close"].iloc[-2]
        if prev_close > 0 and not (np.isnan(today_open) or np.isnan(prev_close)):
            gap_pct = (today_open - prev_close) / prev_close * 100
            if abs(gap_pct) > 3:
                risk_score += 2
                reasons.append(f"窓開け{gap_pct:+.1f}% → 追いかけ買いは危険")

    # ── 4. 出来高希薄リスク（当日 vs 20日平均） ───────────────────
    if "Volume" in df.columns and len(df) >= 20:
        vol_series = df["Volume"].dropna()
        if len(vol_series) >= 20:
            today_vol = vol_series.iloc[-1]
            avg_vol = vol_series.iloc[-21:-1].mean()  # 直近20日（当日除外）
            if avg_vol > 0 and not np.isnan(today_vol):
                vol_ratio_pct = today_vol / avg_vol * 100
                if vol_ratio_pct < 40:
                    risk_score += 2
                    reasons.append(
                        f"出来高が平均の{vol_ratio_pct:.0f}% → シグナルの信頼性低下"
                    )

    # ── 5. VIX水準リスク ──────────────────────────────────────────
    if vix_level is not None:
        v = float(vix_level)
        if v > 30:
            risk_score += 3
            reasons.append(f"VIX {v:.1f}（パニック水準）→ 市場全体が不安定")
        elif v > 20:
            risk_score += 1
            reasons.append(f"VIX {v:.1f}（やや高め）→ 慎重に")

    # ── リスクレベル判定 ──────────────────────────────────────────
    risk_score = min(risk_score, 10)

    if force_skip:
        risk_score = max(risk_score, 5)  # force_skipはスコアも HIGH 水準に揃える
    if risk_score >= 5:
        risk_level = "HIGH"
        should_skip = True
        entry_limit_pct = 0.0
    elif risk_score >= 2:
        risk_level = "MEDIUM"
        should_skip = False
        entry_limit_pct = 2.0
    else:
        risk_level = "LOW"
        should_skip = False
        entry_limit_pct = 3.0

    return {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "reasons": reasons,
        "entry_limit_pct": entry_limit_pct,
        "should_skip": should_skip,
    }
