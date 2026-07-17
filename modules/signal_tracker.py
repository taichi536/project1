"""
シグナル精度トラッカー

買い/売りシグナルが出た後、実際に価格がどう動いたかを記録・集計する。
alert_runner.py から呼ばれ、翌日以降の価格変化をフォローする。
"""

import json
from pathlib import Path
from datetime import datetime, timedelta

from modules import userstore

_LEGACY_TRACKER = Path(__file__).parent.parent / ".signal_tracker.json"


def _tracker_file() -> Path:
    return userstore.user_path("signal_tracker.json", legacy=_LEGACY_TRACKER)


def _load() -> dict:
    p = _tracker_file()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {"signals": [], "summary": {}}


def _save(data: dict):
    try:
        _tracker_file().write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        pass


def record_signal(ticker: str, verdict: str, score: int, price: float):
    """シグナル発生時に記録する"""
    data = _load()
    # 同一銘柄・同一日の重複は上書き
    today = datetime.now().strftime("%Y-%m-%d")
    data["signals"] = [
        s for s in data["signals"]
        if not (s["ticker"] == ticker and s["date"] == today and s["verdict"] == verdict)
    ]
    data["signals"].append({
        "ticker": ticker,
        "verdict": verdict,
        "score": score,
        "price_at_signal": price,
        "date": today,
        "result": None,        # 後から埋める
        "price_after_3d": None,
        "price_after_5d": None,
    })
    # 直近1000件のみ保持
    data["signals"] = data["signals"][-1000:]
    _save(data)


def update_results():
    """3日後・5日後の結果を埋める（alert_runnerから定期呼び出し）"""
    try:
        from modules.data_fetcher import fetch_ohlcv
    except ImportError:
        return

    data = _load()
    today = datetime.now().date()
    changed = False

    for s in data["signals"]:
        if s.get("result") is not None:
            continue
        signal_date = datetime.strptime(s["date"], "%Y-%m-%d").date()
        days_elapsed = (today - signal_date).days
        if days_elapsed < 3:
            continue

        try:
            df = fetch_ohlcv(s["ticker"], period="1mo")
            if df.empty:
                continue
            signal_ts = str(signal_date)
            # signal_date以降のデータを取得
            after = df[df.index >= signal_ts]
            if len(after) < 1:
                continue

            entry_price = s["price_at_signal"]
            if entry_price <= 0:
                continue

            if days_elapsed >= 3 and s["price_after_3d"] is None and len(after) >= 3:
                p3 = float(after.iloc[2]["Close"])
                s["price_after_3d"] = round(p3, 2)
                s["return_3d_pct"] = round((p3 - entry_price) / entry_price * 100, 2)
                changed = True

            if days_elapsed >= 5 and s["price_after_5d"] is None and len(after) >= 5:
                p5 = float(after.iloc[4]["Close"])
                s["price_after_5d"] = round(p5, 2)
                s["return_5d_pct"] = round((p5 - entry_price) / entry_price * 100, 2)
                # 買いシグナルで5日後にプラスなら正解
                if s["verdict"] == "買い":
                    s["result"] = "correct" if p5 > entry_price else "wrong"
                elif s["verdict"] == "売り":
                    s["result"] = "correct" if p5 < entry_price else "wrong"
                changed = True
        except Exception:
            continue

    if changed:
        # 精度サマリーを更新
        scored = [s for s in data["signals"] if s.get("result") is not None]
        if scored:
            buy_signals = [s for s in scored if s["verdict"] == "買い"]
            sell_signals = [s for s in scored if s["verdict"] == "売り"]

            def _accuracy(lst):
                if not lst:
                    return None
                correct = sum(1 for s in lst if s["result"] == "correct")
                return round(correct / len(lst) * 100, 1)

            data["summary"] = {
                "total_evaluated": len(scored),
                "buy_accuracy_pct": _accuracy(buy_signals),
                "sell_accuracy_pct": _accuracy(sell_signals),
                "overall_accuracy_pct": _accuracy(scored),
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
        _save(data)


def get_summary() -> dict:
    """精度サマリーを返す"""
    return _load().get("summary", {})


def get_recent_signals(limit: int = 20) -> list[dict]:
    """直近のシグナル記録を返す"""
    data = _load()
    return list(reversed(data.get("signals", [])[-limit:]))
