"""ペーパートレード（仮想売買）エンジン

3市場（BTC/FX/日本株）でRSI+MACDシグナルを使い、
リアルマネーなしで売買シミュレーションを行う。
"""

import json
import os
import pandas as pd
import numpy as np
from datetime import datetime

PAPER_FILE = os.path.join(os.path.dirname(__file__), "..", ".paper_trades.json")

MARKETS = {
    "BTC":  {"ticker": "BTC-USD",  "interval": "1h",  "period": "7d",  "initial": 1000.0, "fee": 0.001, "unit": "USD", "decimals": 0},
    "FX":   {"ticker": "USDJPY=X", "interval": "1h",  "period": "7d",  "initial": 100000.0, "fee": 0.0002, "unit": "円", "decimals": 2},
    "株":   {"ticker": "^N225",    "interval": "1d",  "period": "3mo", "initial": 100000.0, "fee": 0.001, "unit": "円", "decimals": 0},
}


def _calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _calc_macd(close: pd.Series):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    return hist


def fetch_market_data(market: str) -> pd.DataFrame:
    import yfinance as yf
    cfg = MARKETS[market]
    df = yf.download(cfg["ticker"], period=cfg["period"],
                     interval=cfg["interval"], auto_adjust=True, progress=False)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df[["Close"]].copy()
    df.columns = ["Close"]
    df = df.dropna()
    return df


def get_signal(df: pd.DataFrame) -> str:
    """RSI + MACD の複合シグナル → 'buy' / 'sell' / 'hold'"""
    if len(df) < 30:
        return "hold"
    close = df["Close"].squeeze()
    rsi = _calc_rsi(close).iloc[-1]
    hist = _calc_macd(close)
    hist_now = hist.iloc[-1]
    hist_prev = hist.iloc[-2]

    rsi_buy = rsi < 35
    rsi_sell = rsi > 65
    macd_buy = hist_prev < 0 and hist_now >= 0
    macd_sell = hist_prev > 0 and hist_now <= 0

    if rsi_buy and macd_buy:
        return "buy"
    if rsi_sell and macd_sell:
        return "sell"
    if rsi_buy:
        return "buy_weak"
    if rsi_sell:
        return "sell_weak"
    return "hold"


def load_state() -> dict:
    if os.path.exists(PAPER_FILE):
        try:
            with open(PAPER_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "positions": {},
        "history": [],
        "balance": {m: MARKETS[m]["initial"] for m in MARKETS},
        "started_at": datetime.now().isoformat(),
    }


def save_state(state: dict):
    with open(PAPER_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def run_paper_session(dry_run: bool = False, verbose: bool = True) -> dict:
    """全市場のシグナルを確認し、ペーパーポジションを更新する"""
    state = load_state()
    results = {}

    for market, cfg in MARKETS.items():
        if verbose:
            print(f"\n[{market}] データ取得中...")

        df = fetch_market_data(market)
        if df.empty:
            if verbose:
                print(f"  データ取得失敗")
            results[market] = {"error": "データ取得失敗"}
            continue

        close = float(df["Close"].iloc[-1])
        signal = get_signal(df)
        rsi = float(_calc_rsi(df["Close"].squeeze()).iloc[-1])
        hist = float(_calc_macd(df["Close"].squeeze()).iloc[-1])

        position = state["positions"].get(market)
        balance = state["balance"][market]
        fee = cfg["fee"]
        unit = cfg["unit"]
        dec = cfg["decimals"]

        if verbose:
            print(f"  現在値: {close:,.{dec}f} {unit}  RSI: {rsi:.1f}  MACD hist: {hist:.4f}")
            print(f"  シグナル: {signal}  残高: {balance:,.{dec}f} {unit}  ポジション: {'あり' if position else 'なし'}")

        action = None

        # 買いシグナル & ポジションなし
        if signal in ("buy", "buy_weak") and not position and balance > close * (1 + fee):
            shares = balance * 0.95 / (close * (1 + fee))
            cost = shares * close * (1 + fee)
            state["balance"][market] -= cost
            state["positions"][market] = {
                "entry_price": close,
                "shares": shares,
                "entry_time": datetime.now().isoformat(),
                "signal": signal,
            }
            action = f"買い @{close:,.{dec}f}"
            if verbose:
                print(f"  → 買い実行 @{close:,.{dec}f} {unit}  ({shares:.6f}単位)")

        # 売りシグナル & ポジションあり
        elif signal in ("sell", "sell_weak") and position:
            shares = position["shares"]
            proceeds = shares * close * (1 - fee)
            entry_cost = shares * position["entry_price"] * (1 + fee)
            pnl = proceeds - entry_cost
            pnl_pct = pnl / entry_cost * 100

            state["balance"][market] += proceeds
            state["history"].append({
                "market": market,
                "entry_price": position["entry_price"],
                "exit_price": close,
                "shares": shares,
                "pnl": round(pnl, dec),
                "pnl_pct": round(pnl_pct, 2),
                "entry_time": position["entry_time"],
                "exit_time": datetime.now().isoformat(),
            })
            del state["positions"][market]
            action = f"売り @{close:,.{dec}f}  損益: {pnl:+,.{dec}f} {unit} ({pnl_pct:+.1f}%)"
            if verbose:
                print(f"  → 売り実行 @{close:,.{dec}f}  損益: {pnl:+,.{dec}f} {unit} ({pnl_pct:+.1f}%)")

        # 含み損益
        unrealized = 0.0
        if state["positions"].get(market):
            pos = state["positions"][market]
            unrealized = (close - pos["entry_price"]) * pos["shares"]

        total = state["balance"][market] + (
            state["positions"][market]["shares"] * close if state["positions"].get(market) else 0
        )
        initial = cfg["initial"]
        total_pnl_pct = (total / initial - 1) * 100

        results[market] = {
            "close": close,
            "signal": signal,
            "rsi": round(rsi, 1),
            "action": action,
            "balance": state["balance"][market],
            "position": state["positions"].get(market),
            "unrealized": round(unrealized, dec),
            "total": round(total, dec),
            "total_pnl_pct": round(total_pnl_pct, 2),
        }

    if not dry_run:
        save_state(state)

    return {"results": results, "history": state["history"], "state": state}


def get_summary() -> dict:
    """現在の損益サマリーを返す"""
    state = load_state()
    summary = {}

    for market, cfg in MARKETS.items():
        df = fetch_market_data(market)
        close = float(df["Close"].iloc[-1]) if not df.empty else 0
        balance = state["balance"][market]
        position = state["positions"].get(market)
        pos_value = position["shares"] * close if position else 0
        total = balance + pos_value
        initial = cfg["initial"]
        trades = [h for h in state["history"] if h["market"] == market]
        total_pnl = sum(t["pnl"] for t in trades)
        wins = sum(1 for t in trades if t["pnl"] > 0)

        summary[market] = {
            "initial": initial,
            "total": round(total, cfg["decimals"]),
            "total_pnl_pct": round((total / initial - 1) * 100, 2),
            "realized_pnl": round(total_pnl, cfg["decimals"]),
            "trades": len(trades),
            "wins": wins,
            "win_rate": round(wins / len(trades) * 100, 1) if trades else 0,
            "unit": cfg["unit"],
        }

    return summary


def reset_paper_trades():
    """ペーパートレードをリセット"""
    if os.path.exists(PAPER_FILE):
        os.remove(PAPER_FILE)
