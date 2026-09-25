"""
doda-XのプロフィールURLが、過去にどんな形式で記録されていたかを調べる。読み取り専用。

実行:
  python3 probe_dodax_url.py
  python3 probe_dodax_url.py rds      # 比較用に他媒体も見られる
"""
import json
import sys
import urllib.request
import urllib.parse
from collections import Counter

SUPABASE_URL = 'https://ovwnyivqnqqiagutjxoo.supabase.co'
SUPABASE_KEY = 'sb_publishable_tEQ4TOve0uCydsGiEm1cDA_D1LQ49wN'
H = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}', 'Prefer': 'count=exact'}

PLATFORM = sys.argv[1] if len(sys.argv) > 1 else 'dodax'


def get(url):
    req = urllib.request.Request(url, headers=H)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf-8')), r.headers.get('Content-Range', '')


print(f'=== platform = {PLATFORM} ===')
_, cr = get(f'{SUPABASE_URL}/rest/v1/scouts?select=id&limit=1&platform=eq.{PLATFORM}')
print(f'全件: {cr.split("/")[-1]}件')

cols = 'platform_candidate_id,profile_url,sent_at,ext_version'
rows, _ = get(f'{SUPABASE_URL}/rest/v1/scouts?select={cols}&platform=eq.{PLATFORM}'
              f'&profile_url=not.is.null&order=sent_at.desc&limit=500')
rows = [r for r in rows if (r.get('profile_url') or '').strip()]
print(f'直近500件のうち profile_url が入っているもの: {len(rows)}件\n')

if not rows:
    print('profile_urlが記録された行はありませんでした。')
    print('→ 実際のプロフィール画面のURL形式を教えてください。')
    sys.exit()

print('=== URLの形（数値部分を<数値>に置換して集計）===')
pat = Counter()
for r in rows:
    p = urllib.parse.urlparse(r['profile_url'])
    seg = [s for s in p.path.split('/') if s]
    shape = '/'.join('<数値>' if s.isdigit() else s for s in seg)
    q = '?' + '&'.join(sorted(urllib.parse.parse_qs(p.query))) if p.query else ''
    pat[f'{p.netloc}/{shape}{q}'] += 1
for k, v in pat.most_common(10):
    print(f'  {v:4d}件  {k}')

print('\n=== 実例（新しい順に5件）===')
for r in rows[:5]:
    print(f"  {r['sent_at'][:10]}  ver={r.get('ext_version') or '-':10s}  id={r['platform_candidate_id']}")
    print(f"    {r['profile_url']}")

print('\n=== 記録できていた時期（バージョン別）===')
for k, v in Counter(r.get('ext_version') or '(なし)' for r in rows).most_common(10):
    print(f'  {k:12s}: {v}件')
