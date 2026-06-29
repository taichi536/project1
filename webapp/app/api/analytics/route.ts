import { NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { getDb } from '@/lib/db';

export async function GET() {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const db = getDb();
  const userId = session.user.id;

  // Assignee stats: undone threads grouped by assignee
  const assigneeStats = db.prepare(`
    SELECT
      COALESCE(u.name, '未割当') as assignee_name,
      COUNT(*) as count
    FROM thread_cache tc
    LEFT JOIN users u ON u.id = tc.assigned_to
    WHERE tc.user_id = ? AND tc.is_done = 0
    GROUP BY tc.assigned_to, u.name
    ORDER BY count DESC
  `).all(userId) as { assignee_name: string; count: number }[];

  // Upcoming actions: next_action_due within next 7 days, not done
  const upcomingActions = db.prepare(`
    SELECT
      tc.subject,
      tc.next_action,
      tc.next_action_due,
      COALESCE(u.name, '未割当') as assignee_name
    FROM thread_cache tc
    LEFT JOIN users u ON u.id = tc.assigned_to
    WHERE tc.user_id = ?
      AND tc.is_done = 0
      AND tc.next_action_due IS NOT NULL
      AND tc.next_action_due >= date('now', 'localtime')
      AND tc.next_action_due <= date('now', 'localtime', '+7 days')
    ORDER BY tc.next_action_due ASC
  `).all(userId) as { subject: string; next_action: string; next_action_due: string; assignee_name: string }[];

  // Weekly done: threads marked done in last 7 days (synced_at as proxy)
  const weeklyDone = (db.prepare(`
    SELECT COUNT(*) as count FROM thread_cache
    WHERE user_id = ?
      AND is_done = 1
      AND synced_at >= datetime('now', 'localtime', '-7 days')
  `).get(userId) as { count: number }).count;

  // Weekly new: threads synced in last 7 days
  const weeklyNew = (db.prepare(`
    SELECT COUNT(*) as count FROM thread_cache
    WHERE user_id = ?
      AND synced_at >= datetime('now', 'localtime', '-7 days')
  `).get(userId) as { count: number }).count;

  return NextResponse.json({ assigneeStats, upcomingActions, weeklyDone, weeklyNew });
}
