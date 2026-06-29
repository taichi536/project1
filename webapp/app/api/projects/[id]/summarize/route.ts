import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { getDb } from '@/lib/db';
import { fetchThreads } from '@/lib/gmail';
import Anthropic from '@anthropic-ai/sdk';

const client = new Anthropic();

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  if (!session.accessToken) {
    return NextResponse.json({ error: 'Gmail未連携', needsAuth: true }, { status: 403 });
  }

  const { id } = await params;
  const db = getDb();

  const project = db.prepare(`SELECT * FROM projects WHERE id = ? AND user_id = ?`).get(id, session.user.id) as { name: string } | undefined;
  if (!project) return NextResponse.json({ error: 'Not found' }, { status: 404 });

  const dbThreads = db.prepare(`SELECT thread_id FROM gmail_threads WHERE project_id = ?`).all(id) as { thread_id: string }[];
  const threadIds = new Set(dbThreads.map(t => t.thread_id));

  // Gmailからスレッド内容を取得
  const allThreads = await fetchThreads(session.accessToken, 50);
  const projectThreads = allThreads.filter(t => threadIds.has(t.threadId));

  if (projectThreads.length === 0) {
    return NextResponse.json({ error: 'このプロジェクトにメールが紐付けられていません' }, { status: 400 });
  }

  // メール内容をテキスト化
  const emailText = projectThreads.map(t => {
    const msgs = t.messages.map(m =>
      `[${m.date}] From: ${m.from}\n${m.body.slice(0, 500)}`
    ).join('\n---\n');
    return `【スレッド: ${t.subject}】\n${msgs}`;
  }).join('\n\n===\n\n');

  const { type } = await req.json().catch(() => ({ type: 'summary' }));

  let prompt = '';
  if (type === 'reply') {
    prompt = `以下は案件「${project.name}」に関するメールのやり取りです。
最後のメールへの返信文を日本語のビジネスメールとして作成してください。
簡潔で丁寧な返信を作成してください。

${emailText}

返信文のみを出力してください。`;
  } else {
    prompt = `以下は案件「${project.name}」に関するメールのやり取りです。
以下の項目を簡潔にまとめてください：

1. **現在の状況**: 案件の進捗を1〜2文で
2. **未返信のメール**: 返信が必要なメールがあれば相手と件名を列挙
3. **次にすべきアクション**: 具体的に何をすべきか

${emailText}`;
  }

  const response = await client.messages.create({
    model: 'claude-haiku-4-5-20251001',
    max_tokens: 1024,
    messages: [{ role: 'user', content: prompt }],
  });

  const result = response.content[0].type === 'text' ? response.content[0].text : '';
  return NextResponse.json({ result, type });
}
