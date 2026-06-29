'use client';
import { useState, useRef } from 'react';
import { Upload, CheckCircle, AlertCircle, FileText, Download } from 'lucide-react';

type ImportResult = { imported: number; total: number; errors: string[] };

const SAMPLE_CSV = `名前,会社名,役職,メール,種別,件名,ステータス,担当者,送信日
田中 花子,株式会社サンプル,営業部長,hanako@example.com,メール,新サービスのご提案,未対応,山田,2026-06-01
鈴木 一郎,合同会社テスト,代表取締役,,電話,定例MTGの件,対応中,佐藤,2026-06-05
佐藤 美咲,テスト株式会社,人事担当,,メール,採用についてのお問い合わせ,完了,山田,2026-06-10`;

export default function ImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = (f: File) => {
    if (!f.name.endsWith('.csv')) { alert('CSVファイルを選択してください'); return; }
    setFile(f);
    setResult(null);
  };

  const downloadSample = () => {
    const blob = new Blob(['﻿' + SAMPLE_CSV], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'sample.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = async () => {
    if (!file) return;
    setLoading(true);
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch('/api/import', { method: 'POST', body: fd });
    setResult(await res.json());
    setLoading(false);
  };

  return (
    <div className="max-w-2xl">
      <h2 className="text-2xl font-bold mb-2">データ取込</h2>
      <p className="text-sm text-gray-400 mb-6">ExcelやGoogleスプレッドシートから書き出したCSVをそのまま取り込めます</p>

      {/* サンプルCSVダウンロード */}
      <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-4 mb-6 flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-indigo-700">まずはサンプルCSVをダウンロード</p>
          <p className="text-xs text-indigo-400 mt-0.5">このフォーマットに合わせて入力すると取り込めます</p>
        </div>
        <button onClick={downloadSample}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 shrink-0">
          <Download size={14} /> サンプルをDL
        </button>
      </div>

      {/* ドロップゾーン */}
      <div
        onClick={() => inputRef.current?.click()}
        onDrop={e => { e.preventDefault(); setDragOver(false); if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]); }}
        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors mb-4 ${
          dragOver ? 'border-indigo-400 bg-indigo-50' : 'border-gray-200 hover:border-indigo-300 hover:bg-gray-50'
        }`}>
        <input ref={inputRef} type="file" accept=".csv" className="hidden"
          onChange={e => { if (e.target.files?.[0]) handleFile(e.target.files[0]); }} />
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
            <p className="text-gray-400 text-sm mt-1">Excelは「名前をつけて保存」→「CSV」で書き出せます</p>
          </>
        )}
      </div>

      {/* 対応カラム */}
      <details className="bg-gray-50 rounded-xl mb-6 text-sm">
        <summary className="px-4 py-3 cursor-pointer font-medium text-gray-600 select-none">
          対応しているカラム名を確認する
        </summary>
        <div className="px-4 pb-4 grid grid-cols-2 gap-2 text-gray-500 text-xs">
          {[
            ['相手・名前', '名前 / 氏名 / name'],
            ['会社', '会社名 / 企業名 / company'],
            ['役職・業務', '役職 / ポジション / role'],
            ['メール', 'メール / email'],
            ['種別', '種別 / 区分 / type'],
            ['件名', '件名 / タイトル / subject'],
            ['本文', '本文 / 内容 / body'],
            ['ステータス', '状態 / 対応状況 / status'],
            ['担当者', '担当 / assigned_to'],
            ['日付', '送信日 / 日付 / date'],
          ].map(([label, keys]) => (
            <div key={label}><span className="text-gray-700 font-medium">{label}：</span>{keys}</div>
          ))}
        </div>
      </details>

      <button onClick={handleImport} disabled={!file || loading}
        className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-40">
        <Upload size={16} />
        {loading ? 'インポート中...' : 'インポートする'}
      </button>

      {result && (
        <div className={`mt-6 rounded-xl p-5 ${result.imported > 0 ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
          <div className="flex items-center gap-2 mb-2">
            {result.imported > 0
              ? <CheckCircle size={18} className="text-green-600" />
              : <AlertCircle size={18} className="text-red-500" />}
            <span className="font-semibold text-sm">
              {result.total} 件中 {result.imported} 件をインポートしました
            </span>
          </div>
          {result.imported > 0 && (
            <p className="text-xs text-green-600">ダッシュボードで確認できます</p>
          )}
          {result.errors.length > 0 && (
            <ul className="text-xs text-red-600 mt-2 list-disc list-inside">
              {result.errors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
