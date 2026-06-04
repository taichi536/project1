// ============================================================
// 既存GASスクリプトの末尾に追記してください
// ============================================================
//
// 【スプレッドシートの準備】
//   1. 既存のスカウト管理スプレッドシートに「ポジション」という名前の
//      新しいシートタブを追加
//   2. 1行目（ヘッダー）:
//      A1=ポジション名, B1=業務概要, C1=必須スキル・経験,
//      D1=歓迎スキル・経験, E1=求める人物像
//   3. 2行目以降にポジション情報を入力
//      ※各列は別々のセルに書くので、長い文章もそのまま入力可能
//
// 【GASへの追記手順】
//   1. 既存のGASスクリプトを開く
//   2. このファイルの内容を末尾にコピペして保存
//   3. 既存の doPost 関数内（secretチェックの直後）に以下を追加:
//
//      if (data.action === 'getPositions') {
//        const result = getPositions_();
//        return ContentService.createTextOutput(JSON.stringify(result))
//          .setMimeType(ContentService.MimeType.JSON);
//      }
//
//   4. 「デプロイ」→「デプロイを管理」→既存デプロイの編集（鉛筆）
//      →「バージョン」を「新しいバージョン」に変更→「デプロイ」
//      ※URLは変わりません
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

  // A〜E列を取得（ポジション名, 業務概要, 必須スキル, 歓迎スキル, 求める人物像）
  const values = sheet.getRange(2, 1, lastRow - 1, 5).getValues();

  const positions = values
    .map(row => {
      const name        = String(row[0] || '').trim();
      const overview    = String(row[1] || '').trim();
      const required    = String(row[2] || '').trim();
      const preferred   = String(row[3] || '').trim();
      const personality = String(row[4] || '').trim();

      if (!name) return null;

      // 入力済みの項目だけ結合して description を作る
      const parts = [];
      if (overview)    parts.push(`【業務概要】${overview}`);
      if (required)    parts.push(`【必須スキル・経験】${required}`);
      if (preferred)   parts.push(`【歓迎スキル・経験】${preferred}`);
      if (personality) parts.push(`【求める人物像】${personality}`);

      return { name, description: parts.join(' / ') };
    })
    .filter(Boolean);

  return { ok: true, positions };
}

// 動作確認用（Apps Scriptエディタから実行）
function testGetPositions() {
  const fakeEvent = {
    postData: {
      contents: JSON.stringify({
        secret: SECRET,
        action: 'getPositions',
      })
    }
  };
  Logger.log(doPost(fakeEvent).getContent());
}
