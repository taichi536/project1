import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET(req: NextRequest) {
  const token = req.nextUrl.searchParams.get('token');
  if (!token) return NextResponse.json({ error: 'トークンが必要です' }, { status: 400 });
  const db = getDb();
  const row = db.prepare(`
    SELECT i.email, i.accepted_at, u.name as inviter_name
    FROM invitations i
    JOIN users u ON u.id = i.invited_by
    WHERE i.token = ?
  `).get(token) as { email: string; accepted_at: string | null; inviter_name: string } | undefined;
  if (!row) return NextResponse.json({ error: '招待が見つかりません' }, { status: 404 });
  return NextResponse.json({ inviterName: row.inviter_name, email: row.email, accepted: !!row.accepted_at });
}
