import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { fetchThreads } from '@/lib/gmail';
import { getDb } from '@/lib/db';
import Anthropic from '@anthropic-ai/sdk';

const client = new Anthropic();

export async function GET(_req: NextRequest, { params }: { params: Promise<{ threadId: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  if (!session.accessToken) return NextResponse.json({ error: 'Gmail未連携', needsAuth: true }, { status: 403 });

  const { threadId } = await params;

  try {
    const threads = await fetchThreads(session.accessToken, 50);
    const thread = threads.find(t => t.threadId === threadId);
    if (!thread) return NextResponse.json({ error: 'Not found' }, { status: 404 });

    const db = getDb();
    const meta = db.prepare(`
      SELECT tc.*, d.name as deal_name, u.name as assignee_name
      FROM thread_cache tc
      LEFT JOIN deals d ON d.id = tc.deal_id
      LEFT JOIN users u ON u.id = tc.assigned_to
      WHERE tc.thread_id = ? AND tc.user_id = ?
    `).get(threadId, session.user.id) as Record<string, unknown> | undefined;

    return NextResponse.json({ thread, meta });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'unknown';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ threadId: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const { threadId } = await params;
  const body = await req.json();
  const db = getDb();

  const fields: string[] = [];
  const values: unknown[] = [];

  if (body.is_done !== undefined) { fields.push('is_done = ?'); values.push(body.is_done ? 1 : 0); }
  if (body.assigned_to !== undefined) { fields.push('assigned_to = ?'); values.push(body.assigned_to); }
  if (body.deal_id !== undefined) { fields.push('deal_id = ?'); values.push(body.deal_id); }

  if (fields.length > 0) {
    values.push(threadId, session.user.id);
    db.prepare(`UPDATE thread_cache SET ${fields.join(', ')} WHERE thread_id = ? AND user_id = ?`).run(...values);
  }

  return NextResponse.json({ success: true });
}

export async function POST(req: NextRequest, { params }: { params: Promise<{ threadId: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  if (!session.accessToken) return NextResponse.json({ error: 'Gmail未連携' }, { status: 403 });

  const { threadId } = await params;
  const { type } = await req.json();

  const threads = await fetchThreads(session.accessToken, 50);
  const thread = threads.find(t => t.threadId === threadId);
  if (!thread) return NextResponse.json({ error: 'Not found' }, { status: 404 });

  const emailText = thread.messages.map(m =>
    `[${m.date}]\nFrom: ${m.from}\nTo: ${m.to}\n\n${m.body.slice(0, 800)}`
  ).join('\n\n---\n\n');

  let prompt = '';
  if (type === 'reply') {
    prompt = `以下のメールのやり取りを読んで、最後のメールへの返信文を日本語のビジネスメールとして作成してください。簡潔で丁寧にお願いします。返信文のみ出力してください。\n\n${emailText}`;
  } else if (type === 'summary') {
    prompt = `以下のメールのやり取りを読んで、以下をまとめてください：\n1. 現在の状況（1〜2文）\n2. 返信・対応が必要なことがあれば\n3. 次のアクション\n\n${emailText}`;
  } else if (type === 'task') {
    prompt = `以下のメールのやり取りを読んで、対応が必要なタスクを箇条書きで3つ以内にまとめてください。\n\n${emailText}`;
  }

  const response = await client.messages.create({
    model: 'claude-haiku-4-5-20251001',
    max_tokens: 1024,
    messages: [{ role: 'user', content: prompt }],
  });

  const result = response.content[0].type === 'text' ? response.content[0].text : '';
  return NextResponse.json({ result });
}
