'use client';
import { useState, useRef } from 'react';
import { Upload, CheckCircle, AlertCircle, FileText } from 'lucide-react';

type ImportResult = {
  imported: number;
  total: number;
  errors: string[];
};

export default function ImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = (f: File) => {
    if (!f.name.endsWith('.csv')) return alert('CSVファイルを選択してください');
    setFile(f);
    setResult(null);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  };

  const handleImport = async () => {
    if (!file) return;
    setLoading(true);
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch('/api/import', { method: 'POST', body: fd });
    const data = await res.json();
    setResult(data);
    setLoading(false);
  };

  return (
    <div className="max-w-2xl">
      <h2 className="text-2xl font-bold mb-2">データインポート</h2>
      <p className="text-sm text-gray-400 mb-6">
        CSVファイルをアップロードすると、コミュニケーション記録を一括で取り込めます
      </p>

      {/* ドロップゾーン */}
      <div
        onClick={() => inputRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors mb-4 ${
          dragOver ? 'border-indigo-400 bg-indigo-50' : 'border-gray-200 hover:border-indigo-300 hover:bg-gray-50'
        }`}
      >
        <input ref={inputRef} type="file" accept=".csv" className="hidden" onChange={e => { if (e.target.files?.[0]) handleFile(e.target.files[0]); }} />
        <Upload size={32} className="mx-auto text-gray-300 mb-3" />
        {file ? (
          <div className="flex items-center justify-center gap-2 text-indigo-600">
            <FileText size={16} />
            <span className="font-medium">{file.name}</span>
            <span className="text-gray-400 text-sm">({Math.round(file.size / 1024)} KB)</span>
          </div>
        ) : (
          <>
            <p className="text-gray-500 font-medium">CSVファイルをドロップ、またはクリックして選択</p>
            <p className="text-gray-400 text-sm mt-1">スプレッドシートから書き出したファイルをそのまま使えます</p>
          </>
        )}
      </div>

      {/* 対応カラムの説明 */}
      <div className="bg-gray-50 rounded-xl p-5 mb-6 text-sm">
        <h3 className="font-semibold text-gray-600 mb-3">対応しているカラム名（どれでも可）</h3>
        <div className="grid grid-cols-2 gap-2 text-gray-500">
          {[
            ['相手・連絡先', '名前 / 氏名 / 候補者名 / name'],
            ['会社', '会社名 / 企業名 / company'],
            ['役職・業務', '役職 / ポジション / 職種 / role'],
            ['メール', 'メール / メールアドレス / email'],
            ['プラットフォーム', 'サービス / platform'],
            ['件名', '件名 / タイトル / subject'],
            ['本文・内容', '本文 / メッセージ / 内容 / body'],
            ['ステータス', '状態 / 対応状況 / status'],
            ['担当者', '担当 / assigned_to'],
            ['送信日', '日付 / 送信日 / 送付日 / date'],
          ].map(([label, keys]) => (
            <div key={label}>
              <span className="text-gray-700 font-medium">{label}：</span>{keys}
            </div>
          ))}
        </div>
      </div>

      <button
        onClick={handleImport}
        disabled={!file || loading}
        className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-40"
      >
        <Upload size={16} />
        {loading ? 'インポート中...' : 'インポートする'}
      </button>

      {result && (
        <div className={`mt-6 rounded-xl p-5 ${result.imported > 0 ? 'bg-green-50' : 'bg-red-50'}`}>
          <div className="flex items-center gap-2 mb-2">
            {result.imported > 0 ? <CheckCircle size={20} className="text-green-600" /> : <AlertCircle size={20} className="text-red-500" />}
            <span className="font-semibold">
              {result.total} 件中 {result.imported} 件をインポートしました
            </span>
          </div>
          {result.errors.length > 0 && (
            <ul className="text-sm text-red-600 mt-2 list-disc list-inside">
              {result.errors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
