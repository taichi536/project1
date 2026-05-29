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
from datetime import datetime, date
from dotenv import load_dotenv
load_dotenv()
from modules.data_fetcher import fetch_ohlcv, fetch_earnings_date
from modules.technical import compute_all
from modules.signals import evaluate_signals, overall_signal
from modules.notifier import send_signal_alert, send_screening_alert, send_stop_loss_alert, send_strong_buy_alert, send_strong_sell_alert, send_momentum_rebalance_alert
from modules.screening import screen_single
from modules.diary import get_trades, calc_pnl
from modules.dashboard import load_watchlist
from modules.auto_trade import AutoTrader
from modules.auto_watchlist import run_auto_watchlist
from modules.signal_tracker import record_signal, update_results

_trader = AutoTrader()


def is_trading_day(check_date: date | None = None) -> bool:
    """
    日本株の取引日かどうかを判定する。
    土日は確実にFalse。祝日は fetch_ohlcv で直近データの日付を確認して判定。
    """
    d = check_date or date.today()
    if d.weekday() >= 5:  # 土(5)・日(6)
        return False
    # 直近の取引日付を確認（祝日・年末年始は直近データが古い）
    try:
        from modules.data_fetcher import fetch_ohlcv
        df = fetch_ohlcv("7203", period="5d")  # トヨタで代表確認
        if df.empty:
            return False
        last_date = df.index[-1].date() if hasattr(df.index[-1], "date") else df.index[-1]
        # 直近データが2営業日以上前なら今日は休場
        from pandas.tseries.offsets import BDay
        import pandas as pd
        cutoff = (pd.Timestamp(d) - BDay(2)).date()
        return last_date >= cutoff
    except Exception:
        return True  # 確認できない場合は実行する


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
            df = fetch_ohlcv(ticker, period="2y")
            df = compute_all(df)
            sigs = evaluate_signals(df)
            verdict, score = overall_signal(sigs, df=df)

            # 1時間足で短期エントリータイミングを確認
            if verdict == "買い":
                try:
                    from modules.signals import multi_timeframe_signal
                    tf_results = multi_timeframe_signal(ticker)
                    h1 = next((r for r in tf_results if "1時間" in r["timeframe"]), None)
                    if h1 and h1["verdict"] == "売り":
                        print(f"    ⚠️ 1時間足が売りシグナル → 短期では下落圧力あり（日足シグナルは維持）")
                except Exception:
                    pass
            price = float(df["Close"].iloc[-1])
            rsi = float(df["RSI"].dropna().iloc[-1]) if "RSI" in df.columns and len(df["RSI"].dropna()) > 0 else None
            atr = float(df["ATR"].dropna().iloc[-1]) if "ATR" in df.columns and len(df["ATR"].dropna()) > 0 else None

            prev_verdict = signals_state.get(ticker, {}).get("verdict")
            changed = prev_verdict is not None and prev_verdict != verdict

            print(f"  {ticker}: {verdict} (score={score:+d}, 前回={prev_verdict or '初回'})")

            should_notify = False
            today = datetime.now().strftime("%Y-%m-%d")
            prev_score = signals_state.get(ticker, {}).get("score", 0)
            score_delta = abs(score - prev_score)

            # 1) シグナルが変わって「買い」or「売り」になった
            if changed and verdict in ("買い", "売り"):
                should_notify = True
            # 2) 強い買いシグナル（スコア+4以上）は1日1回制限。ただしスコアが2以上悪化→改善した場合は再通知
            elif verdict == "買い" and score >= 4:
                last_strong = signals_state.get(ticker, {}).get("last_strong_buy_date")
                last_notified_score = signals_state.get(ticker, {}).get("last_notified_score", 0)
                if last_strong != today or abs(score - last_notified_score) >= 2:
                    should_notify = True
                    signals_state.setdefault(ticker, {})["last_strong_buy_date"] = today
                    signals_state.setdefault(ticker, {})["last_notified_score"] = score
            # 3) 強い売りシグナル（スコア-4以下）は1日1回制限。ただしスコアが2以上急落した場合は再通知
            elif verdict == "売り" and score <= -4:
                last_strong_sell = signals_state.get(ticker, {}).get("last_strong_sell_date")
                last_notified_score = signals_state.get(ticker, {}).get("last_notified_score", 0)
                if last_strong_sell != today or abs(score - last_notified_score) >= 2:
                    should_notify = True
                    signals_state.setdefault(ticker, {})["last_strong_sell_date"] = today
                    signals_state.setdefault(ticker, {})["last_notified_score"] = score

            if should_notify:
                # シグナル精度トラッキングに記録
                if verdict in ("買い", "売り"):
                    record_signal(ticker, verdict, score, price)

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

                # 自動売買（有効な場合のみ）
                if _trader.is_enabled():
                    trade_result = _trader.execute_signal(
                        ticker=ticker,
                        verdict=verdict,
                        score=score,
                        price=price,
                        atr=atr,
                        stop_loss=price * 0.95 if verdict == "買い" else None,
                    )
                    if trade_result:
                        print(f"    → 自動売買: {trade_result.get('status')} {trade_result.get('message', '')}")
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
                if notified_stops.get(ticker) != today:
                    print(f"  ⚠️ {ticker}: 現在値 {current:.2f} が損切りライン {stop:.2f} に接近！")
                    send_stop_loss_alert(ticker, current, stop)
                    notified_stops[ticker] = today
                    # 自動売買が有効なら損切りを実行
                    if _trader.is_enabled():
                        trade_result = _trader._execute_sell(ticker, current, reason=f"損切りライン到達({stop:.2f})")
                        print(f"    → 自動損切り: {trade_result.get('status')} {trade_result.get('message', '')}")
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


_MOMENTUM_HOLDINGS_FILE = Path(__file__).parent / ".momentum_holdings.json"
_MOMENTUM_STOP_LOSS_PCT = float(os.getenv("MOMENTUM_STOP_LOSS_PCT", "10.0"))  # 買値から-X%で損切り
_MOMENTUM_ENTRY_FILE = Path(__file__).parent / ".momentum_entries.json"  # 買値記録


def _load_momentum_holdings() -> list:
    if _MOMENTUM_HOLDINGS_FILE.exists():
        try:
            return json.loads(_MOMENTUM_HOLDINGS_FILE.read_text())
        except Exception:
            pass
    return []


def _load_momentum_entries() -> dict:
    if _MOMENTUM_ENTRY_FILE.exists():
        try:
            return json.loads(_MOMENTUM_ENTRY_FILE.read_text())
        except Exception:
            pass
    return {}


def run_momentum_stop_loss():
    """モメンタム保有銘柄の損切り・緊急撤退監視（毎日実行）"""
    from modules.notifier import send_momentum_rebalance_alert

    holdings = _load_momentum_holdings()
    if not holdings:
        print("[モメンタム監視] 保有銘柄なし、スキップ")
        return

    print(f"[モメンタム監視] 保有銘柄: {holdings}")
    entries = _load_momentum_entries()
    state = _load_state()
    today = datetime.now().strftime("%Y-%m-%d")
    notified = state.get("momentum_stop_notified", {})

    emergency_exit = []
    stop_loss_triggers = []
    above_ma_count = 0

    for ticker in holdings:
        try:
            df = fetch_ohlcv(ticker, period="14mo")
            if df is None or df.empty:
                continue
            current = float(df["Close"].iloc[-1])

            # 200日MAチェック（緊急撤退判定用）
            if len(df) >= 200:
                ma200 = float(df["Close"].rolling(200).mean().iloc[-1])
                if current > ma200:
                    above_ma_count += 1

            # 損切りチェック（買値から-MOMENTUM_STOP_LOSS_PCT%）
            entry_price = entries.get(ticker)
            if entry_price:
                entry_price = float(entry_price)
                drop_pct = (current - entry_price) / entry_price * 100
                threshold = -_MOMENTUM_STOP_LOSS_PCT
                if drop_pct <= threshold and notified.get(ticker) != today:
                    print(f"  ⚠️ {ticker}: 買値{entry_price:.0f}→現在{current:.0f} ({drop_pct:+.1f}%) 損切りライン到達")
                    stop_loss_triggers.append((ticker, drop_pct))
                    notified[ticker] = today
                else:
                    print(f"  {ticker}: {current:.0f} ({drop_pct:+.1f}%)")
            else:
                print(f"  {ticker}: {current:.0f} (買値未記録)")

        except Exception as e:
            print(f"  {ticker}: エラー - {e}")

    # 緊急撤退判定: 保有銘柄の半数以上が200日MA以下
    if holdings and above_ma_count < len(holdings) / 2:
        emergency_exit = holdings
        print(f"  🚨 緊急撤退シグナル: {above_ma_count}/{len(holdings)}銘柄のみMA上位")

    # 通知送信
    if stop_loss_triggers:
        sell_tickers = [t for t, _ in stop_loss_triggers]
        from modules.notifier import _telegram, _slack
        import re
        now_str = datetime.now().strftime("%Y年%m月%d日 %H:%M")
        msg_lines = [f"⚠️ <b>損切りアラート</b> {now_str}\n"]
        for t, pct in stop_loss_triggers:
            msg_lines.append(f"🔴 {t}: {pct:+.1f}% → 売却を検討してください")
        message = "\n".join(msg_lines)
        tg = os.getenv("TELEGRAM_BOT_TOKEN")
        chat = os.getenv("TELEGRAM_CHAT_ID")
        if tg and chat:
            from modules.notifier import _telegram as _tg
            _tg(tg, chat, message)
        sw = os.getenv("SLACK_WEBHOOK_URL")
        if sw:
            from modules.notifier import _slack as _sl
            _sl(sw, re.sub(r"<b>(.*?)</b>", r"*\1*", message))

    if emergency_exit and state.get("emergency_exit_notified") != today:
        now_str = datetime.now().strftime("%Y年%m月%d日 %H:%M")
        import re
        msg = (f"🚨 <b>緊急撤退アラート</b> {now_str}\n\n"
               f"保有銘柄の過半数が200日MAを下回りました。\n"
               f"下落相場に入った可能性があります。\n\n"
               f"⚡ 全銘柄売却を強く推奨します:\n"
               + "\n".join(f"🔴 {t}" for t in emergency_exit))
        tg = os.getenv("TELEGRAM_BOT_TOKEN")
        chat = os.getenv("TELEGRAM_CHAT_ID")
        if tg and chat:
            from modules.notifier import _telegram as _tg
            _tg(tg, chat, msg)
        sw = os.getenv("SLACK_WEBHOOK_URL")
        if sw:
            from modules.notifier import _slack as _sl
            _sl(sw, re.sub(r"<b>(.*?)</b>", r"*\1*", msg))
        state["emergency_exit_notified"] = today
        print(f"  🚨 緊急撤退通知送信")

    state["momentum_stop_notified"] = notified
    _save_state(state)


def run_momentum_rebalance():
    """月次モメンタムリバランス通知（毎月1日頃に実行）"""
    from modules.universe import UNIVERSE
    from modules.data_fetcher import fetch_ohlcv, normalize_ticker
    import pandas as pd

    UNIVERSE_KEY = "🇯🇵 日本株メジャー"
    TOP_N = 5
    LOOKBACK_DAYS = 126  # 約6ヶ月
    MA_PERIOD = 200

    tickers_raw = UNIVERSE[UNIVERSE_KEY]["tickers"]
    tickers = [normalize_ticker(t) for t in tickers_raw]

    print(f"[月次リバランス] {UNIVERSE_KEY} {len(tickers)}銘柄のモメンタム計算中...")

    prices = {}
    for t in tickers:
        try:
            df = fetch_ohlcv(t, period="14mo")
            if df is not None and not df.empty and len(df) > MA_PERIOD:
                prices[t] = df["Close"].squeeze()
        except Exception as e:
            print(f"  {t}: 取得失敗 ({e})")

    if len(prices) < 2:
        print("  データ不足のためスキップ")
        return

    price_df = pd.DataFrame(prices).ffill()
    cur = price_df.iloc[-1]
    past = price_df.iloc[max(0, len(price_df) - LOOKBACK_DAYS)]
    momentum = ((cur / past) - 1) * 100
    ma200 = price_df.tail(MA_PERIOD).mean()
    qualified = momentum[cur > ma200].dropna().sort_values(ascending=False)
    new_top = list(qualified.head(TOP_N).index)

    # 前回の推奨を読み込む
    prev_holdings = _load_momentum_holdings()

    buy = [t for t in new_top if t not in prev_holdings]
    sell = [t for t in prev_holdings if t not in new_top]
    hold = [t for t in new_top if t in prev_holdings]

    rankings = list(zip(qualified.index.tolist(), qualified.values.tolist()))

    print(f"  推奨TOP{TOP_N}: {new_top}")
    print(f"  買い: {buy} / 売り: {sell} / 継続: {hold}")

    # 保有銘柄と買値を保存
    _MOMENTUM_HOLDINGS_FILE.write_text(json.dumps(new_top, ensure_ascii=False))
    entries = _load_momentum_entries()
    for t in buy:
        try:
            df = fetch_ohlcv(t, period="5d")
            if df is not None and not df.empty:
                entries[t] = float(df["Close"].iloc[-1])
        except Exception:
            pass
    for t in sell:
        entries.pop(t, None)
    _MOMENTUM_ENTRY_FILE.write_text(json.dumps(entries, ensure_ascii=False))

    if buy or sell:
        result = send_momentum_rebalance_alert(buy=buy, sell=sell, hold=hold, rankings=rankings)
        print(f"  → 通知送信: {result}")
    else:
        print("  → 変更なし、通知スキップ")


def main():
    parser = argparse.ArgumentParser(description="株式アラートランナー")
    parser.add_argument("--mode", choices=["all", "signal", "stoploss", "screening", "watchlist", "momentum"],
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

        # 休場日チェック（watchlistモード以外）
        if args.mode != "watchlist" and not is_trading_day():
            print("📅 本日は市場休場日のためシグナルチェックをスキップします")
            return

        # 未約定の指値注文を処理
        if _trader.is_enabled() and hasattr(_trader.broker, "process_pending_orders"):
            pending = _trader.broker.get_orders()
            pending_tickers = list({o["ticker"] for o in pending if o.get("status") == "pending"})
            if pending_tickers:
                print(f"[指値注文処理] {len(pending_tickers)}銘柄の未約定注文を確認中...")
                ohlcv_map = {}
                for t in pending_tickers:
                    try:
                        df = fetch_ohlcv(t, period="3d")
                        if not df.empty:
                            row = df.iloc[-1]
                            ohlcv_map[t] = {
                                "open": float(row["Open"]), "high": float(row["High"]),
                                "low": float(row["Low"]), "close": float(row["Close"]),
                            }
                    except Exception:
                        pass
                fill_results = _trader.broker.process_pending_orders(ohlcv_map)
                for r in fill_results:
                    print(f"  → {r['message']}")

        # シグナル精度の後追い更新（3日後・5日後の結果を記録）
        try:
            update_results()
        except Exception:
            pass

        # 月曜の朝9時だけ自動ウォッチリスト更新（週1回）
        if args.mode in ("all", "watchlist"):
            now = datetime.now()
            is_monday_morning = (now.weekday() == 0 and now.hour == 9)
            if args.mode == "watchlist" or is_monday_morning:
                run_auto_watchlist()

        if args.mode in ("all", "signal"):
            run_signal_alerts(tickers)
        if args.mode in ("all", "stoploss"):
            run_stop_loss_check()
        if args.mode in ("all", "screening"):
            run_screening_alerts(tickers)

        # モメンタム保有銘柄の損切り・緊急撤退監視（毎日実行）
        if args.mode in ("all", "momentum", "stoploss"):
            run_momentum_stop_loss()

        # 月次モメンタムリバランス（毎月1〜3日に1回実行）
        if args.mode in ("all", "momentum"):
            now_dt = datetime.now()
            if args.mode == "momentum" or now_dt.day <= 3:
                run_momentum_rebalance()

        print(f"\n次回チェック: {args.loop}分後" if args.loop > 0 else "\n完了")

    run_once()

    if args.loop > 0:
        print(f"\n{args.loop}分ごとに自動チェックします（止めるには Ctrl+C）")
        while True:
            time.sleep(args.loop * 60)
            run_once()


if __name__ == "__main__":
    main()
