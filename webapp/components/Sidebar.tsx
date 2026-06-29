'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, MessageSquare, CheckSquare, BarChart2, Sparkles, Upload } from 'lucide-react';

const nav = [
  { href: '/', label: 'ダッシュボード', icon: LayoutDashboard },
  { href: '/communications', label: 'コミュニケーション', icon: MessageSquare },
  { href: '/tasks', label: 'タスク管理', icon: CheckSquare },
  { href: '/analytics', label: '分析', icon: BarChart2 },
  { href: '/generate', label: 'AI文面生成', icon: Sparkles },
  { href: '/import', label: 'データ取込', icon: Upload },
];

export default function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="w-56 bg-white border-r border-gray-200 flex flex-col py-6 px-4 shrink-0">
      <div className="mb-8">
        <h1 className="text-lg font-bold text-indigo-600">WorkFlow AI</h1>
        <p className="text-xs text-gray-400 mt-1">業務効率化アシスタント</p>
      </div>
      <nav className="flex flex-col gap-1">
        {nav.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                active
                  ? 'bg-indigo-50 text-indigo-700 font-medium'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              <Icon size={16} />
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
