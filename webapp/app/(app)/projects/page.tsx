'use client';
import { useEffect, useState } from 'react';
import { Plus, Folder, Mail, ChevronRight, AlertCircle } from 'lucide-react';
import Link from 'next/link';

type Project = {
  id: number;
  name: string;
  description: string;
  status: string;
  thread_count: number;
  unread_count: number;
  deal_thread_count: number;
  deal_needs_reply: number;
  created_at: string;
};

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', description: '' });
  const [loading, setLoading] = useState(false);

  const load = () => fetch('/api/projects').then(r => r.json()).then(setProjects);
  useEffect(() => { load(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    await fetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    });
    setForm({ name: '', description: '' });
    setShowForm(false);
    setLoading(false);
    load();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">案件管理</h2>
          <p className="text-sm text-gray-400 mt-1">案件ごとにメールをまとめてAIが状況を整理します</p>
        </div>
        <button onClick={() => setShowForm(true)} className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700">
          <Plus size={16} /> 新規案件
        </button>
      </div>

      {showForm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <form onSubmit={handleCreate} className="bg-white rounded-xl p-6 w-full max-w-md shadow-xl">
            <h3 className="font-semibold text-lg mb-4">新規案件を作成</h3>
            <div className="space-y-3 mb-4">
              <div>
                <label className="text-xs font-medium text-gray-600 block mb-1">案件名 <span className="text-red-500">*</span></label>
                <input required value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                  placeholder="例: 株式会社〇〇 新規提案" className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 block mb-1">メモ</label>
                <textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
                  placeholder="案件の概要など" className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm" rows={3} />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg">キャンセル</button>
              <button type="submit" disabled={loading} className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 disabled:opacity-50">
                {loading ? '作成中...' : '作成'}
              </button>
            </div>
          </form>
        </div>
      )}

      {projects.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-16 text-center">
          <Folder size={40} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-500 font-medium mb-1">案件がまだありません</p>
          <p className="text-sm text-gray-400">「新規案件」ボタンから案件を作成して、関連するメールをまとめましょう</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {projects.map(p => {
            const totalThreads = (p.thread_count ?? 0) + (p.deal_thread_count ?? 0);
            const hasNeedsReply = (p.deal_needs_reply ?? 0) > 0;
            return (
              <Link key={p.id} href={`/projects/${p.id}`}
                className="bg-white rounded-xl border border-gray-200 p-5 hover:border-indigo-300 hover:shadow-sm transition-all flex items-center justify-between group">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 bg-indigo-50 rounded-xl flex items-center justify-center">
                    <Folder size={20} className="text-indigo-500" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-gray-900">{p.name}</span>
                      {hasNeedsReply && (
                        <span className="flex items-center gap-1 bg-red-100 text-red-600 text-xs px-2 py-0.5 rounded-full font-medium">
                          <AlertCircle size={10} />要返信
                        </span>
                      )}
                    </div>
                    {p.description && <div className="text-sm text-gray-400 mt-0.5">{p.description}</div>}
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-1.5 text-sm text-gray-400">
                    <Mail size={14} />
                    <span>{totalThreads} スレッド</span>
                    {(p.unread_count ?? 0) > 0 && (
                      <span className="bg-red-500 text-white text-xs rounded-full px-1.5 py-0.5 ml-1">{p.unread_count}</span>
                    )}
                  </div>
                  <ChevronRight size={16} className="text-gray-300 group-hover:text-indigo-400 transition-colors" />
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
