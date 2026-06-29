import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { sendSlackNotification, buildStatusChangeNotice } from '@/lib/slack';

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const db = getDb();
  const { id } = await params;
  const body = await req.json();

  const fields = Object.keys(body).map(k => `${k} = ?`).join(', ');
  db.prepare(`UPDATE communications SET ${fields} WHERE id = ?`).run(...Object.values(body), id);

  // ステータス変更時にSlack通知
  if (body.status) {
    const row = db.prepare(`
      SELECT c.subject, co.name as contact_name
      FROM communications c LEFT JOIN contacts co ON c.contact_id = co.id
      WHERE c.id = ?
    `).get(id) as { subject: string; contact_name: string } | undefined;

    if (row) {
      sendSlackNotification(buildStatusChangeNotice(row.contact_name, row.subject, body.status));
    }
  }

  return NextResponse.json({ success: true });
}

export async function DELETE(_: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const db = getDb();
  const { id } = await params;
  db.prepare(`DELETE FROM communications WHERE id = ?`).run(id);
  return NextResponse.json({ success: true });
}
