"""
8/20のbizreachだけ、Supabase側がGASより1件多い(50 vs 51)。
重複行なのか、GAS側に無い記録なのかを確認する。書き込みは一切しない。

実行:
  python3 check_bizreach_0820.py
"""
import json
import os
import re
import sys
import datetime
import urllib.request
from collections import Counter

SUPABASE_URL = 'https://ovwnyivqnqqiagutjxoo.supabase.co'
SUPABASE_KEY = 'sb_publishable_tEQ4TOve0uCydsGiEm1cDA_D1LQ49wN'

GAS_URL = os.environ.get('GAS_URL')
GAS_SECRET = os.environ.get('GAS_SECRET', 'snowwe2024')

if not GAS_URL:
    print('環境変数 GAS_URL が設定されていません。')
    sys.exit(1)

H = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
TARGET_DAY = '2026-08-20'
TARGET_PLATFORM = 'bizreach'


def post_json(url, payload, timeout=340):
    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='POST', headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode('utf-8')
        return json.loads(raw) if raw.strip() else {}


def get_json(url, headers, timeout=60):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def normalize_company(name):
    if not name:
        return ''
    s = str(name).lower()
    s = re.sub(r'株式会社|（株）|\(株\)|合同会社|有限会社|グループ', '', s)
    s = re.sub(r'[・\s　,、.。]', '', s)
    return s.strip()


print('Supabase側を取得中...', flush=True)
url = (f'{SUPABASE_URL}/rest/v1/scouts'
       f'?select=id,recruiter_name,company_name,platform,sent_at,platform_candidate_id,candidate_name'
       f'&platform=eq.{TARGET_PLATFORM}'
       f'&sent_at=gte.{TARGET_DAY}T00:00:00&sent_at=lt.{TARGET_DAY}T23:59:59'
       f'&order=sent_at.asc&limit=500')
rows = get_json(url, H)
print(f'  → {len(rows)} 件\n')

print('GAS側を取得中...', flush=True)
gas = post_json(GAS_URL, {'secret': GAS_SECRET, 'action': 'getAllDailySheetHistory'})
gas_rows = []
for r in gas.get('records', []):
    if not r.get('date'):
        continue
    day = datetime.datetime.fromtimestamp(r['date'] / 1000, tz=datetime.timezone.utc).strftime('%Y-%m-%d')
    if day == TARGET_DAY and r.get('platform') == 'ビズリーチ':
        gas_rows.append(r)
print(f'  → {len(gas_rows)} 件\n')

print('--- platform_candidate_id が重複している行 ---')
dup = [k for k, v in Counter(r.get('platform_candidate_id') for r in rows).items() if v > 1]
if dup:
    for d in dup:
        same = [r for r in rows if r.get('platform_candidate_id') == d]
        print(f'  id={d} が {len(same)} 件:')
        for s in same:
            print(f'    row_id={s["id"]} 会社名="{s.get("company_name")}" '
                  f'担当者="{s.get("recruiter_name")}" sent_at={s.get("sent_at")}')
else:
    print('  なし')

print('\n--- 会社名+担当者 が重複している行 ---')
key = lambda r: f'{(r.get("recruiter_name") or "").strip()}|{normalize_company(r.get("company_name"))}'
dup2 = [k for k, v in Counter(key(r) for r in rows).items() if v > 1]
if dup2:
    for d in dup2:
        same = [r for r in rows if key(r) == d]
        print(f'  "{d}" が {len(same)} 件:')
        for s in same:
            print(f'    row_id={s["id"]} pid={s.get("platform_candidate_id")} sent_at={s.get("sent_at")}')
else:
    print('  なし')

print('\n--- GAS側に見当たらないSupabase行 ---')
gas_keys = Counter(f'{(r.get("recruiter") or "").strip()}|{normalize_company(r.get("company"))}' for r in gas_rows)
supa_keys = Counter(key(r) for r in rows)
for k in sorted(supa_keys):
    diff = supa_keys[k] - gas_keys.get(k, 0)
    if diff > 0:
        print(f'  "{k}" Supabase {supa_keys[k]}件 / GAS {gas_keys.get(k, 0)}件 (+{diff})')
        for s in [r for r in rows if key(r) == k]:
            print(f'    row_id={s["id"]} pid={s.get("platform_candidate_id")} '
                  f'候補者名="{s.get("candidate_name")}" sent_at={s.get("sent_at")}')
