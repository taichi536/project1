import yfinance as yf
from modules.data_fetcher import normalize_ticker


def get_fundamental_summary(ticker: str) -> dict:
    t = normalize_ticker(ticker)
    info = yf.Ticker(t).info

    def pct(v):
        return round(v * 100, 2) if v is not None else None

    return {
        "企業名": info.get("longName") or info.get("shortName", ticker),
        "セクター": info.get("sector", "N/A"),
        "業種": info.get("industry", "N/A"),
        "時価総額": info.get("marketCap"),
        "PBR": info.get("priceToBook"),
        "PER（実績）": info.get("trailingPE"),
        "PER（予想）": info.get("forwardPE"),
        "PEGレシオ": info.get("pegRatio"),
        "ROE": pct(info.get("returnOnEquity")),
        "ROA": pct(info.get("returnOnAssets")),
        "営業利益率": pct(info.get("operatingMargins")),
        "純利益率": pct(info.get("profitMargins")),
        "売上成長率": pct(info.get("revenueGrowth")),
        "利益成長率": pct(info.get("earningsGrowth")),
        "配当利回り": pct(info.get("dividendYield")),
        "自己資本比率": None,  # balance_sheetから別途計算
        "FCF利回り": None,     # cashflowから別途計算
        "ベータ": info.get("beta"),
        "52週高値": info.get("fiftyTwoWeekHigh"),
        "52週安値": info.get("fiftyTwoWeekLow"),
        "アナリスト推奨": info.get("recommendationKey", "N/A"),
    }


def get_risk_metrics(ticker: str, price: float, atr: float) -> dict:
    """ATRベースの損切りライン計算"""
    stop_loss_1x = price - atr
    stop_loss_2x = price - 2 * atr
    risk_pct_1x = (atr / price) * 100
    risk_pct_2x = risk_pct_1x * 2

    return {
        "現在値": price,
        "ATR": round(atr, 2),
        "損切りライン (ATR×1)": round(stop_loss_1x, 2),
        "損切りライン (ATR×2)": round(stop_loss_2x, 2),
        "リスク率 (ATR×1)": round(risk_pct_1x, 2),
        "リスク率 (ATR×2)": round(risk_pct_2x, 2),
    }
