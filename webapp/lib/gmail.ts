import { google } from 'googleapis';

export function getGmailClient(accessToken: string) {
  const auth = new google.auth.OAuth2();
  auth.setCredentials({ access_token: accessToken });
  return google.gmail({ version: 'v1', auth });
}

export type GmailThread = {
  threadId: string;
  subject: string;
  from: string;
  lastFrom: string;
  snippet: string;
  date: string;
  messageCount: number;
  messages: GmailMessage[];
};

export type GmailMessage = {
  id: string;
  from: string;
  to: string;
  subject: string;
  date: string;
  body: string;
};

function getHeader(headers: { name?: string | null; value?: string | null }[], name: string): string {
  return headers.find(h => h.name?.toLowerCase() === name.toLowerCase())?.value ?? '';
}

function decodeBody(part: { mimeType?: string; body?: { data?: string }; parts?: unknown[] }): string {
  if (part.body?.data) {
    const buf = Buffer.from(part.body.data, 'base64');
    // UTF-8で読めるか試みる、失敗したらlatin1で読む（文字化け回避）
    const text = buf.toString('utf-8');
    // 文字化けチェック：置換文字(U+FFFD)が多い場合はlatin1にフォールバック
    const replacements = (text.match(/�/g) ?? []).length;
    if (replacements > 5) {
      return buf.toString('latin1');
    }
    return text;
  }
  if (part.parts) {
    // text/plainを優先
    for (const p of part.parts as typeof part[]) {
      if (p.mimeType === 'text/plain') {
        const text = decodeBody(p);
        if (text) return text;
      }
    }
    // text/htmlも試みる
    for (const p of part.parts as typeof part[]) {
      if (p.mimeType === 'text/html') {
        const text = decodeBody(p);
        if (text) return text.replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').replace(/&lt;/g, '<').replace(/&gt;/g, '>');
      }
    }
    // ネストされたパートを再帰
    for (const p of part.parts as typeof part[]) {
      const text = decodeBody(p);
      if (text) return text;
    }
  }
  return '';
}

// 一覧取得：metadataのみ（高速）
export async function fetchThreadList(accessToken: string, maxResults = 200): Promise<GmailThread[]> {
  const gmail = getGmailClient(accessToken);

  // ページネーションで全件取得
  const threads: { id?: string | null; historyId?: string | null }[] = [];
  let pageToken: string | undefined = undefined;
  const perPage = 100;

  while (threads.length < maxResults) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const listRes: any = await gmail.users.threads.list({
      userId: 'me',
      maxResults: Math.min(perPage, maxResults - threads.length),
      labelIds: ['INBOX'],
      pageToken,
    });
    threads.push(...(listRes.data.threads ?? []));
    if (!listRes.data.nextPageToken || threads.length >= maxResults) break;
    pageToken = listRes.data.nextPageToken;
  }

  // metadata形式で並列取得（本文なし）
  const results = await Promise.all(
    threads.filter(t => t.id).map(async t => {
      try {
        const detail = await gmail.users.threads.get({
          userId: 'me',
          id: t.id!,
          format: 'metadata',
          metadataHeaders: ['From', 'To', 'Subject', 'Date'],
        });
        const msgs = detail.data.messages ?? [];
        if (msgs.length === 0) return null;

        const firstHeaders = msgs[0].payload?.headers ?? [];
        const lastHeaders = msgs[msgs.length - 1].payload?.headers ?? [];

        return {
          threadId: t.id!,
          subject: getHeader(firstHeaders, 'Subject') || '(件名なし)',
          from: getHeader(firstHeaders, 'From'),
          snippet: detail.data.snippet ?? '',
          date: getHeader(lastHeaders, 'Date'),
          messageCount: msgs.length,
          lastFrom: getHeader(lastHeaders, 'From'),
          messages: [],
        };
      } catch {
        return null;
      }
    })
  );

  return results.filter(Boolean) as GmailThread[];
}

// 1スレッドの本文取得（クリック時）
export async function fetchThreadDetail(accessToken: string, threadId: string): Promise<GmailThread | null> {
  const gmail = getGmailClient(accessToken);

  try {
    const detail = await gmail.users.threads.get({
      userId: 'me',
      id: threadId,
      format: 'full',
    });

    const msgs = detail.data.messages ?? [];
    if (msgs.length === 0) return null;

    const messages: GmailMessage[] = msgs.map(m => {
      const headers = m.payload?.headers ?? [];
      return {
        id: m.id ?? '',
        from: getHeader(headers, 'From'),
        to: getHeader(headers, 'To'),
        subject: getHeader(headers, 'Subject'),
        date: getHeader(headers, 'Date'),
        body: m.payload ? decodeBody(m.payload as Parameters<typeof decodeBody>[0]) : '',
      };
    });

    const first = messages[0];
    const last = messages[messages.length - 1];
    return {
      threadId,
      subject: first.subject || '(件名なし)',
      from: first.from,
      lastFrom: last.from,
      snippet: detail.data.snippet ?? '',
      date: last.date,
      messageCount: msgs.length,
      messages,
    };
  } catch {
    return null;
  }
}

// 後方互換（既存コードが使っている場合）
export async function fetchThreads(accessToken: string, maxResults = 20): Promise<GmailThread[]> {
  return fetchThreadList(accessToken, maxResults);
}
