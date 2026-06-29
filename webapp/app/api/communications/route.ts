import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET(req: NextRequest) {
  const db = getDb();
  const { searchParams } = new URL(req.url);
  const status = searchParams.get('status');
  const type = searchParams.get('type');

  let query = `
    SELECT c.*, co.name as contact_name, co.company, co.platform
    FROM communications c
    LEFT JOIN contacts co ON c.contact_id = co.id
    WHERE 1=1
  `;
  const params: string[] = [];

  if (status) { query += ` AND c.status = ?`; params.push(status); }
  if (type) { query += ` AND c.type = ?`; params.push(type); }

  query += ` ORDER BY c.created_at DESC`;

  const rows = db.prepare(query).all(...params);
  return NextResponse.json(rows);
}

export async function POST(req: NextRequest) {
  const db = getDb();
  const body = await req.json();

  // 連絡先が存在しない場合は新規作成
  let contactId = body.contact_id;
  if (!contactId && body.contact_name) {
    const result = db.prepare(
      `INSERT INTO contacts (name, company, role, email, platform) VALUES (?, ?, ?, ?, ?)`
    ).run(body.contact_name, body.company || null, body.role || null, body.email || null, body.platform || null);
    contactId = result.lastInsertRowid;
  }

  const result = db.prepare(`
    INSERT INTO communications (contact_id, type, direction, subject, body, status, assigned_to, sent_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    contactId || null,
    body.type || 'email',
    body.direction || 'outbound',
    body.subject || null,
    body.body || null,
    body.status || 'pending',
    body.assigned_to || null,
    body.sent_at || null,
  );

  return NextResponse.json({ id: result.lastInsertRowid }, { status: 201 });
}
