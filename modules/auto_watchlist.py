"""
自動ウォッチリスト管理モジュール

ユニバースからテクニカルシグナルが強い銘柄を自動で追加し、
シグナルが弱くなった銘柄を自動で除外する。
"""

import json
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from modules.universe import UNIVERSE
from modules.dashboard import load_watchlist, save_watchlist
from modules.data_fetcher import fetch_ohlcv
from modules.technical import compute_all
from modules.signals import evaluate_signals, overall_signal

_SETTINGS_FILE = Path(__file__).parent.parent / ".auto_watchlist_settings.json"
_STATE_FILE = Path(__file__).parent.parent / ".auto_watchlist_state.json"
_RESULT_FILE = Path(__file__).parent.parent / ".auto_watchlist_last_result.json"

DEFAULT_SETTINGS = {
    "enabled": False,
    "categories": ["🇯🇵 日本株メジャー", "🇺🇸 米国大型株（S&P500）"],
    "add_score_threshold": 3,       # このスコア以上で追加
    "remove_score_threshold": -2,   # このスコア以下が続いたら削除
    "remove_consecutive_days": 3,   # N回連続で弱シグナルなら削除
    "max_watchlist_size": 20,       # ウォッチリストの最大銘柄数
    "protected_tickers": [],        # 自動削除しない銘柄（手動登録）
}


def load_settings() -> dict:
    if _SETTINGS_FILE.exists():
        try:
            saved = json.loads(_SETTINGS_FILE.read_text())
            return {**DEFAULT_SETTINGS, **saved}
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()


def save_settings(updates: dict):
    settings = load_settings()
    settings.update(updates)
    _SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2))


def _load_state() -> dict:
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_state(state: dict):
    _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def get_universe_tickers(categories: list[str]) -> list[str]:
    """指定カテゴリの銘柄を重複なしで返す"""
    tickers = []
    seen = set()
    for cat in categories:
        for t in UNIVERSE.get(cat, {}).get("tickers", []):
            if t not in seen:
                tickers.append(t)
                seen.add(t)
    return tickers


def run_auto_watchlist(verbose: bool = True) -> dict:
    """
    ユニバースをスキャンしてウォッチリストを自動更新する。
    Returns: {"added": [...], "removed": [...], "skipped": int, "scores": {ticker: score}}
    """
    settings = load_settings()
    if not settings["enabled"]:
        if verbose:
            print("[自動ウォッチリスト] 無効（設定でONにしてください）")
        return {"added": [], "removed": [], "skipped": 0, "scores": {}}

    watchlist = load_watchlist()
    state = _load_state()
    weak_counts = state.get("weak_counts", {})  # ticker → 連続弱シグナル数
    today = datetime.now().strftime("%Y-%m-%d")

    universe_tickers = get_universe_tickers(settings["categories"])
    add_threshold = settings["add_score_threshold"]
    remove_threshold = settings["remove_score_threshold"]
    remove_consecutive = settings["remove_consecutive_days"]
    max_size = settings["max_watchlist_size"]
    protected = set(settings.get("protected_tickers", []))

    added = []
    removed = []
    skipped = 0
    scores = {}  # ticker → score の記録

    if verbose:
        print(f"[自動ウォッチリスト] {len(universe_tickers)}銘柄を並列スキャン中...")

    def _scan_one(ticker):
        df = fetch_ohlcv(ticker, period="3mo")
        df = compute_all(df)
        sigs = evaluate_signals(df)
        verdict, score = overall_signal(sigs, df=df)
        return ticker, verdict, score

    scan_results = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_scan_one, t): t for t in universe_tickers}
        for future in as_completed(futures):
            t = futures[future]
            try:
                ticker, verdict, score = future.result()
                scan_results[ticker] = (verdict, score)
                if verbose:
                    print(f"  {ticker}: {verdict} score={score:+d}")
            except Exception as e:
                if verbose:
                    print(f"  {t}: エラー - {e}")

    for ticker in universe_tickers:
        if ticker not in scan_results:
            continue
        verdict, score = scan_results[ticker]
        scores[ticker] = {"verdict": verdict, "score": score}

        # 強シグナル → ウォッチリストに追加
        if score >= add_threshold and ticker not in watchlist:
            if len(watchlist) < max_size:
                watchlist.append(ticker)
                added.append(ticker)
                weak_counts.pop(ticker, None)
                if verbose:
                    print(f"    ✅ {ticker} ウォッチリストに追加（score={score:+d}）")
            else:
                skipped += 1

        # シグナルが強い → 弱カウントをリセット
        elif score > remove_threshold:
            weak_counts.pop(ticker, None)

        # 弱シグナルが続く → カウントアップして削除判定
        elif score <= remove_threshold and ticker in watchlist and ticker not in protected:
            weak_counts[ticker] = weak_counts.get(ticker, 0) + 1
            if weak_counts[ticker] >= remove_consecutive:
                watchlist.remove(ticker)
                removed.append(ticker)
                weak_counts.pop(ticker, None)
                if verbose:
                    print(f"    ❌ {ticker} ウォッチリストから削除（{remove_consecutive}回連続弱シグナル）")
            else:
                if verbose:
                    print(f"    ⚠️ {ticker} 弱シグナル {weak_counts[ticker]}/{remove_consecutive}回")

    save_watchlist(watchlist)
    _save_state({"weak_counts": weak_counts, "last_run": today})

    result = {
        "added": added,
        "removed": removed,
        "skipped": skipped,
        "scores": scores,
        "scanned": len(scores),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "watchlist": watchlist,
    }
    _RESULT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    if verbose:
        print(f"\n[自動ウォッチリスト] 完了: +{len(added)}件追加 / -{len(removed)}件削除")
        print(f"  現在のウォッチリスト（{len(watchlist)}銘柄）: {watchlist}")

    return result


def load_last_result() -> dict | None:
    """前回のスキャン結果をファイルから読み込む"""
    if _RESULT_FILE.exists():
        try:
            return json.loads(_RESULT_FILE.read_text())
        except Exception:
            pass
    return None
