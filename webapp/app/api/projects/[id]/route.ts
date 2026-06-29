import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { getDb } from '@/lib/db';

export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const { id } = await params;
  const db = getDb();

  const project = db.prepare(`SELECT * FROM projects WHERE id = ? AND user_id = ?`)
    .get(id, session.user.id);
  if (!project) return NextResponse.json({ error: 'Not found' }, { status: 404 });

  const threads = db.prepare(`
    SELECT * FROM gmail_threads WHERE project_id = ? ORDER BY last_message_at DESC
  `).all(id);

  // Fetch thread_cache threads linked via deals (deal_id = project id by convention)
  const dealThreads = db.prepare(`
    SELECT tc.id, tc.thread_id, tc.subject, tc.from_email, tc.last_message_at,
           tc.needs_reply, tc.next_action, tc.next_action_due, tc.message_count, tc.snippet,
           tc.is_done, tc.deal_id,
           d.name as deal_name
    FROM thread_cache tc
    LEFT JOIN deals d ON d.id = tc.deal_id
    WHERE tc.deal_id = ?
    ORDER BY tc.last_message_at DESC
  `).all(id);

  return NextResponse.json({ project, threads, dealThreads });
}

export async function DELETE(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const { id } = await params;
  const db = getDb();
  db.prepare(`DELETE FROM projects WHERE id = ? AND user_id = ?`).run(id, session.user.id);
  return NextResponse.json({ success: true });
}
