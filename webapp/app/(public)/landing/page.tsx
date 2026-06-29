import Link from 'next/link';
import { MessageSquare, BarChart2, Sparkles, CheckCircle } from 'lucide-react';

const FEATURES = [
  {
    icon: MessageSquare,
    title: 'コミュニケーションを一元管理',
    desc: 'メール・商談・電話など、あらゆる対外連絡の対応状況をチームで共有。対応漏れや属人化を防ぎます。',
  },
  {
    icon: BarChart2,
    title: 'データを可視化・分析',
    desc: '返信率・対応件数・フォロー状況をリアルタイムで把握。AIが次にやるべきことを提案します。',
  },
  {
    icon: Sparkles,
    title: 'AIが文面を自動生成',
    desc: '営業メール・返信・フォローアップ・提案書など、相手の情報を入力するだけでAIが最適な文章を作成。',
  },
];

const STEPS = [
  { num: '1', title: 'アカウントを作成', desc: 'メールアドレスとパスワードで30秒で登録できます' },
  { num: '2', title: 'データを取り込む', desc: 'Excelやスプレッドシートからそのままインポート可能' },
  { num: '3', title: 'AIと一緒に業務を効率化', desc: 'ダッシュボードでチームの状況を把握し、AIが次の一手を提案' },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-white">
      {/* ヘッダー */}
      <header className="flex items-center justify-between px-8 py-5 border-b border-gray-100">
        <div>
          <span className="text-xl font-bold text-indigo-600">WorkFlow AI</span>
          <span className="text-xs text-gray-400 ml-2">業務効率化アシスタント</span>
        </div>
        <div className="flex gap-3">
          <Link href="/login" className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 font-medium">
            ログイン
          </Link>
          <Link href="/login" className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg font-medium hover:bg-indigo-700">
            無料で始める
          </Link>
        </div>
      </header>

      {/* ヒーロー */}
      <section className="text-center px-8 py-24 max-w-3xl mx-auto">
        <div className="inline-block px-3 py-1 bg-indigo-50 text-indigo-600 text-xs font-medium rounded-full mb-6">
          中小企業向け AIアシスタント
        </div>
        <h1 className="text-4xl font-bold text-gray-900 leading-tight mb-6">
          データを入れるだけで、<br />
          <span className="text-indigo-600">AIが次のアクションを提案</span>
        </h1>
        <p className="text-lg text-gray-500 mb-10 leading-relaxed">
          スプレッドシートやCSVで管理していた業務記録をそのまま取り込み。<br />
          対応漏れを防ぎ、チームで共有し、AIが文面まで作ってくれます。
        </p>
        <div className="flex items-center justify-center gap-4">
          <Link href="/login"
            className="px-8 py-3.5 bg-indigo-600 text-white rounded-xl font-semibold hover:bg-indigo-700 transition-colors">
            無料で始める →
          </Link>
          <Link href="/login" className="px-8 py-3.5 border border-gray-200 text-gray-600 rounded-xl font-medium hover:bg-gray-50 transition-colors">
            ログイン
          </Link>
        </div>
        <p className="text-xs text-gray-400 mt-4">クレジットカード不要・すぐに使えます</p>
      </section>

      {/* 機能 */}
      <section className="bg-gray-50 px-8 py-20">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-2xl font-bold text-center mb-12">3つの機能で業務を効率化</h2>
          <div className="grid grid-cols-3 gap-6">
            {FEATURES.map(({ icon: Icon, title, desc }) => (
              <div key={title} className="bg-white rounded-2xl p-6 border border-gray-100">
                <div className="w-10 h-10 bg-indigo-50 rounded-xl flex items-center justify-center mb-4">
                  <Icon size={20} className="text-indigo-600" />
                </div>
                <h3 className="font-semibold mb-2">{title}</h3>
                <p className="text-sm text-gray-500 leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 使い方 */}
      <section className="px-8 py-20 max-w-3xl mx-auto">
        <h2 className="text-2xl font-bold text-center mb-12">3ステップで始められます</h2>
        <div className="flex flex-col gap-6">
          {STEPS.map(({ num, title, desc }) => (
            <div key={num} className="flex items-start gap-5">
              <div className="w-10 h-10 rounded-full bg-indigo-600 text-white flex items-center justify-center font-bold text-sm shrink-0">
                {num}
              </div>
              <div>
                <h3 className="font-semibold mb-1">{title}</h3>
                <p className="text-sm text-gray-500">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="bg-indigo-600 px-8 py-16 text-center text-white">
        <h2 className="text-2xl font-bold mb-4">今すぐ無料で試してみましょう</h2>
        <p className="text-indigo-200 mb-8 text-sm">登録はメールアドレスとパスワードだけ。30秒で完了します。</p>
        <Link href="/login"
          className="inline-block px-8 py-3.5 bg-white text-indigo-600 rounded-xl font-semibold hover:bg-indigo-50 transition-colors">
          無料で始める →
        </Link>
      </section>

      <footer className="text-center py-8 text-xs text-gray-400">
        © 2026 WorkFlow AI
      </footer>
    </div>
  );
}
