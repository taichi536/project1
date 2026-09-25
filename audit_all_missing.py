"""
全担当者・全媒体について、シート(手入力)とSupabase(自動記録)を突き合わせ、
記録漏れを洗い出す。照合は「時刻の近さ＋大学名」を主軸にするため、
会社名の表記ゆれ(全角半角・旧字体・略称)の影響を受けない。読み取り専用。

拡張機能の接続切れ(Extension context invalidated)による漏れは、
「ある時点から連続して漏れる」形になるため、連続ブロックも検出して表示する。

実行:
  python3 audit_all_missing.py                      # 直近7日
  python3 audit_all_missing.py 2026-09-17 2026-09-18 # 期間指定
"""
import json
import os
import re
import sys
import datetime
import unicodedata
import urllib.request
from collections import defaultdict

SUPABASE_URL = 'https://ovwnyivqnqqiagutjxoo.supabase.co'
SUPABASE_KEY = 'sb_publishable_tEQ4TOve0uCydsGiEm1cDA_D1LQ49wN'
GAS_URL = os.environ.get('GAS_URL')
GAS_SECRET = os.environ.get('GAS_SECRET', 'snowwe2024')
H = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
JST = datetime.timezone(datetime.timedelta(hours=9))

MEDIA_LABEL_TO_KEY = {
    'RDS': 'rds', 'ビズリーチ': 'bizreach', 'dodaX': 'dodax', 'doda X': 'dodax',
    'アンビ': 'ambi', 'AMBI': 'ambi', 'Green': 'green', 'グリーン': 'green', 'マイナビ': 'mynavi',
}
KANJI_VARIANTS = {'鐵': '鉄', '廣': '広', '龍': '竜', '澤': '沢', '齋': '斎', '邊': '辺', '會': '会'}

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
    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='POST', headers={})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode('utf-8')
        return json.loads(raw) if raw.strip() else {}


def get_json(url, timeout=90):
    with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def norm_univ(s):
    s = unicodedata.normalize('NFKC', str(s or '')).lower()
    for a, b in KANJI_VARIANTS.items():
        s = s.replace(a, b)
    s = re.sub(r'[・\s,、.。／/\-ー－&]', '', s)
    s = re.sub(r'(学部|研究科|専門職大学院).*$', '', s)
    s = re.sub(r'(大学院|大学|大)$', '', s)
    return s.strip()


fetch_from = (datetime.date.fromisoformat(DAY_FROM) - datetime.timedelta(days=1)).isoformat()

print(f'[1/2] GASから{fetch_from}以降を取得中...', flush=True)
gas = post_json(GAS_URL, {'secret': GAS_SECRET, 'action': 'getAllDailySheetHistory', 'since': fetch_from})
gas_by_key = defaultdict(list)
for r in gas.get('records', []):
    wd = r.get('workDate') or ''
    if wd < fetch_from or wd > DAY_TO or not r.get('date'):
        continue
    pkey = MEDIA_LABEL_TO_KEY.get(r.get('platform', ''), r.get('platform', ''))
    who = r.get('recruiter') or '(空欄)'
    r['_t'] = datetime.datetime.fromtimestamp(r['date'] / 1000, tz=datetime.timezone.utc).astimezone(JST)
    gas_by_key[(who, pkey)].append(r)
print(f'  シート: {sum(len(v) for v in gas_by_key.values())}件', flush=True)

print(f'[2/2] Supabaseから取得中...', flush=True)
end_excl = (datetime.date.fromisoformat(DAY_TO) + datetime.timedelta(days=1)).isoformat()
supa_rows = []
offset = 0
while True:
    page = get_json(
        f'{SUPABASE_URL}/rest/v1/scouts?select=platform,recruiter_name,company_name,university,sent_at'
        f'&sent_at=gte.{fetch_from}T00:00:00&sent_at=lt.{end_excl}T15:00:00'
        f'&order=sent_at.asc&limit=1000&offset={offset}')
    if not page:
        break
    supa_rows.extend(page)
    offset += 1000
    if len(page) < 1000:
        break
supa_by_key = defaultdict(list)
for s in supa_rows:
    s['_t'] = datetime.datetime.fromisoformat(str(s['sent_at']).replace('Z', '+00:00')).astimezone(JST)
    supa_by_key[((s.get('recruiter_name') or '(空欄)'), s.get('platform') or '')].append(s)
print(f'  Supabase: {len(supa_rows)}件\n', flush=True)

lo = datetime.datetime.fromisoformat(DAY_FROM).replace(tzinfo=JST)
hi = datetime.datetime.fromisoformat(DAY_TO).replace(tzinfo=JST) + datetime.timedelta(days=1)

print(f'=== 記録漏れの集計（{DAY_FROM}〜{DAY_TO}）===\n')
print(f'{"担当者":10s} {"媒体":10s} {"シート":>6s} {"記録済":>6s} {"漏れ":>5s} {"漏れ率":>7s}')
total_sheet = total_miss = 0
details = {}

for key in sorted(set(gas_by_key) | set(supa_by_key)):
    who, media = key
    gas_rows = sorted(gas_by_key.get(key, []), key=lambda x: x['_t'])
    unused = list(supa_by_key.get(key, []))
    miss = []
    for g in gas_rows:
        gu = norm_univ(g.get('univ'))
        hit = None
        for s in unused:
            if abs((s['_t'] - g['_t']).total_seconds()) > 300:
                continue
            su = norm_univ(s.get('university'))
            if gu and su and (gu == su or gu.startswith(su) or su.startswith(gu)):
                hit = s
                break
        if not hit:
            best, best_gap = None, 181
            for s in unused:
                gap = abs((s['_t'] - g['_t']).total_seconds())
                if gap < best_gap:
                    best, best_gap = s, gap
            hit = best
        if hit:
            unused.remove(hit)
        elif lo <= g['_t'] < hi:
            miss.append(g)

    in_window = [g for g in gas_rows if lo <= g['_t'] < hi]
    if not in_window:
        continue
    total_sheet += len(in_window)
    total_miss += len(miss)
    rate = len(miss) / len(in_window) * 100
    mark = '  ⚠️' if rate >= 10 else ''
    print(f'{who:10s} {media:10s} {len(in_window):6d} {len(in_window)-len(miss):6d} {len(miss):5d} {rate:6.1f}%{mark}')
    if miss:
        details[key] = miss

print(f'\n合計: シート {total_sheet}件 / 漏れ {total_miss}件 ({total_miss/max(1,total_sheet)*100:.1f}%)')

print('\n=== 漏れが連続している時間帯（拡張機能の接続切れの疑い）===')
found_block = False
for key, miss in details.items():
    who, media = key
    blocks = []
    cur = [miss[0]]
    for prev, g in zip(miss, miss[1:]):
        if (g['_t'] - prev['_t']).total_seconds() <= 15 * 60:
            cur.append(g)
        else:
            blocks.append(cur)
            cur = [g]
    blocks.append(cur)
    for b in blocks:
        if len(b) < 3:
            continue
        found_block = True
        print(f"  {who} / {media}: {b[0]['_t'].strftime('%m/%d %H:%M')} 〜 {b[-1]['_t'].strftime('%H:%M')} "
              f"に {len(b)}件連続で漏れ  ⚠️")
if not found_block:
    print('  （3件以上の連続した漏れは見つかりませんでした）')
