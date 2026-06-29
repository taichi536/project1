'use client';
import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

type Stats = {
  needsReply: number;
  undone: number;
  done: number;
  total: number;
};

type AssigneeStat = { assignee_name: string; count: number };
type UpcomingAction = { subject: string; next_action: string; next_action_due: string; assignee_name: string };
type AnalyticsData = {
  assigneeStats: AssigneeStat[];
  upcomingActions: UpcomingAction[];
  weeklyDone: number;
  weeklyNew: number;
};

const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

export default function AnalyticsPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);

  useEffect(() => {
    fetch('/api/stats').then(r => r.json()).then(d => { if (!d.error) setStats(d); });
    fetch('/api/analytics').then(r => r.json()).then(d => { if (!d.error) setAnalytics(d); });
  }, []);

  const doneRate = stats && stats.total > 0 ? Math.round((stats.done / stats.total) * 100) : 0;

  const pieData = stats ? [
    { name: '対応済み', value: stats.done },
    { name: '未対応', value: Math.max(0, stats.undone - stats.needsReply) },
    { name: '要返信', value: stats.needsReply },
  ].filter(d => d.value > 0) : [];

  const weeklyDoneRate = analytics && analytics.weeklyNew > 0
    ? Math.round((analytics.weeklyDone / analytics.weeklyNew) * 100)
    : 0;

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">分析</h2>

      <div className="grid grid-cols-2 gap-6">
        {/* 今週の対応状況 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="font-semibold mb-4 text-sm text-gray-600">今週の対応状況</h3>
          {analytics ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="text-center">
                  <div className="text-3xl font-bold text-indigo-600">{analytics.weeklyDone}</div>
                  <div className="text-xs text-gray-400 mt-1">対応済み</div>
                </div>
                <div className="text-gray-300 text-2xl">/</div>
                <div className="text-center">
                  <div className="text-3xl font-bold text-gray-700">{analytics.weeklyNew}</div>
                  <div className="text-xs text-gray-400 mt-1">新着スレッド</div>
                </div>
                <div className="text-center">
                  <div className="text-3xl font-bold text-emerald-600">{weeklyDoneRate}%</div>
                  <div className="text-xs text-gray-400 mt-1">対応率</div>
                </div>
              </div>
              <div className="bg-gray-100 rounded-full h-3 overflow-hidden">
                <div
                  className="bg-emerald-500 h-full rounded-full transition-all"
                  style={{ width: `${weeklyDoneRate}%` }}
                />
              </div>
              <p className="text-xs text-gray-400">過去7日間のスレッド集計</p>
            </div>
          ) : (
            <p className="text-gray-400 text-sm text-center py-8">読み込み中...</p>
          )}
        </div>

        {/* ステータス内訳 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="font-semibold mb-4 text-sm text-gray-600">ステータス内訳</h3>
          {pieData.length === 0 ? (
            <p className="text-gray-400 text-sm text-center py-8">データなし</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" outerRadius={80} dataKey="value"
                  label={({ name, value }) => `${name}: ${value}`}>
                  {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* 担当者別 未対応件数 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="font-semibold mb-4 text-sm text-gray-600">担当者別 未対応件数</h3>
          {!analytics || analytics.assigneeStats.length === 0 ? (
            <p className="text-gray-400 text-sm text-center py-8">データなし</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={analytics.assigneeStats} layout="vertical" margin={{ left: 8 }}>
                <XAxis type="number" tick={{ fontSize: 12 }} />
                <YAxis type="category" dataKey="assignee_name" tick={{ fontSize: 12 }} width={80} />
                <Tooltip />
                <Bar dataKey="count" fill="#6366f1" radius={[0, 4, 4, 0]} name="未対応件数" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* 対応完了率 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="font-semibold mb-4 text-sm text-gray-600">対応完了率</h3>
          <div className="flex items-center gap-6">
            <div>
              <div className="text-5xl font-bold text-indigo-600">{doneRate}%</div>
              <div className="text-sm text-gray-400 mt-1">対応完了率</div>
            </div>
            <div className="flex-1">
              <div className="bg-gray-100 rounded-full h-4 overflow-hidden">
                <div className="bg-indigo-600 h-full rounded-full transition-all" style={{ width: `${doneRate}%` }} />
              </div>
              <div className="text-sm text-gray-500 mt-2">
                <span>{stats?.done ?? 0} 件対応済み</span>
                <span className="text-gray-400"> / {stats?.total ?? 0} 件</span>
              </div>
            </div>
          </div>
          {stats && stats.needsReply > 0 && (
            <div className="mt-4 p-3 bg-red-50 rounded-lg text-sm text-red-600">
              ⚠️ {stats.needsReply} 件が返信待ちです。受信トレイを確認してください。
            </div>
          )}
        </div>

        {/* 次のアクション期日 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 col-span-2">
          <h3 className="font-semibold mb-4 text-sm text-gray-600">次のアクション期日（7日以内）</h3>
          {!analytics || analytics.upcomingActions.length === 0 ? (
            <p className="text-gray-400 text-sm text-center py-8">期日が近いアクションはありません</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100">
                    <th className="text-left py-2 pr-4 font-medium text-gray-500">件名</th>
                    <th className="text-left py-2 pr-4 font-medium text-gray-500">次のアクション</th>
                    <th className="text-left py-2 pr-4 font-medium text-gray-500">期日</th>
                    <th className="text-left py-2 font-medium text-gray-500">担当者</th>
                  </tr>
                </thead>
                <tbody>
                  {analytics.upcomingActions.map((a, i) => {
                    const due = new Date(a.next_action_due);
                    const today = new Date();
                    today.setHours(0, 0, 0, 0);
                    const daysLeft = Math.ceil((due.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
                    const urgent = daysLeft <= 1;
                    return (
                      <tr key={i} className="border-b border-gray-50 hover:bg-gray-50">
                        <td className="py-2 pr-4 text-gray-800 max-w-xs truncate">{a.subject || '(件名なし)'}</td>
                        <td className="py-2 pr-4 text-gray-600 max-w-xs truncate">{a.next_action || '-'}</td>
                        <td className="py-2 pr-4">
                          <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-1 rounded-full ${urgent ? 'bg-red-100 text-red-700' : 'bg-amber-50 text-amber-700'}`}>
                            {a.next_action_due}
                            {daysLeft === 0 ? ' (今日)' : daysLeft === 1 ? ' (明日)' : ` (${daysLeft}日後)`}
                          </span>
                        </td>
                        <td className="py-2 text-gray-600">{a.assignee_name}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
