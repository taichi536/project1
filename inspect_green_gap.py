"""
たけと/Green の 9/18 について、シートとSupabaseを時刻順に並べて突き合わせる。
連続漏れの原因を「接続切れ」「候補者IDの重複」「そもそも送信されていない」の
どれなのか切り分ける。読み取り専用。
"""
import json
import os
import sys
import datetime
import urllib.request
from collections import Counter

SUPABASE_URL = 'https://ovwnyivqnqqiagutjxoo.supabase.co'
SUPABASE_KEY = 'sb_publishable_tEQ4TOve0uCydsGiEm1cDA_D1LQ49wN'
GAS_URL = os.environ.get('GAS_URL')
GAS_SECRET = os.environ.get('GAS_SECRET', 'snowwe2024')
H = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
JST = datetime.timezone(datetime.timedelta(hours=9))

MEDIA = {'RDS': 'rds', 'ビズリーチ': 'bizreach', 'dodaX': 'dodax', 'doda X': 'dodax',
         'アンビ': 'ambi', 'AMBI': 'ambi', 'Green': 'green', 'グリーン': 'green', 'マイナビ': 'mynavi'}

args = [a for a in sys.argv[1:] if not a.startswith('-')]
WHO = args[0] if len(args) > 0 else 'たけと'
MEDIA_KEY = args[1] if len(args) > 1 else 'green'
DAY = args[2] if len(args) > 2 else '2026-09-18'

if not GAS_URL:
    print('環境変数 GAS_URL が設定されていません。')
    sys.exit(1)


def post_json(url, payload, timeout=340):
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), method='POST', headers={})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode('utf-8')
        return json.loads(raw) if raw.strip() else {}


def get_json(url, timeout=90):
    with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


print(f'[1/2] GASから{DAY}以降を取得中...', flush=True)
gas = post_json(GAS_URL, {'secret': GAS_SECRET, 'action': 'getAllDailySheetHistory', 'since': DAY})
sheet = []
for r in gas.get('records', []):
    if not r.get('date'):
        continue
    if (r.get('recruiter') or '') != WHO:
        continue
    if MEDIA.get(r.get('platform', ''), r.get('platform', '')) != MEDIA_KEY:
        continue
    t = datetime.datetime.fromtimestamp(r['date'] / 1000, tz=datetime.timezone.utc).astimezone(JST)
    if t.strftime('%Y-%m-%d') != DAY:
        continue
    sheet.append({'t': t, 'company': r.get('company') or '', 'univ': r.get('univ') or ''})
sheet.sort(key=lambda x: x['t'])
print(f'  シート: {len(sheet)}件', flush=True)

print('[2/2] Supabaseから取得中...', flush=True)
nxt = (datetime.date.fromisoformat(DAY) + datetime.timedelta(days=1)).isoformat()
cols = 'platform_candidate_id,recruiter_name,company_name,university,sent_at,ext_version,position_name'
rows = get_json(f'{SUPABASE_URL}/rest/v1/scouts?select={cols}&platform=eq.{MEDIA_KEY}'
                f'&sent_at=gte.{DAY}T00:00:00&sent_at=lt.{nxt}T15:00:00&order=sent_at.asc&limit=1000')
supa = []
for s in rows:
    if (s.get('recruiter_name') or '') != WHO:
        continue
    t = datetime.datetime.fromisoformat(str(s['sent_at']).replace('Z', '+00:00')).astimezone(JST)
    supa.append({'t': t, 'id': s.get('platform_candidate_id') or '', 'company': s.get('company_name') or '',
                 'univ': s.get('university') or '', 'ver': s.get('ext_version') or '-'})
supa.sort(key=lambda x: x['t'])
print(f'  Supabase: {len(supa)}件\n', flush=True)

print('=== 時刻順に並べた突き合わせ ===')
print(f'{"時刻":8s} {"側":6s} {"会社名":22s} {"候補者ID":24s} {"ver"}')
merged = [{'t': x['t'], 'side': 'シート', 'company': x['company'], 'id': '', 'ver': ''} for x in sheet]
merged += [{'t': x['t'], 'side': 'Supa', 'company': x['company'], 'id': x['id'], 'ver': x['ver']} for x in supa]
merged.sort(key=lambda x: (x['t'], x['side']))
prev = None
for m in merged:
    if prev and (m['t'] - prev).total_seconds() > 20 * 60:
        print(f'  --- {int((m["t"] - prev).total_seconds() / 60)}分の空き ---')
    print(f'{m["t"].strftime("%H:%M:%S"):8s} {m["side"]:6s} {m["company"][:20]:22s} {m["id"]:24s} {m["ver"]}')
    prev = m['t']

print('\n=== 候補者IDの重複（重複排除に弾かれた可能性の確認）===')
dup = {k: v for k, v in Counter(x['id'] for x in supa).items() if v > 1}
if dup:
    for k, v in dup.items():
        print(f'  {k}: {v}件')
else:
    print('  重複なし')

ids = [x['id'] for x in supa]
print(f'\n候補者IDの種類: {len(set(ids))} / 記録件数: {len(ids)}')
print('※ 種類が極端に少ない場合、同じIDが使い回されて重複排除に弾かれています')

print('\n=== 拡張機能のバージョン別 ===')
for k, v in Counter(x['ver'] for x in supa).most_common():
    print(f'  {k}: {v}件')
