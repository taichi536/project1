import { NextRequest, NextResponse } from 'next/server';
import Anthropic from '@anthropic-ai/sdk';

const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { type, context } = body;

  const prompts: Record<string, string> = {
    outreach: `以下の情報をもとに、ビジネスアウトリーチメールを生成してください。
情報: ${JSON.stringify(context)}
・件名と本文を生成してください
・相手の状況・属性に合わせた内容にする
・200〜300文字程度の簡潔な文面
・返信・次のアクションを促す一文で締める`,

    reply: `以下の受信メッセージに対する返信文を生成してください。
元のメッセージ: ${context.original}
状況・補足: ${context.situation || 'なし'}
・丁寧かつ簡潔に
・次のアクションを明確にする`,

    followup: `以下の相手へのフォローアップメッセージを生成してください。
相手情報: ${JSON.stringify(context)}
・前回の連絡から間が空いていることに自然に触れる
・返信を促す
・100〜150文字程度`,

    proposal: `以下の情報をもとに、提案・営業メールを生成してください。
情報: ${JSON.stringify(context)}
・件名と本文を生成してください
・相手の課題・ニーズに触れる
・自社・自分の提供価値を簡潔に伝える
・次のステップ（打ち合わせ打診など）で締める`,

    report: `以下の情報をもとに、業務報告・進捗報告の文章を生成してください。
情報: ${JSON.stringify(context)}
・簡潔な箇条書きと要約を含める
・完了事項・進行中事項・課題を整理する`,
  };

  const prompt = prompts[type] ?? `以下の内容でビジネスメッセージを生成してください: ${JSON.stringify(context)}`;

  const message = await client.messages.create({
    model: 'claude-haiku-4-5-20251001',
    max_tokens: 1024,
    messages: [{ role: 'user', content: prompt }],
  });

  const text = message.content[0].type === 'text' ? message.content[0].text : '';
  return NextResponse.json({ text });
}
