import { NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { fetchThreadList } from '@/lib/gmail';

// 開発用: needs_reply判定のデバッグ情報を返す
export async function GET() {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  if (process.env.NODE_ENV !== 'development') {
    return NextResponse.json({ error: 'Not available in production' }, { status: 403 });
  }

  if (!session.accessToken) return NextResponse.json({ error: 'Gmail未連携' }, { status: 403 });

  const myEmail = session.user.email ?? '';
  const threads = await fetchThreadList(session.accessToken, 10);

  const debug = threads.slice(0, 10).map(t => {
    const lastFrom = t.lastFrom ?? '';
    const lastFromEmail = (lastFrom.match(/<(.+?)>/)?.[1] ?? lastFrom).trim().toLowerCase();
    const myEmailLower = myEmail.trim().toLowerCase();
    const needsReply = (myEmailLower && lastFromEmail && lastFromEmail !== myEmailLower) ? 1 : 0;
    return {
      subject: t.subject,
      lastFrom,
      lastFromEmail,
      myEmail: myEmailLower,
      needsReply,
      match: lastFromEmail === myEmailLower,
    };
  });

  return NextResponse.json({ myEmail, debug });
}
