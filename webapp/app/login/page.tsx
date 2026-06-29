'use client';
import { useState } from 'react';
import { signIn } from 'next-auth/react';
import { useRouter } from 'next/navigation';

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
    const res = await signIn('credentials', {
      email: form.email,
      password: form.password,
      redirect: false,
    });
    if (res?.error) {
      setError('メールアドレスまたはパスワードが正しくありません');
    } else {
      router.push('/');
    }
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
    if (!res.ok) {
      setError(data.error);
    } else {
      await signIn('credentials', { email: form.email, password: form.password, redirect: false });
      router.push('/');
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="bg-white rounded-2xl shadow-lg p-8 w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold text-indigo-600">WorkFlow AI</h1>
          <p className="text-sm text-gray-400 mt-1">業務効率化AIアシスタント</p>
        </div>

        <div className="flex rounded-lg border border-gray-200 p-1 mb-6">
          {(['login', 'register'] as const).map(m => (
            <button key={m} onClick={() => { setMode(m); setError(''); }}
              className={`flex-1 py-1.5 text-sm rounded-md font-medium transition-colors ${mode === m ? 'bg-indigo-600 text-white' : 'text-gray-500 hover:text-gray-700'}`}>
              {m === 'login' ? 'ログイン' : '新規登録'}
            </button>
          ))}
        </div>

        <form onSubmit={mode === 'login' ? handleLogin : handleRegister} className="flex flex-col gap-3">
          {mode === 'register' && (
            <input required placeholder="お名前" value={form.name}
              onChange={e => setForm({ ...form, name: e.target.value })}
              className="border border-gray-200 rounded-lg px-3 py-2 text-sm" />
          )}
          <input required type="email" placeholder="メールアドレス" value={form.email}
            onChange={e => setForm({ ...form, email: e.target.value })}
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm" />
          <input required type="password" placeholder="パスワード" value={form.password}
            onChange={e => setForm({ ...form, password: e.target.value })}
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm" />

          {error && <p className="text-red-500 text-xs">{error}</p>}

          <button type="submit" disabled={loading}
            className="mt-2 py-2.5 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50">
            {loading ? '処理中...' : mode === 'login' ? 'ログイン' : 'アカウント作成'}
          </button>
        </form>
      </div>
    </div>
  );
}
