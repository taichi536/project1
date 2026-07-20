"""
arb_monitor.py ─ 取引所間アービトラージ検証モニター（ペーパー専用）
====================================================================
「取引所間の価格エラーを発見して稼ぐ」という主張を、実弾ゼロで検証する。

実行:
  python3 arb_monitor.py --minutes 60     # 60分間監視して自動終了
  python3 arb_monitor.py                  # Ctrl+C まで監視し続ける
  python3 arb_monitor.py --report         # 蓄積したログの集計レポート

【誠実仕様】
  1. 板の実勢（買値bid/売値ask）を使う。「安い所のask で買い、高い所のbid で売る」
  2. 往復の taker 手数料を差し引く（取引所ごとの実レート）
  3. レイテンシペナルティ: チャンス検出時ではなく「次の観測時点」の価格で
     約定したことにする（人間・自宅botが実際に動ける速度の現実）
  4. Binance は USDT建てなので USDT/USD レートで補正（無視すると偽の
     「価格エラー」が大量発生する、この種の主張の典型的なタネ）

【このモニターが無視している現実（結果を見る時に思い出すこと）】
  - 両取引所に事前に資金を置いておく必要がある（資金効率は半分以下）
  - 送金は10分〜数時間かかるので、残高リバランスのコストが別途かかる
  - 注文サイズが大きいと板を食って価格が滑る（ここでは少額を仮定）
  → つまりここで出る数字は実際より「甘い」。これで儲からなければ確定で無理。

※ 本ツールは検証記録用であり、投資助言ではない。実際の発注は一切しない。
"""

import argparse
import csv
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests

OUTPUT_DIR = "results"
SNAP_FILE = os.path.join(OUTPUT_DIR, "arb_snapshots.csv")
OPP_FILE = os.path.join(OUTPUT_DIR, "arb_opportunities.csv")

POLL_SEC = 10          # 観測間隔（秒）
NOTIONAL = 1000.0      # 仮定する取引額（USD）

# 個人がすぐ使える水準の taker 手数料（片道）
FEES = {
    "binance":  0.0010,
    "coinbase": 0.0060,
    "kraken":   0.0026,
    "bitstamp": 0.0040,
    "gemini":   0.0040,
}


# ── 各取引所の公開ティッカー（認証不要） ─────────────────────────────────────
def _get(url, **kw):
    r = requests.get(url, timeout=5, **kw)
    r.raise_for_status()
    return r.json()


def fetch_binance():
    d = _get("https://api.binance.com/api/v3/ticker/bookTicker",
             params={"symbol": "BTCUSDT"})
    return float(d["bidPrice"]), float(d["askPrice"]), "USDT"


def fetch_coinbase():
    d = _get("https://api.exchange.coinbase.com/products/BTC-USD/ticker")
    return float(d["bid"]), float(d["ask"]), "USD"


def fetch_kraken():
    d = _get("https://api.kraken.com/0/public/Ticker", params={"pair": "XBTUSD"})
    t = list(d["result"].values())[0]
    return float(t["b"][0]), float(t["a"][0]), "USD"


def fetch_bitstamp():
    d = _get("https://www.bitstamp.net/api/v2/ticker/btcusd/")
    return float(d["bid"]), float(d["ask"]), "USD"


def fetch_gemini():
    d = _get("https://api.gemini.com/v1/pubticker/btcusd")
    return float(d["bid"]), float(d["ask"]), "USD"


def fetch_usdt_rate():
    """USDT/USD レート（Kraken）。Binance の USDT建て価格を USD に補正する。"""
    try:
        d = _get("https://api.kraken.com/0/public/Ticker", params={"pair": "USDTZUSD"})
        t = list(d["result"].values())[0]
        return (float(t["b"][0]) + float(t["a"][0])) / 2
    except Exception:
        return 1.0


EXCHANGES = {
    "binance": fetch_binance,
    "coinbase": fetch_coinbase,
    "kraken": fetch_kraken,
    "bitstamp": fetch_bitstamp,
    "gemini": fetch_gemini,
}


# ── スナップショット取得 ─────────────────────────────────────────────────────
def take_snapshot() -> dict:
    """全取引所の bid/ask をUSD換算で返す。失敗した取引所は含めない。"""
    usdt = fetch_usdt_rate()
    quotes = {}
    with ThreadPoolExecutor(max_workers=len(EXCHANGES)) as ex:
        futs = {name: ex.submit(fn) for name, fn in EXCHANGES.items()}
        for name, fut in futs.items():
            try:
                bid, ask, ccy = fut.result()
                if ccy == "USDT":
                    bid, ask = bid * usdt, ask * usdt
                if 0 < bid < ask * 1.05:   # 異常値ガード
                    quotes[name] = {"bid": bid, "ask": ask}
            except Exception:
                pass
    return quotes


# ── 機会の計算 ───────────────────────────────────────────────────────────────
def find_best_opportunity(quotes: dict) -> dict | None:
    """
    「buy側のaskで買い、sell側のbidで売る」全ペアの中から、
    手数料控除後ネットが最大のものを返す。
    """
    best = None
    for buy_ex, bq in quotes.items():
        for sell_ex, sq in quotes.items():
            if buy_ex == sell_ex:
                continue
            gross = sq["bid"] / bq["ask"] - 1
            net = gross - FEES[buy_ex] - FEES[sell_ex]
            if best is None or net > best["net"]:
                best = {
                    "buy_ex": buy_ex, "sell_ex": sell_ex,
                    "buy_ask": bq["ask"], "sell_bid": sq["bid"],
                    "gross": gross, "net": net,
                }
    return best


def realized_net(opp: dict, next_quotes: dict) -> float | None:
    """
    レイテンシ考慮の実現損益: 検出時に発注しても約定は次の観測時点の
    価格になる、として同じペアの損益を再計算する。
    """
    bq = next_quotes.get(opp["buy_ex"])
    sq = next_quotes.get(opp["sell_ex"])
    if not bq or not sq:
        return None
    gross = sq["bid"] / bq["ask"] - 1
    return gross - FEES[opp["buy_ex"]] - FEES[opp["sell_ex"]]


# ── 監視ループ ───────────────────────────────────────────────────────────────
def run_monitor(minutes: float | None):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    snap_new = not os.path.exists(SNAP_FILE)
    opp_new = not os.path.exists(OPP_FILE)
    snap_f = open(SNAP_FILE, "a", newline="")
    opp_f = open(OPP_FILE, "a", newline="")
    snap_w = csv.writer(snap_f)
    opp_w = csv.writer(opp_f)
    if snap_new:
        snap_w.writerow(["時刻", "取引所数", "最良ペア", "グロス差(%)", "手数料後(%)"])
    if opp_new:
        opp_w.writerow(["検出時刻", "買い取引所", "売り取引所",
                        "検出時ネット(%)", f"{POLL_SEC}秒後の実現ネット(%)",
                        f"想定損益(USD, 元手{NOTIONAL:.0f}ドル)"])

    print(f"\n📡 5取引所のBTC価格を{POLL_SEC}秒間隔で監視します（ペーパー専用・発注なし）")
    print(f"   終了: {'約' + str(minutes) + '分後に自動終了' if minutes else 'Ctrl+C'}")
    print(f"   ログ: {SNAP_FILE} / {OPP_FILE}\n")

    deadline = time.time() + minutes * 60 if minutes else None
    pending = None       # 前回検出した機会（次の観測で実現損益を確定する）
    n_obs = n_opp = 0

    try:
        while deadline is None or time.time() < deadline:
            t0 = time.time()
            quotes = take_snapshot()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if len(quotes) >= 2:
                n_obs += 1
                best = find_best_opportunity(quotes)

                # 前回検出分の実現損益を確定
                if pending is not None:
                    rn = realized_net(pending, quotes)
                    rn_pct = f"{rn * 100:.4f}" if rn is not None else ""
                    pnl = f"{rn * NOTIONAL:.2f}" if rn is not None else ""
                    opp_w.writerow([pending["time"], pending["buy_ex"], pending["sell_ex"],
                                    f"{pending['net'] * 100:.4f}", rn_pct, pnl])
                    opp_f.flush()
                    pending = None

                snap_w.writerow([now, len(quotes), f"{best['buy_ex']}→{best['sell_ex']}",
                                 f"{best['gross'] * 100:.4f}", f"{best['net'] * 100:.4f}"])
                snap_f.flush()

                mark = ""
                if best["net"] > 0:
                    n_opp += 1
                    pending = {**best, "time": now}
                    mark = "  🚨 手数料後もプラスの機会！（次の観測で実現値を確定）"
                sys.stdout.write(
                    f"\r  [{now}] 観測{n_obs:4d}回  最良: {best['buy_ex']}→{best['sell_ex']} "
                    f"グロス{best['gross'] * 100:+.3f}% 手数料後{best['net'] * 100:+.3f}%"
                    f"  機会累計{n_opp}回{mark}   "
                )
                sys.stdout.flush()
            else:
                sys.stdout.write(f"\r  [{now}] 取得できた取引所が{len(quotes)}箇所（2未満）… ")
                sys.stdout.flush()

            time.sleep(max(0.5, POLL_SEC - (time.time() - t0)))
    except KeyboardInterrupt:
        pass
    finally:
        snap_f.close()
        opp_f.close()

    print(f"\n\n  監視終了。観測 {n_obs} 回、手数料後プラスの機会 {n_opp} 回。")
    print(f"  集計: python3 arb_monitor.py --report\n")


# ── レポート ─────────────────────────────────────────────────────────────────
def run_report():
    import pandas as pd
    if not os.path.exists(SNAP_FILE):
        print("\n❌ ログがありません。まず監視を実行してください。\n")
        return

    snaps = pd.read_csv(SNAP_FILE)
    print("\n" + "=" * 62)
    print("  📊 アービトラージ検証レポート")
    print("=" * 62)
    print(f"  観測回数:          {len(snaps):,} 回"
          f"（約{len(snaps) * POLL_SEC / 3600:.1f}時間分）")
    print(f"  グロス差の平均:    {snaps['グロス差(%)'].mean():+.4f}%")
    print(f"  グロス差の最大:    {snaps['グロス差(%)'].max():+.4f}%")
    print(f"  手数料後の平均:    {snaps['手数料後(%)'].mean():+.4f}%")
    print(f"  手数料後プラス率:  {(snaps['手数料後(%)'] > 0).mean() * 100:.2f}%")

    if os.path.exists(OPP_FILE):
        opps = pd.read_csv(OPP_FILE)
        if len(opps):
            det = opps.iloc[:, 3]
            rea = pd.to_numeric(opps.iloc[:, 4], errors="coerce")
            pnl = pd.to_numeric(opps.iloc[:, 5], errors="coerce")
            print(f"\n  ── 「機会」の追跡（検出 → {POLL_SEC}秒後に約定した場合）──")
            print(f"  検出された機会:      {len(opps)} 回")
            print(f"  検出時の平均ネット:  {det.mean():+.4f}%")
            print(f"  実現の平均ネット:    {rea.mean():+.4f}%  ← これが「取れた」数字")
            print(f"  実現もプラスだった率: {(rea > 0).mean() * 100:.1f}%")
            print(f"  想定損益の合計:      {pnl.sum():+.2f} USD（元手{NOTIONAL:.0f}ドル・全機会に参加）")
        else:
            print(f"\n  手数料後プラスの機会: 0 回")
    print()
    print("  💡 「検出時ネット」と「実現ネット」の差 = あなたが届く前に")
    print("     消えた分。実現ネットの平均がマイナスなら、この戦略は")
    print("     存在しない獲物を追いかける行為だと確定します。")
    print("  ⚠️  ここには送金コスト・資金拘束・スリッページは含まれていません。")
    print("     実際の成績はこの数字よりさらに悪化します。")
    print("=" * 62 + "\n")


def main():
    p = argparse.ArgumentParser(description="取引所間アービトラージ検証モニター（ペーパー専用）")
    p.add_argument("--minutes", type=float, default=None, help="監視時間（分）。省略でCtrl+Cまで")
    p.add_argument("--report", action="store_true", help="蓄積ログの集計レポート")
    args = p.parse_args()

    if args.report:
        run_report()
    else:
        run_monitor(args.minutes)


if __name__ == "__main__":
    main()
