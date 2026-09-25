"""ポジション提案の精度を測る。拡張機能と同じロジックをブラウザ抜きで実行する。"""
import json, os, re, sys, urllib.parse, urllib.request

POSITIONS_API = 'https://143-198-195-132.nip.io/api/positions'
ANTHROPIC_API = 'https://api.anthropic.com/v1/messages'
MODEL = 'claude-haiku-4-5-20251001'
API_KEY = os.environ.get('ANTHROPIC_API_KEY', '').strip()

CASES = [
 {'name':'CRM・デジタルマーケ（事業会社）',
  'expect':['マーケティング','マーケ','CX','顧客体験','カスタマー','Customer','CRM','Song','song','クリエイティブ','フロントオフィス'],
  'profile':'''株式会社◯◯（消費財メーカー、従業員3,000名）
デジタルマーケティング部 CRMグループ マネージャー / 2019年4月〜在職中
・自社ECおよび会員基盤（会員数約180万人）のCRM戦略立案と実行を担当
・MA（Salesforce Marketing Cloud）を用いたシナリオ設計、セグメント別配信の設計・改善
・顧客データ基盤（CDP）の導入プロジェクトに事業側の責任者として参画
・LTV向上施策により、既存顧客の年間購入回数を1.8回から2.4回へ改善
・広告代理店3社のディレクション、年間予算6億円の配分最適化
・メンバー6名のマネジメント
株式会社△△（広告代理店）/ 2014年4月〜2019年3月
・アカウントプランナーとして消費財・小売クライアントを担当
慶應義塾大学 商学部 卒業 / 34歳'''},
 {'name':'経理・財務（メーカー）',
  'expect':['財務','経理','経営管理','CFO','ファイナンス','アカウンティング'],
  'profile':'''株式会社◯◯（精密機器メーカー、売上2,400億円）
経理部 主計課 課長代理 / 2017年4月〜在職中
・連結決算業務の取りまとめ（子会社28社、うち海外14社）
・IFRS導入プロジェクトのメンバーとして会計方針の策定に関与
・月次・四半期・年次決算、有価証券報告書の作成
・原価計算制度の見直し、製品別収益性分析の仕組みづくり
株式会社△△（監査法人）/ 2012年10月〜2017年3月
・製造業・小売業の法定監査に従事
公認会計士 / 一橋大学 経済学部 卒業 / 37歳'''},
 {'name':'SCM・調達（製造業）',
  'expect':['サプライチェーン','SCM','オペレーション','調達','ロジスティクス','購買','Operations'],
  'profile':'''株式会社◯◯（自動車部品メーカー）
グローバル調達本部 部品調達部 課長 / 2018年4月〜在職中
・電子部品・樹脂部品の調達戦略立案、年間調達額約900億円
・半導体不足時の代替ソース開拓、BCP体制の構築
・サプライヤー約120社の評価制度の設計と運用
・需給計画（S&OP）会議の事務局として生産・販売・調達の調整をリード
・在庫回転日数を62日から45日へ改善
東京工業大学 工学部 卒業 / 38歳'''},
 {'name':'法人営業（金融）',
  'expect':['金融','FS','ファイナンシャル','銀行','保険','証券','営業','セールス'],
  'profile':'''株式会社◯◯銀行 法人営業部 上席調査役 / 2016年4月〜在職中
・中堅・中小企業約80社を担当、融資残高約450億円
・事業承継・M&Aの提案、実行支援（成約12件）
・資本政策、ストラクチャードファイナンスの組成
・取引先の海外進出支援（東南アジア中心）
早稲田大学 政治経済学部 卒業 / 40歳'''},
 {'name':'人事（制度設計）',
  'expect':['人事','組織','HR','People','タレント','チェンジマネジメント','Human'],
  'profile':'''株式会社◯◯（IT企業、従業員1,200名）
人事本部 人事企画部 マネージャー / 2019年7月〜在職中
・等級・評価・報酬制度の全面改定プロジェクトをリード（対象1,200名）
・ジョブ型人事制度の設計、職務記述書の整備
・人事システム（Workday）の導入、業務プロセスの再設計
・従業員エンゲージメント調査の設計と改善施策の推進
中央大学 法学部 卒業 / 36歳'''},
 {'name':'生産技術（自動車）',
  'expect':['製造','インダストリー','生産','IND','モビリティ','自動車','エンジニアリング'],
  'profile':'''株式会社◯◯（自動車メーカー）生産技術部 主任 / 2015年4月〜在職中
・車体組立ラインの工程設計、設備仕様の策定
・海外工場（タイ・メキシコ）の立ち上げに従事、現地技術者の教育を担当
・IoTセンサーを用いた設備稼働モニタリングの導入、ダウンタイムを23%削減
・自動化・省人化の投資計画立案（年間約40億円）
名古屋大学 工学部 機械航空工学科 卒業 / 35歳'''},
 {'name':'ITインフラ・クラウド',
  'expect':['クラウド','インフラ','テクノロジー','IT','アーキテクト','エンジニア','TEC','Technology','Software','ソフトウェア'],
  'profile':'''株式会社◯◯（SIer）クラウドインフラ部 テックリード / 2018年4月〜在職中
・金融機関の基幹システムのAWS移行プロジェクトでインフラ設計を担当
・TerraformによるIaC化、CI/CDパイプラインの構築
・Kubernetesを用いたコンテナ基盤の設計・運用
・セキュリティ要件（FISC準拠）の整理とアーキテクチャへの反映
AWS認定ソリューションアーキテクト プロフェッショナル
東京理科大学 理工学部 卒業 / 36歳'''},
 {'name':'データサイエンティスト',
  'expect':['データ','AI','アナリティクス','Data','サイエンス','機械学習','Analytics'],
  'profile':'''株式会社◯◯（EC事業会社）データサイエンス部 シニアデータサイエンティスト / 2020年4月〜在職中
・需要予測モデルの構築（LightGBM、Prophet）、欠品率を4.2%から1.8%へ改善
・レコメンドエンジンの改善、CTRを前年比118%に
・A/Bテスト基盤の設計、効果検証プロセスの標準化
・BigQuery / dbt によるデータ基盤の整備
京都大学大学院 情報学研究科 修了 / 33歳'''},
]

FIRM_JA={'Accenture':'アクセンチュア','Deloitte':'デロイト トーマツ コンサルティング',
 'EY':'EYストラテジー・アンド・コンサルティング','PwC':'PwCコンサルティング',
 'KPMG':'KPMGコンサルティング','future':'フューチャー'}

def http_json(url,data=None,headers=None,timeout=120):
    req=urllib.request.Request(url,data=data,headers=headers or {},method='POST' if data else 'GET')
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))

def claude(prompt,max_tokens):
    body=json.dumps({'model':MODEL,'max_tokens':max_tokens,'messages':[{'role':'user','content':prompt}]}).encode()
    d=http_json(ANTHROPIC_API,body,{'content-type':'application/json','x-api-key':API_KEY,'anthropic-version':'2023-06-01'})
    u=d.get('usage',{})
    return (d.get('content',[{}])[0].get('text','') or '').strip(), u.get('input_tokens',0)/1e6+u.get('output_tokens',0)/1e6*5

def firm_ja(f): return FIRM_JA.get(f,f or '')

def match_text(p):
    t=(p.get('title') or '').strip(); i=(p.get('industry') or '').strip(); c=(p.get('categoryLabel') or '').strip()
    parts=[t]
    if i: parts.append(i)
    if c and c!=i and c not in i and i not in c: parts.append(c)
    return ' / '.join([x for x in parts if x])

def hits(p,exp):
    s=f"{p.get('title') or ''} {p.get('industry') or ''} {p.get('categoryLabel') or ''}"
    return any(k in s for k in exp)

def run_case(case,positions):
    cost=0.0
    indexed='\n'.join(f"{i}\t{firm_ja(p['firm'])}\t{match_text(p)}" for i,p in enumerate(positions))
    step1=f'''あなたはハイクラスコンサル転職支援の専門エージェントです。募集ポジションはアクセンチュア・BIG4・ベイカレント等、複数のファームのものが混在しています。
以下の候補者プロフィールと募集ポジション一覧を照合し、最も合致しそうなポジションを上位15件選んでください。
一覧は「番号<TAB>ファーム名<TAB>ポジション名 / 領域 / カテゴリ」の形式です。

【選び方】
1. 最優先は職能の一致です。候補者がこれまで担ってきた職能（営業、マーケティング、CRM、人事、財務・経理、経営企画、SCM・調達、生産・製造、IT・システム、データ・AI、リスク・監査 等）と、ポジションが扱う職能が噛み合うものを選んでください。
2. 職能が合わないポジションは、ファームの知名度が高くても選ばないでください。「戦略」「DX」「テクノロジー」等の汎用的な名前は、どの候補者にも当てはまるように見えますが、候補者の職能と関係がなければ不適切です。
3. 職能が合う候補が15件に満たない場合のみ、隣接領域に広げてください。
4. ポジション名の長さはファームごとの記載ルールの違いで、求人の良し悪しとは無関係です。

【募集ポジション一覧】
{indexed}

【候補者プロフィール】
{case['profile']}

【重要】出力は番号のJSON配列のみ:
[12,45,301,...]'''
    text,c=claude(step1,300); cost+=c
    m=re.search(r'\[[\s\S]*?\]',text); short=[]
    if m:
        try: short=[positions[int(n)] for n in json.loads(m.group()) if isinstance(n,int) and 0<=n<len(positions)][:15]
        except Exception: pass
    if not short: return {'error':'絞り込みに失敗','cost':cost}
    ids=urllib.parse.quote(','.join(p['id'] for p in short))
    det=http_json(f'{POSITIONS_API}?ids={ids}').get('positions',[])
    by={p['id']:p for p in det}; detailed=[by.get(p['id'],p) for p in short]
    def desc(p):
        q=[]
        if p.get('categoryLabel'): q.append('【カテゴリ】'+p['categoryLabel'])
        if p.get('jobContent'): q.append('【職務内容】'+p['jobContent'])
        if p.get('qualification'): q.append('【応募要件】'+p['qualification'])
        return ' / '.join(q)[:2500]
    listing='\n'.join(f"{firm_ja(p['firm'])}｜{p['title']}: {desc(p)}" for p in detailed)
    step2=f'''あなたはコンサルファームへの転職支援を専門とするハイクラス転職エージェントです。
候補者にスカウトを送る際、どのポジションで打てば「刺さるか」を判断してください。

【判断の視点】（上から順に重要）
1. 職能が一致しているか。合わないものは他がどれだけ良くても高いスコアを付けないこと
2. 候補者の主要スキルと募集要件が具体的に合致しているか
3. 推定グレード・経験年数に見合ったポジションか

【注意】「戦略」「DX」「テクノロジー」のような汎用的な名前は、募集要件を読まないとどの候補者にも合うように見えます。名前の印象ではなく募集要件で判断してください。

【募集ポジション一覧】
{listing}

【候補者プロフィール】
{case['profile']}

以下のJSON形式のみで出力:
{{"suggestions":[{{"position":"ポジション名","match_score":90,"reason":"理由を1文で"}}]}}'''
    t2,c2=claude(step2,1500); cost+=c2
    m2=re.search(r'\{[\s\S]*\}',t2); top=[]
    if m2:
        s=re.sub(r'[\r\n]+',' ',m2.group()); s=re.sub(r',(\s*[}\]])',r'\1',s)
        try: top=json.loads(s).get('suggestions',[])[:3]
        except Exception: pass
    def find(nm):
        n=re.sub(r'^[^｜]{1,30}｜','',str(nm or '')).strip()
        for p in detailed:
            if p['title'].strip()==n or n in p['title'] or p['title'] in n: return p
        return None
    tp=[find(s.get('position')) for s in top]
    return {'top':top,'top_pos':tp,
            'ok_top':any(p is not None and hits(p,case['expect']) for p in tp),
            'ok_short':any(hits(p,case['expect']) for p in detailed),
            'n_short':sum(1 for p in detailed if hits(p,case['expect'])),
            'n_all':sum(1 for p in positions if hits(p,case['expect'])),'cost':cost}

def main():
    if not API_KEY:
        print('ANTHROPIC_API_KEY が未設定です'); sys.exit(1)
    print('ポジション一覧を取得中...',flush=True)
    positions=http_json(f'{POSITIONS_API}?compact=1').get('positions',[])
    print(f'  {len(positions)}件\n',flush=True)
    want=[int(a) for a in sys.argv[1:] if a.isdigit()]
    total=passed=0; cost=0.0; res=[]
    for i,case in enumerate(CASES,1):
        if want and i not in want: continue
        print(f'[{i}/{len(CASES)}] {case["name"]} ...',flush=True)
        r=run_case(case,positions); cost+=r.get('cost',0); total+=1
        if r.get('error'):
            print(f'    ❌ {r["error"]}\n'); res.append((case['name'],'実行失敗')); continue
        if r['ok_top']: passed+=1; v='✅ 合格'
        elif r['ok_short']: v='⚠️ 順位の問題'
        else: v='❌ 取りこぼし'
        res.append((case['name'],v))
        print(f'    {v}')
        print(f'    期待職能の求人: 全{len(positions)}件中{r["n_all"]}件 / 絞り込み15件中{r["n_short"]}件')
        for j,(s,p) in enumerate(zip(r['top'],r['top_pos']),1):
            mk='○' if (p is not None and hits(p,case['expect'])) else '×'
            print(f'    {j}位 {mk} {str(s.get("position",""))[:60]}（{s.get("match_score","")}点）')
        print()
    print('='*64)
    for nm,v in res: print(f'  {v:14s} {nm}')
    print(f'\n合格 {passed}/{total} 件 / 実行費用 ${cost:.3f}')
    print('\n⚠️ 順位の問題 が多い → 判断基準の与え方に原因がある')
    print('❌ 取りこぼし が多い → 850件から15件を選ばせる作り自体に原因がある')

main()
