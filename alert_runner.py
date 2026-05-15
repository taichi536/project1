"""
定期アラート実行スクリプト

【使い方】
  python alert_runner.py               # 1回だけ実行して終了
  python alert_runner.py --loop 60     # 60分ごとに自動チェック（起動しっぱなし）

【通知されるタイミング】
  - シグナルが変化したとき（例: 様子見 → 買い）
  - スコア+4以上の強い買いシグナルが出たとき
  - 損切りラインに近づいたとき

【環境変数の設定例（.envファイルまたはターミナルで設定）】
  TELEGRAM_BOT_TOKEN=1234567890:ABCdef...
  TELEGRAM_CHAT_ID=123456789
  WATCH_TICKERS=7203,9984,6758,AAPL,MSFT
"""

import argparse
import json
import time
import os
from pathlib import Path
from datetime import datetime
from modules.data_fetcher import fetch_ohlcv, fetch_earnings_date
from modules.technical import compute_all
from modules.signals import evaluate_signals, overall_signal
from modules.notifier import send_signal_alert, send_screening_alert, send_stop_loss_alert, send_strong_buy_alert, send_strong_sell_alert
from modules.screening import screen_single
from modules.diary import get_trades, calc_pnl
from modules.dashboard import load_watchlist

# ── 設定 ──────────────────────────────────────────────────────────────────────
# 環境変数 WATCH_TICKERS が未設定なら watchlist.json を使う
_env_tickers = os.getenv("WATCH_TICKERS", "")
WATCH_TICKERS = [t.strip() for t in _env_tickers.split(",") if t.strip()] if _env_tickers else load_watchlist()

SIGNAL_THRESHOLD = int(os.getenv("SIGNAL_THRESHOLD", "3"))  # スコアの絶対値がこれ以上で通知
STOP_LOSS_MARGIN = float(os.getenv("STOP_LOSS_MARGIN", "1.03"))  # 損切りラインの3%以内で警告

# シグナル履歴ファイル（同じシグナルが続いても重複通知しないために使う）
_STATE_FILE = Path(__file__).parent / ".alert_state.json"


def _load_state() -> dict:
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_state(state: dict):
    _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False))


def run_signal_alerts(tickers: list[str] | None = None):
    targets = tickers or WATCH_TICKERS
    print(f"[シグナル監視] 対象: {targets}")
    state = _load_state()
    signals_state = state.get("signals", {})

    for ticker in targets:
        ticker = ticker.strip()
        try:
            df = fetch_ohlcv(ticker, period="6mo")
            df = compute_all(df)
            sigs = evaluate_signals(df)
            verdict, score = overall_signal(sigs, df=df)
            price = float(df["Close"].iloc[-1])
            rsi = float(df["RSI"].dropna().iloc[-1]) if "RSI" in df.columns and len(df["RSI"].dropna()) > 0 else None
            atr = float(df["ATR"].dropna().iloc[-1]) if "ATR" in df.columns and len(df["ATR"].dropna()) > 0 else None

            prev_verdict = signals_state.get(ticker, {}).get("verdict")
            changed = prev_verdict is not None and prev_verdict != verdict

            print(f"  {ticker}: {verdict} (score={score:+d}, 前回={prev_verdict or '初回'})")

            should_notify = False
            today = datetime.now().strftime("%Y-%m-%d")
            # 1) シグナルが変わって「買い」or「売り」になった
            if changed and verdict in ("買い", "売り"):
                should_notify = True
            # 2) 強い買いシグナル（スコア+4以上）は1日1回制限で通知
            elif verdict == "買い" and score >= 4:
                last_strong = signals_state.get(ticker, {}).get("last_strong_buy_date")
                if last_strong != today:
                    should_notify = True
                    signals_state.setdefault(ticker, {})["last_strong_buy_date"] = today
            # 3) 強い売りシグナル（スコア-4以下）は1日1回制限で通知
            elif verdict == "売り" and score <= -4:
                last_strong_sell = signals_state.get(ticker, {}).get("last_strong_sell_date")
                if last_strong_sell != today:
                    should_notify = True
                    signals_state.setdefault(ticker, {})["last_strong_sell_date"] = today

            if should_notify:
                if verdict == "買い" and score >= 4:
                    reasons = [s["判定"] for s in sorted(sigs, key=lambda x: abs(x["スコア"]), reverse=True)[:3]]
                    ed_days = None
                    try:
                        ed_days = fetch_earnings_date(ticker).get("days_until")
                    except Exception:
                        pass
                    from modules.risk_filter import assess_signal_risk
                    risk = assess_signal_risk(ticker, df, earnings_days=ed_days)
                    print(f"    リスク: {risk['risk_level']} (score={risk['risk_score']}) {risk['reasons']}")
                    if risk["should_skip"]:
                        print(f"    → リスクフィルターによりスキップ: {ticker}")
                        signals_state[ticker] = {
                            **signals_state.get(ticker, {}),
                            "verdict": verdict,
                            "score": score,
                            "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        }
                        continue
                    entry_limit_pct = risk.get("entry_limit_pct", 0)
                    entry_limit = price * (1 + entry_limit_pct / 100) if entry_limit_pct > 0 else None
                    result = send_strong_buy_alert(
                        ticker=ticker,
                        price=price,
                        score=score,
                        reasons=reasons,
                        stop_loss=price * 0.95,
                        target=price * 1.10,
                        rsi=rsi,
                        earnings_days=ed_days,
                        entry_limit=entry_limit,
                    )
                elif verdict == "売り" and score <= -4:
                    reasons = [s["判定"] for s in sorted(sigs, key=lambda x: abs(x["スコア"]), reverse=True)[:3]]
                    ed_days = None
                    try:
                        ed_days = fetch_earnings_date(ticker).get("days_until")
                    except Exception:
                        pass
                    result = send_strong_sell_alert(
                        ticker=ticker,
                        price=price,
                        score=score,
                        reasons=reasons,
                        stop_loss=price * 1.05,
                        target=price * 0.90,
                        rsi=rsi,
                        earnings_days=ed_days,
                    )
                else:
                    result = send_signal_alert(
                        ticker=ticker,
                        verdict=verdict,
                        score=score,
                        price=price,
                        signals=sigs,
                        rsi=rsi,
                        atr=atr,
                    )
                print(f"    → 通知送信: {result}")
            else:
                print(f"    → シグナル変化なし、通知スキップ")

            # 状態を保存
            signals_state[ticker] = {
                **signals_state.get(ticker, {}),
                "verdict": verdict,
                "score": score,
                "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }

        except Exception as e:
            print(f"  {ticker}: エラー - {e}")

    state["signals"] = signals_state
    _save_state(state)


def run_stop_loss_check():
    print("[損切り監視] 保有ポジションを確認中...")
    trades_df = get_trades(limit=10000)
    pnl_data = calc_pnl(trades_df)
    positions = pnl_data["positions"]

    if not positions:
        print("  保有ポジションなし")
        return

    stop_map = {}
    if not trades_df.empty:
        buys = trades_df[trades_df["action"] == "買い"]
        for _, row in buys.iterrows():
            t = row["ticker"]
            if row.get("stop_loss") and float(row["stop_loss"]) > 0:
                stop_map[t] = float(row["stop_loss"])

    state = _load_state()
    notified_stops = state.get("notified_stops", {})
    today = datetime.now().strftime("%Y-%m-%d")

    for ticker in positions:
        try:
            df = fetch_ohlcv(ticker, period="5d")
            current = float(df["Close"].iloc[-1])
            stop = stop_map.get(ticker)

            if stop and current <= stop * STOP_LOSS_MARGIN:
                # 同じ日に複数回通知しない
                if notified_stops.get(ticker) != today:
                    print(f"  ⚠️ {ticker}: 現在値 {current:.2f} が損切りライン {stop:.2f} に接近！")
                    send_stop_loss_alert(ticker, current, stop)
                    notified_stops[ticker] = today
                else:
                    print(f"  {ticker}: 損切り接近（本日通知済み）")
            else:
                print(f"  {ticker}: 現在値 {current:.2f} / 損切り {stop or '未設定'} → 問題なし")
        except Exception as e:
            print(f"  {ticker}: エラー - {e}")

    state["notified_stops"] = notified_stops
    _save_state(state)


def run_screening_alerts(tickers: list[str] | None = None):
    targets = tickers or WATCH_TICKERS
    print(f"[スクリーニング] 対象: {targets}")
    passed = []
    for ticker in targets:
        ticker = ticker.strip()
        try:
            result = screen_single(ticker)
            status = "合格 ✅" if result["合否"] else "不合格"
            print(f"  {ticker}: {status}")
            if result["合否"]:
                passed.append(ticker)
        except Exception as e:
            print(f"  {ticker}: エラー - {e}")

    if passed:
        send_screening_alert(passed)
        print(f"  → スクリーニング通知送信: {passed}")
    else:
        print("  → 合格銘柄なし、通知なし")


def main():
    parser = argparse.ArgumentParser(description="株式アラートランナー")
    parser.add_argument("--mode", choices=["all", "signal", "stoploss", "screening"],
                        default="all")
    parser.add_argument("--loop", type=int, default=0,
                        help="繰り返し間隔（分）。省略か0で1回のみ実行")
    parser.add_argument("--tickers", type=str, default="",
                        help="対象銘柄をカンマ区切りで指定（省略時はwatchlist.jsonを使用）")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()] if args.tickers else None

    def run_once():
        print(f"\n{'='*50}")
        print(f"チェック開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        tg = bool(os.getenv("TELEGRAM_BOT_TOKEN"))
        sl = bool(os.getenv("SLACK_WEBHOOK_URL"))
        print(f"通知先: Telegram={'✅' if tg else '❌未設定'} / Slack={'✅' if sl else '❌未設定'}")
        print(f"{'='*50}")

        if not tg and not sl:
            print("⚠️ 警告: TELEGRAM_BOT_TOKEN または SLACK_WEBHOOK_URL が設定されていません。")
            print("   通知は届きません。環境変数を設定してください。")

        if args.mode in ("all", "signal"):
            run_signal_alerts(tickers)
        if args.mode in ("all", "stoploss"):
            run_stop_loss_check()
        if args.mode in ("all", "screening"):
            run_screening_alerts(tickers)

        print(f"\n次回チェック: {args.loop}分後" if args.loop > 0 else "\n完了")

    run_once()

    if args.loop > 0:
        print(f"\n{args.loop}分ごとに自動チェックします（止めるには Ctrl+C）")
        while True:
            time.sleep(args.loop * 60)
            run_once()


if __name__ == "__main__":
    main()
