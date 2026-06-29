import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { sendEmail } from '@/lib/gmail';

export async function POST(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.id) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  if (!session.accessToken) return NextResponse.json({ error: 'Gmail未連携' }, { status: 403 });

  const { to, cc, bcc, subject, body } = await req.json();
  if (!to || !body) return NextResponse.json({ error: '宛先と本文は必須です' }, { status: 400 });

  await sendEmail(session.accessToken, {
    to,
    cc,
    bcc,
    subject: subject || '',
    body,
  });

  return NextResponse.json({ success: true });
}
