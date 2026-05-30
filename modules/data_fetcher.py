import yfinance as yf
import pandas as pd
import requests
import json
import os
import time
from pathlib import Path
from datetime import datetime, timedelta
try:
    import streamlit as st
    def _st_cache(ttl: int):
        return st.cache_data(ttl=ttl, show_spinner=False)
except ImportError:
    def _st_cache(ttl: int):  # type: ignore
        return lambda f: f


# ── USD/JPY 為替レートキャッシュ ─────────────────────────────────────────────
_fx_cache: dict = {}
_FX_CACHE_TTL = 300   # 5分
_FX_FILE_CACHE = Path(__file__).parent.parent / ".fx_rate_cache.json"
_FX_DEFAULT = 150.0   # APIが全て失敗した場合のデフォルト


def _load_fx_file_cache() -> dict:
    try:
        if _FX_FILE_CACHE.exists():
            return json.loads(_FX_FILE_CACHE.read_text())
    except Exception:
        pass
    return {}


def _save_fx_file_cache(rate: float):
    try:
        _FX_FILE_CACHE.write_text(json.dumps({"rate": rate, "saved_at": time.time()}, ensure_ascii=False))
    except Exception:
        pass


def set_usdjpy_rate(rate: float):
    """UIから手動でUSD/JPYレートを設定する"""
    if 80 < rate < 200:
        _fx_cache["rate"] = rate
        _fx_cache["fetched_at"] = time.time()
        _save_fx_file_cache(rate)


def _fetch_usdjpy_from_api() -> float | None:
    """複数の無料APIを順番に試してUSD/JPYレートを取得する"""
    import urllib.request
    apis = [
        # frankfurter.app（ECBデータ、無料・APIキー不要）
        ("https://api.frankfurter.app/latest?from=USD&to=JPY",
         lambda d: d["rates"]["JPY"]),
        # exchangerate-api.com（無料枠あり）
        ("https://api.exchangerate-api.com/v4/latest/USD",
         lambda d: d["rates"]["JPY"]),
        # open.er-api.com（無料・APIキー不要）
        ("https://open.er-api.com/v6/latest/USD",
         lambda d: d["rates"]["JPY"]),
    ]
    for url, extractor in apis:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read())
                rate = float(extractor(data))
                if 80 < rate < 200:
                    return rate
        except Exception:
            continue
    return None


def get_usdjpy_rate() -> float:
    """USD/JPY レートを返す（5分キャッシュ）。
    取得順: yfinance → 無料FX API → ファイルキャッシュ → デフォルト150円
    """
    now = time.time()
    if _fx_cache.get("rate") and now - _fx_cache.get("fetched_at", 0) < _FX_CACHE_TTL:
        return _fx_cache["rate"]

    def _store(rate: float) -> float:
        _fx_cache["rate"] = rate
        _fx_cache["fetched_at"] = now
        _save_fx_file_cache(rate)
        return rate

    # 方法1: yfinance fast_info
    for sym in ["USDJPY=X", "JPY=X"]:
        try:
            tk = yf.Ticker(sym)
            rate = tk.fast_info.get("last_price") or tk.fast_info.get("regularMarketPrice")
            if rate and 80 < rate < 200:
                return _store(float(rate))
        except Exception:
            continue

    # 方法2: yfinance download
    try:
        df = yf.download("USDJPY=X", period="2d", auto_adjust=True, progress=False)
        if not df.empty:
            close = df["Close"]
            rate = float(close.iloc[-1] if hasattr(close.iloc[-1], "__float__") else close.iloc[-1].iloc[0])
            if 80 < rate < 200:
                return _store(rate)
    except Exception:
        pass

    # 方法3: 無料FX API（frankfurter / exchangerate-api / open.er-api）
    rate = _fetch_usdjpy_from_api()
    if rate:
        return _store(rate)

    # 方法4: ファイルキャッシュから復元（古くても使う）
    file_cache = _load_fx_file_cache()
    if file_cache.get("rate") and 80 < file_cache["rate"] < 200:
        _fx_cache["rate"] = file_cache["rate"]
        _fx_cache["fetched_at"] = now
        return _fx_cache["rate"]

    return _FX_DEFAULT


def is_us_ticker(ticker: str) -> bool:
    """米国株かどうか判定（数字のみ or .T 末尾は日本株）"""
    t = ticker.strip().upper()
    return not (t.isdigit() or t.endswith(".T"))


def normalize_ticker(ticker: str) -> str:
    ticker = ticker.strip().upper()
    if ticker.isdigit() and len(ticker) == 4:
        ticker = ticker + ".T"
    return ticker


def is_japan_ticker(ticker: str) -> bool:
    t = normalize_ticker(ticker)
    return t.endswith(".T")


# ── yfinance fast_info（最新価格をほぼリアルタイムで取得） ────────────────────
def fetch_current_price(ticker: str) -> dict:
    """
    fast_info を使って最新価格を取得。
    yfinanceのOHLCVより遅延が少ない（数分〜ほぼリアル）。
    """
    t = normalize_ticker(ticker)
    try:
        tk = yf.Ticker(t)
        fi = tk.fast_info
        price = fi.get("last_price") or fi.get("regularMarketPrice")
        prev = fi.get("previous_close") or fi.get("regularMarketPreviousClose")
        change_pct = ((price - prev) / prev * 100) if price and prev else None
        return {
            "ticker": ticker,
            "price": price,
            "prev_close": prev,
            "change_pct": round(change_pct, 2) if change_pct else None,
            "source": "yfinance_fast",
        }
    except Exception as e:
        return {"ticker": ticker, "price": None, "error": str(e)}


# ── J-Quants API（日本株・v2対応） ───────────────────────────────────────────
class JQuantsClient:
    BASE_V2 = "https://api.jquants.com/v2"
    BASE_V1 = "https://api.jquants.com/v1"

    def __init__(self, api_key: str | None = None,
                 refresh_token: str | None = None,
                 email: str | None = None, password: str | None = None):
        self._api_key = api_key
        self._init_refresh_token = refresh_token
        self.email = email
        self.password = password
        self._refresh_token: str | None = refresh_token
        self._id_token: str | None = None
        self._token_expiry: datetime | None = None

    def _headers(self) -> dict:
        if self._api_key:
            return {"x-api-key": self._api_key}
        if not self._id_token or datetime.now() > (self._token_expiry or datetime.min):
            self._get_id_token()
        return {"Authorization": f"Bearer {self._id_token}"}

    def _get_id_token(self) -> str:
        # v1: メール/パスワード → リフレッシュトークン → IDトークン
        if not self._refresh_token:
            resp = requests.post(f"{self.BASE_V1}/token/auth_user",
                                 json={"mailaddress": self.email, "password": self.password},
                                 timeout=10)
            if not resp.ok:
                raise RuntimeError(f"J-Quants auth error {resp.status_code}: {resp.text[:200]}")
            self._refresh_token = resp.json()["refreshToken"]
        resp = requests.post(f"{self.BASE_V1}/token/auth_refresh",
                             params={"refreshtoken": self._refresh_token}, timeout=10)
        if not resp.ok:
            raise RuntimeError(f"J-Quants refresh error {resp.status_code}: {resp.text[:200]}")
        token = resp.json()["idToken"]
        self._id_token = token
        self._token_expiry = datetime.now() + timedelta(hours=23)
        return token

    def get_price_range(self, code: str, date_from: str, date_to: str) -> pd.DataFrame:
        """期間指定で株価取得"""
        if self._api_key:
            return self._get_price_range_v2(code, date_from, date_to)
        return self._get_price_range_v1(code, date_from, date_to)

    def _get_price_range_v2(self, code: str, date_from: str, date_to: str) -> pd.DataFrame:
        params = {"code": code, "from": date_from, "to": date_to}
        resp = requests.get(f"{self.BASE_V2}/equities/bars/daily",
                            headers=self._headers(), params=params, timeout=20)
        if not resp.ok:
            raise RuntimeError(f"J-Quants v2 error {resp.status_code}: {resp.text[:200]}")

        body = resp.json()
        data = body.get("daily_quotes", body.get("data", []))
        df = pd.DataFrame(data)
        if not df.empty:
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date").sort_index()
            df = df.rename(columns={
                "AdjOpen": "Open", "AdjHigh": "High", "AdjLow": "Low",
                "AdjClose": "Close", "Volume": "Volume",
                "AdjO": "Open", "AdjH": "High", "AdjL": "Low",
                "AdjC": "Close", "AdjVo": "Volume",
            })
            cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            df = df[cols]
        return df

    def _get_price_range_v1(self, code: str, date_from: str, date_to: str) -> pd.DataFrame:
        params = {"code": code, "date_from": date_from, "date_to": date_to}
        resp = requests.get(f"{self.BASE_V1}/prices/daily_quotes",
                            headers=self._headers(), params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("daily_quotes", [])
        df = pd.DataFrame(data)
        if not df.empty:
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date").sort_index()
            cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            df = df[cols]
        return df

    def get_company_master(self) -> dict[str, str]:
        """銘柄コード→社名の辞書を返す（/equities/master）"""
        resp = requests.get(f"{self.BASE_V2}/equities/master",
                            headers=self._headers(), timeout=30)
        if not resp.ok:
            raise RuntimeError(f"J-Quants master error {resp.status_code}: {resp.text[:200]}")
        data = resp.json().get("data", [])
        return {
            row["Code"][:4]: row.get("CompanyName", "")
            for row in data if row.get("Code") and row.get("CompanyName")
        }

    def get_trading_calendar(self, date_from: str, date_to: str) -> set[str]:
        """取引日の日付セットを返す（/markets/calendar）"""
        resp = requests.get(f"{self.BASE_V2}/markets/calendar",
                            headers=self._headers(),
                            params={"from": date_from, "to": date_to}, timeout=15)
        if not resp.ok:
            raise RuntimeError(f"J-Quants calendar error {resp.status_code}: {resp.text[:200]}")
        data = resp.json().get("data", [])
        return {row["Date"] for row in data if row.get("HolidayDivision") == "1"}

    def get_earnings_calendar(self, code: str) -> list[dict]:
        """決算発表予定日を返す（/equities/earnings-calendar）"""
        resp = requests.get(f"{self.BASE_V2}/equities/earnings-calendar",
                            headers=self._headers(),
                            params={"code": code}, timeout=10)
        if not resp.ok:
            return []
        return resp.json().get("data", [])


def _get_jquants_client() -> JQuantsClient | None:
    # JQUANTS_API_KEYはdirect API key（Bearer token）として使用
    api_key = os.getenv("JQUANTS_API_KEY")
    if api_key:
        return JQuantsClient(api_key=api_key)
    # リフレッシュトークン（JWT形式 eyJ...）
    refresh_token = os.getenv("JQUANTS_REFRESH_TOKEN")
    if refresh_token:
        return JQuantsClient(refresh_token=refresh_token)
    # メール＋パスワード方式
    email = os.getenv("JQUANTS_EMAIL")
    password = os.getenv("JQUANTS_PASSWORD")
    if email and password:
        return JQuantsClient(email=email, password=password)
    return None


_COMPANY_MASTER_CACHE_FILE = Path(__file__).parent.parent / ".jquants_company_master.json"
_CALENDAR_CACHE_FILE = Path(__file__).parent.parent / ".jquants_calendar.json"


def fetch_jquants_company_master() -> dict[str, str]:
    """J-Quantsから全上場銘柄の社名を取得（週1回更新キャッシュ）"""
    import time
    if _COMPANY_MASTER_CACHE_FILE.exists():
        try:
            cached = json.loads(_COMPANY_MASTER_CACHE_FILE.read_text())
            if time.time() - cached.get("_fetched_at", 0) < 86400 * 7:
                return {k: v for k, v in cached.items() if k != "_fetched_at"}
        except Exception:
            pass
    client = _get_jquants_client()
    if not client:
        return {}
    try:
        master = client.get_company_master()
        master["_fetched_at"] = time.time()
        _COMPANY_MASTER_CACHE_FILE.write_text(json.dumps(master, ensure_ascii=False))
        return {k: v for k, v in master.items() if k != "_fetched_at"}
    except Exception:
        return {}


def fetch_jquants_is_trading_day(check_date: str) -> bool | None:
    """J-Quantsで取引日かどうか確認。取得できない場合はNoneを返す"""
    import time
    from datetime import timedelta
    date_from = (datetime.strptime(check_date, "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")
    date_to = (datetime.strptime(check_date, "%Y-%m-%d") + timedelta(days=5)).strftime("%Y-%m-%d")
    cache_key = f"{date_from}_{date_to}"
    if _CALENDAR_CACHE_FILE.exists():
        try:
            cached = json.loads(_CALENDAR_CACHE_FILE.read_text())
            if cached.get("_key") == cache_key:
                return check_date in cached.get("trading_days", [])
        except Exception:
            pass
    client = _get_jquants_client()
    if not client:
        return None
    try:
        trading_days = client.get_trading_calendar(date_from, date_to)
        _CALENDAR_CACHE_FILE.write_text(json.dumps(
            {"_key": cache_key, "trading_days": list(trading_days)}, ensure_ascii=False))
        return check_date in trading_days
    except Exception:
        return None


# ── Alpaca Markets API（米国株リアルタイム・無料登録必須） ─────────────────
def fetch_alpaca_price(ticker: str) -> dict | None:
    api_key = os.getenv("ALPACA_API_KEY")
    secret = os.getenv("ALPACA_SECRET_KEY")
    if not api_key or not secret:
        return None
    try:
        url = f"https://data.alpaca.markets/v2/stocks/{ticker}/quotes/latest"
        resp = requests.get(url,
                            headers={"APCA-API-KEY-ID": api_key,
                                     "APCA-API-SECRET-KEY": secret},
                            timeout=8)
        if resp.status_code == 200:
            q = resp.json().get("quote", {})
            mid = (q.get("ap", 0) + q.get("bp", 0)) / 2
            return {"ticker": ticker, "price": mid, "source": "alpaca_realtime"}
    except Exception:
        pass
    return None


# ── 統合インターフェース ─────────────────────────────────────────────────────
def fetch_realtime_price(ticker: str) -> dict:
    """
    利用可能な最良のソースから現在価格を取得。
    優先順位: Alpaca(US) > J-Quants(JP) > yfinance fast_info
    """
    if not is_japan_ticker(ticker):
        alpaca = fetch_alpaca_price(ticker)
        if alpaca:
            return alpaca

    result = fetch_current_price(ticker)
    return result


@_st_cache(ttl=300)
def fetch_ohlcv(ticker: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    t = normalize_ticker(ticker)

    # SMA75を計算するには最低100日分必要。短期間を自動延長（日足のみ）
    if interval == "1d":
        min_days = {"1mo": "3mo", "2mo": "6mo", "3mo": "6mo"}
        period = min_days.get(period, period)

    # yfinance非標準の期間（14d, 30d, 60d等）はstart日付に変換
    _non_standard = {
        "3d": 3, "7d": 7, "14d": 14, "21d": 21,
        "30d": 30, "45d": 45, "60d": 60, "90d": 90,
    }
    _start_date = None
    if period in _non_standard:
        _start_date = (datetime.now() - timedelta(days=_non_standard[period])).strftime("%Y-%m-%d")

    # J-Quantsが使えて日本株なら使用
    if is_japan_ticker(ticker) and interval == "1d":
        client = _get_jquants_client()
        if client:
            try:
                code = ticker.replace(".T", "").zfill(4)
                date_to = datetime.now().strftime("%Y-%m-%d")
                period_map = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "5y": 1825}
                days = period_map.get(period, 180)
                date_from = _start_date or (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                df = client.get_price_range(code, date_from, date_to)
                if not df.empty and all(c in df.columns for c in ["Open", "High", "Low", "Close"]):
                    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            except Exception:
                pass  # フォールバック

    if _start_date:
        df = yf.download(t, start=_start_date, interval=interval, auto_adjust=True, progress=False)
    else:
        df = yf.download(t, period=period, interval=interval, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"データを取得できませんでした: {ticker}")
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()


@_st_cache(ttl=3600)
def fetch_earnings_date(ticker: str) -> dict:
    """次の決算発表日と残り日数を返す"""
    try:
        t = normalize_ticker(ticker)
        info = yf.Ticker(t).info
        ed = info.get("earningsDate") or info.get("earningsTimestamp")
        if ed:
            if isinstance(ed, (list, tuple)) and ed:
                ed = ed[0]
            if isinstance(ed, (int, float)):
                d = datetime.fromtimestamp(ed).date()
            else:
                d = pd.Timestamp(ed).date()
            days_until = (d - datetime.now().date()).days
            if 0 <= days_until <= 180:
                return {"date": str(d), "days_until": days_until}
    except Exception:
        pass
    return {"date": None, "days_until": None}


@_st_cache(ttl=3600)
def fetch_info(ticker: str) -> dict:
    t = normalize_ticker(ticker)
    return yf.Ticker(t).info


def fetch_financials(ticker: str) -> dict:
    t = normalize_ticker(ticker)
    tk = yf.Ticker(t)
    return {
        "income_stmt": tk.financials,
        "balance_sheet": tk.balance_sheet,
        "cashflow": tk.cashflow,
    }
