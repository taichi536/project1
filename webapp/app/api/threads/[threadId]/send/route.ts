import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { fetchThreadDetail, sendEmail } from '@/lib/gmail';
import { getDb } from '@/lib/db';

export async function POST(req: NextRequest, { params }: { params: Promise<{ threadId: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  if (!session.accessToken) return NextResponse.json({ error: 'Gmail未連携' }, { status: 403 });

  const { threadId } = await params;
  const { to, subject, body } = await req.json();
  if (!to || !body) return NextResponse.json({ error: '宛先と本文は必須です' }, { status: 400 });

  // スレッドのIn-Reply-ToとReferencesを取得
  const thread = await fetchThreadDetail(session.accessToken, threadId);
  const lastMsg = thread?.messages[thread.messages.length - 1];
  const messageId = lastMsg?.id;

  await sendEmail(session.accessToken, {
    to,
    subject: subject || (thread?.subject ? `Re: ${thread.subject}` : ''),
    body,
    threadId,
    inReplyTo: messageId,
    references: messageId,
  });

  // 送信後は対応済みに更新
  const db = getDb();
  db.prepare(`UPDATE thread_cache SET is_done = 1, needs_reply = 0 WHERE thread_id = ? AND user_id = ?`)
    .run(threadId, session.user.id);

  return NextResponse.json({ success: true });
}
