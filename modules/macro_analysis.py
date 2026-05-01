import anthropic
from modules.news_fetcher import fetch_market_news, score_macro_relevance


_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


MACRO_INDICATORS = {
    "日本": {
        "政策金利（日銀）": {"値": "0.5%", "方向": "引き上げ傾向", "投資影響": "円高・金融株プラス・成長株マイナス"},
        "CPI（消費者物価）": {"値": "約3%台", "方向": "高止まり", "投資影響": "実質賃金圧迫・消費関連に注意"},
        "USD/JPY": {"値": "約145円前後", "方向": "不安定", "投資影響": "輸出株に影響大"},
        "日本株見通し（2026年末）": {"値": "TOPIX 4,100 / 日経 61,500", "方向": "強気予想", "投資影響": "中長期は強気バイアス"},
    },
    "米国": {
        "FFレート（FRB）": {"値": "4.25-4.5%", "方向": "据え置き〜引き下げ検討", "投資影響": "利下げ期待でグロース株にプラス"},
        "米CPI": {"値": "約2.5%台", "方向": "鈍化傾向", "投資影響": "インフレ沈静化なら利下げ加速"},
        "AIセクター相場": {"値": "継続中", "方向": "持続性あり", "投資影響": "半導体・クラウド銘柄に中期追い風"},
        "関税リスク": {"値": "対中・対日", "方向": "地政学リスク高い", "投資影響": "製造業・自動車に逆風の可能性"},
    },
}


def get_macro_context() -> dict:
    return MACRO_INDICATORS


def analyze_news_sentiment(
    ticker: str,
    company_name: str,
    sector: str,
    news_items: list[dict],
) -> str:
    if not news_items:
        news_text = "ニュースを取得できませんでした。"
    else:
        # マクロ関連スコアでソートして上位15件
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
    for region, indicators in MACRO_INDICATORS.items():
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

    client = _get_client()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def quick_market_sentiment(news_items: list[dict]) -> str:
    """ニュース一覧から市場全体のセンチメントを素早く判定"""
    if not news_items:
        return "ニュースデータなし"

    titles = "\n".join(f"- {n['title']}" for n in news_items[:20])

    prompt = f"""以下の最新ニュース見出し一覧を見て、株式市場全体のセンチメントを3段階で判定し、根拠を2文で述べてください。

ニュース一覧:
{titles}

回答形式（日本語）:
センチメント: [強気 / 中立 / 弱気]
根拠: （2文以内）"""

    client = _get_client()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
