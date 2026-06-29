'use client';
import { useState } from 'react';
import { signIn } from 'next-auth/react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Sparkles, BarChart2, MessageSquare } from 'lucide-react';

const POINTS = [
  { icon: MessageSquare, text: '対応漏れをゼロに' },
  { icon: BarChart2, text: 'チームの状況を一目で把握' },
  { icon: Sparkles, text: 'AIが文面・提案を自動生成' },
];

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    const res = await signIn('credentials', { email: form.email, password: form.password, redirect: false });
    if (res?.error) setError('メールアドレスまたはパスワードが正しくありません');
    else router.push('/');
    setLoading(false);
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    const res = await fetch('/api/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    });
    const data = await res.json();
    if (!res.ok) { setError(data.error); setLoading(false); return; }
    await signIn('credentials', { email: form.email, password: form.password, redirect: false });
    router.push('/');
    setLoading(false);
  };

  return (
    <div className="min-h-screen flex">
      <div className="hidden lg:flex flex-col justify-center w-1/2 bg-indigo-600 px-16 text-white">
        <div className="mb-12">
          <h1 className="text-3xl font-bold mb-3">WorkFlow AI</h1>
          <p className="text-indigo-200 text-lg leading-relaxed">
            データを入れるだけで、AIが状況を分析して<br />次のアクションを提案します。
          </p>
        </div>
        <div className="flex flex-col gap-5">
          {POINTS.map(({ icon: Icon, text }) => (
            <div key={text} className="flex items-center gap-4">
              <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center shrink-0">
                <Icon size={20} />
              </div>
              <span className="font-medium">{text}</span>
            </div>
          ))}
        </div>
        <p className="mt-16 text-indigo-300 text-sm">
          ← <Link href="/landing" className="underline hover:text-white">サービスの詳細を見る</Link>
        </p>
      </div>

      <div className="flex-1 flex items-center justify-center px-8">
        <div className="w-full max-w-sm">
          <div className="mb-8 lg:hidden">
            <h1 className="text-2xl font-bold text-indigo-600">WorkFlow AI</h1>
          </div>
          <h2 className="text-xl font-bold mb-1">
            {mode === 'login' ? 'ログイン' : 'アカウント作成'}
          </h2>
          <p className="text-sm text-gray-400 mb-6">
            {mode === 'login' ? 'アカウントにログインしてください' : '無料ですぐに使い始められます'}
          </p>

          {/* Googleログイン */}
          <button onClick={() => signIn('google', { callbackUrl: '/' })}
            className="w-full flex items-center justify-center gap-3 border border-gray-200 rounded-lg py-2.5 text-sm font-medium hover:bg-gray-50 transition-colors mb-4">
            <svg width="18" height="18" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>
            Googleでログイン（Gmail連携）
          </button>

          <div className="flex items-center gap-3 mb-4">
            <div className="flex-1 h-px bg-gray-200" />
            <span className="text-xs text-gray-400">またはメールで</span>
            <div className="flex-1 h-px bg-gray-200" />
          </div>

          <form onSubmit={mode === 'login' ? handleLogin : handleRegister} className="flex flex-col gap-3">
            {mode === 'register' && (
              <div>
                <label className="text-xs text-gray-500 block mb-1">お名前</label>
                <input required placeholder="山田 太郎" value={form.name}
                  onChange={e => setForm({ ...form, name: e.target.value })}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />
              </div>
            )}
            <div>
              <label className="text-xs text-gray-500 block mb-1">メールアドレス</label>
              <input required type="email" placeholder="you@example.com" value={form.email}
                onChange={e => setForm({ ...form, email: e.target.value })}
                className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">パスワード</label>
              <input required type="password" placeholder="8文字以上" value={form.password}
                onChange={e => setForm({ ...form, password: e.target.value })}
                className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />
            </div>
            {error && (
              <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-xs text-red-600">{error}</div>
            )}
            <button type="submit" disabled={loading}
              className="mt-1 py-3 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 transition-colors">
              {loading ? '処理中...' : mode === 'login' ? 'ログイン' : '無料で始める'}
            </button>
          </form>

          <div className="mt-5 text-center text-sm text-gray-400">
            {mode === 'login' ? (
              <>アカウントをお持ちでない方は{' '}
                <button onClick={() => { setMode('register'); setError(''); }} className="text-indigo-600 font-medium hover:underline">新規登録</button>
              </>
            ) : (
              <>すでにアカウントをお持ちの方は{' '}
                <button onClick={() => { setMode('login'); setError(''); }} className="text-indigo-600 font-medium hover:underline">ログイン</button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
