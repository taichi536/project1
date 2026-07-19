// background.js — GAS中継 & ポジション一覧の管理

// ポジション一覧（ここだけ編集すれば popup・content 両方に反映される）
const POSITION_LIST = [
  'ファンクションコンサルタント(営業/Eコマース)-song',
  'Customerコンサルタント（オープンポジション）- song',
  'Customerストラテジスト(成長戦略コンサルタント)-song',
  '製品・サービス開発DXコンサルタント/アーキテクト - IND',
  'ファンクションコンサルタント（マーケティング）- song',
  'PRコンサルタント - OPE',
  '人材・組織コンサルタント - BUS',
  '製造プロセスDXコンサルタント/ アーキテクト・エンジニア- IND',
  'テクノロジーコンサルタント（製造・流通領域）- TEC',
  '財務・経営管理コンサルタント（CFO＆EV）- BUS',
  'クラウドアーキテクト / エンジニア / コンサルタント – TEC',
  'サプライチェーン＆オペレーションコンサルタント【マネジャー候補】- BUS',
  'Webシステムエンジニア / Webシステムコンサルタント - song',
  'プロダクトマネジャー - song',
  'プロジェクトマネージャー - OPE',
  '社会インフラ・建設・不動産領域コンサルタント/エンジニア - IND',
  'ソリューション・エンジニア - TEC',
  'システムコンサルタント - TEC',
  '購買・調達担当（スペシャリスト）- CORP',
  'テクノロジーセールス（リセールサポート）- TEC',
  'インダストリーコンサルタント（ライフサイエンス領域）- BUS',
  'ソリューション・エンジニア（金融領域）- TEC',
  'DXソリューションコンサルタント(自動車領域)-IND',
  'テクノロジーコンサルタント（公共サービス・医療健康領域）- TEC',
  'UIUXデザイナー / UIUX Designer - ソング本部',
  'インダストリーコンサルタント（化学領域）- BUS',
  'テクノロジーコンサルタント（通信・メディア・ハイテク領域）- TEC',
  'フィールドコンサルタント – OPE',
  'ファンクションコンサルタント（カスタマーサービス/チェンジマネジメント）- song',
  'データサイエンティスト/データドリブン コンサルタント - AIグループ - BUS',
  'Customer Data＆AI コンサルタント - song',
  'ECエンジニア / ECコンサルタント - song',
  'サーバーサイドリードエンジニア - song',
  'メディアプロモーター - OPE',
  'モバイルエクスペリエンスコンサルタント / エンジニア - TEC',
  '法務・コンプライアンス担当（シニア・アナリスト）-CORP',
  'M&Aコンサルタント - BUS',
  'テクノロジープラットフォーム戦略コンサルタント – TEC',
  'デジタル・テクノロジーアーキテクト - TEC',
  'BC(SAP)',
  '仙台オープンポジション - TEC',
  'マーケティングシステムエンジニア / マーケティングシステムコンサルタント - song',
  'BC(IT)',
  'BC(クリエイティブ)',
  'クオリティ&テスティングコンサルタント / エンジニア - TEC',
  'BC(文系)',
  'テクノロジーコンサルタント（インテグレーションアーキテクト）-TEC',
  'BC(半導体)',
  'KPMG_宇宙',
  'BC(ポテンシャル)',
  'BC(プロディース部)',
  'dirbato',
  'BC(不動産)',
  'インダストリーコンサルタント（石油・エネルギー領域）-BUS',
  'テクノロジーコンサルタント（サプライチェーン&オペレーション）-TEC',
  'インダストリーコンサルタント（素材領域）-BUS',
  'インダストリーコンサルタント（カスタマーフロント）【金融サービス領域】- song',
  'BC(事務職)',
  'リスク&コンプライアンスコンサルタント(CFO&EV)-BUS',
  'AC(IT)',
  'フロントエンドエンジニア - OPE',
  'インダストリーコンサルタント（電力・ガス領域）- BUS',
  'インダストリーコンサルタント（銀行領域）- BUS',
  'インダストリーコンサルタント（保険領域）- BUS',
  'ソフトウェアエンジニア（Java）- TEC',
  'インダストリーコンサルタント（公共サービス領域）- BUS',
  'Salesforce コンサルタント / エンジニア - TEC',
  'インダストリーコンサルタント（通信・メディア領域）- BUS',
  'BC（FAS）',
  '品質管理エキスパート（CQA）- テクノロジー コンサルティング本部 (QE&A)',
  'インフラエンジニア',
  'サステナビリティコンサルタント - ビジネス コンサルティング本部',
  'AIエンジニア - TEC (Data&AI)',
  'インダストリーコンサルタント（証券領域）- BUS',
  'インダストリーコンサルタント（消費財・サービス領域）-BUS',
];

// ── API利用額トラッキング（バックグラウンド側で一元管理） ──────────────────
// popup.js/content.jsは短命（ポップアップは閉じるとJSが即終了、content.jsは
// ページ遷移で破棄される）なため、chrome.storage.localへの書き込みが完了する
// 前にコンテキストごと消えて記録が失われることがある。永続的なservice worker
// 側で一元的に書き込むことで、この取りこぼしを防ぐ。
const CLAUDE_PRICING = {
  'claude-sonnet-4-6': { input: 3.00, output: 15.00 },
  'claude-haiku-4-5-20251001': { input: 1.00, output: 5.00 },
};

async function recordApiCostInBackground(model, usage) {
  const pricing = CLAUDE_PRICING[model];
  if (!pricing || !usage) return null;
  const cost = ((usage.input_tokens || 0) / 1e6) * pricing.input
    + ((usage.output_tokens || 0) / 1e6) * pricing.output;
  const today = new Date().toISOString().slice(0, 10);
  const r = await chrome.storage.local.get(['apiCostStats']);
  const stats = r.apiCostStats || { totalUSD: 0, byDate: {} };
  stats.totalUSD = (stats.totalUSD || 0) + cost;
  stats.byDate[today] = (stats.byDate[today] || 0) + cost;
  const cutoff = Date.now() - 90 * 24 * 60 * 60 * 1000;
  for (const d of Object.keys(stats.byDate)) {
    if (new Date(d).getTime() < cutoff) delete stats.byDate[d];
  }
  await chrome.storage.local.set({ apiCostStats: stats });
  return stats;
}

// ── 自動更新チェック ────────────────────────────────────────────────────
const GITHUB_MANIFEST_URL =
  'https://raw.githubusercontent.com/taichi536/project1/main/manifest.json';

async function checkForUpdate() {
  try {
    const res = await fetch(GITHUB_MANIFEST_URL + '?_=' + Date.now(), { cache: 'no-store' });
    if (!res.ok) return;
    const remote = await res.json();
    const current = chrome.runtime.getManifest().version;
    if (remote.version && remote.version !== current) {
      // バッチ実行中は強制リロードを延期（コンテンツスクリプトが破棄されてバッチが止まるのを防ぐ）
      // ただし30分以上前のバッチは異常終了とみなして延期しない（更新が永久にブロックされるのを防ぐ）
      // 夜間自動実行は最大3スロット並列で動くため、進捗はスロットごとに別キーに保存されている
      // （content.jsのautoAddProgressKey()参照）。どれか1つでも実行中ならリロードを延期する。
      const progressKeys = ['autoAddProgress', 'autoAddProgress_slot0', 'autoAddProgress_slot1', 'autoAddProgress_slot2'];
      const stored = await chrome.storage.local.get(progressKeys);
      const isRecentBatch = progressKeys.some(k => {
        const prog = stored[k];
        return prog?.running && prog?.ts && (Date.now() - prog.ts) < 30 * 60 * 1000;
      });
      if (isRecentBatch) {
        console.log(`[Snow-we] バッチ実行中のため更新を延期: ${current} → ${remote.version}`);
        return;
      }
      console.log(`[Snow-we] 新バージョン検出: ${current} → ${remote.version} 自動リロード中...`);
      chrome.runtime.reload();
    }
  } catch (_) {
    // ネットワーク不可時は無視
  }
}

// アラームが未登録の時だけ作成（サービスワーカー再起動のたびにリセットされるのを防ぐ）
// → ポップアップを開くたびに6秒後にreloadが走りポップアップが閉じるバグを修正
chrome.alarms.get('snowWeUpdateCheck', (existing) => {
  if (!existing) {
    chrome.alarms.create('snowWeUpdateCheck', { delayInMinutes: 5, periodInMinutes: 5 });
  }
});
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'snowWeUpdateCheck') checkForUpdate();
  if (alarm.name === 'snowWeAutoRun') startAutoRun();
  if (alarm.name === 'snowWeAnomalyCheck') checkAnomalies();
  if (alarm.name === 'snowWeGasQueueFlush') flushGasScoutQueue();
});

// ── スカウト記録のバッチ送信キュー ──────────────────────────────────────
// 以前は候補者を1件処理するたびに即座にGASへPOSTしていたが、RDSの一括送信等で
// 候補者が短時間に連続処理されると、GAS側・拡張機能側の両方で書き込みが競合
// しやすかった（このセッションで繰り返し見つかった不具合の根本原因）。
// 個別リクエストを都度投げるのをやめ、いったんキューに積んでおいて数秒〜1分
// おきにまとめて1回のリクエストで送る方式に変更。同時書き込みの発生回数
// そのものを減らすことで、競合が起きる余地自体を小さくする。
let _gasQueueChain = Promise.resolve();
function withQueueLock(fn) {
  const result = _gasQueueChain.then(fn, fn);
  _gasQueueChain = result.catch(() => {});
  return result;
}

async function enqueueGasScout(payload) {
  return withQueueLock(async () => {
    const { gasScoutQueue } = await chrome.storage.local.get(['gasScoutQueue']);
    const queue = gasScoutQueue || [];
    queue.push(payload);
    await chrome.storage.local.set({ gasScoutQueue: queue });
  });
}

// enqueueGasScoutと同じ直列化キュー(withQueueLock)を通すことで、
// 「キューを読む→送信対象として空にする」処理と新規追加が競合しないようにしている
let _quickFlushTimer = null;
function scheduleQuickFlush() {
  if (_quickFlushTimer) return;
  _quickFlushTimer = setTimeout(() => {
    _quickFlushTimer = null;
    flushGasScoutQueue();
  }, 12000); // 12秒デバウンス：連続する候補者処理をより大きな1回のバッチにまとめて
             // GASへのリクエスト本数自体を減らし、同時実行数の圧迫を緩和する
             // （以前は4秒だったが、複数メンバーが同時にスカウト送信する時間帯に
             // リクエストが集中し、GAS側の同時実行数上限に近づいていたと考えられるため延長）
}

chrome.alarms.get('snowWeGasQueueFlush', (existing) => {
  if (!existing) {
    // setTimeoutはサービスワーカーが途中で休止すると失われるため、
    // 1分おきのアラームを取りこぼし時の保険にする
    chrome.alarms.create('snowWeGasQueueFlush', { delayInMinutes: 1, periodInMinutes: 1 });
  }
});

// 連続失敗に応じて再送間隔を自動的に延ばすサーキットブレーカー。
// サービスワーカーはアイドル時に頻繁に再起動されメモリ上の変数が消えるため、
// chrome.storage.localに状態を持たせて再起動をまたいでも機能するようにする
// （30秒/1分/2分/4分/8分…と倍々に延ばし、最大15分でキャップ。GAS側の同時実行数
// 上限を拡張機能側から圧迫し続けて悪化させる「再送の嵐」を防ぐのが目的。
// キューの中身自体は消さないので、記録が失われることはなく間隔が空くだけ）
async function getGasBackoffUntil() {
  const { gasBackoff } = await chrome.storage.local.get(['gasBackoff']);
  return gasBackoff?.nextRetryTs || 0;
}
async function recordGasSuccess() {
  await chrome.storage.local.set({ gasBackoff: { consecutiveFailures: 0, nextRetryTs: 0 } });
}
async function recordGasFailure() {
  const { gasBackoff } = await chrome.storage.local.get(['gasBackoff']);
  const consecutiveFailures = (gasBackoff?.consecutiveFailures || 0) + 1;
  const waitMs = Math.min(30000 * Math.pow(2, consecutiveFailures - 1), 15 * 60 * 1000);
  await chrome.storage.local.set({
    gasBackoff: { consecutiveFailures, nextRetryTs: Date.now() + waitMs }
  });
  console.warn(`[Snow-we] GASサーキットブレーカー作動: 連続失敗${consecutiveFailures}回、次回再送まで約${Math.round(waitMs / 1000)}秒待機`);
}

async function flushGasScoutQueue() {
  return withQueueLock(async () => {
    // バックオフ期間中は今回のフラッシュをスキップ（キューの中身はそのまま残る）
    const backoffUntil = await getGasBackoffUntil();
    if (Date.now() < backoffUntil) return;

    const { gasSettings, gasScoutQueue } = await chrome.storage.local.get(['gasSettings', 'gasScoutQueue']);
    const queue = gasScoutQueue || [];
    if (queue.length === 0) return;
    const secret = gasSettings?.secret || 'snowwe2024';
    const urls = [gasSettings?.url, gasSettings?.dbUrl].filter((u, i, arr) => u && arr.indexOf(u) === i);
    if (urls.length === 0) return; // GAS未設定。次回のアラームで再試行

    // 送信対象をこの場でキューから確保する。ネットワーク待ちの間に新しく
    // 積まれた分は、空になった新しいキューに独立して溜まっていく
    await chrome.storage.local.set({ gasScoutQueue: [] });

    // フェッチがハングし続けて次のリクエストが積み重なるのを防ぐため、
    // 25秒でタイムアウトさせる（GASのLockService待ち最大30秒より少し短く設定）
    const body = JSON.stringify({ secret, action: 'recordScoutBatch', items: queue });
    const results = await Promise.allSettled(urls.map(async url => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 25000);
      try {
        const r = await fetch(url, { method: 'POST', body, signal: controller.signal });
        return await r.json();
      } finally {
        clearTimeout(timer);
      }
    }));
    const anySuccess = results.some(r => r.status === 'fulfilled' && r.value?.ok !== false);

    if (anySuccess) {
      await recordGasSuccess();
      for (const item of queue) {
        if (item.candidateId) await patchScoutHistoryEntry(item.candidateId, { gasSent: true });
      }
      console.log(`[Snow-we] スカウト記録バッチ送信成功: ${queue.length}件`);
    } else {
      await recordGasFailure();
      // 失敗の実際の理由を記録する（原因調査のため。rejectedならエラー内容、
      // fulfilledでもok:falseならGASが返したエラーメッセージを出す）
      results.forEach((r, i) => {
        if (r.status === 'rejected') {
          console.warn('[Snow-we] スカウト記録送信失敗の詳細 url=' + urls[i] + ':', r.reason?.message || r.reason);
        } else if (r.value?.ok === false) {
          console.warn('[Snow-we] スカウト記録送信、GASがエラーを返却 url=' + urls[i] + ':', r.value?.error || '(詳細不明)');
        }
      });
      console.warn('[Snow-we] スカウト記録バッチ送信、全URLで失敗。キューに戻します');
      const retried = queue.map(it => ({ ...it, _attempts: (it._attempts || 0) + 1 }));
      const giveUp = retried.filter(it => it._attempts >= 8); // 8回(約8分〜)失敗し続けたら諦めて人の確認に回す
      const keep = retried.filter(it => it._attempts < 8);
      for (const it of giveUp) {
        if (it.candidateId) await patchScoutHistoryEntry(it.candidateId, { gasSent: false, retryCount: 8 });
      }
      // このタイミングまでに新規追加された分と合流させて書き戻す（withQueueLock内なので安全）
      const { gasScoutQueue: currentQueue } = await chrome.storage.local.get(['gasScoutQueue']);
      await chrome.storage.local.set({ gasScoutQueue: [...keep, ...(currentQueue || [])] });
    }
  });
}

// scoutHistoryの1件だけを、書き込み直前に読み直してから安全に更新する
// （content.js側の同名ヘルパーと同じ考え方。詳細はそちらのコメント参照）
async function patchScoutHistoryEntry(candidateId, patch) {
  try {
    const { scoutHistory } = await chrome.storage.local.get(['scoutHistory']);
    const latest = scoutHistory || {};
    if (!latest[candidateId]) return; // 既に削除・変更されている場合は上書きしない
    latest[candidateId] = { ...latest[candidateId], ...patch };
    await chrome.storage.local.set({ scoutHistory: latest });
  } catch (_) {}
}

// ② GAS側が検知した「空欄で記録された」件について、ローカルにある正しい値で
// GAS側の空欄セルを自動で埋める（fixField）。ローカルに対応データが無い、
// または部分的にしか直せない場合だけ、人の確認が必要な残件として返す。
async function autoRepairAnomalies(url, secret, serverAnomalies, scoutHistory) {
  const remaining = [];
  const { gasSettings } = await chrome.storage.local.get(['gasSettings']);
  for (const a of serverAnomalies) {
    const h = a.candidateId ? (scoutHistory || {})[a.candidateId] : null;
    const fields = {};
    if (h) {
      if (a.missing.includes('担当者') && gasSettings?.recruiter) fields.recruiter = gasSettings.recruiter;
      if (a.missing.includes('会社名') && h.company) fields.company = h.company;
      if (a.missing.includes('ポジション名') && h.position) fields.position = h.position;
    }
    if (!a.candidateId || Object.keys(fields).length === 0) { remaining.push(a); continue; }
    try {
      const res = await fetch(url, { method: 'POST', body: JSON.stringify({ secret, action: 'fixField', candidateId: a.candidateId, fields }) });
      const data = await res.json();
      if (data.ok) {
        console.log('[Snow-we] 記録不備を自動修復:', a.candidateId, fields);
      } else {
        remaining.push(a);
      }
    } catch (_) {
      remaining.push(a);
    }
  }
  return remaining;
}

async function checkAnomalies() {
  try {
    const { gasSettings, scoutHistory } = await chrome.storage.local.get(['gasSettings', 'scoutHistory']);
    const url = gasSettings?.url || gasSettings?.dbUrl;
    const secret = gasSettings?.secret || 'snowwe2024';

    // ① GAS側で検知した「届いたが必須項目が空欄だった」ケース → 自動修復を試みる
    let serverAnomalies = [];
    if (url) {
      try {
        const res = await fetch(url, { method: 'POST', body: JSON.stringify({ secret, action: 'getAnomalies' }) });
        const data = await res.json();
        if (data.ok) serverAnomalies = data.anomalies || [];
      } catch (_) {
        // ネットワーク不可時は無視（次の定期チェックで再試行）
      }
      if (serverAnomalies.length > 0) {
        serverAnomalies = await autoRepairAnomalies(url, secret, serverAnomalies, scoutHistory);
      }
    }

    // ② クライアント側で「GASに一度も届かなかった」ケース（自動リトライがまだ成功していないもの）
    const tenMinAgo = Date.now() - 10 * 60 * 1000;
    const undelivered = Object.values(scoutHistory || {})
      .filter(h => h.gasSent === false && h.date && h.date < tenMinAgo && (h.retryCount || 0) >= 8)
      .map(h => ({ ts: h.date, recruiter: '', company: h.company || '', missing: 'GAS未送信(自動リトライ失敗)', sheet: '' }));

    const anomalies = [...serverAnomalies, ...undelivered].sort((a, b) => b.ts - a.ts);
    await chrome.storage.local.set({ recordAnomalies: { items: anomalies, checkedAt: Date.now() } });
    updateAnomalyBadge(anomalies.length);
  } catch (_) {
    // 想定外エラー時は無視（次の定期チェックで再試行）
  }
}

function updateAnomalyBadge(count) {
  if (count > 0) {
    chrome.action.setBadgeText({ text: String(Math.min(count, 99)) });
    chrome.action.setBadgeBackgroundColor({ color: '#DC2626' });
  } else {
    chrome.action.setBadgeText({ text: '' });
  }
}

// ── 夜間自動実行（並列スロット対応） ──────────────────────────────────────────
// slotId → {slotId, tabId, windowId, urlQueue, urlIndex, maxPages}
let _autoRunSlots = [];
// onUpdated 重複発火防止：送信済みタブIDセット
const _autoRunSentTabs = new Set();

function _doStartAutoRun(autoRunConfig) {
  const urls = (autoRunConfig.urls || []).filter(u => u?.trim());
  if (!urls.length) return;
  const maxPages = autoRunConfig.maxPagesPerUrl || 2;
  const concurrency = Math.min(autoRunConfig.concurrency || 1, 3);

  _autoRunSlots = [];

  // URLをconcurrency個のグループにラウンドロビン分配
  const groups = Array.from({ length: concurrency }, () => []);
  urls.forEach((url, i) => groups[i % concurrency].push(url));
  const activeGroups = groups.filter(g => g.length > 0);

  console.log(`[Snow-we] 夜間自動実行: ${urls.length}URL × ${activeGroups.length}並列`);
  chrome.storage.local.set({ autoRunState: { isRunning: true, startedAt: Date.now() } });

  activeGroups.forEach((groupUrls, slotIdx) => {
    const slot = { slotId: slotIdx, tabId: null, windowId: null, urlQueue: groupUrls, urlIndex: 0, maxPages };
    _autoRunSlots.push(slot);

    if (slotIdx === 0) {
      // スロット0: 既存ウィンドウで開く
      _openNextUrlInSlot(slot);
    } else {
      // スロット1+: 新しいウィンドウ（別ウィンドウなら各々アクティブタブを持てる）
      chrome.windows.create({ focused: false }, (win) => {
        slot.windowId = win.id;
        // windowsは空白タブ付きで開くので、そこに最初のURLを開く
        const blankTabId = win.tabs?.[0]?.id;
        chrome.tabs.create({ url: slot.urlQueue[0], windowId: win.id }, (tab) => {
          slot.tabId = tab.id;
          if (blankTabId) chrome.tabs.remove(blankTabId, () => {});
          console.log(`[Snow-we] スロット${slotIdx}: ウィンドウ作成 (${slot.urlQueue.length}URL)`);
        });
      });
    }
  });
}

function startAutoRun() {
  chrome.storage.local.get(['autoRunConfig'], ({ autoRunConfig }) => {
    if (!autoRunConfig?.enabled) return;
    _doStartAutoRun(autoRunConfig);
  });
}

function _openNextUrlInSlot(slot) {
  if (slot.urlIndex >= slot.urlQueue.length) {
    console.log(`[Snow-we] スロット${slot.slotId}: 全URL完了`);
    if (slot.windowId) { chrome.windows.remove(slot.windowId, () => {}); slot.windowId = null; }
    _autoRunSlots = _autoRunSlots.filter(s => s.slotId !== slot.slotId);
    if (_autoRunSlots.length === 0) {
      console.log('[Snow-we] 夜間自動実行完了 - 全スロット処理済み');
      chrome.storage.local.set({ autoRunState: { isRunning: false, completedAt: Date.now() } });
    }
    return;
  }
  const url = slot.urlQueue[slot.urlIndex];
  const opts = slot.windowId ? { url, windowId: slot.windowId } : { url };
  chrome.tabs.create(opts, (tab) => {
    slot.tabId = tab.id;
    console.log(`[Snow-we] スロット${slot.slotId}: ${slot.urlIndex + 1}/${slot.urlQueue.length} 開始`);
  });
}

chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status !== 'complete') return;
  const slot = _autoRunSlots.find(s => s.tabId === tabId);
  if (!slot) return;
  // Angular SPAはルーター初期化でstatus:'complete'が複数回発火する → 重複防止
  if (_autoRunSentTabs.has(tabId)) return;
  _autoRunSentTabs.add(tabId);
  // SPAや仮想スクロールはアクティブタブでないと描画されないため前面に出す
  chrome.tabs.update(tabId, { active: true }, () => {
    setTimeout(() => {
      chrome.tabs.sendMessage(tabId, {
        type: 'autoRun',
        slotId: slot.slotId,
        maxPages: slot.maxPages,
        urlIndex: slot.urlIndex,
        totalUrls: slot.urlQueue.length,
      }).catch(() => {});
    }, 2500);
  });
});

// サービスワーカー起動時にアラームを復元
chrome.storage.local.get(['autoRunConfig'], ({ autoRunConfig }) => {
  if (!autoRunConfig?.enabled) return;
  chrome.alarms.get('snowWeAutoRun', (existing) => {
    if (existing) return;
    setAutoRunAlarm(autoRunConfig);
  });
});

function setAutoRunAlarm(autoRunConfig) {
  chrome.alarms.clear('snowWeAutoRun', () => {
    if (!autoRunConfig?.enabled) return;
    const now = new Date();
    const h = autoRunConfig.hour ?? 2;
    const m = autoRunConfig.minute ?? 0;
    let minutesUntil = h * 60 + m - (now.getHours() * 60 + now.getMinutes());
    if (minutesUntil <= 0) minutesUntil += 24 * 60;
    chrome.alarms.create('snowWeAutoRun', { delayInMinutes: minutesUntil, periodInMinutes: 24 * 60 });
    console.log(`[Snow-we] 自動実行アラーム: ${minutesUntil}分後 (毎日${h}:${String(m).padStart(2,'0')})`);
  });
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  // API利用額の記録（popup/content.jsの短命なコンテキストに依存しないよう、
  // service worker側で書き込みを完結させる）
  if (msg.type === 'recordApiCost') {
    recordApiCostInBackground(msg.model, msg.usage)
      .then(stats => sendResponse({ ok: true, stats }))
      .catch(() => sendResponse({ ok: false }));
    return true;
  }

  // 自動実行: 1URL完了 → 次のURLへ
  if (msg.type === 'autoRunComplete') {
    const slotId = msg.slotId ?? 0;
    const slot = _autoRunSlots.find(s => s.slotId === slotId) || _autoRunSlots[0];
    if (slot) {
      if (slot.tabId) {
        _autoRunSentTabs.delete(slot.tabId);
        chrome.tabs.remove(slot.tabId, () => {});
        slot.tabId = null;
      }
      slot.urlIndex++;
      setTimeout(() => _openNextUrlInSlot(slot), 1500);
    }
    sendResponse({ ok: true });
    return true;
  }

  // アラーム設定
  if (msg.type === 'setAutoRunAlarm') {
    setAutoRunAlarm(msg.autoRunConfig);
    sendResponse({ ok: true });
    return true;
  }

  // 今すぐテスト実行
  if (msg.type === 'startAutoRunNow') {
    _doStartAutoRun(msg.autoRunConfig);
    sendResponse({ ok: true });
    return true;
  }

  // スカウト記録をバッチ送信キューに追加（content.jsの候補者処理から呼ばれる）
  if (msg.type === 'queueGasScout') {
    enqueueGasScout(msg.payload)
      .then(() => { scheduleQuickFlush(); sendResponse({ ok: true }); })
      .catch(() => sendResponse({ ok: false }));
    return true;
  }

  // 記録不備の再チェック（popup表示時に呼ばれる）
  if (msg.type === 'refreshAnomalies') {
    checkAnomalies().then(() => sendResponse({ ok: true })).catch(() => sendResponse({ ok: false }));
    return true;
  }

  // 記録不備を確認済みにする
  if (msg.type === 'ackAnomalies') {
    chrome.storage.local.get(['gasSettings']).then(({ gasSettings }) => {
      const url = gasSettings?.url || gasSettings?.dbUrl;
      const secret = gasSettings?.secret || 'snowwe2024';
      if (!url) { sendResponse({ ok: false }); return; }
      fetch(url, { method: 'POST', body: JSON.stringify({ secret, action: 'ackAnomalies' }) })
        .then(() => {
          chrome.storage.local.set({ recordAnomalies: { items: [], checkedAt: Date.now() } });
          updateAnomalyBadge(0);
          sendResponse({ ok: true });
        })
        .catch(() => sendResponse({ ok: false }));
    });
    return true;
  }

  // GASへのPOST中継
  if (msg.type === 'gasPost') {
    const { url, payload } = msg;
    if (!url) { sendResponse({ ok: false }); return true; }
    fetch(url, { method: 'POST', body: JSON.stringify(payload) })
      .then(r => r.json())
      .then(data => sendResponse({ ok: data.ok !== false, gasError: data.error || null }))
      .catch(err => sendResponse({ ok: false, gasError: err.message }));
    return true;
  }

  // チームのAI判定フィードバック一覧をGASから取得
  if (msg.type === 'getTeamFeedbacks') {
    chrome.storage.local.get(['gasSettings']).then(({ gasSettings }) => {
      const url    = gasSettings?.url || gasSettings?.dbUrl;
      const secret = gasSettings?.secret || 'snowwe2024';
      if (!url) { sendResponse({ feedbacks: [] }); return; }
      fetch(url, {
        method: 'POST',
        body: JSON.stringify({ secret, action: 'getFeedbacks', limit: 30 }),
      })
        .then(r => r.json())
        .then(data => sendResponse({ feedbacks: data.feedbacks || [] }))
        .catch(() => sendResponse({ feedbacks: [] }));
    });
    return true;
  }

  // ポジション要件をGASから取得
  if (msg.type === 'getPositionRequirements') {
    const { position } = msg;
    chrome.storage.local.get(['gasSettings']).then(({ gasSettings }) => {
      const url    = gasSettings?.positionUrl || gasSettings?.url || gasSettings?.dbUrl;
      const secret = gasSettings?.secret || 'snowwe2024';
      if (!url) {
        sendResponse({ ok: false, requirements: '', companyCriteria: '' });
        return;
      }
      fetch(url, {
        method: 'POST',
        body: JSON.stringify({ secret, action: 'getPositionRequirements', position }),
      })
        .then(r => r.json())
        .then(data => sendResponse(data))
        .catch(() => sendResponse({ ok: false, requirements: '', companyCriteria: '' }));
    });
    return true;
  }

  // ポジション一覧を返す（GASスプレッドシートから取得、失敗時はハードコードで代替）
  if (msg.type === 'getPositionList') {
    chrome.storage.local.get(['gasSettings']).then(({ gasSettings }) => {
      const positionUrl = gasSettings?.positionUrl || gasSettings?.url || gasSettings?.dbUrl;
      const secret = gasSettings?.secret || 'snowwe2024';
      if (!positionUrl) {
        sendResponse({ positions: POSITION_LIST });
        return;
      }
      fetch(positionUrl, {
        method: 'POST',
        body: JSON.stringify({ secret, action: 'getPositions' }),
      })
        .then(r => r.json())
        .then(data => {
          if (data.ok && data.positions?.length > 0) {
            console.log('[Snow-we] getPositionList: GASから取得成功', data.positions.length, '件');
            sendResponse({ positions: data.positions.map(p => typeof p === 'string' ? p : p.name) });
          } else {
            console.warn('[Snow-we] getPositionList: GAS応答が空/NG。ハードコード一覧にフォールバック', JSON.stringify(data).slice(0, 200));
            sendResponse({ positions: POSITION_LIST });
          }
        })
        .catch(e => {
          console.warn('[Snow-we] getPositionList: GAS取得失敗。ハードコード一覧にフォールバック', e.message);
          sendResponse({ positions: POSITION_LIST });
        });
    });
    return true;
  }

  // ポジション一覧（説明付き）を返す — AI提案機能用
  if (msg.type === 'getPositionListWithDesc') {
    chrome.storage.local.get(['gasSettings']).then(({ gasSettings }) => {
      // positionUrl → url → dbUrl の優先順でフォールバック
      const positionUrl = gasSettings?.positionUrl || gasSettings?.url || gasSettings?.dbUrl;
      const secret = gasSettings?.secret || 'snowwe2024';
      if (!positionUrl) { sendResponse({ positions: [] }); return; }
      fetch(positionUrl, {
        method: 'POST',
        body: JSON.stringify({ secret, action: 'getPositions' }),
      })
        .then(r => r.json())
        .then(data => {
          if (data.ok && data.positions?.length > 0) {
            sendResponse({ positions: data.positions });
          } else {
            sendResponse({ positions: [] });
          }
        })
        .catch(() => sendResponse({ positions: [] }));
    });
    return true;
  }
});
