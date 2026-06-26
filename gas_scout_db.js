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

// 産業分類（F列・全73種）
const GICS_INDUSTRIES = [
  'エネルギー設備・サービス', '石油・ガス・消耗燃料',
  '化学', '建設資材', '容器・包装', '金属・鉱業', '紙製品・林産品',
  '建設関連製品', '建設・土木', '電気設備', '機械', '重工業',
  '商社',
  '各種支援サービス', 'セキュリティ・警報装置サービス', '人事・雇用サービス',
  'コンサルティングサービス', '調査',
  '航空貨物・物流サービス', '旅客航空輸送', '海上運輸', '陸上運輸', '運送インフラ',
  '自動車用部品', '自動車',
  '民生用電子機器', '家具・装飾', '住宅建設', '家庭用品・雑貨', 'レジャー用品',
  'アパレル・アクセサリー・贅沢品', '繊維',
  'ホテル・レストラン・レジャー', '教育サービス',
  '販売', '大規模小売り', '専門小売り',
  '飲料', '食品', 'タバコ', '家庭用品・パーソナルケア用品',
  'ヘルスケア機器・用品', 'ヘルスケアプロバイダー', 'バイオテクノロジー',
  '医薬品', 'ライフサイエンス・ツール/サービス',
  '銀行', '信託銀行', '金融サービス', '消費者金融', '資本市場',
  '生命保険・健康保険', '動産保険・損害保険',
  '情報技術サービス', 'SIer', 'ソフトウェア', 'SaaS', 'AI',
  '通信機器', 'コンピュータ・周辺機器', '電子装置・機器・部品',
  '半導体・半導体製造装置', '各種電気通信サービス',
  'メディア', '娯楽',
  'デベロッパー', '不動産',
  '電力', 'ガス',
  '官公庁', '教育機関', 'メガベンチャー', 'その他',
];

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

// ── 手動入力時の送信日時自動入力（onEdit シンプルトリガー） ──────
// 日付シート：年齢列（各メンバーの先頭列）に値を入れたとき
//             送信日時列（年齢列+6）が空なら現在時刻を自動セット
// スカウト管理DB：担当者列(B)に値を入れたとき送信日時列(A)が空なら現在時刻をセット
function onEdit(e) {
  if (!e) return;
  const sheet = e.range.getSheet();
  const name  = sheet.getName();
  const col   = e.range.getColumn();
  const row   = e.range.getRow();
  if (row < 3) return; // ヘッダー・集計行は無視

  // ── 日付シート ──
  if (/\d{4}年\d{1,2}月\d{1,2}日/.test(name)) {
    const ageCols = Object.values(MEMBER_MAP); // [3, 13, 23, 33]
    if (!ageCols.includes(col)) return;
    const val = e.range.getValue();
    if (val === '' || val === null || val === undefined) return; // 年齢を消しても送信日時はそのまま
    const tsCell = sheet.getRange(row, col + 6); // 送信日時は年齢から6列後
    if (tsCell.getValue() === '' || tsCell.getValue() === null || tsCell.getValue() === undefined) {
      tsCell.setValue(new Date()).setNumberFormat('yyyy/MM/dd HH:mm');
    }
    return;
  }

  // ── スカウト管理DB ──
  if (name === SHEET_DB && col === 2) { // B列 = 担当者
    const tsCell = sheet.getRange(row, 1); // A列 = 送信日時
    const val = e.range.getValue();
    if (val !== '' && val !== null && val !== undefined &&
        (tsCell.getValue() === '' || tsCell.getValue() === null || tsCell.getValue() === undefined)) {
      tsCell.setValue(new Date()).setNumberFormat('yyyy/MM/dd HH:mm');
    }
  }
}

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

    // ── フィードバック一覧取得（チーム共有用） ──
    if (data.action === 'getFeedbacks') {
      const fbSheet = ss.getSheetByName(SHEET_FEEDBACK);
      if (!fbSheet) return json({ ok: true, feedbacks: [] });
      const rows = fbSheet.getDataRange().getValues();
      if (rows.length <= 1) return json({ ok: true, feedbacks: [] });
      const limit = Math.min(data.limit || 30, 100);
      const feedbacks = rows.slice(1)
        .reverse()
        .slice(0, limit)
        .map(r => ({
          ts:             r[0] ? new Date(r[0]).getTime() : 0,
          recruiter:      String(r[1] || ''),
          platform:       String(r[2] || ''),
          aiVerdict:      String(r[3] || ''),
          correction:     String(r[4] || ''),
          profileSummary: String(r[5] || ''),
        }))
        .filter(f => f.aiVerdict && f.correction && f.profileSummary);
      return json({ ok: true, feedbacks });
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
  let industry = '';
  try { industry = lookupIndustry(ss, data.company || ''); } catch (_) {}

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
  const sheetNameAlt = sheetName.replace('(', '（').replace(')', '）');
  let sheet = ss.getSheetByName(sheetName) || ss.getSheetByName(sheetNameAlt);
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

  // ポジション名・業界列にドロップダウン設定
  applyPositionDropdown(ss, sheet, nextRow, startCol + 3);
  applyIndustryDropdown(sheet, nextRow, startCol + 5);

  Logger.log('日付シート記録: ' + sheetName + ' / ' + recruiter + ' / 行' + nextRow + ' / ' + (data.position || ''));
}

// ── 業界ドロップダウンを設定（GICS産業リスト・1セル用）──────
function applyIndustryDropdown(sheet, row, col) {
  try {
    const rule = SpreadsheetApp.newDataValidation()
      .requireValueInList(GICS_INDUSTRIES, true)
      .setAllowInvalid(true).build();
    sheet.getRange(row, col).setDataValidation(rule);
  } catch (err) {
    Logger.log('業界ドロップダウン設定エラー: ' + err.message);
  }
}

// 全日付シートの業界列ドロップダウンをGICSに一括更新
// GASエディタから手動で1回実行してください
function updateAllIndustryDropdowns() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const datePattern = /^\d{4}年\d{1,2}月\d{1,2}日[（(][日月火水木金土][）)]$/;
  const rule = SpreadsheetApp.newDataValidation()
    .requireValueInList(GICS_INDUSTRIES, true)
    .setAllowInvalid(true).build();
  let sheetCount = 0;

  ss.getSheets().forEach(sheet => {
    if (!datePattern.test(sheet.getName())) return;
    const lastRow = sheet.getLastRow();
    if (lastRow < 3) return;

    // 列ごとに範囲でまとめて設定（セル個別でなく範囲指定→高速）
    Object.values(MEMBER_MAP).forEach(startCol => {
      const industryCol = startCol + 5;
      const numRows = lastRow - 2; // 3行目〜lastRow
      sheet.getRange(3, industryCol, numRows, 1).setDataValidation(rule);
    });
    sheetCount++;
  });

  // 原本シートにも適用（今後コピーされるシートに引き継がれる）
  const template = ss.getSheetByName(SHEET_TEMPLATE);
  if (template) {
    Object.values(MEMBER_MAP).forEach(startCol => {
      template.getRange(3, startCol + 5, 500, 1).setDataValidation(rule);
    });
  }

  const msg = sheetCount + '枚の日付シートにGICSドロップダウンを設定しました（原本シートも更新済み）';
  Logger.log(msg);
  SpreadsheetApp.getUi().alert(msg);
}

// ── ポジション名ドロップダウンを設定 ─────────────────────────
function applyPositionDropdown(ss, sheet, row, col) {
  try {
    const posSheet = ss.getSheetByName(SHEET_POSITIONS);
    if (!posSheet) return;
    const lastRow = posSheet.getLastRow();
    if (lastRow < 2) return;
    // 範囲参照型（手動設定と同じ形式）で既存ドロップダウンと一致させる
    const sourceRange = posSheet.getRange(2, 1, lastRow - 1, 1);
    const rule = SpreadsheetApp.newDataValidation()
      .requireValueInRange(sourceRange, true)
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

// ── 過去データの業界を一括GICS再分類 ────────────────────────────
// batchClassify を先に完走させてからこの関数を実行してください。
// ClaudeのAPI呼び出しは行わず、マスターシートとキーワードのみで適用します（高速）。
function reclassifyAllIndustries() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const datePattern = /^\d{4}年\d{1,2}月\d{1,2}日[（(][日月火水木金土][）)]$/;
  const norm = s => s.replace(/[　\s]/g, '').toLowerCase();

  // Step 1: マスターシートを読み込む
  let indSheet = ss.getSheetByName(SHEET_INDUSTRY);
  if (!indSheet) {
    indSheet = ss.insertSheet(SHEET_INDUSTRY);
    indSheet.appendRow(['会社名', '業界', '登録方法', '登録日']);
  }
  const masterMap = {};
  indSheet.getDataRange().getValues().slice(1).forEach(r => {
    const name = String(r[0] || '').trim();
    const ind  = String(r[1] || '').trim();
    if (name && GICS_INDUSTRIES.includes(ind)) masterMap[norm(name)] = ind;
  });

  function classify(companyName) {
    if (!companyName) return '';
    const nc = norm(companyName);
    for (const [name, ind] of Object.entries(masterMap)) {
      if (name === nc || nc.includes(name) || name.includes(nc)) return ind;
    }
    return gicsAutoClassify(companyName);
  }

  // Step 2: 全日付シートに適用
  let updated = 0, skipped = 0, unknown = 0;
  const unknownList   = []; // 分類不明（会社名あり・分類できず）
  const oldValList    = []; // 旧分類のまま残っている行（会社名あり・旧値・分類できず）

  ss.getSheets().forEach(sheet => {
    if (!datePattern.test(sheet.getName())) return;
    const lastRow = sheet.getLastRow();
    if (lastRow < 3) return;

    Object.values(MEMBER_MAP).forEach(startCol => {
      const numRows      = lastRow - 2;
      const companyVals  = sheet.getRange(3, startCol + 1, numRows, 1).getValues();
      const industryVals = sheet.getRange(3, startCol + 5, numRows, 1).getValues();

      let changed = false;
      const newVals = industryVals.map((r, i) => {
        const company = String(companyVals[i][0] || '').trim();
        if (!company) { skipped++; return r; }
        const current = String(r[0] || '').trim();
        const newInd = classify(company);
        if (!newInd) {
          unknown++;
          // 会社名ありで分類不能 → ログに記録
          const entry = company + (current ? ' (現在値: ' + current + ')' : ' (現在値: 空白)');
          if (!unknownList.includes(entry)) unknownList.push(entry);
          if (current && !GICS_INDUSTRIES.includes(current)) {
            if (!oldValList.includes(entry)) oldValList.push(entry);
          }
          return r;
        }
        if (newInd === current) { skipped++; return r; }
        updated++;
        changed = true;
        return [newInd];
      });

      if (changed) sheet.getRange(3, startCol + 5, numRows, 1).setValues(newVals);
    });
  });

  let msg = '完了:\n・更新: ' + updated + '件\n・スキップ（既に正しい or 空行）: ' + skipped + '件\n・分類不明（マスタ未登録）: ' + unknown + '件';
  if (unknownList.length > 0) {
    msg += '\n\n【分類不明の会社名】（業界マスタに手動登録してください）:\n' + unknownList.slice(0, 30).join('\n');
    if (unknownList.length > 30) msg += '\n...他' + (unknownList.length - 30) + '社';
  }
  Logger.log(msg);
  SpreadsheetApp.getUi().alert(msg);
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

// ── 業界マスタから業界を取得 ───────────────────────────────────
// 優先順位: ①マスターシート手動登録 → ②キーワード自動分類 → ③Claude API分類
function lookupIndustry(ss, companyName) {
  if (!companyName) return '';

  let indSheet = null;
  try { indSheet = ss.getSheetByName(SHEET_INDUSTRY); } catch (_) {}

  // ① マスターシートを検索
  if (indSheet) {
    try {
      const norm = s => s.replace(/[　\s]/g, '').toLowerCase();
      const normCompany = norm(companyName);
      const rows = indSheet.getDataRange().getValues().slice(1);
      for (const row of rows) {
        const name = norm(String(row[0] || ''));
        if (!name) continue;
        if (name === normCompany || normCompany.includes(name) || name.includes(normCompany)) {
          const industry = String(row[1] || '');
          // GICSリストにある値のみ返す（古い42分類は無視してキーワード/APIで再分類）
          if (GICS_INDUSTRIES.includes(industry)) return industry;
          break;
        }
      }
    } catch (_) {}
  }

  // ② キーワード自動分類
  const kwResult = gicsAutoClassify(companyName);
  if (kwResult) {
    cacheIndustryToSheet(ss, indSheet, companyName, kwResult);
    return kwResult;
  }

  // ③ Claude API で分類（APIキーが設定されている場合のみ）
  const apiKey = PropertiesService.getScriptProperties().getProperty('ANTHROPIC_API_KEY');
  if (!apiKey) {
    Logger.log('[Snow-we] 業界分類スキップ: ANTHROPIC_API_KEY がスクリプトプロパティに未設定 / 会社名: ' + companyName);
    return '';
  }
  const aiResult = classifyIndustryWithClaude(companyName);
  if (aiResult) {
    cacheIndustryToSheet(ss, indSheet, companyName, aiResult);
    return aiResult;
  }

  Logger.log('[Snow-we] 業界分類失敗: Claude APIが空を返した / 会社名: ' + companyName);
  return '';
}

// 分類結果をマスターシートにキャッシュ（次回以降は即返却）
// 既存シートの列構造（会社名・業界・登録方法・登録日）に合わせて追記
function cacheIndustryToSheet(ss, indSheet, companyName, industry) {
  try {
    if (!indSheet) {
      indSheet = ss.insertSheet(SHEET_INDUSTRY);
      indSheet.appendRow(['会社名', '業界', '登録方法', '登録日']);
    }
    const now = new Date();
    indSheet.appendRow([companyName, industry, '自動', now]);
  } catch (_) {}
}

// ── Claude API で GICS産業を自動分類（1社） ──────────────────────
function classifyIndustryWithClaude(companyName) {
  try {
    const apiKey = PropertiesService.getScriptProperties().getProperty('ANTHROPIC_API_KEY');
    if (!apiKey) return '';

    const res = UrlFetchApp.fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
      },
      payload: JSON.stringify({
        model: 'claude-haiku-4-5-20251001',
        max_tokens: 30,
        messages: [{
          role: 'user',
          content: `会社名「${companyName}」をGICS産業分類で分類してください。\n以下のリストから最も適切な産業名を1つだけ返してください（産業名のみ、説明不要）：\n${GICS_INDUSTRIES.join('\n')}`,
        }],
      }),
      muteHttpExceptions: true,
    });

    if (res.getResponseCode() !== 200) return '';
    const text = (JSON.parse(res.getContentText()).content?.[0]?.text || '').trim();
    return GICS_INDUSTRIES.find(i => text.includes(i)) || '';
  } catch (_) {
    return '';
  }
}

// ── 未分類の会社をClaude APIで一括分類（20社ずつバッチ処理） ──────
// 全シートで業界が空または旧分類の会社を収集してClaudeで一括分類し
// マスターシートに保存する。完了後に reclassifyAllIndustries を実行すること。
function claudeBatchClassify() {
  const apiKey = PropertiesService.getScriptProperties().getProperty('ANTHROPIC_API_KEY');
  if (!apiKey) {
    SpreadsheetApp.getUi().alert('ANTHROPIC_API_KEY が設定されていません。\nプロジェクトの設定 → スクリプトプロパティ に追加してください。');
    return;
  }

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const datePattern = /^\d{4}年\d{1,2}月\d{1,2}日[（(][日月火水木金土][）)]$/;

  // 未分類の会社名を収集（重複排除）
  const unclassified = new Set();
  ss.getSheets().forEach(sheet => {
    if (!datePattern.test(sheet.getName())) return;
    const lastRow = sheet.getLastRow();
    if (lastRow < 3) return;

    Object.entries(MEMBER_MAP).forEach(([, startCol]) => {
      const companyCol  = startCol + 1;
      const industryCol = startCol + 5;
      const numRows = lastRow - 2;
      const companyVals  = sheet.getRange(3, companyCol,  numRows, 1).getValues();
      const industryVals = sheet.getRange(3, industryCol, numRows, 1).getValues();
      companyVals.forEach((r, i) => {
        const company  = String(r[0] || '').trim();
        const industry = String(industryVals[i][0] || '').trim();
        if (!company) return;
        if (GICS_INDUSTRIES.includes(industry)) return; // 既に正しく分類済み
        if (gicsAutoClassify(company)) return;          // キーワードで分類可能
        unclassified.add(company);
      });
    });
  });

  if (unclassified.size === 0) {
    SpreadsheetApp.getUi().alert('未分類の会社はありません。');
    return;
  }

  const companies = Array.from(unclassified);
  Logger.log('未分類会社数: ' + companies.length);

  // マスターシートを取得または作成
  let indSheet = ss.getSheetByName(SHEET_INDUSTRY);
  if (!indSheet) {
    indSheet = ss.insertSheet(SHEET_INDUSTRY);
    indSheet.appendRow(['会社名', '業界', '登録方法', '登録日']);
  }

  // 20社ずつバッチでClaude APIに送る
  const BATCH_SIZE = 20;
  let classified = 0;

  for (let i = 0; i < companies.length; i += BATCH_SIZE) {
    const batch = companies.slice(i, i + BATCH_SIZE);

    try {
      const prompt = '以下の会社名をそれぞれGICS産業分類で分類してください。\n' +
        '各会社について、下記リストから最も適切な産業名を1つ選んでください。\n\n' +
        '【産業リスト】\n' + GICS_INDUSTRIES.join('\n') + '\n\n' +
        '【会社リスト】\n' + batch.map((c, j) => (j+1) + '. ' + c).join('\n') + '\n\n' +
        '【回答形式】番号と産業名のみ、各行に1件：\n1. 産業名\n2. 産業名\n...';

      const res = UrlFetchApp.fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': apiKey,
          'anthropic-version': '2023-06-01',
        },
        payload: JSON.stringify({
          model: 'claude-haiku-4-5-20251001',
          max_tokens: 600,
          messages: [{ role: 'user', content: prompt }],
        }),
        muteHttpExceptions: true,
      });

      if (res.getResponseCode() === 200) {
        const text = (JSON.parse(res.getContentText()).content?.[0]?.text || '');
        const lines = text.trim().split('\n');
        batch.forEach((company, j) => {
          const line = lines[j] || '';
          const industry = GICS_INDUSTRIES.find(ind => line.includes(ind)) || '';
          if (industry) {
            indSheet.appendRow([company, industry, 'Claude一括', new Date()]);
            classified++;
            Logger.log(company + ' → ' + industry);
          }
        });
      }
    } catch (_) {}

    if (i + BATCH_SIZE < companies.length) Utilities.sleep(500);
  }

  const msg = companies.length + '社中 ' + classified + '社を分類しマスターに保存しました。\n次に reclassifyAllIndustries を実行してください。';
  Logger.log(msg);
  SpreadsheetApp.getUi().alert(msg);
}

// ── 産業キーワード自動分類 ───────────────────────────
function gicsAutoClassify(companyName) {
  if (!companyName) return '';
  const n = companyName.replace(/[株式会社　\s]/g, '').toLowerCase();

  // コンサルティング・専門サービス
  if (/accenture|アクセンチュア/.test(n))                                  return 'コンサルティングサービス';
  if (/マッキンゼー|mckinsey|ボストンコンサル|bcg|roland berger|ローランドベルガー|bain|ベイン/.test(n)) return 'コンサルティングサービス';
  if (/デロイト|deloitte|pwc|kpmg|ey |アーンスト/.test(n))                 return 'コンサルティングサービス';
  if (/ベイカレント|baycurrent/.test(n))                                    return 'コンサルティングサービス';

  // SIer（システムインテグレーター）
  if (/ntt(データ|data|コミュニケーションズ|communications)/.test(n))       return 'SIer';
  if (/野村総研|nri/.test(n))                                               return 'SIer';
  if (/伊藤忠テクノ|ctc/.test(n))                                           return 'SIer';
  if (/scsk/.test(n))                                                        return 'SIer';
  if (/インフォシス|infosys|tcs|wipro/.test(n))                             return 'SIer';

  // 情報技術サービス
  if (/富士通|fujitsu/.test(n))                                             return '情報技術サービス';
  if (/日立|hitachi/.test(n))                                               return '情報技術サービス';
  if (/nec|日本電気/.test(n))                                               return '情報技術サービス';
  if (/ibm|日本ibm/.test(n))                                                return '情報技術サービス';

  // SaaS
  if (/salesforce|セールスフォース/.test(n))                                return 'SaaS';
  if (/freee/.test(n))                                                       return 'SaaS';
  if (/smarthr/.test(n))                                                     return 'SaaS';
  if (/microsoft|マイクロソフト/.test(n))                                   return 'ソフトウェア';
  if (/oracle|オラクル/.test(n))                                            return 'ソフトウェア';
  if (/sap/.test(n))                                                         return 'ソフトウェア';

  // AI
  if (/google|グーグル|alphabet/.test(n))                                   return 'AI';

  // メガベンチャー
  if (/amazon|アマゾン|aws/.test(n) && !/モバイル/.test(n))                return 'メガベンチャー';
  if (/楽天|rakuten/.test(n) && !/モバイル|銀行/.test(n))                  return 'メガベンチャー';
  if (/メルカリ|mercari/.test(n))                                           return 'メガベンチャー';
  if (/サイバーエージェント|cyberagent/.test(n))                            return 'メガベンチャー';

  // 通信
  if (/softbank|ソフトバンク/.test(n) && !/銀行/.test(n))                  return '各種電気通信サービス';
  if (/kddi|au/.test(n))                                                     return '各種電気通信サービス';
  if (/docomo|ドコモ/.test(n))                                              return '各種電気通信サービス';
  if (/楽天モバイル|rakutenmobile/.test(n))                                 return '各種電気通信サービス';
  if (/ntt(東日本|西日本|^$)/.test(n) || n === 'ntt')                       return '各種電気通信サービス';

  // 金融・銀行
  if (/信託銀行|三菱uf.+信託|三井住友信託|みずほ信託/.test(n))             return '信託銀行';
  if (/三菱uf|mufg|三菱東京/.test(n))                                       return '銀行';
  if (/みずほ|mizuho/.test(n) && !/証券/.test(n))                          return '銀行';
  if (/三井住友|smbc/.test(n) && !/証券|日興/.test(n))                     return '銀行';
  if (/りそな|resona/.test(n))                                              return '銀行';
  if (/(銀行|bank)/.test(n) && !/信託/.test(n))                            return '銀行';
  if (/野村証券|大和証券|みずほ証券|三菱uf.+証券|smbc日興|証券/.test(n))   return '資本市場';
  if (/日本生命|第一生命|住友生命|明治安田|生命保険/.test(n))              return '生命保険・健康保険';
  if (/東京海上|損保ジャパン|三井住友海上|あいおい|損保|火災/.test(n))     return '動産保険・損害保険';
  if (/オリックス|orix/.test(n))                                            return '金融サービス';

  // 不動産・デベロッパー
  if (/三井不動産|三菱地所|住友不動産|野村不動産/.test(n))                 return 'デベロッパー';
  if (/積水ハウス|大和ハウス|旭化成ホームズ|住宅/.test(n))                 return '住宅建設';
  if (/(不動産)/.test(n))                                                   return '不動産';

  // 製造・自動車
  if (/toyota|トヨタ/.test(n))                                             return '自動車';
  if (/honda|ホンダ|本田技/.test(n))                                       return '自動車';
  if (/nissan|日産/.test(n))                                                return '自動車';
  if (/mazda|マツダ/.test(n))                                               return '自動車';
  if (/subaru|スバル/.test(n))                                              return '自動車';
  if (/suzuki|スズキ/.test(n))                                              return '自動車';
  if (/mitsubishi motors|三菱自動車/.test(n))                               return '自動車';
  if (/デンソー|denso|アイシン|aisin|豊田自動/.test(n))                     return '自動車用部品';
  if (/ブリヂストン|bridgestone|住友ゴム/.test(n))                          return '自動車用部品';

  // 重工業
  if (/川崎重工|三菱重工|ihiエアロ|ihi|石川島/.test(n))                    return '重工業';

  // 半導体・電子
  if (/キーエンス|keyence/.test(n))                                         return '電子装置・機器・部品';
  if (/ソニー|sony/.test(n))                                                return '民生用電子機器';
  if (/パナソニック|panasonic/.test(n))                                     return '民生用電子機器';
  if (/東京エレク|tel|applied materials|レーザーテック/.test(n))            return '半導体・半導体製造装置';
  if (/ルネサス|renesas|ローム|rohm|東芝デバイス/.test(n))                  return '半導体・半導体製造装置';
  if (/(半導体|semiconductor)/.test(n))                                      return '半導体・半導体製造装置';

  // 医薬品・ヘルスケア
  if (/武田薬品|takeda|アステラス|astellas|第一三共|大塚製薬|中外製薬|エーザイ|eisai/.test(n)) return '医薬品';
  if (/医薬品|製薬|pharma/.test(n))                                         return '医薬品';
  if (/オリンパス|olympus|テルモ|terumo|シスメックス/.test(n))              return 'ヘルスケア機器・用品';
  if (/病院|クリニック|メディカル|medical|healthcare/.test(n))              return 'ヘルスケアプロバイダー';

  // 人材・採用
  if (/リクルート|recruit/.test(n) && !/不動産|住宅/.test(n))              return '人事・雇用サービス';
  if (/パーソル|persol|マンパワー|manpower/.test(n))                        return '人事・雇用サービス';

  // セキュリティ
  if (/セコム|secom|アルソック|alsok/.test(n))                              return 'セキュリティ・警報装置サービス';

  // 小売
  if (/セブン.?イレブン|ローソン|ファミリーマート|コンビニ/.test(n))       return '大規模小売り';
  if (/イオン|ウォルマート|walmart|ドンキ|ユニー/.test(n))                  return '大規模小売り';
  if (/ユニクロ|uniqlo|ファーストリテ|zara|h&m/.test(n))                   return '専門小売り';
  if (/ニトリ|nitori/.test(n))                                              return '家具・装飾';

  // 消費財
  if (/花王|kao|資生堂|shiseido|p&g/.test(n))                              return '家庭用品・パーソナルケア用品';
  if (/味の素|ajinomoto|キリン|kirin|アサヒ|asahi|サントリー|suntory|サッポロ/.test(n)) return '飲料';
  if (/日清食品|明治|森永|カルビー|ネスレ|nestle/.test(n))                  return '食品';

  // メディア・エンタメ
  if (/電通|dentsu|博報堂|hakuhodo/.test(n))                                return 'メディア';
  if (/(テレビ|tv|放送|フジ|ntv|tbs|abc)/.test(n))                          return 'メディア';
  if (/任天堂|nintendo|コナミ|konami|netflix|ネットフリックス/.test(n))      return '娯楽';

  // 商社
  if (/三菱商事|三井物産|住友商事|伊藤忠|丸紅|双日|豊田通商|商事|物産/.test(n)) return '商社';

  // 建設・土木
  if (/鹿島|清水建設|大成建設|竹中工務|大林組|建設/.test(n))               return '建設・土木';

  // 物流・運輸
  if (/ヤマト|yamato|佐川|sagawa|日本郵便|jppost/.test(n))                  return '航空貨物・物流サービス';
  if (/jal|ana|日本航空|全日空|航空/.test(n))                               return '旅客航空輸送';
  if (/jr|東海道新幹線|鉄道|railway/.test(n))                               return '陸上運輸';
  if (/商船三井|日本郵船|川崎汽船|海運/.test(n))                            return '海上運輸';

  // エネルギー・化学
  if (/jxtg|eneos|出光|idemitsu|コスモ石油/.test(n))                        return '石油・ガス・消耗燃料';
  if (/東電|東京電力|関西電力|中部電力|九州電力|電力/.test(n))              return '電力';
  if (/旭化成|住友化学|三菱化学|東レ|toray|化学/.test(n))                   return '化学';

  // 官公庁・教育機関
  if (/省|庁|役所|官公庁|市役所|区役所|町役場/.test(n))                    return '官公庁';
  if (/大学|高校|専門学校|学校法人/.test(n))                               return '教育機関';

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
    '　• 返信率：'+(rows.length>0?Math.round(totalReplied/rows.length*100):0)+'%（'+totalReplied+'件）',
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

// ── 業界マスタの古い分類をGICSに書き換える（reclassifyAllIndustriesの前に実行）──
function reclassifyMaster() {
  const ss    = SpreadsheetApp.getActiveSpreadsheet();
  const props = PropertiesService.getScriptProperties();
  const apiKey = props.getProperty('ANTHROPIC_API_KEY');

  const indSheet = ss.getSheetByName(SHEET_INDUSTRY);
  if (!indSheet) { SpreadsheetApp.getUi().alert('業界マスタシートが見つかりません'); return; }

  const rows = indSheet.getDataRange().getValues().slice(1); // ヘッダー除く

  // 非GICS（古い分類 or 空白）の行を特定
  const toFix = [];
  rows.forEach((row, i) => {
    const name = String(row[0] || '').trim();
    const ind  = String(row[1] || '').trim();
    if (!name) return;
    if (!ind || !GICS_INDUSTRIES.includes(ind)) {
      toFix.push({ sheetRow: i + 2, name, ind }); // sheetRow: 1-indexed（ヘッダー+1）
    }
  });

  if (toFix.length === 0) {
    SpreadsheetApp.getUi().alert('業界マスタはすべてGICS分類済みです');
    return;
  }

  SpreadsheetApp.getUi().alert('非GICS行が ' + toFix.length + ' 件見つかりました。再分類を開始します（キーワード→Claude API）');

  // Step1: キーワード分類
  let kwUpdated = 0;
  const needsApi = [];
  toFix.forEach(item => {
    const kw = gicsAutoClassify(item.name);
    if (kw) {
      indSheet.getRange(item.sheetRow, 2).setValue(kw);
      indSheet.getRange(item.sheetRow, 3).setValue('キーワード再分類');
      kwUpdated++;
    } else {
      needsApi.push(item);
    }
  });

  // Step2: Claude APIで残りを分類
  let apiUpdated = 0;
  if (apiKey && needsApi.length > 0) {
    const BATCH = 20;
    for (let i = 0; i < needsApi.length; i += BATCH) {
      const batch = needsApi.slice(i, i + BATCH);
      try {
        const prompt = '以下の会社名をGICS産業分類してください。下記リストから1つ選んでください。\n\n【産業リスト】\n' +
          GICS_INDUSTRIES.join('\n') + '\n\n【会社リスト】\n' +
          batch.map((c, j) => (j+1)+'. '+c.name).join('\n') +
          '\n\n【回答形式】番号と産業名のみ：\n1. 産業名\n2. 産業名\n...';
        const res = UrlFetchApp.fetch('https://api.anthropic.com/v1/messages', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'x-api-key': apiKey, 'anthropic-version': '2023-06-01' },
          payload: JSON.stringify({ model: 'claude-haiku-4-5-20251001', max_tokens: 600,
            messages: [{ role: 'user', content: prompt }] }),
          muteHttpExceptions: true,
        });
        if (res.getResponseCode() === 200) {
          const lines = (JSON.parse(res.getContentText()).content?.[0]?.text || '').trim().split('\n');
          batch.forEach((item, j) => {
            const ind = GICS_INDUSTRIES.find(x => (lines[j]||'').includes(x)) || '';
            if (ind) {
              indSheet.getRange(item.sheetRow, 2).setValue(ind);
              indSheet.getRange(item.sheetRow, 3).setValue('Claude再分類');
              apiUpdated++;
            }
          });
        }
      } catch(e) { Logger.log('API error: ' + e.message); }
      if (i + BATCH < needsApi.length) Utilities.sleep(300);
    }
  }

  const remaining = toFix.length - kwUpdated - apiUpdated;
  let msg = '業界マスタ再分類完了:\n・キーワード更新: ' + kwUpdated + '件\n・Claude更新: ' + apiUpdated + '件\n・未分類: ' + remaining + '件';
  if (remaining > 0) msg += '\n\n未分類の会社は手動で業界マスタに追加してください。';
  msg += '\n\n次に reclassifyAllIndustries を実行してください。';
  Logger.log(msg);
  SpreadsheetApp.getUi().alert(msg);
}

// ── 未分類会社を25シートずつ処理（何度でも実行可・途中再開対応）──
function batchClassify() {
  const ss    = SpreadsheetApp.getActiveSpreadsheet();
  const props = PropertiesService.getScriptProperties();
  const apiKey = props.getProperty('ANTHROPIC_API_KEY');
  if (!apiKey) { SpreadsheetApp.getUi().alert('ANTHROPIC_API_KEY が未設定です。'); return; }

  const datePattern = /^\d{4}年\d{1,2}月\d{1,2}日[（(][日月火水木金土][）)]$/;
  const allSheetNames = ss.getSheets().map(s => s.getName()).filter(n => datePattern.test(n));
  const doneSheets    = new Set(JSON.parse(props.getProperty('BATCH_DONE_SHEETS') || '[]'));
  const pendingSheets = allSheetNames.filter(n => !doneSheets.has(n));

  if (pendingSheets.length === 0) {
    props.deleteProperty('BATCH_DONE_SHEETS');
    SpreadsheetApp.getUi().alert('全シート処理完了！\n次に reclassifyAllIndustries を実行してください。');
    return;
  }

  const thisRound = pendingSheets.slice(0, 25);

  let indSheet = ss.getSheetByName(SHEET_INDUSTRY);
  if (!indSheet) {
    indSheet = ss.insertSheet(SHEET_INDUSTRY);
    indSheet.appendRow(['会社名', '業界', '登録方法', '登録日']);
  }
  const existingMap = {};
  indSheet.getDataRange().getValues().slice(1).forEach(r => {
    const name = String(r[0] || '').trim();
    const ind  = String(r[1] || '').trim();
    if (name) existingMap[name] = ind;
  });

  const maxCol = Math.max(...Object.values(MEMBER_MAP).map(s => s + 5));
  const unclassified = new Set();
  thisRound.forEach(sheetName => {
    const sheet = ss.getSheetByName(sheetName);
    if (!sheet) return;
    const lastRow = sheet.getLastRow();
    if (lastRow < 3) return;
    const data = sheet.getRange(3, 1, lastRow - 2, maxCol).getValues();
    Object.values(MEMBER_MAP).forEach(startCol => {
      data.forEach(row => {
        const company = String(row[startCol] || '').trim();
        if (!company || /^\d+$/.test(company)) return;
        if (existingMap[company] && GICS_INDUSTRIES.includes(existingMap[company])) return;
        if (gicsAutoClassify(company)) return;
        unclassified.add(company);
      });
    });
  });

  const companies = Array.from(unclassified);
  const BATCH = 20;
  let classified = 0;
  const newRows = [];
  for (let i = 0; i < companies.length; i += BATCH) {
    const batch = companies.slice(i, i + BATCH);
    try {
      const prompt = '以下の会社名をGICS産業分類してください。下記リストから1つ選んでください。\n\n【産業リスト】\n' +
        GICS_INDUSTRIES.join('\n') + '\n\n【会社リスト】\n' +
        batch.map((c, j) => (j+1)+'. '+c).join('\n') +
        '\n\n【回答形式】番号と産業名のみ：\n1. 産業名\n2. 産業名\n...';
      const res = UrlFetchApp.fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-api-key': apiKey, 'anthropic-version': '2023-06-01' },
        payload: JSON.stringify({ model: 'claude-haiku-4-5-20251001', max_tokens: 600,
          messages: [{ role: 'user', content: prompt }] }),
        muteHttpExceptions: true,
      });
      if (res.getResponseCode() === 200) {
        const lines = (JSON.parse(res.getContentText()).content?.[0]?.text || '').trim().split('\n');
        batch.forEach((company, j) => {
          const ind = GICS_INDUSTRIES.find(x => (lines[j]||'').includes(x)) || '';
          if (ind) { newRows.push([company, ind, 'Claude一括', new Date()]); classified++; }
        });
      }
    } catch(_) {}
    if (i + BATCH < companies.length) Utilities.sleep(300);
  }

  if (newRows.length > 0) {
    indSheet.getRange(indSheet.getLastRow()+1, 1, newRows.length, 4).setValues(newRows);
  }

  thisRound.forEach(n => doneSheets.add(n));
  props.setProperty('BATCH_DONE_SHEETS', JSON.stringify(Array.from(doneSheets)));

  const remaining = pendingSheets.length - thisRound.length;
  SpreadsheetApp.getUi().alert(
    '【' + thisRound.length + 'シート処理完了】\n' +
    '今回: ' + companies.length + '社収集 → ' + classified + '社分類\n\n' +
    (remaining > 0
      ? 'あと ' + remaining + 'シート残っています。\nもう一度 batchClassify を実行してください。'
      : '全シート完了！\n次に reclassifyAllIndustries を実行してください。'));
}

// ── 送信日時の表示形式を「yyyy/MM/dd HH:mm」に統一（一度だけ実行）──
function fixTimestampFormat() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const datePattern = /^\d{4}年\d{1,2}月\d{1,2}日[（(][日月火水木金土][）)]$/;
  const fmt = 'yyyy/MM/dd HH:mm';
  let count = 0;

  ss.getSheets().forEach(sheet => {
    if (!datePattern.test(sheet.getName())) return;
    const lastRow = sheet.getLastRow();
    if (lastRow < 3) return;
    Object.values(MEMBER_MAP).forEach(startCol => {
      sheet.getRange(3, startCol + 6, lastRow - 2, 1).setNumberFormat(fmt);
    });
    count++;
  });

  const tmpl = ss.getSheetByName(SHEET_TEMPLATE);
  if (tmpl) {
    Object.values(MEMBER_MAP).forEach(startCol => {
      tmpl.getRange(3, startCol + 6, 500, 1).setNumberFormat(fmt);
    });
  }
  SpreadsheetApp.getUi().alert(count + '枚のシートに日時フォーマットを適用しました。');
}

// ── 会社名入力時に業界を自動入力するトリガー設定（一度だけ実行）──
function setupOnEditTrigger() {
  ScriptApp.getProjectTriggers().forEach(t => {
    if (t.getHandlerFunction() === 'onEditIndustry') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('onEditIndustry')
    .forSpreadsheet(SpreadsheetApp.getActiveSpreadsheet())
    .onEdit()
    .create();
  SpreadsheetApp.getUi().alert('設定完了。会社名を入力すると業界が自動入力されます。');
}

function onEditIndustry(e) {
  try {
    const sheet = e.range.getSheet();
    const datePattern = /^\d{4}年\d{1,2}月\d{1,2}日[（(][日月火水木金土][）)]$/;
    if (!datePattern.test(sheet.getName())) return;
    const col = e.range.getColumn();
    const row = e.range.getRow();
    if (row < 3) return;
    const colMap = {};
    Object.values(MEMBER_MAP).forEach(startCol => { colMap[startCol + 1] = startCol + 5; });
    const industryCol = colMap[col];
    if (!industryCol) return;
    const companyName = String(e.range.getValue() || '').trim();
    if (!companyName) return;
    const current = String(sheet.getRange(row, industryCol).getValue() || '').trim();
    if (GICS_INDUSTRIES.includes(current)) return;
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const industry = lookupIndustry(ss, companyName);
    if (industry) {
      sheet.getRange(row, industryCol).setValue(industry);
      applyIndustryDropdown(sheet, row, industryCol);
    }
  } catch (_) {}
}
