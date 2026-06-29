'use client';
import { useEffect, useState } from 'react';
import { AlertCircle, CheckCircle, Mail, Inbox, ArrowRight, Clock } from 'lucide-react';
import Link from 'next/link';

type TodayAction = {
  thread_id: string;
  subject: string;
  next_action: string | null;
  next_action_due: string;
  from_email: string;
};

type Stats = {
  needsReply: number;
  undone: number;
  done: number;
  total: number;
  todayActions: TodayAction[];
  overdueActions: number;
  recent: {
    thread_id: string;
    subject: string;
    from_email: string;
    last_message_at: string;
    needs_reply: number;
    assignee_name: string | null;
  }[];
};

function formatDate(dateStr: string): string {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr.slice(0, 10);
  const now = new Date();
  const days = Math.floor((now.getTime() - d.getTime()) / 86400000);
  if (days === 0) return d.toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' });
  if (days < 7) return `${days}日前`;
  return d.toLocaleDateString('ja-JP', { month: 'numeric', day: 'numeric' });
}

function isOverdue(dueDateStr: string): boolean {
  if (!dueDateStr) return false;
  const today = new Date().toISOString().slice(0, 10);
  return dueDateStr < today;
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    fetch('/api/stats').then(r => r.json()).then(d => {
      if (!d.error) setStats(d);
    });
  }, []);

  const doneRate = stats && stats.total > 0 ? Math.round((stats.done / stats.total) * 100) : 0;

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">ダッシュボード</h2>
        <Link href="/inbox" className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700">
          <Inbox size={14} />
          受信トレイを開く
        </Link>
      </div>

      {/* KPIカード */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <KpiCard
          icon={<AlertCircle size={18} className="text-red-500" />}
          label="要返信"
          value={stats?.needsReply ?? '—'}
          sub="件"
          bg="bg-red-50"
          href="/inbox?filter=needs_reply"
        />
        <KpiCard
          icon={<Mail size={18} className="text-yellow-500" />}
          label="未対応"
          value={stats?.undone ?? '—'}
          sub="件"
          bg="bg-yellow-50"
          href="/inbox"
        />
        <KpiCard
          icon={<CheckCircle size={18} className="text-green-500" />}
          label="対応済み"
          value={stats?.done ?? '—'}
          sub="件"
          bg="bg-green-50"
          href="/inbox?filter=done"
        />
        <KpiCard
          icon={<Mail size={18} className="text-indigo-500" />}
          label="対応完了率"
          value={`${doneRate}%`}
          sub={`${stats?.done ?? 0} / ${stats?.total ?? 0}件`}
          bg="bg-indigo-50"
        />
      </div>

      {/* 今日のアクション */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden mb-6">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Clock size={15} className="text-orange-500" />
            <h3 className="font-semibold text-sm text-gray-700">今日のアクション</h3>
            {stats && stats.overdueActions > 0 && (
              <span className="bg-red-100 text-red-600 text-xs px-2 py-0.5 rounded-full font-medium">
                {stats.overdueActions}件期限超過
              </span>
            )}
          </div>
          <Link href="/inbox" className="text-xs text-indigo-500 hover:underline flex items-center gap-1">
            受信トレイ <ArrowRight size={12} />
          </Link>
        </div>

        {!stats ? (
          <div className="text-center py-8 text-gray-400 text-sm">読み込み中...</div>
        ) : stats.todayActions.length === 0 ? (
          <div className="text-center py-8 text-gray-400 text-sm">
            <CheckCircle size={24} className="mx-auto mb-2 text-green-300" />
            今日のアクションはありません
          </div>
        ) : (
          <div className="divide-y divide-gray-50">
            {stats.todayActions.map(t => {
              const overdue = isOverdue(t.next_action_due);
              return (
                <Link key={t.thread_id} href="/inbox"
                  className="flex items-center gap-4 px-6 py-3 hover:bg-gray-50 transition-colors group">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      {overdue ? (
                        <span className="bg-red-100 text-red-600 text-xs px-1.5 py-0.5 rounded font-medium shrink-0">期限超過</span>
                      ) : (
                        <span className="bg-orange-100 text-orange-600 text-xs px-1.5 py-0.5 rounded font-medium shrink-0">本日期限</span>
                      )}
                      <span className={`text-sm font-medium truncate ${overdue ? 'text-red-700' : 'text-gray-800'}`}>
                        {t.subject || '（件名なし）'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-400 truncate">{t.from_email}</span>
                      {t.next_action && (
                        <span className={`text-xs truncate ${overdue ? 'text-red-500' : 'text-gray-500'}`}>
                          → {t.next_action}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className={`text-xs shrink-0 ${overdue ? 'text-red-500 font-medium' : 'text-gray-400'}`}>
                    {t.next_action_due}
                  </div>
                  <ArrowRight size={14} className="text-gray-300 group-hover:text-indigo-400 shrink-0" />
                </Link>
              );
            })}
          </div>
        )}
      </div>

      {/* 未対応スレッド一覧 */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-sm text-gray-700">未対応メール（新着順）</h3>
          <Link href="/inbox" className="text-xs text-indigo-500 hover:underline flex items-center gap-1">
            すべて見る <ArrowRight size={12} />
          </Link>
        </div>

        {!stats ? (
          <div className="text-center py-10 text-gray-400 text-sm">読み込み中...</div>
        ) : stats.recent.length === 0 ? (
          <div className="text-center py-10 text-gray-400 text-sm">
            <CheckCircle size={28} className="mx-auto mb-2 text-green-300" />
            未対応のメールはありません
          </div>
        ) : (
          <div className="divide-y divide-gray-50">
            {stats.recent.map(t => (
              <Link key={t.thread_id} href="/inbox"
                className="flex items-center gap-4 px-6 py-3 hover:bg-gray-50 transition-colors group">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    {t.needs_reply === 1 && (
                      <span className="bg-red-100 text-red-600 text-xs px-1.5 py-0.5 rounded font-medium shrink-0">要返信</span>
                    )}
                    <span className="text-sm font-medium text-gray-800 truncate">
                      {t.from_email?.replace(/<.*>/, '').trim() || t.from_email}
                    </span>
                    {t.assignee_name && (
                      <span className="text-xs text-indigo-400 shrink-0">@{t.assignee_name}</span>
                    )}
                  </div>
                  <div className="text-sm text-gray-500 truncate">{t.subject}</div>
                </div>
                <div className="text-xs text-gray-400 shrink-0">{formatDate(t.last_message_at)}</div>
                <ArrowRight size={14} className="text-gray-300 group-hover:text-indigo-400 shrink-0" />
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function KpiCard({ icon, label, value, sub, bg, href }: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  sub: string;
  bg: string;
  href?: string;
}) {
  const content = (
    <div className={`${bg} rounded-xl p-4 border border-gray-100 ${href ? 'hover:opacity-80 transition-opacity' : ''}`}>
      <div className="flex items-center gap-2 mb-2">{icon}<span className="text-xs text-gray-500">{label}</span></div>
      <div className="text-3xl font-bold text-gray-800">{value}</div>
      <div className="text-xs text-gray-400 mt-1">{sub}</div>
    </div>
  );
  return href ? <Link href={href}>{content}</Link> : <div>{content}</div>;
}
