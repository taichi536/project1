"""
backfill前の最終安全確認。
Supabaseの8/16以降の行が729件あるのに、(担当者×日)でGASと照合できたのは596件だけ
だった(=133件が浮いている)。この133件が「recruiter_nameが空欄・表記違いのまま
保存された実在の記録」なのかを確認する。もしそうなら、753件をそのままbackfillすると
その分だけ重複が発生するため、照合ロジックの修正が必要になる。

書き込みは一切しない。

実行:
  python3 check_recruiter_blank.py
"""
import json
import urllib.request
import datetime
from collections import Counter, defaultdict

SUPABASE_URL = 'https://ovwnyivqnqqiagutjxoo.supabase.co'
SUPABASE_KEY = 'sb_publishable_tEQ4TOve0uCydsGiEm1cDA_D1LQ49wN'

h = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}

rows = []
offset = 0
PAGE = 1000
while True:
    url = (f'{SUPABASE_URL}/rest/v1/scouts'
           f'?select=recruiter_name,company_name,platform,sent_at,platform_candidate_id'
           f'&sent_at=gte.2026-08-16T00:00:00&order=sent_at.asc&limit={PAGE}&offset={offset}')
    req = urllib.request.Request(url, headers=h)
    page = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
    if not page:
        break
    rows.extend(page)
    offset += PAGE
    if len(page) < PAGE:
        break

print(f'Supabase 8/16以降の行数: {len(rows)} 件\n')

print('--- recruiter_name の分布 ---')
for k, v in Counter((r.get('recruiter_name') or '(空欄)') for r in rows).most_common():
    print(f'  {k!r}: {v}件')

print('\n--- platform の分布 ---')
for k, v in Counter((r.get('platform') or '(空)') for r in rows).most_common():
    print(f'  {k}: {v}件')

print('\n--- platform_candidate_id の接頭辞別 (backfill/legacy由来かどうか) ---')
def prefix(pid):
    pid = str(pid or '')
    for p in ('legacy_', 'backfill0816_', 'backfill_'):
        if pid.startswith(p):
            return p
    return '(通常=拡張機能が自動記録)'
for k, v in Counter(prefix(r.get('platform_candidate_id')) for r in rows).most_common():
    print(f'  {k}: {v}件')

print('\n--- recruiter_nameが空欄の行の日別・媒体別内訳 ---')
blanks = [r for r in rows if not (r.get('recruiter_name') or '').strip()]
print(f'  空欄の行: {len(blanks)} 件')
if blanks:
    by_day = Counter(str(r.get('sent_at'))[:10] for r in blanks)
    print('  日別:', dict(sorted(by_day.items())))
    print('  媒体別:', dict(Counter(r.get('platform') or '(空)' for r in blanks)))
    print('  会社名サンプル:', [r.get('company_name') for r in blanks[:10]])

print('\n--- 日別の行数(Supabase) ---')
by_day_all = Counter(str(r.get('sent_at'))[:10] for r in rows)
for d in sorted(by_day_all):
    print(f'  {d}: {by_day_all[d]}件')
