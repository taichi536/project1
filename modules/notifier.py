import requests
import os
from datetime import datetime


def _telegram(token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def _slack(webhook_url: str, text: str) -> bool:
    try:
        resp = requests.post(webhook_url, json={"text": text}, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def send_signal_alert(
    ticker: str,
    verdict: str,
    score: int,
    price: float,
    signals: list[dict],
    rsi: float | None = None,
    atr: float | None = None,
    telegram_token: str | None = None,
    telegram_chat_id: str | None = None,
    slack_webhook: str | None = None,
) -> dict[str, bool]:
    emoji = {"買い": "🟢", "売り": "🔴", "様子見": "🟡"}.get(verdict, "⚪")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    top_signals = "\n".join(
        f"  • {s['指標']}: {s['判定']}"
        for s in sorted(signals, key=lambda x: abs(x["スコア"]), reverse=True)[:3]
    )

    message = (
        f"📈 <b>株式シグナルアラート</b>\n"
        f"─────────────────\n"
        f"銘柄: <b>{ticker}</b>\n"
        f"現在値: {price:,.2f}\n"
        f"シグナル: {emoji} <b>{verdict}</b>（スコア: {score:+d}）\n"
        f"RSI: {rsi:.1f}  ATR: {atr:.2f}\n"
        f"─────────────────\n"
        f"注目指標:\n{top_signals}\n"
        f"─────────────────\n"
        f"⏰ {now}"
    )

    results = {}

    tg_token = telegram_token or os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if tg_token and tg_chat:
        results["telegram"] = _telegram(tg_token, tg_chat, message)

    sw = slack_webhook or os.getenv("SLACK_WEBHOOK_URL")
    if sw:
        # Slackはプレーンテキスト
        plain = message.replace("<b>", "*").replace("</b>", "*").replace("<br>", "\n")
        results["slack"] = _slack(sw, plain)

    return results


def send_screening_alert(
    passed_tickers: list[str],
    telegram_token: str | None = None,
    telegram_chat_id: str | None = None,
    slack_webhook: str | None = None,
) -> dict[str, bool]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if passed_tickers:
        ticker_list = "\n".join(f"  ✅ {t}" for t in passed_tickers)
        message = (
            f"🔍 <b>バリュー株スクリーニング結果</b>\n"
            f"─────────────────\n"
            f"合格銘柄 ({len(passed_tickers)}件):\n{ticker_list}\n"
            f"─────────────────\n"
            f"⏰ {now}"
        )
    else:
        message = (
            f"🔍 <b>バリュー株スクリーニング結果</b>\n"
            f"─────────────────\n"
            f"条件を満たす銘柄はありませんでした\n"
            f"⏰ {now}"
        )

    results = {}
    tg_token = telegram_token or os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if tg_token and tg_chat:
        results["telegram"] = _telegram(tg_token, tg_chat, message)

    sw = slack_webhook or os.getenv("SLACK_WEBHOOK_URL")
    if sw:
        plain = message.replace("<b>", "*").replace("</b>", "*")
        results["slack"] = _slack(sw, plain)

    return results


def send_stop_loss_alert(
    ticker: str,
    current_price: float,
    stop_price: float,
    telegram_token: str | None = None,
    telegram_chat_id: str | None = None,
    slack_webhook: str | None = None,
) -> dict[str, bool]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    message = (
        f"🚨 <b>損切りラインアラート</b>\n"
        f"─────────────────\n"
        f"銘柄: <b>{ticker}</b>\n"
        f"現在値: {current_price:,.2f}\n"
        f"損切りライン: {stop_price:,.2f}\n"
        f"⚠️ 損切りラインに近づいています！\n"
        f"─────────────────\n"
        f"⏰ {now}"
    )

    results = {}
    tg_token = telegram_token or os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if tg_token and tg_chat:
        results["telegram"] = _telegram(tg_token, tg_chat, message)

    sw = slack_webhook or os.getenv("SLACK_WEBHOOK_URL")
    if sw:
        plain = message.replace("<b>", "*").replace("</b>", "*")
        results["slack"] = _slack(sw, plain)

    return results
