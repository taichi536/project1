"""
Supabaseに記録済みの会社名・大学名が、どれくらい正しく取れているかを媒体別に測る。
書き込みは一切しない。

「明らかに会社名ではない」「明らかに大学名ではない」パターンを機械的に数えるので、
どの媒体のどの抽出ロジックを直すべきかが件数で分かる。

実行:
  python3 audit_extraction.py           # 直近30日
  python3 audit_extraction.py --all     # 全期間
"""
import json
import re
import sys
import datetime
import urllib.request
from collections import Counter, defaultdict

SUPABASE_URL = 'https://ovwnyivqnqqiagutjxoo.supabase.co'
SUPABASE_KEY = 'sb_publishable_tEQ4TOve0uCydsGiEm1cDA_D1LQ49wN'
H = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}

ALL = '--all' in sys.argv
since = '' if ALL else (datetime.datetime.now(datetime.timezone.utc)
                        - datetime.timedelta(days=30)).strftime('%Y-%m-%d')

print(f'Supabaseから取得中（{"全期間" if ALL else since + " 以降"}）...', flush=True)
rows = []
offset = 0
PAGE = 1000
while True:
    url = (f'{SUPABASE_URL}/rest/v1/scouts'
           f'?select=platform,company_name,university,candidate_age,platform_candidate_id,sent_at'
           + (f'&sent_at=gte.{since}T00:00:00' if since else '')
           + f'&order=sent_at.asc&limit={PAGE}&offset={offset}')
    page = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=90).read().decode())
    if not page:
        break
    rows.extend(page)
    offset += PAGE
    if len(page) < PAGE:
        break
print(f'  → {len(rows)} 件\n')

# 拡張機能が自動記録した行だけを評価対象にする。
# ・legacy_ / backfill... = 件数合わせのために後から入れた行（会社名以外が空）
# ・sheet_ = スプレッドシートから取り込んだ行。手入力のため「早稲田」「本田技研工業」の
#   ように略記されており、これを抽出ミスとして数えると大学名の誤り率が74〜98%という
#   実態とかけ離れた数字になる（実際に発生させてしまったため明示的に除外する）
SYNTHETIC_PREFIXES = ('legacy_', 'backfill', 'sheet_', '__rebuild_probe')
print('--- platform_candidate_id の接頭辞別 件数 ---')
def prefix_of(pid):
    pid = str(pid or '')
    for p in SYNTHETIC_PREFIXES:
        if pid.startswith(p):
            return p
    return '(拡張機能の自動記録)'
for k, v in Counter(prefix_of(r.get('platform_candidate_id')) for r in rows).most_common():
    print(f'  {k}: {v}件')

rows = [r for r in rows if not str(r.get('platform_candidate_id') or '').startswith(SYNTHETIC_PREFIXES)]
print(f'\n（後から取り込んだ行を除いた評価対象: {len(rows)} 件）\n')


def company_problem(c, univ):
    """会社名として明らかにおかしいパターンを返す（正常ならNone）"""
    s = (c or '').strip()
    if not s:
        return '空欄'
    if re.search(r'\d{1,3}歳', s):
        return '年齢が入っている'
    if re.search(r'\s[/／]\s', s):
        return '業種表記(A / B)'
    if re.search(r'卒業|修了|在学|入学|研究科|専攻|学歴', s):
        return '学歴が入っている'
    if re.match(r'^[\d,.\s]+$', s):
        return '数字だけ'
    if re.search(r'万円|年収', s):
        return '年収が入っている'
    if re.match(r'^\d+通$', s) or s in ('新着', 'NEW'):
        return 'カードの定型ラベル'
    if re.search(r'(?:大学院|大学)$', s) and '病院' not in s:
        return '大学名が入っている'
    if univ and s.strip() == (univ or '').strip():
        return '大学名と同じ値'
    if len(s) > 40:
        return '長すぎる(40字超)'
    return None


def univ_problem(u):
    """大学名として明らかにおかしいパターンを返す（空欄はカウントするが別枠）"""
    s = (u or '').strip()
    if not s:
        return '空欄'
    if re.search(r'株式会社|合同会社|有限会社|ホールディングス', s):
        return '会社名が入っている'
    if '学歴' in s:
        return '「学歴」を含む'
    if re.match(r'^(?:[0-9０-９]{1,2}|[一二三四五六七八九十]{1,2})年制', s):
        return '一般名詞(◯年制)'
    if re.match(r'^(?:国公立|国立|公立|私立|有名|難関|一般)(?:大学院|大学)$', s):
        return '一般名詞(国公立大学等)'
    if not re.search(r'大学|大学院|高専|専門学校', s):
        return '学校名に見えない'
    if len(s) > 30:
        return '長すぎる(30字超)'
    return None


by_platform = defaultdict(list)
for r in rows:
    by_platform[r.get('platform') or '(不明)'].append(r)

print('=' * 70)
print('会社名の状態（媒体別）')
print('=' * 70)
print(f'{"媒体":10s} {"件数":>6s} {"問題あり":>8s} {"問題率":>7s}')
comp_detail = {}
for p in sorted(by_platform, key=lambda k: -len(by_platform[k])):
    rs = by_platform[p]
    probs = [(company_problem(r.get('company_name'), r.get('university')), r) for r in rs]
    bad = [(k, r) for k, r in probs if k]
    comp_detail[p] = bad
    rate = len(bad) / len(rs) * 100 if rs else 0
    flag = '  ⚠️' if rate >= 5 else ''
    print(f'{p:10s} {len(rs):6d} {len(bad):8d} {rate:6.1f}%{flag}')

print('\n--- 会社名の問題の内訳（媒体別・上位） ---')
for p in sorted(comp_detail, key=lambda k: -len(comp_detail[k])):
    bad = comp_detail[p]
    if not bad:
        continue
    print(f'\n[{p}] {len(bad)}件')
    for kind, n in Counter(k for k, _ in bad).most_common():
        print(f'    {kind}: {n}件')
        samples = [r for k, r in bad if k == kind][:3]
        for s in samples:
            print(f'        例) company_name="{s.get("company_name")}" '
                  f'university="{s.get("university")}" {str(s.get("sent_at"))[:10]}')

print('\n' + '=' * 70)
print('大学名の状態（媒体別）')
print('=' * 70)
print(f'{"媒体":10s} {"件数":>6s} {"空欄":>6s} {"空欄率":>7s} {"誤り":>6s} {"誤り率":>7s}')
univ_detail = {}
for p in sorted(by_platform, key=lambda k: -len(by_platform[k])):
    rs = by_platform[p]
    probs = [(univ_problem(r.get('university')), r) for r in rs]
    empty = [(k, r) for k, r in probs if k == '空欄']
    bad = [(k, r) for k, r in probs if k and k != '空欄']
    univ_detail[p] = bad
    er = len(empty) / len(rs) * 100 if rs else 0
    br = len(bad) / len(rs) * 100 if rs else 0
    flag = '  ⚠️' if br >= 5 else ''
    print(f'{p:10s} {len(rs):6d} {len(empty):6d} {er:6.1f}% {len(bad):6d} {br:6.1f}%{flag}')

print('\n--- 大学名の問題の内訳（空欄を除く） ---')
for p in sorted(univ_detail, key=lambda k: -len(univ_detail[k])):
    bad = univ_detail[p]
    if not bad:
        continue
    print(f'\n[{p}] {len(bad)}件')
    for kind, n in Counter(k for k, _ in bad).most_common():
        print(f'    {kind}: {n}件')
        for s in [r for k, r in bad if k == kind][:3]:
            print(f'        例) university="{s.get("university")}" '
                  f'company_name="{s.get("company_name")}" {str(s.get("sent_at"))[:10]}')

print('\n※ 空欄は「本当にその媒体に情報が無い」場合もあるため、誤りとは別に集計しています。')
