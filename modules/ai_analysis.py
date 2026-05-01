import anthropic
import json


_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def analyze_five_forces(company_name: str, sector: str, industry: str) -> str:
    prompt = f"""あなたは株式投資の専門家です。以下の企業についてポーター のファイブフォース分析を行ってください。

企業名: {company_name}
セクター: {sector}
業種: {industry}

以下の5つの力それぞれについて、【強い/中程度/弱い】の評価と100字程度の根拠を述べてください。
最後に投資家視点での総合評価（強み・リスク）を200字以内でまとめてください。

1. 買い手の交渉力
2. 売り手（供給者）の交渉力
3. 競合他社との競争
4. 新規参入の脅威
5. 代替品・代替サービスの脅威

日本語で回答してください。"""

    client = _get_client()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def analyze_chart_ai(
    ticker: str,
    signals: list[dict],
    overall: str,
    score: int,
    current_price: float,
    rsi: float | None,
    atr: float | None,
) -> str:
    signals_text = "\n".join(
        f"- {s['指標']}: {s['値']} → {s['判定']} (スコア: {s['スコア']:+d})" for s in signals
    )

    prompt = f"""あなたは経験豊富な株式テクニカルアナリストです。以下のデータを基に、投資家向けの分析コメントを生成してください。

銘柄: {ticker}
現在値: {current_price:.2f}
総合シグナル: {overall}（スコア: {score:+d}）
RSI: {rsi:.1f if rsi else 'N/A'}
ATR: {atr:.2f if atr else 'N/A'}

【各指標の状況】
{signals_text}

以下の構成で分析してください（合計300字以内）：
1. 現在の相場状況（1〜2文）
2. 注目すべきシグナル（1〜2文）
3. 短期的な売買タイミングの見解（1〜2文）
4. 注意すべきリスク（1文）

日本語で、投資家が実際に判断できる具体的な内容にしてください。"""

    client = _get_client()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
