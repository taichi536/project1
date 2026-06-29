import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { getDb } from '@/lib/db';

// Gmailスレッドをプロジェクトにひもつけ
export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const { id } = await params;
  const db = getDb();

  const project = db.prepare(`SELECT id FROM projects WHERE id = ? AND user_id = ?`).get(id, session.user.id);
  if (!project) return NextResponse.json({ error: 'Not found' }, { status: 404 });

  const { threadId, subject, snippet, fromEmail, lastMessageAt, messageCount } = await req.json();

  db.prepare(`
    INSERT INTO gmail_threads (project_id, user_id, thread_id, subject, snippet, from_email, last_message_at, message_count)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(thread_id, user_id) DO UPDATE SET
      project_id = excluded.project_id,
      subject = excluded.subject,
      snippet = excluded.snippet,
      last_message_at = excluded.last_message_at,
      message_count = excluded.message_count,
      synced_at = datetime('now','localtime')
  `).run(id, session.user.id, threadId, subject, snippet, fromEmail, lastMessageAt, messageCount);

  return NextResponse.json({ success: true });
}

export async function DELETE(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const { id } = await params;
  const { threadId } = await req.json();
  const db = getDb();
  db.prepare(`DELETE FROM gmail_threads WHERE project_id = ? AND thread_id = ? AND user_id = ?`)
    .run(id, threadId, session.user.id);
  return NextResponse.json({ success: true });
}
