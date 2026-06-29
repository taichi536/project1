import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { getDb } from '@/lib/db';

export async function GET() {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const db = getDb();
  const templates = db.prepare('SELECT * FROM templates WHERE user_id = ? ORDER BY created_at DESC').all(session.user.id);
  return NextResponse.json({ templates });
}

export async function POST(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const { title, body } = await req.json();
  if (!title?.trim() || !body?.trim()) return NextResponse.json({ error: 'タイトルと本文は必須です' }, { status: 400 });

  const db = getDb();
  const result = db.prepare('INSERT INTO templates (user_id, title, body) VALUES (?, ?, ?)').run(session.user.id, title.trim(), body.trim());
  const template = db.prepare('SELECT * FROM templates WHERE id = ?').get(result.lastInsertRowid);
  return NextResponse.json({ template });
}
