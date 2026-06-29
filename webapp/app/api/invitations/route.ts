import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { getDb } from '@/lib/db';

export async function GET() {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  const db = getDb();
  const invitations = db.prepare(
    'SELECT id, email, token, accepted_at, created_at FROM invitations WHERE invited_by = ? ORDER BY created_at DESC'
  ).all(session.user.id);
  return NextResponse.json({ invitations });
}

export async function POST(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  const { email } = await req.json();
  if (!email) return NextResponse.json({ error: 'メールアドレスを入力してください' }, { status: 400 });
  const token = crypto.randomUUID();
  const db = getDb();
  db.prepare('INSERT INTO invitations (invited_by, email, token) VALUES (?, ?, ?)').run(session.user.id, email, token);
  const inviteUrl = `${process.env.NEXTAUTH_URL}/invite/${token}`;
  return NextResponse.json({ token, inviteUrl });
}
