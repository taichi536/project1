"""
backfill_recent_only.py が「未登録」と判定した753件が、本当に未登録なのか
(会社名の表記ゆれ等でシグネチャが一致しないだけで実はSupabaseに存在するのか)を
切り分けるための診断スクリプト。書き込みは一切行わない。

考え方:
  「未登録」判定された各GAS記録について、
  1) 同じ担当者・同じ日にSupabase側の記録が何件あるか（会社名を無視）
  2) その中に、正規化した会社名を緩く比較(部分一致)して近い候補があるか
  を調べる。もし「同じ担当者・同じ日のSupabase記録数」が「同じ担当者・同じ日の
  GAS記録数」と近ければ、会社名の表記ゆれで一致しなかっただけの可能性が高い
  （＝backfillすると重複登録のリスクがある）。

実行:
  python3 diagnose_missing.py
"""
import json
import os
import re
import sys
import datetime
import urllib.request
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

if not GAS_URL:
    print('環境変数 GAS_URL が設定されていません。')
    sys.exit(1)


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


def day_bucket_ms(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc).strftime('%Y-%m-%d')


def normalize_company(name):
    if not name:
        return ''
    s = str(name).lower()
    s = re.sub(r'株式会社|（株）|\(株\)|合同会社|有限会社|グループ', '', s)
    s = re.sub(r'[・\s　,、.。]', '', s)
    return s.strip()


def signature(recruiter, company, day_key):
    return f"{(recruiter or '').strip()}|{normalize_company(company)}|{day_key}"


print(f'[1/3] GASから{CUTOFF_WORKDATE}以降の記録を取得中...', flush=True)
gas_data = post_json(GAS_URL, {'secret': GAS_SECRET, 'action': 'getAllDailySheetHistory'}, timeout=340)
records = [r for r in gas_data.get('records', []) if (r.get('workDate') or '') >= CUTOFF_WORKDATE]
print(f'  → {len(records)}件', flush=True)

print('[2/3] Supabaseの既存記録(同期間)を取得中...', flush=True)
cutoff_iso = f'{CUTOFF_WORKDATE}T00:00:00'
supa_rows = []
offset = 0
PAGE = 1000
while True:
    page = get_json(
        f'{SUPABASE_URL}/rest/v1/scouts?select=recruiter_name,company_name,sent_at'
        f'&sent_at=gte.{cutoff_iso}&order=sent_at.asc&limit={PAGE}&offset={offset}',
        headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'},
    )
    if not page:
        break
    supa_rows.extend(page)
    offset += PAGE
    if len(page) < PAGE:
        break
print(f'  → Supabase生の行数(重複含む): {len(supa_rows)} 件', flush=True)

existing_sigs = set()
by_recruiter_day = defaultdict(list)  # (recruiter, day) -> [company_name, ...] 会社名無視で担当者+日だけの実件数
for row in supa_rows:
    try:
        dt = datetime.datetime.fromisoformat(row['sent_at'].replace('Z', '+00:00'))
    except (TypeError, ValueError):
        continue
    day = day_bucket_ms(dt.timestamp() * 1000)
    recruiter = (row.get('recruiter_name') or '').strip()
    company = row.get('company_name') or ''
    existing_sigs.add(signature(recruiter, company, day))
    by_recruiter_day[(recruiter, day)].append(company)

print(f'  → シグネチャ種類数(担当者+正規化会社名+日): {len(existing_sigs)} 件')
print(f'  → (担当者,日)の組み合わせ数: {len(by_recruiter_day)} 件')

print('[3/3] 未登録判定 & 内訳分析中...', flush=True)
gas_by_recruiter_day = defaultdict(int)
for r in records:
    if not r.get('company') or not r.get('date'):
        continue
    recruiter = (r.get('recruiter') or '').strip()
    day = day_bucket_ms(r['date'])
    gas_by_recruiter_day[(recruiter, day)] += 1

missing = []
for r in records:
    if not r.get('company') or not r.get('date'):
        continue
    recruiter = (r.get('recruiter') or '').strip()
    day = day_bucket_ms(r['date'])
    sig = signature(recruiter, r.get('company'), day)
    if sig not in existing_sigs:
        missing.append((r, recruiter, day))

print(f'  → 未登録件数: {len(missing)} 件\n')

# 分類:
#  A) 同じ(担当者,日)のSupabase実件数 >= 同じ(担当者,日)のGAS件数
#     → その日はSupabase側もほぼ揃っている可能性が高く、会社名の表記ゆれで
#       このGAS記録だけシグネチャが一致しなかった可能性が高い(=誤検知の疑い)
#  B) 同じ(担当者,日)のSupabase実件数 < GAS件数
#     → 本当にその分だけSupabase側が足りていない可能性が高い(=真の未登録の疑い)
#  C) 同じ(担当者,日)の組み合わせがSupabaseに1件も無い
#     → 完全に記録が抜けている日(=真の未登録の可能性が非常に高い)

cat_a = []
cat_b = []
cat_c = []
for r, recruiter, day in missing:
    key = (recruiter, day)
    supa_count = len(by_recruiter_day.get(key, []))
    gas_count = gas_by_recruiter_day.get(key, 0)
    if supa_count == 0:
        cat_c.append((r, recruiter, day, supa_count, gas_count))
    elif supa_count >= gas_count:
        cat_a.append((r, recruiter, day, supa_count, gas_count))
    else:
        cat_b.append((r, recruiter, day, supa_count, gas_count))

print(f'A) 表記ゆれ誤検知の疑い（同じ担当者・同日のSupabase件数 >= GAS件数）: {len(cat_a)} 件')
print(f'B) 部分的に不足の疑い（同じ担当者・同日のSupabase件数 < GAS件数）    : {len(cat_b)} 件')
print(f'C) その日は1件もSupabaseに無い（真の未登録の可能性が高い）          : {len(cat_c)} 件')
print(f'   合計: {len(cat_a) + len(cat_b) + len(cat_c)} 件（= 未登録件数と一致するはず）\n')

if cat_a:
    print('--- A) 表記ゆれ誤検知サンプル（GAS会社名 vs 同担当者同日のSupabase会社名一覧）---')
    for r, recruiter, day, supa_count, gas_count in cat_a[:15]:
        supa_companies = by_recruiter_day.get((recruiter, day), [])
        print(f'  [{day}] {recruiter} / GAS会社名="{r.get("company")}" (正規化="{normalize_company(r.get("company"))}")'
              f'  Supabase側同日会社名候補={ [c + "(正規化=" + normalize_company(c) + ")" for c in supa_companies] }')
    print('')

if cat_b:
    print('--- B) 部分不足サンプル ---')
    for r, recruiter, day, supa_count, gas_count in cat_b[:10]:
        print(f'  [{day}] {recruiter} / GAS会社名="{r.get("company")}" / '
              f'同日GAS件数={gas_count} 同日Supabase件数={supa_count}')
    print('')

if cat_c:
    print('--- C) 完全欠落サンプル ---')
    by_day_c = Counter(day for _, _, day, _, _ in cat_c)
    print('  日別件数:', dict(sorted(by_day_c.items())))
    print('  担当者別件数:', dict(Counter(recruiter for _, recruiter, _, _, _ in cat_c)))

print('\n判定の見方:')
print('  Aが多い場合 → backfill_recent_only.pyの会社名正規化ロジックを強化すべき'
      '（このままcommitすると重複登録が大量発生するリスクが高い）')
print('  Cが多い場合 → その担当者・その日は自動記録が本当に機能していなかった可能性が高く、'
      'backfillする価値が高い')
