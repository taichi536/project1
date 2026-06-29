import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { getDb } from '@/lib/db';

export async function GET() {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const db = getDb();
  const projects = db.prepare(`
    SELECT p.*,
      COUNT(DISTINCT gt.id) as thread_count,
      SUM(gt.has_unread) as unread_count,
      COUNT(DISTINCT tc.id) as deal_thread_count,
      SUM(CASE WHEN tc.needs_reply = 1 AND tc.is_done = 0 THEN 1 ELSE 0 END) as deal_needs_reply
    FROM projects p
    LEFT JOIN gmail_threads gt ON gt.project_id = p.id
    LEFT JOIN thread_cache tc ON tc.deal_id = p.id
    WHERE p.user_id = ?
    GROUP BY p.id
    ORDER BY p.created_at DESC
  `).all(session.user.id);

  return NextResponse.json(projects);
}

export async function POST(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const { name, description } = await req.json();
  if (!name) return NextResponse.json({ error: '案件名を入力してください' }, { status: 400 });

  const db = getDb();
  const result = db.prepare(`INSERT INTO projects (user_id, name, description) VALUES (?, ?, ?)`)
    .run(session.user.id, name, description ?? null);

  return NextResponse.json({ id: result.lastInsertRowid, name }, { status: 201 });
}
