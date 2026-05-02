import anthropic
import json
import hashlib
import time
from pathlib import Path

_client = None
_CACHE_PATH = Path(__file__).parent.parent / ".ai_cache.json"
_CACHE_TTL = 3600  # 1時間キャッシュ

# 1回あたりの概算コスト（ドル）
_COST_PER_CALL = {
    "chart":       0.02,   # チャートAI解説
    "five_forces": 0.04,   # ファイブフォース
    "sentiment":   0.03,   # ニュースセンチメント
    "backtest":    0.02,   # バックテスト評価
}


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


# ── キャッシュ管理 ──────────────────────────────────────────────────────────
def _load_cache() -> dict:
    if _CACHE_PATH.exists():
        try:
            return json.loads(_CACHE_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict):
    _CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2))


def _cache_key(kind: str, *args) -> str:
    raw = kind + "|" + "|".join(str(a) for a in args)
    return hashlib.md5(raw.encode()).hexdigest()


def _get_cached(key: str) -> str | None:
    cache = _load_cache()
    entry = cache.get(key)
    if entry and time.time() - entry["ts"] < _CACHE_TTL:
        return entry["text"]
    return None


def _set_cached(key: str, text: str):
    cache = _load_cache()
    cache[key] = {"ts": time.time(), "text": text}
    # キャッシュが大きくなりすぎないよう古いエントリを削除
    if len(cache) > 200:
        oldest = sorted(cache.items(), key=lambda x: x[1]["ts"])[:50]
        for k, _ in oldest:
            del cache[k]
    _save_cache(cache)


# ── コスト追跡 ──────────────────────────────────────────────────────────────
_COST_LOG_PATH = Path(__file__).parent.parent / ".ai_cost_log.json"


def _log_cost(kind: str, cached: bool):
    log = {}
    if _COST_LOG_PATH.exists():
        try:
            log = json.loads(_COST_LOG_PATH.read_text())
        except Exception:
            pass

    month = time.strftime("%Y-%m")
    if month not in log:
        log[month] = {"calls": 0, "cached_calls": 0, "estimated_usd": 0.0}

    log[month]["calls"] += 1
    if cached:
        log[month]["cached_calls"] += 1
    else:
        log[month]["estimated_usd"] += _COST_PER_CALL.get(kind, 0.02)

    _COST_LOG_PATH.write_text(json.dumps(log, indent=2))


def get_cost_summary() -> dict:
    if not _COST_LOG_PATH.exists():
        return {}
    try:
        return json.loads(_COST_LOG_PATH.read_text())
    except Exception:
        return {}


# ── AI分析関数 ──────────────────────────────────────────────────────────────
def analyze_five_forces(company_name: str, sector: str, industry: str) -> str:
    key = _cache_key("five_forces", company_name, sector, industry)
    cached = _get_cached(key)
    if cached:
        _log_cost("five_forces", cached=True)
        return cached + "\n\n*（キャッシュ済み・API未使用）*"

    prompt = f"""あなたは株式投資の専門家です。以下の企業についてポーターのファイブフォース分析を行ってください。

企業名: {company_name}
セクター: {sector}
業種: {industry}

以下の5つの力それぞれについて、【強い/中程度/弱い】の評価と100字程度の根拠を述べてください。
最後に投資家視点での総合評価（強み・リスク）を200字以内でまとめてください。

1. 買い手の交渉力
2. 売り手（供給者）の交渉力
3. 競合他社との競争
4. 新規参入の脅威
5. 代替品・代替サービスの脅威

日本語で回答してください。"""

    client = _get_client()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    result = message.content[0].text
    _set_cached(key, result)
    _log_cost("five_forces", cached=False)
    return result


def analyze_chart_ai(
    ticker: str,
    signals: list[dict],
    overall: str,
    score: int,
    current_price: float,
    rsi: float | None,
    atr: float | None,
) -> str:
    # 価格は±1%以内なら同じキャッシュを使う（細かい変動で再取得しない）
    price_bucket = round(current_price / (current_price * 0.01)) if current_price else 0
    key = _cache_key("chart", ticker, overall, score, price_bucket)
    cached = _get_cached(key)
    if cached:
        _log_cost("chart", cached=True)
        return cached + "\n\n*（キャッシュ済み・API未使用）*"

    signals_text = "\n".join(
        f"- {s['指標']}: {s['値']} → {s['判定']} (スコア: {s['スコア']:+d})" for s in signals
    )
    prompt = f"""あなたは経験豊富な株式テクニカルアナリストです。以下のデータを基に、投資家向けの分析コメントを生成してください。

銘柄: {ticker}
現在値: {current_price:.2f}
総合シグナル: {overall}（スコア: {score:+d}）
RSI: {f'{rsi:.1f}' if rsi else 'N/A'}
ATR: {f'{atr:.2f}' if atr else 'N/A'}

【各指標の状況】
{signals_text}

以下の構成で分析してください（合計300字以内）：
1. 現在の相場状況（1〜2文）
2. 注目すべきシグナル（1〜2文）
3. 短期的な売買タイミングの見解（1〜2文）
4. 注意すべきリスク（1文）

日本語で、投資家が実際に判断できる具体的な内容にしてください。"""

    client = _get_client()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    result = message.content[0].text
    _set_cached(key, result)
    _log_cost("chart", cached=False)
    return result
