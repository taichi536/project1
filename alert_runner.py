"""
定期アラート実行スクリプト
使い方:
  python alert_runner.py                  # 1回だけ実行
  python alert_runner.py --loop 60        # 60分ごとに繰り返す
  python alert_runner.py --mode screening # スクリーニングのみ

cron設定例（平日9:00と15:00に実行）:
  0 9,15 * * 1-5 cd /path/to/project1 && python alert_runner.py
"""

import argparse
import time
import os
from modules.data_fetcher import fetch_ohlcv, fetch_info
from modules.technical import compute_all
from modules.signals import evaluate_signals, overall_signal
from modules.notifier import send_signal_alert, send_screening_alert, send_stop_loss_alert
from modules.screening import screen_single
from modules.diary import get_trades, calc_pnl


WATCH_TICKERS = os.getenv("WATCH_TICKERS", "7203,9984,AAPL").split(",")
SIGNAL_THRESHOLD = int(os.getenv("SIGNAL_THRESHOLD", "2"))   # この絶対値以上でアラート
STOP_LOSS_MARGIN = float(os.getenv("STOP_LOSS_MARGIN", "1.05"))  # 損切りラインの何%以内で警告


def run_signal_alerts():
    print(f"[シグナル監視] 対象銘柄: {WATCH_TICKERS}")
    for ticker in WATCH_TICKERS:
        ticker = ticker.strip()
        try:
            df = fetch_ohlcv(ticker, period="6mo")
            df = compute_all(df)
            signals = evaluate_signals(df)
            verdict, score = overall_signal(signals)
            price = df["Close"].iloc[-1]
            rsi = df["RSI"].dropna().iloc[-1] if "RSI" in df.columns else None
            atr = df["ATR"].dropna().iloc[-1] if "ATR" in df.columns else None

            print(f"  {ticker}: {verdict} (score={score:+d}, 価格={price:.2f})")

            if abs(score) >= SIGNAL_THRESHOLD:
                results = send_signal_alert(
                    ticker=ticker,
                    verdict=verdict,
                    score=score,
                    price=price,
                    signals=signals,
                    rsi=rsi,
                    atr=atr,
                )
                print(f"    通知送信: {results}")
            else:
                print(f"    スコア {score:+d} は閾値未満のためスキップ")

        except Exception as e:
            print(f"  {ticker}: エラー - {e}")


def run_screening_alerts(tickers: list[str] | None = None):
    targets = tickers or WATCH_TICKERS
    print(f"[スクリーニング] 対象銘柄: {targets}")
    passed = []
    for ticker in targets:
        ticker = ticker.strip()
        try:
            result = screen_single(ticker)
            status = "合格 ✅" if result["合否"] else "不合格 ❌"
            print(f"  {ticker}: {status}")
            if result["合否"]:
                passed.append(ticker)
        except Exception as e:
            print(f"  {ticker}: エラー - {e}")

    results = send_screening_alert(passed)
    print(f"  通知送信: {results}")


def run_stop_loss_check():
    print("[損切り監視] 保有ポジションを確認中...")
    trades_df = get_trades(limit=10000)
    pnl_data = calc_pnl(trades_df)
    positions = pnl_data["positions"]

    if not positions:
        print("  保有ポジションなし")
        return

    # 投資日記から損切りラインを取得
    stop_map = {}
    if not trades_df.empty:
        buys = trades_df[trades_df["action"] == "買い"]
        for _, row in buys.iterrows():
            t = row["ticker"]
            if row["stop_loss"] and row["stop_loss"] > 0:
                # 最新の損切りラインを使用
                stop_map[t] = float(row["stop_loss"])

    for ticker, lots in positions.items():
        try:
            info = fetch_info(ticker)
            current = info.get("currentPrice") or info.get("regularMarketPrice")
            if not current:
                continue

            stop = stop_map.get(ticker)
            if stop and current <= stop * STOP_LOSS_MARGIN:
                print(f"  ⚠️ {ticker}: 現在値 {current:.2f} が損切りライン {stop:.2f} に接近！")
                results = send_stop_loss_alert(ticker, current, stop)
                print(f"    通知送信: {results}")
            else:
                atr_stop = stop or "未設定"
                print(f"  {ticker}: 現在値 {current:.2f} / 損切りライン {atr_stop}")
        except Exception as e:
            print(f"  {ticker}: エラー - {e}")


def main():
    parser = argparse.ArgumentParser(description="株式アラートランナー")
    parser.add_argument("--mode", choices=["all", "signal", "screening", "stoploss"],
                        default="all", help="実行モード")
    parser.add_argument("--loop", type=int, default=0,
                        help="繰り返し間隔（分）。0=1回のみ")
    parser.add_argument("--tickers", type=str, default="",
                        help="カンマ区切りの銘柄コード（省略時は環境変数WATCH_TICKERSを使用）")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()] if args.tickers else None

    def run_once():
        print(f"\n{'='*50}")
        print(f"アラートチェック開始: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*50}")

        if args.mode in ("all", "signal"):
            run_signal_alerts()
        if args.mode in ("all", "screening"):
            run_screening_alerts(tickers)
        if args.mode in ("all", "stoploss"):
            run_stop_loss_check()

    run_once()

    if args.loop > 0:
        print(f"\n{args.loop}分ごとに繰り返します（Ctrl+Cで停止）")
        while True:
            time.sleep(args.loop * 60)
            run_once()


if __name__ == "__main__":
    main()
