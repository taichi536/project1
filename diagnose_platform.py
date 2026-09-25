"""
753件の未登録記録を媒体(プラットフォーム)別に集計する。
さらに、れいしろうさんの3日間(8/16,8/20,8/21)全欠落分(=バージョンが古かった可能性が
高いと分かっている分)を除外した「残り」でも媒体別に集計し直し、特定の媒体に
偏りが残っていないかを確認する。書き込みは一切しない。

実行:
  python3 diagnose_platform.py
"""
import json
import os
import re
import sys
import datetime
import urllib.request
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


def day_bucket_ms(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc).strftime('%Y-%m-%d')


def normalize_company(name):
    if not name:
        return ''
    s = str(name).lower()
    s = re.sub(r'株式会社|（株）|\(株\)|合同会社|有限会社|グループ', '', s)
    s = re.sub(r'[・\s　,、.。]', '', s)
    return s.strip()


def signature(recruiter, company, day_key):
    return f"{(recruiter or '').strip()}|{normalize_company(company)}|{day_key}"


print(f'[1/3] GASから{CUTOFF_WORKDATE}以降の記録を取得中...', flush=True)
gas_data = post_json(GAS_URL, {'secret': GAS_SECRET, 'action': 'getAllDailySheetHistory'}, timeout=340)
records = [r for r in gas_data.get('records', []) if (r.get('workDate') or '') >= CUTOFF_WORKDATE]
print(f'  → {len(records)}件', flush=True)

print('[2/3] Supabaseの既存記録(同期間)を取得中...', flush=True)
cutoff_iso = f'{CUTOFF_WORKDATE}T00:00:00'
supa_rows = []
offset = 0
PAGE = 1000
while True:
    page = get_json(
        f'{SUPABASE_URL}/rest/v1/scouts?select=recruiter_name,company_name,sent_at'
        f'&sent_at=gte.{cutoff_iso}&order=sent_at.asc&limit={PAGE}&offset={offset}',
        headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'},
    )
    if not page:
        break
    supa_rows.extend(page)
    offset += PAGE
    if len(page) < PAGE:
        break

existing_sigs = set()
supa_count_by_key = defaultdict(int)
for row in supa_rows:
    try:
        dt = datetime.datetime.fromisoformat(row['sent_at'].replace('Z', '+00:00'))
    except (TypeError, ValueError):
        continue
    day = day_bucket_ms(dt.timestamp() * 1000)
    recruiter = (row.get('recruiter_name') or '').strip()
    company = row.get('company_name') or ''
    existing_sigs.add(signature(recruiter, company, day))
    supa_count_by_key[(recruiter, day)] += 1

gas_count_by_key = defaultdict(int)
for r in records:
    if not r.get('company') or not r.get('date'):
        continue
    recruiter = (r.get('recruiter') or '').strip()
    day = day_bucket_ms(r['date'])
    gas_count_by_key[(recruiter, day)] += 1

print('[3/3] 媒体別に集計中...', flush=True)
# 「説明のついている全欠落」= その(担当者,日)でSupabase側が0件のキー
explained_zero_keys = {key for key in gas_count_by_key if supa_count_by_key.get(key, 0) == 0}

total_by_platform = Counter()
missing_by_platform = Counter()
missing_excl_explained_by_platform = Counter()
total_excl_explained_by_platform = Counter()

for r in records:
    if not r.get('company') or not r.get('date'):
        continue
    recruiter = (r.get('recruiter') or '').strip()
    day = day_bucket_ms(r['date'])
    key = (recruiter, day)
    platform_key = MEDIA_LABEL_TO_KEY.get(r.get('platform', ''), r.get('platform', '') or '(不明)')
    sig = signature(recruiter, r.get('company'), day)
    is_missing = sig not in existing_sigs

    total_by_platform[platform_key] += 1
    if is_missing:
        missing_by_platform[platform_key] += 1

    if key not in explained_zero_keys:
        total_excl_explained_by_platform[platform_key] += 1
        if is_missing:
            missing_excl_explained_by_platform[platform_key] += 1

print(f'\n--- 媒体別 未登録内訳(全753件ベース) ---')
print(f'{"媒体":10s} {"GAS":>6s} {"未登録":>6s} {"未登録率":>8s}')
for p in sorted(total_by_platform, key=lambda k: -missing_by_platform[k]):
    total = total_by_platform[p]
    miss = missing_by_platform[p]
    rate = miss / total * 100 if total else 0
    print(f'{p:10s} {total:6d} {miss:6d} {rate:7.1f}%')

zero_key_count = sum(1 for k in explained_zero_keys)
zero_key_recruiters = Counter(k[0] for k in explained_zero_keys)
print(f'\n(参考: 完全欠落(説明のつく可能性が高い)キー数 = {zero_key_count} 件 内訳: {dict(zero_key_recruiters)})')

print(f'\n--- 媒体別 未登録内訳(完全欠落キーを除外した残り。=個別バグ疑いの残差) ---')
print(f'{"媒体":10s} {"GAS":>6s} {"未登録":>6s} {"未登録率":>8s}')
for p in sorted(total_excl_explained_by_platform, key=lambda k: -missing_excl_explained_by_platform[k]):
    total = total_excl_explained_by_platform[p]
    miss = missing_excl_explained_by_platform[p]
    rate = miss / total * 100 if total else 0
    flag = '  ⚠️' if rate > 20 else ''
    print(f'{p:10s} {total:6d} {miss:6d} {rate:7.1f}%{flag}')
