// ============================================================
// 既存GASスクリプトの末尾に追記してください
// ============================================================
//
// 【スプレッドシートの準備】
//   1. 既存のスカウト管理スプレッドシートに「ポジション」という名前の
//      新しいシートタブを追加
//   2. A1=ポジション名, B1=募集要件（ヘッダー行）
//   3. 2行目以降にポジション情報を入力
//
// 【GASへの追記手順】
//   1. 既存のGASスクリプトを開く
//   2. このコードを末尾にコピペして保存
//   3. 「デプロイ」→「デプロイを管理」→既存デプロイの「編集（鉛筆アイコン）」
//      →「バージョン」を「新しいバージョン」に変更→「デプロイ」
//      ※新規デプロイではなく既存デプロイの更新でOKです
// ============================================================

function getPositions_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName('ポジション');

  if (!sheet) {
    return { ok: false, error: '「ポジション」シートが見つかりません' };
  }

  const lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return { ok: true, positions: [] };
  }

  const values = sheet.getRange(2, 1, lastRow - 1, 2).getValues();
  const positions = values
    .map(row => ({
      name: String(row[0] || '').trim(),
      description: String(row[1] || '').trim(),
    }))
    .filter(p => p.name);

  return { ok: true, positions };
}

// ※既存のdoPost関数内の try ブロックに以下を追記してください：
//
//   if (data.action === 'getPositions') {
//     const result = getPositions_();
//     return ContentService.createTextOutput(JSON.stringify(result))
//       .setMimeType(ContentService.MimeType.JSON);
//   }
//
// 追記場所の例（既存コードの抜粋）:
//
//   function doPost(e) {
//     try {
//       const data = JSON.parse(e.postData.contents);
//       if (data.secret !== SECRET) { ... }
//
//       ↓ ここに追記 ↓
//       if (data.action === 'getPositions') {
//         const result = getPositions_();
//         return ContentService.createTextOutput(JSON.stringify(result))
//           .setMimeType(ContentService.MimeType.JSON);
//       }
//
//       const cols = RECRUITER_COLS[data.recruiter];  ← 既存コード
