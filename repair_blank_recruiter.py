"""
Supabaseのscoutsテーブルで recruiter_name が空欄のまま保存されてしまった行を、
GAS側の記録と突き合わせて担当者名を補完する。

背景:
  content.jsのGAS送信側には「担当者名が空なら送らない」というガードがあるが、
  Supabase送信側には同じガードも、GAS側にあるcandidateId経由の自動修復の仕組みも
  無かったため、設定の読み込みが一瞬空になったタイミングの記録が担当者名だけ
  空欄で保存されていた(実データで133件確認)。この状態だと「担当者×日」での
  照合が全て外れ、実在するのに「未登録」と誤判定されてbackfillで重複を生む。

補完のやり方(安全側に倒す):
  ① 会社名(正規化)+日付 でGAS側に一致する記録があり、その担当者が1人に定まる場合
     → その担当者名で補完する
  ② ①で決まらない場合、同じ日・同じ媒体のGAS記録の担当者が1人に定まる場合
     → その担当者名で補完する(会社名が誤抽出されている行の救済)
  ③ どちらでも1人に定まらない場合は補完しない(手動確認に回す)

実行:
  python3 repair_blank_recruiter.py            # 確認のみ(書き込まない)
  python3 repair_blank_recruiter.py --commit   # 実際に補完する
"""
import json
import os
import re
import sys
import datetime
import urllib.request
import urllib.error
from collections import Counter, defaultdict

SUPABASE_URL = 'https://ovwnyivqnqqiagutjxoo.supabase.co'
SUPABASE_KEY = 'sb_publishable_tEQ4TOve0uCydsGiEm1cDA_D1LQ49wN'

GAS_URL = os.environ.get('GAS_URL')
GAS_SECRET = os.environ.get('GAS_SECRET', 'snowwe2024')

CUTOFF_WORKDATE = '2026-08-16'

MEDIA_LABEL_TO_KEY = {
    'RDS': 'rds', 'ビズリーチ': 'bizreach', 'dodaX': 'dodax', 'doda X': 'dodax',
    'アンビ': 'ambi', 'AMBI': 'ambi', 'Green': 'green', 'グリーン': 'green', 'マイナビ': 'mynavi',
}

if not GAS_URL:
    print('環境変数 GAS_URL が設定されていません。')
    sys.exit(1)

COMMIT = '--commit' in sys.argv

H = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}


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


def patch_json(url, payload, headers=None, timeout=60):
    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='PATCH', headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode('utf-8')
        return json.loads(raw) if raw.strip() else {}


def day_of_ms(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc).strftime('%Y-%m-%d')


def normalize_company(name):
    if not name:
        return ''
    s = str(name).lower()
    s = re.sub(r'株式会社|（株）|\(株\)|合同会社|有限会社|グループ', '', s)
    s = re.sub(r'[・\s　,、.。]', '', s)
    return s.strip()


print(f'[1/4] GASから{CUTOFF_WORKDATE}以降の記録を取得中...', flush=True)
gas_data = post_json(GAS_URL, {'secret': GAS_SECRET, 'action': 'getAllDailySheetHistory'}, timeout=340)
gas_records = [r for r in gas_data.get('records', []) if (r.get('workDate') or '') >= CUTOFF_WORKDATE]
print(f'  → {len(gas_records)}件', flush=True)

# GAS側の索引を作る
by_company_day = defaultdict(set)   # (正規化会社名, 日) -> {担当者}
by_day_platform = defaultdict(set)  # (日, 媒体key) -> {担当者}
for r in gas_records:
    if not r.get('date'):
        continue
    day = day_of_ms(r['date'])
    recruiter = (r.get('recruiter') or '').strip()
    if not recruiter:
        continue
    platform_key = MEDIA_LABEL_TO_KEY.get(r.get('platform', ''), r.get('platform', ''))
    comp = normalize_company(r.get('company'))
    if comp:
        by_company_day[(comp, day)].add(recruiter)
    by_day_platform[(day, platform_key)].add(recruiter)

print('[2/4] Supabaseの担当者名が空欄の行を取得中...', flush=True)
blanks = []
offset = 0
PAGE = 1000
while True:
    url = (f'{SUPABASE_URL}/rest/v1/scouts'
           f'?select=id,recruiter_name,company_name,platform,sent_at'
           f'&sent_at=gte.{CUTOFF_WORKDATE}T00:00:00'
           f'&or=(recruiter_name.is.null,recruiter_name.eq.)'
           f'&order=sent_at.asc&limit={PAGE}&offset={offset}')
    page = get_json(url, headers=H)
    if not page:
        break
    blanks.extend(page)
    offset += PAGE
    if len(page) < PAGE:
        break
print(f'  → 担当者名が空欄の行: {len(blanks)} 件', flush=True)

if not blanks:
    print('補完対象がありません。')
    sys.exit(0)

print('[3/4] GAS側と突き合わせて担当者名を判定中...', flush=True)
plan = []        # (row, recruiter, 判定方法)
unresolved = []  # 決められなかった行
for row in blanks:
    day = str(row.get('sent_at'))[:10]
    comp = normalize_company(row.get('company_name'))
    platform = row.get('platform') or ''

    cands = by_company_day.get((comp, day), set()) if comp else set()
    if len(cands) == 1:
        plan.append((row, next(iter(cands)), '会社名+日'))
        continue

    cands2 = by_day_platform.get((day, platform), set())
    if len(cands2) == 1:
        plan.append((row, next(iter(cands2)), '日+媒体'))
        continue

    unresolved.append((row, cands, cands2))

print(f'  → 補完できる: {len(plan)} 件 / 判定できない: {len(unresolved)} 件\n')

print('--- 補完内容の内訳 ---')
print('  担当者別:', dict(Counter(rec for _, rec, _ in plan)))
print('  判定方法別:', dict(Counter(method for _, _, method in plan)))
print('  日別:', dict(sorted(Counter(str(row.get('sent_at'))[:10] for row, _, _ in plan).items())))

print('\n--- 補完サンプル(先頭15件) ---')
for row, rec, method in plan[:15]:
    print(f'  [{str(row.get("sent_at"))[:10]}] {row.get("platform"):9s} '
          f'会社名="{row.get("company_name")}" → 担当者="{rec}" ({method})')

if unresolved:
    print(f'\n--- 判定できなかった行(先頭15件) ---')
    for row, c1, c2 in unresolved[:15]:
        print(f'  [{str(row.get("sent_at"))[:10]}] {row.get("platform"):9s} '
              f'会社名="{row.get("company_name")}" 会社名+日候補={sorted(c1)} 日+媒体候補={sorted(c2)}')

if not COMMIT:
    print('\n--commit を付けずに実行したため、まだ書き込んでいません。')
    print('内容を確認してから python3 repair_blank_recruiter.py --commit を実行してください。')
    sys.exit(0)

print('\n[4/4] Supabaseへ書き込み中...', flush=True)
write_headers = dict(H)
write_headers['Content-Type'] = 'application/json'
write_headers['Prefer'] = 'return=minimal'

ok = 0
failed = []
for row, rec, method in plan:
    try:
        patch_json(f'{SUPABASE_URL}/rest/v1/scouts?id=eq.{row["id"]}',
                   {'recruiter_name': rec}, headers=write_headers)
        ok += 1
        if ok % 25 == 0:
            print(f'  {ok}/{len(plan)} 件 完了', flush=True)
    except urllib.error.HTTPError as e:
        failed.append((row.get('id'), e.code, e.read().decode('utf-8')[:150]))

print(f'\n補完完了: {ok} 件')
if failed:
    print(f'失敗: {len(failed)} 件')
    for rid, code, msg in failed[:10]:
        print(f'  id={rid}: {code} {msg}')
