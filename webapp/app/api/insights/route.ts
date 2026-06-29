import { NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { getDb } from '@/lib/db';

export async function GET() {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const db = getDb();
  const userId = session.user.id;

  const total = (db.prepare(`SELECT COUNT(*) as count FROM thread_cache WHERE user_id = ?`).get(userId) as { count: number }).count;

  if (total === 0) {
    return NextResponse.json({
      insight: 'まずGmailを連携してメールを取り込みましょう。インポートするとAIが状況を分析して次のアクションを提案します。',
      level: 'info',
    });
  }

  const today = new Date().toISOString().slice(0, 10);

  const needsReply = (db.prepare(`SELECT COUNT(*) as count FROM thread_cache WHERE user_id = ? AND needs_reply = 1 AND is_done = 0`).get(userId) as { count: number }).count;
  const overdueCount = (db.prepare(`SELECT COUNT(*) as count FROM thread_cache WHERE user_id = ? AND is_done = 0 AND next_action_due IS NOT NULL AND next_action_due < ?`).get(userId, today) as { count: number }).count;
  const doneCount = (db.prepare(`SELECT COUNT(*) as count FROM thread_cache WHERE user_id = ? AND is_done = 1`).get(userId) as { count: number }).count;

  let insight = '';
  let level: 'info' | 'warning' = 'info';

  if (overdueCount > 0) {
    insight = `期限切れのアクションが${overdueCount}件あります。優先して対応してください。`;
    level = 'warning';
  } else if (needsReply > 0) {
    insight = `返信が必要なメールが${needsReply}件あります。早めに対応しましょう。`;
    level = 'warning';
  } else {
    const rate = total > 0 ? Math.round((doneCount / total) * 100) : 0;
    insight = `対応完了率は${rate}%です。未対応メールを確認して処理を進めましょう。`;
    level = 'info';
  }

  return NextResponse.json({ insight, level });
}
