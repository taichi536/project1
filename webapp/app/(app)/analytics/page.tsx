'use client';
import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

type Stats = {
  needsReply: number;
  undone: number;
  done: number;
  total: number;
};

const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444'];

export default function AnalyticsPage() {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    fetch('/api/stats').then(r => r.json()).then(d => { if (!d.error) setStats(d); });
  }, []);

  const doneRate = stats && stats.total > 0 ? Math.round((stats.done / stats.total) * 100) : 0;

  const pieData = stats ? [
    { name: '対応済み', value: stats.done },
    { name: '未対応', value: Math.max(0, stats.undone - stats.needsReply) },
    { name: '要返信', value: stats.needsReply },
  ].filter(d => d.value > 0) : [];

  const barData = stats ? [
    { name: '要返信', value: stats.needsReply },
    { name: '未対応', value: stats.undone },
    { name: '対応済み', value: stats.done },
    { name: '合計', value: stats.total },
  ] : [];

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">分析</h2>

      <div className="grid grid-cols-2 gap-6">
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

        {/* 件数バー */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="font-semibold mb-4 text-sm text-gray-600">件数サマリー</h3>
          {barData.length === 0 ? (
            <p className="text-gray-400 text-sm text-center py-8">データなし</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={barData}>
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="value" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* 対応完了率 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 col-span-2">
          <h3 className="font-semibold mb-4 text-sm text-gray-600">対応完了率</h3>
          <div className="flex items-center gap-8">
            <div>
              <div className="text-5xl font-bold text-indigo-600">{doneRate}%</div>
              <div className="text-sm text-gray-400 mt-1">対応完了率</div>
            </div>
            <div className="flex-1 bg-gray-100 rounded-full h-4 overflow-hidden">
              <div className="bg-indigo-600 h-full rounded-full transition-all" style={{ width: `${doneRate}%` }} />
            </div>
            <div className="text-sm text-gray-500">
              <div>{stats?.done ?? 0} 件対応済み</div>
              <div className="text-gray-400">/ {stats?.total ?? 0} 件</div>
            </div>
          </div>
          {stats && stats.needsReply > 0 && (
            <div className="mt-4 p-3 bg-red-50 rounded-lg text-sm text-red-600">
              ⚠️ {stats.needsReply} 件が返信待ちです。受信トレイを確認してください。
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
