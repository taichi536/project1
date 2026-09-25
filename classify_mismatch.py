"""
不一致を「表記ゆれ / 隣の候補者と一致 / 抽出ミス / 不明」に自動分類する。読み取り専用。
「隣の候補者と一致」が多ければ、詳細パネルが前の候補者のまま記録されている
（1件ずつずれている）ことになる。
"""
import json, os, re, sys, datetime, unicodedata, urllib.request
from collections import defaultdict, Counter

SUPABASE_URL = 'https://ovwnyivqnqqiagutjxoo.supabase.co'
SUPABASE_KEY = 'sb_publishable_tEQ4TOve0uCydsGiEm1cDA_D1LQ49wN'
GAS_URL = os.environ.get('GAS_URL'); GAS_SECRET = os.environ.get('GAS_SECRET', 'snowwe2024')
H = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
JST = datetime.timezone(datetime.timedelta(hours=9)); WINDOW = 300
MEDIA = {'RDS':'rds','ビズリーチ':'bizreach','dodaX':'dodax','doda X':'dodax','アンビ':'ambi',
         'AMBI':'ambi','Green':'green','グリーン':'green','マイナビ':'mynavi'}
KANJI = {'鐵':'鉄','廣':'広','龍':'竜','澤':'沢','齋':'斎','邊':'辺','會':'会','應':'応','眞':'真'}
args=[a for a in sys.argv[1:] if not a.startswith('-')]
DAY_FROM, DAY_TO = (args[0], args[1]) if len(args)>=2 else (
    (datetime.date.today()-datetime.timedelta(days=7)).isoformat(), datetime.date.today().isoformat())
if not GAS_URL: print('GAS_URL 未設定'); sys.exit(1)

def post(u,p,t=340):
    r=urllib.request.Request(u,data=json.dumps(p).encode(),method='POST',headers={})
    with urllib.request.urlopen(r,timeout=t) as x:
        raw=x.read().decode(); return json.loads(raw) if raw.strip() else {}
def get(u,t=90):
    with urllib.request.urlopen(urllib.request.Request(u,headers=H),timeout=t) as x:
        return json.loads(x.read().decode())

def base(s):
    s=unicodedata.normalize('NFKC',str(s or '')).lower()
    for a,b in KANJI.items(): s=s.replace(a,b)
    return s
def hard(s):
    """表記ゆれを強めに吸収した比較用の形"""
    s=base(s)
    s=re.sub(r'(株式会社|有限会社|合同会社|\(株\)|㈱|ホールディングス|グループ)','',s)
    s=re.sub(r'[ぁ-ん]', lambda m: chr(ord(m.group())+0x60), s)   # ひらがな→カタカナ
    s=s.replace('ヰ','イ').replace('ヱ','エ')
    s=re.sub(r'[ィイ]','イ',s); s=re.sub(r'[ャヤ]','ヤ',s)
    s=re.sub(r'[^0-9a-zァ-ヴー一-龥]','',s)
    return s
def univ_key(s):
    s=hard(s); s=re.sub(r'(ダイガクイン|ダイガク|大学院|大学|大)+$','',s); return s
ABBR={'横国':'横浜国立','東工大':'東京工業','青学':'青山学院','横市':'横浜市立','阪大':'大阪',
      '名大':'名古屋','北大':'北海道','九大':'九州','東北大':'東北','神大':'神戸','早大':'早稲田'}
def univ_same(a,b):
    ka,kb=univ_key(ABBR.get(str(a).strip(),a)),univ_key(ABBR.get(str(b).strip(),b))
    if not ka or not kb: return None
    return ka==kb or ka.startswith(kb) or kb.startswith(ka)
def comp_same(a,b):
    ka,kb=hard(a),hard(b)
    if not ka or not kb: return None
    if ka==kb or ka.startswith(kb) or kb.startswith(ka): return True
    short=min(len(ka),len(kb))
    return short>=4 and (ka[:short]==kb[:short])
def is_extract_bug(v):
    v=str(v or '')
    if not v: return False
    if len(v)<=1: return True
    if re.search(r'(大学|学部|学科|大学院)',v) and not re.search(r'(株式会社|法人)',v): return True
    if re.search(r'(部長|課長|室長|グループ長|リーダー|代理|担当)\s*$',v): return True
    if re.search(r'(推進部|企画部|営業部|開発部|本部)',v) and '会社' not in v: return True
    if v in ('基本情報','希望条件','職歴','現職','前職'): return True
    if re.search(r'(学生時代|留学|卒業後|在学中)',v): return True
    return False

ff=(datetime.date.fromisoformat(DAY_FROM)-datetime.timedelta(days=1)).isoformat()
ee=(datetime.date.fromisoformat(DAY_TO)+datetime.timedelta(days=2)).isoformat()
print(f'[1/2] GAS取得中...',flush=True)
gas=post(GAS_URL,{'secret':GAS_SECRET,'action':'getAllDailySheetHistory','since':ff})
sheet=defaultdict(list)
for r in gas.get('records',[]):
    if not r.get('date'): continue
    t=datetime.datetime.fromtimestamp(r['date']/1000,tz=datetime.timezone.utc).astimezone(JST)
    sheet[((r.get('recruiter') or '(空欄)'),MEDIA.get(r.get('platform',''),r.get('platform','')))].append(
        {'t':t,'company':r.get('company') or '','univ':r.get('univ') or '','age':r.get('age') or ''})
print(f'  シート {sum(len(v) for v in sheet.values())}件',flush=True)
print('[2/2] Supabase取得中...',flush=True)
cols='platform,recruiter_name,company_name,university,candidate_age,sent_at'
supa=[];off=0
while True:
    pg=get(f'{SUPABASE_URL}/rest/v1/scouts?select={cols}&sent_at=gte.{ff}T00:00:00'
           f'&sent_at=lt.{ee}T00:00:00&order=sent_at.asc&limit=1000&offset={off}')
    if not pg: break
    supa+=pg; off+=1000
    if len(pg)<1000: break
print(f'  Supabase {len(supa)}件\n',flush=True)
lo=datetime.datetime.fromisoformat(DAY_FROM).replace(tzinfo=JST)
hi=datetime.datetime.fromisoformat(DAY_TO).replace(tzinfo=JST)+datetime.timedelta(days=1)
sb=defaultdict(list)
for s in supa:
    t=datetime.datetime.fromisoformat(str(s['sent_at']).replace('Z','+00:00')).astimezone(JST)
    if lo<=t<hi: s['_t']=t; sb[((s.get('recruiter_name') or '(空欄)'),s.get('platform') or '')].append(s)

res=defaultdict(Counter); samples=defaultdict(list)
for key in sorted(set(sb)|set(sheet)):
    who,plat=key
    ss=sorted(sb.get(key,[]),key=lambda x:x['_t'])
    gg=sorted([g for g in sheet.get(key,[]) if lo<=g['t']<hi],key=lambda x:x['t'])
    if not ss or not gg: continue
    pairs=sorted((abs((s['_t']-g['t']).total_seconds()),i,j)
                 for i,s in enumerate(ss) for j,g in enumerate(gg)
                 if abs((s['_t']-g['t']).total_seconds())<=WINDOW)
    us,ug,matched=set(),set(),[]
    for d,i,j in pairs:
        if i in us or j in ug: continue
        us.add(i); ug.add(j); matched.append((i,j))
    for i,j in matched:
        s,g=ss[i],gg[j]
        for label,sv,gv,eq in [('会社名',s.get('company_name'),g['company'],comp_same),
                               ('大学',s.get('university'),g['univ'],univ_same)]:
            r=eq(gv,sv)
            res[(plat,label)]['照合']+=1
            if r is None: res[(plat,label)]['比較不能']+=1; continue
            if r: res[(plat,label)]['一致']+=1; continue
            if is_extract_bug(sv):
                res[(plat,label)]['抽出ミス']+=1
                if len(samples[(plat,label,'抽出ミス')])<4:
                    samples[(plat,label,'抽出ミス')].append(f"シート「{gv}」⇔ Supabase「{sv}」")
                continue
            nb=None
            for k in (j-1,j+1,j-2,j+2):
                if 0<=k<len(gg):
                    kv=gg[k]['company'] if label=='会社名' else gg[k]['univ']
                    if eq(kv,sv): nb=k-j; break
            if nb is not None:
                res[(plat,label)][f'隣と一致({nb:+d})']+=1
                if len(samples[(plat,label,'隣')])<4:
                    samples[(plat,label,'隣')].append(f"シート「{gv}」⇔ Supabase「{sv}」({nb:+d}件目のシート値と一致)")
            else:
                res[(plat,label)]['不明']+=1
                if len(samples[(plat,label,'不明')])<4:
                    samples[(plat,label,'不明')].append(f"シート「{gv}」⇔ Supabase「{sv}」")

print(f'=== 不一致の内訳（{DAY_FROM}〜{DAY_TO}）===')
for (plat,label),c in sorted(res.items()):
    tot=c['照合']; ok=c['一致']
    print(f'\n■ {plat} / {label}  照合{tot}件 / 一致{ok}件 ({ok/max(1,tot-c["比較不能"])*100:.1f}%)')
    for k,v in c.most_common():
        if k in ('照合','一致'): continue
        print(f'    {k}: {v}件')
print('\n=== 実例 ===')
for k,v in sorted(samples.items()):
    print(f'\n■ {k[0]} / {k[1]} / {k[2]}')
    for e in v: print(f'    {e}')
