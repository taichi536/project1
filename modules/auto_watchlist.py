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

    for ticker, (verdict, score) in scan_results.items():
        scores[ticker] = {"verdict": verdict, "score": score}

    # スコア上位max_size銘柄を新ウォッチリストとして選出（protected銘柄は必ず含む）
    ranked = sorted(scan_results.items(), key=lambda x: x[1][1], reverse=True)
    new_watchlist = list(protected & set(scan_results.keys()))
    for ticker, (verdict, score) in ranked:
        if len(new_watchlist) >= max_size:
            break
        if ticker not in new_watchlist:
            new_watchlist.append(ticker)

    # 変化を記録
    old_set = set(watchlist)
    new_set = set(new_watchlist)
    added = list(new_set - old_set)
    removed = list(old_set - new_set)
    watchlist = new_watchlist

    if verbose:
        for t in added:
            s = scan_results.get(t, (None, 0))[1]
            print(f"    ✅ {t} 追加（score={s:+d}）")
        for t in removed:
            s = scan_results.get(t, (None, 0))[1]
            print(f"    ❌ {t} 除外（score={s:+d}）")

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
