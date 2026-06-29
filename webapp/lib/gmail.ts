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

export async function fetchThreads(accessToken: string, maxResults = 20): Promise<GmailThread[]> {
  const gmail = getGmailClient(accessToken);

  const listRes = await gmail.users.threads.list({
    userId: 'me',
    maxResults,
    labelIds: ['INBOX'],
  });

  const threads = listRes.data.threads ?? [];

  const results: GmailThread[] = [];
  for (const t of threads) {
    if (!t.id) continue;
    try {
      const detail = await gmail.users.threads.get({ userId: 'me', id: t.id, format: 'full' });
      const msgs = detail.data.messages ?? [];
      if (msgs.length === 0) continue;

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
      results.push({
        threadId: t.id,
        subject: first.subject || '(件名なし)',
        from: first.from,
        snippet: detail.data.snippet ?? '',
        date: last.date,
        messageCount: msgs.length,
        messages,
      });
    } catch {
      // スキップ
    }
  }
  return results;
}
