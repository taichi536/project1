'use client';
import { useEffect, useState } from 'react';
import { Trash2, Copy, Check } from 'lucide-react';

type Invitation = {
  id: number;
  email: string;
  token: string;
  accepted_at: string | null;
  created_at: string;
};

type RoutingRule = {
  id: number;
  match_domain: string | null;
  match_keyword: string | null;
  assign_to: string | null;
  assign_to_name: string | null;
};

type Template = {
  id: number;
  title: string;
  body: string;
};

type User = {
  id: string;
  name: string;
  email: string;
};

const SHORTCUTS = [
  { key: 'D', description: '対応済みにマーク' },
  { key: 'R', description: '返信モードを開く' },
  { key: 'Escape', description: 'パネルを閉じる' },
];

export default function SettingsPage() {
  const [rules, setRules] = useState<RoutingRule[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [ruleForm, setRuleForm] = useState({ match_domain: '', match_keyword: '', assign_to: '' });
  const [ruleError, setRuleError] = useState('');
  const [ruleLoading, setRuleLoading] = useState(false);

  const [templates, setTemplates] = useState<Template[]>([]);
  const [tplForm, setTplForm] = useState({ title: '', body: '' });
  const [tplError, setTplError] = useState('');
  const [tplLoading, setTplLoading] = useState(false);

  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteError, setInviteError] = useState('');
  const [inviteLoading, setInviteLoading] = useState(false);
  const [lastInviteUrl, setLastInviteUrl] = useState('');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    fetch('/api/routing-rules').then(r => r.json()).then(d => { if (d.rules) setRules(d.rules); });
    fetch('/api/users').then(r => r.json()).then(d => { if (d.users) setUsers(d.users); });
    fetch('/api/templates').then(r => r.json()).then(d => { if (d.templates) setTemplates(d.templates); });
    fetch('/api/invitations').then(r => r.json()).then(d => { if (d.invitations) setInvitations(d.invitations); });
  }, []);

  async function sendInvite(e: React.FormEvent) {
    e.preventDefault();
    setInviteError('');
    if (!inviteEmail.trim()) { setInviteError('メールアドレスを入力してください'); return; }
    setInviteLoading(true);
    const res = await fetch('/api/invitations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: inviteEmail }),
    });
    const data = await res.json();
    if (!res.ok) {
      setInviteError(data.error || 'エラーが発生しました');
    } else {
      setLastInviteUrl(data.inviteUrl);
      setInviteEmail('');
      const updated = await fetch('/api/invitations').then(r => r.json());
      if (updated.invitations) setInvitations(updated.invitations);
    }
    setInviteLoading(false);
  }

  function copyInviteUrl() {
    navigator.clipboard.writeText(lastInviteUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function addRule(e: React.FormEvent) {
    e.preventDefault();
    setRuleError('');
    if (!ruleForm.match_domain && !ruleForm.match_keyword) {
      setRuleError('ドメインまたはキーワードを入力してください');
      return;
    }
    setRuleLoading(true);
    const res = await fetch('/api/routing-rules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(ruleForm),
    });
    const data = await res.json();
    if (!res.ok) {
      setRuleError(data.error || 'エラーが発生しました');
    } else {
      setRuleForm({ match_domain: '', match_keyword: '', assign_to: '' });
      const updated = await fetch('/api/routing-rules').then(r => r.json());
      if (updated.rules) setRules(updated.rules);
    }
    setRuleLoading(false);
  }

  async function deleteRule(id: number) {
    await fetch(`/api/routing-rules/${id}`, { method: 'DELETE' });
    setRules(prev => prev.filter(r => r.id !== id));
  }

  async function addTemplate(e: React.FormEvent) {
    e.preventDefault();
    setTplError('');
    if (!tplForm.title.trim() || !tplForm.body.trim()) {
      setTplError('タイトルと本文は必須です');
      return;
    }
    setTplLoading(true);
    const res = await fetch('/api/templates', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(tplForm),
    });
    const data = await res.json();
    if (!res.ok) {
      setTplError(data.error || 'エラーが発生しました');
    } else {
      setTplForm({ title: '', body: '' });
      if (data.template) setTemplates(prev => [data.template, ...prev]);
    }
    setTplLoading(false);
  }

  async function deleteTemplate(id: number) {
    await fetch(`/api/templates/${id}`, { method: 'DELETE' });
    setTemplates(prev => prev.filter(t => t.id !== id));
  }

  return (
    <div className="max-w-3xl mx-auto py-8 px-4 space-y-10">
      <h2 className="text-2xl font-bold text-gray-900">設定</h2>

      {/* チームメンバー招待 */}
      <section>
        <h3 className="text-lg font-semibold text-gray-800 mb-4">チームメンバー招待</h3>

        <div className="bg-white border border-gray-200 rounded-xl p-6 mb-4">
          <form onSubmit={sendInvite} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">招待するメールアドレス</label>
              <input
                type="email"
                value={inviteEmail}
                onChange={e => setInviteEmail(e.target.value)}
                placeholder="teammate@example.com"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            {inviteError && <p className="text-red-500 text-xs">{inviteError}</p>}
            <button
              type="submit"
              disabled={inviteLoading}
              className="bg-indigo-600 text-white text-sm px-4 py-2 rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              {inviteLoading ? '送信中...' : '招待を送る'}
            </button>
          </form>

          {lastInviteUrl && (
            <div className="mt-4 p-3 bg-indigo-50 rounded-lg flex items-center gap-2">
              <p className="text-xs text-indigo-700 flex-1 break-all">{lastInviteUrl}</p>
              <button
                onClick={copyInviteUrl}
                className="text-indigo-600 hover:text-indigo-800 shrink-0"
                title="コピー"
              >
                {copied ? <Check size={15} /> : <Copy size={15} />}
              </button>
            </div>
          )}
        </div>

        {invitations.length === 0 ? (
          <p className="text-sm text-gray-400 px-1">招待がまだありません</p>
        ) : (
          <div className="space-y-2">
            {invitations.map(inv => (
              <div key={inv.id} className="bg-white border border-gray-200 rounded-xl px-4 py-3 flex items-center justify-between gap-4">
                <span className="text-sm text-gray-700">{inv.email}</span>
                {inv.accepted_at ? (
                  <span className="text-xs bg-green-50 text-green-700 px-2 py-0.5 rounded">承認済み</span>
                ) : (
                  <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded">未承認</span>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* 自動振り分けルール */}
      <section>
        <h3 className="text-lg font-semibold text-gray-800 mb-4">自動振り分けルール</h3>

        <div className="bg-white border border-gray-200 rounded-xl p-6 mb-4">
          <form onSubmit={addRule} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">ドメイン（例: example.com）</label>
                <input
                  type="text"
                  value={ruleForm.match_domain}
                  onChange={e => setRuleForm(prev => ({ ...prev, match_domain: e.target.value }))}
                  placeholder="example.com"
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">キーワード</label>
                <input
                  type="text"
                  value={ruleForm.match_keyword}
                  onChange={e => setRuleForm(prev => ({ ...prev, match_keyword: e.target.value }))}
                  placeholder="見積もり"
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">担当者</label>
              <select
                value={ruleForm.assign_to}
                onChange={e => setRuleForm(prev => ({ ...prev, assign_to: e.target.value }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              >
                <option value="">未割り当て</option>
                {users.map(u => (
                  <option key={u.id} value={u.id}>{u.name} ({u.email})</option>
                ))}
              </select>
            </div>
            {ruleError && <p className="text-red-500 text-xs">{ruleError}</p>}
            <button
              type="submit"
              disabled={ruleLoading}
              className="bg-indigo-600 text-white text-sm px-4 py-2 rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              {ruleLoading ? '追加中...' : 'ルールを追加'}
            </button>
          </form>
        </div>

        {rules.length === 0 ? (
          <p className="text-sm text-gray-400 px-1">ルールがまだありません</p>
        ) : (
          <div className="space-y-2">
            {rules.map(rule => (
              <div key={rule.id} className="bg-white border border-gray-200 rounded-xl px-4 py-3 flex items-center justify-between gap-4">
                <div className="flex flex-wrap gap-2 text-sm">
                  {rule.match_domain && (
                    <span className="bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded text-xs">
                      ドメイン: {rule.match_domain}
                    </span>
                  )}
                  {rule.match_keyword && (
                    <span className="bg-purple-50 text-purple-700 px-2 py-0.5 rounded text-xs">
                      キーワード: {rule.match_keyword}
                    </span>
                  )}
                  {rule.assign_to_name ? (
                    <span className="text-gray-500 text-xs">→ {rule.assign_to_name}</span>
                  ) : (
                    <span className="text-gray-400 text-xs">→ 未割り当て</span>
                  )}
                </div>
                <button
                  onClick={() => deleteRule(rule.id)}
                  className="text-gray-400 hover:text-red-500 transition-colors shrink-0"
                  title="削除"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* テンプレート管理 */}
      <section>
        <h3 className="text-lg font-semibold text-gray-800 mb-4">テンプレート管理</h3>

        <div className="bg-white border border-gray-200 rounded-xl p-6 mb-4">
          <p className="text-xs text-gray-500 mb-3">
            使用できる変数: <code className="bg-gray-100 px-1 rounded">{'{{名前}}'}</code>{' '}
            <code className="bg-gray-100 px-1 rounded">{'{{会社名}}'}</code>{' '}
            <code className="bg-gray-100 px-1 rounded">{'{{件名}}'}</code>
          </p>
          <form onSubmit={addTemplate} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">タイトル</label>
              <input
                type="text"
                value={tplForm.title}
                onChange={e => setTplForm(prev => ({ ...prev, title: e.target.value }))}
                placeholder="初回ご連絡の返信"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">本文</label>
              <textarea
                value={tplForm.body}
                onChange={e => setTplForm(prev => ({ ...prev, body: e.target.value }))}
                placeholder={'{{名前}} 様\n\nお世話になっております。\n{{件名}} についてご連絡いたします。'}
                rows={5}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 resize-none"
              />
            </div>
            {tplError && <p className="text-red-500 text-xs">{tplError}</p>}
            <button
              type="submit"
              disabled={tplLoading}
              className="bg-indigo-600 text-white text-sm px-4 py-2 rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              {tplLoading ? '追加中...' : 'テンプレートを追加'}
            </button>
          </form>
        </div>

        {templates.length === 0 ? (
          <p className="text-sm text-gray-400 px-1">テンプレートがまだありません</p>
        ) : (
          <div className="space-y-3">
            {templates.map(tpl => (
              <div key={tpl.id} className="bg-white border border-gray-200 rounded-xl p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm text-gray-800 mb-1">{tpl.title}</p>
                    <p className="text-xs text-gray-500 whitespace-pre-wrap line-clamp-3">{tpl.body}</p>
                  </div>
                  <button
                    onClick={() => deleteTemplate(tpl.id)}
                    className="text-gray-400 hover:text-red-500 transition-colors shrink-0 mt-0.5"
                    title="削除"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ショートカット一覧 */}
      <section>
        <h3 className="text-lg font-semibold text-gray-800 mb-4">ショートカット一覧</h3>
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          {SHORTCUTS.map((s, i) => (
            <div
              key={s.key}
              className={`flex items-center gap-4 px-5 py-3 ${i !== SHORTCUTS.length - 1 ? 'border-b border-gray-100' : ''}`}
            >
              <kbd className="bg-gray-100 text-gray-700 text-xs font-mono px-2 py-1 rounded border border-gray-200 min-w-[2.5rem] text-center">
                {s.key}
              </kbd>
              <span className="text-sm text-gray-600">{s.description}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
