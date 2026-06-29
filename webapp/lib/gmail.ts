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
    return Buffer.from(part.body.data, 'base64').toString('utf-8');
  }
  if (part.parts) {
    for (const p of part.parts as typeof part[]) {
      if (p.mimeType === 'text/plain') {
        const text = decodeBody(p);
        if (text) return text;
      }
    }
    for (const p of part.parts as typeof part[]) {
      const text = decodeBody(p);
      if (text) return text;
    }
  }
  return '';
}

// 一覧取得：metadataのみ（高速）
export async function fetchThreadList(accessToken: string, maxResults = 50): Promise<GmailThread[]> {
  const gmail = getGmailClient(accessToken);

  const listRes = await gmail.users.threads.list({
    userId: 'me',
    maxResults,
    labelIds: ['INBOX'],
  });

  const threads = listRes.data.threads ?? [];

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
