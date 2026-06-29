import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { getDb } from '@/lib/db';

export async function GET() {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  const db = getDb();
  const rules = db.prepare(`
    SELECT r.*, u.name as assign_to_name
    FROM routing_rules r
    LEFT JOIN users u ON u.id = r.assign_to
    WHERE r.user_id = ? ORDER BY r.created_at DESC
  `).all(session.user.id);
  return NextResponse.json({ rules });
}

export async function POST(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  const { match_domain, match_keyword, assign_to } = await req.json();
  if (!match_domain && !match_keyword) return NextResponse.json({ error: '条件を入力してください' }, { status: 400 });
  const db = getDb();
  db.prepare('INSERT INTO routing_rules (user_id, match_domain, match_keyword, assign_to) VALUES (?, ?, ?, ?)')
    .run(session.user.id, match_domain || null, match_keyword || null, assign_to || null);
  return NextResponse.json({ success: true });
}
