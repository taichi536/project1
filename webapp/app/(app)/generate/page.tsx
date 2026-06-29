'use client';
import { useState } from 'react';
import { Sparkles, Copy, Check, Save } from 'lucide-react';

type GenType = 'outreach' | 'reply' | 'followup' | 'proposal' | 'report';

const TYPES: { key: GenType; label: string; description: string }[] = [
  { key: 'outreach', label: 'アウトリーチ', description: '初めて連絡する相手へ' },
  { key: 'reply', label: '返信', description: '受け取ったメッセージへ' },
  { key: 'followup', label: 'フォローアップ', description: '返信がない相手へ' },
  { key: 'proposal', label: '提案・営業', description: '商品・サービスの提案' },
  { key: 'report', label: '業務報告', description: '進捗・完了の報告' },
];

type FormState = Record<string, string>;

const FORM_FIELDS: Record<GenType, { key: string; placeholder: string; multiline?: boolean; span2?: boolean }[]> = {
  outreach: [
    { key: 'name', placeholder: '相手の名前' },
    { key: 'company', placeholder: '相手の会社・組織' },
    { key: 'role', placeholder: '相手の役職・業務内容' },
    { key: 'purpose', placeholder: '連絡の目的（例：打ち合わせ打診）' },
    { key: 'point', placeholder: '相手に合わせて触れたいポイント', span2: true },
  ],
  reply: [
    { key: 'original', placeholder: '元のメッセージを貼り付け', multiline: true, span2: true },
    { key: 'situation', placeholder: '補足（例：確認中、対応済み）', span2: true },
  ],
  followup: [
    { key: 'name', placeholder: '相手の名前' },
    { key: 'company', placeholder: '相手の会社・組織' },
    { key: 'lastContact', placeholder: '前回の連絡内容' },
    { key: 'elapsed', placeholder: '経過期間（例：1週間）' },
  ],
  proposal: [
    { key: 'name', placeholder: '相手の名前' },
    { key: 'company', placeholder: '相手の会社・組織' },
    { key: 'problem', placeholder: '相手の課題・ニーズ' },
    { key: 'value', placeholder: '提供できる価値・内容' },
    { key: 'next', placeholder: '次のステップ（例：30分の打ち合わせ）', span2: true },
  ],
  report: [
    { key: 'to', placeholder: '報告先（例：上司、チーム）' },
    { key: 'period', placeholder: '対象期間（例：今週、6月）' },
    { key: 'done', placeholder: '完了事項', multiline: true, span2: true },
    { key: 'inProgress', placeholder: '進行中の事項', multiline: true, span2: true },
    { key: 'issues', placeholder: '課題・懸念点（任意）', span2: true },
  ],
};

export default function GeneratePage() {
  const [type, setType] = useState<GenType>('outreach');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState('');
  const [subject, setSubject] = useState('');
  const [copied, setCopied] = useState(false);
  const [saved, setSaved] = useState(false);
  const [form, setForm] = useState<FormState>({});

  const handleTypeChange = (t: GenType) => {
    setType(t);
    setForm({});
    setResult('');
    setSubject('');
    setSaved(false);
  };

  const generate = async () => {
    setLoading(true);
    setResult('');
    setSaved(false);
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, context: form }),
    });
    const data = await res.json();
    setResult(data.text);
    // 件名を自動抽出（「件名：〜」形式に対応）
    const subjectMatch = data.text.match(/件名[：:]\s*(.+)/);
    if (subjectMatch) setSubject(subjectMatch[1].trim());
    setLoading(false);
  };

  const copy = () => {
    navigator.clipboard.writeText(result);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const saveAsRecord = async () => {
    setSaving(true);
    const contactName = form.name || form.to || '不明';
    const company = form.company || '';
    await fetch('/api/communications', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contact_name: contactName,
        company,
        type: 'email',
        direction: 'outbound',
        subject: subject || `${TYPES.find(t2 => t2.key === type)?.label} - ${contactName}`,
        body: result,
        status: 'pending',
        sent_at: new Date().toISOString().slice(0, 16),
      }),
    });
    setSaved(true);
    setSaving(false);
  };

  const fields = FORM_FIELDS[type];

  return (
    <div className="max-w-2xl">
      <h2 className="text-2xl font-bold mb-1">AIビジネス文面生成</h2>
      <p className="text-sm text-gray-400 mb-6">業種・業務を問わず、あらゆるビジネス文書をAIが生成します</p>

      {/* 種別選択 */}
      <div className="grid grid-cols-5 gap-2 mb-6">
        {TYPES.map(({ key, label, description }) => (
          <button key={key} onClick={() => handleTypeChange(key)}
            className={`flex flex-col items-center p-3 rounded-xl text-sm border transition-colors ${
              type === key ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
            }`}>
            <span className="font-medium">{label}</span>
            <span className={`text-xs mt-1 text-center leading-tight ${type === key ? 'text-indigo-200' : 'text-gray-400'}`}>
              {description}
            </span>
          </button>
        ))}
      </div>

      {/* 入力フォーム */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 mb-4">
        <div className="grid grid-cols-2 gap-3">
          {fields.map(({ key, placeholder, multiline, span2 }) =>
            multiline ? (
              <textarea key={key} placeholder={placeholder} value={form[key] ?? ''}
                onChange={e => setForm({ ...form, [key]: e.target.value })}
                className={`border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none ${span2 ? 'col-span-2' : ''}`}
                rows={3} />
            ) : (
              <input key={key} placeholder={placeholder} value={form[key] ?? ''}
                onChange={e => setForm({ ...form, [key]: e.target.value })}
                className={`border border-gray-200 rounded-lg px-3 py-2 text-sm ${span2 ? 'col-span-2' : ''}`} />
            )
          )}
        </div>
      </div>

      <button onClick={generate} disabled={loading}
        className="flex items-center gap-2 px-6 py-3 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 mb-6">
        <Sparkles size={16} />
        {loading ? '生成中...' : 'AIで生成する'}
      </button>

      {result && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex justify-between items-center mb-3">
            <h3 className="font-semibold text-sm text-gray-600">生成結果</h3>
            <div className="flex gap-2">
              <button onClick={copy}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50">
                {copied ? <Check size={13} className="text-green-500" /> : <Copy size={13} />}
                {copied ? 'コピー済み' : 'コピー'}
              </button>
              <button onClick={saveAsRecord} disabled={saving || saved}
                className={`flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg font-medium transition-colors ${
                  saved ? 'bg-green-100 text-green-700 border border-green-200' : 'bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50'
                }`}>
                <Save size={13} />
                {saved ? '記録に保存済み' : saving ? '保存中...' : '記録に保存'}
              </button>
            </div>
          </div>

          {/* 件名編集 */}
          {subject && (
            <div className="mb-3 pb-3 border-b border-gray-100">
              <label className="text-xs text-gray-400 block mb-1">件名</label>
              <input value={subject} onChange={e => setSubject(e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm" />
            </div>
          )}

          <pre className="text-sm whitespace-pre-wrap text-gray-700 leading-relaxed">{result}</pre>
        </div>
      )}
    </div>
  );
}
