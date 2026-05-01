import yfinance as yf
import pandas as pd


def normalize_ticker(ticker: str) -> str:
    ticker = ticker.strip().upper()
    # 日本株：4桁数字なら .T を付与
    if ticker.isdigit() and len(ticker) == 4:
        ticker = ticker + ".T"
    return ticker


def fetch_ohlcv(ticker: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    t = normalize_ticker(ticker)
    df = yf.download(t, period=period, interval=interval, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"データを取得できませんでした: {ticker}")
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    return df


def fetch_info(ticker: str) -> dict:
    t = normalize_ticker(ticker)
    info = yf.Ticker(t).info
    return info


def fetch_financials(ticker: str) -> dict:
    t = normalize_ticker(ticker)
    tk = yf.Ticker(t)
    return {
        "income_stmt": tk.financials,
        "balance_sheet": tk.balance_sheet,
        "cashflow": tk.cashflow,
    }
