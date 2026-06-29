'use client';
import { useState } from 'react';
import { Sparkles, Copy, Check } from 'lucide-react';

type GenType = 'scout' | 'reply' | 'followup';

export default function GeneratePage() {
  const [type, setType] = useState<GenType>('scout');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState('');
  const [copied, setCopied] = useState(false);

  const [scoutForm, setScoutForm] = useState({ name: '', company: '', role: '', career: '', reason: '' });
  const [replyForm, setReplyForm] = useState({ original: '', situation: '' });
  const [followupForm, setFollowupForm] = useState({ name: '', company: '', role: '', lastContact: '' });

  const generate = async () => {
    setLoading(true);
    setResult('');
    const context = type === 'scout' ? scoutForm : type === 'reply' ? replyForm : followupForm;
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, context }),
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

  return (
    <div className="max-w-2xl">
      <h2 className="text-2xl font-bold mb-6">AI文面生成</h2>

      {/* タブ */}
      <div className="flex gap-2 mb-6">
        {(['scout', 'reply', 'followup'] as GenType[]).map(t => (
          <button key={t} onClick={() => setType(t)} className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${type === t ? 'bg-indigo-600 text-white' : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'}`}>
            {t === 'scout' ? 'スカウト文' : t === 'reply' ? '返信文' : 'フォローアップ'}
          </button>
        ))}
      </div>

      {/* フォーム */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 mb-4">
        {type === 'scout' && (
          <div className="grid grid-cols-2 gap-3">
            <input placeholder="候補者名" value={scoutForm.name} onChange={e => setScoutForm({ ...scoutForm, name: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm" />
            <input placeholder="現職会社" value={scoutForm.company} onChange={e => setScoutForm({ ...scoutForm, company: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm" />
            <input placeholder="現職ポジション" value={scoutForm.role} onChange={e => setScoutForm({ ...scoutForm, role: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm" />
            <input placeholder="注目したキャリアポイント" value={scoutForm.reason} onChange={e => setScoutForm({ ...scoutForm, reason: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm" />
            <textarea placeholder="職歴・スキルの概要" value={scoutForm.career} onChange={e => setScoutForm({ ...scoutForm, career: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm col-span-2" rows={3} />
          </div>
        )}
        {type === 'reply' && (
          <div className="flex flex-col gap-3">
            <textarea placeholder="元のメッセージ" value={replyForm.original} onChange={e => setReplyForm({ ...replyForm, original: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm" rows={4} />
            <input placeholder="状況・補足（例：面談調整中）" value={replyForm.situation} onChange={e => setReplyForm({ ...replyForm, situation: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm" />
          </div>
        )}
        {type === 'followup' && (
          <div className="grid grid-cols-2 gap-3">
            <input placeholder="相手の名前" value={followupForm.name} onChange={e => setFollowupForm({ ...followupForm, name: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm" />
            <input placeholder="会社名" value={followupForm.company} onChange={e => setFollowupForm({ ...followupForm, company: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm" />
            <input placeholder="ポジション" value={followupForm.role} onChange={e => setFollowupForm({ ...followupForm, role: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm" />
            <input placeholder="前回連絡日（例：2週間前）" value={followupForm.lastContact} onChange={e => setFollowupForm({ ...followupForm, lastContact: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm" />
          </div>
        )}
      </div>

      <button onClick={generate} disabled={loading} className="flex items-center gap-2 px-6 py-3 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 mb-6">
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
          <pre className="text-sm whitespace-pre-wrap text-gray-700">{result}</pre>
        </div>
      )}
    </div>
  );
}
