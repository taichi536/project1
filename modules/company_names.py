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
    # 日本株メジャー
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
    "9983": "ファーストリテイリング",
    "8766": "東京海上HD",
    "8591": "オリックス",
    "9301": "三菱倉庫",
    "4452": "花王",
    # 高配当・インフラ
    "5020": "ENEOSホールディングス",
    "8001": "伊藤忠商事",
    "8002": "丸紅",
    "1928": "積水ハウス",
    "8309": "三井住友TH",
    # 自動車・製造
    "7270": "SUBARU",
    "7201": "日産自動車",
    "7261": "マツダ",
    "7011": "三菱重工業",
    # 半導体・電子部品
    "6857": "アドバンテスト",
    "6723": "ルネサスエレクトロニクス",
    "6920": "レーザーテック",
    "6146": "ディスコ",
    "6971": "京セラ",
    "6976": "太陽誘電",
    # テック・ネット
    "3659": "ネクソン",
    "4755": "楽天グループ",
    "2413": "エムスリー",
    "4689": "Zホールディングス",
    "3765": "ガンホー",
    # 医薬品
    "4503": "アステラス製薬",
    "4523": "エーザイ",
    # 金融・証券
    "8725": "MS&AD",
    "8750": "第一生命HD",
    "8601": "大和証券G",
    "8604": "野村HD",
    "8697": "JPX",
    "8830": "住友不動産",
    "3289": "東急不動産HD",
    "3003": "ヒューリック",
    "8308": "りそなHD",
    "8331": "千葉銀行",
    "8369": "京都銀行",
    "8355": "静岡銀行",
    # エネルギー
    "5019": "出光興産",
    "5021": "コスモエネルギー",
    "1605": "INPEX",
    "9531": "東京ガス",
    "9532": "大阪ガス",
    "9533": "東邦ガス",
    "9501": "東京電力HD",
    "9502": "中部電力",
    "9503": "関西電力",
    # 化学・素材
    "4183": "三井化学",
    "3407": "旭化成",
    "3405": "クラレ",
    "4208": "UBE",
    "4042": "東ソー",
    "4005": "住友化学",
    "5713": "住友金属鉱山",
    "5411": "JFEホールディングス",
    # 米国大型株
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
    "AMD": "Advanced Micro",
    "QCOM": "Qualcomm",
    "TXN": "Texas Instr.",
    "GS": "Goldman Sachs",
    "MS": "Morgan Stanley",
    "C": "Citigroup",
    "WFC": "Wells Fargo",
    "AXP": "American Express",
    "BLK": "BlackRock",
    "BX": "Blackstone",
    # AI・半導体（米国）
    "ASML": "ASML Holding",
    "TSM": "TSMC",
    "MU": "Micron",
    "AMAT": "Applied Materials",
    "KLAC": "KLA Corp",
    # テック（米国）
    "UBER": "Uber",
    "SHOP": "Shopify",
    # エネルギー（米国）
    "COP": "ConocoPhillips",
    "SLB": "Schlumberger",
    "BP": "BP plc",
    # 化学（米国）
    "LIN": "Linde",
    "APD": "Air Products",
    "DD": "DuPont",
    # 医薬品（米国）
    "PFE": "Pfizer",
    "ABT": "Abbott",
    "TMO": "Thermo Fisher",
    # 産業（米国）
    "HON": "Honeywell",
    "CAT": "Caterpillar",
    # ETF・インデックス
    "SPY": "S&P500 ETF",
    "QQQ": "NASDAQ ETF",
    "DIA": "ダウ ETF",
    "IWM": "Russell2000 ETF",
    "VT": "全世界株 ETF",
    "EEM": "新興国 ETF",
    "GLD": "金 ETF",
    "TLT": "米国長期債 ETF",
    "VNQ": "米国REIT ETF",
    "ARKK": "ARK ETF",
    "SOXX": "半導体 ETF",
    "XLK": "テクノロジー ETF",
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
