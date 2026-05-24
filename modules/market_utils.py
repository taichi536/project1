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


def is_tradeable(ticker: str = "") -> tuple[bool, str]:
    """
    取引可能かどうかを判定する。
    Returns: (tradeable: bool, reason: str)
    土日・市場閉場中は False を返す。
    """
    from modules.data_fetcher import is_japan_ticker
    if is_japan_ticker(ticker):
        open_ = is_japan_market_open()
        if not open_:
            now = datetime.now(JST)
            if now.weekday() >= 5:
                return False, "土日のため取引不可（日本市場は閉場）"
            return False, "日本市場の取引時間外（9:00〜11:30 / 12:30〜15:30）"
    else:
        open_ = is_us_market_open()
        if not open_:
            now = datetime.now(ET)
            if now.weekday() >= 5:
                return False, "土日のため取引不可（米国市場は閉場）"
            return False, "米国市場の取引時間外（ET 9:30〜16:00）"
    return True, ""


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
