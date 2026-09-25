"""
GASの日付ごとのシートとSupabaseのscoutsテーブルを、日付ごと(YYYY-MM-DD)に
件数を突き合わせて一致しているか確認する。

実行:
  python3 check_daily_match.py
"""
import json
import os
import sys
import datetime
import urllib.request

GAS_URL = os.environ.get('GAS_URL', '')
GAS_SECRET = os.environ.get('GAS_SECRET', 'snowwe2024')
SUPABASE_URL = 'https://ovwnyivqnqqiagutjxoo.supabase.co'
SUPABASE_KEY = 'sb_publishable_tEQ4TOve0uCydsGiEm1cDA_D1LQ49wN'

if not GAS_URL:
    print('環境変数 GAS_URL を設定してください。')
    sys.exit(1)


def post_json(url, payload, timeout=340):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode('utf-8')
        return json.loads(raw) if raw.strip() else {}


def get_json(url, headers, timeout=60):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode('utf-8')
        return json.loads(raw) if raw.strip() else []


print('[1/3] GASから全履歴を取得中...', flush=True)
res = post_json(GAS_URL, {'action': 'getAllDailySheetHistory', 'secret': GAS_SECRET})
if not res.get('ok'):
    print('取得失敗:', res)
    sys.exit(1)
gas_records = res.get('records', [])
print(f'  {len(gas_records)}件取得', flush=True)

print('[2/3] Supabaseから全件取得中...', flush=True)
headers = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
page_size = 1000
offset = 0
supa_rows = []
while True:
    url = f'{SUPABASE_URL}/rest/v1/scouts?select=sent_at'
    h = dict(headers)
    h['Range'] = f'{offset}-{offset + page_size - 1}'
    page = get_json(url, h)
    supa_rows.extend(page)
    if len(page) < page_size:
        break
    offset += page_size
print(f'  {len(supa_rows)}件取得', flush=True)

print('[3/3] 日付ごとに突き合わせ中...', flush=True)
gas_by_day = {}
for r in gas_records:
    ts = r.get('date')
    if not ts:
        continue
    day = datetime.datetime.fromtimestamp(ts / 1000, tz=datetime.timezone.utc).strftime('%Y-%m-%d')
    gas_by_day[day] = gas_by_day.get(day, 0) + 1

supa_by_day = {}
for r in supa_rows:
    sa = r.get('sent_at')
    if not sa:
        continue
    day = str(sa)[:10]
    supa_by_day[day] = supa_by_day.get(day, 0) + 1

all_days = sorted(set(gas_by_day) | set(supa_by_day))
print(f'\n{"日付":12s} {"GAS":>6s} {"Supabase":>9s} {"差":>6s}')
mismatch_count = 0
for day in all_days:
    g = gas_by_day.get(day, 0)
    s = supa_by_day.get(day, 0)
    diff = s - g
    flag = '' if diff == 0 else '  ⚠️'
    if diff != 0:
        mismatch_count += 1
    print(f'{day:12s} {g:6d} {s:9d} {diff:+6d}{flag}')

print(f'\n合計: GAS {sum(gas_by_day.values())}件 / Supabase {sum(supa_by_day.values())}件')
print(f'一致しない日数: {mismatch_count} / {len(all_days)}日')
