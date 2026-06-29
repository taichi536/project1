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
      const lastFromEmail = (lastFrom.match(/<(.+?)>/)?.[1] ?? lastFrom).trim().toLowerCase();
      const myEmailLower = myEmail.trim().toLowerCase();
      // 自分のメール or myEmailが未設定 → 返信不要
      const needsReply = (myEmailLower && lastFromEmail && lastFromEmail !== myEmailLower) ? 1 : 0;

      // is_done と assigned_to は上書きしない（ユーザーが手動で変更した値を保持）
      // GmailのDate headerをISO形式に変換してソート可能にする
      const parsedDate = t.date ? new Date(t.date) : null;
      const isoDate = parsedDate && !isNaN(parsedDate.getTime()) ? parsedDate.toISOString() : t.date;

      db.prepare(`
        INSERT INTO thread_cache (user_id, thread_id, subject, snippet, from_email, last_message_at, message_count, needs_reply, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))
        ON CONFLICT(thread_id, user_id) DO UPDATE SET
          subject = excluded.subject,
          snippet = excluded.snippet,
          from_email = excluded.from_email,
          last_message_at = excluded.last_message_at,
          message_count = excluded.message_count,
          needs_reply = CASE WHEN thread_cache.is_done = 1 THEN 0 ELSE excluded.needs_reply END,
          synced_at = excluded.synced_at
      `).run(
        session.user.id, t.threadId, t.subject, t.snippet,
        t.from, isoDate, t.messageCount, needsReply
      );
    }

    // Gmailから取得したスレッドのIDセット
    const fetchedIds = new Set(threads.map(t => t.threadId));

    const cached = db.prepare(`
      SELECT tc.*, d.name as deal_name, u.name as assignee_name
      FROM thread_cache tc
      LEFT JOIN deals d ON d.id = tc.deal_id
      LEFT JOIN users u ON u.id = tc.assigned_to
      WHERE tc.user_id = ? AND tc.thread_id IN (${[...fetchedIds].map(() => '?').join(',')})
      ORDER BY tc.last_message_at DESC
    `).all(session.user.id, ...[...fetchedIds]) as Array<Record<string, unknown>>;

    const filtered = cached;

    return NextResponse.json({ threads: filtered });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'unknown';
    return NextResponse.json({ error: `Gmail取得エラー: ${msg}` }, { status: 500 });
  }
}
