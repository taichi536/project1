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
      const lastFromEmail = lastFrom.match(/<(.+?)>/)?.[1] ?? lastFrom;
      const needsReply = lastFromEmail && !lastFromEmail.toLowerCase().includes(myEmail.toLowerCase()) ? 1 : 0;

      // is_done と assigned_to は上書きしない（ユーザーが手動で変更した値を保持）
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
        t.from, t.date, t.messageCount, needsReply
      );
    }

    // Gmailから取得したスレッドのIDセット
    const fetchedIds = new Set(threads.map(t => t.threadId));

    const cached = db.prepare(`
      SELECT tc.*, d.name as deal_name, u.name as assignee_name
      FROM thread_cache tc
      LEFT JOIN deals d ON d.id = tc.deal_id
      LEFT JOIN users u ON u.id = tc.assigned_to
      WHERE tc.user_id = ?
      ORDER BY tc.last_message_at DESC
    `).all(session.user.id) as Array<Record<string, unknown>>;

    // 今回取得できたスレッドのみ返す（古いキャッシュを除外）
    const filtered = cached.filter(t => fetchedIds.has(t.thread_id as string));

    return NextResponse.json({ threads: filtered });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'unknown';
    return NextResponse.json({ error: `Gmail取得エラー: ${msg}` }, { status: 500 });
  }
}
