import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET() {
  const db = getDb();
  const rows = db.prepare(`SELECT * FROM tasks ORDER BY created_at DESC`).all();
  return NextResponse.json(rows);
}

export async function POST(req: NextRequest) {
  const db = getDb();
  const body = await req.json();
  const result = db.prepare(`
    INSERT INTO tasks (title, description, priority, assigned_to, due_date)
    VALUES (?, ?, ?, ?, ?)
  `).run(body.title, body.description || null, body.priority || 'medium', body.assigned_to || null, body.due_date || null);
  return NextResponse.json({ id: result.lastInsertRowid }, { status: 201 });
}
