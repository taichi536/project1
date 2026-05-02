from datetime import datetime, time
import pytz

JST = pytz.timezone("Asia/Tokyo")
ET = pytz.timezone("America/New_York")


def is_japan_market_open() -> bool:
    now = datetime.now(JST)
    if now.weekday() >= 5:  # 土日
        return False
    market_open = time(9, 0)
    morning_close = time(11, 30)
    afternoon_open = time(12, 30)
    market_close = time(15, 30)
    t = now.time()
    return (market_open <= t <= morning_close) or (afternoon_open <= t <= market_close)


def is_us_market_open() -> bool:
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    market_open = time(9, 30)
    market_close = time(16, 0)
    return market_open <= now.time() <= market_close


def market_status() -> dict:
    jp_open = is_japan_market_open()
    us_open = is_us_market_open()
    now_jst = datetime.now(JST)

    return {
        "jp_open": jp_open,
        "us_open": us_open,
        "jp_label": "🟢 開場中" if jp_open else "🔴 閉場中",
        "us_label": "🟢 開場中" if us_open else "🔴 閉場中",
        "any_open": jp_open or us_open,
        # yfinanceは最大15分遅延
        "data_delay_note": "※ 株価データは最大15分遅延（yfinanceの仕様）",
        "now_jst": now_jst.strftime("%Y-%m-%d %H:%M JST"),
        # 推奨更新間隔
        "recommended_interval_sec": 60 if (jp_open or us_open) else 300,
    }
