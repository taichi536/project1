'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, CheckSquare, BarChart2, LogOut, Folder, Inbox, Settings } from 'lucide-react';
import { signOut, useSession } from 'next-auth/react';
import { useEffect, useState } from 'react';

const nav = [
  { href: '/', label: 'ダッシュボード', icon: LayoutDashboard },
  { href: '/inbox', label: '受信トレイ', icon: Inbox, badge: true },
  { href: '/projects', label: '案件管理', icon: Folder },
  { href: '/tasks', label: 'タスク管理', icon: CheckSquare },
  { href: '/analytics', label: '分析', icon: BarChart2 },
  { href: '/settings', label: '設定', icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { data: session } = useSession();
  const [needsReplyCount, setNeedsReplyCount] = useState(0);

  useEffect(() => {
    fetch('/api/stats').then(r => r.json()).then(d => { if (!d.error) setNeedsReplyCount(d.needsReply ?? 0); });
  }, []);

  return (
    <aside className="w-56 bg-white border-r border-gray-200 flex flex-col py-6 px-4 shrink-0">
      <div className="mb-8">
        <h1 className="text-lg font-bold text-indigo-600">WorkFlow AI</h1>
        <p className="text-xs text-gray-400 mt-1">業務効率化アシスタント</p>
      </div>

      <nav className="flex flex-col gap-1 flex-1">
        {nav.map(({ href, label, icon: Icon, badge }) => {
          const active = pathname === href;
          return (
            <Link key={href} href={href}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                active ? 'bg-indigo-50 text-indigo-700 font-medium' : 'text-gray-600 hover:bg-gray-100'
              }`}>
              <Icon size={16} />
              <span className="flex-1">{label}</span>
              {badge && needsReplyCount > 0 && (
                <span className="bg-red-500 text-white text-xs rounded-full px-1.5 py-0.5 min-w-[18px] text-center leading-none">
                  {needsReplyCount > 99 ? '99+' : needsReplyCount}
                </span>
              )}
            </Link>
          );
        })}

      </nav>

      {session?.user && (
        <div className="border-t border-gray-100 pt-4 mt-4">
          <div className="px-3 mb-2">
            <p className="text-xs font-medium text-gray-700 truncate">{session.user.name}</p>
            <p className="text-xs text-gray-400 truncate">{session.user.email}</p>
          </div>
          <button onClick={() => signOut({ callbackUrl: '/login' })}
            className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-500 hover:bg-gray-100 w-full">
            <LogOut size={16} />
            ログアウト
          </button>
        </div>
      )}
    </aside>
  );
}
