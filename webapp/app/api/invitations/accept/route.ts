import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function POST(req: NextRequest) {
  const { token } = await req.json();
  if (!token) return NextResponse.json({ error: 'トークンが必要です' }, { status: 400 });
  const db = getDb();
  const invitation = db.prepare('SELECT id, accepted_at FROM invitations WHERE token = ?').get(token) as { id: number; accepted_at: string | null } | undefined;
  if (!invitation) return NextResponse.json({ error: '招待が見つかりません' }, { status: 404 });
  if (!invitation.accepted_at) {
    db.prepare("UPDATE invitations SET accepted_at = datetime('now','localtime') WHERE token = ?").run(token);
  }
  return NextResponse.json({ success: true });
}
