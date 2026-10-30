"""
全担当者・全媒体について、シート(手入力)とSupabase(自動記録)を突き合わせ、
記録漏れを洗い出す。照合は「時刻の近さ＋大学名」を主軸にするため、
会社名の表記ゆれ(全角半角・旧字体・略称)の影響を受けない。読み取り専用。

拡張機能の接続切れ(Extension context invalidated)による漏れは、
「ある時点から連続して漏れる」形になるため、連続ブロックも検出して表示する。

比べる相手は拡張機能が書いた行だけ（ext_version があるもの）。
2026-10-24 からシートの行が Supabase に写されており（ext_version が空）、
それと突き合わせるとシート同士を比べることになって必ず一致してしまう。
写しも含めたいときだけ --with-sync を付ける。

実行:
  python3 audit_all_missing.py                      # 直近7日
  python3 audit_all_missing.py 2026-09-17 2026-09-18 # 期間指定
  python3 audit_all_missing.py 2026-10-25 2026-10-29 --with-sync
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
# RLSを有効にしたため、publishableキーでは scouts を読めない。
# service_role キーを環境変数から渡す（ファイルにも履歴にも残さない）
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')
GAS_URL = os.environ.get('GAS_URL')
GAS_SECRET = os.environ.get('GAS_SECRET', 'snowwe2024')
H = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
JST = datetime.timezone(datetime.timedelta(hours=9))

MEDIA_LABEL_TO_KEY = {
    'RDS': 'rds', 'ビズリーチ': 'bizreach', 'dodaX': 'dodax', 'doda X': 'dodax',
    'アンビ': 'ambi', 'AMBI': 'ambi', 'Green': 'green', 'グリーン': 'green', 'マイナビ': 'mynavi',
    # シートの表記は「Linkedin」、Supabase側は「linkedin」。この表にLinkedInが無く、
    # シートの表記がそのまま媒体キーになっていたため、大文字小文字が違うだけで
    # 別の媒体として扱われ、10件すべてが「記録漏れ100%」かつ「自動記録にあって
    # シートに無いもの10件」として両側に出ていた（実際は両方に同じ10件がある）
    'Linkedin': 'linkedin', 'LinkedIn': 'linkedin', 'リンクトイン': 'linkedin',
}
# 表記ゆれ（大文字小文字・前後の空白）で媒体キーが割れるのを防ぐ。
# 上の表に無い媒体も小文字に揃えてから突き合わせる
_MEDIA_NORM = {k.strip().lower(): v for k, v in MEDIA_LABEL_TO_KEY.items()}
KANJI_VARIANTS = {
    '鐵': '鉄', '廣': '広', '龍': '竜', '澤': '沢', '齋': '斎', '邊': '辺', '會': '会',
    # 大学名で実際に表記が割れるもの。「慶應義塾大学」と「慶応義塾大学」が
    # 別大学として扱われ、同じ人を結び付けられなくなっていた
    '應': '応', '學': '学', '國': '国', '藝': '芸', '豐': '豊', '壽': '寿',
    # 「野村証券」(シート) と「野村證券株式会社」(自動記録) が別会社として扱われていた
    '證': '証',
}

args = [a for a in sys.argv[1:] if not a.startswith('-')]
if len(args) >= 2:
    DAY_FROM, DAY_TO = args[0], args[1]
else:
    DAY_TO = datetime.date.today().isoformat()
    DAY_FROM = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()

if not GAS_URL:
    print('環境変数 GAS_URL が設定されていません。')
    sys.exit(1)


def describe_html(raw, status):
    """GASはエラーをHTMLのページで返す。タグを落として、画面に見える文字を出す"""
    title = re.search(r'<title[^>]*>(.*?)</title>', raw, re.S | re.I)
    visible = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', raw)
    visible = re.sub(r'<[^>]+>', ' ', visible)
    visible = re.sub(r'\s+', ' ', visible).strip()
    print(f'   HTTP {status}')
    if title:
        t = re.sub(r'\s+', ' ', title.group(1)).strip()[:200]
        print(f'   タイトル: {t}')
    print(f'   本文: {visible[:400] or "(表示される文字なし)"}')


def post_json(url, payload, timeout=340):
    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='POST', headers={})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8')
            status = resp.status
    except urllib.error.HTTPError as e:
        # 404はデプロイが見つからない（URLが古い・デプロイを消した・作り直した）。
        # 本文にGoogleの説明が入っていることがあるので、それも出す
        raw = ''
        try:
            raw = e.read().decode('utf-8', 'replace')
        except Exception:
            pass
        print(f'❌ GASがHTTP {e.code} を返しました。')
        if raw:
            describe_html(raw, e.code)
        if e.code == 404:
            print('   デプロイが見つかりません。考えられる原因:')
            print('   ・GASを再デプロイしてURLが変わった（環境変数GAS_URLが古い）')
            print('   ・デプロイを削除した／アーカイブした')
            print('   確認: Apps Script → デプロイ → デプロイを管理 → ウェブアプリのURL')
            print('   いまのGAS_URLの末尾: ...' + (url or '')[-12:])
        sys.exit(1)
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # GASはエラー時にHTMLのページを返す（権限切れ、実行時エラー、実行回数の
        # 上限など）。そのままJSONとして読もうとすると「Expecting value」で
        # 落ち、何が起きたのか分からないまま終わる。中身を見せる
        print('❌ GASがJSON以外を返しました。')
        describe_html(raw, status)
        if '<html' in raw.lower() or '<!doctype' in raw.lower():
            print('   HTMLが返っています。考えられる原因:')
            print('   ・GASのデプロイのアクセス権限が「全員」でなくなっている')
            print('   ・GAS側で実行時エラーが出ている（スクリプトエディタの実行ログを確認）')
            print('   ・1日の実行時間・呼び出し回数の上限に達した（時間をおいて再実行）')
        sys.exit(1)


def get_json(url, timeout=90):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        # 401はキーの問題。例外をそのまま出すと何が足りないのか分からず、
        # 実際にターミナルを開き直しただけで原因の切り分けに時間を使った
        if e.code in (401, 403):
            print('❌ Supabaseに拒否されました（HTTP %d）。' % e.code)
            print('   SUPABASE_KEY が設定されていないか、service_roleキーではありません。')
            print(f"   いまのキーの先頭: {SUPABASE_KEY[:14] or '(未設定)'}")
            print("   設定例: export SUPABASE_KEY='sb_secret_...'")
            sys.exit(1)
        raise


# 小書きのカナは表記が割れる。実データで「富士フィルム」(シート) と
# 「富士フイルム」(自動記録) が別会社として扱われていた
SMALL_KANA = str.maketrans('ァィゥェォャュョヮヵヶ', 'アイウエオヤユヨワカケ')


def norm(s):
    """会社名を比べるための正規化。法人格・記号・空白・旧字体・小書きカナ・
    よくある略称の違いを吸収する"""
    s = unicodedata.normalize('NFKC', str(s or '')).lower()
    for a, b in KANJI_VARIANTS.items():
        s = s.replace(a, b)
    # シートは略称で書かれることが多い。実データで「日清食品HD」と
    # 「日清食品ホールディングス株式会社…」が結び付かなかった。
    # 「日清食品hd」のように日本語に続くため \b は使えない（日本語も単語文字
    # として扱われ、境界にならない）。英数字が前後に無いことで判定する。
    # 小書きカナを揃える前に置き換える（置き換えた文字列も同じ正規化を通すため）
    s = re.sub(r'(?<![a-z0-9])hd(?![a-z0-9])', 'ホールディングス', s)
    s = s.translate(SMALL_KANA)
    s = re.sub(r'(株式会社|有限会社|合同会社|\(株\)|㈱)', '', s)
    s = re.sub(r'[・\s,、.。／/\-ー－&()（）]', '', s)
    return s.strip()


def company_match(a, b):
    """会社名が同じと言えるか。支店・事業部・役職が後ろに付く形があるため
    包含も認めるが、短い一致は別会社どうしを結び付ける（「三菱」で三菱商事と
    三菱電機が一致してしまう）。短い方が4文字以上のときだけ認める"""
    if not (a and b):
        return False
    if a == b:
        return True
    return min(len(a), len(b)) >= 4 and (a in b or b in a)


def norm_age(v):
    """年齢を比べるための正規化。シートは「35」「35歳」等の文字列、
    自動記録側は数値で入っている"""
    m = re.search(r'\d{1,3}', str(v or ''))
    return m.group(0) if m else ''


# 同じ人とみなす送信時刻の差。シートは手で書くため数分ずれることがある
WINDOW_SEC = 600


def is_date_only(g):
    """シートに送信時刻が無い行（LinkedIn など）。GAS が日付だけの行を
    12:00:00 にしているため、時刻での突き合わせができない"""
    if g.get('timeEstimated'):
        return True
    t = g['_t']
    return t.hour == 12 and t.minute == 0 and t.second == 0


def near(s, g):
    """自動記録 s とシート行 g が、時刻の上で同じ送信でありうるか。
    時刻の無いシート行は同じ日なら可とする（大学・会社などの一致を別に要求する）"""
    if is_date_only(g):
        # 後日入力の行は入力時刻が入っているため、シートのタブの日付で比べる
        wd = g.get('workDate') or g['_t'].date().isoformat()
        return s['_t'].date().isoformat() == wd
    return abs((s['_t'] - g['_t']).total_seconds()) <= WINDOW_SEC


def norm_univ(s):
    s = unicodedata.normalize('NFKC', str(s or '')).lower()
    for a, b in KANJI_VARIANTS.items():
        s = s.replace(a, b)
    s = re.sub(r'[・\s,、.。／/\-ー－&]', '', s)
    s = re.sub(r'(学部|研究科|専門職大学院).*$', '', s)
    # 1回だけだと「東京工業大学大学院」が「東京工業大学」までしか縮まらず、
    # 「東京工業大学」（→「東京工業」）と一致しない。変化しなくなるまで繰り返す
    while True:
        t = re.sub(r'(大学院|大学|大)$', '', s)
        if t == s:
            break
        s = t
    return s.strip()


fetch_from = (datetime.date.fromisoformat(DAY_FROM) - datetime.timedelta(days=1)).isoformat()

print(f'[1/2] GASから{fetch_from}以降を取得中...', flush=True)
gas = post_json(GAS_URL, {'secret': GAS_SECRET, 'action': 'getAllDailySheetHistory', 'since': fetch_from})
gas_by_key = defaultdict(list)
for r in gas.get('records', []):
    wd = r.get('workDate') or ''
    if wd < fetch_from or wd > DAY_TO or not r.get('date'):
        continue
    raw_media = (r.get('platform') or '').strip()
    pkey = _MEDIA_NORM.get(raw_media.lower(), raw_media.lower())
    who = r.get('recruiter') or '(空欄)'
    r['_t'] = datetime.datetime.fromtimestamp(r['date'] / 1000, tz=datetime.timezone.utc).astimezone(JST)
    gas_by_key[(who, pkey)].append(r)
print(f'  シート: {sum(len(v) for v in gas_by_key.values())}件', flush=True)

WITH_SYNC = '--with-sync' in sys.argv
# シートの写し（ext_version が空）を外し、拡張機能が書いた行だけと比べる
EXT_FILTER = '' if WITH_SYNC else '&ext_version=not.is.null'
print(f"[2/2] Supabaseから取得中...（{'写しも含む' if WITH_SYNC else '拡張機能の記録のみ'}）", flush=True)
end_excl = (datetime.date.fromisoformat(DAY_TO) + datetime.timedelta(days=1)).isoformat()
supa_rows = []
offset = 0
while True:
    page = get_json(
        # 年齢・ポジションを取っていなかったため、「年齢とポジション一致」の
        # 照合が一度も成立せず（両方とも常に空）、本来そこで結び付くはずの行が
        # 「時刻のみ」に落ちていた。中身を並べて出したときも、すべての行で
        # 「自動記録が取れていない」と表示され、記録側の不具合に見えていた
        f'{SUPABASE_URL}/rest/v1/scouts?select=platform,recruiter_name,company_name,'
        f'university,candidate_age,position_name,sent_at,ext_version'
        f'{EXT_FILTER}'
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
    supa_by_key[((s.get('recruiter_name') or '(空欄)'), (s.get('platform') or '').strip().lower())].append(s)
print(f'  Supabase: {len(supa_rows)}件\n', flush=True)

# 1件も読めていないのに集計に進むと、シートの全件が「漏れ」と表示され、
# 実態と正反対の結論になる。実際にそれで「100%漏れ」と誤認した
if not supa_rows:
    print('❌ Supabaseから1件も取得できませんでした。集計は行いません。')
    print('   SUPABASE_KEY が service_role キーか確認してください。')
    print('   publishableキーではRLSにより scouts を読めません。')
    print(f"   いまのキーの先頭: {SUPABASE_KEY[:14] or '(未設定)'}")
    sys.exit(1)

lo = datetime.datetime.fromisoformat(DAY_FROM).replace(tzinfo=JST)
hi = datetime.datetime.fromisoformat(DAY_TO).replace(tzinfo=JST) + datetime.timedelta(days=1)

print(f'=== 記録漏れの集計（{DAY_FROM}〜{DAY_TO}）===\n')
print(f'{"担当者":10s} {"媒体":12s} {"シート":>6s} {"確認済":>6s} {"未確認":>6s} {"漏れ":>5s} {"漏れ率":>7s}')
total_sheet = total_miss = 0
details = {}

# 媒体が空欄の行は最後に回す。シートは手入力なので媒体を書き忘れることがあり、
# その行を媒体ごとに突き合わせると必ず「漏れ」になる（実際に45件が誤検出された）。
# 媒体が分かっている行を先に消化し、残った自動記録と突き合わせる
used_ids = set()
# 突き合わせの質。本人確認できた分と、時刻が近いだけの分を分けて数える
match_how = {}
# 「時刻のみ」で結び付けた行の中身。どちらの値がどう違うのかを後で出す
timeonly_rows = []
# 本人確認できた組。項目ごとの一致を後で数える
pairs = []
# 担当者×媒体ごとの「時刻のみ」の件数
unconfirmed_by_key = {}
for key in sorted(set(gas_by_key) | set(supa_by_key), key=lambda k: (k[1] == '', k)):
    who, media = key
    gas_rows = sorted(gas_by_key.get(key, []), key=lambda x: x['_t'])
    if media == '':
        # 媒体を問わず、その担当者のまだ使われていない記録すべてを対象にする
        pool = [s for k, v in supa_by_key.items() if k[0] == who for s in v]
    else:
        pool = supa_by_key.get(key, [])
    unused = [s for s in pool if id(s) not in used_ids]
    miss = []
    for g in gas_rows:
        gu = norm_univ(g.get('univ'))
        gc = norm(g.get('company'))
        hit = None
        how = ''
        # 大学名か会社名が一致すれば、同じ人だと言える。
        # 大学名は前方一致を使わない。norm_univ が「大学」「大学院」を落とすため、
        # 前方一致にすると別の大学どうしが一致してしまう（実際に確認した）：
        #   東京大学(→東京) と 東京工業大学(→東京工業)
        #   日本大学(→日本) と 日本女子大学(→日本女子)
        #   関西大学(→関西) と 関西学院大学(→関西学院)
        # 「東京大学」と「東京大学大学院」はどちらも「東京」に揃うので、
        # 前方一致が無くても一致する。完全一致で足りる
        for s in unused:
            if not near(s, g):
                continue
            su = norm_univ(s.get('university'))
            if gu and su and gu == su:
                hit, how = s, '大学一致'
                break
        if not hit:
            for s in unused:
                if not near(s, g):
                    continue
                sc = norm(s.get('company_name'))
                if not (gc and sc):
                    continue
                # 会社名は支店・事業部が付く形があるため前方一致を残すが、
                # 短い前方一致は別会社どうしを結び付ける（「三菱」で三菱商事と
                # 三菱電機が一致してしまう）。短い方が4文字以上のときだけ認める
                # 以前は前方一致だけだったため、自動記録側の会社名の後ろに
                # 部署・役職が付いている行（「…ホールディングス株式会社食品
                # 開発部　課長」）が結び付かなかった
                # 時刻の無い行（LinkedIn）は会社名でしか結び付けられず、シートは
                # 「ソニー」のような短い略称で書かれる。同じ担当者・媒体・日に絞って
                # いるので、短くても片方がもう片方を含めば同じ人とみなす
                loose = is_date_only(g) and min(len(gc), len(sc)) >= 2 and (gc in sc or sc in gc)
                if company_match(gc, sc) or loose:
                    hit, how = s, '会社一致'
                    break
        # 大学も会社も取れていない（または崩れている）行が「時刻のみ」に落ちていた。
        # シートには年齢とポジションがあり、自動記録側にも両方ある。2つとも
        # 一致すれば、5分の窓の中では同じ人と見てよい（年齢だけ・ポジションだけ
        # では、同じ条件の候補者に連続送信したときに別人を結び付けうる）
        # シートの大学名は略称で書かれる（「市立」「電通」「つくば」）。
        # 完全一致では結び付かないが、片方がもう片方を含み、かつ会社名も
        # 一致するなら同じ人と見てよい。大学だけでの部分一致は別人を
        # 結び付けうるため認めない
        if not hit and gu and gc:
            for s in unused:
                if not near(s, g):
                    continue
                su, sc = norm_univ(s.get('university')), norm(s.get('company_name'))
                if not (su and sc):
                    continue
                if (gu in su or su in gu) and company_match(gc, sc):
                    hit, how = s, '大学(略称)と会社の一致'
                    break
        if not hit:
            ga, gp = norm_age(g.get('age')), norm(g.get('position'))
            if ga and gp:
                for s in unused:
                    if not near(s, g):
                        continue
                    sa, sp = norm_age(s.get('candidate_age')), norm(s.get('position_name'))
                    if sa and sp and ga == sa and gp == sp:
                        hit, how = s, '年齢とポジション一致'
                        break

        # どちらも一致しない場合は、時刻が近いというだけで結び付ける。
        # 別人を結び付けている可能性があるため、一致とは別に数える。
        # 以前はこれを区別せず「一致」に含めていたので、本人確認ができているのか
        # 時刻が近かっただけなのかが分からなかった
        if not hit and not is_date_only(g):
            best, best_gap = None, 181
            for s in unused:
                gap = abs((s['_t'] - g['_t']).total_seconds())
                if gap < best_gap:
                    best, best_gap = s, gap
            if best:
                hit, how = best, '時刻のみ'
        if hit:
            unused.remove(hit)
            used_ids.add(id(hit))
            if lo <= g['_t'] < hi:
                match_how[how] = match_how.get(how, 0) + 1
                if how != '時刻のみ':
                    pairs.append((who, media, g, hit))
                if how == '時刻のみ':
                    unconfirmed_by_key[key] = unconfirmed_by_key.get(key, 0) + 1
                    timeonly_rows.append((who, media, g, hit))
        elif lo <= g['_t'] < hi:
            miss.append(g)

    in_window = [g for g in gas_rows if lo <= g['_t'] < hi]
    if not in_window:
        continue
    total_sheet += len(in_window)
    total_miss += len(miss)
    rate = len(miss) / len(in_window) * 100
    mark = '  ⚠️' if rate >= 10 else ''
    # 「記録済」は本人確認できたものだけ。時刻が近いだけのものは別に数える。
    # 以前は両方を記録済に含めていたため、別人を結び付けていても気づけなかった
    unconf = unconfirmed_by_key.get(key, 0)
    print(f'{who:10s} {media or "(媒体未入力)":12s} {len(in_window):6d} '
          f'{len(in_window)-len(miss)-unconf:6d} {unconf:6d} {len(miss):5d} {rate:6.1f}%{mark}')
    if miss:
        details[key] = miss

print(f'\n合計: シート {total_sheet}件 / 漏れ {total_miss}件 ({total_miss/max(1,total_sheet)*100:.1f}%)')

# ── 突き合わせの質 ──
# 「一致した」の中身を分けて出す。大学名・会社名で本人確認できた分と、
# 時刻が近いというだけで結び付けた分では、意味がまったく違う。
# 以前は区別していなかったため、別人を結び付けていても気づけなかった
print('\n=== 突き合わせの質 ===')
matched_total = sum(match_how.values())
for how in ('大学一致', '会社一致', '大学(略称)と会社の一致', '年齢とポジション一致', '時刻のみ'):
    n = match_how.get(how, 0)
    if matched_total:
        print(f'  {how}: {n}件 ({n / matched_total * 100:.1f}%)')
if match_how.get('時刻のみ', 0):
    print('  ※「時刻のみ」は別人を結び付けている可能性があります。')
    print('    この分は「記録できている」と言い切れません。')

# 「時刻のみ」になった行は、シートと自動記録で大学も会社名も一致しなかったもの。
# 件数だけ出しても何を直せばよいか分からないため、両方の値を並べて出す。
# どちらが欠けているのか（取得できていない／表記が違う／別人）が一目で分かる
if timeonly_rows:
    print(f'\n=== 時刻のみで結び付けた {len(timeonly_rows)}件の中身 ===')
    print('   シート側 → 自動記録側 の順。値が違う項目が、直す対象です。')
    for who, media, g, s_row in timeonly_rows[:30]:
        print(f'\n  {g["_t"].strftime("%m/%d %H:%M")} {who} / {media or "(媒体未入力)"}')
        for label, gv, sv in (
            ('大学  ', g.get('university') or g.get('univ') or '', s_row.get('university') or ''),
            ('会社  ', g.get('company') or g.get('company_name') or '', s_row.get('company_name') or ''),
            ('年齢  ', g.get('age') or '', s_row.get('candidate_age') or ''),
            ('ポジション', g.get('position') or '', s_row.get('position_name') or ''),
        ):
            gv, sv = str(gv).strip(), str(sv).strip()
            if not gv and not sv:
                mark = '両方なし'
            elif not sv:
                mark = '← 自動記録が取れていない'
            elif not gv:
                mark = '← シートが空欄'
            elif norm(gv) == norm(sv):
                mark = '一致'
            else:
                mark = '← 食い違い'
            print(f'    {label} シート「{gv[:40] or "(空)"}」 / 自動記録「{sv[:40] or "(空)"}」 {mark}')
    if len(timeonly_rows) > 30:
        print(f'\n  （ほか {len(timeonly_rows)-30}件）')

# ── 項目ごとの一致 ──
# 漏れていないことに加えて、記録した中身がシートと同じかを確かめる。
# 大学・会社は表記ゆれ（略称・株式会社の有無）を一致とみなす


def field_verdict(kind, gv, sv):
    gv, sv = str(gv or '').strip(), str(sv or '').strip()
    if not gv and not sv:
        return '両方空'
    if not sv:
        return '記録が空'
    if not gv:
        return 'シート空'
    if kind == 'univ':
        a, b = norm_univ(gv), norm_univ(sv)
        ok = a == b or (min(len(a), len(b)) >= 2 and (a in b or b in a))
    elif kind == 'company':
        a, b = norm(gv), norm(sv)
        ok = company_match(a, b) or (min(len(a), len(b)) >= 2 and (a in b or b in a))
    elif kind == 'age':
        ok = norm_age(gv) == norm_age(sv)
    else:
        a, b = norm(gv), norm(sv)
        ok = a == b or (min(len(a), len(b)) >= 4 and (a in b or b in a))
    return '一致' if ok else '食い違い'


FIELDS = (('大学', 'univ', ('university', 'univ'), 'university'),
          ('会社', 'company', ('company', 'company_name'), 'company_name'),
          ('年齢', 'age', ('age',), 'candidate_age'),
          ('ポジション', 'position', ('position',), 'position_name'))
VERDICTS = ('一致', '食い違い', '記録が空', 'シート空', '両方空')
print(f'\n=== 記録の中身がシートと合っているか（本人確認できた {len(pairs)}件）===')
print('   「記録が空」「食い違い」が直す対象。「シート空」「両方空」は問題なし。')
by_media = defaultdict(list)
for p in pairs:
    by_media[p[1] or '(媒体未入力)'].append(p)
bad_rows = []
for media, ps in sorted(by_media.items()):
    gaps = sorted(abs((s['_t'] - g['_t']).total_seconds()) for _, _, g, s in ps if not is_date_only(g))
    gap_txt = (f'時刻差 中央{int(gaps[len(gaps)//2])}秒・最大{int(gaps[-1])}秒' if gaps
               else '時刻差 —（シートに時刻なし）')
    print(f'\n  {media}: {len(ps)}件  {gap_txt}')
    for label, kind, gkeys, skey in FIELDS:
        cnt = {v: 0 for v in VERDICTS}
        for who, _, g, s in ps:
            gv = next((g.get(k) for k in gkeys if g.get(k)), '')
            v = field_verdict(kind, gv, s.get(skey))
            cnt[v] += 1
            if v in ('食い違い', '記録が空'):
                bad_rows.append((who, media, label, v, g, gv, s.get(skey)))
        print(f'    {label:6s} ' + '  '.join(f'{v}{cnt[v]}' for v in VERDICTS if cnt[v]))
if bad_rows:
    print(f'\n  直す対象 {len(bad_rows)}項目（先頭40件）:')
    for who, media, label, v, g, gv, sv in sorted(bad_rows, key=lambda r: r[4]['_t'])[:40]:
        print(f"    {g['_t'].strftime('%m/%d %H:%M')} {who} / {media} {label} {v}: "
              f"シート「{str(gv or '')[:30] or '(空)'}」 / 記録「{str(sv or '')[:30] or '(空)'}」")

# ── 逆方向 ──
# シートに無いのに自動記録にあるもの。送っていないのに記録されていれば、
# 件数が水増しされる。これまで一度も測っていなかった。
# 手入力をやめる判断には、両方向が必要になる
extra = [s for s in supa_rows if id(s) not in used_ids and lo <= s['_t'] < hi]
print(f'\n=== 自動記録にあって、シートに無いもの: {len(extra)}件 ===')
if extra:
    by_who = {}
    for s in extra:
        k = (s.get('recruiter_name') or '(空欄)', s.get('platform') or '(なし)')
        by_who[k] = by_who.get(k, 0) + 1
    for (who, media), n in sorted(by_who.items(), key=lambda kv: -kv[1]):
        print(f'  {who} / {media}: {n}件')
    # 「シートに無い」と「突き合わせに失敗した」は別物。シートに行があっても、
    # 会社名や大学が合わなければ同じ1件が「漏れ」と「逆方向」の両方に出る。
    # 区別せずに「手入力漏れ」と読むと、こちらの抽出不良を相手のせいにしてしまう
    # （実際にその誤読をした）。近い時刻に未照合のシート行があるかを併せて出す
    all_miss = [g for rows in details.values() for g in rows]
    print('\n  内訳（先頭20件）:')
    for s in sorted(extra, key=lambda x: x['_t'])[:20]:
        who = s.get('recruiter_name') or ''
        near = [g for g in all_miss
                if (g.get('recruiter') or '') == who
                and abs((g['_t'] - s['_t']).total_seconds()) <= 600]
        if near:
            g = min(near, key=lambda x: abs((x['_t'] - s['_t']).total_seconds()))
            note = (f"  ← 同じ担当者の未照合のシート行が{int(abs((g['_t'] - s['_t']).total_seconds()))}秒差にあり"
                    f"（{g.get('company') or '会社名なし'}）。突き合わせ失敗の可能性")
        else:
            note = '  ← 近い時刻に未照合のシート行なし。シートへの未記入の可能性'
        print(f"    {s['_t'].strftime('%m/%d %H:%M')} {who or '(空欄)'} "
              f"/ {s.get('platform') or '(なし)'} / {s.get('company_name') or '(会社名なし)'}{note}")
    print('\n  「突き合わせ失敗の可能性」は、こちらの抽出が崩れていて同じ1件を')
    print('  結び付けられていないもの。会社名の取得を直す対象。')
    print('  「シートへの未記入の可能性」は、送信はしたがシートに書かれていないもの。')
    print('  ただし送信が確実と言えるのは通信を検知している媒体(rds/bizreach)だけで、')
    print('  doda X・Greenはボタン検知のため、送信の成立までは確認できない。')

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
