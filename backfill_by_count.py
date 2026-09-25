"""
件数差ベースのbackfill（重複を原理的に作らない方式）。

これまでのシグネチャ照合方式(backfill_recent_only.py)は、
  ・会社名の誤抽出（実データで company_name="29歳" 等を確認）
  ・担当者名が空欄のまま保存された行（133件確認、うち31件は補完不能）
のせいで「実在するのに未登録」と誤判定し、753件という過大な数字を出していた
（GASとSupabaseの単純な件数差は457件）。

この方式では、
  1. (日 × 媒体) ごとに GAS件数 と Supabase件数 を数える
  2. 不足数 N = GAS件数 - Supabase件数（0以下なら何もしない）
  3. その枠のGAS記録のうち、シグネチャがSupabaseに無いものを候補として
     先頭からN件だけ追加する
とするため、追加後の件数は必ずGAS件数以下になり、重複が構造的に発生しない。
担当者名を比較キーに使わないので、担当者名が空欄の行も正しく1件として数えられる。

グリーンは拡張機能側に実装が無く自動記録の対象外のため、集計から除外する。

実行:
  python3 backfill_by_count.py            # 確認のみ
  python3 backfill_by_count.py --commit   # 実際に書き込む
"""
import json
import os
import re
import sys
import datetime
import urllib.request
import urllib.error
from collections import Counter, defaultdict

SUPABASE_URL = 'https://ovwnyivqnqqiagutjxoo.supabase.co'
SUPABASE_KEY = 'sb_publishable_tEQ4TOve0uCydsGiEm1cDA_D1LQ49wN'

GAS_URL = os.environ.get('GAS_URL')
GAS_SECRET = os.environ.get('GAS_SECRET', 'snowwe2024')

CUTOFF_WORKDATE = '2026-08-16'

MEDIA_LABEL_TO_KEY = {
    'RDS': 'rds', 'ビズリーチ': 'bizreach', 'dodaX': 'dodax', 'doda X': 'dodax',
    'アンビ': 'ambi', 'AMBI': 'ambi', 'Green': 'green', 'グリーン': 'green', 'マイナビ': 'mynavi',
}

# 拡張機能側にgreen専用の実装が一切無く（content.js内で'green'はプラットフォーム判定の
# 1箇所にしか登場しない）、そもそも自動記録の対象外のため、突き合わせから除外する
EXCLUDE_PLATFORMS = {'green'}

if not GAS_URL:
    print('環境変数 GAS_URL が設定されていません。')
    sys.exit(1)

COMMIT = '--commit' in sys.argv
H = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}


def post_json(url, payload, headers=None, timeout=340):
    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='POST', headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode('utf-8')
        return json.loads(raw) if raw.strip() else {}


def get_json(url, headers=None, timeout=60):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def day_of_ms(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc).strftime('%Y-%m-%d')


def normalize_company(name):
    if not name:
        return ''
    s = str(name).lower()
    s = re.sub(r'株式会社|（株）|\(株\)|合同会社|有限会社|グループ', '', s)
    s = re.sub(r'[・\s　,、.。]', '', s)
    return s.strip()


# 媒体を含めないと、同じ担当者が同じ会社に同じ日で別媒体にも送っている場合に
# 誤って一致してしまい、その枠の追加候補が不足数に足りなくなる（実データの
# 8/19 ambi で、Supabase側が0件なのに候補が11件しか作れない事象を確認）。
# 追加件数の上限は(日×媒体)の不足数で別途抑えているため、ここを厳密にしても
# 重複が増えることはない
def signature(recruiter, company, day_key, platform_key):
    return f"{(recruiter or '').strip()}|{normalize_company(company)}|{day_key}|{platform_key}"


def parse_age(age_str):
    if not age_str:
        return None
    digits = re.sub(r'[^\d]', '', str(age_str))
    return int(digits) if digits else None


print(f'[1/4] GASから{CUTOFF_WORKDATE}以降の記録を取得中...', flush=True)
gas_data = post_json(GAS_URL, {'secret': GAS_SECRET, 'action': 'getAllDailySheetHistory'}, timeout=340)
all_records = [r for r in gas_data.get('records', []) if (r.get('workDate') or '') >= CUTOFF_WORKDATE]

records = []
for r in all_records:
    if not r.get('date'):
        continue
    pkey = MEDIA_LABEL_TO_KEY.get(r.get('platform', ''), r.get('platform', ''))
    if pkey in EXCLUDE_PLATFORMS:
        continue
    r['_pkey'] = pkey
    r['_day'] = day_of_ms(r['date'])
    records.append(r)
print(f'  → {len(all_records)}件 中、対象(グリーン除く) {len(records)}件', flush=True)

print('[2/4] Supabaseの既存記録(同期間)を取得中...', flush=True)
supa_rows = []
offset = 0
PAGE = 1000
while True:
    url = (f'{SUPABASE_URL}/rest/v1/scouts'
           f'?select=recruiter_name,company_name,platform,sent_at'
           f'&sent_at=gte.{CUTOFF_WORKDATE}T00:00:00&order=sent_at.asc&limit={PAGE}&offset={offset}')
    page = get_json(url, headers=H)
    if not page:
        break
    supa_rows.extend(page)
    offset += PAGE
    if len(page) < PAGE:
        break
print(f'  → Supabase行数: {len(supa_rows)} 件', flush=True)

existing_sigs = set()
supa_count = Counter()   # (日, 媒体) -> 件数
for row in supa_rows:
    pkey = row.get('platform') or ''
    if pkey in EXCLUDE_PLATFORMS:
        continue
    day = str(row.get('sent_at'))[:10]
    supa_count[(day, pkey)] += 1
    existing_sigs.add(signature(row.get('recruiter_name'), row.get('company_name'), day, pkey))

print('[3/4] (日×媒体)ごとの不足数を計算中...', flush=True)
gas_by_bucket = defaultdict(list)
for r in records:
    gas_by_bucket[(r['_day'], r['_pkey'])].append(r)

to_add = []
print(f'\n{"日付":12s} {"媒体":10s} {"GAS":>5s} {"Supa":>5s} {"不足":>5s} {"追加":>5s}')
for key in sorted(gas_by_bucket):
    day, pkey = key
    bucket = gas_by_bucket[key]
    gas_c = len(bucket)
    supa_c = supa_count.get(key, 0)
    shortfall = max(0, gas_c - supa_c)

    # この枠のGAS記録のうち、Supabaseにシグネチャが見当たらないものを候補にする
    cands = [r for r in bucket
             if signature(r.get('recruiter'), r.get('company'), day, pkey) not in existing_sigs]
    picked = cands[:shortfall]
    to_add.extend(picked)

    flag = '' if shortfall == 0 else ('  ⚠️' if len(picked) < shortfall else '')
    print(f'{day:12s} {pkey:10s} {gas_c:5d} {supa_c:5d} {shortfall:5d} {len(picked):5d}{flag}')

print(f'\n追加対象: {len(to_add)} 件')
print('担当者別内訳:', dict(Counter((r.get('recruiter') or '(空欄)') for r in to_add)))
print('媒体別内訳:', dict(Counter(r['_pkey'] for r in to_add)))

gas_total = len(records)
supa_total = sum(supa_count.values())
print(f'\n参考: 対象期間のGAS {gas_total}件 / Supabase {supa_total}件 / 単純な件数差 {gas_total - supa_total}件')

rows = []
for r in to_add:
    rows.append({
        'platform': r['_pkey'],
        'platform_candidate_id': f"backfill0816_{r.get('date')}_{len(rows)}",
        'candidate_name': '',
        'candidate_age': parse_age(r.get('age')),
        'candidate_industry': '',
        'company_name': r.get('company', ''),
        'university': r.get('univ', ''),
        'position_name': r.get('position', ''),
        'recruiter_name': r.get('recruiter', ''),
        'sent_at': datetime.datetime.fromtimestamp(r['date'] / 1000, tz=datetime.timezone.utc).isoformat(),
        'scout_message': '',
        'work_date': r.get('workDate') or None,
        'time_estimated': bool(r.get('timeEstimated')),
    })

if not COMMIT:
    print('\n--commit を付けずに実行したため、まだ書き込んでいません。')
    print('件数を確認してから python3 backfill_by_count.py --commit を実行してください。')
    sys.exit(0)

if not rows:
    print('追加対象がありません。')
    sys.exit(0)

print('\n[4/4] Supabaseへ書き込み中...', flush=True)
BATCH = 200
write_headers = dict(H)
write_headers['Content-Type'] = 'application/json'
write_headers['Prefer'] = 'return=minimal'

failed_rows = []
for i in range(0, len(rows), BATCH):
    chunk = rows[i:i + BATCH]
    try:
        post_json(f'{SUPABASE_URL}/rest/v1/scouts', chunk, headers=write_headers)
        print(f'  {i + len(chunk)}/{len(rows)} 件 書き込み完了', flush=True)
    except urllib.error.HTTPError as e:
        print(f'  バッチ失敗({e.code})。1件ずつ再試行します...', flush=True)
        for row in chunk:
            try:
                post_json(f'{SUPABASE_URL}/rest/v1/scouts', [row], headers=write_headers)
            except urllib.error.HTTPError as e2:
                failed_rows.append((row, e2.code, e2.read().decode('utf-8')))
        print(f'  {i + len(chunk)}/{len(rows)} 件 処理完了（個別リトライ済み）')

if failed_rows:
    print(f'\n書き込みに失敗した行: {len(failed_rows)}件')
    for row, code, msg in failed_rows[:10]:
        print(f"  {row.get('platform_candidate_id')} / {row.get('company_name')}: {code} {msg[:150]}")

print('完了。')
