import os
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta


# ── リアルタイム市場指標 ────────────────────────────────────────────────────────
_MARKET_SYMBOLS = {
    "日経平均": "^N225",
    "TOPIX（1306ETF）": "1306.T",
    "S&P500": "^GSPC",
    "NASDAQ": "^IXIC",
    "USD/JPY": "USDJPY=X",
    "米10年債利回り": "^TNX",
    "原油(WTI)": "CL=F",
    "金": "GC=F",
    "VIX（恐怖指数）": "^VIX",
}

_STATIC_MACRO = {
    "日本": {
        "政策金利（日銀）": {"値": "0.5%", "方向": "引き上げ傾向", "投資影響": "円高・金融株プラス・成長株マイナス"},
        "CPI（消費者物価）": {"値": "約3%台", "方向": "高止まり", "投資影響": "実質賃金圧迫・消費関連に注意"},
    },
    "米国": {
        "FFレート（FRB）": {"値": "4.25-4.5%", "方向": "据え置き〜引き下げ検討", "投資影響": "利下げ期待でグロース株にプラス"},
        "米CPI": {"値": "約2.5%台", "方向": "鈍化傾向", "投資影響": "インフレ沈静化なら利下げ加速"},
        "関税リスク": {"値": "対中・対日", "方向": "地政学リスク高い", "投資影響": "製造業・自動車に逆風の可能性"},
    },
}


def fetch_live_market_data() -> list[dict]:
    """yfinanceで主要市場指標をリアルタイム取得"""
    results = []
    for name, symbol in _MARKET_SYMBOLS.items():
        try:
            tk = yf.Ticker(symbol)
            fi = tk.fast_info
            price = fi.get("last_price") or fi.get("regularMarketPrice")
            prev = fi.get("previous_close") or fi.get("regularMarketPreviousClose")
            if price is None:
                hist = tk.history(period="5d")
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])
                    prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else price
            if price is None:
                continue
            change_pct = ((price - prev) / prev * 100) if prev and prev != 0 else 0.0
            trend = "↑" if change_pct > 0 else ("↓" if change_pct < 0 else "→")
            results.append({
                "指標": name,
                "現在値": _fmt_price(name, price),
                "前日比": f"{trend} {change_pct:+.2f}%",
                "change_pct": change_pct,
                "symbol": symbol,
            })
        except Exception:
            pass
    return results


def _fmt_price(name: str, price: float) -> str:
    if "JPY" in name or "日経" in name or "TOPIX" in name:
        return f"{price:,.0f}"
    if "債利回り" in name or "VIX" in name:
        return f"{price:.2f}%"
    if "原油" in name or "金" in name:
        return f"${price:,.2f}"
    return f"{price:,.2f}"


def get_market_sentiment_rule(live_data: list[dict]) -> dict:
    """
    ルールベースで市場センチメントを判定（AI不要）。
    Returns: {"label": "強気"|"中立"|"弱気", "score": int, "reasons": list[str]}
    """
    score = 0
    reasons = []

    vix = next((d for d in live_data if "VIX" in d["指標"]), None)
    sp500 = next((d for d in live_data if "S&P500" in d["指標"]), None)
    nikkei = next((d for d in live_data if "日経" in d["指標"]), None)
    usdjpy = next((d for d in live_data if "USD/JPY" in d["指標"]), None)
    oil = next((d for d in live_data if "原油" in d["指標"]), None)

    if vix:
        val_str = vix["現在値"].replace("%", "").replace(",", "")
        try:
            v = float(val_str)
            if v < 15:
                score += 2
                reasons.append(f"VIX {v:.1f}（低水準）→ 市場は落ち着いている")
            elif v < 20:
                score += 1
                reasons.append(f"VIX {v:.1f}（普通）→ 特段の恐怖なし")
            elif v < 30:
                score -= 1
                reasons.append(f"VIX {v:.1f}（やや高め）→ 不安心理が高まっている")
            else:
                score -= 2
                reasons.append(f"VIX {v:.1f}（高水準）→ 市場パニック状態")
        except ValueError:
            pass

    if sp500 and sp500["change_pct"] is not None:
        c = sp500["change_pct"]
        if c > 1.0:
            score += 2
            reasons.append(f"S&P500が{c:+.1f}%上昇 → 米国株は強い")
        elif c > 0:
            score += 1
            reasons.append(f"S&P500が{c:+.1f}%上昇 → 米国株はプラス圏")
        elif c > -1.0:
            score -= 1
            reasons.append(f"S&P500が{c:+.1f}%下落 → 米国株は軟調")
        else:
            score -= 2
            reasons.append(f"S&P500が{c:+.1f}%下落 → 米国株は大幅安")

    if nikkei and nikkei["change_pct"] is not None:
        c = nikkei["change_pct"]
        if c > 1.0:
            score += 1
            reasons.append(f"日経平均が{c:+.1f}%上昇 → 国内株は堅調")
        elif c < -1.0:
            score -= 1
            reasons.append(f"日経平均が{c:+.1f}%下落 → 国内株は軟調")

    if usdjpy and usdjpy["change_pct"] is not None:
        c = usdjpy["change_pct"]
        val_str = usdjpy["現在値"].replace(",", "")
        try:
            v = float(val_str)
            if c > 0.3:
                reasons.append(f"円安進行（USD/JPY {v:.1f}）→ 輸出株・外需株に有利")
            elif c < -0.3:
                reasons.append(f"円高進行（USD/JPY {v:.1f}）→ 輸入株に有利、輸出株に注意")
        except ValueError:
            pass

    if score >= 3:
        label = "強気"
    elif score >= 1:
        label = "やや強気"
    elif score >= -1:
        label = "中立"
    elif score >= -2:
        label = "やや弱気"
    else:
        label = "弱気"

    return {"label": label, "score": score, "reasons": reasons}


def get_sector_impact(live_data: list[dict]) -> list[dict]:
    """市場データからセクター別の影響をルールベースで判定"""
    impacts = []
    usdjpy = next((d for d in live_data if "USD/JPY" in d["指標"]), None)
    oil = next((d for d in live_data if "原油" in d["指標"]), None)
    gold = next((d for d in live_data if d["指標"] == "金"), None)
    vix = next((d for d in live_data if "VIX" in d["指標"]), None)
    tnx = next((d for d in live_data if "債利回り" in d["指標"]), None)

    if usdjpy:
        c = usdjpy.get("change_pct", 0) or 0
        if c > 0.3:
            impacts.append({"セクター": "輸出・自動車", "方向": "🟢 有利", "理由": f"円安（{usdjpy['現在値']}）→ 輸出収益増加"})
            impacts.append({"セクター": "内需・小売", "方向": "🔴 不利", "理由": "円安 → 輸入コスト上昇"})
        elif c < -0.3:
            impacts.append({"セクター": "輸出・自動車", "方向": "🔴 不利", "理由": f"円高（{usdjpy['現在値']}）→ 輸出採算悪化"})
            impacts.append({"セクター": "輸入・航空", "方向": "🟢 有利", "理由": "円高 → 燃料費・仕入れコスト低下"})

    if oil:
        c = oil.get("change_pct", 0) or 0
        if c > 1.5:
            impacts.append({"セクター": "石油・エネルギー", "方向": "🟢 有利", "理由": f"原油高（{oil['現在値']}）→ 石油株の収益増"})
            impacts.append({"セクター": "輸送・航空", "方向": "🔴 不利", "理由": "原油高 → 燃料費上昇"})
        elif c < -1.5:
            impacts.append({"セクター": "石油・エネルギー", "方向": "🔴 不利", "理由": f"原油安（{oil['現在値']}）→ 石油株の収益減"})
            impacts.append({"セクター": "輸送・航空", "方向": "🟢 有利", "理由": "原油安 → 燃料費低下"})

    if tnx:
        val_str = tnx["現在値"].replace("%", "").replace(",", "")
        try:
            v = float(val_str)
            c = tnx.get("change_pct", 0) or 0
            if c > 0.5 or v > 4.5:
                impacts.append({"セクター": "銀行・金融", "方向": "🟢 有利", "理由": f"金利上昇（{v:.2f}%）→ 利ザヤ拡大"})
                impacts.append({"セクター": "グロース・成長株", "方向": "🔴 不利", "理由": "金利上昇 → 将来CF割引率上昇"})
                impacts.append({"セクター": "REIT・不動産", "方向": "🔴 不利", "理由": "金利上昇 → 借入コスト増"})
            elif c < -0.5 or v < 3.5:
                impacts.append({"セクター": "銀行・金融", "方向": "🔴 不利", "理由": f"金利低下（{v:.2f}%）→ 利ザヤ縮小"})
                impacts.append({"セクター": "グロース・成長株", "方向": "🟢 有利", "理由": "金利低下 → バリュエーション改善"})
        except ValueError:
            pass

    if vix:
        val_str = vix["現在値"].replace("%", "").replace(",", "")
        try:
            v = float(val_str)
            if v > 25:
                impacts.append({"セクター": "ディフェンシブ（食品・医薬）", "方向": "🟢 有利", "理由": f"VIX高（{v:.1f}）→ リスクオフで安定株に資金移動"})
                impacts.append({"セクター": "金・貴金属", "方向": "🟢 有利", "理由": "リスクオフ → 安全資産選好"})
        except ValueError:
            pass

    return impacts


def get_macro_context() -> dict:
    return _STATIC_MACRO


# ── AI分析（オプション） ────────────────────────────────────────────────────────
def analyze_news_sentiment(
    ticker: str,
    company_name: str,
    sector: str,
    news_items: list[dict],
) -> str:
    try:
        import anthropic
        from modules.news_fetcher import score_macro_relevance
    except ImportError:
        return "anthropicパッケージが未インストールです。"

    if not news_items:
        news_text = "ニュースを取得できませんでした。"
    else:
        scored = sorted(
            news_items,
            key=lambda n: score_macro_relevance(n["title"], n.get("summary", "")),
            reverse=True,
        )[:15]
        news_text = "\n".join(
            f"[{n['source']}] {n['title']}" + (f" — {n['summary'][:100]}" if n.get("summary") else "")
            for n in scored
        )

    macro_text = ""
    for region, indicators in _STATIC_MACRO.items():
        macro_text += f"\n【{region}マクロ環境】\n"
        for name, data in indicators.items():
            macro_text += f"  • {name}: {data['値']}（{data['方向']}）→ {data['投資影響']}\n"

    prompt = f"""あなたは株式投資の専門家です。以下のマクロ経済環境・最新ニュースを踏まえて、指定銘柄への影響を分析してください。

=== 対象銘柄 ===
銘柄コード: {ticker}
企業名: {company_name}
セクター: {sector}

=== 現在のマクロ経済環境 ===
{macro_text}

=== 最新ニュース（マクロ関連上位）===
{news_text}

以下の構成で分析してください（合計400字以内）：

1. **マクロ環境の総評**（1〜2文）：現在の金利・為替・地政学リスクの概況
2. **この銘柄への直接影響**（2〜3文）：セクター特性を踏まえた具体的な影響
3. **注目すべきニュース**（1〜2文）：特に関連性の高いニュースとその意味
4. **投資タイミングへの示唆**（1〜2文）：マクロ観点からの買い/様子見/売りの判断根拠

日本語で、投資家が実際に判断に使える具体的な内容にしてください。"""

    client = anthropic.Anthropic()
    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception as e:
        return f"AI分析エラー: {e}"


def quick_market_sentiment(news_items: list[dict]) -> str:
    try:
        import anthropic
    except ImportError:
        return "anthropicパッケージが未インストールです。"

    if not news_items:
        return "ニュースデータなし"

    titles = "\n".join(f"- {n['title']}" for n in news_items[:20])
    prompt = f"""以下の最新ニュース見出し一覧を見て、株式市場全体のセンチメントを3段階で判定し、根拠を2文で述べてください。

ニュース一覧:
{titles}

回答形式（日本語）:
センチメント: [強気 / 中立 / 弱気]
根拠: （2文以内）"""

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
