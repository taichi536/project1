import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const db = getDb();
  const { id } = await params;
  const body = await req.json();

  const fields = Object.keys(body).map(k => `${k} = ?`).join(', ');
  const values = [...Object.values(body), id];

  db.prepare(`UPDATE communications SET ${fields} WHERE id = ?`).run(...values);
  return NextResponse.json({ success: true });
}

export async function DELETE(_: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const db = getDb();
  const { id } = await params;
  db.prepare(`DELETE FROM communications WHERE id = ?`).run(id);
  return NextResponse.json({ success: true });
}
