// ============================================================
// Snow-we スカウト管理DB - Google Apps Script
// 対象スプレッドシート: スカウト管理DB（新規）
// ============================================================

// ── 設定 ────────────────────────────────────────────────────
const SLACK_WEBHOOK_URL = 'YOUR_SLACK_WEBHOOK_URL'; // ← Slack Incoming Webhook URLを貼る
const SLACK_CHANNEL     = '#scout-report';           // ← 送信先チャンネル名
const GAS_SECRET        = 'snowwe2024';

const SHEET_DB        = 'スカウト管理DB';
const SHEET_DASHBOARD = '効果測定';

const STATUS_LIST = ['未返信', '返信あり', '面談設定', '書類選考', '一次面接', '最終面接', '内定', '辞退', '見送り'];

const MEDIA_LABEL = {
  rds: 'RDS', bizreach: 'ビズリーチ', dodax: 'doda X',
  ambi: 'AMBI', green: 'Green', mynavi: 'マイナビ'
};

// ── doPost: 拡張機能からのスカウトデータを受信 ──────────────
function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    if (data.secret !== GAS_SECRET) {
      return ContentService.createTextOutput(JSON.stringify({ ok: false, error: 'unauthorized' }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    const ss    = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(SHEET_DB);
    if (!sheet) setupSheets();

    const dbSheet = ss.getSheetByName(SHEET_DB);
    const ts      = data.ts ? new Date(data.ts) : new Date();
    const media   = MEDIA_LABEL[data.media] || data.media || '';

    dbSheet.appendRow([
      ts,                    // A: 送信日時
      data.recruiter || '',  // B: 担当者
      data.age       || '',  // C: 年齢
      data.company   || '',  // D: 会社名
      data.univ      || '',  // E: 大学
      data.position  || '',  // F: ポジション名
      media,                 // G: 媒体
      '未返信',              // H: ステータス（初期値）
      '',                    // I: 返信日
      '',                    // J: 面談日
      '',                    // K: メモ
    ]);

    // ステータス列にドロップダウンを設定
    const lastRow = dbSheet.getLastRow();
    const statusCell = dbSheet.getRange(lastRow, 8); // H列
    const rule = SpreadsheetApp.newDataValidation()
      .requireValueInList(STATUS_LIST, true)
      .setAllowInvalid(false)
      .build();
    statusCell.setDataValidation(rule);

    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ ok: false, error: err.message }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

// ── setupSheets: シート初期設定（最初に一度だけ手動実行） ────
function setupSheets() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  // ── スカウト管理DBシート ──
  let db = ss.getSheetByName(SHEET_DB);
  if (!db) db = ss.insertSheet(SHEET_DB);
  db.clearContents();

  const dbHeaders = ['送信日時', '担当者', '年齢', '会社名', '大学', 'ポジション名', '媒体', 'ステータス', '返信日', '面談日', 'メモ'];
  db.getRange(1, 1, 1, dbHeaders.length).setValues([dbHeaders]);

  // ヘッダー行の書式
  const headerRange = db.getRange(1, 1, 1, dbHeaders.length);
  headerRange.setBackground('#4338CA').setFontColor('#ffffff').setFontWeight('bold');
  db.setFrozenRows(1);
  db.setColumnWidth(1, 150); // 送信日時
  db.setColumnWidth(4, 200); // 会社名
  db.setColumnWidth(6, 250); // ポジション名
  db.setColumnWidth(8, 120); // ステータス
  db.setColumnWidth(11, 200); // メモ

  // ── 効果測定シート ──
  let dash = ss.getSheetByName(SHEET_DASHBOARD);
  if (!dash) dash = ss.insertSheet(SHEET_DASHBOARD);

  Logger.log('シートのセットアップ完了');
}

// ── updateDashboard: 効果測定シートを更新 ───────────────────
function updateDashboard() {
  const ss     = SpreadsheetApp.getActiveSpreadsheet();
  const db     = ss.getSheetByName(SHEET_DB);
  const dash   = ss.getSheetByName(SHEET_DASHBOARD);
  if (!db || !dash) return;

  const rows = db.getDataRange().getValues();
  if (rows.length <= 1) return;

  const data = rows.slice(1).filter(r => r[0]); // ヘッダー除く・空行除く

  // 集計ヘルパー
  function aggregate(keyIdx) {
    const map = {};
    data.forEach(r => {
      const key    = r[keyIdx] || '不明';
      const status = r[7] || '未返信';
      if (!map[key]) map[key] = { total: 0, replied: 0, interviewed: 0 };
      map[key].total++;
      if (['返信あり','面談設定','書類選考','一次面接','最終面接','内定'].includes(status)) map[key].replied++;
      if (['面談設定','書類選考','一次面接','最終面接','内定'].includes(status)) map[key].interviewed++;
    });
    return Object.entries(map).sort((a, b) => b[1].total - a[1].total);
  }

  dash.clearContents();
  let row = 1;

  function writeSection(title, headers, entries, keyLabel) {
    dash.getRange(row, 1).setValue(title).setFontWeight('bold').setBackground('#E0E7FF');
    dash.getRange(row, 1, 1, headers.length).setBackground('#E0E7FF').setFontWeight('bold');
    row++;
    dash.getRange(row, 1, 1, headers.length).setValues([headers]).setFontWeight('bold').setBackground('#F5F3FF');
    row++;
    entries.forEach(([key, v]) => {
      const rate = v.total > 0 ? Math.round(v.replied / v.total * 100) + '%' : '-';
      dash.getRange(row, 1, 1, 4).setValues([[key, v.total, v.replied, rate]]);
      row++;
    });
    row++;
  }

  writeSection('📊 ポジション別',  ['ポジション名', '送信数', '返信数', '返信率'], aggregate(5), 5);
  writeSection('👤 担当者別',      ['担当者',       '送信数', '返信数', '返信率'], aggregate(1), 1);
  writeSection('📱 媒体別',        ['媒体',         '送信数', '返信数', '返信率'], aggregate(6), 6);

  // 最終更新日時
  dash.getRange(row, 1).setValue(`最終更新: ${new Date().toLocaleString('ja-JP')}`).setFontColor('#888');

  Logger.log('効果測定ダッシュボード更新完了');
}

// ── sendWeeklyReport: 毎週月曜朝にSlack送信 ─────────────────
function sendWeeklyReport() {
  const ss   = SpreadsheetApp.getActiveSpreadsheet();
  const db   = ss.getSheetByName(SHEET_DB);
  if (!db) return;

  const rows = db.getDataRange().getValues().slice(1).filter(r => r[0]);
  const now  = new Date();
  const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

  // 今週分のデータ
  const weekData = rows.filter(r => new Date(r[0]) >= weekAgo);
  if (weekData.length === 0) {
    postToSlack('今週のスカウト送信はありませんでした。');
    return;
  }

  // 担当者別集計
  const byRecruiter = {};
  weekData.forEach(r => {
    const name = r[1] || '不明';
    if (!byRecruiter[name]) byRecruiter[name] = { total: 0, replied: 0 };
    byRecruiter[name].total++;
    if (['返信あり','面談設定','書類選考','一次面接','最終面接','内定'].includes(r[7])) {
      byRecruiter[name].replied++;
    }
  });

  // ポジション別トップ5
  const byPosition = {};
  weekData.forEach(r => {
    const pos = r[5] || '不明';
    byPosition[pos] = (byPosition[pos] || 0) + 1;
  });
  const topPositions = Object.entries(byPosition)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  // 全体返信率（累計）
  const totalReplied = rows.filter(r => ['返信あり','面談設定','書類選考','一次面接','最終面接','内定'].includes(r[7])).length;
  const replyRate = rows.length > 0 ? Math.round(totalReplied / rows.length * 100) : 0;

  // 面談中・選考中
  const inProgress = rows.filter(r => ['面談設定','書類選考','一次面接','最終面接'].includes(r[7])).length;

  // メッセージ組み立て
  const recruiterLines = Object.entries(byRecruiter)
    .sort((a, b) => b[1].total - a[1].total)
    .map(([name, v]) => `　• ${name}：${v.total}件${v.replied > 0 ? `（返信${v.replied}件）` : ''}`)
    .join('\n');

  const positionLines = topPositions
    .map(([pos, count]) => `　• ${pos}：${count}件`)
    .join('\n');

  const message = [
    `📊 *週次スカウトレポート* (${weekAgo.toLocaleDateString('ja-JP')} 〜 ${now.toLocaleDateString('ja-JP')})`,
    '',
    `*今週の送信数：${weekData.length}件*`,
    '',
    `*担当者別*`,
    recruiterLines,
    '',
    `*送信ポジション TOP5*`,
    positionLines,
    '',
    `*累計ステータス*`,
    `　• 累計送信：${rows.length}件`,
    `　• 返信率：${replyRate}%（${totalReplied}件）`,
    `　• 面談・選考中：${inProgress}件`,
  ].join('\n');

  postToSlack(message);
  updateDashboard();
}

function postToSlack(text) {
  if (!SLACK_WEBHOOK_URL || SLACK_WEBHOOK_URL === 'YOUR_SLACK_WEBHOOK_URL') {
    Logger.log('Slack Webhook URLが未設定です: ' + text);
    return;
  }
  UrlFetchApp.fetch(SLACK_WEBHOOK_URL, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify({ text, channel: SLACK_CHANNEL }),
  });
}

// ── setWeeklyTrigger: 週次トリガーを設定（一度だけ手動実行） ─
function setWeeklyTrigger() {
  // 既存トリガーを削除
  ScriptApp.getProjectTriggers().forEach(t => {
    if (t.getHandlerFunction() === 'sendWeeklyReport') ScriptApp.deleteTrigger(t);
  });
  // 毎週月曜 09:00 に設定
  ScriptApp.newTrigger('sendWeeklyReport')
    .timeBased()
    .onWeekDay(ScriptApp.WeekDay.MONDAY)
    .atHour(9)
    .create();
  Logger.log('週次トリガーを設定しました（毎週月曜9時）');
}
