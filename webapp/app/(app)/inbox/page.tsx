'use client';
import { useEffect, useState } from 'react';
import { RefreshCw, Mail, CheckCircle, Clock, Sparkles, X, Send, ChevronDown, Search, FileText, Trash2, Plus } from 'lucide-react';

type Thread = {
  id: number;
  thread_id: string;
  subject: string;
  snippet: string;
  from_email: string;
  last_message_at: string;
  message_count: number;
  needs_reply: number;
  is_done: number;
  deal_name: string | null;
  assignee_name: string | null;
};

type Message = {
  id: string;
  from: string;
  to: string;
  subject: string;
  date: string;
  body: string;
};

type ThreadDetail = {
  threadId: string;
  subject: string;
  messages: Message[];
};

function formatDate(dateStr: string): string {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr.slice(0, 10);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const days = Math.floor(diff / 86400000);
  if (days === 0) return d.toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' });
  if (days < 7) return `${days}日前`;
  return d.toLocaleDateString('ja-JP', { month: 'numeric', day: 'numeric' });
}

export default function InboxPage() {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<Thread | null>(null);
  const [detail, setDetail] = useState<ThreadDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [aiResult, setAiResult] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiType, setAiType] = useState('');
  const [filter, setFilter] = useState<'all' | 'needs_reply' | 'done'>('all');
  const [showReply, setShowReply] = useState(false);
  const [replyBody, setReplyBody] = useState('');
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState('');
  const [search, setSearch] = useState('');
  const [users, setUsers] = useState<{ id: number; name: string; email: string }[]>([]);
  const [templates, setTemplates] = useState<{ id: number; title: string; body: string }[]>([]);
  const [showTemplates, setShowTemplates] = useState(false);
  const [showNewTemplate, setShowNewTemplate] = useState(false);
  const [newTemplateTitle, setNewTemplateTitle] = useState('');
  const [newTemplateBody, setNewTemplateBody] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    const res = await fetch('/api/inbox');
    const data = await res.json();
    if (!res.ok) {
      setError(data.error ?? 'エラーが発生しました');
    } else {
      setThreads(data.threads);
    }
    setLoading(false);
  };

  const loadTemplates = () => fetch('/api/templates').then(r => r.json()).then(d => setTemplates(d.templates ?? []));

  useEffect(() => {
    load();
    fetch('/api/users').then(r => r.json()).then(d => setUsers(d.users ?? []));
    loadTemplates();
  }, []);

  const openThread = async (t: Thread) => {
    setSelected(t);
    setAiResult('');
    setShowReply(false);
    setReplyBody('');
    setSendResult('');
    setDetailLoading(true);
    const res = await fetch(`/api/threads/${t.thread_id}`);
    const data = await res.json();
    setDetail(data.thread ?? null);
    setDetailLoading(false);
  };

  const markDone = async (threadId: string, done: boolean) => {
    await fetch(`/api/threads/${threadId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_done: done }),
    });
    setThreads(prev => prev.map(t => t.thread_id === threadId ? { ...t, is_done: done ? 1 : 0, needs_reply: done ? 0 : t.needs_reply } : t));
    if (selected?.thread_id === threadId) setSelected(prev => prev ? { ...prev, is_done: done ? 1 : 0 } : prev);
  };

  const saveTemplate = async () => {
    if (!newTemplateTitle.trim() || !newTemplateBody.trim()) return;
    await fetch('/api/templates', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: newTemplateTitle, body: newTemplateBody }),
    });
    setNewTemplateTitle('');
    setNewTemplateBody('');
    setShowNewTemplate(false);
    loadTemplates();
  };

  const deleteTemplate = async (id: number) => {
    await fetch(`/api/templates/${id}`, { method: 'DELETE' });
    loadTemplates();
  };

  const insertTemplate = (body: string) => {
    setReplyBody(body);
    setShowReply(true);
    setShowTemplates(false);
  };

  const assignTo = async (threadId: string, userId: number | null) => {
    await fetch(`/api/threads/${threadId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ assigned_to: userId }),
    });
    const assigneeName = users.find(u => u.id === userId)?.name ?? null;
    setThreads(prev => prev.map(t => t.thread_id === threadId ? { ...t, assignee_name: assigneeName } : t));
    if (selected?.thread_id === threadId) setSelected(prev => prev ? { ...prev, assignee_name: assigneeName } : prev);
  };

  const getAI = async (type: string) => {
    if (!selected) return;
    setAiType(type);
    setAiLoading(true);
    setAiResult('');
    const res = await fetch(`/api/threads/${selected.thread_id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type }),
    });
    const data = await res.json();
    const result = data.result ?? data.error;
    setAiResult(result);
    setAiLoading(false);
    // 返信文の場合は自動でコンポーザーに入れる
    if (type === 'reply') {
      setReplyBody(result);
      setShowReply(true);
    }
  };

  const sendReply = async () => {
    if (!selected || !replyBody.trim()) return;
    setSending(true);
    setSendResult('');
    const lastMsg = detail?.messages[detail.messages.length - 1];
    const to = lastMsg?.from ?? selected.from_email;
    const subject = detail?.subject ? `Re: ${detail.subject}` : '';

    const res = await fetch(`/api/threads/${selected.thread_id}/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ to, subject, body: replyBody }),
    });
    const data = await res.json();
    if (res.ok) {
      setSendResult('送信しました');
      setShowReply(false);
      setReplyBody('');
      setThreads(prev => prev.map(t => t.thread_id === selected.thread_id ? { ...t, is_done: 1, needs_reply: 0 } : t));
      setSelected(prev => prev ? { ...prev, is_done: 1, needs_reply: 0 } : prev);
    } else {
      setSendResult(`エラー: ${data.error}`);
    }
    setSending(false);
  };

  const filtered = threads.filter(t => {
    if (filter === 'needs_reply' && !(t.needs_reply && !t.is_done)) return false;
    if (filter === 'done' && !t.is_done) return false;
    if (filter === 'all' && t.is_done) return false;
    if (search) {
      const q = search.toLowerCase();
      return t.subject?.toLowerCase().includes(q) || t.from_email?.toLowerCase().includes(q) || t.snippet?.toLowerCase().includes(q);
    }
    return true;
  });

  const needsReplyCount = threads.filter(t => t.needs_reply && !t.is_done).length;

  return (
    <div className="flex h-full gap-0 -m-8">
      {/* 左: スレッド一覧 */}
      <div className="w-96 border-r border-gray-200 flex flex-col bg-white shrink-0">
        <div className="p-4 border-b border-gray-200">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-bold text-lg">受信トレイ</h2>
            <button onClick={load} disabled={loading} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400">
              <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>
          <div className="relative mb-2">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="検索..."
              className="w-full pl-7 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
          </div>
          <div className="flex gap-1">
            {(['all', 'needs_reply', 'done'] as const).map(f => (
              <button key={f} onClick={() => setFilter(f)}
                className={`flex-1 py-1.5 text-xs rounded-lg font-medium transition-colors ${filter === f ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'}`}>
                {f === 'all' ? `未対応 (${threads.filter(t => !t.is_done).length})` : f === 'needs_reply' ? `要返信 (${needsReplyCount})` : '完了'}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="m-3 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">{error}</div>
        )}

        <div className="flex-1 overflow-y-auto">
          {loading && threads.length === 0 && (
            <div className="text-center py-16 text-gray-400 text-sm">読み込み中...</div>
          )}
          {!loading && filtered.length === 0 && (
            <div className="text-center py-16 text-gray-400 text-sm">メールがありません</div>
          )}
          {filtered.map(t => (
            <div key={t.thread_id}
              onClick={() => openThread(t)}
              className={`px-4 py-3 border-b border-gray-100 cursor-pointer hover:bg-gray-50 transition-colors ${selected?.thread_id === t.thread_id ? 'bg-indigo-50 border-l-2 border-l-indigo-500' : ''}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    {t.needs_reply && !t.is_done && (
                      <span className="bg-red-100 text-red-600 text-xs px-1.5 py-0.5 rounded font-medium shrink-0">要返信</span>
                    )}
                    <span className="text-sm font-medium truncate">{t.from_email?.replace(/<.*>/, '').trim() || t.from_email}</span>
                  </div>
                  <div className="text-sm text-gray-700 truncate">{t.subject}</div>
                  <div className="text-xs text-gray-400 truncate mt-0.5">{t.snippet}</div>
                  {t.assignee_name && (
                    <div className="text-xs text-indigo-500 mt-0.5">@{t.assignee_name}</div>
                  )}
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  <div className="text-xs text-gray-400">{formatDate(t.last_message_at)}</div>
                  <div className="text-xs text-gray-400">{t.message_count}件</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 右: スレッド詳細 */}
      <div className="flex-1 flex flex-col bg-gray-50 overflow-hidden">
        {!selected ? (
          <div className="flex-1 flex items-center justify-center text-gray-400">
            <div className="text-center">
              <Mail size={40} className="mx-auto mb-3 text-gray-300" />
              <p className="text-sm">メールを選択してください</p>
            </div>
          </div>
        ) : (
          <>
            {/* ヘッダー */}
            <div className="bg-white border-b border-gray-200 px-6 py-4 shrink-0">
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-lg leading-tight">{selected.subject}</h3>
                  <p className="text-sm text-gray-400 mt-0.5">{selected.from_email}</p>
                </div>
                <div className="flex items-center gap-2 ml-4 shrink-0">
                  <select
                    value={users.find(u => u.name === selected.assignee_name)?.id ?? ''}
                    onChange={e => assignTo(selected.thread_id, e.target.value ? Number(e.target.value) : null)}
                    className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 text-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-300 max-w-[120px]">
                    <option value="">担当者なし</option>
                    {users.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
                  </select>
                  <button onClick={() => markDone(selected.thread_id, !selected.is_done)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                      selected.is_done ? 'bg-gray-100 text-gray-500 hover:bg-gray-200' : 'bg-green-50 text-green-600 hover:bg-green-100'
                    }`}>
                    <CheckCircle size={14} />
                    {selected.is_done ? '未対応に戻す' : '対応済み'}
                  </button>
                  <button onClick={() => setSelected(null)} className="p-1.5 text-gray-400 hover:text-gray-600">
                    <X size={16} />
                  </button>
                </div>
              </div>

              {/* AIアクション */}
              <div className="flex gap-2 mt-3">
                <button onClick={() => getAI('summary')} disabled={aiLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white text-xs rounded-lg hover:bg-indigo-700 disabled:opacity-50">
                  <Sparkles size={12} />
                  {aiLoading && aiType === 'summary' ? '分析中...' : '状況を整理'}
                </button>
                <button onClick={() => getAI('reply')} disabled={aiLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 border border-indigo-200 text-indigo-600 text-xs rounded-lg hover:bg-indigo-50 disabled:opacity-50">
                  <ChevronDown size={12} />
                  {aiLoading && aiType === 'reply' ? '生成中...' : 'AI返信を作成'}
                </button>
                <button onClick={() => getAI('task')} disabled={aiLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 border border-gray-200 text-gray-600 text-xs rounded-lg hover:bg-gray-50 disabled:opacity-50">
                  <Clock size={12} />
                  {aiLoading && aiType === 'task' ? '生成中...' : 'タスク抽出'}
                </button>
                <button onClick={() => setShowReply(!showReply)}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 ml-auto">
                  <Send size={12} />
                  返信する
                </button>
              </div>

              {/* AI結果 */}
              {aiResult && aiType !== 'reply' && (
                <div className="mt-3 p-3 bg-indigo-50 rounded-lg border border-indigo-100">
                  <div className="text-xs font-medium text-indigo-600 mb-1">
                    {aiType === 'summary' ? '状況サマリー' : 'タスク'}
                  </div>
                  <div className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">{aiResult}</div>
                </div>
              )}

              {sendResult && (
                <div className={`mt-2 text-xs px-3 py-2 rounded-lg ${sendResult.includes('エラー') ? 'bg-red-50 text-red-600' : 'bg-green-50 text-green-600'}`}>
                  {sendResult}
                </div>
              )}
            </div>

            {/* 返信コンポーザー */}
            {showReply && (
              <div className="bg-white border-b border-gray-200 px-6 py-4 shrink-0">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-xs text-gray-500">
                    返信先: {detail?.messages[detail.messages.length - 1]?.from ?? selected.from_email}
                  </div>
                  <div className="relative">
                    <button onClick={() => { setShowTemplates(!showTemplates); setShowNewTemplate(false); }}
                      className="flex items-center gap-1.5 px-2.5 py-1 text-xs border border-gray-200 text-gray-600 rounded-lg hover:bg-gray-50">
                      <FileText size={11} />
                      テンプレート
                    </button>
                    {showTemplates && (
                      <div className="absolute right-0 top-8 w-72 bg-white border border-gray-200 rounded-xl shadow-lg z-10 overflow-hidden">
                        <div className="p-3 border-b border-gray-100 flex items-center justify-between">
                          <span className="text-xs font-medium text-gray-600">テンプレート一覧</span>
                          <button onClick={() => setShowNewTemplate(!showNewTemplate)}
                            className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-700">
                            <Plus size={11} />新規作成
                          </button>
                        </div>
                        {showNewTemplate && (
                          <div className="p-3 border-b border-gray-100 bg-gray-50">
                            <input value={newTemplateTitle} onChange={e => setNewTemplateTitle(e.target.value)}
                              placeholder="テンプレート名" className="w-full text-xs border border-gray-200 rounded px-2 py-1 mb-2 focus:outline-none focus:ring-1 focus:ring-indigo-300" />
                            <textarea value={newTemplateBody} onChange={e => setNewTemplateBody(e.target.value)}
                              placeholder="本文" rows={3} className="w-full text-xs border border-gray-200 rounded px-2 py-1 mb-2 resize-none focus:outline-none focus:ring-1 focus:ring-indigo-300" />
                            <button onClick={saveTemplate} className="w-full py-1 bg-indigo-600 text-white text-xs rounded hover:bg-indigo-700">保存</button>
                          </div>
                        )}
                        <div className="max-h-48 overflow-y-auto">
                          {templates.length === 0 ? (
                            <div className="text-xs text-gray-400 text-center py-4">テンプレートがありません</div>
                          ) : templates.map(t => (
                            <div key={t.id} className="flex items-center gap-2 px-3 py-2 hover:bg-gray-50 group">
                              <button onClick={() => insertTemplate(t.body)} className="flex-1 text-left">
                                <div className="text-xs font-medium text-gray-700">{t.title}</div>
                                <div className="text-xs text-gray-400 truncate">{t.body.slice(0, 40)}</div>
                              </button>
                              <button onClick={() => deleteTemplate(t.id)} className="opacity-0 group-hover:opacity-100 text-gray-300 hover:text-red-400">
                                <Trash2 size={12} />
                              </button>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
                <textarea
                  value={replyBody}
                  onChange={e => setReplyBody(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  rows={6}
                  placeholder="返信文を入力してください..."
                />
                <div className="flex justify-end gap-2 mt-2">
                  <button onClick={() => { setShowReply(false); setReplyBody(''); setShowTemplates(false); }}
                    className="px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded-lg">
                    キャンセル
                  </button>
                  <button onClick={sendReply} disabled={sending || !replyBody.trim()}
                    className="flex items-center gap-1.5 px-4 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50">
                    <Send size={13} />
                    {sending ? '送信中...' : '送信'}
                  </button>
                </div>
              </div>
            )}

            {/* メール本文 */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {detailLoading ? (
                <div className="text-center text-gray-400 text-sm py-8">読み込み中...</div>
              ) : detail?.messages.map((m, i) => (
                <div key={m.id} className="bg-white rounded-xl border border-gray-200 p-4">
                  <div className="flex items-center justify-between mb-3 pb-3 border-b border-gray-100">
                    <div>
                      <div className="text-sm font-medium">{m.from}</div>
                      <div className="text-xs text-gray-400">To: {m.to}</div>
                    </div>
                    <div className="text-xs text-gray-400">{m.date}</div>
                  </div>
                  <div className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed max-h-96 overflow-y-auto">
                    {m.body.slice(0, 3000) || '(本文なし)'}
                  </div>
                  {i === detail.messages.length - 1 && selected.needs_reply && !selected.is_done && (
                    <div className="mt-3 pt-3 border-t border-gray-100">
                      <span className="text-xs bg-red-50 text-red-500 px-2 py-1 rounded-full">返信が必要です</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
