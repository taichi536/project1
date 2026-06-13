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

// GICS産業分類（F列・全65種）
const GICS_INDUSTRIES = [
  'エネルギー設備・サービス','石油・ガス・消耗燃料','化学','建設資材','容器・包装',
  '金属・鉱業','紙製品・林産品','航空宇宙・防衛','建設関連製品','建設・土木',
  '電気設備','コングロマリット','機械','商社・流通業','商業サービス・用品',
  '航空貨物・物流サービス','旅客航空輸送業','海運業','陸運・鉄道','運送インフラ',
  '自動車部品','自動車','家庭用耐久財','レジャー用品','繊維・アパレル・贅沢品',
  'ホテル・レストラン・レジャー','各種消費者サービス','メディア','販売',
  'インターネット販売・カタログ販売','複合小売り','専門小売り','食品・生活必需品小売り',
  '飲料','食品','タバコ','家庭用品','パーソナル用品','ヘルスケア機器・用品',
  'ヘルスケア・プロバイダー/ヘルスケア・サービス','バイオテクノロジー','医薬品',
  '商業銀行','貯蓄・抵当・不動産金融','各種金融サービス','消費者金融','資本市場',
  '保険','不動産','インターネットソフトウェア・サービス','情報技術サービス',
  'ソフトウェア','通信機器','コンピュータ・周辺機器','電子装置・機器','事務用電子機器',
  '半導体・半導体製造装置','各種電気通信サービス','無線通信サービス',
  '電力','ガス','総合公益事業','水道','独立系発電事業者・エネルギー販売業者',
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

  // ポジション名・業界列にドロップダウン設定
  applyPositionDropdown(ss, sheet, nextRow, startCol + 3);
  applyIndustryDropdown(sheet, nextRow, startCol + 5);

  Logger.log('日付シート記録: ' + sheetName + ' / ' + recruiter + ' / 行' + nextRow + ' / ' + (data.position || ''));
}

// ── 業界ドロップダウンを設定（GICS産業リスト）────────────────
function applyIndustryDropdown(sheet, row, col) {
  try {
    const rule = SpreadsheetApp.newDataValidation()
      .requireValueInList(GICS_INDUSTRIES, true)
      .setAllowInvalid(true)
      .build();
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
  let updated = 0;

  ss.getSheets().forEach(sheet => {
    if (!datePattern.test(sheet.getName())) return;
    const lastRow = sheet.getLastRow();
    if (lastRow < 3) return;

    Object.values(MEMBER_MAP).forEach(startCol => {
      const industryCol = startCol + 5;
      for (let row = 3; row <= lastRow; row++) {
        applyIndustryDropdown(sheet, row, industryCol);
        updated++;
      }
    });
  });

  const msg = updated + '件の業界セルにGICSドロップダウンを設定しました';
  Logger.log(msg);
  SpreadsheetApp.getUi().alert(msg);
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

// ── 過去データの業界を一括GICS再分類 ────────────────────────────
// GASエディタから手動で実行してください（メニュー → 関数を選択 → reclassifyAllIndustries）
function reclassifyAllIndustries() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const datePattern = /^\d{4}年\d{1,2}月\d{1,2}日[（(][日月火水木金土][）)]$/;
  let updated = 0, skipped = 0;

  ss.getSheets().forEach(sheet => {
    if (!datePattern.test(sheet.getName())) return;

    const lastRow = sheet.getLastRow();
    if (lastRow < 3) return;

    Object.values(MEMBER_MAP).forEach(startCol => {
      const companyCol  = startCol + 1; // 会社名
      const industryCol = startCol + 5; // 業界

      for (let row = 3; row <= lastRow; row++) {
        const company = String(sheet.getRange(row, companyCol).getValue() || '').trim();
        if (!company) continue;

        const newIndustry = lookupIndustry(ss, company);
        if (!newIndustry) { skipped++; continue; }

        const current = String(sheet.getRange(row, industryCol).getValue() || '').trim();
        if (current === newIndustry) { skipped++; continue; }

        sheet.getRange(row, industryCol).setValue(newIndustry);
        updated++;
        Logger.log(sheet.getName() + ' 行' + row + ': ' + company + ' → ' + newIndustry);
      }
    });
  });

  const msg = '完了: ' + updated + '件を更新、' + skipped + '件はスキップ（分類不明 or 変更なし）';
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
          return String(row[1] || '');
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
  const aiResult = classifyIndustryWithClaude(companyName);
  if (aiResult) {
    cacheIndustryToSheet(ss, indSheet, companyName, aiResult);
    return aiResult;
  }

  return '';
}

// 分類結果をマスターシートにキャッシュ（次回以降は即返却）
function cacheIndustryToSheet(ss, indSheet, companyName, industry) {
  try {
    if (!indSheet) {
      indSheet = ss.insertSheet(SHEET_INDUSTRY);
      indSheet.appendRow(['会社名', '業界（GICS産業）']);
    }
    indSheet.appendRow([companyName, industry]);
  } catch (_) {}
}

// ── Claude API で GICS産業を自動分類 ─────────────────────────────
// GASのスクリプトプロパティに ANTHROPIC_API_KEY を設定してください
// （GASエディタ → プロジェクトの設定 → スクリプトプロパティ）
function classifyIndustryWithClaude(companyName) {
  try {
    const apiKey = PropertiesService.getScriptProperties().getProperty('ANTHROPIC_API_KEY');
    if (!apiKey) return '';

    const industries = [
      'エネルギー設備・サービス','石油・ガス・消耗燃料','化学','建設資材','容器・包装',
      '金属・鉱業','紙製品・林産品','航空宇宙・防衛','建設関連製品','建設・土木',
      '電気設備','コングロマリット','機械','商社・流通業','商業サービス・用品',
      '航空貨物・物流サービス','旅客航空輸送業','海運業','陸運・鉄道','運送インフラ',
      '自動車部品','自動車','家庭用耐久財','レジャー用品','繊維・アパレル・贅沢品',
      'ホテル・レストラン・レジャー','各種消費者サービス','メディア','販売',
      'インターネット販売・カタログ販売','複合小売り','専門小売り','食品・生活必需品小売り',
      '飲料','食品','タバコ','家庭用品','パーソナル用品','ヘルスケア機器・用品',
      'ヘルスケア・プロバイダー/ヘルスケア・サービス','バイオテクノロジー','医薬品',
      '商業銀行','貯蓄・抵当・不動産金融','各種金融サービス','消費者金融','資本市場',
      '保険','不動産','インターネットソフトウェア・サービス','情報技術サービス',
      'ソフトウェア','通信機器','コンピュータ・周辺機器','電子装置・機器','事務用電子機器',
      '半導体・半導体製造装置','各種電気通信サービス','無線通信サービス',
      '電力','ガス','総合公益事業','水道','独立系発電事業者・エネルギー販売業者',
    ];

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
          content: `会社名「${companyName}」をGICS産業分類で分類してください。\n以下のリストから最も適切な産業名を1つだけ返してください（産業名のみ、説明不要）：\n${industries.join('\n')}`,
        }],
      }),
      muteHttpExceptions: true,
    });

    if (res.getResponseCode() !== 200) return '';
    const text = (JSON.parse(res.getContentText()).content?.[0]?.text || '').trim();
    return industries.find(i => text.includes(i)) || '';
  } catch (_) {
    return '';
  }
}

// ── GICS F列（産業）キーワード自動分類 ───────────────────────────
function gicsAutoClassify(companyName) {
  if (!companyName) return '';
  const n = companyName.replace(/[株式会社　\s]/g, '').toLowerCase();

  // 情報技術・コンサルティング
  if (/accenture|アクセンチュア/.test(n))                    return 'ソフトウェア';
  if (/ベイカレント|baycurrent/.test(n))                      return '情報技術サービス';
  if (/ibm|日本ibm/.test(n))                                  return '情報技術サービス';
  if (/microsoft|マイクロソフト/.test(n))                     return 'ソフトウェア';
  if (/oracle|オラクル/.test(n))                              return 'ソフトウェア';
  if (/sap/.test(n))                                          return 'ソフトウェア';
  if (/salesforce|セールスフォース/.test(n))                  return 'ソフトウェア';
  if (/google|グーグル|alphabet/.test(n))                     return 'インターネットソフトウェア・サービス';
  if (/amazon|アマゾン|aws/.test(n))                          return 'インターネット販売・カタログ販売';
  if (/ntt(データ|data|コミュニケーションズ|communications)/.test(n)) return '情報技術サービス';
  if (/ntt(東日本|西日本|docomo|ドコモ|^$)/.test(n) || n === 'ntt') return '各種電気通信サービス';
  if (/富士通|fujitsu/.test(n))                               return '情報技術サービス';
  if (/日立|hitachi/.test(n))                                 return '情報技術サービス';
  if (/nec|日本電気/.test(n))                                 return '情報技術サービス';
  if (/野村総研|nri/.test(n))                                 return '情報技術サービス';
  if (/伊藤忠テクノ|ctc/.test(n))                             return '情報技術サービス';
  if (/インフォシス|infosys|tcs|wipro/.test(n))               return '情報技術サービス';
  if (/デロイト|deloitte|pwc|kpmg|ey |アーンスト/.test(n))    return '各種商業・専門サービス';
  if (/マッキンゼー|mckinsey|ボストンコンサル|bcg|roland berger|ローランドベルガー|bain|ベイン/.test(n)) return '各種商業・専門サービス';

  // 通信
  if (/softbank|ソフトバンク/.test(n))                        return '無線通信サービス';
  if (/kddi|au/.test(n))                                      return '無線通信サービス';
  if (/docomo|ドコモ/.test(n))                                return '無線通信サービス';
  if (/楽天モバイル|rakutenmobile/.test(n))                   return '無線通信サービス';

  // 金融・銀行
  if (/三菱uf|mufg|三菱東京/.test(n))                        return '商業銀行';
  if (/みずほ|mizuho/.test(n))                                return '商業銀行';
  if (/三井住友|smbc/.test(n))                                return '商業銀行';
  if (/りそな|resona/.test(n))                                return '商業銀行';
  if (/(銀行|bank)/.test(n))                                  return '商業銀行';
  if (/野村証券|大和証券|みずほ証券|三菱uf.+証券|smbc日興|証券/.test(n)) return '資本市場';
  if (/日本生命|第一生命|住友生命|明治安田|生命保険/.test(n)) return '保険';
  if (/東京海上|損保ジャパン|三井住友海上|あいおい|損保|火災/.test(n)) return '保険';
  if (/三井不動産|三菱地所|住友不動産|野村不動産|不動産/.test(n)) return '不動産';
  if (/オリックス|orix/.test(n))                              return '各種金融サービス';

  // 製造・自動車
  if (/toyota|トヨタ/.test(n))                               return '自動車';
  if (/honda|ホンダ|本田技/.test(n))                         return '自動車';
  if (/nissan|日産/.test(n))                                  return '自動車';
  if (/mazda|マツダ/.test(n))                                 return '自動車';
  if (/subaru|スバル/.test(n))                                return '自動車';
  if (/suzuki|スズキ/.test(n))                                return '自動車';
  if (/mitsubishi motors|三菱自動車/.test(n))                 return '自動車';
  if (/デンソー|denso|アイシン|aisin|豊田自動/.test(n))       return '自動車部品';
  if (/ブリヂストン|bridgestone|住友ゴム/.test(n))            return '自動車部品';

  // 半導体・電子
  if (/キーエンス|keyence/.test(n))                           return '電子装置・機器';
  if (/ソニー|sony/.test(n))                                  return '電子装置・機器';
  if (/パナソニック|panasonic/.test(n))                       return '電子装置・機器';
  if (/東京エレク|tel|applied materials|レーザーテック/.test(n)) return '半導体・半導体製造装置';
  if (/ルネサス|renesas|ローム|rohm|東芝デバイス/.test(n))    return '半導体・半導体製造装置';
  if (/(半導体|semiconductor)/.test(n))                        return '半導体・半導体製造装置';

  // 医薬品・ヘルスケア
  if (/武田薬品|takeda|アステラス|astellas|第一三共|大塚製薬|中外製薬|エーザイ|eisai/.test(n)) return '医薬品';
  if (/医薬品|製薬|pharma/.test(n))                           return '医薬品';
  if (/オリンパス|olympus|テルモ|terumo|シスメックス/.test(n)) return 'ヘルスケア機器・用品';
  if (/病院|クリニック|メディカル|medical|healthcare/.test(n)) return 'ヘルスケア・プロバイダー/ヘルスケア・サービス';

  // 小売・消費財
  if (/セブン.?イレブン|ローソン|ファミリーマート|コンビニ/.test(n)) return '食品・生活必需品小売り';
  if (/イオン|ウォルマート|walmart|ドンキ|ユニー/.test(n))     return '複合小売り';
  if (/ユニクロ|uniqlo|ファーストリテ|zara|h&m/.test(n))      return '専門小売り';
  if (/amazon|楽天|rakuten|メルカリ|mercari|yahoo.+ショッピング/.test(n) && !/銀行|モバイル/.test(n)) return 'インターネット販売・カタログ販売';

  // 食品・飲料
  if (/味の素|ajinomoto|キリン|kirin|アサヒ|asahi|サントリー|suntory|サッポロ/.test(n)) return '飲料';
  if (/日清食品|明治|森永|カルビー|味の素|ネスレ|nestle/.test(n)) return '食品';

  // メディア・広告
  if (/電通|dentsu|博報堂|hakuhodo|サイバーエージェント|cyberagent/.test(n)) return 'メディア';
  if (/(テレビ|tv|放送|フジ|ntv|tbs|abc)/.test(n))             return 'メディア';

  // 商社
  if (/三菱商事|三井物産|住友商事|伊藤忠|丸紅|双日|豊田通商|商事|物産/.test(n)) return '商社・流通業';

  // 建設・不動産
  if (/鹿島|清水建設|大成建設|竹中工務|大林組|建設/.test(n))  return '建設・土木';

  // 物流・運輸
  if (/ヤマト|yamato|佐川|sagawa|日本郵便|jppost/.test(n))    return '航空貨物・物流サービス';
  if (/jal|ana|日本航空|全日空|航空/.test(n))                  return '旅客航空輸送業';
  if (/jr|東海道新幹線|鉄道|railway/.test(n))                  return '陸運・鉄道';

  // エネルギー・化学
  if (/jxtg|eneos|出光|idemitsu|コスモ石油/.test(n))          return '石油・ガス・消耗燃料';
  if (/東電|東京電力|関西電力|中部電力|九州電力|電力/.test(n)) return '電力';
  if (/旭化成|住友化学|三菱化学|東レ|toray|化学/.test(n))      return '化学';

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
