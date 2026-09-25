"""
diagnose_missing.py の追加版。753件の未登録を(担当者×日)ごとに集計し、
GAS件数・Supabase件数・未登録件数・未登録率を一覧表示する。書き込みは一切しない。

実行:
  python3 diagnose_summary.py
"""
import json
import os
import re
import sys
import datetime
import urllib.request
from collections import defaultdict

SUPABASE_URL = 'https://ovwnyivqnqqiagutjxoo.supabase.co'
SUPABASE_KEY = 'sb_publishable_tEQ4TOve0uCydsGiEm1cDA_D1LQ49wN'

GAS_URL = os.environ.get('GAS_URL')
GAS_SECRET = os.environ.get('GAS_SECRET', 'snowwe2024')

CUTOFF_WORKDATE = '2026-08-16'

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

existing_sigs = set()
supa_count_by_key = defaultdict(int)
for row in supa_rows:
    try:
        dt = datetime.datetime.fromisoformat(row['sent_at'].replace('Z', '+00:00'))
    except (TypeError, ValueError):
        continue
    day = day_bucket_ms(dt.timestamp() * 1000)
    recruiter = (row.get('recruiter_name') or '').strip()
    company = row.get('company_name') or ''
    existing_sigs.add(signature(recruiter, company, day))
    supa_count_by_key[(recruiter, day)] += 1

print('[3/3] (担当者×日)ごとに集計中...', flush=True)
gas_count_by_key = defaultdict(int)
missing_count_by_key = defaultdict(int)
platform_by_key = defaultdict(set)

for r in records:
    if not r.get('company') or not r.get('date'):
        continue
    recruiter = (r.get('recruiter') or '').strip()
    day = day_bucket_ms(r['date'])
    key = (recruiter, day)
    gas_count_by_key[key] += 1
    platform_by_key[key].add(r.get('platform', ''))
    sig = signature(recruiter, r.get('company'), day)
    if sig not in existing_sigs:
        missing_count_by_key[key] += 1

print(f'\n{"日付":12s} {"担当者":10s} {"GAS":>5s} {"Supabase":>9s} {"未登録":>6s} {"未登録率":>8s}  媒体')
rows = []
for key in gas_count_by_key:
    recruiter, day = key
    gas_c = gas_count_by_key[key]
    supa_c = supa_count_by_key.get(key, 0)
    miss_c = missing_count_by_key.get(key, 0)
    rate = (miss_c / gas_c * 100) if gas_c else 0
    rows.append((day, recruiter, gas_c, supa_c, miss_c, rate, ','.join(sorted(platform_by_key[key]))))

rows.sort(key=lambda x: (x[0], -x[4]))
total_gas = total_supa = total_miss = 0
for day, recruiter, gas_c, supa_c, miss_c, rate, platforms in rows:
    flag = '  ⚠️' if miss_c else ''
    print(f'{day:12s} {recruiter:10s} {gas_c:5d} {supa_c:9d} {miss_c:6d} {rate:7.1f}%{flag}  {platforms}')
    total_gas += gas_c
    total_supa += supa_c
    total_miss += miss_c

print(f'\n合計: GAS {total_gas}件 / Supabase(担当者×日照合) {total_supa}件 / 未登録 {total_miss}件')
