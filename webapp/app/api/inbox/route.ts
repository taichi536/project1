import { NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { fetchThreadList } from '@/lib/gmail';
import { getDb } from '@/lib/db';

export async function GET() {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  if (!session.accessToken) {
    return NextResponse.json({ error: 'GmailはGoogleアカウントでログインすると使えます。', needsAuth: true }, { status: 403 });
  }

  try {
    const threads = await fetchThreadList(session.accessToken, 200);
    const db = getDb();
    const myEmail = session.user.email ?? '';

    for (const t of threads) {
      const lastFrom = t.lastFrom ?? '';
      // 最後のメールが自分以外から来ている かつ 対応済みでない場合に要返信
      const needsReply = lastFrom && !lastFrom.toLowerCase().includes(myEmail.toLowerCase()) ? 1 : 0;

      db.prepare(`
        INSERT INTO thread_cache (user_id, thread_id, subject, snippet, from_email, last_message_at, message_count, needs_reply, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))
        ON CONFLICT(thread_id, user_id) DO UPDATE SET
          subject = excluded.subject,
          snippet = excluded.snippet,
          from_email = excluded.from_email,
          last_message_at = excluded.last_message_at,
          message_count = excluded.message_count,
          needs_reply = excluded.needs_reply,
          synced_at = excluded.synced_at
      `).run(
        session.user.id, t.threadId, t.subject, t.snippet,
        t.from, t.date, t.messageCount, needsReply
      );
    }

    const cached = db.prepare(`
      SELECT tc.*, d.name as deal_name, u.name as assignee_name
      FROM thread_cache tc
      LEFT JOIN deals d ON d.id = tc.deal_id
      LEFT JOIN users u ON u.id = tc.assigned_to
      WHERE tc.user_id = ?
      ORDER BY tc.last_message_at DESC
    `).all(session.user.id);

    return NextResponse.json({ threads: cached });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'unknown';
    return NextResponse.json({ error: `Gmail取得エラー: ${msg}` }, { status: 500 });
  }
}
