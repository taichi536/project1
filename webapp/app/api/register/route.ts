import { NextRequest, NextResponse } from 'next/server';
import bcrypt from 'bcryptjs';
import { getDb } from '@/lib/db';

export async function POST(req: NextRequest) {
  const { name, email, password } = await req.json();
  if (!name || !email || !password) {
    return NextResponse.json({ error: '全項目を入力してください' }, { status: 400 });
  }

  const db = getDb();
  const existing = db.prepare(`SELECT id FROM users WHERE email = ?`).get(email);
  if (existing) {
    return NextResponse.json({ error: 'このメールアドレスは既に登録されています' }, { status: 409 });
  }

  const hash = await bcrypt.hash(password, 12);
  // 最初のユーザーは自動でadmin
  const count = (db.prepare(`SELECT COUNT(*) as c FROM users`).get() as { c: number }).c;
  const role = count === 0 ? 'admin' : 'member';

  db.prepare(`INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)`)
    .run(name, email, hash, role);

  return NextResponse.json({ success: true, role }, { status: 201 });
}
