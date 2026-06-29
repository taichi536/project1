'use client';
import { useEffect, useState, use } from 'react';
import { Mail, Sparkles, RefreshCw, Plus, X, ArrowLeft, MessageSquare, AlertCircle, Zap } from 'lucide-react';
import Link from 'next/link';

type Thread = {
  id: number;
  thread_id: string;
  subject: string;
  snippet: string;
  from_email: string;
  last_message_at: string;
  message_count: number;
};

type DealThread = {
  id: number;
  thread_id: string;
  subject: string;
  from_email: string;
  last_message_at: string;
  needs_reply: number;
  next_action: string | null;
  next_action_due: string | null;
  message_count: number;
  snippet: string;
  is_done: number;
  deal_id: number;
};

type GmailThread = {
  threadId: string;
  subject: string;
  from: string;
  snippet: string;
  date: string;
  messageCount: number;
};

type Project = { id: number; name: string; description: string };

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

export default function ProjectDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [project, setProject] = useState<Project | null>(null);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [dealThreads, setDealThreads] = useState<DealThread[]>([]);
  const [gmailThreads, setGmailThreads] = useState<GmailThread[]>([]);
  const [showGmail, setShowGmail] = useState(false);
  const [gmailLoading, setGmailLoading] = useState(false);
  const [gmailError, setGmailError] = useState('');
  const [summary, setSummary] = useState('');
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryType, setSummaryType] = useState<'summary' | 'reply'>('summary');

  const load = () => {
    fetch(`/api/projects/${id}`).then(r => r.json()).then(d => {
      setProject(d.project);
      setThreads(d.threads ?? []);
      setDealThreads(d.dealThreads ?? []);
    });
  };

  useEffect(() => { load(); }, [id]);

  const loadGmail = async () => {
    setGmailLoading(true);
    setGmailError('');
    const res = await fetch('/api/gmail');
    const data = await res.json();
    if (!res.ok) {
      setGmailError(data.error ?? 'エラーが発生しました');
    } else {
      setGmailThreads(data.threads);
      setShowGmail(true);
    }
    setGmailLoading(false);
  };

  const addThread = async (t: GmailThread) => {
    await fetch(`/api/projects/${id}/threads`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        threadId: t.threadId,
        subject: t.subject,
        snippet: t.snippet,
        fromEmail: t.from,
        lastMessageAt: t.date,
        messageCount: t.messageCount,
      }),
    });
    load();
  };

  const removeThread = async (threadId: string) => {
    await fetch(`/api/projects/${id}/threads`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ threadId }),
    });
    load();
  };

  const getSummary = async (type: 'summary' | 'reply') => {
    setSummaryType(type);
    setSummaryLoading(true);
    setSummary('');
    const res = await fetch(`/api/projects/${id}/summarize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type }),
    });
    const data = await res.json();
    setSummary(data.result ?? data.error ?? 'エラーが発生しました');
    setSummaryLoading(false);
  };

  const linkedIds = new Set(threads.map(t => t.thread_id));

  if (!project) return <div className="text-gray-400 text-sm">読み込み中...</div>;

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <Link href="/projects" className="text-gray-400 hover:text-gray-600">
          <ArrowLeft size={20} />
        </Link>
        <div>
          <h2 className="text-2xl font-bold">{project.name}</h2>
          {project.description && <p className="text-sm text-gray-400 mt-0.5">{project.description}</p>}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* 左: スレッド一覧 */}
        <div className="col-span-2 space-y-4">
          {/* 受信トレイから紐付けられたメール */}
          {dealThreads.length > 0 && (
            <div>
              <h3 className="font-semibold mb-3">紐付けられたメール ({dealThreads.length})</h3>
              <div className="space-y-2">
                {dealThreads.map(t => (
                  <div key={t.thread_id} className="bg-white rounded-xl border border-gray-200 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex gap-3 flex-1 min-w-0">
                        <div className="w-8 h-8 bg-blue-50 rounded-lg flex items-center justify-center shrink-0 mt-0.5">
                          <Mail size={14} className="text-blue-500" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-medium text-sm truncate">{t.subject || '(件名なし)'}</span>
                            {t.needs_reply === 1 && !t.is_done && (
                              <span className="flex items-center gap-1 bg-red-100 text-red-600 text-xs px-1.5 py-0.5 rounded-full shrink-0 font-medium">
                                <AlertCircle size={10} />要返信
                              </span>
                            )}
                            {t.is_done === 1 && (
                              <span className="bg-green-100 text-green-600 text-xs px-1.5 py-0.5 rounded-full shrink-0">対応済み</span>
                            )}
                          </div>
                          <div className="text-xs text-gray-400 mt-0.5">{t.from_email}</div>
                          {t.snippet && <div className="text-xs text-gray-400 mt-1 line-clamp-1">{t.snippet}</div>}
                          <div className="flex items-center gap-3 mt-1">
                            <span className="text-xs text-gray-300">{t.message_count}件 · {formatDate(t.last_message_at)}</span>
                            {t.next_action && (
                              <span className="flex items-center gap-1 text-xs text-orange-500">
                                <Zap size={10} />{t.next_action}{t.next_action_due ? ` (${t.next_action_due})` : ''}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Gmailから手動追加したスレッド */}
          <div>
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">紐付けメール ({threads.length})</h3>
              <button onClick={loadGmail} disabled={gmailLoading}
                className="flex items-center gap-2 px-3 py-1.5 text-sm border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50">
                <Plus size={14} />
                {gmailLoading ? '読み込み中...' : 'メールを追加'}
              </button>
            </div>

            {gmailError && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-600 mt-3">
                {gmailError}
                {gmailError.includes('Gmail未連携') && (
                  <div className="mt-2">
                    <a href="/api/auth/signin" className="text-indigo-600 underline">Googleでログインしなおす</a>
                  </div>
                )}
              </div>
            )}

            {threads.length === 0 && !showGmail && dealThreads.length === 0 && (
              <div className="bg-white rounded-xl border border-dashed border-gray-200 p-10 text-center mt-3">
                <Mail size={32} className="mx-auto text-gray-300 mb-3" />
                <p className="text-sm text-gray-400">「メールを追加」からGmailのスレッドをこの案件に紐付けましょう</p>
              </div>
            )}

            <div className="space-y-2 mt-3">
              {threads.map(t => (
                <div key={t.thread_id} className="bg-white rounded-xl border border-gray-200 p-4 flex items-start justify-between">
                  <div className="flex gap-3">
                    <div className="w-8 h-8 bg-indigo-50 rounded-lg flex items-center justify-center shrink-0 mt-0.5">
                      <MessageSquare size={14} className="text-indigo-500" />
                    </div>
                    <div>
                      <div className="font-medium text-sm">{t.subject}</div>
                      <div className="text-xs text-gray-400 mt-0.5">{t.from_email}</div>
                      <div className="text-xs text-gray-400 mt-1 line-clamp-2">{t.snippet}</div>
                      <div className="text-xs text-gray-300 mt-1">{t.message_count}件のメッセージ</div>
                    </div>
                  </div>
                  <button onClick={() => removeThread(t.thread_id)} className="text-gray-300 hover:text-red-400 ml-3 shrink-0">
                    <X size={14} />
                  </button>
                </div>
              ))}
            </div>

            {/* Gmail選択パネル */}
            {showGmail && (
              <div className="bg-white rounded-xl border border-indigo-200 p-4 mt-3">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="font-medium text-sm">Gmailから選択</h4>
                  <button onClick={() => setShowGmail(false)} className="text-gray-400 hover:text-gray-600"><X size={14} /></button>
                </div>
                <div className="space-y-2 max-h-80 overflow-y-auto">
                  {gmailThreads.map(t => (
                    <div key={t.threadId}
                      className={`p-3 rounded-lg border text-sm cursor-pointer transition-colors ${
                        linkedIds.has(t.threadId)
                          ? 'border-indigo-200 bg-indigo-50 opacity-50 cursor-default'
                          : 'border-gray-100 hover:border-indigo-200 hover:bg-indigo-50'
                      }`}
                      onClick={() => !linkedIds.has(t.threadId) && addThread(t)}>
                      <div className="font-medium">{t.subject}</div>
                      <div className="text-xs text-gray-400 mt-0.5">{t.from} · {t.messageCount}件</div>
                      <div className="text-xs text-gray-400 mt-1 line-clamp-1">{t.snippet}</div>
                      {linkedIds.has(t.threadId) && <div className="text-xs text-indigo-500 mt-1">追加済み</div>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 右: AIサマリー */}
        <div className="space-y-4">
          <h3 className="font-semibold">AI分析</h3>
          <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
            <button onClick={() => getSummary('summary')} disabled={summaryLoading || (threads.length === 0 && dealThreads.length === 0)}
              className="w-full flex items-center gap-2 px-3 py-2.5 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 disabled:opacity-50 justify-center">
              <Sparkles size={14} />
              {summaryLoading && summaryType === 'summary' ? '分析中...' : '状況をサマリー'}
            </button>
            <button onClick={() => getSummary('reply')} disabled={summaryLoading || (threads.length === 0 && dealThreads.length === 0)}
              className="w-full flex items-center gap-2 px-3 py-2.5 border border-indigo-200 text-indigo-600 text-sm rounded-lg hover:bg-indigo-50 disabled:opacity-50 justify-center">
              <RefreshCw size={14} />
              {summaryLoading && summaryType === 'reply' ? '生成中...' : '返信文を作成'}
            </button>
            {threads.length === 0 && dealThreads.length === 0 && (
              <p className="text-xs text-gray-400 text-center">メールを追加するとAI分析が使えます</p>
            )}
          </div>

          {summary && (
            <div className="bg-white rounded-xl border border-indigo-100 p-4">
              <div className="text-xs font-medium text-indigo-600 mb-2">
                {summaryType === 'summary' ? '状況サマリー' : '返信文の提案'}
              </div>
              <div className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">{summary}</div>
              {summaryType === 'reply' && (
                <button onClick={() => navigator.clipboard.writeText(summary)}
                  className="mt-3 text-xs text-indigo-600 hover:underline">
                  クリップボードにコピー
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
