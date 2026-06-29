import { NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { getDb } from '@/lib/db';

export async function GET() {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const db = getDb();
  const userId = session.user.id;

  const needsReply = (db.prepare(`
    SELECT COUNT(*) as count FROM thread_cache WHERE user_id = ? AND needs_reply = 1 AND is_done = 0
  `).get(userId) as { count: number }).count;

  const undone = (db.prepare(`
    SELECT COUNT(*) as count FROM thread_cache WHERE user_id = ? AND is_done = 0
  `).get(userId) as { count: number }).count;

  const done = (db.prepare(`
    SELECT COUNT(*) as count FROM thread_cache WHERE user_id = ? AND is_done = 1
  `).get(userId) as { count: number }).count;

  const total = (db.prepare(`
    SELECT COUNT(*) as count FROM thread_cache WHERE user_id = ?
  `).get(userId) as { count: number }).count;

  // 最近のスレッド（未対応のもの、最新5件）
  const recent = db.prepare(`
    SELECT tc.*, u.name as assignee_name
    FROM thread_cache tc
    LEFT JOIN users u ON u.id = tc.assigned_to
    WHERE tc.user_id = ? AND tc.is_done = 0
    ORDER BY tc.last_message_at DESC LIMIT 8
  `).all(userId);

  return NextResponse.json({ needsReply, undone, done, total, recent });
}
