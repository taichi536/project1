import pandas as pd
import yfinance as yf
from modules.data_fetcher import normalize_ticker


NAGOCHOU_CRITERIA = {
    "PBR": ("pbRatio", "<=", 1.0),
    "PER": ("forwardPE", "<=", 10.0),
    "自己資本比率": ("debtToEquity", "computed", 60.0),
    "配当利回り": ("dividendYield", ">=", 0.03),
}


def _piotroski_score(info: dict, tk: yf.Ticker) -> int:
    """Piotroski F-Score (0〜9) の簡易版"""
    score = 0
    try:
        bs = tk.balance_sheet
        cf = tk.cashflow
        fs = tk.financials

        if bs is None or bs.empty or fs is None or fs.empty:
            return -1

        # ROA > 0
        net_income = fs.loc["Net Income"].iloc[0] if "Net Income" in fs.index else None
        total_assets = bs.loc["Total Assets"].iloc[0] if "Total Assets" in bs.index else None
        if net_income is not None and total_assets and total_assets > 0:
            if net_income / total_assets > 0:
                score += 1

        # 営業CF > 0
        op_cf = None
        for key in ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"]:
            if key in cf.index:
                op_cf = cf.loc[key].iloc[0]
                break
        if op_cf is not None and op_cf > 0:
            score += 1

        # ROA改善
        total_assets_prev = None  # 以降で参照するため先に初期化
        net_income_prev = None
        if len(fs.columns) >= 2 and net_income is not None and total_assets:
            net_income_prev = fs.loc["Net Income"].iloc[1] if "Net Income" in fs.index else None
            total_assets_prev = bs.loc["Total Assets"].iloc[1] if len(bs.columns) >= 2 and "Total Assets" in bs.index else None
            if net_income_prev is not None and total_assets_prev and total_assets_prev > 0:
                if (net_income / total_assets) > (net_income_prev / total_assets_prev):
                    score += 1

        # 自己資本比率改善
        eq = bs.loc["Stockholders Equity"].iloc[0] if "Stockholders Equity" in bs.index else None
        eq_prev = bs.loc["Stockholders Equity"].iloc[1] if "Stockholders Equity" in bs.index and len(bs.columns) >= 2 else None
        if eq is not None and total_assets and eq_prev is not None and total_assets_prev:
            if (eq / total_assets) > (eq_prev / total_assets_prev):
                score += 1

        # 流動比率改善
        curr_a = bs.loc["Current Assets"].iloc[0] if "Current Assets" in bs.index else None
        curr_l = bs.loc["Current Liabilities"].iloc[0] if "Current Liabilities" in bs.index else None
        curr_a_p = bs.loc["Current Assets"].iloc[1] if "Current Assets" in bs.index and len(bs.columns) >= 2 else None
        curr_l_p = bs.loc["Current Liabilities"].iloc[1] if "Current Liabilities" in bs.index and len(bs.columns) >= 2 else None
        if all(v is not None and v != 0 for v in [curr_a, curr_l, curr_a_p, curr_l_p]):
            if (curr_a / curr_l) > (curr_a_p / curr_l_p):
                score += 1

        # 新株発行なし（株式数増加なし）
        shares = info.get("sharesOutstanding", 0)
        shares_prev = info.get("floatShares", 0)
        if shares and shares_prev and shares <= shares_prev * 1.01:
            score += 1

        # 売上総利益率改善
        gross = fs.loc["Gross Profit"].iloc[0] if "Gross Profit" in fs.index else None
        rev = fs.loc["Total Revenue"].iloc[0] if "Total Revenue" in fs.index else None
        gross_p = fs.loc["Gross Profit"].iloc[1] if "Gross Profit" in fs.index and len(fs.columns) >= 2 else None
        rev_p = fs.loc["Total Revenue"].iloc[1] if "Total Revenue" in fs.index and len(fs.columns) >= 2 else None
        if all(v is not None and v != 0 for v in [gross, rev, gross_p, rev_p]):
            if (gross / rev) > (gross_p / rev_p):
                score += 1

        # 資産回転率改善
        if total_assets and total_assets_prev and rev and rev_p:
            if (rev / total_assets) > (rev_p / total_assets_prev):
                score += 1

        # accrual（CFO > ROA）
        if op_cf is not None and net_income is not None and total_assets:
            if op_cf / total_assets > net_income / total_assets:
                score += 1

    except Exception:
        return -1

    return score


def screen_single(ticker: str) -> dict:
    t = normalize_ticker(ticker)
    tk = yf.Ticker(t)
    info = tk.info

    result = {"ticker": ticker, "合否": True, "詳細": {}}

    # PBR
    pbr = info.get("priceToBook")
    result["詳細"]["PBR"] = {
        "値": pbr,
        "基準": "≤ 1.0",
        "合否": pbr is not None and pbr <= 1.0,
    }

    # PER
    per = info.get("trailingPE") or info.get("forwardPE")
    result["詳細"]["PER"] = {
        "値": per,
        "基準": "≤ 10.0",
        "合否": per is not None and per <= 10.0,
    }

    # 自己資本比率（equity/assets）
    eq_ratio = None
    try:
        bs = tk.balance_sheet
        if bs is not None and not bs.empty:
            eq = bs.loc["Stockholders Equity"].iloc[0] if "Stockholders Equity" in bs.index else None
            ta = bs.loc["Total Assets"].iloc[0] if "Total Assets" in bs.index else None
            if eq is not None and ta and ta > 0:
                eq_ratio = eq / ta * 100
    except Exception:
        pass
    result["詳細"]["自己資本比率"] = {
        "値": eq_ratio,
        "基準": "≥ 60%",
        "合否": eq_ratio is not None and eq_ratio >= 60.0,
    }

    # 配当利回り
    div_yield = info.get("dividendYield")
    if div_yield is not None:
        div_yield_pct = div_yield * 100
    else:
        div_yield_pct = None
    result["詳細"]["配当利回り"] = {
        "値": div_yield_pct,
        "基準": "≥ 3.0%",
        "合否": div_yield_pct is not None and div_yield_pct >= 3.0,
    }

    # 売上高営業利益率（直近期）
    op_margin = info.get("operatingMargins")
    if op_margin is not None:
        op_margin_pct = op_margin * 100
    else:
        op_margin_pct = None
    result["詳細"]["営業利益率"] = {
        "値": op_margin_pct,
        "基準": "≥ 10%",
        "合否": op_margin_pct is not None and op_margin_pct >= 10.0,
    }

    # 売上成長（revenue growth）
    rev_growth = info.get("revenueGrowth")
    if rev_growth is not None:
        rev_growth_pct = rev_growth * 100
    else:
        rev_growth_pct = None
    result["詳細"]["売上成長率"] = {
        "値": rev_growth_pct,
        "基準": "> 0%（継続成長）",
        "合否": rev_growth_pct is not None and rev_growth_pct > 0,
    }

    # Piotroski Fスコア
    f_score = _piotroski_score(info, tk)
    result["詳細"]["Piotroski Fスコア"] = {
        "値": f_score if f_score >= 0 else "取得不可",
        "基準": "≥ 7（優良）",
        "合否": f_score >= 7,
    }

    # 総合合否（必須6条件）
    must_pass = ["PBR", "PER", "自己資本比率", "配当利回り", "営業利益率", "売上成長率"]
    result["合否"] = all(result["詳細"][k]["合否"] for k in must_pass)

    return result
