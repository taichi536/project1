import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { sendSlackNotification, buildOverdueAlert } from '@/lib/slack';

// 要フォローアップ案件をSlackに通知する
export async function POST(req: NextRequest) {
  const { type } = await req.json();

  if (type === 'overdue') {
    const db = getDb();
    const items = db.prepare(`
      SELECT c.subject, c.sent_at, co.name as contact_name
      FROM communications c
      LEFT JOIN contacts co ON c.contact_id = co.id
      WHERE c.status IN ('pending', 'in_progress')
        AND c.direction = 'outbound'
        AND c.sent_at < datetime('now', '-3 days', 'localtime')
    `).all() as { subject: string; sent_at: string; contact_name: string }[];

    if (items.length === 0) {
      return NextResponse.json({ message: '要フォローアップ案件はありません' });
    }

    const sent = await sendSlackNotification(buildOverdueAlert(items));
    return NextResponse.json({ sent, count: items.length });
  }

  return NextResponse.json({ error: '不明なtypeです' }, { status: 400 });
}
