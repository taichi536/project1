// ============================================================
// Snow-we スカウト管理 - Google Apps Script
// ============================================================

// ── 設定 ────────────────────────────────────────────────────
const SLACK_WEBHOOK_URL = 'YOUR_SLACK_WEBHOOK_URL'; // ← Slack Incoming Webhook URLを貼る
const SLACK_CHANNEL     = '#scout-report';
const GAS_SECRET        = 'snowwe2024';

const SHEET_DB         = 'スカウト管理DB';
const SHEET_DASHBOARD  = '効果測定';
const SHEET_FEEDBACK   = 'AI判定フィードバック';
const SHEET_POSITIONS  = 'ポジション';
const SHEET_CONDITIONS = 'コンサル別条件';
const SHEET_TEMPLATE   = '原本';
const SHEET_INDUSTRY   = '🏭 業界マスタ';

const STATUS_LIST = ['未返信', '返信あり', '面談設定', '書類選考', '一次面接', '最終面接', '内定', '辞退', '見送り'];

const MEDIA_LABEL = {
  rds: 'RDS', bizreach: 'ビズリーチ', dodax: 'doda X',
  ambi: 'AMBI', green: 'Green', mynavi: 'マイナビ'
};

// メンバーと年齢列の対応（各セクション7列: 年齢・会社名・大学・ポジション名・媒体・業界・送信日時）
// ★ メンバーが増えた場合はここに追加する
const MEMBER_MAP = {
  'たけと':      3,   // C=年齢, D=会社名, E=大学, F=ポジション名, G=媒体, H=業界, I=送信日時
  'ゆうき':     13,   // M=年齢, N=会社名, O=大学, P=ポジション名, Q=媒体, R=業界, S=送信日時
  'たいち':     23,   // W=年齢, X=会社名, Y=大学, Z=ポジション名, AA=媒体, AB=業界, AC=送信日時
  'れいしろう': 33,   // AG=年齢, AH=会社名, AI=大学, AJ=ポジション名, AK=媒体, AL=業界, AM=送信日時
};

// ── doPost ──────────────────────────────────────────────────
function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    if (data.secret !== GAS_SECRET) {
      return json({ ok: false, error: 'unauthorized' });
    }

    const ss = SpreadsheetApp.getActiveSpreadsheet();

    // ── フィードバック保存 ──
    if (data.action === 'saveFeedback') {
      let fbSheet = ss.getSheetByName(SHEET_FEEDBACK);
      if (!fbSheet) {
        fbSheet = ss.insertSheet(SHEET_FEEDBACK);
        fbSheet.getRange(1, 1, 1, 6).setValues([['日時', '担当者', '媒体', 'AI判定', '訂正後', '候補者概要']])
          .setBackground('#4338CA').setFontColor('#ffffff').setFontWeight('bold');
        fbSheet.setFrozenRows(1);
      }
      const ts = data.ts ? new Date(data.ts) : new Date();
      fbSheet.appendRow([ts, data.recruiter || '',
        MEDIA_LABEL[data.platform] || data.platform || '',
        data.aiVerdict || '', data.correction || '', data.profileSummary || '']);
      return json({ ok: true });
    }

    // ── ポジション要件取得 ──
    if (data.action === 'getPositionRequirements') {
      const posSheet  = ss.getSheetByName(SHEET_POSITIONS);
      const condSheet = ss.getSheetByName(SHEET_CONDITIONS);
      const posName   = data.position || '';
      let requirements = '', matchedName = '';
      if (posSheet) {
        const rows = posSheet.getDataRange().getValues();
        const normInput = normPos(posName);
        for (let i = 1; i < rows.length; i++) {
          if (!rows[i][0]) continue;
          if (normPos(String(rows[i][0])) === normInput) {
            requirements = String(rows[i][1] || '').substring(0, 2000);
            matchedName  = String(rows[i][0]);
            break;
          }
        }
      }
      let companyCriteria = '';
      if (condSheet && matchedName) {
        const company = detectCompany(matchedName);
        if (company) companyCriteria = getCompanyCriteria(condSheet, company);
      }
      return json({ ok: true, requirements, companyCriteria });
    }

    // ── ポジション一覧取得 ──
    if (data.action === 'getPositions') {
      const posSheet = ss.getSheetByName(SHEET_POSITIONS);
      if (!posSheet) return json({ ok: false });
      const positions = posSheet.getDataRange().getValues().slice(1)
        .filter(r => r[0])
        .map(r => ({ name: String(r[0]), description: String(r[1] || '').substring(0, 500) }));
      return json({ ok: true, positions });
    }

    // ── スカウト記録 ──
    recordScout(ss, data);
    return json({ ok: true });

  } catch (err) {
    return json({ ok: false, error: err.message });
  }
}

// ── スカウト記録：日付別シート ＋ スカウト管理DB の両方に書く ──
function recordScout(ss, data) {
  const ts      = data.ts ? new Date(data.ts) : new Date();
  const media   = MEDIA_LABEL[data.media] || data.media || '';
  const ageVal  = parseInt(data.age) || '';
  const industry = lookupIndustry(ss, data.company || '');

  // ── 1. 日付別シートに書く ──
  writeToDailySheet(ss, data, ts, media, ageVal, industry);

  // ── 2. スカウト管理DBにも書く（集計・Slackレポート用） ──
  let dbSheet = ss.getSheetByName(SHEET_DB);
  if (!dbSheet) {
    dbSheet = ss.insertSheet(SHEET_DB);
    const headers = ['送信日時', '担当者', '年齢', '会社名', '大学', 'ポジション名', '媒体', 'ステータス', '返信日', '面談日', 'メモ'];
    dbSheet.getRange(1, 1, 1, headers.length).setValues([headers])
      .setBackground('#4338CA').setFontColor('#ffffff').setFontWeight('bold');
    dbSheet.setFrozenRows(1);
  }
  dbSheet.appendRow([ts, data.recruiter || '', ageVal, data.company || '',
    data.univ || '', data.position || '', media, '未返信', '', '', '']);
  const lastRow = dbSheet.getLastRow();

  // ステータス列にドロップダウン設定
  const statusRule = SpreadsheetApp.newDataValidation()
    .requireValueInList(STATUS_LIST, true).setAllowInvalid(false).build();
  dbSheet.getRange(lastRow, 8).setDataValidation(statusRule);

  // ポジション名列にドロップダウン設定
  applyPositionDropdown(ss, dbSheet, lastRow, 6);
}

// ── 日付別シートへの書き込み ─────────────────────────────────
function writeToDailySheet(ss, data, ts, media, ageVal, industry) {
  const recruiter = (data.recruiter || '').trim();
  const startCol  = findMemberCol(recruiter);
  if (!startCol) {
    Logger.log('メンバー未登録: "' + recruiter + '" / 登録済み: ' + Object.keys(MEMBER_MAP).join(', '));
    return;
  }

  // 送信時刻に対応する日付シートを取得（なければ原本からコピー）
  const sheetName = getSheetNameForTs(data.ts);
  let sheet = ss.getSheetByName(sheetName);
  if (!sheet) {
    const template = ss.getSheetByName(SHEET_TEMPLATE);
    if (!template) {
      Logger.log('原本シートが見つかりません');
      return;
    }
    sheet = template.copyTo(ss);
    sheet.setName(sheetName);
    ss.moveActiveSheet(1);
  }

  // 次の空行を探す（3行目から）
  const nextRow = findNextRow(sheet, startCol);

  // データを書き込む（年齢・会社名・大学・ポジション名・媒体・業界・送信日時）
  sheet.getRange(nextRow, startCol, 1, 7).setValues([[
    ageVal, data.company || '', data.univ || '',
    data.position || '', media, industry, ts,
  ]]);

  // ポジション名列（startCol+3）にドロップダウン設定
  applyPositionDropdown(ss, sheet, nextRow, startCol + 3);

  Logger.log('日付シート記録: ' + sheetName + ' / ' + recruiter + ' / 行' + nextRow + ' / ' + (data.position || ''));
}

// ── ポジション名ドロップダウンを設定 ─────────────────────────
function applyPositionDropdown(ss, sheet, row, col) {
  try {
    const posSheet = ss.getSheetByName(SHEET_POSITIONS);
    if (!posSheet) return;
    const posNames = posSheet.getDataRange().getValues()
      .slice(1).map(r => String(r[0] || '')).filter(Boolean);
    if (posNames.length === 0) return;
    const rule = SpreadsheetApp.newDataValidation()
      .requireValueInList(posNames, true)
      .setAllowInvalid(true)
      .build();
    sheet.getRange(row, col).setDataValidation(rule);
  } catch (err) {
    Logger.log('ドロップダウン設定エラー: ' + err.message);
  }
}

// ── メンバー名から年齢列を取得（部分一致対応） ───────────────
function findMemberCol(recruiter) {
  if (!recruiter) return null;
  if (MEMBER_MAP[recruiter] !== undefined) return MEMBER_MAP[recruiter];
  for (const [name, col] of Object.entries(MEMBER_MAP)) {
    if (name.includes(recruiter) || recruiter.includes(name)) return col;
  }
  return null;
}

// ── 次の空行を取得（3行目から） ──────────────────────────────
function findNextRow(sheet, startCol) {
  const lastRow = Math.max(sheet.getLastRow(), 2);
  for (let r = 3; r <= lastRow + 1; r++) {
    const val = sheet.getRange(r, startCol).getValue();
    if (val === '' || val === null || val === undefined) return r;
  }
  return lastRow + 1;
}

// ── 日付シート名を取得（送信時刻をJSTに変換して決定） ────────
// data.ts（Unixミリ秒）を使うのでGASのタイムゾーン設定に依存しない
function getSheetNameForTs(tsMs) {
  const date     = new Date(tsMs || Date.now());
  const weekdays = ['日', '月', '火', '水', '木', '金', '土'];
  // Utilities.formatDate で明示的にAsia/Tokyoを指定
  const year   = parseInt(Utilities.formatDate(date, 'Asia/Tokyo', 'yyyy'));
  const month  = parseInt(Utilities.formatDate(date, 'Asia/Tokyo', 'M'));
  const day    = parseInt(Utilities.formatDate(date, 'Asia/Tokyo', 'd'));
  const isoDay = parseInt(Utilities.formatDate(date, 'Asia/Tokyo', 'u')); // 1=月〜7=日
  return year + '年' + month + '月' + day + '日(' + weekdays[isoDay % 7] + ')';
}

// ── 業界マスタから業界を取得 ─────────────────────────────────
function lookupIndustry(ss, companyName) {
  if (!companyName) return '';
  try {
    const indSheet = ss.getSheetByName(SHEET_INDUSTRY);
    if (!indSheet) return '';
    const norm = s => s.replace(/[　\s]/g, '').toLowerCase();
    const normCompany = norm(companyName);
    const rows = indSheet.getDataRange().getValues().slice(1);
    for (const row of rows) {
      const name = norm(String(row[0] || ''));
      if (!name) continue;
      if (name === normCompany || normCompany.includes(name) || name.includes(normCompany)) {
        return String(row[1] || '');
      }
    }
  } catch (_) {}
  return '';
}

// ── ポジション名正規化 ────────────────────────────────────────
function normPos(name) {
  return name.replace(/^[A-Za-z]+[）)]\s*/u, '')
    .replace(/[（]/g, '(').replace(/[）]/g, ')')
    .replace(/　/g, ' ').replace(/\s+/g, ' ')
    .replace(/\s*[-－–—]\s*/g, '-').trim().toLowerCase();
}

function detectCompany(posName) {
  if (/^AC[）)]/.test(posName)) return 'アクセンチュア';
  if (/^BC/.test(posName))      return 'ベイカレント';
  return null;
}

function getCompanyCriteria(condSheet, companyName) {
  const rows = condSheet.getDataRange().getValues();
  let colIdx = -1;
  for (let j = 0; j < rows[0].length; j++) {
    if (rows[0][j] === companyName) { colIdx = j; break; }
  }
  if (colIdx === -1) return '';
  return rows.slice(1).filter(r => r[0] && r[colIdx])
    .map(r => '【' + r[0] + '】\n' + r[colIdx]).join('\n\n').substring(0, 3000);
}

function json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// ── 効果測定ダッシュボード更新 ───────────────────────────────
function updateDashboard() {
  const ss   = SpreadsheetApp.getActiveSpreadsheet();
  const db   = ss.getSheetByName(SHEET_DB);
  const dash = ss.getSheetByName(SHEET_DASHBOARD) || ss.insertSheet(SHEET_DASHBOARD);
  if (!db) return;

  const rows = db.getDataRange().getValues();
  if (rows.length <= 1) return;
  const data = rows.slice(1).filter(r => r[0]);

  function aggregate(keyIdx) {
    const map = {};
    data.forEach(r => {
      const key = r[keyIdx] || '不明';
      const st  = r[7] || '未返信';
      if (!map[key]) map[key] = { total: 0, replied: 0 };
      map[key].total++;
      if (['返信あり','面談設定','書類選考','一次面接','最終面接','内定'].includes(st)) map[key].replied++;
    });
    return Object.entries(map).sort((a, b) => b[1].total - a[1].total);
  }

  dash.clearContents();
  let row = 1;
  function writeSection(title, headers, entries) {
    dash.getRange(row, 1, 1, headers.length).setValues([headers]).setFontWeight('bold').setBackground('#E0E7FF');
    row++;
    entries.forEach(([key, v]) => {
      const rate = v.total > 0 ? Math.round(v.replied / v.total * 100) + '%' : '-';
      dash.getRange(row, 1, 1, 4).setValues([[key, v.total, v.replied, rate]]);
      row++;
    });
    row++;
  }
  writeSection('📊 ポジション別', ['ポジション名','送信数','返信数','返信率'], aggregate(5));
  writeSection('👤 担当者別',     ['担当者',       '送信数','返信数','返信率'], aggregate(1));
  writeSection('📱 媒体別',       ['媒体',         '送信数','返信数','返信率'], aggregate(6));
  dash.getRange(row, 1).setValue('最終更新: ' + new Date().toLocaleString('ja-JP')).setFontColor('#888');
}

// ── 週次Slackレポート ────────────────────────────────────────
function sendWeeklyReport() {
  const ss  = SpreadsheetApp.getActiveSpreadsheet();
  const db  = ss.getSheetByName(SHEET_DB);
  if (!db) return;

  const rows    = db.getDataRange().getValues().slice(1).filter(r => r[0]);
  const now     = new Date();
  const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  const week    = rows.filter(r => new Date(r[0]) >= weekAgo);
  if (week.length === 0) { postToSlack('今週のスカウト送信はありませんでした。'); return; }

  const byRec = {};
  week.forEach(r => {
    const n = r[1] || '不明';
    if (!byRec[n]) byRec[n] = { total: 0, replied: 0 };
    byRec[n].total++;
    if (['返信あり','面談設定','書類選考','一次面接','最終面接','内定'].includes(r[7])) byRec[n].replied++;
  });
  const byPos = {};
  week.forEach(r => { const p = r[5] || '不明'; byPos[p] = (byPos[p] || 0) + 1; });
  const topPos = Object.entries(byPos).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const totalReplied = rows.filter(r => ['返信あり','面談設定','書類選考','一次面接','最終面接','内定'].includes(r[7])).length;

  const msg = [
    '📊 *週次スカウトレポート* (' + weekAgo.toLocaleDateString('ja-JP') + ' 〜 ' + now.toLocaleDateString('ja-JP') + ')',
    '', '*今週の送信数：' + week.length + '件*', '',
    '*担当者別*',
    Object.entries(byRec).sort((a,b)=>b[1].total-a[1].total).map(([n,v])=>'　• '+n+'：'+v.total+'件'+(v.replied>0?'（返信'+v.replied+'件）':'')).join('\n'),
    '', '*送信ポジション TOP5*',
    topPos.map(([p,c])=>'　• '+p+'：'+c+'件').join('\n'),
    '', '*累計*',
    '　• 累計送信：'+rows.length+'件',
    '　• 返信率：'+（rows.length>0?Math.round(totalReplied/rows.length*100):0)+'%（'+totalReplied+'件）',
  ].join('\n');

  postToSlack(msg);
  updateDashboard();
}

function postToSlack(text) {
  if (!SLACK_WEBHOOK_URL || SLACK_WEBHOOK_URL === 'YOUR_SLACK_WEBHOOK_URL') return;
  UrlFetchApp.fetch(SLACK_WEBHOOK_URL, {
    method: 'post', contentType: 'application/json',
    payload: JSON.stringify({ text, channel: SLACK_CHANNEL }),
  });
}

// ── 週次トリガー設定（一度だけ手動実行） ────────────────────
function setWeeklyTrigger() {
  ScriptApp.getProjectTriggers().forEach(t => {
    if (t.getHandlerFunction() === 'sendWeeklyReport') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('sendWeeklyReport')
    .timeBased().onWeekDay(ScriptApp.WeekDay.MONDAY).atHour(9).create();
  Logger.log('週次トリガー設定完了（毎週月曜9時）');
}
