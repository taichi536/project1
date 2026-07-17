import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import yfinance as yf
from modules.data_fetcher import fetch_ohlcv, normalize_ticker, fetch_realtime_price
from modules.technical import compute_all
from modules.signals import evaluate_signals, overall_signal

from modules import userstore

_LEGACY_WATCHLIST = Path(__file__).parent.parent / "watchlist.json"
_LEGACY_SCAN_CACHE = Path(__file__).parent.parent / ".scan_cache.json"
_CACHE_TTL_SECONDS = 1800  # 30分間キャッシュ


def _watchlist_path() -> Path:
    return userstore.user_path("watchlist.json", legacy=_LEGACY_WATCHLIST)


def _scan_cache_path() -> Path:
    return userstore.user_path("scan_cache.json", legacy=_LEGACY_SCAN_CACHE)


def load_watchlist() -> list[str]:
    p = _watchlist_path()
    if p.exists():
        return json.loads(p.read_text())
    return ["7203", "9984", "6758", "AAPL", "MSFT"]


def save_watchlist(tickers: list[str]):
    _watchlist_path().write_text(json.dumps(tickers, ensure_ascii=False))


def _load_cache() -> dict:
    p = _scan_cache_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {}


def _save_cache(cache: dict):
    try:
        _scan_cache_path().write_text(json.dumps(cache, ensure_ascii=False))
    except Exception:
        pass


def _batch_fetch_ohlcv(tickers: list[str], period: str = "3mo") -> dict[str, pd.DataFrame]:
    """複数銘柄を1回のAPIリクエストで一括取得（yfinance batch）"""
    norm_map = {t: normalize_ticker(t) for t in tickers}
    norm_list = list(set(norm_map.values()))
    result = {}
    try:
        raw = yf.download(
            norm_list, period=period, auto_adjust=True,
            progress=False, group_by="ticker", threads=True,
        )
        for t, nt in norm_map.items():
            try:
                df = raw[nt] if len(norm_list) > 1 else raw
                if df is None or df.empty:
                    continue
                df = df.copy()
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
                cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
                df = df[cols].dropna()
                if not df.empty:
                    result[t] = df
            except Exception:
                pass
    except Exception:
        pass
    return result


def _process_ticker_from_df(ticker: str, df: pd.DataFrame) -> dict:
    """取得済みDataFrameからシグナルを計算（ネットワーク不要）"""
    try:
        df = compute_all(df)
        signals = evaluate_signals(df)
        verdict, score = overall_signal(signals, df=df)
        close = float(df["Close"].iloc[-1])
        prev_close = float(df["Close"].iloc[-2]) if len(df) >= 2 else close
        change_pct = (close - prev_close) / prev_close * 100
        rsi = df["RSI"].dropna().iloc[-1] if "RSI" in df.columns else None
        macd_hist = df["MACD_hist"].dropna().iloc[-1] if "MACD_hist" in df.columns else None
        reasons = [s["判定"] for s in sorted(signals, key=lambda x: abs(x["スコア"]), reverse=True)[:2]
                   if abs(s["スコア"]) >= 1]
        return {
            "ticker": ticker, "現在値": round(close, 2),
            "前日比(%)": round(change_pct, 2), "シグナル": verdict, "スコア": score,
            "RSI": round(float(rsi), 1) if rsi is not None else None,
            "MACD方向": "↑" if macd_hist and macd_hist > 0 else "↓",
            "理由": " / ".join(reasons) if reasons else "-", "エラー": None,
        }
    except Exception as e:
        return {"ticker": ticker, "現在値": None, "前日比(%)": None, "シグナル": "エラー",
                "スコア": 0, "RSI": None, "MACD方向": "-", "理由": str(e)[:40], "エラー": str(e)}


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


def scan_all(tickers: list[str], max_workers: int = 20) -> list[dict]:
    """
    高速スキャン:
    1. yfinance batch APIで全銘柄を1リクエストで一括取得
    2. 取得できた銘柄は並列でシグナル計算（ネットワーク不要）
    3. 取得失敗銘柄は個別フォールバック
    """
    # キャッシュから取得済みの銘柄を除く
    cache = _load_cache()
    now = time.time()
    cached = {}
    uncached = []
    for t in tickers:
        entry = cache.get(t)
        if entry and now - entry.get("_cached_at", 0) < _CACHE_TTL_SECONDS:
            cached[t] = {k: v for k, v in entry.items() if k != "_cached_at"}
        else:
            uncached.append(t)

    if not uncached:
        return [cached[t] for t in tickers if t in cached]

    # Step1: バッチ一括取得（1リクエスト）
    batch = _batch_fetch_ohlcv(uncached)

    # Step2: 取得成功 → 並列でシグナル計算（ネットワーク不要、高速）
    # 取得失敗 → 個別フォールバック
    results = dict(cached)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for t in uncached:
            if t in batch:
                futures[executor.submit(_process_ticker_from_df, t, batch[t])] = t
            else:
                futures[executor.submit(scan_ticker, t, False)] = t  # キャッシュ未使用で個別取得

        for future in as_completed(futures):
            t = futures[future]
            try:
                r = future.result()
                results[t] = r
                # キャッシュ更新
                cache[t] = {**r, "_cached_at": now}
            except Exception as e:
                results[t] = {"ticker": t, "現在値": None, "前日比(%)": None,
                               "シグナル": "エラー", "スコア": 0, "RSI": None,
                               "MACD方向": "-", "理由": str(e)[:40], "エラー": str(e)}

    _save_cache(cache)
    return [results[t] for t in tickers if t in results]
