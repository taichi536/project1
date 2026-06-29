import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const db = getDb();
  const { id } = await params;
  const body = await req.json();
  const fields = Object.keys(body).map(k => `${k} = ?`).join(', ');
  db.prepare(`UPDATE tasks SET ${fields} WHERE id = ?`).run(...Object.values(body), id);
  return NextResponse.json({ success: true });
}

export async function DELETE(_: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const db = getDb();
  const { id } = await params;
  db.prepare(`DELETE FROM tasks WHERE id = ?`).run(id);
  return NextResponse.json({ success: true });
}
