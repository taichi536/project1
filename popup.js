// popup.js v1.14.1

const $ = id => document.getElementById(id);

// Supabase設定（content.jsと同一プロジェクト。承認待ちキューの読み書きに使用）
const SUPABASE_URL = 'https://ovwnyivqnqqiagutjxoo.supabase.co';
const SUPABASE_KEY = 'sb_publishable_tEQ4TOve0uCydsGiEm1cDA_D1LQ49wN';

const _ANTHROPIC_HEADERS = {
  'Content-Type': 'application/json',
  'anthropic-version': '2023-06-01',
  'anthropic-dangerous-direct-browser-access': 'true'
};

async function claudeFetch(apiKey, body, maxRetries = 4) {
  let delay = 3000;
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { ..._ANTHROPIC_HEADERS, 'x-api-key': apiKey },
      body: JSON.stringify(body)
    });
    if (response.status === 529 || response.status === 429) {
      if (attempt === maxRetries) throw new Error('APIが混み合っています。しばらく待ってから再試行してください。');
      await new Promise(r => setTimeout(r, delay));
      delay = Math.min(delay * 2, 30000);
      continue;
    }
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.error?.message || `APIエラー (${response.status})`);
    }
    const data = await response.json();
    await recordApiCost(body.model, data.usage);
    return data;
  }
}

// API利用額の記録はbackground.js（service worker）に一元化する。
// ポップアップは閉じると同時にJSが即座に終了するため、ここでchrome.storage.local
// に直接書き込むと、ユーザーが結果を見てすぐポップアップを閉じた場合に書き込みが
// 完了せず記録が失われる（実際の請求額と大きく乖離する原因になっていた）。
async function recordApiCost(model, usage) {
  if (!usage) return;
  try {
    const res = await chrome.runtime.sendMessage({ type: 'recordApiCost', model, usage });
    if (res?.stats) renderApiCostDisplay(res.stats);
  } catch (_) {}
}

function renderApiCostDisplay(stats) {
  const el = $('api-cost-display');
  if (!el || !stats) return;
  const today = new Date().toISOString().slice(0, 10);
  const todayUSD = stats.byDate[today] || 0;
  el.textContent = `API利用額 — 本日: $${todayUSD.toFixed(3)} / 累計: $${(stats.totalUSD || 0).toFixed(2)}`;
}

// ホスト名から媒体名を判定（フィードバック記録用。content.jsのgetPlatform()と同じ対応）
function platformFromHostname(hostname = '') {
  if (/bizreach|es-support/.test(hostname)) return 'bizreach';
  if (/doda-x|x\.doda/.test(hostname)) return 'dodax';
  if (/ambi|en-ambi/.test(hostname)) return 'ambi';
  if (/green-japan/.test(hostname)) return 'green';
  if (/mynavi/.test(hostname)) return 'mynavi';
  if (/rikunabi|hrtech|recruitdirect/.test(hostname)) return 'rds';
  return hostname || 'unknown';
}

// 単体判定の訂正フィードバックを記録する。ポップアップは独立したコンテキストで
// 完結するため、doda-xのようにページ遷移でオンページのバッジ・訂正ボタンが
// 消えてしまう媒体でも、ここから確実にフィードバックを記録できる
async function saveFeedback(profileSummary, aiVerdict, correction, platform) {
  const ts = Date.now();
  try {
    const stored = await chrome.storage.local.get(['snowWeFeedbacks']);
    const feedbacks = stored.snowWeFeedbacks || [];
    feedbacks.unshift({ profileSummary, aiVerdict, correction, platform, ts });
    if (feedbacks.length > 50) feedbacks.length = 50;
    await chrome.storage.local.set({ snowWeFeedbacks: feedbacks });
  } catch (_) {}

  try {
    const { gasSettings } = await chrome.storage.local.get(['gasSettings']);
    const gasUrl = gasSettings?.url || gasSettings?.dbUrl;
    const secret = gasSettings?.secret || 'snowwe2024';
    if (gasUrl && gasSettings?.feedbackEnabled !== false) {
      await chrome.runtime.sendMessage({
        type: 'gasPost',
        url: gasUrl,
        payload: {
          action: 'saveFeedback',
          secret,
          recruiter: gasSettings?.recruiter || '',
          platform,
          aiVerdict,
          correction,
          profileSummary,
          ts,
        }
      });
    }
  } catch (_) {}
}

// 判定結果に「訂正」ボタンを表示する（ポップアップ内で完結・ページ遷移の影響を受けない）
function renderFeedbackButtons(overall, profileSummary, platform) {
  const el = $('screening-feedback');
  if (!el) return;
  const options = overall === 'OK'
    ? [{ label: '❌ 実はNG', value: 'NG' }]
    : overall === 'NG'
    ? [{ label: '✅ 実はOK', value: 'OK' }]
    : [{ label: '✅ OK', value: 'OK' }, { label: '❌ NG', value: 'NG' }];

  el.style.display = 'flex';
  el.style.gap = '6px';
  el.innerHTML = '<span style="font-size:11px;color:#888780;align-self:center;">判定を訂正:</span>';
  options.forEach(({ label, value }) => {
    const btn = document.createElement('button');
    btn.textContent = label;
    btn.style.cssText = 'font-size:11px;padding:4px 9px;border-radius:6px;border:1px solid #d4d4d4;background:#fff;cursor:pointer;';
    btn.addEventListener('click', async () => {
      el.innerHTML = '<span style="font-size:11px;color:#888780;">保存中...</span>';
      await saveFeedback(profileSummary, overall, value, platform);
      el.innerHTML = `<span style="font-size:11px;color:#4338CA;">↩ 訂正: ${value} を記録しました</span>`;
    });
    el.appendChild(btn);
  });
}

// ============================================================
// 初期化
// ============================================================
document.addEventListener('DOMContentLoaded', async () => {
  try {
  // バージョン表示を manifest から自動更新
  try {
    const mv = chrome.runtime.getManifest();
    const vEl = document.querySelector('.header-text .sub');
    if (vEl && mv.version) vEl.textContent = `Snow-we.Inc — v${mv.version}`;
  } catch (_) {}

  const result = await chrome.storage.local.get(['apiKey', 'currentPosition']).catch(() => ({}));
  if (result.apiKey) $('api-key').value = result.apiKey;

  try {
    const costResult = await chrome.storage.local.get(['apiCostStats']);
    renderApiCostDisplay(costResult.apiCostStats || { totalUSD: 0, byDate: {} });
  } catch (_) {}

  // background.js からポジション一覧を取得してセレクタを初期化
  // MV3サービスワーカーが停止中の場合 sendMessage が失敗することがあるため try-catch
  const posSel = $('position-select');
  let positions = [];
  try {
    const resp = await chrome.runtime.sendMessage({ type: 'getPositionList' });
    positions = resp?.positions || [];
  } catch (_) {}
  (positions || []).forEach(name => {
    posSel.appendChild(new Option(name, name));
  });
  // 保存済みのポジションを復元
  if (result.currentPosition) posSel.value = result.currentPosition;
  // popup表示時に現在の選択を即座に保存（初回も含む）
  if (posSel.value) chrome.storage.local.set({ currentPosition: posSel.value });
  // ポジション変更時にchrome.storageへ保存
  posSel.addEventListener('change', () => {
    chrome.storage.local.set({ currentPosition: posSel.value });
  });

  // タブ切り替え
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      $(`tab-${btn.dataset.tab}`).classList.add('active');
      if (btn.dataset.tab === 'history') renderHistory();
      if (btn.dataset.tab === 'approval') renderApprovalQueue();
    });
  });

  // 社格チェックボックス
  document.querySelectorAll('#company-tier-group .checkbox-item').forEach(label => {
    label.addEventListener('click', () => {
      const cb = label.querySelector('input');
      cb.checked = !cb.checked;
      label.classList.toggle('checked', cb.checked);
    });
  });

  await loadSettings();

  // 記録不備アラート（Slack等の通知は使わず、popupを開いた時にだけ静かに知らせる）
  renderAnomalyBanner();
  chrome.runtime.sendMessage({ type: 'refreshAnomalies' }).then(() => renderAnomalyBanner()).catch(() => {});
  } catch (e) {
    console.error('[Snow-we] popup初期化エラー:', e);
  }
});

// ============================================================
// 記録不備アラート（担当者・会社名・ポジション名が空欄で記録されたケース）
// Slackのような即時プッシュ通知はうるさくなりがちなので採用せず、
// popupを開いた自然なタイミングでだけ、GAS側の検出結果を表示する。
// ============================================================
async function renderAnomalyBanner() {
  const { recordAnomalies } = await chrome.storage.local.get(['recordAnomalies']).catch(() => ({}));
  const items = recordAnomalies?.items || [];
  const banner = $('anomaly-banner');
  const text = $('anomaly-banner-text');
  if (!banner || !text) return;
  if (items.length === 0) { banner.style.display = 'none'; return; }
  const preview = items.slice(0, 3)
    .map(a => `・${a.recruiter || '不明'} / ${a.company || '不明'} / ${a.missing}`).join('\n');
  text.textContent = `⚠️ スカウト記録に不備が${items.length}件あります\n${preview}` +
    (items.length > 3 ? `\n...他${items.length - 3}件` : '');
  banner.style.display = 'block';
}

$('anomaly-ack-btn')?.addEventListener('click', async () => {
  await chrome.runtime.sendMessage({ type: 'ackAnomalies' }).catch(() => {});
  renderAnomalyBanner();
});

// ============================================================
// APIキー保存
// ============================================================
// APIキーからASCII範囲外の文字を除去する
function sanitizeApiKey(raw) {
  return (raw || '').replace(/[^\x21-\x7E]/g, '').trim();
}

$('save-btn').addEventListener('click', () => {
  const raw = $('api-key').value;
  const key = sanitizeApiKey(raw);
  if (!key) return;

  // 除去された文字があれば入力欄を更新して通知
  if (key !== raw.trim()) {
    $('api-key').value = key;
    $('save-btn').textContent = '⚠️ 不正文字を除去して保存';
    setTimeout(() => { $('save-btn').textContent = '保存'; }, 3000);
  } else {
    $('save-btn').textContent = '保存済';
    setTimeout(() => { $('save-btn').textContent = '保存'; }, 2000);
  }

  chrome.storage.local.set({ apiKey: key });
});

// ============================================================
// 設定の保存・読み込み
// ============================================================
async function loadSettings() {
  const r = await chrome.storage.local.get(['screeningCriteria', 'gasSettings', 'autoRunConfig']);
  const c = r.screeningCriteria || {};
  const gas = r.gasSettings || {};

  if (c.ageMin) $('age-min').value = c.ageMin;
  if (c.ageMax) $('age-max').value = c.ageMax;
  const ai = c.ageIncome || {};
  if (ai.age20s)    $('income-20s').value    = ai.age20s;
  if (ai.age30to35) $('income-30to35').value = ai.age30to35;
  if (ai.age36to39) $('income-36to39').value = ai.age36to39;
  if (ai.age40to42) $('income-40to42').value = ai.age40to42;
  if (ai.age43to45) $('income-43to45').value = ai.age43to45;
  if (c.educationReq) $('education-req').value = c.educationReq;
  if (c.minTenure) $('min-tenure').value = c.minTenure;
  if (c.requiredKeywords) $('required-keywords').value = c.requiredKeywords;
  if (c.excludeCompanies !== undefined) {
    $('exclude-companies').value = c.excludeCompanies;
  } else {
    $('exclude-companies').value = 'アクセンチュア, ベイカレント';
  }
  if (c.excludeKeywords) $('exclude-keywords').value = c.excludeKeywords;
  if (c.autoTagName) $('auto-tag-name').value = c.autoTagName;

  if (gas.recruiter) $('gas-recruiter').value = gas.recruiter;
  if (gas.url) $('gas-url').value = gas.url;
  if (gas.dbUrl) $('gas-db-url').value = gas.dbUrl;
  if (gas.secret) $('gas-secret').value = gas.secret;
  if (gas.positionUrl) $('position-gas-url').value = gas.positionUrl;
  $('toggle-scout-record').checked = gas.scoutRecordEnabled !== false;
  $('toggle-feedback').checked = gas.feedbackEnabled !== false;

  const arc = r.autoRunConfig || {};
  $('auto-run-enabled').checked = arc.enabled || false;
  $('auto-run-hour').value = arc.hour ?? 2;
  $('auto-run-minute').value = arc.minute ?? 0;
  $('auto-run-max-pages').value = arc.maxPagesPerUrl ?? 2;
  $('auto-run-concurrency').value = arc.concurrency ?? 1;
  $('auto-run-urls').value = (arc.urls || []).join('\n');

  if (c.companyTiers && c.companyTiers.length > 0) {
    document.querySelectorAll('#company-tier-group .checkbox-item').forEach(label => {
      const val = label.dataset.value;
      const cb = label.querySelector('input');
      if (c.companyTiers.includes(val)) {
        cb.checked = true;
        label.classList.add('checked');
      }
    });
  }
}

$('settings-save-btn').addEventListener('click', async () => {
  const companyTiers = [];
  document.querySelectorAll('#company-tier-group input:checked').forEach(cb => {
    companyTiers.push(cb.value);
  });

  const parseIncome = id => { const v = $(id).value; return v ? parseInt(v) : null; };
  const criteria = {
    ageMin: $('age-min').value ? parseInt($('age-min').value) : null,
    ageMax: $('age-max').value ? parseInt($('age-max').value) : null,
    ageIncome: {
      age20s:    parseIncome('income-20s'),
      age30to35: parseIncome('income-30to35'),
      age36to39: parseIncome('income-36to39'),
      age40to42: parseIncome('income-40to42'),
      age43to45: parseIncome('income-43to45'),
    },
    companyTiers,
    educationReq: $('education-req').value,
    minTenure: $('min-tenure').value ? parseFloat($('min-tenure').value) : null,
    requiredKeywords: $('required-keywords').value.trim(),
    excludeCompanies: $('exclude-companies').value.trim(),
    excludeKeywords: $('exclude-keywords').value.trim(),
    autoTagName: $('auto-tag-name').value.trim(),
  };

  const gasSettings = {
    recruiter: $('gas-recruiter').value.trim(),
    url: $('gas-url').value.trim(),
    dbUrl: $('gas-db-url').value.trim(),
    secret: $('gas-secret').value.trim(),
    positionUrl: $('position-gas-url').value.trim(),
    scoutRecordEnabled: $('toggle-scout-record').checked,
    feedbackEnabled: $('toggle-feedback').checked,
  };
  // recruiterNameを単独でも保存（content scriptからの読み込みを安定化）
  chrome.storage.local.set({ recruiterName: gasSettings.recruiter });

  const autoRunConfig = {
    enabled: $('auto-run-enabled').checked,
    hour: parseInt($('auto-run-hour').value) || 2,
    minute: parseInt($('auto-run-minute').value) || 0,
    maxPagesPerUrl: parseInt($('auto-run-max-pages').value) || 2,
    concurrency: Math.min(parseInt($('auto-run-concurrency').value) || 1, 3),
    urls: $('auto-run-urls').value.split('\n').map(u => u.trim()).filter(Boolean),
  };

  await chrome.storage.local.set({ screeningCriteria: criteria, gasSettings, autoRunConfig });
  chrome.runtime.sendMessage({ type: 'setAutoRunAlarm', autoRunConfig }).catch(() => {});

  const saved = $('settings-saved');
  saved.style.display = 'block';
  setTimeout(() => { saved.style.display = 'none'; }, 2000);
});

// 夜間自動実行 テスト実行
$('auto-run-test-btn').addEventListener('click', async () => {
  const urls = $('auto-run-urls').value.split('\n').map(u => u.trim()).filter(Boolean);
  const maxPages = parseInt($('auto-run-max-pages').value) || 2;
  const statusEl = $('auto-run-test-status');

  if (urls.length === 0) {
    statusEl.style.display = 'block';
    statusEl.textContent = '❌ URLを1件以上入力してください';
    return;
  }

  // 設定を一時保存してstartAutoRunをトリガー
  const autoRunConfig = {
    enabled: true,
    hour: parseInt($('auto-run-hour').value) || 2,
    minute: parseInt($('auto-run-minute').value) || 0,
    maxPagesPerUrl: maxPages,
    urls,
  };
  await chrome.storage.local.set({ autoRunConfig });
  chrome.runtime.sendMessage({ type: 'startAutoRunNow', autoRunConfig }).catch(() => {});

  statusEl.style.display = 'block';
  statusEl.textContent = `▶ テスト実行開始: ${urls.length}件のURLを順番に処理します。ブラウザのタブが自動で開きます。`;
});

// GAS接続テスト
$('gas-test-btn').addEventListener('click', async () => {
  const url = $('gas-url').value.trim();
  const recruiter = $('gas-recruiter').value;
  const secret = $('gas-secret').value.trim();
  const resultEl = $('gas-test-result');
  resultEl.style.display = 'block';
  resultEl.style.color = '#2c2c2a';

  if (!url) { resultEl.textContent = '❌ GAS URLを入力してください'; return; }
  if (!recruiter) { resultEl.textContent = '❌ 担当者を選択してください'; return; }

  resultEl.textContent = '接続中...';
  try {
    const res = await fetch(url, {
      method: 'POST',
      body: JSON.stringify({
        secret,
        recruiter,
        company: '【テスト】接続確認',
        age: '30',
        media: 'rds',
        position: 'テスト',
        industry: 'テスト',
        ts: Date.now(),
      }),
    });
    const text = await res.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { raw: text }; }
    if (data.ok) {
      resultEl.style.color = '#085041';
      resultEl.textContent = data.sheet
        ? `✅ 接続成功！シート「${data.sheet}」の${data.row}行目に書き込みました`
        : '✅ 接続成功！GASスプレッドシートへの書き込みを確認しました';
    } else {
      resultEl.style.color = '#b91c1c';
      resultEl.textContent = `❌ エラー: ${data.error || text}`;
    }
  } catch (e) {
    resultEl.style.color = '#b91c1c';
    resultEl.textContent = `❌ 通信エラー: ${e.message}`;
  }
});

// ============================================================
// タブ1: パーソナライズ文生成
// ============================================================
$('generate-btn').addEventListener('click', () => runGenerate());
$('regen-btn').addEventListener('click', () => runGenerate());

$('copy-btn').addEventListener('click', () => {
  const text = $('result-text').textContent;
  navigator.clipboard.writeText(text).then(() => {
    $('copy-btn').textContent = 'コピーしました!';
    $('copy-btn').classList.add('copied');
    setTimeout(() => {
      $('copy-btn').textContent = '文のみコピー';
      $('copy-btn').classList.remove('copied');
    }, 2000);
  });
});

$('copy-template-btn').addEventListener('click', () => {
  const personalized = $('result-text').textContent.trim();
  const positionName = $('position-select').value;
  const template = buildTemplate(personalized, positionName);
  navigator.clipboard.writeText(template).then(() => {
    $('copy-template-btn').textContent = 'コピーしました!';
    $('copy-template-btn').classList.add('copied');
    setTimeout(() => {
      $('copy-template-btn').textContent = 'テンプレ全文をコピー';
      $('copy-template-btn').classList.remove('copied');
    }, 2000);
  });
});

function buildTemplate(personalizedLine, positionName) {
  const pos = positionName || '営業戦略コンサルタント';
  return `候補者様

初めまして。ハイクラス転職エージェント、株式会社Snow-we.Inc代表の桝井と申します。

この度、貴方様のご経歴を拝見し、アクセンチュアの「${pos}」のポジションに高い親和性を感じ、ご連絡いたしました。

${personalizedLine}

当方の経験上、面接次第ではありますが、かなり高い確度で本ポジションにてオファーが出ると感じます。

また、コンサルの長時間労働等をご懸念される方も多いですが、働き方改革も相当に進んでおり、残業平均は月20時間程度でWLBを大事にしながら、無理なく新たなチャレンジをしていける環境に変貌しております。

ポジション詳細のご紹介の前に少しだけ、弊社と当方のご紹介をさせてください。`;
}

// content.jsが動いているか確認し、必要なら再注入してからプロフィール取得
async function getProfileSafe(tab) {
  // pingでcontent.js動作確認
  const isAlive = await chrome.tabs.sendMessage(tab.id, { action: 'ping' })
    .then(() => true).catch(() => false);

  if (!isAlive) {
    // 動いていない → 再注入
    try {
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] });
      await new Promise(r => setTimeout(r, 1000));
    } catch (e) {
      throw new Error('このページでは動作できません。対応している媒体の候補者ページを開いてください。');
    }
  }

  // プロフィール取得
  try {
    return await chrome.tabs.sendMessage(tab.id, { action: 'getProfile' });
  } catch (e) {
    throw new Error('プロフィールの取得に失敗しました。ページを再読み込みしてください。');
  }
}

async function runGenerate() {
  const apiKey = sanitizeApiKey($('api-key').value);
  if (!apiKey) {
    setStatus('generate', 'error', 'APIキーを入力して保存してください');
    return;
  }

  setStatus('generate', 'loading', 'プロフィールを取得中...');
  $('generate-btn').disabled = true;
  $('result-section').style.display = 'none';

  let profileData;
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    profileData = await getProfileSafe(tab);
  } catch (e) {
    setStatus('generate', 'error', 'プロフィールを取得できませんでした。ページを再読み込みして再度お試しください。');
    $('generate-btn').disabled = false;
    return;
  }

  if (!profileData || !profileData.success) {
    if (profileData && profileData.needsCandidateSelection) {
      setStatus('generate', 'error', '👆 候補者カードをクリックして右パネルにプロフィールを表示してから実行してください');
    } else {
      setStatus('generate', 'error', 'プロフィール情報が取得できませんでした');
    }
    $('generate-btn').disabled = false;
    return;
  }

  // 選択中のポジション情報を取得
  const positionName = $('position-select').value || '';
  let positionDescription = '';
  if (positionName) {
    try {
      const r2 = await chrome.storage.local.get(['gasSettings']);
      const gas2 = r2.gasSettings || {};
      const posUrl = gas2.positionUrl || gas2.url || gas2.dbUrl;
      if (posUrl) {
        const posRes = await fetch(posUrl, {
          method: 'POST',
          body: JSON.stringify({ secret: gas2.secret || 'snowwe2024', action: 'getPositionRequirements', position: positionName }),
        });
        if (posRes.ok) {
          const posData = await posRes.json();
          positionDescription = posData.requirements || '';
        }
      }
    } catch (_) {}
  }

  setStatus('generate', 'loading', `パーソナライズ文を生成中... (取得: ${profileData.length || 0}文字)`);

  try {
    const result = await generatePersonalizedLine(apiKey, profileData.profileText, positionName, positionDescription);
    $('result-text').textContent = result;
    $('result-section').style.display = 'block';
    setStatus('generate', 'success', '生成完了 — コピーしてテンプレ冒頭に貼り付けてください');
  } catch (e) {
    setStatus('generate', 'error', `生成エラー: ${e.message}`);
  }

  $('generate-btn').disabled = false;
}

async function generatePersonalizedLine(apiKey, profileText, positionName = '', positionDescription = '') {
  apiKey = sanitizeApiKey(apiKey);

  const positionSection = positionName ? `
【応募ポジション】
名称: ${positionName}
${positionDescription ? `募集要件:\n${positionDescription.substring(0, 800)}` : ''}
` : '';

  const prompt = `あなたはハイクラスコンサル転職エージェントのアシスタントです。

以下の候補者プロフィールを読んで、スカウトメールに挿入するパーソナライズ文を1文で作成してください。

【挿入位置】
直前：「この度、貴方様のご経歴を拝見し、アクセンチュアの「${positionName || '〇〇'}」のポジションに高い親和性を感じ、ご連絡いたしました。」
直後：「当方の経験上、面接次第ではありますが、かなり高い確度で本ポジションにてオファーが出ると感じます。」

【良い例】
・「証券リテール営業10年で個人成果と支店マネジメントの両面を担われ、営業プレイヤーと育成担当の経験を積み重ねてこられた点が印象的でした。」
・「金融機関での現場営業を土台に、提携銀行への販売推進では研修設計から同行サポートまで構造的に支援を組み立ててこられており、このポジションをはじめ幅広い可能性を感じております。」

【厳禁】
- 「〜でいらっしゃいます。」という断定で終わるのはNG
- 「まさに〜そのもの」「〜こそが〜」のような大げさな断言
- 「〜視座」「〜発想転換」「〜思考プロセス」のような仰々しい分析表現
- 「即戦力」「希少」などの評価語
- 「高い親和性を感じ」の繰り返し
- 「ぜひ〜」「お話しさせていただきたく」
- 「〇〇様」「田中様」など名前から書き始めること

【文末】
必ず「〜、このポジションをはじめ幅広い可能性があると感じます。」または「〜、このポジションやその他にも多くの可能性があると感じます。」のような形で締めること。

【ルール】
- 1文のみ。余計な前置き・説明・補足は一切不要
- 職歴・実績の描写から直接入る
- 丁寧だが重くなりすぎないトーン
- 「※」「---」で始まる注記・免責・説明文は絶対に出力しないこと
- 出力は1文のみ。それ以外は何も書かないこと

【候補者プロフィール】
${profileText}`;

  const data = await claudeFetch(apiKey, {
    model: 'claude-sonnet-4-6',
    max_tokens: 200,
    messages: [{ role: 'user', content: prompt }]
  });
  const text = data.content?.[0]?.text || '';
  if (!text) throw new Error('レスポンスが空でした');
  // Strip any appended footnotes (e.g. "---\n\n※プロフィールが..." added when profile data is thin)
  const cleaned = text
    .replace(/\s*---[\s\S]*$/, '')   // remove "---" separator and everything after
    .replace(/\s*※[\s\S]*$/, '')    // remove "※" footnote and everything after
    .trim();
  return cleaned.replace(/^「/, '').replace(/」$/, '');
}

// ============================================================
// タブ2: ポジション提案
// ============================================================
$('suggest-btn').addEventListener('click', () => runSuggestPosition());

async function runSuggestPosition() {
  const apiKey = sanitizeApiKey($('api-key').value);
  if (!apiKey) {
    setStatus('suggest', 'error', 'APIキーを入力して保存してください');
    return;
  }

  setStatus('suggest', 'loading', 'プロフィールを取得中...');
  $('suggest-btn').disabled = true;
  $('suggest-result').style.display = 'none';

  let profileData;
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    profileData = await getProfileSafe(tab);
  } catch (e) {
    setStatus('suggest', 'error', 'プロフィールを取得できませんでした。ページを再読み込みして再度お試しください。');
    $('suggest-btn').disabled = false;
    return;
  }

  if (!profileData || !profileData.success || !profileData.profileText) {
    if (profileData && profileData.needsCandidateSelection) {
      setStatus('suggest', 'error', '👆 候補者カードをクリックして右パネルにプロフィールを表示してから実行してください');
    } else {
      setStatus('suggest', 'error', 'プロフィール情報が取得できませんでした');
    }
    $('suggest-btn').disabled = false;
    return;
  }

  setStatus('suggest', 'loading', 'ポジションを分析中...');

  try {
    const result = await suggestPosition(apiKey, profileData.profileText);
    renderSuggestion(result);
    $('suggest-result').style.display = 'block';
    setStatus('suggest', 'success', '分析完了');
  } catch (e) {
    setStatus('suggest', 'error', `分析エラー: ${e.message}`);
  }

  $('suggest-btn').disabled = false;
}

async function fetchPositionsFromGas(positionUrl, secret) {
  const res = await fetch(positionUrl, {
    method: 'POST',
    body: JSON.stringify({ secret, action: 'getPositions' }),
  });
  if (!res.ok) throw new Error(`GAS接続エラー (${res.status})`);
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || 'ポジション取得失敗');
  return data.positions || [];
}

async function extractCandidateAttributes(apiKey, profileText) {
  const prompt = `以下の候補者プロフィールから転職提案に必要な属性を抽出してください。

【候補者プロフィール】
${profileText}

JSON形式のみで出力（コードブロック不要）:
{"current_role":"現在の役職","current_industry":"現職業界（例:SIer・コンサル・メーカー等）","company_size":"企業規模（大手・中堅・ベンチャー等）","experience_years":経験年数の整数,"key_skills":["スキル1","スキル2"],"estimated_grade":"推定グレード（例:Manager相当・Consultant相当）","transfer_axis":"転職軸（記載があれば。なければ職歴から推測）","strengths":"アクセンチュアで活かせる最大の強み1文"}`;

  const data = await claudeFetch(apiKey, {
    model: 'claude-haiku-4-5-20251001',
    max_tokens: 400,
    messages: [{ role: 'user', content: prompt }]
  }).catch(() => null);
  if (!data) return null;
  const text = (data.content?.[0]?.text || '').trim();
  const match = text.match(/\{[\s\S]*\}/);
  if (!match) return null;
  try { return JSON.parse(match[0]); } catch (_) { return null; }
}

async function suggestPosition(apiKey, profileText) {
  apiKey = sanitizeApiKey(apiKey);

  // GASからポジション取得を試みる
  const r = await chrome.storage.local.get(['gasSettings']);
  const gas = r.gasSettings || {};
  let positions = [];
  let usingGas = false;

  const gasUrl = gas.positionUrl || gas.url || gas.dbUrl;
  if (gasUrl) {
    try {
      setStatus('suggest', 'loading', 'GASからポジション情報を取得中...');
      const fetched = await fetchPositionsFromGas(gasUrl, gas.secret || 'snowwe2024');
      if (fetched.length > 0) {
        positions = fetched;
        usingGas = true;
      }
    } catch (e) {
      // GAS取得失敗時はデフォルト一覧にフォールバック
    }
  }

  // Step 0: 候補者プロフィールを構造化抽出
  setStatus('suggest', 'loading', '候補者プロフィールを分析中...');
  const candidateAttrs = await extractCandidateAttributes(apiKey, profileText);

  if (!usingGas) {
    // GAS未設定：従来通り1回のSonnet呼び出し（ポジション名のみ）
    const positionListText = Array.from(document.querySelectorAll('#position-select option'))
      .map(o => o.value).filter(Boolean).join('\n');
    setStatus('suggest', 'loading', 'ポジションを分析中...');
    return await suggestPositionSingleStep(apiKey, profileText, positionListText, candidateAttrs);
  }

  // GAS設定済み：ポジション数が30件以下なら全件をSonnetへ直接渡す
  if (positions.length <= 30) {
    setStatus('suggest', 'loading', `${positions.length}件のポジションを分析中...`);
    const detailList = positions
      .map(p => p.description ? `${p.name}: ${p.description}` : p.name)
      .join('\n');
    return await suggestPositionSingleStep(apiKey, profileText, detailList, candidateAttrs);
  }

  // 31件以上の場合：2ステップ処理
  // ── Step 1: Haikuで全ポジションから上位15件に絞り込み ──
  setStatus('suggest', 'loading', `Step1: ${positions.length}件から候補を絞り込み中...`);
  const nameWithSnippetList = positions.map(p =>
    p.description ? `${p.name}（${p.description.substring(0, 120)}）` : p.name
  ).join('\n');
  const step1Prompt = `あなたはアクセンチュア転職支援の専門エージェントです。
以下の候補者プロフィールと募集ポジション一覧を照合し、最も合致しそうなポジション名を上位15件選んでください。
ポジション名の後の括弧内は募集要件の冒頭です。候補者の職歴・スキルと照合して判断してください。

【募集ポジション一覧（名前＋要件概要）】
${nameWithSnippetList}

【候補者プロフィール】
${profileText}

【重要】出力はJSON配列のみ。ポジション名は一覧に記載された文字列を一字一句そのままコピーすること:
["ポジション名1","ポジション名2",...]`;

  const step1Data = await claudeFetch(apiKey, {
    model: 'claude-haiku-4-5-20251001',
    max_tokens: 500,
    messages: [{ role: 'user', content: step1Prompt }]
  });
  const step1Text = (step1Data.content?.[0]?.text || '').trim();
  const arrMatch = step1Text.match(/\[[\s\S]*\]/);
  let top15Names = [];
  if (arrMatch) {
    try { top15Names = JSON.parse(arrMatch[0]); } catch (_) {}
  }

  // 完全一致→部分一致の順でポジションを照合
  const matched = top15Names.map(name => {
    const exact = positions.find(p => p.name === name);
    if (exact) return exact;
    const partial = positions.find(p => p.name.includes(name) || name.includes(p.name));
    return partial || null;
  }).filter(Boolean);

  // マッチできなかった場合はStep1をスキップして全件渡す
  const top15 = matched.length >= 3 ? matched : positions;

  // ── Step 2: Sonnetで詳細ランキング ──
  setStatus('suggest', 'loading', `Step2: ${top15.length}件を詳細分析中...`);
  const detailList = top15
    .map(p => p.description ? `${p.name}: ${p.description}` : p.name)
    .join('\n');
  return await suggestPositionSingleStep(apiKey, profileText, detailList, candidateAttrs);
}

async function suggestPositionSingleStep(apiKey, profileText, positionListText, candidateAttrs = null) {
  const attrSection = candidateAttrs ? `
【候補者属性（構造化）】
- 現職: ${candidateAttrs.current_role || '不明'}（${candidateAttrs.current_industry || '不明'} / ${candidateAttrs.company_size || '不明'}）
- 経験年数: ${candidateAttrs.experience_years || '不明'}年
- 主要スキル: ${(candidateAttrs.key_skills || []).join('、') || '不明'}
- 推定グレード: ${candidateAttrs.estimated_grade || '不明'}
- 転職軸: ${candidateAttrs.transfer_axis || '不明'}
- 強み: ${candidateAttrs.strengths || '不明'}
` : '';

  const prompt = `あなたはアクセンチュア日本法人への転職支援を専門とするハイクラス転職エージェントです。
候補者にスカウトを送る際、どのポジションで打てば「刺さるか」を判断してください。
${attrSection}
【判断の視点】
1. 候補者の推定グレード・経験年数に見合ったポジションか
2. 候補者の主要スキルと募集要件が具体的に合致しているか
3. 候補者の転職軸・強みが活かせるポジションか（転職軸が不明な場合は職歴から推測）
4. 「名前：募集要件」の形式の場合は必ず募集要件の内容を精読し、候補者のスキル・経験と照合すること

【重要ルール】
- 必ず【募集ポジション一覧】に記載されたポジション名をそのまま使用すること（コロン以前の部分のみ）
- 一覧にないポジション名は絶対に使用しないこと
- スコアは「このポジションで打ったら候補者に刺さる確度」として1〜100で評価すること
- 候補者の経験と募集要件が実質的に合致しているポジションのみ推薦すること

【募集ポジション一覧】
${positionListText}

【候補者プロフィール】
${profileText}

以下のJSON形式のみで出力してください（コードブロック・前置き・説明は一切不要）:
{"suggestions":[{"position":"ポジション名","match_score":90,"reason":"推奨理由を1文で記述"}]}
※必ず守ること: reasonは1文で簡潔に。ダブルクォート・改行・バックスラッシュを含めないこと。`;

  const data = await claudeFetch(apiKey, {
    model: 'claude-sonnet-4-6',
    max_tokens: 1500,
    messages: [{ role: 'user', content: prompt }]
  });
  const text = (data.content?.[0]?.text || '').trim();
  const jsonMatch = text.match(/\{[\s\S]*\}/);
  if (!jsonMatch) throw new Error('AIの応答からJSONを抽出できませんでした');
  const cleaned = jsonMatch[0]
    .replace(/[\r\n]+/g, ' ')
    .replace(/,(\s*[}\]])/g, '$1')
    .replace(/[\x00-\x1F\x7F]/g, ' ')
    .replace(/\s+/g, ' ');
  try {
    return JSON.parse(cleaned);
  } catch (e) {
    throw new Error(`JSON解析エラー（AIの応答形式が不正）: ${e.message}`);
  }
}

function renderSuggestion(result) {
  const container = $('suggest-cards');
  container.innerHTML = '';

  (result.suggestions || []).forEach((s, i) => {
    const score = s.match_score || 0;
    const card = document.createElement('div');
    card.className = 'suggest-card' + (i === 0 ? ' best' : '');
    const scoreLabel = score >= 80 ? '刺さる可能性 高' : score >= 60 ? '刺さる可能性 中' : '参考程度';
    const scoreColor = score >= 80 ? '#059669' : score >= 60 ? '#D97706' : '#6B7280';
    card.innerHTML = `
      <div class="suggest-card-header">
        <span class="suggest-rank">${i === 0 ? '🥇 最推奨' : i === 1 ? '🥈 次点' : '🥉 候補'}</span>
        <span class="suggest-score" style="color:${scoreColor}">${score}点 <span style="font-size:10px;font-weight:normal">(${scoreLabel})</span></span>
      </div>
      <div class="suggest-position">${escapeHtml(s.position || '')}</div>
      <div class="suggest-reason">${escapeHtml(s.reason || '')}</div>
      <button class="use-position-btn" data-position="${escapeHtml(s.position || '')}">このポジションで生成</button>
    `;
    container.appendChild(card);

    card.querySelector('.use-position-btn').addEventListener('click', () => {
      $('position-select').value = s.position;
      document.querySelectorAll('.tab-btn')[0].click();
      const existing = $('result-text').textContent.trim();
      if (!existing) runGenerate();
    });
  });

  if (result.suggestions?.[0]) {
    $('position-select').value = result.suggestions[0].position;
  }
}

// ============================================================
// タブ3: 一次選定（一括）
// ============================================================
$('batch-screening-btn').addEventListener('click', () => runBatchScreening());
$('auto-add-btn').addEventListener('click', () => runAutoAdd());
$('screening-btn').addEventListener('click', () => runScreening());

async function runBatchScreening() {
  const apiKey = sanitizeApiKey($('api-key').value);
  if (!apiKey) {
    setStatus('screening', 'error', 'APIキーを入力して保存してください');
    return;
  }

  setStatus('screening', 'loading', '一覧の候補者カードを取得中...');
  $('batch-screening-btn').disabled = true;
  $('screening-result').style.display = 'none';

  let tab;
  try {
    [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  } catch (e) {
    setStatus('screening', 'error', 'タブを取得できませんでした');
    $('batch-screening-btn').disabled = false;
    return;
  }

  let batchData;
  try {
    batchData = await chrome.tabs.sendMessage(tab.id, { action: 'getBatchCandidates' });
  } catch (e) {
    setStatus('screening', 'error', '候補者カードを取得できませんでした。RDSの一覧画面で実行してください。');
    $('batch-screening-btn').disabled = false;
    return;
  }

  if (!batchData || !batchData.success || !batchData.cards || batchData.cards.length === 0) {
    setStatus('screening', 'error', '候補者カードが見つかりませんでした。画面を確認してください。');
    $('batch-screening-btn').disabled = false;
    return;
  }

  const count = batchData.cards.length;
  const chunks = Math.ceil(count / 80);

  const r = await chrome.storage.local.get(['screeningCriteria', 'gasSettings', 'currentPosition']);
  const criteria = r.screeningCriteria || {};
  const gas = r.gasSettings || {};
  const currentPosition = r.currentPosition || '';

  // ポジション要件をGASから取得（設定済みの場合）
  let posReq = '', companyCriteriaBatch = '';
  if (currentPosition) {
    const gasUrl = gas.positionUrl || gas.url || gas.dbUrl;
    if (gasUrl) {
      try {
        setStatus('screening', 'loading', 'ポジション要件を取得中...');
        const posRes = await fetch(gasUrl, {
          method: 'POST',
          body: JSON.stringify({ secret: gas.secret || 'snowwe2024', action: 'getPositionRequirements', position: currentPosition }),
        });
        const posData = await posRes.json();
        if (posData.ok && (posData.requirements || posData.companyCriteria)) {
          posReq = posData.requirements || '';
          companyCriteriaBatch = posData.companyCriteria || '';
        }
      } catch (_) {}
    }
  }

  setStatus('screening', 'loading', chunks > 1 ? `${count}人を${chunks}回に分けて判定中...` : `${count}人を判定中...`);

  try {
    const results = await runBatchScreeningAI(apiKey, batchData.cards, criteria, posReq, currentPosition, companyCriteriaBatch);
    await chrome.tabs.sendMessage(tab.id, { action: 'setBatchResults', results });

    const okCount = results.filter(r => r.overall === 'OK').length;
    const ngCount = results.filter(r => r.overall === 'NG').length;
    const warnCount = results.filter(r => r.overall === '要確認').length;

    setStatus('screening', 'success',
      `判定完了 ${count}人 — ✅${okCount}人 ⚠️${warnCount}人 ❌${ngCount}人`);
  } catch (e) {
    setStatus('screening', 'error', `判定エラー: ${e.message}`);
  }

  $('batch-screening-btn').disabled = false;
}

function buildStandardCriteria(ageIncome) {
  const ai = ageIncome || {};
  const v = (key, def) => ai[key] || def;
  return `【重要】以下の企業名・職歴に関するNG条件は、【候補者プロフィール】に記載されている候補者自身の実際の勤務先・経歴のみを見て判定すること。応募ポジションの依頼主企業名（【応募ポジション】セクション等に出てくる企業名）は候補者の職歴ではないため、絶対に判定材料にしないこと。
【ハードNG：以下は必ずNG（例外なし）】
- 職歴にアクセンチュアが含まれる → 即NG
- 職歴にベイカレントが含まれる → 即NG（例外：43歳以上かつ財務・経理・FP&A職歴あり → 要確認）
- 年収がプロフィールに明記されており、以下の閾値を下回る → 必ずNG（情報が明確な場合は「迷う」余地なし）。年収が幅（例：750〜1000万円）で記載されている場合は上限値で判断し、上限値が基準以上であればNGにしない。
  ・20代: ${v('age20s', 500)}万円未満
  ・30〜35歳: ${v('age30to35', 700)}万円未満
  ・36〜39歳: ${v('age36to39', 800)}万円未満
  ・40〜42歳: ${v('age40to42', 1000)}万円未満
  ・43〜45歳: ${v('age43to45', 1200)}万円未満
  ・46歳以上: ${v('age43to45', 1200)}万円以上かつ財務・経理・FP&A職歴があれば「要確認」、それ以外はNG

【要確認（ボーダーライン）】年収が閾値の+150万円以内
  ・43〜45歳: ${v('age43to45', 1200)}〜${v('age43to45', 1200)+150}万円
  ・40〜42歳: ${v('age40to42', 1000)}〜${v('age40to42', 1000)+100}万円
  ・36〜39歳: ${v('age36to39', 800)}〜${v('age36to39', 800)+100}万円
  ・30〜35歳: ${v('age30to35', 700)}〜${v('age30to35', 700)+100}万円

【その他の判定基準】
- 社格: 上場企業・大手グループ・知名度ある企業はOK。無名の零細企業のみNG。判断は現職のみで行い、過去の在籍企業の社格でNGにしない。
- 以下は必ずOKとして扱うこと：NTTグループ各社（NTT西日本・NTT東日本・NTTデータ・NTTコミュニケーションズ・NTTドコモ等）／JRグループ各社（JR東日本・JR西日本・JR東海・JR九州・JR北海道・JR四国等）／地域電力各社（東京電力・関西電力・中部電力・東北電力・九州電力・北海道電力・中国電力・四国電力・北陸電力等）／都市ガス会社（東京ガス・大阪ガス・東邦ガス・西部ガス等）／レバレジーズ（レバテック）・シフト
- 学歴: 国立大学・早慶上智・MARCHはOK。それ以外は社格・年収で補完されればOK
- 転職回数: 20代最大2社、30代最大3社、40代最大4社
- 不動産売買仲介・賃貸仲介の専業営業職、保険外交員専業のキャリアは「要確認」とする
- 年収が不明な場合・上記以外で迷う場合: OKとする`;
}

async function runBatchScreeningAI(apiKey, cards, criteria, posReq = '', positionName = '', companyCriteria = '') {
  apiKey = sanitizeApiKey(apiKey);
  const criteriaLines = buildCriteriaLines(criteria);
  const standardCriteria = buildStandardCriteria(criteria.ageIncome);
  const posSection = posReq ? `\n【応募ポジション：${positionName}（参考情報。必須スキル等との適合度はNG判定の根拠にしないこと）】\n${posReq.slice(0, 600)}\n` : '';
  const companySection = companyCriteria ? `\n【会社別採用基準（共通基準より優先）】\n${companyCriteria.slice(0, 600)}\n` : '';
  const CHUNK = 80; // 80人ずつ処理（出力トークン上限対策）

  const callChunk = async (chunk, offset) => {
    const candidateList = chunk.map((c, i) => {
      const age = c.age ? `${c.age}歳` : '';
      const income = c.incomeText ? `年収${c.incomeText}` : '';
      const meta = [age, income].filter(Boolean).join(' / ');
      return `候補者${offset + i + 1}: ${c.summary}${meta ? ` [${meta}]` : ''}`;
    }).join('\n');

    const prompt = `あなたは転職エージェントの一次選定アシスタントです。
${companySection}
以下の【選定基準】に照らして、各候補者を判定してください。
カード情報は概要のみです。年収・学歴など情報が読み取れない項目は「問題なし」として扱い、明確にNGと確認できる場合のみNGとしてください。迷う場合は必ずOKとしてください。
${posSection}
【選定基準】
${standardCriteria}
${criteriaLines ? '\n【追加条件】\n' + criteriaLines : ''}

【候補者一覧】
${candidateList}

各候補者について、判定理由（r）を15文字以内で簡潔に記述してください。NGの場合のみ、根拠となる候補者一覧本文からの引用（q）を12文字以内でそのまま書き写してください（要約・言い換え不可、OK/要確認の場合qは省略可）。
以下のJSON形式のみで出力してください（説明不要）:
{"results":[{"i":${offset + 1},"o":"OK","r":"理由"},{"i":${offset + 2},"o":"NG","r":"理由","q":"引用"}]}`;

    const data = await claudeFetch(apiKey, {
      model: 'claude-haiku-4-5-20251001',
      max_tokens: 4000,
      messages: [{ role: 'user', content: prompt }]
    });
    const text = (data.content?.[0]?.text || '').trim();
    const clean = text.replace(/```json|```/g, '').trim();
    const jsonMatch = clean.match(/\{[\s\S]*\}/);
    let parsed;
    try { parsed = JSON.parse(jsonMatch ? jsonMatch[0] : clean); } catch {
      const fallback = [...clean.matchAll(/"o"\s*:\s*"([^"]+)"/g)].map(m => m[1]);
      return chunk.map((_, i) => ({ overall: fallback[i] || '要確認', reason: '' }));
    }
    return (parsed.results || []).map((r, i) => {
      let overall = r.overall || r.o || '要確認';
      let reason = r.reason || r.r || '';
      const quote = r.quote || r.q || '';
      // NG判定の根拠引用(q)が、実際に候補者本人のカード概要に存在するかを機械的に検証する。
      // 見当たらない場合（応募ポジション欄の依頼主企業名や基準にない独自解釈との混同等）は
      // 根拠のない判定とみなし、要確認へ格下げする。
      const summary = chunk[i]?.summary || '';
      const normalize = s => s.replace(/\s+/g, '');
      if (overall === 'NG') {
        const grounded = quote && quote.length >= 3 && normalize(summary).includes(normalize(quote));
        if (!grounded) {
          overall = '要確認';
          reason = `[要確認:根拠不明] ${reason}`;
        }
      }
      return { overall, reason };
    });
  };

  const allResults = [];
  for (let i = 0; i < cards.length; i += CHUNK) {
    const chunk = cards.slice(i, i + CHUNK);
    const chunkResults = await callChunk(chunk, i);
    allResults.push(...chunkResults);
  }
  return allResults;
}

function buildCriteriaLines(criteria) {
  const lines = [];
  if (criteria.ageMin || criteria.ageMax) {
    const min = criteria.ageMin ? `${criteria.ageMin}歳以上` : '';
    const max = criteria.ageMax ? `${criteria.ageMax}歳以下` : '';
    lines.push(`- 年齢: ${[min, max].filter(Boolean).join('かつ')}`);
  }
  const tiers = (criteria.companyTiers || []).filter(t => t && t !== '不問');
  if (tiers.length > 0) {
    lines.push(`- 社格条件: 現職が${tiers.join('・')}のいずれかであること。いずれにも当てはまらない場合はNG`);
  }
  if (criteria.educationReq && criteria.educationReq !== '不問') {
    lines.push(`- 学歴条件: ${criteria.educationReq}を満たすこと`);
  }
  if (criteria.minTenure) lines.push(`- 在籍期間: 過去の全職歴を含め、${criteria.minTenure}年未満の在籍が明確に確認できる場合のみNG。在籍期間が不明・記載なしの場合はOKとして扱う`);
  if (criteria.requiredKeywords) lines.push(`- 必須経験: ${criteria.requiredKeywords}`);
  if (criteria.excludeCompanies) lines.push(`- 除外企業: 職歴に${criteria.excludeCompanies}のいずれかが含まれる場合は過去・現職問わず即NG`);
  if (criteria.excludeKeywords) lines.push(`- 除外: ${criteria.excludeKeywords}`);
  return lines.join('\n');
}

async function runAutoAdd() {
  const apiKey = sanitizeApiKey($('api-key').value);
  if (!apiKey) {
    setStatus('screening', 'error', 'APIキーを入力して保存してください');
    return;
  }
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return;
  $('auto-add-btn').disabled = true;
  setStatus('screening', 'loading', '🤖 自動リスト追加を開始します...');
  try {
    await chrome.tabs.sendMessage(tab.id, { action: 'triggerAutoAdd' });
    setStatus('screening', 'loading', '🤖 実行中です。ページ上で進捗を確認してください');
    setTimeout(() => { $('auto-add-btn').disabled = false; }, 3000);
  } catch (e) {
    setStatus('screening', 'error', '❌ エラー：一覧ページで実行してください');
    $('auto-add-btn').disabled = false;
  }
}

async function runScreening() {
  const apiKey = sanitizeApiKey($('api-key').value);
  if (!apiKey) {
    setStatus('screening', 'error', 'APIキーを入力して保存してください');
    return;
  }

  setStatus('screening', 'loading', 'プロフィールを取得中...');
  $('screening-btn').disabled = true;
  $('screening-result').style.display = 'none';
  $('screening-feedback').style.display = 'none';

  let tab;
  try {
    [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  } catch (e) {
    setStatus('screening', 'error', 'タブを取得できませんでした');
    $('screening-btn').disabled = false;
    return;
  }

  // 判定中バッジを表示
  chrome.tabs.sendMessage(tab.id, { action: 'showBadgeChecking' }).catch(() => {});

  let profileData;
  try {
    profileData = await getProfileSafe(tab);
  } catch (e) {
    setStatus('screening', 'error', 'プロフィールを取得できませんでした。ページを再読み込みして再度お試しください。');
    $('screening-btn').disabled = false;
    return;
  }

  if (!profileData || !profileData.success) {
    chrome.tabs.sendMessage(tab.id, { action: 'clearBadge' }).catch(() => {});
    if (profileData && profileData.needsCandidateSelection) {
      setStatus('screening', 'error', '👆 候補者カードをクリックして右パネルにプロフィールを表示してから実行してください');
    } else {
      setStatus('screening', 'error', 'プロフィール情報が取得できませんでした');
    }
    $('screening-btn').disabled = false;
    return;
  }

  const r = await chrome.storage.local.get(['screeningCriteria', 'gasSettings', 'currentPosition']);
  const criteria = r.screeningCriteria || {};
  const gas = r.gasSettings || {};
  const currentPosition = r.currentPosition || '';
  let posReq = '', companyCriteriaScreen = '';
  if (currentPosition) {
    const gasUrl = gas.positionUrl || gas.url || gas.dbUrl;
    if (gasUrl) {
      try {
        const posRes = await fetch(gasUrl, {
          method: 'POST',
          body: JSON.stringify({ secret: gas.secret || 'snowwe2024', action: 'getPositionRequirements', position: currentPosition }),
        });
        const posData = await posRes.json();
        if (posData.ok && (posData.requirements || posData.companyCriteria)) {
          posReq = posData.requirements || '';
          companyCriteriaScreen = posData.companyCriteria || '';
        }
      } catch (_) {}
    }
  }

  setStatus('screening', 'loading', '選定基準と照合中...');

  try {
    const result = await runScreeningAI(apiKey, profileData.profileText, criteria, posReq, currentPosition, companyCriteriaScreen);
    renderScreeningResult(result);
    $('screening-result').style.display = 'block';

    // 結果バッジをカードに表示（訂正ボタン用にprofileSummary/reasonも渡す）
    const profileSummary = profileData.profileText
      .split('\n').map(l => l.trim()).filter(Boolean).slice(0, 12).join(' / ').substring(0, 200);
    chrome.tabs.sendMessage(tab.id, {
      action: 'showBadgeResult',
      overall: result.overall,
      reason: result.comment || '',
      profileSummary,
    }).catch(() => {});

    // ポップアップ側にも訂正ボタンを表示（doda-x等、ページ遷移でオンページの
    // バッジが消えて訂正できなくなる媒体でも、ここから確実に記録できるようにする）
    renderFeedbackButtons(result.overall, profileSummary, platformFromHostname(profileData.hostname));

    const overall = result.overall;
    if (overall === 'OK') {
      setStatus('screening', 'success', '判定完了 — 基準をクリアしています');
    } else if (overall === 'NG') {
      setStatus('screening', 'error', '判定完了 — 基準を満たしていません');
    } else {
      setStatus('screening', 'idle', '判定完了 — 要確認項目があります');
    }
  } catch (e) {
    chrome.tabs.sendMessage(tab.id, { action: 'clearBadge' }).catch(() => {});
    setStatus('screening', 'error', `判定エラー: ${e.message}`);
  }

  $('screening-btn').disabled = false;
}

async function runScreeningAI(apiKey, profileText, criteria, posReq = '', positionName = '', companyCriteria = '') {
  apiKey = sanitizeApiKey(apiKey);
  const criteriaText = buildCriteriaLines(criteria);
  const posSection = posReq ? `\n【応募ポジション：${positionName}（参考情報。必須スキル等との適合度はNG判定の根拠にしないこと）】\n${posReq.slice(0, 600)}\n` : '';
  const companySection = companyCriteria ? `\n【会社別採用基準（共通基準より優先）】\n${companyCriteria.slice(0, 600)}\n` : '';

  // 年齢はAIの自由読解に任せると誤読・誤比較が起きるため、コード側で確実に抽出して明示する
  const ageMatch = profileText.match(/(\d{2,3})歳/);
  const ageNote = ageMatch
    ? `\n【候補者の年齢（自動抽出・正）】${ageMatch[1]}歳 ※年齢条件の判定は必ずこの数値を使うこと。プロフィール本文中の勤続年数・経験年数・西暦等、他の数字と混同しないこと。`
    : '';

  const prompt = `あなたは転職エージェントの一次選定アシスタントです。
${companySection}
以下の【選定基準】と【候補者プロフィール】を照合し、各基準について候補者がクリアしているかを判定してください。
プロフィールに情報が記載されていない項目は「情報なし」として扱ってください。
${posSection}
【選定基準】
${buildStandardCriteria(criteria.ageIncome)}
${criteriaText ? '\n【追加条件】\n' + criteriaText : ''}
${ageNote}
【候補者プロフィール】
${profileText}

以下のJSON形式のみで出力してください（説明・前置き不要）:
{
  "candidate": {
    "age": "プロフィールから読み取った年齢（例: 43歳）。不明な場合は空文字",
    "income": "現在年収（例: 1100〜1200万円）。不明な場合は空文字",
    "current_company": "直近の在籍企業名。不明な場合は空文字",
    "education": "最終学歴の学校名。不明な場合は空文字",
    "experience_years": "社会人経験年数（例: 約15年）。不明な場合は空文字"
  },
  "overall": "OK" | "NG" | "要確認",
  "criteria": [
    {
      "name": "判定項目名",
      "result": "OK" | "NG" | "情報なし",
      "detail": "判定根拠を1文で（プロフィールから読み取れた具体的な情報を含める）",
      "quote": "resultがNGの場合、根拠となる【候補者プロフィール】本文からの引用を20字以内でそのまま書き写す（要約・言い換え・応募ポジション欄からの引用は不可）。それ以外は空文字"
    }
  ],
  "comment": "総合的なコメントを2〜3文で。スカウトを打つべきかどうかの所見を含める。"
}`;

  const data = await claudeFetch(apiKey, {
    model: 'claude-haiku-4-5-20251001',
    max_tokens: 800,
    messages: [{ role: 'user', content: prompt }]
  });
  const text = (data.content?.[0]?.text || '').trim();
  const clean = text.replace(/```json|```/g, '').trim();
  const jsonMatch = clean.match(/\{[\s\S]*\}/);
  let parsed;
  try { parsed = JSON.parse(jsonMatch ? jsonMatch[0] : clean); } catch {
    throw new Error('JSON解析エラー（AIの応答形式が不正）: ' + clean.substring(0, 100));
  }

  // NG判定した各criteria項目のquote（根拠引用）が、実際に候補者プロフィール本文に
  // 存在するかを機械的に検証する。NG項目が1つ以上あるのに、いずれのquoteも本文に
  // 見当たらない場合は根拠のない判定（応募ポジション欄との混同・基準にない独自解釈等）
  // とみなし、要確認へ格下げする。
  if (parsed.overall === 'NG') {
    const normalize = s => s.replace(/\s+/g, '');
    const normProfile = normalize(profileText);
    const ngCriteria = (parsed.criteria || []).filter(c => c.result === 'NG');
    const hasGroundedNG = ngCriteria.some(c => c.quote && c.quote.length >= 3 && normProfile.includes(normalize(c.quote)));
    if (ngCriteria.length > 0 && !hasGroundedNG) {
      console.warn('[Snow-we] NG判定の根拠引用が候補者プロフィールに見当たらない → 要確認に修正:', ngCriteria);
      parsed.overall = '要確認';
      parsed.comment = `[要確認: NG判定の根拠となる引用が候補者プロフィールに見当たりません] ${parsed.comment || ''}`;
    }
  }

  return parsed;
}

function renderScreeningResult(result) {
  // 候補者サマリーカード
  const card = $('candidate-card');
  const c = result.candidate || {};
  const fields = [
    { name: '年齢',   value: c.age },
    { name: '年収',   value: c.income },
    { name: '直近',   value: c.current_company },
    { name: '学歴',   value: c.education },
    { name: '経験',   value: c.experience_years },
  ].filter(f => f.name);

  card.innerHTML = `
    <div class="candidate-card">
      <div class="candidate-card-label">📋 AIが読み取った候補者情報</div>
      <div class="candidate-fields">
        ${fields.map(f => `
          <div class="candidate-field">
            <span class="candidate-field-name">${escapeHtml(f.name)}</span>
            <span class="candidate-field-value ${f.value ? '' : 'unknown'}">${f.value ? escapeHtml(f.value) : '情報なし'}</span>
          </div>
        `).join('')}
      </div>
    </div>
  `;

  // 総合判定バッジ
  const badgeWrap = $('overall-badge-wrap');
  const overall = result.overall || '要確認';
  const criteria = result.criteria || [];
  const okCount = criteria.filter(c => c.result === 'OK').length;
  const totalCount = criteria.filter(c => c.result !== '情報なし').length;
  const pct = totalCount > 0 ? Math.round((okCount / totalCount) * 100) : 0;

  const bannerClass = overall === 'OK' ? 'ok' : overall === 'NG' ? 'ng' : 'warn';
  const bannerIcon = overall === 'OK' ? '🟢' : overall === 'NG' ? '🔴' : '🟡';
  const verdictText = overall === 'OK' ? 'スカウト推奨' : overall === 'NG' ? 'スカウト見送り' : '要確認';

  badgeWrap.innerHTML = `
    <div class="overall-banner ${bannerClass}">
      <div class="overall-icon">${bannerIcon}</div>
      <div class="overall-text">
        <div class="overall-label">総合判定</div>
        <div class="overall-verdict">${verdictText}</div>
        <div class="overall-score">${okCount} / ${criteria.length} 項目クリア</div>
      </div>
    </div>
    <div class="score-bar-wrap">
      <div class="score-bar-track">
        <div class="score-bar-fill ${bannerClass}" style="width:${pct}%"></div>
      </div>
    </div>
  `;

  // 各基準（NG → 情報なし → OK の順に並べて視認性を上げる）
  const sorted = [...criteria].sort((a, b) => {
    const order = { 'NG': 0, '情報なし': 1, 'OK': 2 };
    return (order[a.result] ?? 1) - (order[b.result] ?? 1);
  });

  const list = $('criteria-list');
  list.innerHTML = '';
  sorted.forEach(c => {
    const rowClass = c.result === 'OK' ? 'ok' : c.result === 'NG' ? 'ng' : 'skip';
    const icon = c.result === 'OK' ? '✅' : c.result === 'NG' ? '❌' : '—';
    const row = document.createElement('div');
    row.className = `criterion-row ${rowClass}`;
    row.innerHTML = `
      <span class="criterion-icon">${icon}</span>
      <div class="criterion-body">
        <div class="criterion-name">${escapeHtml(c.name || '')}</div>
        <div class="criterion-detail">${escapeHtml(c.detail || '')}</div>
      </div>
    `;
    list.appendChild(row);
  });

  // コメント
  $('screening-comment').textContent = result.comment || '';
}

// ============================================================
// APIキー接続テスト
// ============================================================
$('api-test-btn').addEventListener('click', async () => {
  const apiKey = sanitizeApiKey($('api-key').value);
  const resultEl = $('api-test-result');
  resultEl.style.display = 'block';
  resultEl.style.color = '#2c2c2a';
  resultEl.textContent = '接続中...';

  if (!apiKey) {
    resultEl.textContent = '❌ APIキーが入力されていません';
    return;
  }

  resultEl.textContent = `送信キー: "${apiKey.substring(0, 12)}..." (${apiKey.length}文字)`;

  try {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true'
      },
      body: JSON.stringify({
        model: 'claude-haiku-4-5-20251001',
        max_tokens: 10,
        messages: [{ role: 'user', content: 'hi' }]
      })
    });

    const data = await response.json();
    if (response.ok) {
      resultEl.textContent = `✅ 接続成功！`;
      resultEl.style.color = '#085041';
    } else {
      resultEl.textContent = `❌ ${response.status}: ${JSON.stringify(data.error || data)}`;
      resultEl.style.color = '#b91c1c';
    }
  } catch (e) {
    resultEl.textContent = `❌ 通信エラー: ${e.message}`;
    resultEl.style.color = '#b91c1c';
  }
});

// ============================================================
// チーム設定コード（生成・適用）
// ============================================================
$('generate-setup-code-btn').addEventListener('click', () => {
  const data = {
    url: $('gas-url').value.trim(),
    dbUrl: $('gas-db-url').value.trim(),
    secret: $('gas-secret').value.trim(),
    positionUrl: $('position-gas-url').value.trim(),
    recruiter: $('gas-recruiter').value.trim(),
  };
  const msg = $('setup-code-msg');
  const showMsg = (text, color) => { msg.textContent = text; msg.style.color = color; msg.style.display = 'block'; };
  if (!data.url && !data.dbUrl) {
    showMsg('❌ GAS URLが入力されていません', '#b91c1c');
    return;
  }
  try {
    const encoded = btoa(encodeURIComponent(JSON.stringify(data)));
    $('setup-code-input').value = 'snow1:' + encoded;
    showMsg('✅ コードを生成しました。コピーしてSlackで共有してください', '#085041');
  } catch (e) {
    showMsg('❌ 生成エラー: ' + e.message, '#b91c1c');
  }
});

$('apply-setup-code-btn').addEventListener('click', () => {
  const code = $('setup-code-input').value.trim();
  const msg = $('setup-code-msg');
  const showMsg = (text, color) => { msg.textContent = text; msg.style.color = color; msg.style.display = 'block'; };
  if (!code) {
    showMsg('❌ コードを入力してください', '#b91c1c');
    return;
  }
  if (!code.startsWith('snow1:')) {
    showMsg('❌ 無効なコードです（snow1: で始まる必要があります）', '#b91c1c');
    return;
  }
  try {
    const data = JSON.parse(decodeURIComponent(atob(code.slice(6))));
    if (data.url)         $('gas-url').value = data.url;
    if (data.dbUrl)       $('gas-db-url').value = data.dbUrl;
    if (data.secret)      $('gas-secret').value = data.secret;
    if (data.positionUrl) $('position-gas-url').value = data.positionUrl;
    if (data.recruiter)   $('gas-recruiter').value = data.recruiter;
    showMsg('✅ 適用しました！「設定を保存」を押して確定してください', '#085041');
  } catch (e) {
    showMsg('❌ コードの解析に失敗しました: ' + e.message, '#b91c1c');
  }
});

// ============================================================
// デバッグ
// ============================================================
$('debug-btn').addEventListener('click', async () => {
  setStatus('generate', 'loading', 'DOM情報を取得中...');
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const result = await chrome.tabs.sendMessage(tab.id, { action: 'debugDOM' });
    if (result && result.success) {
      const info = result.info;
      const msg = [
        `URL: ${info.url}`,
        `詳細パネル検出: ${info.detailPanelFound ? '✅ 成功' : '❌ 失敗'}`,
        `セレクターヒット数:`,
        ...Object.entries(info.selectorHits).map(([k,v]) => `  ${k}: ${v}件`),
        `見出し: ${info.headings.join(' / ') || 'なし'}`,
        `取得テキスト冒頭: ${info.previewText}`
      ].join('\n');
      $('debug-output').textContent = msg;
      $('debug-section').style.display = 'block';
      setStatus('generate', 'idle', 'デバッグ情報を取得しました（下記参照）');
    }
  } catch (e) {
    setStatus('generate', 'error', `エラー: ${e.message}`);
  }
});

// ============================================================
// タブ4: 履歴
// ============================================================
const SCOUT_KEY = 'scoutHistory';

async function loadHistory() {
  const r = await chrome.storage.local.get([SCOUT_KEY]);
  return r[SCOUT_KEY] || {};
}

async function saveHistory(history) {
  await chrome.storage.local.set({ [SCOUT_KEY]: history });
}

async function renderHistory() {
  const history = await loadHistory();
  const entries = Object.entries(history);
  const now = Date.now();
  const day = 1000 * 60 * 60 * 24;

  const recentCount = entries.filter(([, v]) => (now - (v.date || 0)) < 30 * day).length;
  const rescoutableCount = entries.filter(([, v]) => (now - (v.date || 0)) >= 90 * day).length;

  $('history-total').textContent = entries.length;
  $('history-recent').textContent = recentCount;
  $('history-rescoutable').textContent = rescoutableCount;
  $('history-count-label').textContent = `${entries.length}件のスカウト記録`;

  const list = $('history-list');
  if (entries.length === 0) {
    list.innerHTML = '<div style="padding:20px; text-align:center; color:#aaa; font-size:12px;">スカウト履歴なし</div>';
    return;
  }

  // Sort by date descending
  entries.sort((a, b) => (b[1].date || 0) - (a[1].date || 0));

  list.innerHTML = entries.slice(0, 200).map(([id, v]) => {
    const daysAgo = Math.floor((now - (v.date || 0)) / day);
    const rescoutable = daysAgo >= 90;
    const dateStr = v.date ? new Date(v.date).toLocaleDateString('ja-JP', { month: 'numeric', day: 'numeric', year: '2-digit' }) : '不明';
    const company = v.company || id.split('/').pop() || '不明';
    const platform = v.platform || 'unknown';
    const platformLabel = { bizreach: 'BR', rds: 'RDS', dodax: 'DX', ambi: 'AMBI', green: 'Green', mynavi: 'MY' }[platform] || platform;
    const ageStr = v.age ? ` · ${v.age}` : '';
    const univStr = v.univ ? ` · ${v.univ}` : '';
    const recruiterStr = v.recruiter ? ` · ${v.recruiter}` : '';
    const unsentBadge = v.gasSent === false ? `<span style="font-size:9px; padding:1px 5px; border-radius:8px; background:#FEF3C7; color:#D97706; margin-left:4px; flex-shrink:0;">未送信</span>` : '';
    const posStr = v.position ? `<div class="history-item-pos">${escapeHtml(v.position)}</div>` : '';
    const replyHtml = v.replied
      ? `<span class="reply-tag">💬 返信あり</span>`
      : `<button class="reply-btn" data-id="${escapeHtml(id)}">返信あり</button>`;

    return `<div class="history-item">
      <span class="history-item-platform">${platformLabel}</span>
      <div class="history-item-body">
        <div class="history-item-company" style="display:flex; align-items:center;">${escapeHtml(company)}${unsentBadge}</div>
        ${posStr}
        <div class="history-item-meta">${dateStr}${ageStr}${univStr}${recruiterStr}</div>
      </div>
      ${replyHtml}
      <span class="history-item-days ${rescoutable ? 'rescoutable' : 'recent'}">${daysAgo}日前${rescoutable ? ' ↩' : ''}</span>
    </div>`;
  }).join('');

  // 返信ありボタンのイベント
  list.querySelectorAll('.reply-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.id;
      const h = await loadHistory();
      if (!h[id]) return;
      h[id].replied = true;
      h[id].repliedDate = Date.now();
      await saveHistory(h);

      // GASにも送信（設定済みの場合）
      try {
        const r = await chrome.storage.local.get(['gasSettings', 'screeningCriteria']);
        const gas = r.gasSettings || {};
        const replyGasUrl = gas.url || gas.dbUrl;
        if (replyGasUrl) {
          await fetch(replyGasUrl, {
            method: 'POST',
            body: JSON.stringify({
              secret: gas.secret || 'snowwe2024',
              action: 'recordReply',
              recruiter: gas.recruiter || '',
              company: h[id].company || '',
              platform: h[id].platform || '',
              sentDate: h[id].date || 0,
              repliedDate: h[id].repliedDate,
            }),
          });
        }
      } catch (_) {}

      await renderHistory();
    });
  });
}

function escapeHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ============================================================
// 承認待ちリスト（AIが星をつけた候補者の人間レビュー画面）
// ============================================================
const PLATFORM_LABELS = { bizreach: 'Bizreach', rds: 'RDS', dodax: 'Doda X', ambi: 'AMBI', green: 'Green', mynavi: 'Mynavi' };

async function fetchPendingScoutQueue() {
  const res = await fetch(
    `${SUPABASE_URL}/rest/v1/scout_queue?status=eq.pending_review&order=created_at.desc&limit=100`,
    { headers: { apikey: SUPABASE_KEY, Authorization: `Bearer ${SUPABASE_KEY}` } }
  );
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function updateScoutQueueEntry(id, patch) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/scout_queue?id=eq.${id}`, {
    method: 'PATCH',
    headers: {
      apikey: SUPABASE_KEY,
      Authorization: `Bearer ${SUPABASE_KEY}`,
      'Content-Type': 'application/json',
      Prefer: 'return=minimal',
    },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(await res.text());
}

async function renderApprovalQueue() {
  const listEl = $('approval-list');
  const countEl = $('approval-count-label');
  listEl.innerHTML = '<div style="padding:20px; text-align:center; color:#aaa; font-size:12px;">読み込み中...</div>';

  let rows, positions;
  try {
    [rows, positions] = await Promise.all([
      fetchPendingScoutQueue(),
      chrome.runtime.sendMessage({ type: 'getPositionList' }).then(r => r?.positions || []).catch(() => []),
    ]);
  } catch (e) {
    listEl.innerHTML = `<div style="padding:20px; text-align:center; color:#A32D2D; font-size:12px;">読み込み失敗: ${escapeHtml(e.message || '')}</div>`;
    countEl.textContent = '';
    return;
  }

  countEl.textContent = `${rows.length}件が承認待ち`;
  if (rows.length === 0) {
    listEl.innerHTML = '<div style="padding:20px; text-align:center; color:#aaa; font-size:12px;">承認待ちの候補者はいません</div>';
    return;
  }

  listEl.innerHTML = rows.map(row => {
    const platformLabel = PLATFORM_LABELS[row.platform] || row.platform;
    const metaParts = [row.age, row.company, row.univ].filter(Boolean);
    const posOptions = positions.length > 0 ? positions : (row.position ? [row.position] : []);
    const optionsHtml = posOptions.map(p =>
      `<option value="${escapeHtml(p)}"${p === row.position ? ' selected' : ''}>${escapeHtml(p)}</option>`
    ).join('');
    // プルダウンは幅の都合で長いポジション名が省略されて見えなくなることがあるため、
    // 選択中のポジション名を上に全文表示する（プルダウンを変更すると更新される）
    const roomLinkHtml = row.room_url
      ? `<a class="approval-card-room-link" href="${escapeHtml(row.room_url)}" target="_blank" rel="noopener">🔗 検討中リストを開く（本人を探して確認）</a>`
      : '';
    return `<div class="approval-card" data-id="${row.id}">
      <div class="approval-card-top">
        <span class="approval-card-platform">${escapeHtml(platformLabel)}</span>
        <span class="approval-card-meta">${escapeHtml(metaParts.join(' · ') || '情報なし')}</span>
      </div>
      ${row.ai_reason ? `<div class="approval-card-reason">🤖 ${escapeHtml(row.ai_reason)}</div>` : ''}
      ${roomLinkHtml}
      <div class="approval-card-position-label">送信ポジション: ${escapeHtml(row.position || '（未設定）')}</div>
      <select class="approval-position-select">${optionsHtml || '<option value="">（ポジション一覧未取得）</option>'}</select>
      <div class="approval-card-actions">
        <button class="approve-btn" data-action="approve">✅ 承認</button>
        <button class="reject-btn" data-action="reject">❌ 却下</button>
      </div>
    </div>`;
  }).join('');

  listEl.querySelectorAll('.approval-card').forEach(card => {
    const id = card.dataset.id;
    const select = card.querySelector('.approval-position-select');
    const positionLabel = card.querySelector('.approval-card-position-label');
    select.addEventListener('change', () => {
      positionLabel.textContent = `送信ポジション: ${select.value || '（未設定）'}`;
    });
    card.querySelector('[data-action="approve"]').addEventListener('click', async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      try {
        await updateScoutQueueEntry(id, { status: 'approved', position: select.value, reviewed_at: new Date().toISOString() });
        card.remove();
        countEl.textContent = `${listEl.querySelectorAll('.approval-card').length}件が承認待ち`;
      } catch (err) {
        btn.disabled = false;
        alert('承認処理に失敗しました: ' + (err.message || ''));
      }
    });
    card.querySelector('[data-action="reject"]').addEventListener('click', async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      try {
        await updateScoutQueueEntry(id, { status: 'rejected', reviewed_at: new Date().toISOString() });
        card.remove();
        countEl.textContent = `${listEl.querySelectorAll('.approval-card').length}件が承認待ち`;
      } catch (err) {
        btn.disabled = false;
        alert('却下処理に失敗しました: ' + (err.message || ''));
      }
    });
  });
}

$('approval-refresh-btn').addEventListener('click', renderApprovalQueue);

// CSVエクスポート
$('history-export-btn').addEventListener('click', async () => {
  const history = await loadHistory();
  const entries = Object.entries(history);
  if (entries.length === 0) {
    showHistoryMsg('履歴がありません', '#888');
    return;
  }

  entries.sort((a, b) => (b[1].date || 0) - (a[1].date || 0));

  const headers = ['送信日時', '会社名', '年齢', '大学', 'ポジション名', '業界', '媒体', '返信', '候補者ID'];
  const rows = entries.map(([id, v]) => {
    const dateStr = v.date ? new Date(v.date).toLocaleString('ja-JP') : '';
    return [dateStr, v.company || '', v.age || '', v.univ || '', v.position || '', v.industry || '', v.platform || '', v.replied ? '返信あり' : '', id]
      .map(c => `"${String(c).replace(/"/g, '""')}"`).join(',');
  });

  const csv = '﻿' + [headers.join(','), ...rows].join('\r\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `scout_history_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
  showHistoryMsg(`${entries.length}件をエクスポートしました`, '#085041');
});

// CSVインポートボタン
$('history-import-btn').addEventListener('click', () => {
  $('history-import-hint').style.display = 'block';
  $('history-import-file').click();
});

$('history-import-file').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const text = await file.text();
  const lines = text.replace(/\r/g, '').split('\n').filter(l => l.trim());
  if (lines.length === 0) { showHistoryMsg('CSVが空です', '#b91c1c'); return; }

  // Detect header row (contains any Japanese header keyword)
  const headerKeywords = ['送信日時', '会社名', '年齢', '媒体', 'date', 'company', 'platform'];
  let startLine = 0;
  if (headerKeywords.some(k => lines[0].toLowerCase().includes(k.toLowerCase()))) startLine = 1;

  const history = await loadHistory();
  let imported = 0;
  let skipped = 0;

  for (let i = startLine; i < lines.length; i++) {
    const cols = parseCSVLine(lines[i]);
    if (cols.length < 2) { skipped++; continue; }

    // Support two formats:
    // Format A (extension new): 送信日時, 会社名, 年齢, 大学, ポジション名, 業界, 媒体, 返信, 候補者ID
    // Format B (extension old): 送信日時, 会社名, 年齢, 媒体, 候補者ID
    // Format C (Excel export):  送信日時, 会社名, 年齢, 媒体, ポジション名, 業界
    const dateRaw = cols[0] || '';
    const company = cols[1] || '';
    const age = cols[2] || '';
    // detect new format by checking if col[3] looks like a university/blank (not a platform name)
    const platformKeywords = ['bizreach', 'br', 'rds', 'dodax', 'doda', 'ambi', 'green', 'mynavi', 'my', 'bireach'];
    const col3 = (cols[3] || '').toLowerCase();
    const isNewFormat = cols.length >= 7 && !platformKeywords.includes(col3);
    let univ = '', position = '', industry = '', platform = '', candidateIdCol = '', replied = false;
    if (isNewFormat) {
      univ = cols[3] || '';
      position = cols[4] || '';
      industry = cols[5] || '';
      platform = cols[6] || '';
      replied = (cols[7] || '') === '返信あり';
      candidateIdCol = cols[8] || '';
    } else {
      platform = cols[3] || '';
      candidateIdCol = cols[4] || '';
      position = cols[5] || '';
      industry = cols[6] || '';
    }

    const dateVal = parseJapaneseDate(dateRaw);

    let candidateId;
    if (candidateIdCol.startsWith('http') || candidateIdCol.includes('/') || candidateIdCol.startsWith('import_') || candidateIdCol.startsWith('manual_')) {
      candidateId = candidateIdCol.replace(/[?#].*$/, '');
    } else {
      const dateKey = dateVal ? new Date(dateVal).toISOString().slice(0, 10) : 'unknown';
      candidateId = `import_${dateKey}_${company.replace(/\s/g, '_')}`;
    }

    if (history[candidateId]) { skipped++; continue; }

    history[candidateId] = {
      date: dateVal || Date.now(),
      company,
      age,
      univ,
      position,
      industry,
      platform: normalizePlatform(platform),
      name: '',
      ...(replied ? { replied: true } : {}),
    };
    imported++;
  }

  await saveHistory(history);
  await renderHistory();
  showHistoryMsg(`${imported}件をインポート（${skipped}件スキップ）`, imported > 0 ? '#085041' : '#888');
  e.target.value = '';
});

function parseCSVLine(line) {
  const result = [];
  let cur = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') { cur += '"'; i++; }
      else inQuotes = !inQuotes;
    } else if (ch === ',' && !inQuotes) {
      result.push(cur.trim()); cur = '';
    } else {
      cur += ch;
    }
  }
  result.push(cur.trim());
  return result;
}

function parseJapaneseDate(s) {
  if (!s) return null;
  // Try ISO format first
  const d = new Date(s);
  if (!isNaN(d.getTime())) return d.getTime();
  // Japanese format: 2024/5/1, 2024年5月1日
  const m = s.match(/(\d{4})[\/\-年](\d{1,2})[\/\-月](\d{1,2})/);
  if (m) return new Date(parseInt(m[1]), parseInt(m[2]) - 1, parseInt(m[3])).getTime();
  return null;
}

function normalizePlatform(s) {
  const map = {
    'ビズリーチ': 'bizreach', 'bizreach': 'bizreach', 'br': 'bizreach',
    'リクナビ': 'rds', 'rds': 'rds', 'hrtech': 'rds',
    'doda': 'dodax', 'dodax': 'dodax', 'doda-x': 'dodax', 'doda x': 'dodax', 'x.doda': 'dodax',
    'ambi': 'ambi',
    'green': 'green', 'グリーン': 'green',
    'マイナビ': 'mynavi', 'mynavi': 'mynavi',
  };
  return map[(s || '').toLowerCase()] || s || 'unknown';
}

// 手動追加
$('history-manual-btn').addEventListener('click', () => {
  const form = $('history-manual-form');
  form.style.display = form.style.display === 'none' ? 'block' : 'none';
  if (form.style.display === 'block') {
    const today = new Date().toISOString().slice(0, 10);
    $('manual-date').value = today;
    $('manual-company').focus();
  }
});
$('manual-cancel-btn').addEventListener('click', () => {
  $('history-manual-form').style.display = 'none';
});
$('manual-save-btn').addEventListener('click', async () => {
  const company = $('manual-company').value.trim();
  if (!company) { showHistoryMsg('会社名は必須です', '#b91c1c'); return; }
  const age = $('manual-age').value.trim();
  const univ = $('manual-univ').value.trim();
  const position = $('manual-position').value.trim();
  const platform = $('manual-platform').value;
  const dateVal = $('manual-date').value ? new Date($('manual-date').value).getTime() : Date.now();
  const dateKey = new Date(dateVal).toISOString().slice(0, 10);
  const candidateId = `manual_${dateKey}_${company.replace(/\s/g, '_')}_${Date.now() % 10000}`;
  const history = await loadHistory();
  history[candidateId] = { date: dateVal, platform, name: '', company, age, univ, position, industry: '' };
  await saveHistory(history);
  $('history-manual-form').style.display = 'none';
  $('manual-company').value = '';
  $('manual-age').value = '';
  $('manual-univ').value = '';
  $('manual-position').value = '';
  await renderHistory();
  showHistoryMsg('手動追加しました', '#085041');
});

// 未送信をGASに再送
$('history-resend-btn').addEventListener('click', async () => {
  const r = await chrome.storage.local.get(['gasSettings', 'screeningCriteria']);
  const gas = r.gasSettings || {};
  const gasUrl = gas.url || gas.dbUrl;
  if (!gasUrl || !gas.recruiter) {
    showHistoryMsg('GAS URLまたは担当者名が未設定です（設定タブを確認）', '#b91c1c'); return;
  }
  const history = await loadHistory();
  // gasSent === false のもののみ（undefined/true は送信済みとみなす）
  const unsent = Object.entries(history).filter(([, v]) => v.gasSent === false && v.company && v.date);
  if (unsent.length === 0) {
    showHistoryMsg('未送信の記録はありません', '#888'); return;
  }
  showHistoryMsg(`${unsent.length}件を再送中...`, '#D97706');
  let success = 0;
  for (const [id, v] of unsent) {
    const payload = {
      secret: gas.secret || 'snowwe2024',
      recruiter: gas.recruiter,
      company: v.company || '',
      age: (v.age || '').replace(/[歳才]/, ''),
      univ: v.univ || '',
      media: v.platform || '',
      position: v.position || '',
      industry: v.industry || '',
      ts: v.date,
    };
    try {
      const res = await fetch(gasUrl, { method: 'POST', body: JSON.stringify(payload) });
      const json = await res.json();
      if (json.ok) { history[id].gasSent = true; success++; }
    } catch (_) {}
    if (gas.dbUrl && gas.dbUrl !== gasUrl) {
      try { await fetch(gas.dbUrl, { method: 'POST', body: JSON.stringify(payload) }); } catch (_) {}
    }
  }
  await saveHistory(history);
  await renderHistory();
  showHistoryMsg(`${success}/${unsent.length}件をGASに送信しました`, success > 0 ? '#085041' : '#b91c1c');
});

// チーム履歴同期
$('history-sync-btn').addEventListener('click', async () => {
  showHistoryMsg('GASから同期中...', '#4338CA');
  let r2 = {};
  try { r2 = await chrome.storage.local.get(['gasSettings']); } catch (_) {}
  const gas = r2.gasSettings || {};
  if (!gas.url && !gas.dbUrl) {
    showHistoryMsg('GAS URLが設定されていません（設定タブを確認）', '#b91c1c'); return;
  }
  try {
    const res = await fetch(gas.url || gas.dbUrl, {
      method: 'POST',
      body: JSON.stringify({ secret: gas.secret || 'snowwe2024', action: 'getTeamHistory', days: 180 }),
    });
    const json = await res.json();
    if (!json.ok) throw new Error('GAS error');
    const records = json.records || [];
    const history = await loadHistory();
    let added = 0;
    const mediaNorm = { 'ビズリーチ': 'bizreach', 'RDS': 'rds', 'doda X': 'dodax', 'AMBI': 'ambi', 'Green': 'green', 'マイナビ': 'mynavi' };
    for (const rec of records) {
      const dateKey = rec.date ? new Date(rec.date).toISOString().slice(0, 10) : 'unknown';
      const candidateId = `team_${dateKey}_${(rec.company || '').replace(/\s/g, '_')}_${rec.recruiter || ''}`;
      if (history[candidateId]) continue;
      history[candidateId] = {
        date: rec.date || Date.now(),
        platform: mediaNorm[rec.platform] || rec.platform || 'unknown',
        name: '',
        company: rec.company || '',
        age: rec.age || '',
        univ: rec.univ || '',
        position: rec.position || '',
        industry: '',
        recruiter: rec.recruiter || '',
      };
      added++;
    }
    await saveHistory(history);
    await renderHistory();
    showHistoryMsg(`同期完了：${added}件追加（計${records.length}件取得）`, '#085041');
  } catch (e) {
    showHistoryMsg('同期失敗: ' + e.message, '#b91c1c');
  }
});

// 履歴クリア
$('history-clear-btn').addEventListener('click', async () => {
  if (!confirm('スカウト履歴をすべて削除しますか？この操作は取り消せません。')) return;
  await chrome.storage.local.remove([SCOUT_KEY]);
  await renderHistory();
  showHistoryMsg('履歴をクリアしました', '#888');
});

function showHistoryMsg(msg, color) {
  const el = $('history-msg');
  el.textContent = msg;
  el.style.color = color || '#2c2c2a';
  el.style.display = 'block';
  setTimeout(() => { el.style.display = 'none'; }, 3000);
}

// ============================================================
// ユーティリティ
// ============================================================
function setStatus(tab, type, message) {
  const idMap = { generate: 'status', suggest: 'suggest-status', screening: 'screening-status' };
  const el = $(idMap[tab] || 'status');
  if (!el) return;
  el.className = `status ${type}`;
  if (type === 'loading') {
    el.innerHTML = `<div class="spinner"></div>${message}`;
  } else {
    el.textContent = message;
  }
}
