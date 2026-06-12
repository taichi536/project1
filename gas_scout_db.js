// ============================================================
// Snow-we スカウト管理 - Google Apps Script
// ============================================================

// ── 設定 ────────────────────────────────────────────────────
const SLACK_WEBHOOK_URL = 'YOUR_SLACK_WEBHOOK_URL'; // ← Slack Incoming Webhook URLを貼る
const SLACK_CHANNEL     = '#scout-report';
const GAS_SECRET        = 'snowwe2024';

const SHEET_FEEDBACK   = 'AI判定フィードバック';
const SHEET_POSITIONS  = 'ポジション';
const SHEET_CONDITIONS = 'コンサル別条件';
const SHEET_TEMPLATE   = '原本';
const SHEET_INDUSTRY   = '🏭 業界マスタ';

const MEDIA_LABEL = {
  rds: 'RDS', bizreach: 'ビズリーチ', dodax: 'doda X',
  ambi: 'AMBI', green: 'Green', mynavi: 'マイナビ'
};

// メンバーと年齢列（C=3, M=13, W=23, AG=33）の対応
// 各セクション: 年齢・会社名・大学・ポジション名・媒体・業界・送信日時（7列）
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
      return ContentService.createTextOutput(JSON.stringify({ ok: false, error: 'unauthorized' }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    const ss = SpreadsheetApp.getActiveSpreadsheet();

    // ── フィードバック保存 ──
    if (data.action === 'saveFeedback') {
      let fbSheet = ss.getSheetByName(SHEET_FEEDBACK);
      if (!fbSheet) {
        fbSheet = ss.insertSheet(SHEET_FEEDBACK);
        const headers = ['日時', '担当者', '媒体', 'AI判定', '訂正後', '候補者概要'];
        fbSheet.getRange(1, 1, 1, headers.length).setValues([headers])
          .setBackground('#4338CA').setFontColor('#ffffff').setFontWeight('bold');
        fbSheet.setFrozenRows(1);
      }
      const ts = data.ts ? new Date(data.ts) : new Date();
      fbSheet.appendRow([ts, data.recruiter || '', MEDIA_LABEL[data.platform] || data.platform || '',
        data.aiVerdict || '', data.correction || '', data.profileSummary || '']);
      return ContentService.createTextOutput(JSON.stringify({ ok: true }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // ── ポジション要件取得 ──
    if (data.action === 'getPositionRequirements') {
      const posSheet  = ss.getSheetByName(SHEET_POSITIONS);
      const condSheet = ss.getSheetByName(SHEET_CONDITIONS);
      const posName   = data.position || '';
      let requirements = '';
      let matchedSheetName = '';
      if (posSheet) {
        const rows = posSheet.getDataRange().getValues();
        const normInput = normPos(posName);
        for (let i = 1; i < rows.length; i++) {
          if (!rows[i][0]) continue;
          if (normPos(String(rows[i][0])) === normInput) {
            requirements     = String(rows[i][1] || '').substring(0, 2000);
            matchedSheetName = String(rows[i][0]);
            break;
          }
        }
      }
      let companyCriteria = '';
      if (condSheet && matchedSheetName) {
        const company = detectCompany(matchedSheetName);
        if (company) companyCriteria = getCompanyCriteria(condSheet, company);
      }
      return ContentService.createTextOutput(JSON.stringify({ ok: true, requirements, companyCriteria }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // ── ポジション一覧取得 ──
    if (data.action === 'getPositions') {
      const posSheet = ss.getSheetByName(SHEET_POSITIONS);
      if (!posSheet) return ContentService.createTextOutput(JSON.stringify({ ok: false }))
        .setMimeType(ContentService.MimeType.JSON);
      const rows = posSheet.getDataRange().getValues().slice(1);
      const positions = rows.filter(r => r[0]).map(r => ({
        name: String(r[0]),
        description: String(r[1] || '').substring(0, 500)
      }));
      return ContentService.createTextOutput(JSON.stringify({ ok: true, positions }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // ── スカウト記録（日付別シートに書き込み） ──
    writeToDailySheet(ss, data);

    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ ok: false, error: err.message }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

// ── 日付別シートに書き込み ───────────────────────────────────
function writeToDailySheet(ss, data) {
  const recruiter = (data.recruiter || '').trim();
  const startCol  = findMemberCol(recruiter);
  if (!startCol) {
    Logger.log('メンバーが見つかりません: ' + recruiter + ' / 登録済み: ' + Object.keys(MEMBER_MAP).join(', '));
    return;
  }

  // 今日の日付シートを取得（なければ原本からコピー）
  const sheetName = getTodaySheetName();
  let sheet = ss.getSheetByName(sheetName);
  if (!sheet) {
    const template = ss.getSheetByName(SHEET_TEMPLATE);
    if (template) {
      sheet = template.copyTo(ss);
      sheet.setName(sheetName);
      // 先頭に移動
      ss.setActiveSheet(sheet);
      ss.moveActiveSheet(1);
    } else {
      Logger.log('原本シートが見つかりません');
      return;
    }
  }

  // 次の空行を探す（3行目から）
  const nextRow = findNextRow(sheet, startCol);

  // 業界を業界マスタから取得
  const industry = lookupIndustry(ss, data.company || '');

  // データを書き込む
  const ts     = data.ts ? new Date(data.ts) : new Date();
  const media  = MEDIA_LABEL[data.media] || data.media || '';
  const ageVal = parseInt(data.age) || '';

  sheet.getRange(nextRow, startCol, 1, 7).setValues([[
    ageVal,              // 年齢
    data.company  || '', // 会社名
    data.univ     || '', // 大学
    data.position || '', // ポジション名
    media,               // 媒体
    industry,            // 業界
    ts,                  // 送信日時
  ]]);

  // ポジション名列にドロップダウンを設定
  const posSheet = ss.getSheetByName(SHEET_POSITIONS);
  if (posSheet) {
    const posNames = posSheet.getDataRange().getValues()
      .slice(1).map(r => String(r[0] || '')).filter(Boolean);
    if (posNames.length > 0) {
      const posRule = SpreadsheetApp.newDataValidation()
        .requireValueInList(posNames, true)
        .setAllowInvalid(true)
        .build();
      sheet.getRange(nextRow, startCol + 3).setDataValidation(posRule);
    }
  }

  Logger.log('記録完了: ' + sheetName + ' / ' + recruiter + ' / 行' + nextRow + ' / ' + (data.position || ''));
}

// ── メンバー名から年齢列を取得（部分一致対応） ───────────────
function findMemberCol(recruiter) {
  if (!recruiter) return null;
  // 完全一致
  if (MEMBER_MAP[recruiter]) return MEMBER_MAP[recruiter];
  // 部分一致（登録名に入力名が含まれるか、または逆）
  for (const [name, col] of Object.entries(MEMBER_MAP)) {
    if (name.includes(recruiter) || recruiter.includes(name)) return col;
  }
  return null;
}

// ── 次の空行を取得（3行目から下方向へ） ────────────────────
function findNextRow(sheet, startCol) {
  const lastRow = Math.max(sheet.getLastRow(), 2);
  for (let r = 3; r <= lastRow + 1; r++) {
    const val = sheet.getRange(r, startCol).getValue();
    if (val === '' || val === null || val === undefined) return r;
  }
  return lastRow + 1;
}

// ── 今日の日付シート名を生成 ─────────────────────────────────
function getTodaySheetName() {
  const now      = new Date();
  const year     = now.getFullYear();
  const month    = now.getMonth() + 1;
  const day      = now.getDate();
  const weekdays = ['日', '月', '火', '水', '木', '金', '土'];
  const weekday  = weekdays[now.getDay()];
  return year + '年' + month + '月' + day + '日(' + weekday + ')';
}

// ── 業界マスタから業界を取得 ─────────────────────────────────
function lookupIndustry(ss, companyName) {
  if (!companyName) return '';
  const indSheet = ss.getSheetByName(SHEET_INDUSTRY);
  if (!indSheet) return '';
  const rows = indSheet.getDataRange().getValues().slice(1);
  const norm = s => s.replace(/[　\s]/g, '').toLowerCase();
  const normCompany = norm(companyName);
  for (const row of rows) {
    const name = String(row[0] || '');
    if (!name) continue;
    if (norm(name) === normCompany || normCompany.includes(norm(name)) || norm(name).includes(normCompany)) {
      return String(row[1] || '');
    }
  }
  return '';
}

// ── ポジション名正規化 ────────────────────────────────────────
function normPos(name) {
  return name
    .replace(/^[A-Za-z]+[）)]\s*/u, '')
    .replace(/[（]/g, '(').replace(/[）]/g, ')')
    .replace(/　/g, ' ').replace(/\s+/g, ' ')
    .replace(/\s*[-－–—]\s*/g, '-')
    .trim().toLowerCase();
}

// ── ポジション名から会社を判定 ───────────────────────────────
function detectCompany(posName) {
  if (/^AC[）)]/.test(posName)) return 'アクセンチュア';
  if (/^BC/.test(posName))      return 'ベイカレント';
  return null;
}

// ── 会社別条件をテキストで返す ───────────────────────────────
function getCompanyCriteria(condSheet, companyName) {
  const rows = condSheet.getDataRange().getValues();
  const headerRow = rows[0];
  let colIdx = -1;
  for (let j = 0; j < headerRow.length; j++) {
    if (headerRow[j] === companyName) { colIdx = j; break; }
  }
  if (colIdx === -1) return '';
  const lines = [];
  for (let i = 1; i < rows.length; i++) {
    const label = rows[i][0];
    const val   = rows[i][colIdx];
    if (label && val) lines.push('【' + label + '】\n' + val);
  }
  return lines.join('\n\n').substring(0, 3000);
}

// ── Slackへ送信 ──────────────────────────────────────────────
function postToSlack(text) {
  if (!SLACK_WEBHOOK_URL || SLACK_WEBHOOK_URL === 'YOUR_SLACK_WEBHOOK_URL') {
    Logger.log('Slack Webhook URLが未設定: ' + text);
    return;
  }
  UrlFetchApp.fetch(SLACK_WEBHOOK_URL, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify({ text, channel: SLACK_CHANNEL }),
  });
}

// ── setWeeklyTrigger: 週次トリガー設定（一度だけ手動実行） ───
function setWeeklyTrigger() {
  ScriptApp.getProjectTriggers().forEach(t => {
    if (t.getHandlerFunction() === 'sendWeeklyReport') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('sendWeeklyReport')
    .timeBased().onWeekDay(ScriptApp.WeekDay.MONDAY).atHour(9).create();
  Logger.log('週次トリガーを設定しました（毎週月曜9時）');
}
