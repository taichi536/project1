// ============================================================
// 社内ナレッジ（チャットbot用）— 既存GASスクリプトの末尾に追記してください
// ============================================================
//
// なぜスプレッドシートに置くのか
//   拡張機能のリポジトリは公開されているため、Supabaseの公開鍵も公開されている。
//   そこに社内ナレッジを置くと誰でも読めてしまう。GAS経由なら、URLと合言葉は
//   各メンバーの拡張機能の設定の中にしかない。ポジション情報と同じ経路になる。
//   更新もスプレッドシートに書くだけで済み、いまの運用のまま増やしていける。
//
// 【スプレッドシートの準備】
//   1. スカウト管理スプレッドシートに「ナレッジ」という名前のシートタブを追加
//   2. 1行目（ヘッダー）:
//      A1=カテゴリ, B1=見出し, C1=内容
//   3. 2行目以降に書いていく。1行＝1つの知識。
//
//      カテゴリ      見出し                  内容
//      ----------------------------------------------------------------
//      選考          アクセンチュアの選考     3次面接まで。1次はケース…
//      スカウト      返信率が高い書き出し     数値の実績を最初の一文に…
//      条件          未経験可のファーム       〇〇、〇〇。年齢は35歳まで…
//
//   ※内容は長くても構いません（セルにそのまま書けます）。
//   ※候補者の氏名・経歴など個人情報は書かないでください。
//     チャットのたびに外部のAIへ送られます。
//
// 【GASへの追記手順】
//   1. 既存のGASスクリプトを開く
//   2. このファイルの内容を末尾にコピペして保存
//      （既存のファイルを上書きしないこと。末尾に足すだけです）
//   3. 既存の doPost 関数内（secretチェックの直後）に、次の5行を追加:
//
//      if (data.action === 'getKnowledge') {
//        const result = getKnowledge_();
//        return ContentService.createTextOutput(JSON.stringify(result))
//          .setMimeType(ContentService.MimeType.JSON);
//      }
//
//   4. 「デプロイ」→「デプロイを管理」→既存デプロイの編集（鉛筆マーク）→
//      バージョン「新バージョン」→「デプロイ」
//      ※これをやらないと、追記した内容は反映されません
// ============================================================

function getKnowledge_() {
  try {
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('ナレッジ');
    if (!sheet) return { ok: false, error: '「ナレッジ」シートが見つかりません' };

    const values = sheet.getDataRange().getValues();
    if (values.length < 2) return { ok: true, items: [] };

    const items = [];
    for (let i = 1; i < values.length; i++) {
      const category = String(values[i][0] || '').trim();
      const title    = String(values[i][1] || '').trim();
      const body     = String(values[i][2] || '').trim();
      // 見出しも内容も空の行は、表の下の余白。読み飛ばす
      if (!title && !body) continue;
      items.push({ category, title, body });
    }
    return { ok: true, items: items, updatedAt: new Date().toISOString() };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}
