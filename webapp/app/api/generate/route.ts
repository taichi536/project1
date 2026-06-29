import { NextRequest, NextResponse } from 'next/server';
import Anthropic from '@anthropic-ai/sdk';

const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { type, context } = body;

  const prompts: Record<string, string> = {
    scout: `以下の候補者情報をもとに、スカウトメッセージを生成してください。
候補者情報: ${JSON.stringify(context)}
・件名と本文を生成してください
・200〜300文字程度の簡潔な文面
・候補者のキャリアに合わせたパーソナライズを必ず含める
・返信を促す一文で締める`,

    reply: `以下の問い合わせに対する返信文を生成してください。
元のメッセージ: ${context.original}
状況: ${context.situation || ''}
・丁寧かつ簡潔に
・次のアクションを明確にする`,

    followup: `以下の相手へのフォローアップメッセージを生成してください。
相手情報: ${JSON.stringify(context)}
・前回の連絡から時間が経っていることに触れる
・返信を自然に促す
・100〜150文字程度`,
  };

  const prompt = prompts[type] || `以下の内容で業務メッセージを生成してください: ${JSON.stringify(context)}`;

  const message = await client.messages.create({
    model: 'claude-haiku-4-5-20251001',
    max_tokens: 1024,
    messages: [{ role: 'user', content: prompt }],
  });

  const text = message.content[0].type === 'text' ? message.content[0].text : '';
  return NextResponse.json({ text });
}
