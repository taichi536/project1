'use client';
import { useEffect, useState } from 'react';
import { Plus, RefreshCw } from 'lucide-react';

type Communication = {
  id: number;
  contact_name: string;
  company: string;
  platform: string;
  type: string;
  direction: string;
  subject: string;
  body: string;
  status: string;
  assigned_to: string;
  sent_at: string;
  replied_at: string;
  created_at: string;
};

const statusLabel: Record<string, string> = {
  pending: '未対応',
  in_progress: '対応中',
  done: '完了',
  no_reply: '返信なし',
};

const statusColor: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  in_progress: 'bg-blue-100 text-blue-800',
  done: 'bg-green-100 text-green-800',
  no_reply: 'bg-gray-100 text-gray-600',
};

const statusOptions = ['pending', 'in_progress', 'done', 'no_reply'];

export default function CommunicationsPage() {
  const [items, setItems] = useState<Communication[]>([]);
  const [filterStatus, setFilterStatus] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    contact_name: '', company: '', platform: '', type: 'scout',
    direction: 'outbound', subject: '', body: '', assigned_to: '', sent_at: '',
  });

  const load = () => {
    const q = filterStatus ? `?status=${filterStatus}` : '';
    fetch(`/api/communications${q}`).then(r => r.json()).then(setItems);
  };

  useEffect(() => { load(); }, [filterStatus]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await fetch('/api/communications', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form) });
    setShowForm(false);
    setForm({ contact_name: '', company: '', platform: '', type: 'scout', direction: 'outbound', subject: '', body: '', assigned_to: '', sent_at: '' });
    load();
  };

  const updateStatus = async (id: number, status: string) => {
    await fetch(`/api/communications/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) });
    load();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">コミュニケーション管理</h2>
        <div className="flex gap-2">
          <button onClick={load} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-100">
            <RefreshCw size={16} />
          </button>
          <button onClick={() => setShowForm(true)} className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700">
            <Plus size={16} /> 新規登録
          </button>
        </div>
      </div>

      {/* フィルター */}
      <div className="flex gap-2 mb-4">
        <button onClick={() => setFilterStatus('')} className={`px-3 py-1 rounded-full text-sm ${!filterStatus ? 'bg-indigo-600 text-white' : 'bg-white border border-gray-200 text-gray-600'}`}>すべて</button>
        {statusOptions.map(s => (
          <button key={s} onClick={() => setFilterStatus(s)} className={`px-3 py-1 rounded-full text-sm ${filterStatus === s ? 'bg-indigo-600 text-white' : 'bg-white border border-gray-200 text-gray-600'}`}>
            {statusLabel[s]}
          </button>
        ))}
      </div>

      {/* 新規登録フォーム */}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <form onSubmit={handleSubmit} className="bg-white rounded-xl p-6 w-full max-w-lg shadow-xl">
            <h3 className="font-semibold text-lg mb-4">コミュニケーション登録</h3>
            <div className="grid grid-cols-2 gap-3 mb-3">
              <input required placeholder="相手の名前" value={form.contact_name} onChange={e => setForm({ ...form, contact_name: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm" />
              <input placeholder="会社名" value={form.company} onChange={e => setForm({ ...form, company: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm" />
              <select value={form.type} onChange={e => setForm({ ...form, type: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm">
                <option value="scout">スカウト</option>
                <option value="email">メール</option>
                <option value="slack">Slack</option>
                <option value="other">その他</option>
              </select>
              <input placeholder="プラットフォーム (例: BizReach)" value={form.platform} onChange={e => setForm({ ...form, platform: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm" />
              <input placeholder="件名" value={form.subject} onChange={e => setForm({ ...form, subject: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm col-span-2" />
              <input placeholder="担当者" value={form.assigned_to} onChange={e => setForm({ ...form, assigned_to: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm" />
              <input type="datetime-local" value={form.sent_at} onChange={e => setForm({ ...form, sent_at: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm" />
            </div>
            <textarea placeholder="本文" value={form.body} onChange={e => setForm({ ...form, body: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm w-full mb-4" rows={4} />
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg">キャンセル</button>
              <button type="submit" className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700">登録</button>
            </div>
          </form>
        </div>
      )}

      {/* 一覧テーブル */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {items.length === 0 ? (
          <p className="text-center text-gray-400 py-12 text-sm">データがありません</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr className="text-left text-gray-400">
                <th className="px-4 py-3 font-medium">相手</th>
                <th className="px-4 py-3 font-medium">種別</th>
                <th className="px-4 py-3 font-medium">件名</th>
                <th className="px-4 py-3 font-medium">担当者</th>
                <th className="px-4 py-3 font-medium">ステータス</th>
                <th className="px-4 py-3 font-medium">送信日時</th>
              </tr>
            </thead>
            <tbody>
              {items.map(item => (
                <tr key={item.id} className="border-b border-gray-50 hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <div className="font-medium">{item.contact_name ?? '—'}</div>
                    {item.company && <div className="text-xs text-gray-400">{item.company}</div>}
                    {item.platform && <div className="text-xs text-indigo-400">{item.platform}</div>}
                  </td>
                  <td className="px-4 py-3 text-gray-500">{item.type}</td>
                  <td className="px-4 py-3 max-w-xs truncate">{item.subject ?? '—'}</td>
                  <td className="px-4 py-3 text-gray-500">{item.assigned_to ?? '—'}</td>
                  <td className="px-4 py-3">
                    <select
                      value={item.status}
                      onChange={e => updateStatus(item.id, e.target.value)}
                      className={`px-2 py-0.5 rounded-full text-xs border-0 cursor-pointer ${statusColor[item.status]}`}
                    >
                      {statusOptions.map(s => <option key={s} value={s}>{statusLabel[s]}</option>)}
                    </select>
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{item.sent_at?.slice(0, 16) ?? item.created_at?.slice(0, 16)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
