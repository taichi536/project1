import { NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { fetchThreads } from '@/lib/gmail';

export async function GET() {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  if (!session.accessToken) {
    return NextResponse.json({ error: 'Gmail未連携。Googleでログインしてください。', needsAuth: true }, { status: 403 });
  }

  try {
    const threads = await fetchThreads(session.accessToken, 30);
    return NextResponse.json({ threads });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'unknown';
    return NextResponse.json({ error: `Gmail取得エラー: ${msg}` }, { status: 500 });
  }
}
