import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/lib/auth';

export async function POST(_req: NextRequest, { params }: { params: Promise<{ threadId: string }> }) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  if (!session.accessToken) return NextResponse.json({ error: 'Gmail未連携', needsAuth: true }, { status: 403 });

  const { threadId } = await params;

  try {
    const { google } = await import('googleapis');
    const auth2 = new google.auth.OAuth2();
    auth2.setCredentials({ access_token: session.accessToken });
    const gmail = google.gmail({ version: 'v1', auth: auth2 });

    const thread = await gmail.users.threads.get({ userId: 'me', id: threadId });
    for (const msg of thread.data.messages ?? []) {
      if (msg.labelIds?.includes('UNREAD')) {
        await gmail.users.messages.modify({
          userId: 'me',
          id: msg.id!,
          requestBody: { removeLabelIds: ['UNREAD'] },
        });
      }
    }
  } catch (e) {
    // Gmail API errors are non-fatal; log and continue
    console.error('Failed to mark as read in Gmail:', e);
  }

  return NextResponse.json({ success: true });
}
