"""
全担当者・全媒体について、シート(手入力)とSupabase(自動記録)を突き合わせ、
記録漏れを洗い出す。照合は「時刻の近さ＋大学名」を主軸にするため、
会社名の表記ゆれ(全角半角・旧字体・略称)の影響を受けない。読み取り専用。

拡張機能の接続切れ(Extension context invalidated)による漏れは、
「ある時点から連続して漏れる」形になるため、連続ブロックも検出して表示する。

実行:
  python3 audit_all_missing.py                      # 直近7日
  python3 audit_all_missing.py 2026-09-17 2026-09-18 # 期間指定
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
}
KANJI_VARIANTS = {
    '鐵': '鉄', '廣': '広', '龍': '竜', '澤': '沢', '齋': '斎', '邊': '辺', '會': '会',
    # 大学名で実際に表記が割れるもの。「慶應義塾大学」と「慶応義塾大学」が
    # 別大学として扱われ、同じ人を結び付けられなくなっていた
    '應': '応', '學': '学', '國': '国', '藝': '芸', '豐': '豊', '壽': '寿',
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


def post_json(url, payload, timeout=340):
    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='POST', headers={})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode('utf-8')
        return json.loads(raw) if raw.strip() else {}


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


def norm(s):
    """会社名を比べるための正規化。法人格・記号・空白・旧字体の違いを吸収する"""
    s = unicodedata.normalize('NFKC', str(s or '')).lower()
    for a, b in KANJI_VARIANTS.items():
        s = s.replace(a, b)
    s = re.sub(r'(株式会社|有限会社|合同会社|\(株\)|㈱)', '', s)
    s = re.sub(r'[・\s,、.。／/\-ー－&()（）]', '', s)
    return s.strip()


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
    pkey = MEDIA_LABEL_TO_KEY.get(r.get('platform', ''), r.get('platform', ''))
    who = r.get('recruiter') or '(空欄)'
    r['_t'] = datetime.datetime.fromtimestamp(r['date'] / 1000, tz=datetime.timezone.utc).astimezone(JST)
    gas_by_key[(who, pkey)].append(r)
print(f'  シート: {sum(len(v) for v in gas_by_key.values())}件', flush=True)

print(f'[2/2] Supabaseから取得中...', flush=True)
end_excl = (datetime.date.fromisoformat(DAY_TO) + datetime.timedelta(days=1)).isoformat()
supa_rows = []
offset = 0
while True:
    page = get_json(
        f'{SUPABASE_URL}/rest/v1/scouts?select=platform,recruiter_name,company_name,university,sent_at'
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
    supa_by_key[((s.get('recruiter_name') or '(空欄)'), s.get('platform') or '')].append(s)
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
            if abs((s['_t'] - g['_t']).total_seconds()) > 300:
                continue
            su = norm_univ(s.get('university'))
            if gu and su and gu == su:
                hit, how = s, '大学一致'
                break
        if not hit:
            for s in unused:
                if abs((s['_t'] - g['_t']).total_seconds()) > 300:
                    continue
                sc = norm(s.get('company_name'))
                if not (gc and sc):
                    continue
                # 会社名は支店・事業部が付く形があるため前方一致を残すが、
                # 短い前方一致は別会社どうしを結び付ける（「三菱」で三菱商事と
                # 三菱電機が一致してしまう）。短い方が4文字以上のときだけ認める
                if gc == sc or (min(len(gc), len(sc)) >= 4
                                and (gc.startswith(sc) or sc.startswith(gc))):
                    hit, how = s, '会社一致'
                    break
        # どちらも一致しない場合は、時刻が近いというだけで結び付ける。
        # 別人を結び付けている可能性があるため、一致とは別に数える。
        # 以前はこれを区別せず「一致」に含めていたので、本人確認ができているのか
        # 時刻が近かっただけなのかが分からなかった
        if not hit:
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
                if how == '時刻のみ':
                    unconfirmed_by_key[key] = unconfirmed_by_key.get(key, 0) + 1
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
for how in ('大学一致', '会社一致', '時刻のみ'):
    n = match_how.get(how, 0)
    if matched_total:
        print(f'  {how}: {n}件 ({n / matched_total * 100:.1f}%)')
if match_how.get('時刻のみ', 0):
    print('  ※「時刻のみ」は別人を結び付けている可能性があります。')
    print('    この分は「記録できている」と言い切れません。')

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
    print('\n  内訳（先頭20件）:')
    for s in sorted(extra, key=lambda x: x['_t'])[:20]:
        print(f"    {s['_t'].strftime('%m/%d %H:%M')} {s.get('recruiter_name') or '(空欄)'} "
              f"/ {s.get('platform') or '(なし)'} / {s.get('company_name') or '(会社名なし)'}")
    print('\n  手入力の書き漏れであれば問題ありませんが、送っていない記録が')
    print('  含まれていれば、件数が水増しされています。')

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
