"""
予測の事前登録ノート
====================
「予測を、結果が出る前にタイムスタンプ付きで固定し、後から答え合わせする」
仕組みの汎用版。投資のフォワードテスト（--signal）で使った規律を、
あらゆる予測（相場・仕事・人生の判断）に一般化する。

誠実性の仕組み:
- 追記専用ログ。各記録は「前の記録のハッシュ」を含む（ハッシュチェーン）。
  過去の記録を1文字でも書き換えると、それ以降の全ハッシュが不整合になり
  改ざんが検出できる。
- 予測の的中率だけでなく「確信度の較正」を測る:
  確信度70%と言った予測群は、実際に約70%当たっているか？
  （当たりすぎ＝過小評価、外れすぎ＝過信。Brierスコアで総合評価）
"""

import hashlib
import json
from datetime import datetime

from modules import userstore


def _file():
    return userstore.user_path("forecasts.json")


def _load() -> list[dict]:
    p = _file()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return []


def _save(entries: list[dict]):
    _file().write_text(json.dumps(entries, ensure_ascii=False, indent=1))


def _entry_hash(entry: dict, prev_hash: str) -> str:
    payload = json.dumps(
        {k: entry[k] for k in ("id", "登録日時", "予測", "期限", "確信度")},
        ensure_ascii=False, sort_keys=True,
    ) + prev_hash
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def add_forecast(statement: str, due_date: str, confidence_pct: int,
                 category: str = "") -> dict:
    """予測を登録する。登録後の本文・確信度は変更不可（チェーンが壊れる）。"""
    entries = _load()
    prev_hash = entries[-1]["hash"] if entries else "GENESIS"
    entry = {
        "id": len(entries) + 1,
        "登録日時": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "予測": statement.strip(),
        "期限": due_date,
        "確信度": int(confidence_pct),
        "カテゴリ": category,
        "結果": None,          # None=未判定 / True=的中 / False=外れ
        "判定日時": None,
        "判定メモ": "",
    }
    entry["hash"] = _entry_hash(entry, prev_hash)
    entries.append(entry)
    _save(entries)
    return entry


def resolve_forecast(forecast_id: int, hit: bool, memo: str = "") -> bool:
    """期限が来た予測に結果を記録する。結果は一度だけ記録できる。"""
    entries = _load()
    for e in entries:
        if e["id"] == forecast_id:
            if e["結果"] is not None:
                return False   # 判定済みの上書きは不可
            e["結果"] = bool(hit)
            e["判定日時"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            e["判定メモ"] = memo.strip()
            _save(entries)
            return True
    return False


def list_forecasts() -> list[dict]:
    return _load()


def verify_chain() -> tuple[bool, int]:
    """ハッシュチェーンの整合性を検証する。(正常か, 検証済み件数)"""
    entries = _load()
    prev = "GENESIS"
    for i, e in enumerate(entries):
        if _entry_hash(e, prev) != e.get("hash"):
            return False, i
        prev = e["hash"]
    return True, len(entries)


def calibration_stats() -> dict:
    """判定済みの予測から的中率・Brierスコア・較正表を計算する。"""
    resolved = [e for e in _load() if e["結果"] is not None]
    if not resolved:
        return {"n": 0}

    n = len(resolved)
    hits = sum(1 for e in resolved if e["結果"])
    # Brierスコア: (確信度 - 結果)^2 の平均。0が完璧、0.25が「常に50%」の水準
    brier = sum((e["確信度"] / 100 - (1 if e["結果"] else 0)) ** 2
                for e in resolved) / n

    # 確信度帯ごとの較正（申告した確率と実際の的中率のズレ）
    bins = {}
    for e in resolved:
        band = f"{(e['確信度'] // 20) * 20}-{(e['確信度'] // 20) * 20 + 19}%"
        if e["確信度"] >= 100:
            band = "80-99%"
        bins.setdefault(band, []).append(e)
    calib = []
    for band in sorted(bins):
        es = bins[band]
        calib.append({
            "確信度帯": band,
            "件数": len(es),
            "申告平均": round(sum(e["確信度"] for e in es) / len(es), 1),
            "実際の的中率": round(100 * sum(1 for e in es if e["結果"]) / len(es), 1),
        })

    return {
        "n": n,
        "hit_rate": round(100 * hits / n, 1),
        "brier": round(brier, 4),
        "calibration": calib,
    }
