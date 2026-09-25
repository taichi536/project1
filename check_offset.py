"""
シートとSupabaseを「何件ずらすと最も一致するか」で調べる。読み取り専用。
ズレ0で最大 → 時刻照合は正しく、-1の不一致は本当に前の候補者を記録している。
ズレ-1で最大 → 時刻照合が1件ずれていただけで、データは正常。
"""
import json, os, re, sys, datetime, unicodedata, urllib.request
from collections import defaultdict, Counter
SUPABASE_URL='https://ovwnyivqnqqiagutjxoo.supabase.co'
SUPABASE_KEY='sb_publishable_tEQ4TOve0uCydsGiEm1cDA_D1LQ49wN'
GAS_URL=os.environ.get('GAS_URL'); GAS_SECRET=os.environ.get('GAS_SECRET','snowwe2024')
H={'apikey':SUPABASE_KEY,'Authorization':f'Bearer {SUPABASE_KEY}'}
JST=datetime.timezone(datetime.timedelta(hours=9))
MEDIA={'RDS':'rds','ビズリーチ':'bizreach','dodaX':'dodax','doda X':'dodax','アンビ':'ambi',
       'AMBI':'ambi','Green':'green','グリーン':'green','マイナビ':'mynavi'}
KANJI={'鐵':'鉄','廣':'広','龍':'竜','澤':'沢','齋':'斎','邊':'辺','會':'会','應':'応'}
a=[x for x in sys.argv[1:] if not x.startswith('-')]
DAY_FROM,DAY_TO=(a[0],a[1]) if len(a)>=2 else ((datetime.date.today()-datetime.timedelta(days=7)).isoformat(),datetime.date.today().isoformat())
if not GAS_URL: print('GAS_URL 未設定'); sys.exit(1)
def post(u,p):
    r=urllib.request.Request(u,data=json.dumps(p).encode(),method='POST',headers={})
    with urllib.request.urlopen(r,timeout=340) as x:
        raw=x.read().decode(); return json.loads(raw) if raw.strip() else {}
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u,headers=H),timeout=90) as x:
        return json.loads(x.read().decode())
def hard(s):
    s=unicodedata.normalize('NFKC',str(s or '')).lower()
    for k,v in KANJI.items(): s=s.replace(k,v)
    s=re.sub(r'(株式会社|有限会社|合同会社|㈱|ホールディングス|グループ)','',s)
    s=re.sub(r'[ぁ-ん]',lambda m:chr(ord(m.group())+0x60),s)
    s=re.sub(r'[^0-9a-zァ-ヴー一-龥]','',s)
    return s
def same(x,y):
    kx,ky=hard(x),hard(y)
    if not kx or not ky: return None
    if kx==ky or kx.startswith(ky) or ky.startswith(kx): return True
    n=min(len(kx),len(ky)); return n>=4 and kx[:n]==ky[:n]
ff=(datetime.date.fromisoformat(DAY_FROM)-datetime.timedelta(days=1)).isoformat()
ee=(datetime.date.fromisoformat(DAY_TO)+datetime.timedelta(days=2)).isoformat()
print('[1/2] GAS取得中...',flush=True)
gas=post(GAS_URL,{'secret':GAS_SECRET,'action':'getAllDailySheetHistory','since':ff})
sheet=defaultdict(list)
for r in gas.get('records',[]):
    if not r.get('date'): continue
    t=datetime.datetime.fromtimestamp(r['date']/1000,tz=datetime.timezone.utc).astimezone(JST)
    sheet[((r.get('recruiter') or '(空欄)'),MEDIA.get(r.get('platform',''),r.get('platform','')),t.strftime('%Y-%m-%d'))].append({'t':t,'company':r.get('company') or ''})
print('[2/2] Supabase取得中...',flush=True)
supa=[];off=0
while True:
    pg=get(f'{SUPABASE_URL}/rest/v1/scouts?select=platform,recruiter_name,company_name,sent_at'
           f'&sent_at=gte.{ff}T00:00:00&sent_at=lt.{ee}T00:00:00&order=sent_at.asc&limit=1000&offset={off}')
    if not pg: break
    supa+=pg; off+=1000
    if len(pg)<1000: break
lo=datetime.datetime.fromisoformat(DAY_FROM).replace(tzinfo=JST)
hi=datetime.datetime.fromisoformat(DAY_TO).replace(tzinfo=JST)+datetime.timedelta(days=1)
sb=defaultdict(list)
for s in supa:
    t=datetime.datetime.fromisoformat(str(s['sent_at']).replace('Z','+00:00')).astimezone(JST)
    if lo<=t<hi: s['_t']=t; sb[((s.get('recruiter_name') or '(空欄)'),s.get('platform') or '',t.strftime('%Y-%m-%d'))].append(s)
print()
score=defaultdict(Counter); dt=defaultdict(list)
for key in sorted(set(sb)&set(sheet)):
    who,plat,day=key
    ss=sorted(sb[key],key=lambda x:x['_t']); gg=sorted(sheet[key],key=lambda x:x['t'])
    if len(ss)<3 or len(gg)<3: continue
    for k in range(-2,3):
        ok=0
        for i,s in enumerate(ss):
            j=i+k
            if 0<=j<len(gg) and same(gg[j]['company'],s.get('company_name')): ok+=1
        score[plat][k]+=ok
    for i,s in enumerate(ss):
        for g in gg:
            if same(g['company'],s.get('company_name')):
                dt[plat].append((s['_t']-g['t']).total_seconds()); break
print('=== 何件ずらすと最も一致するか（0が最大なら照合は正しい）===')
for plat,c in sorted(score.items()):
    best=max(c,key=lambda k:c[k])
    print(f'\n■ {plat}  最適なズレ = {best:+d}')
    for k in range(-2,3):
        bar='█'*int(c[k]/max(1,c[best])*40)
        print(f'    ズレ{k:+d}: {c[k]:5d}件 {bar}{"  ←最大" if k==best else ""}')
print('\n=== 会社名が一致したペアの時刻差（Supabase - シート）===')
for plat,v in sorted(dt.items()):
    if not v: continue
    v=sorted(v); n=len(v)
    print(f'  {plat:10s} 件数{n:5d}  中央値 {v[n//2]:+7.0f}秒  下位25% {v[n//4]:+7.0f}秒  上位25% {v[3*n//4]:+7.0f}秒')
