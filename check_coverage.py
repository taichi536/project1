"""855件のポジションが、職能ごとにどれだけあるかを数える。APIキー不要・読み取り専用。"""
import json, urllib.request
from collections import Counter

d = json.loads(urllib.request.urlopen(
    'https://143-198-195-132.nip.io/api/positions?compact=1', timeout=60).read().decode())
ps = d['positions']

GROUPS = {
    'マーケ・CX・CRM': ['マーケティング','マーケ','CX','顧客体験','カスタマー','Customer','CRM','Song','song','クリエイティブ','フロントオフィス'],
    '財務・経理':      ['財務','経理','経営管理','CFO','ファイナンス','アカウンティング'],
    'SCM・調達':       ['サプライチェーン','SCM','オペレーション','調達','ロジスティクス','購買','Operations'],
    '金融・営業':      ['金融','FS','ファイナンシャル','銀行','保険','証券','営業','セールス'],
    '人事・組織':      ['人事','組織','HR','People','タレント','Human'],
    '製造・インダストリー': ['製造','インダストリー','生産','IND','モビリティ','自動車'],
    'IT・クラウド':    ['クラウド','インフラ','テクノロジー','アーキテクト','エンジニア','TEC','Technology','Software','ソフトウェア'],
    'データ・AI':      ['データ','AI','アナリティクス','Data','サイエンス','機械学習','Analytics'],
    '戦略':            ['戦略','ストラテジ','Strategy','経営企画'],
    'リスク・監査':    ['リスク','監査','ガバナンス','コンプライアンス','Risk'],
}

def text(p):
    return f"{p.get('title') or ''} {p.get('industry') or ''} {p.get('categoryLabel') or ''}"

print(f'全 {len(ps)} 件\n')
print(f'{"職能":22s} {"件数":>5s} {"割合":>6s}   ファーム別')
for name, kws in GROUPS.items():
    hit = [p for p in ps if any(k in text(p) for k in kws)]
    by = Counter(p['firm'] for p in hit)
    top = ' / '.join(f'{k} {v}' for k, v in by.most_common(4))
    print(f'{name:22s} {len(hit):5d} {len(hit)/len(ps)*100:5.1f}%   {top}')

print('\n=== マーケ・CX・CRM の実例（最大15件）===')
for p in [p for p in ps if any(k in text(p) for k in GROUPS['マーケ・CX・CRM'])][:15]:
    print(f"  [{p['firm']}] {p['title'][:50]} ［{p.get('industry') or '-'}］")

print('\n=== どの職能にも当てはまらない求人 ===')
none = [p for p in ps if not any(any(k in text(p) for k in kws) for kws in GROUPS.values())]
print(f'  {len(none)}件')
for p in none[:8]:
    print(f"  [{p['firm']}] {p['title'][:50]} ［{p.get('industry') or '-'}］")
