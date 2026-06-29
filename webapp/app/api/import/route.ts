import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

type Row = Record<string, string>;

// ヘッダーの揺れを正規化するマッピング
const FIELD_MAP: Record<string, string> = {
  // 連絡先
  '名前': 'name', 'name': 'name', '氏名': 'name', '相手': 'name', '候補者名': 'name',
  '会社': 'company', 'company': 'company', '会社名': 'company', '企業名': 'company',
  '役職': 'role', 'role': 'role', 'ポジション': 'role', '職種': 'role',
  'メール': 'email', 'email': 'email', 'メールアドレス': 'email',
  'プラットフォーム': 'platform', 'platform': 'platform', 'サービス': 'platform',
  // コミュニケーション
  '件名': 'subject', 'subject': 'subject', 'タイトル': 'subject',
  '本文': 'body', 'body': 'body', '内容': 'body', 'メッセージ': 'body',
  'ステータス': 'status', 'status': 'status', '状態': 'status', '対応状況': 'status',
  '担当者': 'assigned_to', 'assigned_to': 'assigned_to', '担当': 'assigned_to',
  '送信日': 'sent_at', '送付日': 'sent_at', '日付': 'sent_at', 'date': 'sent_at',
  '種別': 'type', 'type': 'type', '区分': 'type',
  'メモ': 'notes', 'notes': 'notes', '備考': 'notes',
};

const STATUS_MAP: Record<string, string> = {
  '未対応': 'pending', '未送信': 'pending', '待機': 'pending',
  '対応中': 'in_progress', '進行中': 'in_progress', '送信済': 'in_progress',
  '完了': 'done', '対応済': 'done', '済': 'done',
  '返信なし': 'no_reply', '無返信': 'no_reply',
};

// 種別はそのままの文字列を保存（汎用）
const TYPE_MAP: Record<string, string> = {};

function parseCSV(text: string): Row[] {
  const lines = text.trim().split('\n').map(l => l.trimEnd());
  if (lines.length < 2) return [];

  const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''));
  return lines.slice(1).map(line => {
    const values = line.match(/(".*?"|[^,]+|(?<=,)(?=,)|^(?=,)|(?<=,)$)/g) ?? line.split(',');
    const row: Row = {};
    headers.forEach((h, i) => {
      row[h] = (values[i] ?? '').trim().replace(/^"|"$/g, '');
    });
    return row;
  }).filter(row => Object.values(row).some(v => v !== ''));
}

function normalizeRow(row: Row): { contact: Row; comm: Row } {
  const contact: Row = {};
  const comm: Row = {};

  for (const [rawKey, value] of Object.entries(row)) {
    const normalized = FIELD_MAP[rawKey] ?? FIELD_MAP[rawKey.toLowerCase()];
    if (!normalized || !value) continue;

    if (['name', 'company', 'role', 'email', 'platform'].includes(normalized)) {
      contact[normalized] = value;
    } else if (normalized === 'notes') {
      contact[normalized] = value;
    } else {
      if (normalized === 'status') {
        comm[normalized] = STATUS_MAP[value] ?? 'pending';
      } else if (normalized === 'type') {
        comm[normalized] = TYPE_MAP[value] ?? value ?? 'メール';
      } else {
        comm[normalized] = value;
      }
    }
  }

  return { contact, comm };
}

export async function POST(req: NextRequest) {
  const formData = await req.formData();
  const file = formData.get('file') as File | null;

  if (!file) return NextResponse.json({ error: 'ファイルが見つかりません' }, { status: 400 });

  const text = await file.text();
  const rows = parseCSV(text);

  if (rows.length === 0) return NextResponse.json({ error: '有効なデータが見つかりません' }, { status: 400 });

  const db = getDb();
  let imported = 0;
  const errors: string[] = [];

  for (let i = 0; i < rows.length; i++) {
    try {
      const { contact, comm } = normalizeRow(rows[i]);
      if (!contact.name && !comm.subject) continue;

      let contactId: number | bigint | null = null;
      if (contact.name) {
        const existing = db.prepare(`SELECT id FROM contacts WHERE name = ? AND company IS ?`)
          .get(contact.name, contact.company ?? null) as { id: number } | undefined;

        if (existing) {
          contactId = existing.id;
        } else {
          const result = db.prepare(
            `INSERT INTO contacts (name, company, role, email, platform, notes) VALUES (?, ?, ?, ?, ?, ?)`
          ).run(contact.name, contact.company ?? null, contact.role ?? null, contact.email ?? null, contact.platform ?? null, contact.notes ?? null);
          contactId = result.lastInsertRowid;
        }
      }

      db.prepare(`
        INSERT INTO communications (contact_id, type, direction, subject, body, status, assigned_to, sent_at)
        VALUES (?, ?, 'outbound', ?, ?, ?, ?, ?)
      `).run(
        contactId,
        comm.type ?? 'email',
        comm.subject ?? null,
        comm.body ?? null,
        comm.status ?? 'pending',
        comm.assigned_to ?? null,
        comm.sent_at ?? null,
      );

      imported++;
    } catch (e) {
      errors.push(`行 ${i + 2}: ${(e as Error).message}`);
    }
  }

  return NextResponse.json({ imported, total: rows.length, errors });
}
