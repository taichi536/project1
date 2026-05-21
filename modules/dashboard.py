import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from modules.data_fetcher import fetch_ohlcv, fetch_info, normalize_ticker, fetch_realtime_price
from modules.technical import compute_all
from modules.signals import evaluate_signals, overall_signal

WATCHLIST_PATH = Path(__file__).parent.parent / "watchlist.json"
_SCAN_CACHE_FILE = Path(__file__).parent.parent / ".scan_cache.json"
_CACHE_TTL_SECONDS = 300  # 5分間キャッシュ


def load_watchlist() -> list[str]:
    if WATCHLIST_PATH.exists():
        return json.loads(WATCHLIST_PATH.read_text())
    return ["7203", "9984", "6758", "AAPL", "MSFT"]


def save_watchlist(tickers: list[str]):
    WATCHLIST_PATH.write_text(json.dumps(tickers, ensure_ascii=False))


def _load_cache() -> dict:
    if _SCAN_CACHE_FILE.exists():
        try:
            return json.loads(_SCAN_CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_cache(cache: dict):
    try:
        _SCAN_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False))
    except Exception:
        pass


def scan_ticker(ticker: str, use_cache: bool = True) -> dict:
    """1銘柄をスキャンしてシグナル付きのサマリーを返す"""
    # キャッシュチェック
    if use_cache:
        cache = _load_cache()
        entry = cache.get(ticker)
        if entry and time.time() - entry.get("_cached_at", 0) < _CACHE_TTL_SECONDS:
            return {k: v for k, v in entry.items() if k != "_cached_at"}

    try:
        df = fetch_ohlcv(ticker, period="3mo")
        df = compute_all(df)
        signals = evaluate_signals(df)
        verdict, score = overall_signal(signals, df=df)

        # fast_info で最新価格を上書き（遅延を最小化）
        rt = fetch_realtime_price(ticker)
        if rt.get("price"):
            close = rt["price"]
            prev_close = rt.get("prev_close") or df["Close"].iloc[-1]
            change_pct = rt.get("change_pct") or (close - prev_close) / prev_close * 100
        else:
            close = df["Close"].iloc[-1]
            prev_close = df["Close"].iloc[-2] if len(df) >= 2 else close
            change_pct = (close - prev_close) / prev_close * 100

        rsi = df["RSI"].dropna().iloc[-1] if "RSI" in df.columns else None
        atr = df["ATR"].dropna().iloc[-1] if "ATR" in df.columns else None
        macd_hist = df["MACD_hist"].dropna().iloc[-1] if "MACD_hist" in df.columns else None

        reasons = []
        for s in sorted(signals, key=lambda x: abs(x["スコア"]), reverse=True)[:2]:
            if abs(s["スコア"]) >= 1:
                reasons.append(s["判定"])

        result = {
            "ticker": ticker,
            "現在値": round(close, 2),
            "前日比(%)": round(change_pct, 2),
            "シグナル": verdict,
            "スコア": score,
            "RSI": round(rsi, 1) if rsi is not None else None,
            "MACD方向": "↑" if macd_hist and macd_hist > 0 else "↓",
            "理由": " / ".join(reasons) if reasons else "-",
            "エラー": None,
        }

        # キャッシュに保存
        if use_cache:
            cache = _load_cache()
            cache[ticker] = {**result, "_cached_at": time.time()}
            _save_cache(cache)

        return result
    except Exception as e:
        return {
            "ticker": ticker,
            "現在値": None,
            "前日比(%)": None,
            "シグナル": "エラー",
            "スコア": 0,
            "RSI": None,
            "MACD方向": "-",
            "理由": str(e)[:40],
            "エラー": str(e),
        }


def scan_all(tickers: list[str], max_workers: int = 6) -> list[dict]:
    """並列スキャン（最大6銘柄同時取得）"""
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ticker = {executor.submit(scan_ticker, t): t for t in tickers}
        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                results[ticker] = future.result()
            except Exception as e:
                results[ticker] = {
                    "ticker": ticker, "現在値": None, "前日比(%)": None,
                    "シグナル": "エラー", "スコア": 0, "RSI": None,
                    "MACD方向": "-", "理由": str(e)[:40], "エラー": str(e),
                }
    # 元の順序を維持
    return [results[t] for t in tickers if t in results]
