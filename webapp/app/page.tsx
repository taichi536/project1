'use client';
import { useEffect, useState } from 'react';
import { AlertCircle, MessageSquare, CheckCircle, TrendingUp } from 'lucide-react';

type StatsData = {
  statusCounts: { status: string; count: number }[];
  typeCounts: { type: string; count: number }[];
  replyRate: { total: number; replied: number };
  overdueCount: number;
  recent: {
    id: number;
    contact_name: string;
    company: string;
    type: string;
    status: string;
    subject: string;
    created_at: string;
  }[];
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

export default function Dashboard() {
  const [stats, setStats] = useState<StatsData | null>(null);

  useEffect(() => {
    fetch('/api/stats').then(r => r.json()).then(setStats);
  }, []);

  const pending = stats?.statusCounts.find(s => s.status === 'pending')?.count ?? 0;
  const total = stats?.replyRate.total ?? 0;
  const replied = stats?.replyRate.replied ?? 0;
  const replyRatePct = total > 0 ? Math.round((replied / total) * 100) : 0;

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">ダッシュボード</h2>

      {/* KPIカード */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <KpiCard
          icon={<AlertCircle className="text-yellow-500" size={20} />}
          label="未対応"
          value={pending}
          sub="件の対応待ち"
          bg="bg-yellow-50"
        />
        <KpiCard
          icon={<MessageSquare className="text-indigo-500" size={20} />}
          label="総送信数"
          value={total}
          sub="件のアウトバウンド"
          bg="bg-indigo-50"
        />
        <KpiCard
          icon={<TrendingUp className="text-green-500" size={20} />}
          label="返信率"
          value={`${replyRatePct}%`}
          sub={`${replied} / ${total} 件`}
          bg="bg-green-50"
        />
        <KpiCard
          icon={<AlertCircle className="text-red-500" size={20} />}
          label="要フォロー"
          value={stats?.overdueCount ?? 0}
          sub="3日以上返信なし"
          bg="bg-red-50"
        />
      </div>

      {/* 最近のコミュニケーション */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="font-semibold mb-4">最近のコミュニケーション</h3>
        {!stats?.recent.length ? (
          <p className="text-gray-400 text-sm">データがありません。コミュニケーションを登録してください。</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-400 border-b border-gray-100">
                <th className="pb-2 font-medium">相手</th>
                <th className="pb-2 font-medium">種別</th>
                <th className="pb-2 font-medium">件名</th>
                <th className="pb-2 font-medium">ステータス</th>
                <th className="pb-2 font-medium">日時</th>
              </tr>
            </thead>
            <tbody>
              {stats.recent.map(row => (
                <tr key={row.id} className="border-b border-gray-50 hover:bg-gray-50">
                  <td className="py-2">
                    <span className="font-medium">{row.contact_name ?? '—'}</span>
                    {row.company && <span className="text-gray-400 ml-1">({row.company})</span>}
                  </td>
                  <td className="py-2 text-gray-500">{row.type}</td>
                  <td className="py-2">{row.subject ?? '—'}</td>
                  <td className="py-2">
                    <span className={`px-2 py-0.5 rounded-full text-xs ${statusColor[row.status]}`}>
                      {statusLabel[row.status] ?? row.status}
                    </span>
                  </td>
                  <td className="py-2 text-gray-400">{row.created_at?.slice(0, 16)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function KpiCard({ icon, label, value, sub, bg }: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  sub: string;
  bg: string;
}) {
  return (
    <div className={`${bg} rounded-xl p-5 border border-gray-100`}>
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-xs text-gray-500">{label}</span>
      </div>
      <div className="text-3xl font-bold">{value}</div>
      <div className="text-xs text-gray-400 mt-1">{sub}</div>
    </div>
  );
}
