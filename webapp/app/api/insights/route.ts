import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import Anthropic from '@anthropic-ai/sdk';

const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

export async function GET() {
  const db = getDb();

  const statusCounts = db.prepare(
    `SELECT status, COUNT(*) as count FROM communications GROUP BY status`
  ).all() as { status: string; count: number }[];

  const replyRate = db.prepare(`
    SELECT COUNT(*) as total,
    SUM(CASE WHEN replied_at IS NOT NULL THEN 1 ELSE 0 END) as replied
    FROM communications WHERE direction = 'outbound'
  `).get() as { total: number; replied: number };

  const overdue = db.prepare(`
    SELECT COUNT(*) as count FROM communications
    WHERE status IN ('pending','in_progress') AND direction='outbound'
    AND sent_at < datetime('now','-3 days','localtime')
  `).get() as { count: number };

  const total = statusCounts.reduce((s, r) => s + r.count, 0);

  if (total === 0) {
    return NextResponse.json({
      insight: 'まずデータを登録しましょう。CSVインポートか手動入力でコミュニケーション記録を追加すると、AIが状況を分析して次のアクションを提案します。',
      level: 'info',
    });
  }

  const summary = {
    total,
    statusCounts,
    replyRate,
    overdueCount: overdue.count,
  };

  const message = await client.messages.create({
    model: 'claude-haiku-4-5-20251001',
    max_tokens: 200,
    messages: [{
      role: 'user',
      content: `以下の業務データを分析して、今すぐ取るべきアクションを1〜2文で日本語で提案してください。
データ: ${JSON.stringify(summary)}
・数値に基づいた具体的な提案をしてください
・「〜してください」など指示口調で
・50〜80文字程度で簡潔に`,
    }],
  });

  const text = message.content[0].type === 'text' ? message.content[0].text : '';
  const level = overdue.count > 0 ? 'warning' : replyRate.total > 0 && replyRate.replied / replyRate.total < 0.3 ? 'warning' : 'info';

  return NextResponse.json({ insight: text, level });
}
