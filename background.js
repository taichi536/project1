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
      const stored = await chrome.storage.local.get(['autoAddProgress']);
      const prog = stored.autoAddProgress;
      const isRecentBatch = prog?.running && prog?.ts && (Date.now() - prog.ts) < 30 * 60 * 1000;
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
});

// ── 夜間自動実行 ──────────────────────────────────────────────────
let _autoRunTabId = null;

function startAutoRun() {
  chrome.storage.local.get(['autoRunConfig'], ({ autoRunConfig }) => {
    if (!autoRunConfig?.enabled) return;
    const urls = (autoRunConfig.urls || []).filter(u => u?.trim());
    if (!urls.length) return;
    const maxPages = autoRunConfig.maxPagesPerUrl || 2;
    chrome.storage.local.set({ autoRunState: { isRunning: true, urls, urlIndex: 0, maxPages, startedAt: Date.now() } });
    openNextAutoRunUrl();
  });
}

function openNextAutoRunUrl() {
  chrome.storage.local.get(['autoRunState'], ({ autoRunState }) => {
    if (!autoRunState?.isRunning) return;
    const { urls, urlIndex, maxPages } = autoRunState;
    if (urlIndex >= urls.length) {
      console.log('[Snow-we] 夜間自動実行完了 - 全URL処理済み');
      chrome.storage.local.set({ autoRunState: { isRunning: false, completedAt: Date.now() } });
      return;
    }
    const url = urls[urlIndex];
    chrome.tabs.create({ url, active: false }, (tab) => {
      _autoRunTabId = tab.id;
      console.log(`[Snow-we] 夜間自動実行: ${urlIndex + 1}/${urls.length} タブ開始`);
    });
  });
}

chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status !== 'complete') return;
  if (tabId !== _autoRunTabId) return;
  chrome.storage.local.get(['autoRunState'], ({ autoRunState }) => {
    if (!autoRunState?.isRunning) return;
    setTimeout(() => {
      chrome.tabs.sendMessage(tabId, {
        type: 'autoRun',
        maxPages: autoRunState.maxPages,
        urlIndex: autoRunState.urlIndex,
        totalUrls: autoRunState.urls.length,
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
  // 自動実行: 1URL完了 → 次のURLへ
  if (msg.type === 'autoRunComplete') {
    chrome.storage.local.get(['autoRunState'], ({ autoRunState }) => {
      if (!autoRunState?.isRunning) return;
      if (_autoRunTabId) { chrome.tabs.remove(_autoRunTabId, () => {}); _autoRunTabId = null; }
      const nextIndex = (autoRunState.urlIndex || 0) + 1;
      chrome.storage.local.set({ autoRunState: { ...autoRunState, urlIndex: nextIndex } }, () => {
        setTimeout(openNextAutoRunUrl, 1500);
      });
    });
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
    const cfg = msg.autoRunConfig;
    const urls = (cfg.urls || []).filter(u => u?.trim());
    if (!urls.length) { sendResponse({ ok: false }); return true; }
    const maxPages = cfg.maxPagesPerUrl || 2;
    chrome.storage.local.set({
      autoRunState: { isRunning: true, urls, urlIndex: 0, maxPages, startedAt: Date.now() },
    }, () => { openNextAutoRunUrl(); });
    sendResponse({ ok: true });
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

  // ポジション要件をGASから取得
  if (msg.type === 'getPositionRequirements') {
    const { position } = msg;
    chrome.storage.local.get(['gasSettings']).then(({ gasSettings }) => {
      const url    = gasSettings?.dbUrl || gasSettings?.url;
      const secret = gasSettings?.secret;
      if (!url || !secret) {
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
      const positionUrl = gasSettings?.positionUrl;
      const secret = gasSettings?.secret;
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
            sendResponse({ positions: data.positions.map(p => p.name) });
          } else {
            sendResponse({ positions: POSITION_LIST });
          }
        })
        .catch(() => sendResponse({ positions: POSITION_LIST }));
    });
    return true;
  }
});
