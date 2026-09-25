"""自動記録の中身が正しいかを、1対1の割り当てで検証する。読み取り専用。"""
import json, os, re, sys, datetime, unicodedata, urllib.request
from collections import defaultdict, Counter

SUPABASE_URL = 'https://ovwnyivqnqqiagutjxoo.supabase.co'
SUPABASE_KEY = 'sb_publishable_tEQ4TOve0uCydsGiEm1cDA_D1LQ49wN'
GAS_URL = os.environ.get('GAS_URL')
GAS_SECRET = os.environ.get('GAS_SECRET', 'snowwe2024')
H = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
JST = datetime.timezone(datetime.timedelta(hours=9))
WINDOW_SEC = 300

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
    print('環境変数 GAS_URL が設定されていません。'); sys.exit(1)


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
    s = re.sub(r'(大学院|大学|大)+$', '', s)
    return s


def cmp_text(a, b, univ=False):
    na, nb = (norm_univ(a), norm_univ(b)) if univ else (norm(a), norm(b))
    if not na or not nb:
        return None
    return na == nb or na.startswith(nb) or nb.startswith(na)


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
    sheet_by_key[key].append({'t': t, 'company': r.get('company') or '', 'univ': r.get('univ') or '', 'age': r.get('age') or ''})
print(f'  シート: {sum(len(v) for v in sheet_by_key.values())}件', flush=True)

print('[2/2] Supabaseから取得中...', flush=True)
cols = ('platform,platform_candidate_id,recruiter_name,company_name,university,candidate_age,'
        'candidate_name,position_name,candidate_industry,sent_at,ext_version')
supa, offset = [], 0
while True:
    page = get_json(f'{SUPABASE_URL}/rest/v1/scouts?select={cols}'
                    f'&sent_at=gte.{fetch_from}T00:00:00&sent_at=lt.{end_excl}T00:00:00'
                    f'&order=sent_at.asc&limit=1000&offset={offset}')
    if not page:
        break
    supa.extend(page); offset += 1000
    if len(page) < 1000:
        break
print(f'  Supabase: {len(supa)}件\n', flush=True)

lo = datetime.datetime.fromisoformat(DAY_FROM).replace(tzinfo=JST)
hi = datetime.datetime.fromisoformat(DAY_TO).replace(tzinfo=JST) + datetime.timedelta(days=1)
supa_by_key, rows = defaultdict(list), []
for s in supa:
    t = datetime.datetime.fromisoformat(str(s['sent_at']).replace('Z', '+00:00')).astimezone(JST)
    if not (lo <= t < hi):
        continue
    s['_t'] = t; rows.append(s)
    supa_by_key[((s.get('recruiter_name') or '(空欄)'), s.get('platform') or '')].append(s)

print(f'=== ① 項目が埋まっている割合（Supabase {len(rows)}件）===')
FIELDS = [('company_name', '会社名'), ('university', '大学'), ('candidate_age', '年齢'),
          ('position_name', 'ポジション'), ('candidate_name', '候補者名'),
          ('candidate_industry', '業種'), ('recruiter_name', '担当者')]
by_plat = defaultdict(list)
for s in rows:
    by_plat[s.get('platform') or '(空)'].append(s)
print(f'{"媒体":10s} {"件数":>5s} ' + ' '.join(f'{l:>8s}' for _, l in FIELDS))
for plat, lst in sorted(by_plat.items()):
    cells = [f'{sum(1 for s in lst if s.get(f) not in (None, "", 0)) / len(lst) * 100:7.0f}%' for f, _ in FIELDS]
    print(f'{plat:10s} {len(lst):5d} ' + ' '.join(cells))

print('\n=== ② シートの手入力との一致（1対1で割り当て）===')
stats, examples = defaultdict(Counter), defaultdict(list)
for key in sorted(set(supa_by_key) | set(sheet_by_key)):
    who, plat = key
    ss = sorted(supa_by_key.get(key, []), key=lambda x: x['_t'])
    gg = [g for g in sheet_by_key.get(key, []) if lo <= g['t'] < hi]
    if not ss or not gg:
        continue
    pairs = []
    for i, s in enumerate(ss):
        for j, g in enumerate(gg):
            d = abs((s['_t'] - g['t']).total_seconds())
            if d <= WINDOW_SEC:
                pairs.append((d, i, j))
    pairs.sort()
    used_s, used_g, matched = set(), set(), []
    for d, i, j in pairs:
        if i in used_s or j in used_g:
            continue
        used_s.add(i); used_g.add(j); matched.append((ss[i], gg[j]))
    stats[plat]['照合できた'] += len(matched)
    stats[plat]['Supabase側で相手なし'] += len(ss) - len(used_s)
    stats[plat]['シート側で相手なし'] += len(gg) - len(used_g)
    for s, g in matched:
        for label, r, gv, sv in [
            ('会社名', cmp_text(g['company'], s.get('company_name')), g['company'], s.get('company_name')),
            ('大学', cmp_text(g['univ'], s.get('university'), univ=True), g['univ'], s.get('university'))]:
            if r is None:
                stats[plat][f'{label}:比較不能'] += 1
            elif r:
                stats[plat][f'{label}:一致'] += 1
            else:
                stats[plat][f'{label}:不一致'] += 1
                if len(examples[(plat, label)]) < 8:
                    examples[(plat, label)].append(f"{s['_t'].strftime('%m/%d %H:%M')} シート「{gv}」 ⇔ Supabase「{sv}」")
        ga = re.sub(r'\D', '', str(g['age']))
        sa = re.sub(r'\D', '', str(s.get('candidate_age') or ''))
        if not ga or not sa:
            stats[plat]['年齢:比較不能'] += 1
        elif ga == sa:
            stats[plat]['年齢:一致'] += 1
        else:
            stats[plat]['年齢:不一致'] += 1
            if len(examples[(plat, '年齢')]) < 8:
                examples[(plat, '年齢')].append(f"{s['_t'].strftime('%m/%d %H:%M')} シート「{g['age']}」 ⇔ Supabase「{s.get('candidate_age')}」")

for plat in sorted(stats):
    c = stats[plat]
    print(f'\n■ {plat}（照合 {c["照合できた"]}件 / Supabase側で相手なし {c["Supabase側で相手なし"]}件'
          f' / シート側で相手なし {c["シート側で相手なし"]}件）')
    for label in ['会社名', '大学', '年齢']:
        ok, ng, na = c[f'{label}:一致'], c[f'{label}:不一致'], c[f'{label}:比較不能']
        tot = ok + ng
        rate = f'{ok / tot * 100:.1f}%' if tot else '-'
        mark = '  ⚠️' if tot and ok / tot < 0.95 else ''
        print(f'    {label}: 一致{ok} / 不一致{ng} / 比較不能{na}  → 一致率 {rate}{mark}')

print('\n=== ③ 不一致の実例 ===')
if not examples:
    print('  （なし）')
for (plat, label), ex in sorted(examples.items()):
    print(f'\n■ {plat} / {label}')
    for e in ex:
        print(f'    {e}')

print('\n=== ④ 同じ候補者IDが複数回記録されていないか ===')
for plat, lst in sorted(by_plat.items()):
    dup = {k: v for k, v in Counter(s.get('platform_candidate_id') or '' for s in lst).items() if v > 1}
    print(f'  {plat:10s} 重複ID {len(dup)}種 / 余分な行 {sum(v - 1 for v in dup.values())}件')
