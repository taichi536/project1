type SlackPayload = {
  text: string;
  blocks?: object[];
};

export async function sendSlackNotification(payload: SlackPayload): Promise<boolean> {
  const webhookUrl = process.env.SLACK_WEBHOOK_URL;
  if (!webhookUrl) return false;

  try {
    const res = await fetch(webhookUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export function buildOverdueAlert(items: { contact_name: string; subject: string; sent_at: string }[]) {
  return {
    text: `⚠️ フォローアップが必要な案件が ${items.length} 件あります`,
    blocks: [
      {
        type: 'header',
        text: { type: 'plain_text', text: `⚠️ 要フォローアップ：${items.length} 件` },
      },
      {
        type: 'section',
        text: {
          type: 'mrkdwn',
          text: items.map(i =>
            `• *${i.contact_name ?? '不明'}* — ${i.subject ?? '件名なし'} (送信日: ${i.sent_at?.slice(0, 10) ?? '不明'})`
          ).join('\n'),
        },
      },
    ],
  };
}

export function buildStatusChangeNotice(contactName: string, subject: string, newStatus: string) {
  const statusLabel: Record<string, string> = {
    pending: '未対応', in_progress: '対応中', done: '完了', no_reply: '返信なし',
  };
  return {
    text: `📬 ステータス更新：${contactName} の「${subject ?? '件名なし'}」が「${statusLabel[newStatus] ?? newStatus}」になりました`,
  };
}
