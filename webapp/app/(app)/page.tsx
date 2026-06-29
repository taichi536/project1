'use client';
import { useEffect, useState } from 'react';
import { AlertCircle, MessageSquare, TrendingUp, Upload, Sparkles, ArrowRight, Lightbulb } from 'lucide-react';
import Link from 'next/link';

type StatsData = {
  statusCounts: { status: string; count: number }[];
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
  pending: '未対応', in_progress: '対応中', done: '完了', no_reply: '返信なし',
};
const statusColor: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  in_progress: 'bg-blue-100 text-blue-800',
  done: 'bg-green-100 text-green-800',
  no_reply: 'bg-gray-100 text-gray-600',
};

const STEPS = [
  { icon: Upload, label: 'データを取り込む', desc: 'CSVまたは手入力でコミュニケーション記録を追加', href: '/import', color: 'text-indigo-500' },
  { icon: MessageSquare, label: '状況を確認する', desc: '対応漏れや返信待ちを一覧で把握', href: '/communications', color: 'text-blue-500' },
  { icon: Sparkles, label: 'AIで文面を生成', desc: '返信・フォローアップ・提案文をAIが作成', href: '/generate', color: 'text-purple-500' },
];

export default function Dashboard() {
  const [stats, setStats] = useState<StatsData | null>(null);
  const [insight, setInsight] = useState<{ insight: string; level: string } | null>(null);
  const isEmpty = stats !== null && stats.replyRate.total === 0 && stats.statusCounts.length === 0;

  useEffect(() => {
    fetch('/api/stats').then(r => r.json()).then(setStats);
    fetch('/api/insights').then(r => r.json()).then(setInsight);
  }, []);

  const pending = stats?.statusCounts.find(s => s.status === 'pending')?.count ?? 0;
  const total = stats?.replyRate.total ?? 0;
  const replied = stats?.replyRate.replied ?? 0;
  const replyRatePct = total > 0 ? Math.round((replied / total) * 100) : 0;

  return (
    <div className="max-w-4xl">
      <h2 className="text-2xl font-bold mb-6">ダッシュボード</h2>

      {/* AIインサイト */}
      {insight && (
        <div className={`flex items-start gap-3 p-4 rounded-xl mb-6 ${
          insight.level === 'warning' ? 'bg-yellow-50 border border-yellow-200' : 'bg-indigo-50 border border-indigo-100'
        }`}>
          <Lightbulb size={18} className={insight.level === 'warning' ? 'text-yellow-500 shrink-0 mt-0.5' : 'text-indigo-500 shrink-0 mt-0.5'} />
          <p className="text-sm text-gray-700">{insight.insight}</p>
        </div>
      )}

      {/* オンボーディング（データなし時） */}
      {isEmpty ? (
        <div className="bg-white rounded-2xl border border-gray-200 p-8 mb-6">
          <h3 className="font-semibold text-lg mb-2">はじめましょう</h3>
          <p className="text-sm text-gray-400 mb-8">以下の3ステップでWorkFlow AIを使い始められます</p>
          <div className="grid grid-cols-3 gap-4">
            {STEPS.map(({ icon: Icon, label, desc, href, color }, i) => (
              <Link key={href} href={href}
                className="flex flex-col items-start p-5 rounded-xl border border-gray-100 hover:border-indigo-200 hover:bg-indigo-50 transition-colors group">
                <div className="flex items-center gap-2 mb-3">
                  <span className="w-6 h-6 rounded-full bg-gray-100 text-gray-500 text-xs flex items-center justify-center font-bold">{i + 1}</span>
                  <Icon size={18} className={color} />
                </div>
                <span className="font-medium text-sm mb-1">{label}</span>
                <span className="text-xs text-gray-400 leading-relaxed">{desc}</span>
                <ArrowRight size={14} className="mt-3 text-gray-300 group-hover:text-indigo-400 transition-colors" />
              </Link>
            ))}
          </div>
        </div>
      ) : (
        <>
          {/* KPIカード */}
          <div className="grid grid-cols-4 gap-4 mb-6">
            <KpiCard icon={<AlertCircle className="text-yellow-500" size={18} />} label="未対応" value={pending} sub="件の対応待ち" bg="bg-yellow-50" />
            <KpiCard icon={<MessageSquare className="text-indigo-500" size={18} />} label="総送信数" value={total} sub="件" bg="bg-indigo-50" />
            <KpiCard icon={<TrendingUp className="text-green-500" size={18} />} label="返信率" value={`${replyRatePct}%`} sub={`${replied}/${total}件`} bg="bg-green-50" />
            <KpiCard icon={<AlertCircle className="text-red-500" size={18} />} label="要フォロー" value={stats?.overdueCount ?? 0} sub="3日以上放置" bg="bg-red-50" />
          </div>

          {/* 最近の記録 */}
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-sm text-gray-600">最近のコミュニケーション</h3>
              <Link href="/communications" className="text-xs text-indigo-500 hover:underline">すべて見る →</Link>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-400 border-b border-gray-100">
                  <th className="pb-2 font-medium">相手</th>
                  <th className="pb-2 font-medium">件名</th>
                  <th className="pb-2 font-medium">ステータス</th>
                  <th className="pb-2 font-medium">日時</th>
                </tr>
              </thead>
              <tbody>
                {stats?.recent.map(row => (
                  <tr key={row.id} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="py-2">
                      <span className="font-medium">{row.contact_name ?? '—'}</span>
                      {row.company && <span className="text-gray-400 text-xs ml-1">({row.company})</span>}
                    </td>
                    <td className="py-2 text-gray-600 max-w-xs truncate">{row.subject ?? '—'}</td>
                    <td className="py-2">
                      <span className={`px-2 py-0.5 rounded-full text-xs ${statusColor[row.status]}`}>
                        {statusLabel[row.status] ?? row.status}
                      </span>
                    </td>
                    <td className="py-2 text-gray-400 text-xs">{row.created_at?.slice(0, 16)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* クイックアクション（常時表示） */}
      {!isEmpty && (
        <div className="grid grid-cols-3 gap-3 mt-4">
          {STEPS.map(({ icon: Icon, label, href, color }) => (
            <Link key={href} href={href}
              className="flex items-center gap-3 p-4 bg-white rounded-xl border border-gray-200 hover:border-indigo-200 hover:bg-indigo-50 transition-colors text-sm">
              <Icon size={16} className={color} />
              <span className="font-medium text-gray-700">{label}</span>
              <ArrowRight size={14} className="ml-auto text-gray-300" />
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function KpiCard({ icon, label, value, sub, bg }: {
  icon: React.ReactNode; label: string; value: string | number; sub: string; bg: string;
}) {
  return (
    <div className={`${bg} rounded-xl p-4 border border-gray-100`}>
      <div className="flex items-center gap-2 mb-2">{icon}<span className="text-xs text-gray-500">{label}</span></div>
      <div className="text-3xl font-bold">{value}</div>
      <div className="text-xs text-gray-400 mt-1">{sub}</div>
    </div>
  );
}
