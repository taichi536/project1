import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { sendEmail } from '@/lib/gmail';
import { getDb } from '@/lib/db';

export async function POST(req: NextRequest, { params }: { params: Promise<{ threadId: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  if (!session.accessToken) return NextResponse.json({ error: 'Gmail未連携' }, { status: 403 });

  const { threadId } = await params;
  const { to, cc, bcc, subject, body, inReplyTo, references } = await req.json();
  if (!to || !body) return NextResponse.json({ error: '宛先と本文は必須です' }, { status: 400 });

  await sendEmail(session.accessToken, {
    to,
    cc,
    bcc,
    subject: subject || '',
    body,
    threadId,
    inReplyTo,
    references,
  });

  const db = getDb();
  db.prepare(`UPDATE thread_cache SET needs_reply = 0 WHERE thread_id = ? AND user_id = ?`)
    .run(threadId, session.user.id);

  return NextResponse.json({ success: true });
}
