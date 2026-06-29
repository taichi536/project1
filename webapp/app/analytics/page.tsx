'use client';
import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

type StatsData = {
  statusCounts: { status: string; count: number }[];
  typeCounts: { type: string; count: number }[];
  replyRate: { total: number; replied: number };
  overdueCount: number;
};

const STATUS_LABELS: Record<string, string> = {
  pending: '未対応', in_progress: '対応中', done: '完了', no_reply: '返信なし',
};
const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444'];

export default function AnalyticsPage() {
  const [stats, setStats] = useState<StatsData | null>(null);

  useEffect(() => {
    fetch('/api/stats').then(r => r.json()).then(setStats);
  }, []);

  const statusData = stats?.statusCounts.map(s => ({ name: STATUS_LABELS[s.status] ?? s.status, value: s.count })) ?? [];
  const typeData = stats?.typeCounts.map(t => ({ name: t.type, value: t.count })) ?? [];
  const { total = 0, replied = 0 } = stats?.replyRate ?? {};
  const replyRatePct = total > 0 ? Math.round((replied / total) * 100) : 0;

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">分析</h2>

      <div className="grid grid-cols-2 gap-6">
        {/* ステータス別 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="font-semibold mb-4 text-sm text-gray-600">ステータス別件数</h3>
          {statusData.length === 0 ? (
            <p className="text-gray-400 text-sm text-center py-8">データなし</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={statusData} cx="50%" cy="50%" outerRadius={80} dataKey="value" label={({ name, value }) => `${name}: ${value}`}>
                  {statusData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* 種別 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="font-semibold mb-4 text-sm text-gray-600">種別内訳</h3>
          {typeData.length === 0 ? (
            <p className="text-gray-400 text-sm text-center py-8">データなし</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={typeData}>
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="value" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* 返信率 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 col-span-2">
          <h3 className="font-semibold mb-4 text-sm text-gray-600">返信率サマリー</h3>
          <div className="flex items-center gap-8">
            <div>
              <div className="text-5xl font-bold text-indigo-600">{replyRatePct}%</div>
              <div className="text-sm text-gray-400 mt-1">返信率</div>
            </div>
            <div className="flex-1 bg-gray-100 rounded-full h-4 overflow-hidden">
              <div className="bg-indigo-600 h-full rounded-full transition-all" style={{ width: `${replyRatePct}%` }} />
            </div>
            <div className="text-sm text-gray-500">
              <div>{replied} 件返信あり</div>
              <div className="text-gray-400">/ {total} 件送信</div>
            </div>
          </div>
          {stats && stats.overdueCount > 0 && (
            <div className="mt-4 p-3 bg-red-50 rounded-lg text-sm text-red-600">
              ⚠️ {stats.overdueCount} 件が3日以上返信待ちです。フォローアップを検討してください。
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
