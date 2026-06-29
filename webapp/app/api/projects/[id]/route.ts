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

  return NextResponse.json({ project, threads });
}

export async function DELETE(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const { id } = await params;
  const db = getDb();
  db.prepare(`DELETE FROM projects WHERE id = ? AND user_id = ?`).run(id, session.user.id);
  return NextResponse.json({ success: true });
}
