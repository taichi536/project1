#!/usr/bin/env python3
"""記事テーマの優先順位づけと、リライト候補の抽出を行うスクリプト。

使い方:
  python3 seo/prioritize.py plan [--hours 8] [--months 3] [--assume-volume N]
      seo/keywords.csv から、限られた確認工数で「期待相談件数」が最大になる
      記事の組み合わせを選び、月ごとの計画を seo/plan.md に書き出す。

  python3 seo/prioritize.py rewrite <Search Console のエクスポートCSV>
      Search Console の「検索パフォーマンス」→「エクスポート」→「CSV をダウンロード」で
      得たクエリ別（またはページ別）のCSVから、少し直せば順位・クリックが伸びやすい
      項目を並べる。

考え方（plan）:
  テーマの価値 = 月間検索数 × 上位に入れる確率 × その順位でのクリック率 × 相談に進む率
  を「期待相談件数/月」として見積もり、月の確認工数の範囲で合計が最大になるよう
  0/1 ナップサック問題として解く。まとめ記事（pillar）を書かないと個別記事（child）は
  書けない、という順序の制約があるため、クラスタごとに「pillar ＋ child の組み合わせ」を
  選ぶ多肢選択ナップサックとして厳密に解いている。

下の係数はすべて仮置きの目安です。公開後の実データで見直してください。
"""
import argparse
import csv
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))

# 順位ごとのクリック率の目安（Google のオーガニック検索の一般的な傾向）
CTR_BY_POSITION = {1: .28, 2: .15, 3: .11, 4: .08, 5: .07, 6: .05, 7: .04, 8: .03, 9: .025, 10: .02}
CTR_BEYOND_10 = .01

# 競合の強さ → (上位に入れたときに狙える順位, そこまで上がれる確率)
DIFFICULTY = {'低': (3, .6), '中': (6, .35), '高': (12, .1)}

# 転職意欲の強さ（1〜3）→ クリックした人が相談に進む率
CVR_BY_INTENT = {1: .005, 2: .015, 3: .03}

# 工数は 0.5 時間単位で扱う
UNIT = 2


def ctr(position):
    return CTR_BY_POSITION.get(round(position), CTR_BEYOND_10) if position <= 10 else CTR_BEYOND_10


def expected_leads(row, volume):
    pos, prob = DIFFICULTY[row['difficulty']]
    return volume * prob * ctr(pos) * CVR_BY_INTENT[int(row['intent'])]


def load_keywords(path):
    with open(path, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def knapsack(items, capacity):
    """0/1 ナップサック。items は (工数単位, 価値, 項目) のリスト。
    容量ごとの最大価値と、そのときの選択を返す。"""
    best = [(0.0, [])] * (capacity + 1)
    for cost, value, item in items:
        nxt = best[:]
        for c in range(cost, capacity + 1):
            v, chosen = best[c - cost]
            if v + value > nxt[c][0]:
                nxt[c] = (v + value, chosen + [item])
        best = nxt
    # 容量「以下」で最大になるように単調化
    for c in range(1, capacity + 1):
        if best[c - 1][0] > best[c][0]:
            best[c] = best[c - 1]
    return best


def plan(args):
    rows = load_keywords(os.path.join(HERE, 'keywords.csv'))
    missing = []
    clusters = defaultdict(lambda: {'pillar': None, 'children': []})
    for r in rows:
        vol = r['monthly_volume'].strip()
        if vol:
            volume = float(vol.replace(',', ''))
        elif args.assume_volume is not None:
            volume = args.assume_volume
        else:
            missing.append(r['keyword'])
            continue
        r['_value'] = expected_leads(r, volume)
        r['_cost'] = max(1, round(float(r['review_hours']) * UNIT))
        r['_volume'] = volume
        c = clusters[r['cluster']]
        if r['role'] == 'pillar':
            c['pillar'] = r
        else:
            c['children'].append(r)

    if missing:
        print(f'※ 月間検索数が空欄の {len(missing)} 件は計算から外しました（--assume-volume で仮の値を入れられます）。', file=sys.stderr)

    capacity = int(args.hours * args.months * UNIT)

    # クラスタごとに「予算 b を使ったときの最大価値と選択」を作る（多肢選択ナップサックの選択肢）
    options = []
    for name, c in clusters.items():
        pillar = c['pillar']
        children = [ch for ch in c['children'] if ch['status'] != '公開済み']
        if pillar is None:
            # まとめ記事の検索数が未入力のクラスタは、個別記事だけでは選ばない
            continue
        if pillar['status'] == '公開済み':
            base_cost, base_value, base = 0, 0.0, []
        else:
            base_cost, base_value, base = pillar['_cost'], pillar['_value'], [pillar]
        if base_cost > capacity:
            continue
        inner = knapsack([(ch['_cost'], ch['_value'], ch) for ch in children], capacity - base_cost)
        table = {}
        for b in range(base_cost, capacity + 1):
            v, chosen = inner[b - base_cost]
            table[b] = (base_value + v, base + chosen)
        options.append(table)

    # 外側：各クラスタにいくら予算を配るか
    best = [(0.0, [])] * (capacity + 1)
    for table in options:
        nxt = best[:]
        for c in range(capacity + 1):
            for b, (v, chosen) in table.items():
                if b > c or not chosen:
                    continue
                pv, pchosen = best[c - b]
                if pv + v > nxt[c][0]:
                    nxt[c] = (pv + v, pchosen + chosen)
        best = nxt
    total, selected = max(best, key=lambda x: x[0])

    # 月ごとに割り振る：まとめ記事を先に、あとは工数あたりの価値が高い順
    selected.sort(key=lambda r: (r['role'] != 'pillar', -r['_value'] / r['_cost']))
    monthly = int(args.hours * UNIT)
    months = [[] for _ in range(args.months)]
    used = [0] * args.months
    placed_pillars = {}
    pending_pillars = {r['cluster'] for r in selected if r['role'] == 'pillar'}
    unassigned = []
    for r in selected:
        earliest = 0
        if r['role'] == 'child' and r['cluster'] in pending_pillars:
            if r['cluster'] not in placed_pillars:
                unassigned.append(r)  # まとめ記事が月に収まらなかった
                continue
            earliest = placed_pillars[r['cluster']]
        for m in range(earliest, args.months):
            if used[m] + r['_cost'] <= monthly:
                months[m].append(r)
                used[m] += r['_cost']
                if r['role'] == 'pillar':
                    placed_pillars[r['cluster']] = m
                break
        else:
            unassigned.append(r)

    lines = ['# 記事計画（自動生成）', '',
             f'条件：確認工数 月{args.hours}時間 × {args.months}か月。'
             f'期待相談件数の合計（公開後に上位表示できた場合の月あたりの見込み）：**{total:.2f}件/月**', '',
             '※ 係数は仮置きの目安です（seo/prioritize.py の冒頭）。検索数が空欄のテーマは含まれていません。', '']
    for m, items in enumerate(months, 1):
        lines += [f'## {m}か月目（{used[m - 1] / UNIT:g}時間）', '',
                  '| 種類 | 検索語 | クラスタ | 月間検索数 | 競合 | 意欲 | 期待相談件数/月 | 工数(h) |',
                  '|---|---|---|---|---|---|---|---|']
        for r in items:
            kind = 'まとめ' if r['role'] == 'pillar' else '個別'
            lines.append(f"| {kind} | {r['keyword']} | {r['cluster']} | {r['_volume']:g} | {r['difficulty']} | "
                         f"{r['intent']} | {r['_value']:.3f} | {r['_cost'] / UNIT:g} |")
        lines.append('')
    if unassigned:
        lines += ['## 月の枠に収まらなかったテーマ（次の計画で優先）', ''] + [f"- {r['keyword']}" for r in unassigned] + ['']
    if missing:
        lines += ['## 検索数が未入力のテーマ', ''] + [f'- {k}' for k in missing] + ['']
    out = os.path.join(HERE, 'plan.md')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('\n'.join(lines))
    print(f'\n→ {os.path.relpath(out)} に書き出しました。', file=sys.stderr)


def parse_number(text):
    text = (text or '').strip().replace(',', '')
    if text.endswith('%'):
        return float(text[:-1]) / 100
    return float(text) if text else 0.0


def rewrite(args):
    with open(args.csv, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit('CSV が空です。')
    cols = rows[0].keys()

    def pick(*names):
        for n in names:
            if n in cols:
                return n
        sys.exit(f'列が見つかりません: {names}（見つかった列: {list(cols)}）')

    key = pick('上位のクエリ', '上位のページ', 'Top queries', 'Top pages', 'クエリ', 'ページ')
    imp = pick('表示回数', 'Impressions')
    clk = pick('クリック数', 'Clicks')
    pos = pick('掲載順位', 'Position')

    results = []
    for r in rows:
        impressions, clicks, position = parse_number(r[imp]), parse_number(r[clk]), parse_number(r[pos])
        if not (4 <= position <= 20) or impressions < args.min_impressions:
            continue
        # 3位まで上げられたときに増えるクリック数の見込み
        gain = impressions * max(0.0, ctr(3) - clicks / impressions if impressions else 0.0)
        results.append((gain, r[key], impressions, clicks, position))
    results.sort(reverse=True)
    print('| 対象 | 表示回数 | クリック数 | 平均順位 | 3位に上がった場合の追加クリック見込み |')
    print('|---|---|---|---|---|')
    for gain, name, impressions, clicks, position in results[:args.top]:
        print(f'| {name} | {impressions:g} | {clicks:g} | {position:.1f} | +{gain:.1f} |')
    if not results:
        print('（平均順位4〜20位で、表示回数が条件を満たす項目はありませんでした）')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    pp = sub.add_parser('plan', help='記事計画を作る')
    pp.add_argument('--hours', type=float, default=8, help='1か月に使える確認工数（時間）')
    pp.add_argument('--months', type=int, default=3, help='計画する月数')
    pp.add_argument('--assume-volume', type=float, help='検索数が空欄のテーマに仮で入れる月間検索数')
    pp.set_defaults(func=plan)
    pr = sub.add_parser('rewrite', help='リライト候補を出す')
    pr.add_argument('csv', help='Search Console からエクスポートした CSV')
    pr.add_argument('--min-impressions', type=float, default=20, help='対象にする最低表示回数')
    pr.add_argument('--top', type=int, default=15, help='表示する件数')
    pr.set_defaults(func=rewrite)
    args = p.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
