import yfinance as yf
import pandas as pd
import requests
import os
import time
from datetime import datetime, timedelta


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


# ── J-Quants API（日本株リアルタイム・無料登録必須） ────────────────────────
class JQuantsClient:
    BASE = "https://api.jquants.com/v1"

    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self._refresh_token: str | None = None
        self._id_token: str | None = None
        self._token_expiry: datetime | None = None

    def _get_refresh_token(self) -> str:
        resp = requests.post(f"{self.BASE}/token/auth_user",
                             json={"mailaddress": self.email, "password": self.password},
                             timeout=10)
        resp.raise_for_status()
        return resp.json()["refreshToken"]

    def _get_id_token(self) -> str:
        if not self._refresh_token:
            self._refresh_token = self._get_refresh_token()
        resp = requests.post(f"{self.BASE}/token/auth_refresh",
                             params={"refreshtoken": self._refresh_token},
                             timeout=10)
        resp.raise_for_status()
        token = resp.json()["idToken"]
        self._id_token = token
        self._token_expiry = datetime.now() + timedelta(hours=23)
        return token

    def _headers(self) -> dict:
        if not self._id_token or datetime.now() > (self._token_expiry or datetime.min):
            self._get_id_token()
        return {"Authorization": f"Bearer {self._id_token}"}

    def get_daily_quotes(self, code: str, date: str | None = None) -> pd.DataFrame:
        """日次株価（コード: '7203' 形式）"""
        params = {"code": code}
        if date:
            params["date"] = date
        resp = requests.get(f"{self.BASE}/prices/daily_quotes",
                            headers=self._headers(), params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("daily_quotes", [])
        return pd.DataFrame(data)

    def get_price_range(self, code: str, date_from: str, date_to: str) -> pd.DataFrame:
        """期間指定で株価取得"""
        params = {"code": code, "date_from": date_from, "date_to": date_to}
        resp = requests.get(f"{self.BASE}/prices/daily_quotes",
                            headers=self._headers(), params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("daily_quotes", [])
        df = pd.DataFrame(data)
        if not df.empty:
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date").sort_index()
            df = df.rename(columns={
                "Open": "Open", "High": "High", "Low": "Low",
                "Close": "Close", "Volume": "Volume"
            })
        return df


def _get_jquants_client() -> JQuantsClient | None:
    email = os.getenv("JQUANTS_EMAIL")
    password = os.getenv("JQUANTS_PASSWORD")
    if email and password:
        return JQuantsClient(email, password)
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
