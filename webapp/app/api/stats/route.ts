import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET() {
  const db = getDb();

  const statusCounts = db.prepare(`
    SELECT status, COUNT(*) as count FROM communications GROUP BY status
  `).all() as { status: string; count: number }[];

  const typeCounts = db.prepare(`
    SELECT type, COUNT(*) as count FROM communications GROUP BY type
  `).all() as { type: string; count: number }[];

  const replyRate = db.prepare(`
    SELECT
      COUNT(*) as total,
      SUM(CASE WHEN replied_at IS NOT NULL THEN 1 ELSE 0 END) as replied
    FROM communications WHERE direction = 'outbound'
  `).get() as { total: number; replied: number };

  const overdueCount = db.prepare(`
    SELECT COUNT(*) as count FROM communications
    WHERE status IN ('pending', 'in_progress')
    AND sent_at < datetime('now', '-3 days', 'localtime')
    AND direction = 'outbound'
  `).get() as { count: number };

  const recent = db.prepare(`
    SELECT c.*, co.name as contact_name, co.company
    FROM communications c
    LEFT JOIN contacts co ON c.contact_id = co.id
    ORDER BY c.created_at DESC LIMIT 5
  `).all();

  return NextResponse.json({
    statusCounts,
    typeCounts,
    replyRate,
    overdueCount: overdueCount.count,
    recent,
  });
}
