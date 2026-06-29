import { google } from 'googleapis';
// TextDecoder covers ISO-2022-JP and Shift-JIS natively in Node.js 18+

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

function decodeBody(part: { mimeType?: string; body?: { data?: string }; parts?: unknown[]; headers?: { name?: string | null; value?: string | null }[] }): string {
  if (part.body?.data) {
    const buf = Buffer.from(part.body.data, 'base64');

    // Content-Typeからcharsetを取得
    const contentType = getHeader(part.headers ?? [], 'Content-Type');
    const charsetMatch = contentType.match(/charset=["']?([^"';\s]+)/i);
    const charset = charsetMatch?.[1]?.toLowerCase() ?? 'utf-8';

    // 日本語エンコーディング対応（TextDecoderはNode.js 18+で標準対応）
    if (charset && charset !== 'utf-8' && charset !== 'utf8') {
      try {
        return new TextDecoder(charset).decode(buf);
      } catch {
        // 未知のcharsetはUTF-8にフォールバック
      }
    }

    // UTF-8試行
    const text = buf.toString('utf-8');
    const replacements = (text.match(/�/g) ?? []).length;
    if (replacements > 3) {
      try { return new TextDecoder('iso-2022-jp').decode(buf); } catch { return text; }
    }
    return text;
  }

  if (part.parts) {
    // text/plainを優先
    for (const p of part.parts as typeof part[]) {
      if (p.mimeType === 'text/plain') {
        const text = decodeBody(p);
        if (text.trim()) return text;
      }
    }
    // multipart/alternativeなど再帰
    for (const p of part.parts as typeof part[]) {
      if ((p.mimeType ?? '').startsWith('multipart/')) {
        const text = decodeBody(p);
        if (text.trim()) return text;
      }
    }
    // text/htmlをフォールバック
    for (const p of part.parts as typeof part[]) {
      if (p.mimeType === 'text/html') {
        const text = decodeBody(p);
        if (text.trim()) return text.replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
      }
    }
  }
  return '';
}

// 一覧取得：metadataのみ（高速）
export async function fetchThreadList(accessToken: string, maxResults = 200): Promise<GmailThread[]> {
  const gmail = getGmailClient(accessToken);

  const threads: { id?: string | null }[] = [];
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

  // metadata形式で並列取得
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
        body: m.payload ? decodeBody({ ...m.payload, headers } as Parameters<typeof decodeBody>[0]) : '',
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

// メール送信
export async function sendEmail(accessToken: string, params: {
  to: string;
  subject: string;
  body: string;
  threadId?: string;
  inReplyTo?: string;
  references?: string;
}): Promise<void> {
  const gmail = getGmailClient(accessToken);

  const headers = [
    `To: ${params.to}`,
    `Subject: =?UTF-8?B?${Buffer.from(params.subject).toString('base64')}?=`,
    'MIME-Version: 1.0',
    'Content-Type: text/plain; charset=UTF-8',
    'Content-Transfer-Encoding: base64',
  ];
  if (params.inReplyTo) headers.push(`In-Reply-To: ${params.inReplyTo}`);
  if (params.references) headers.push(`References: ${params.references}`);

  const raw = Buffer.from(
    headers.join('\r\n') + '\r\n\r\n' + params.body
  ).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

  await gmail.users.messages.send({
    userId: 'me',
    requestBody: {
      raw,
      ...(params.threadId ? { threadId: params.threadId } : {}),
    },
  });
}

export async function fetchThreads(accessToken: string, maxResults = 20): Promise<GmailThread[]> {
  return fetchThreadList(accessToken, maxResults);
}
