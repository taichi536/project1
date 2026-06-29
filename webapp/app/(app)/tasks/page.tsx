'use client';
import { useEffect, useState } from 'react';
import { Plus } from 'lucide-react';

type Task = {
  id: number;
  title: string;
  description: string;
  status: string;
  priority: string;
  assigned_to: string;
  due_date: string;
  created_at: string;
};

const statusLabel: Record<string, string> = { todo: '未着手', in_progress: '進行中', done: '完了' };
const priorityColor: Record<string, string> = {
  high: 'text-red-600 bg-red-50',
  medium: 'text-yellow-600 bg-yellow-50',
  low: 'text-gray-500 bg-gray-100',
};

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title: '', description: '', priority: 'medium', assigned_to: '', due_date: '' });

  const load = () => fetch('/api/tasks').then(r => r.json()).then(setTasks);
  useEffect(() => { load(); }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    await fetch('/api/tasks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form) });
    setShowForm(false);
    setForm({ title: '', description: '', priority: 'medium', assigned_to: '', due_date: '' });
    load();
  };

  const updateStatus = async (id: number, status: string) => {
    await fetch(`/api/tasks/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) });
    load();
  };

  const columns = ['todo', 'in_progress', 'done'];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">タスク管理</h2>
        <button onClick={() => setShowForm(true)} className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700">
          <Plus size={16} /> 新規タスク
        </button>
      </div>

      {showForm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <form onSubmit={submit} className="bg-white rounded-xl p-6 w-full max-w-md shadow-xl">
            <h3 className="font-semibold text-lg mb-4">タスク登録</h3>
            <div className="flex flex-col gap-3">
              <input required placeholder="タスクタイトル" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm" />
              <textarea placeholder="詳細（任意）" value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm" rows={3} />
              <div className="grid grid-cols-2 gap-3">
                <select value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm">
                  <option value="high">優先度：高</option>
                  <option value="medium">優先度：中</option>
                  <option value="low">優先度：低</option>
                </select>
                <input placeholder="担当者" value={form.assigned_to} onChange={e => setForm({ ...form, assigned_to: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm" />
                <input type="date" value={form.due_date} onChange={e => setForm({ ...form, due_date: e.target.value })} className="border border-gray-200 rounded-lg px-3 py-2 text-sm col-span-2" />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button type="button" onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg">キャンセル</button>
              <button type="submit" className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700">登録</button>
            </div>
          </form>
        </div>
      )}

      {/* カンバンボード */}
      <div className="grid grid-cols-3 gap-4">
        {columns.map(col => (
          <div key={col} className="bg-gray-100 rounded-xl p-4">
            <h3 className="font-semibold text-sm text-gray-600 mb-3">{statusLabel[col]} ({tasks.filter(t => t.status === col).length})</h3>
            <div className="flex flex-col gap-2">
              {tasks.filter(t => t.status === col).map(task => (
                <div key={task.id} className="bg-white rounded-lg p-3 shadow-sm border border-gray-100">
                  <div className="flex items-start justify-between mb-1">
                    <span className="font-medium text-sm">{task.title}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ml-2 shrink-0 ${priorityColor[task.priority]}`}>
                      {task.priority === 'high' ? '高' : task.priority === 'medium' ? '中' : '低'}
                    </span>
                  </div>
                  {task.description && <p className="text-xs text-gray-400 mb-2">{task.description}</p>}
                  {task.assigned_to && <p className="text-xs text-gray-400">担当: {task.assigned_to}</p>}
                  {task.due_date && <p className="text-xs text-gray-400">期限: {task.due_date}</p>}
                  <div className="flex gap-1 mt-2">
                    {columns.filter(c => c !== col).map(s => (
                      <button key={s} onClick={() => updateStatus(task.id, s)} className="text-xs px-2 py-1 bg-gray-100 hover:bg-indigo-100 hover:text-indigo-700 rounded transition-colors">
                        → {statusLabel[s]}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
              {tasks.filter(t => t.status === col).length === 0 && (
                <p className="text-xs text-gray-400 text-center py-4">なし</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
