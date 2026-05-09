// popup.js v1.12.0

const $ = id => document.getElementById(id);

// ============================================================
// 初期化
// ============================================================
document.addEventListener('DOMContentLoaded', async () => {
  const result = await chrome.storage.local.get(['apiKey']);
  if (result.apiKey) $('api-key').value = result.apiKey;

  // タブ切り替え
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      $(`tab-${btn.dataset.tab}`).classList.add('active');
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
  const r = await chrome.storage.local.get(['screeningCriteria']);
  const c = r.screeningCriteria || {};

  if (c.ageMin) $('age-min').value = c.ageMin;
  if (c.ageMax) $('age-max').value = c.ageMax;
  if (c.incomeMin) $('income-min').value = c.incomeMin;
  if (c.educationReq) $('education-req').value = c.educationReq;
  if (c.requiredKeywords) $('required-keywords').value = c.requiredKeywords;
  if (c.excludeKeywords) $('exclude-keywords').value = c.excludeKeywords;

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

  const criteria = {
    ageMin: $('age-min').value ? parseInt($('age-min').value) : null,
    ageMax: $('age-max').value ? parseInt($('age-max').value) : null,
    incomeMin: $('income-min').value ? parseInt($('income-min').value) : null,
    companyTiers,
    educationReq: $('education-req').value,
    requiredKeywords: $('required-keywords').value.trim(),
    excludeKeywords: $('exclude-keywords').value.trim(),
  };

  await chrome.storage.local.set({ screeningCriteria: criteria });
  const saved = $('settings-saved');
  saved.style.display = 'block';
  setTimeout(() => { saved.style.display = 'none'; }, 2000);
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
    profileData = await chrome.tabs.sendMessage(tab.id, { action: 'getProfile' });
  } catch (e) {
    setStatus('generate', 'error', 'プロフィールを取得できませんでした。候補者ページを開いているか確認してください。');
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

  setStatus('generate', 'loading', `パーソナライズ文を生成中... (取得: ${profileData.length || 0}文字)`);

  try {
    const result = await generatePersonalizedLine(apiKey, profileData.profileText);
    $('result-text').textContent = result;
    $('result-section').style.display = 'block';
    setStatus('generate', 'success', '生成完了 — コピーしてテンプレ冒頭に貼り付けてください');
  } catch (e) {
    setStatus('generate', 'error', `生成エラー: ${e.message}`);
  }

  $('generate-btn').disabled = false;
}

async function generatePersonalizedLine(apiKey, profileText) {
  apiKey = sanitizeApiKey(apiKey);
  const prompt = `あなたはハイクラスコンサル転職エージェントのアシスタントです。

以下の候補者プロフィールを読んで、スカウトメールに挿入するパーソナライズ文を1文で作成してください。

【挿入位置】
直前：「この度、貴方様のご経歴を拝見し、アクセンチュアの「〇〇」のポジションに高い親和性を感じ、ご連絡いたしました。」
直後：「当方の経験上、面接次第ではありますが、かなり高い確度で本ポジションにてオファーが出ると感じます。」

【良い例】
・「〇〇様が証券リテール営業10年で個人成果と支店マネジメントの両面を担われ、営業プレイヤーと育成担当の経験を積み重ねてこられた点が印象的でした。」
・「金融機関での現場営業を土台に、提携銀行への販売推進では研修設計から同行サポートまで構造的に支援を組み立ててこられており、このポジションをはじめ幅広い可能性を感じております。」

【厳禁】
- 「〜でいらっしゃいます。」という断定で終わるのはNG
- 「まさに〜そのもの」「〜こそが〜」のような大げさな断言
- 「〜視座」「〜発想転換」「〜思考プロセス」のような仰々しい分析表現
- 「即戦力」「希少」などの評価語
- 「高い親和性を感じ」の繰り返し
- 「ぜひ〜」「お話しさせていただきたく」

【文末】
必ず「〜、このポジションやその他にも多くの可能性があると感じます。」で終わること。

【ルール】
- 1文のみ（前置き・説明不要）
- 「〇〇様の」または「〇〇様が」で始める
- 丁寧だが重くなりすぎないトーン

【候補者プロフィール】
${profileText}`;

  const response = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
      'anthropic-dangerous-direct-browser-access': 'true'
    },
    body: JSON.stringify({
      model: 'claude-sonnet-4-6',
      max_tokens: 200,
      messages: [{ role: 'user', content: prompt }]
    })
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error?.message || `APIエラー (${response.status})`);
  }
  const data = await response.json();
  const text = data.content?.[0]?.text || '';
  if (!text) throw new Error('レスポンスが空でした');
  return text.trim();
}

// ============================================================
// タブ2: ポジション提案
// ============================================================
$('suggest-btn').addEventListener('click', () => runSuggestPosition());

async function runSuggestPosition() {
  const apiKey = $('api-key').value.trim();
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
    profileData = await chrome.tabs.sendMessage(tab.id, { action: 'getProfile' });
  } catch (e) {
    setStatus('suggest', 'error', 'プロフィールを取得できませんでした。候補者ページを開いているか確認してください。');
    $('suggest-btn').disabled = false;
    return;
  }

  if (!profileData || !profileData.success || !profileData.profileText) {
    setStatus('suggest', 'error', 'プロフィール情報が取得できませんでした');
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

async function suggestPosition(apiKey, profileText) {
  apiKey = sanitizeApiKey(apiKey);
  const prompt = `あなたはアクセンチュアへの転職支援を専門とするハイクラスエージェントのアシスタントです。

以下の候補者プロフィールを読み、アクセンチュアで募集されている（または募集される可能性が高い）ポジションの中から最も適したものを3つ提案してください。

【重要な指示】
- 候補者の経歴に最も親和性の高いポジション名を、アクセンチュアの命名規則に合わせて自由に提案してください
- ポジション名は日本語で、具体的かつ正式な表現にしてください

【候補者プロフィール】
${profileText}

以下のJSON形式のみで出力してください（説明・前置き不要）:
{
  "suggestions": [
    {
      "position": "ポジション名",
      "match_score": 90,
      "reason": "このポジションを推奨する理由を2〜3文で。"
    }
  ]
}`;

  const response = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
      'anthropic-dangerous-direct-browser-access': 'true'
    },
    body: JSON.stringify({
      model: 'claude-sonnet-4-6',
      max_tokens: 600,
      messages: [{ role: 'user', content: prompt }]
    })
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error?.message || `APIエラー (${response.status})`);
  }
  const data = await response.json();
  const text = (data.content?.[0]?.text || '').trim();
  const clean = text.replace(/```json|```/g, '').trim();
  return JSON.parse(clean);
}

function renderSuggestion(result) {
  const container = $('suggest-cards');
  container.innerHTML = '';

  (result.suggestions || []).forEach((s, i) => {
    const score = s.match_score || 0;
    const card = document.createElement('div');
    card.className = 'suggest-card' + (i === 0 ? ' best' : '');
    card.innerHTML = `
      <div class="suggest-card-header">
        <span class="suggest-rank">${i === 0 ? '🥇 最推奨' : i === 1 ? '🥈 次点' : '🥉 候補'}</span>
        <span class="suggest-score">${score}点</span>
      </div>
      <div class="suggest-position">${s.position}</div>
      <div class="suggest-reason">${s.reason}</div>
      <button class="use-position-btn" data-position="${s.position}">このポジションで生成</button>
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
$('screening-btn').addEventListener('click', () => runScreening());

async function runBatchScreening() {
  const apiKey = $('api-key').value.trim();
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
  setStatus('screening', 'loading', `${count}人を判定中...`);

  const r = await chrome.storage.local.get(['screeningCriteria']);
  const criteria = r.screeningCriteria || {};

  try {
    const results = await runBatchScreeningAI(apiKey, batchData.cards, criteria);
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

async function runBatchScreeningAI(apiKey, cards, criteria) {
  apiKey = sanitizeApiKey(apiKey);
  const criteriaLines = buildCriteriaLines(criteria);

  const candidateList = cards.map((c, i) =>
    `候補者${i + 1}: ${c.summary}`
  ).join('\n');

  const prompt = `あなたは転職エージェントの一次選定アシスタントです。

以下の【選定基準】に照らして、各候補者を判定してください。
カード情報は概要のみのため、読み取れない項目は「情報なし」として扱ってください。

【選定基準】
${criteriaLines}

【候補者一覧】
${candidateList}

以下のJSON形式のみで出力してください（説明不要）:
{"results":[{"i":1,"o":"OK"},{"i":2,"o":"NG"}]}`;

  const response = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
      'anthropic-dangerous-direct-browser-access': 'true'
    },
    body: JSON.stringify({
      model: 'claude-sonnet-4-6',
      max_tokens: 2000,
      messages: [{ role: 'user', content: prompt }]
    })
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error?.message || `APIエラー (${response.status})`);
  }
  const data = await response.json();
  const text = (data.content?.[0]?.text || '').trim();
  const clean = text.replace(/```json|```/g, '').trim();
  const parsed = JSON.parse(clean);
  return (parsed.results || []).map(r => ({
    overall: r.overall || r.o || '要確認'
  }));
}

function buildCriteriaLines(criteria) {
  const lines = [];
  if (criteria.ageMin || criteria.ageMax) {
    const min = criteria.ageMin ? `${criteria.ageMin}歳以上` : '';
    const max = criteria.ageMax ? `${criteria.ageMax}歳以下` : '';
    lines.push(`- 年齢: ${[min, max].filter(Boolean).join('かつ')}`);
  }
  if (criteria.incomeMin) lines.push(`- 年収: ${criteria.incomeMin}万円以上`);
  if (criteria.companyTiers?.length > 0 && !criteria.companyTiers.includes('不問'))
    lines.push(`- 社格: ${criteria.companyTiers.join('または')}`);
  if (criteria.educationReq && criteria.educationReq !== '不問')
    lines.push(`- 学歴: ${criteria.educationReq}`);
  if (criteria.requiredKeywords) lines.push(`- 必須経験: ${criteria.requiredKeywords}`);
  if (criteria.excludeKeywords) lines.push(`- 除外: ${criteria.excludeKeywords}`);
  return lines.length > 0 ? lines.join('\n') : '- 条件未設定';
}

async function runScreening() {
  const apiKey = $('api-key').value.trim();
  if (!apiKey) {
    setStatus('screening', 'error', 'APIキーを入力して保存してください');
    return;
  }

  setStatus('screening', 'loading', 'プロフィールを取得中...');
  $('screening-btn').disabled = true;
  $('screening-result').style.display = 'none';

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
    profileData = await chrome.tabs.sendMessage(tab.id, { action: 'getProfile' });
  } catch (e) {
    setStatus('screening', 'error', 'プロフィールを取得できませんでした。候補者ページを開いているか確認してください。');
    chrome.tabs.sendMessage(tab.id, { action: 'clearBadge' }).catch(() => {});
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

  const r = await chrome.storage.local.get(['screeningCriteria']);
  const criteria = r.screeningCriteria || {};

  setStatus('screening', 'loading', '選定基準と照合中...');

  try {
    const result = await runScreeningAI(apiKey, profileData.profileText, criteria);
    renderScreeningResult(result);
    $('screening-result').style.display = 'block';

    // 結果バッジをカードに表示
    chrome.tabs.sendMessage(tab.id, { action: 'showBadgeResult', overall: result.overall }).catch(() => {});

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

async function runScreeningAI(apiKey, profileText, criteria) {
  apiKey = sanitizeApiKey(apiKey);
  const criteriaLines = [];

  if (criteria.ageMin || criteria.ageMax) {
    const min = criteria.ageMin ? `${criteria.ageMin}歳以上` : '';
    const max = criteria.ageMax ? `${criteria.ageMax}歳以下` : '';
    criteriaLines.push(`- 年齢: ${[min, max].filter(Boolean).join('かつ')}`);
  }

  if (criteria.incomeMin) {
    criteriaLines.push(`- 年収: ${criteria.incomeMin}万円以上`);
  }

  if (criteria.companyTiers && criteria.companyTiers.length > 0 && !criteria.companyTiers.includes('不問')) {
    criteriaLines.push(`- 社格: ${criteria.companyTiers.join('または')}`);
  }

  if (criteria.educationReq && criteria.educationReq !== '不問') {
    criteriaLines.push(`- 学歴: ${criteria.educationReq}`);
  }

  if (criteria.requiredKeywords) {
    criteriaLines.push(`- 必須経験: ${criteria.requiredKeywords}（いずれかを含む）`);
  }

  if (criteria.excludeKeywords) {
    criteriaLines.push(`- 除外条件: ${criteria.excludeKeywords}（含む場合はNG）`);
  }

  if (criteriaLines.length === 0) {
    criteriaLines.push('- 条件未設定（⚙️設定タブで選定基準を設定してください）');
  }

  const prompt = `あなたは転職エージェントの一次選定アシスタントです。

以下の【選定基準】と【候補者プロフィール】を照合し、各基準について候補者がクリアしているかを判定してください。
プロフィールに情報が記載されていない項目は「情報なし」として扱ってください。

【選定基準】
${criteriaLines.join('\n')}

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
      "detail": "判定根拠を1文で（プロフィールから読み取れた具体的な情報を含める）"
    }
  ],
  "comment": "総合的なコメントを2〜3文で。スカウトを打つべきかどうかの所見を含める。"
}`;

  const response = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
      'anthropic-dangerous-direct-browser-access': 'true'
    },
    body: JSON.stringify({
      model: 'claude-sonnet-4-6',
      max_tokens: 800,
      messages: [{ role: 'user', content: prompt }]
    })
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error?.message || `APIエラー (${response.status})`);
  }
  const data = await response.json();
  const text = (data.content?.[0]?.text || '').trim();
  const clean = text.replace(/```json|```/g, '').trim();
  return JSON.parse(clean);
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
            <span class="candidate-field-name">${f.name}</span>
            <span class="candidate-field-value ${f.value ? '' : 'unknown'}">${f.value || '情報なし'}</span>
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
        <div class="criterion-name">${c.name}</div>
        <div class="criterion-detail">${c.detail}</div>
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
  const apiKey = $('api-key').value.trim();
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
