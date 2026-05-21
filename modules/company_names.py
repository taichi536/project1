"""
銘柄コード → 社名の変換モジュール。
yfinanceで取得した社名をJSONファイルにキャッシュし、
API呼び出しを最小限に抑える。
"""

import json
from pathlib import Path
import yfinance as yf
from modules.data_fetcher import normalize_ticker

_CACHE_FILE = Path(__file__).parent.parent / ".company_names_cache.json"

# 既知の社名（よく使う銘柄をハードコード）
_KNOWN_NAMES: dict[str, str] = {
    # 日本株
    "7203": "トヨタ自動車",
    "9984": "ソフトバンクG",
    "6758": "ソニーグループ",
    "6861": "キーエンス",
    "8306": "三菱UFJ",
    "9432": "NTT",
    "6501": "日立製作所",
    "6902": "デンソー",
    "4063": "信越化学",
    "8035": "東京エレクトロン",
    "9433": "KDDI",
    "4519": "中外製薬",
    "6367": "ダイキン工業",
    "7267": "ホンダ",
    "9022": "JR東海",
    "8316": "三井住友FG",
    "6954": "ファナック",
    "9020": "JR東日本",
    "4543": "テルモ",
    "8411": "みずほFG",
    "7751": "キヤノン",
    "6981": "村田製作所",
    "4661": "オリエンタルランド",
    "2914": "JT",
    "7974": "任天堂",
    "4307": "野村総研",
    "6594": "日本電産",
    "9434": "ソフトバンク",
    "8058": "三菱商事",
    "7741": "HOYA",
    "4502": "武田薬品",
    "6645": "オムロン",
    "7733": "オリンパス",
    "8031": "三井物産",
    "4568": "第一三共",
    "6503": "三菱電機",
    "5108": "ブリヂストン",
    "6752": "パナソニック",
    "7832": "バンダイナムコ",
    "3382": "セブン&アイ",
    "8801": "三井不動産",
    "8802": "三菱地所",
    "9021": "JR西日本",
    "6724": "エプソン",
    "4151": "協和キリン",
    "2802": "味の素",
    "4188": "三菱ケミカル",
    "5401": "日本製鉄",
    # 米国株
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "GOOGL": "Google",
    "AMZN": "Amazon",
    "NVDA": "NVIDIA",
    "META": "Meta",
    "TSLA": "Tesla",
    "BRK-B": "Berkshire",
    "JPM": "JPMorgan",
    "JNJ": "J&J",
    "V": "Visa",
    "UNH": "UnitedHealth",
    "XOM": "Exxon",
    "MA": "Mastercard",
    "PG": "P&G",
    "HD": "Home Depot",
    "CVX": "Chevron",
    "MRK": "Merck",
    "LLY": "Eli Lilly",
    "PEP": "PepsiCo",
    "ABBV": "AbbVie",
    "KO": "Coca-Cola",
    "AVGO": "Broadcom",
    "COST": "Costco",
    "WMT": "Walmart",
    "MCD": "McDonald's",
    "BAC": "BofA",
    "DIS": "Disney",
    "ADBE": "Adobe",
    "CRM": "Salesforce",
    "NFLX": "Netflix",
    "INTC": "Intel",
    "AMD": "AMD",
    "QCOM": "Qualcomm",
    "TXN": "Texas Instr.",
    "SPY": "S&P500 ETF",
    "QQQ": "NASDAQ ETF",
}


def _load_cache() -> dict:
    if _CACHE_FILE.exists():
        try:
            return json.loads(_CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_cache(cache: dict):
    _CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2))


def get_company_name(ticker: str, use_api: bool = True) -> str:
    """
    銘柄コードから社名を返す。
    優先順位: ハードコード → キャッシュ → yfinance API
    取得できない場合はtickerをそのまま返す。
    """
    raw = ticker.strip().upper()
    # 4桁数字はゼロ埋めなしで検索
    key = raw.replace(".T", "")

    if key in _KNOWN_NAMES:
        return _KNOWN_NAMES[key]
    if raw in _KNOWN_NAMES:
        return _KNOWN_NAMES[raw]

    cache = _load_cache()
    if raw in cache:
        return cache[raw]

    if not use_api:
        return raw

    try:
        normalized = normalize_ticker(raw)
        info = yf.Ticker(normalized).fast_info
        # fast_infoに社名はないのでinfoを使う（低速だがキャッシュするので1回だけ）
        full_info = yf.Ticker(normalized).info
        name = full_info.get("shortName") or full_info.get("longName") or raw
        # 長い社名は短縮
        if len(name) > 12:
            name = name[:11] + "…"
        cache[raw] = name
        _save_cache(cache)
        return name
    except Exception:
        return raw


def get_company_names_bulk(tickers: list[str], use_api: bool = False) -> dict[str, str]:
    """複数銘柄の社名を一括取得（APIは使わずキャッシュ・ハードコードのみ）"""
    return {t: get_company_name(t, use_api=use_api) for t in tickers}


def display_name(ticker: str) -> str:
    """「社名 (コード)」形式で返す。社名不明ならコードのみ。"""
    name = get_company_name(ticker, use_api=False)
    if name == ticker.upper().replace(".T", ""):
        return ticker
    return f"{name} ({ticker})"
