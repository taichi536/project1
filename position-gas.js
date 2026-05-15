// ============================================================
// ポジション管理GAS — Snow-we.Inc ポジション提案システム用
//
// 【セットアップ手順】
//   1. Google スプレッドシートを新規作成
//   2. シート名を「ポジション」に変更
//   3. 1行目（ヘッダー）: A1=ポジション名, B1=募集要件
//   4. 2行目以降にポジション情報をコピペ
//   5. 拡張機能 > Apps Script にこのコードを貼り付けて保存
//   6. デプロイ > 新しいデプロイ > ウェブアプリ
//      - 実行ユーザー: 自分
//      - アクセスできるユーザー: 全員
//   7. デプロイURLを拡張機能の設定タブ「ポジション管理GAS URL」に入力
// ============================================================

const POSITION_SECRET = 'snowwe2024';
const POSITION_SHEET_NAME = 'ポジション';

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);

    if (data.secret !== POSITION_SECRET) {
      return json({ ok: false, error: 'unauthorized' });
    }

    if (data.action === 'getPositions') {
      return getPositions();
    }

    return json({ ok: false, error: '不明なアクション' });

  } catch (err) {
    return json({ ok: false, error: err.message });
  }
}

function getPositions() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(POSITION_SHEET_NAME);

  if (!sheet) {
    return json({ ok: false, error: '「ポジション」シートが見つかりません' });
  }

  const lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return json({ ok: true, positions: [] });
  }

  const values = sheet.getRange(2, 1, lastRow - 1, 2).getValues();
  const positions = values
    .map(row => ({
      name: String(row[0] || '').trim(),
      description: String(row[1] || '').trim(),
    }))
    .filter(p => p.name);

  return json({ ok: true, positions });
}

function json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// 動作確認用（Apps Scriptエディタから実行）
function testGetPositions() {
  const fakeEvent = {
    postData: {
      contents: JSON.stringify({
        secret: POSITION_SECRET,
        action: 'getPositions',
      })
    }
  };
  Logger.log(doPost(fakeEvent).getContent());
}
