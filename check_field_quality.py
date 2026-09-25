"""
Supabaseの自動記録の「中身」が正しいかを確認する。件数の一致だけでは、
会社名や年齢が空だったり別人の値が入っていたりしても気づけないため。読み取り専用。
"""
import json
import os
import re
import sys
import datetime
import unicodedata
import urllib.request
from collections import defaultdict, Counter

SUPABASE_URL = 'https://ovwnyivqnqqiagutjxoo.supabase.co'
SUPABASE_KEY = 'sb_publishable_tEQ4TOve0uCydsGiEm1cDA_D1LQ49wN'
GAS_URL = os.environ.get('GAS_URL')
GAS_SECRET = os.environ.get('GAS_SECRET', 'snowwe2024')
H = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
JST = datetime.timezone(datetime.timedelta(hours=9))

MEDIA = {'RDS': 'rds', 'ビズリーチ': 'bizreach', 'dodaX': 'dodax', 'doda X': 'dodax',
         'アンビ': 'ambi', 'AMBI': 'ambi', 'Green': 'green', 'グリーン': 'green', 'マイナビ': 'mynavi'}
KANJI = {'鐵': '鉄', '廣': '広', '龍': '竜', '澤': '沢', '齋': '斎', '邊': '辺', '會': '会'}

args = [a for a in sys.argv[1:] if not a.startswith('-')]
if len(args) >= 2:
    DAY_FROM, DAY_TO = args[0], args[1]
else:
    DAY_TO = datetime.date.today().isoformat()
    DAY_FROM = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()

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


def norm(s):
    s = unicodedata.normalize('NFKC', str(s or '')).lower()
    for a, b in KANJI.items():
        s = s.replace(a, b)
    s = re.sub(r'(株式会社|有限会社|合同会社|\(株\)|㈱)', '', s)
    s = re.sub(r'[・\s,、.。／/\-ー－&()（）]', '', s)
    return s.strip()


def norm_univ(s):
    s = norm(s)
    s = re.sub(r'(学部|研究科|専門職大学院).*$', '', s)
    s = re.sub(r'(大学院|大学|大)$', '', s)
    return s


def same(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return None
    return a == b or a.startswith(b) or b.startswith(a)


fetch_from = (datetime.date.fromisoformat(DAY_FROM) - datetime.timedelta(days=1)).isoformat()
end_excl = (datetime.date.fromisoformat(DAY_TO) + datetime.timedelta(days=2)).isoformat()

print(f'[1/2] GASから{fetch_from}以降を取得中...', flush=True)
gas = post_json(GAS_URL, {'secret': GAS_SECRET, 'action': 'getAllDailySheetHistory', 'since': fetch_from})
sheet_by_key = defaultdict(list)
for r in gas.get('records', []):
    if not r.get('date'):
        continue
    t = datetime.datetime.fromtimestamp(r['date'] / 1000, tz=datetime.timezone.utc).astimezone(JST)
    key = (r.get('recruiter') or '(空欄)', MEDIA.get(r.get('platform', ''), r.get('platform', '')))
    sheet_by_key[key].append({'t': t, 'company': r.get('company') or '', 'univ': r.get('univ') or '',
                              'age': r.get('age') or '', 'position': r.get('position') or ''})
print(f'  シート: {sum(len(v) for v in sheet_by_key.values())}件', flush=True)

print('[2/2] Supabaseから取得中...', flush=True)
cols = ('platform,recruiter_name,company_name,university,candidate_age,candidate_name,'
        'position_name,candidate_industry,sent_at,ext_version')
supa = []
offset = 0
while True:
    page = get_json(f'{SUPABASE_URL}/rest/v1/scouts?select={cols}'
                    f'&sent_at=gte.{fetch_from}T00:00:00&sent_at=lt.{end_excl}T00:00:00'
                    f'&order=sent_at.asc&limit=1000&offset={offset}')
    if not page:
        break
    supa.extend(page)
    offset += 1000
    if len(page) < 1000:
        break
print(f'  Supabase: {len(supa)}件\n', flush=True)

lo = datetime.datetime.fromisoformat(DAY_FROM).replace(tzinfo=JST)
hi = datetime.datetime.fromisoformat(DAY_TO).replace(tzinfo=JST) + datetime.timedelta(days=1)
rows = []
for s in supa:
    t = datetime.datetime.fromisoformat(str(s['sent_at']).replace('Z', '+00:00')).astimezone(JST)
    if lo <= t < hi:
        s['_t'] = t
        rows.append(s)

print(f'=== ① 項目が埋まっている割合（{DAY_FROM}〜{DAY_TO} / Supabase {len(rows)}件）===')
FIELDS = [('company_name', '会社名'), ('university', '大学'), ('candidate_age', '年齢'),
          ('position_name', 'ポジション'), ('candidate_name', '候補者名'),
          ('candidate_industry', '業種'), ('recruiter_name', '担当者')]
by_platform = defaultdict(list)
for s in rows:
    by_platform[s.get('platform') or '(空)'].append(s)

print(f'{"媒体":10s} {"件数":>5s} ' + ' '.join(f'{lbl:>8s}' for _, lbl in FIELDS))
for plat, lst in sorted(by_platform.items()):
    cells = []
    for f, _ in FIELDS:
        filled = sum(1 for s in lst if s.get(f) not in (None, '', 0))
        cells.append(f'{filled / len(lst) * 100:7.0f}%')
    print(f'{plat:10s} {len(lst):5d} ' + ' '.join(cells))

print(f'\n=== ② シートの手入力と一致しているか（±3分で突き合わせ）===')
stats = defaultdict(lambda: Counter())
examples = defaultdict(list)
for plat, lst in sorted(by_platform.items()):
    for s in lst:
        key = (s.get('recruiter_name') or '(空欄)', plat)
        cands = [g for g in sheet_by_key.get(key, []) if abs((g['t'] - s['_t']).total_seconds()) <= 180]
        if not cands:
            stats[plat]['照合できず'] += 1
            continue
        g = min(cands, key=lambda x: abs((x['t'] - s['_t']).total_seconds()))
        stats[plat]['照合できた'] += 1
        r = same(g['company'], s.get('company_name'))
        if r is None:
            stats[plat]['会社名:比較不能'] += 1
        elif r:
            stats[plat]['会社名:一致'] += 1
        else:
            stats[plat]['会社名:不一致'] += 1
            if len(examples[(plat, '会社名')]) < 5:
                examples[(plat, '会社名')].append(
                    f"{s['_t'].strftime('%m/%d %H:%M')} シート「{g['company']}」 ⇔ Supabase「{s.get('company_name')}」")
        gu, su = norm_univ(g['univ']), norm_univ(s.get('university'))
        if not gu or not su:
            stats[plat]['大学:比較不能'] += 1
        elif gu.startswith(su) or su.startswith(gu):
            stats[plat]['大学:一致'] += 1
        else:
            stats[plat]['大学:不一致'] += 1
            if len(examples[(plat, '大学')]) < 5:
                examples[(plat, '大学')].append(
                    f"{s['_t'].strftime('%m/%d %H:%M')} シート「{g['univ']}」 ⇔ Supabase「{s.get('university')}」")
        ga = re.sub(r'\D', '', str(g['age']))
        sa = re.sub(r'\D', '', str(s.get('candidate_age') or ''))
        if not ga or not sa:
            stats[plat]['年齢:比較不能'] += 1
        elif ga == sa:
            stats[plat]['年齢:一致'] += 1
        else:
            stats[plat]['年齢:不一致'] += 1
            if len(examples[(plat, '年齢')]) < 5:
                examples[(plat, '年齢')].append(
                    f"{s['_t'].strftime('%m/%d %H:%M')} シート「{g['age']}」 ⇔ Supabase「{s.get('candidate_age')}」")

for plat in sorted(stats):
    c = stats[plat]
    print(f'\n■ {plat}（照合できた {c["照合できた"]}件 / できず {c["照合できず"]}件）')
    for label in ['会社名', '大学', '年齢']:
        ok, ng, na = c[f'{label}:一致'], c[f'{label}:不一致'], c[f'{label}:比較不能']
        tot = ok + ng
        rate = f'{ok / tot * 100:.1f}%' if tot else '-'
        mark = '  ⚠️' if tot and ok / tot < 0.9 else ''
        print(f'    {label}: 一致{ok} / 不一致{ng} / 比較不能{na}  → 一致率 {rate}{mark}')

print('\n=== ③ 不一致の実例 ===')
if not examples:
    print('  （なし）')
for (plat, label), ex in sorted(examples.items()):
    print(f'\n■ {plat} / {label}')
    for e in ex:
        print(f'    {e}')

print('\n=== ④ ポジション名の記録状況（上位15件）===')
for k, v in Counter((s.get('position_name') or '(空欄)') for s in rows).most_common(15):
    print(f'  {v:5d}件  {k[:60]}')
