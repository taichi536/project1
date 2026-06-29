'use client';
import { useState } from 'react';
import { Sparkles, Copy, Check } from 'lucide-react';

type GenType = 'outreach' | 'reply' | 'followup' | 'proposal' | 'report';

const TYPES: { key: GenType; label: string; description: string }[] = [
  { key: 'outreach', label: 'アウトリーチ', description: '初めて連絡する相手へのメール' },
  { key: 'reply', label: '返信', description: '受け取ったメッセージへの返信' },
  { key: 'followup', label: 'フォローアップ', description: '返信がない相手への再連絡' },
  { key: 'proposal', label: '提案・営業', description: '商品・サービス・アイデアの提案' },
  { key: 'report', label: '業務報告', description: '進捗・完了報告の文章作成' },
];

type FormState = Record<string, string>;

const FORM_FIELDS: Record<GenType, { key: string; placeholder: string; multiline?: boolean; span2?: boolean }[]> = {
  outreach: [
    { key: 'name', placeholder: '相手の名前' },
    { key: 'company', placeholder: '相手の会社・組織' },
    { key: 'role', placeholder: '相手の役職・業務内容' },
    { key: 'purpose', placeholder: '連絡の目的（例：打ち合わせ打診、情報提供）' },
    { key: 'point', placeholder: '相手に合わせて触れたいポイント', span2: true },
  ],
  reply: [
    { key: 'original', placeholder: '元のメッセージを貼り付け', multiline: true, span2: true },
    { key: 'situation', placeholder: '状況・補足（例：対応中、確認が必要）', span2: true },
  ],
  followup: [
    { key: 'name', placeholder: '相手の名前' },
    { key: 'company', placeholder: '相手の会社・組織' },
    { key: 'lastContact', placeholder: '前回の連絡内容（例：提案メールを送付）' },
    { key: 'elapsed', placeholder: '経過期間（例：1週間、10日）' },
  ],
  proposal: [
    { key: 'name', placeholder: '相手の名前' },
    { key: 'company', placeholder: '相手の会社・組織' },
    { key: 'problem', placeholder: '相手の課題・ニーズ' },
    { key: 'value', placeholder: '提供できる価値・内容' },
    { key: 'next', placeholder: '次のステップ（例：30分の打ち合わせをご提案）', span2: true },
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
  const [result, setResult] = useState('');
  const [copied, setCopied] = useState(false);
  const [form, setForm] = useState<FormState>({});

  const handleTypeChange = (t: GenType) => {
    setType(t);
    setForm({});
    setResult('');
  };

  const generate = async () => {
    setLoading(true);
    setResult('');
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, context: form }),
    });
    const data = await res.json();
    setResult(data.text);
    setLoading(false);
  };

  const copy = () => {
    navigator.clipboard.writeText(result);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const fields = FORM_FIELDS[type];

  return (
    <div className="max-w-2xl">
      <h2 className="text-2xl font-bold mb-2">AIビジネス文面生成</h2>
      <p className="text-sm text-gray-400 mb-6">業種・業務を問わず、あらゆるビジネス文書をAIが生成します</p>

      {/* 種別選択 */}
      <div className="grid grid-cols-5 gap-2 mb-6">
        {TYPES.map(({ key, label, description }) => (
          <button
            key={key}
            onClick={() => handleTypeChange(key)}
            className={`flex flex-col items-center p-3 rounded-xl text-sm border transition-colors ${
              type === key
                ? 'bg-indigo-600 text-white border-indigo-600'
                : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
            }`}
          >
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
              <textarea
                key={key}
                placeholder={placeholder}
                value={form[key] ?? ''}
                onChange={e => setForm({ ...form, [key]: e.target.value })}
                className={`border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none ${span2 ? 'col-span-2' : ''}`}
                rows={3}
              />
            ) : (
              <input
                key={key}
                placeholder={placeholder}
                value={form[key] ?? ''}
                onChange={e => setForm({ ...form, [key]: e.target.value })}
                className={`border border-gray-200 rounded-lg px-3 py-2 text-sm ${span2 ? 'col-span-2' : ''}`}
              />
            )
          )}
        </div>
      </div>

      <button
        onClick={generate}
        disabled={loading}
        className="flex items-center gap-2 px-6 py-3 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 mb-6"
      >
        <Sparkles size={16} />
        {loading ? '生成中...' : 'AIで生成する'}
      </button>

      {result && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex justify-between items-center mb-3">
            <h3 className="font-semibold text-sm text-gray-600">生成結果</h3>
            <button onClick={copy} className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600">
              {copied ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
              {copied ? 'コピー済み' : 'コピー'}
            </button>
          </div>
          <pre className="text-sm whitespace-pre-wrap text-gray-700 leading-relaxed">{result}</pre>
        </div>
      )}
    </div>
  );
}
