// content.js v1.5.0
// 各媒体のプロフィールページからテキストを抽出する

// -------------------------------------------------------
// プラットフォーム判定
// -------------------------------------------------------
function getPlatform() {
  const h = location.hostname;
  if (h.includes('rikunabi') || h.includes('hrtech')) return 'rds';
  if (h.includes('bizreach') || h.includes('es-support'))  return 'bizreach';
  if (h.includes('doda-x') || h.includes('dodax'))         return 'dodax';
  if (h.includes('ambi') || h.includes('en-ambi'))         return 'ambi';
  if (h.includes('green-japan'))                            return 'green';
  if (h.includes('mynavi'))                                 return 'mynavi';
  return 'unknown';
}

// -------------------------------------------------------
// 候補者カードへのビジュアルフィードバック
// -------------------------------------------------------
let _selectedCard = null;

function injectStyles() {
  if (document.getElementById('snow-we-styles')) return;
  const style = document.createElement('style');
  style.id = 'snow-we-styles';
  style.textContent = `
    .snow-we-selected {
      outline: 3px solid #6366F1 !important;
      outline-offset: -2px;
      transition: outline .2s;
    }
    .snow-we-badge {
      position: absolute !important;
      top: 6px !important;
      right: 6px !important;
      font-size: 11px !important;
      font-weight: 700 !important;
      padding: 3px 10px !important;
      border-radius: 20px !important;
      z-index: 99999 !important;
      pointer-events: none !important;
      white-space: nowrap !important;
      box-shadow: 0 1px 4px rgba(0,0,0,.25) !important;
      font-family: -apple-system, sans-serif !important;
    }
    .snow-we-badge.checking { background: #6366F1 !important; color: #fff !important; }
    .snow-we-badge.ok       { background: #059669 !important; color: #fff !important; }
    .snow-we-badge.ng       { background: #DC2626 !important; color: #fff !important; }
    .snow-we-badge.warn     { background: #D97706 !important; color: #fff !important; }
    @keyframes snow-we-pulse {
      0%,100% { opacity: 1; } 50% { opacity: .6; }
    }
    .snow-we-badge.checking { animation: snow-we-pulse 1.2s ease-in-out infinite; }

    /* 追加ボタンのハイライト */
    .snow-we-btn-highlight {
      outline: 3px solid #6366F1 !important;
      outline-offset: 3px !important;
      box-shadow: 0 0 10px rgba(99,102,241,0.7) !important;
      animation: snow-we-pulse 1s ease-in-out infinite !important;
      position: relative !important;
      z-index: 9999 !important;
    }
    .snow-we-btn-tip {
      position: absolute !important;
      background: #6366F1 !important;
      color: #fff !important;
      font-size: 10px !important;
      font-weight: 700 !important;
      padding: 2px 8px !important;
      border-radius: 10px !important;
      white-space: nowrap !important;
      z-index: 99999 !important;
      top: -22px !important;
      left: 50% !important;
      transform: translateX(-50%) !important;
      pointer-events: none !important;
    }
  `;
  document.head.appendChild(style);
}

// -------------------------------------------------------
// プラットフォーム別：候補者カードの取得
// -------------------------------------------------------
function findCandidateCardsByPlatform() {
  const platform = getPlatform();
  const agePattern = /\d{2}歳/;
  const vw = window.innerWidth;

  // 親子重複を除外するフィルター（最小要素を優先）
  function dedup(els) {
    return els.filter((el, _, arr) => !arr.some(p => p !== el && p.contains(el)));
  }

  if (platform === 'ambi') {
    // AMBIは全幅カード。「この検討人材リストに追加」ボタンを含む
    return dedup(Array.from(document.querySelectorAll('div, article, li')).filter(el => {
      const rect = el.getBoundingClientRect();
      const text = (el.innerText || '');
      return rect.width > vw * 0.45 &&
             rect.height > 120 && rect.height < 900 &&
             agePattern.test(text) &&
             (text.includes('スカウト') || text.includes('検討人材') || text.includes('万円')) &&
             text.length > 120 && text.length < 8000;
    }));
  }

  if (platform === 'bizreach') {
    // Bizreachは全幅カード。ラベル・コメントボタンを含む
    return dedup(Array.from(document.querySelectorAll('div, article, li')).filter(el => {
      const rect = el.getBoundingClientRect();
      const text = (el.innerText || '');
      return rect.width > vw * 0.45 &&
             rect.height > 80 && rect.height < 700 &&
             agePattern.test(text) &&
             (text.includes('ラベル') || text.includes('コメント') || text.includes('万円')) &&
             text.length > 80 && text.length < 6000;
    }));
  }

  if (platform === 'dodax') {
    // doda-Xは全幅カード。タグ・コメントボタンを含む
    return dedup(Array.from(document.querySelectorAll('div, article, li')).filter(el => {
      const rect = el.getBoundingClientRect();
      const text = (el.innerText || '');
      return rect.width > vw * 0.4 &&
             rect.height > 80 && rect.height < 900 &&
             agePattern.test(text) &&
             (text.includes('タグ') || text.includes('コメント') || text.includes('万円')) &&
             text.length > 100 && text.length < 8000;
    }));
  }

  if (platform === 'rds') {
    // RDS(リクナビHRTech)の検索一覧：全幅カード（スカウト・検討中リスト追加ボタンあり）
    const fullWidthCards = dedup(Array.from(document.querySelectorAll('div, article, li')).filter(el => {
      const rect = el.getBoundingClientRect();
      const text = (el.innerText || '');
      return rect.width > vw * 0.5 &&
             rect.height > 100 && rect.height < 900 &&
             agePattern.test(text) &&
             (text.includes('スカウト') || text.includes('検討中リスト') || text.includes('万円') || text.includes('レジュメ')) &&
             text.length > 100 && text.length < 8000;
    }));
    if (fullWidthCards.length > 0) return fullWidthCards;

    // フォールバック：左パネル型（詳細が右に表示される旧レイアウト）
    return dedup(Array.from(document.querySelectorAll('div, li, article')).filter(el => {
      const rect = el.getBoundingClientRect();
      const text = (el.innerText || '');
      return rect.left < vw * 0.55 &&
             rect.width > 180 && rect.width < vw * 0.6 &&
             rect.height > 50 && rect.height < 500 &&
             agePattern.test(text) &&
             text.length > 40 && text.length < 3000;
    }));
  }

  // green・mynavi・その他：年齢を含む適度なサイズのカード
  return dedup(Array.from(document.querySelectorAll('div, li, article')).filter(el => {
    const rect = el.getBoundingClientRect();
    const text = (el.innerText || '');
    return rect.width > vw * 0.4 &&
           rect.height > 80 && rect.height < 800 &&
           agePattern.test(text) &&
           text.length > 80 && text.length < 6000;
  }));
}

// -------------------------------------------------------
// プラットフォーム別：追加ボタンをハイライト
// -------------------------------------------------------
function highlightAddButton(cardEl) {
  const platform = getPlatform();
  const btnTextMap = {
    ambi:     'この検討人材リストに追加',
    bizreach: 'ラベル',
    dodax:    'タグ',
    rds:      '検討中リスト追加',
  };
  const label = btnTextMap[platform];
  if (!label) return;

  // カード内 or カードの兄弟・親から検索
  const searchRoot = cardEl.closest('li, article, [class*="row"], [class*="item"]') || cardEl.parentElement || document;
  let btn = null;
  searchRoot.querySelectorAll('button, a, span, div').forEach(el => {
    if (!btn && (el.innerText || '').trim().includes(label)) btn = el;
  });
  // カード内で見つからなければページ全体から
  if (!btn) {
    document.querySelectorAll('button, a, span, div').forEach(el => {
      if (!btn && (el.innerText || '').trim() === label) btn = el;
    });
  }
  if (!btn) return;

  // ハイライト
  btn.classList.add('snow-we-btn-highlight');
  if (getComputedStyle(btn).position === 'static') btn.style.position = 'relative';
  const tip = document.createElement('span');
  tip.className = 'snow-we-btn-tip';
  tip.textContent = '👆 ここをクリック';
  btn.appendChild(tip);

  // 5分後に自動解除（追加ボタンをクリックしたら即解除）
  const dismissHighlight = () => {
    btn.classList.remove('snow-we-btn-highlight');
    tip.remove();
    btn.removeEventListener('click', dismissHighlight);
  };
  btn.addEventListener('click', dismissHighlight);
  setTimeout(dismissHighlight, 5 * 60 * 1000);
}

function setupClickTracking() {
  injectStyles();
  document.addEventListener('click', e => {
    const cards = findCandidateCardsByPlatform();
    const clicked = cards.find(c => c.contains(e.target) || c === e.target);
    if (!clicked) return;

    // 以前の選択ハイライトだけ外す（バッジは消さない）
    document.querySelectorAll('.snow-we-selected').forEach(el => el.classList.remove('snow-we-selected'));
    // 単体判定バッジ（batch以外）だけ消す
    document.querySelectorAll('.snow-we-badge:not(.batch)').forEach(b => b.remove());

    _selectedCard = clicked;
    if (getComputedStyle(clicked).position === 'static') clicked.style.position = 'relative';
    clicked.classList.add('snow-we-selected');
  }, true);
}

function showBadge(cls, text) {
  if (!_selectedCard) return;
  document.querySelectorAll('.snow-we-badge').forEach(b => b.remove());
  const badge = document.createElement('div');
  badge.className = `snow-we-badge ${cls}`;
  badge.textContent = text;
  _selectedCard.appendChild(badge);
}

// クリックトラッキング開始
setupClickTracking();

// -------------------------------------------------------
// スカウト送信履歴の管理
// -------------------------------------------------------
const SCOUT_KEY = 'scoutHistory';
const RESCOUNT_DAYS = 90; // 3ヶ月 = 90日

async function getScoutHistory() {
  const r = await chrome.storage.local.get([SCOUT_KEY]);
  return r[SCOUT_KEY] || {};
}

async function recordScoutSent(candidateId, info) {
  if (!candidateId) return;
  const now = Date.now();
  const platform = getPlatform();
  const history = await getScoutHistory();
  history[candidateId] = {
    date: now,
    platform,
    name: info.name || '',
    company: info.company || '',
    age: info.age || '',
  };
  await chrome.storage.local.set({ [SCOUT_KEY]: history });

  // Googleスプレッドシートへ自動記録
  const r2 = await chrome.storage.local.get(['gasSettings', 'currentPosition']);
  const gas = r2.gasSettings || {};
  if (gas.url && gas.recruiter) {
    const ageNum = (info.age || '').replace(/[歳才]/, '');
    fetch(gas.url, {
      method: 'POST',
      body: JSON.stringify({
        secret: gas.secret || 'snowwe2024',
        recruiter: gas.recruiter,
        company: info.company || '',
        age: ageNum,
        univ: info.univ || '',
        media: platform,
        position: r2.currentPosition || '',
        ts: now,
      }),
    }).catch(() => {});
  }
}

// 直近90日以内にスカウト済みかを返す
function scoutStatus(history, candidateId) {
  if (!candidateId) return { scouted: false };
  const record = history[candidateId];
  if (!record) return { scouted: false };
  const daysAgo = Math.floor((Date.now() - record.date) / (1000 * 60 * 60 * 24));
  return { scouted: true, daysAgo, reScoutable: daysAgo >= RESCOUNT_DAYS };
}

// カードから候補者の一意IDを取得（プロフィールURL を優先）
function getCandidateId(cardEl) {
  const url = findProfileUrl(cardEl);
  if (url) return url.replace(/[?#].*$/, ''); // クエリ・ハッシュを除去

  // フォールバック：カードテキストから候補者番号を抽出
  const text = (cardEl.innerText || '');
  const m = text.match(/No\.(\d{5,})|^(\d{6,})\s/m) ||
            text.match(/\b([0-9]{6,10})\b/);
  if (m) return `${getPlatform()}_${m[1] || m[2]}`;
  return null;
}

// カードから基本情報を抽出（履歴保存用）
function extractBasicInfo(cardEl) {
  const text = (cardEl.innerText || '');
  const ageMatch = text.match(/(\d{2,3})歳/);
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);

  // 大学名を抽出（「〇〇大学」「〇〇大学院」「〇〇高専」のパターン）
  let univ = '';
  const univMatch = text.match(/([^\s\n　]{1,20}(?:大学院|大学|高専|専門学校)(?:大学院?)?(?:[-－][^\s\n　]{1,10})?)/);
  if (univMatch) {
    univ = univMatch[1].replace(/[（(（].*/, '').replace(/[学部研究科].*$/, '大学').trim();
  }

  return {
    age: ageMatch ? `${ageMatch[1]}歳` : '',
    company: lines[0] || '',
    univ,
    name: '',
  };
}

// スカウトボタンのクリックを検知して履歴に記録
document.addEventListener('click', async e => {
  const btn = e.target.closest('button, a');
  if (!btn) return;
  const text = (btn.innerText || '').trim();
  if (text !== 'スカウト' && !text.includes('スカウトを送る')) return;

  const cards = findCandidateCardsByPlatform();
  const card = cards.find(c => c.contains(btn) || c === btn.closest('[class*="card"],[class*="row"],li,article'));
  if (!card) return;

  const id = getCandidateId(card);
  if (id) await recordScoutSent(id, extractBasicInfo(card));
}, true);

// -------------------------------------------------------
// 「さらに読み込む」ボタンを押して全候補者をDOMに展開
// -------------------------------------------------------
async function loadAllCandidatesIntoDOM() {
  const platform = getPlatform();
  const LOAD_MORE_TEXTS = ['さらに読み込む', 'もっと見る', 'Load more', '次の候補者'];
  const MAX_LOADS = 15;

  function findLoadMoreBtn() {
    for (const el of document.querySelectorAll('button, a, div[role="button"], span')) {
      const t = (el.innerText || '').trim();
      if (LOAD_MORE_TEXTS.some(kw => t.includes(kw))) return el;
    }
    return null;
  }

  // ページ最下部までスクロールして遅延ロードを誘発
  async function scrollToBottom() {
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
    await new Promise(r => setTimeout(r, 800));
  }

  let loaded = 0;

  for (let i = 0; i < MAX_LOADS; i++) {
    await scrollToBottom();
    const btn = findLoadMoreBtn();
    if (!btn) break;

    const countBefore = findCandidateCardsByPlatform().length;
    showAutoStatus(`📥 さらに読み込み中... (${loaded + 1}回目)`);
    btn.click();
    await new Promise(r => setTimeout(r, 2000));
    const countAfter = findCandidateCardsByPlatform().length;

    loaded++;
    if (countAfter <= countBefore) break; // 増えなければ終了
  }

  // 判定後バッジが見えるよう先頭に戻る
  window.scrollTo({ top: 0, behavior: 'smooth' });
  await new Promise(r => setTimeout(r, 600));
}

// -------------------------------------------------------
// 自動判定：ページロード時に全候補者を自動スクリーニング
// -------------------------------------------------------
async function autoScreenCandidates() {
  // APIキーと設定を取得
  const stored = await chrome.storage.local.get(['apiKey', 'screeningCriteria']);
  const apiKey = stored.apiKey;
  if (!apiKey) return; // APIキー未設定なら何もしない

  const criteria = stored.screeningCriteria || {};

  // カード検出（DOMが安定するまで待つ）
  await new Promise(r => setTimeout(r, 400));

  // 初回カードチェック：候補者一覧ページでなければ終了
  const initialCards = extractAllCandidateCards();
  if (initialCards.length === 0) return;

  injectStyles();
  showAutoStatus('📥 候補者を全件読み込み中...');

  // 「さらに読み込む」を自動クリックして全候補者をDOMに展開
  await loadAllCandidatesIntoDOM();

  // 全件読み込み後に再取得
  const cards = extractAllCandidateCards();
  if (cards.length === 0) return;

  // 判定中バッジを全カードに表示
  cards.forEach(c => {
    if (getComputedStyle(c.el).position === 'static') c.el.style.position = 'relative';
    const badge = document.createElement('div');
    badge.className = 'snow-we-badge batch checking';
    badge.textContent = '🔍 判定中...';
    c.el.appendChild(badge);
  });

  showAutoStatus(`🔍 ${cards.length}人を判定中...`);

  try {
    const results = await callBatchScreeningAPI(apiKey, cards, criteria);

    // 結果をカードに反映
    results.forEach((r, i) => {
      if (!cards[i]) return;
      const el = cards[i].el;
      el.querySelectorAll('.snow-we-badge').forEach(b => b.remove());

      const map = {
        'OK':   ['ok',   '✅ スカウト候補'],
        'NG':   ['ng',   '❌ 見送り'],
        '要確認': ['warn', '⚠️ 要確認'],
      };
      const [cls, text] = map[r.overall] || ['warn', '⚠️ 要確認'];
      const badge = document.createElement('div');
      badge.className = `snow-we-badge batch ${cls}`; // batch クラスでクリック時消去を防ぐ
      badge.textContent = text;
      el.appendChild(badge);

      // OK候補者の追加ボタンを光らせる
      if (r.overall === 'OK') {
        highlightAddButton(el);
      }
    });

    const okCount   = results.filter(r => r.overall === 'OK').length;
    const ngCount   = results.filter(r => r.overall === 'NG').length;
    const warnCount = results.filter(r => r.overall === '要確認').length;
    showAutoStatus(`✅ 判定完了 — ✅${okCount}人 ⚠️${warnCount}人 ❌${ngCount}人`, 6000);

  } catch (e) {
    cards.forEach(c => c.el.querySelectorAll('.snow-we-badge').forEach(b => b.remove()));
    showAutoStatus(`❌ 判定エラー: ${e.message}`, 5000);
  }
}

// 画面右下にステータス表示
function showAutoStatus(message, autoDismissMs) {
  let el = document.getElementById('snow-we-auto-status');
  if (!el) {
    el = document.createElement('div');
    el.id = 'snow-we-auto-status';
    el.style.cssText = `
      position: fixed; bottom: 20px; right: 20px; z-index: 2147483647;
      background: #1e1b4b; color: #fff; font-size: 13px; font-weight: 600;
      padding: 10px 18px; border-radius: 24px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.35);
      font-family: -apple-system, sans-serif;
      pointer-events: none;
      transition: opacity 0.3s;
    `;
    document.body.appendChild(el);
  }
  el.textContent = message;
  el.style.opacity = '1';
  if (autoDismissMs) {
    clearTimeout(el._timer);
    el._timer = setTimeout(() => { el.style.opacity = '0'; }, autoDismissMs);
  }
}

// Claude APIを呼び出す（content.js内から直接）
async function callBatchScreeningAPI(apiKey, cards, criteria) {
  const criteriaLines = buildCriteriaText(criteria);
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

以下のJSON形式のみで出力してください（説明不要・reasonは10文字以内）:
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
  // 短縮キー(i/o)と通常キー(index/overall)の両方に対応
  return (parsed.results || []).map(r => ({
    overall: r.overall || r.o || '要確認'
  }));
}

// -------------------------------------------------------
// 自動リスト追加モード
// -------------------------------------------------------
async function triggerAutoAdd() {
  const stored = await chrome.storage.local.get(['apiKey', 'screeningCriteria']);
  const apiKey = (stored.apiKey || '').replace(/[^\x21-\x7E]/g, '').trim();

  if (!apiKey || apiKey.length < 20) {
    showAutoStatus('⚙️設定タブでAPIキーを保存してください', 4000);
    return;
  }

  const criteria = stored.screeningCriteria || {};
  injectStyles();

  showAutoStatus('📥 読み込み中...');
  document.querySelectorAll('.snow-we-badge.batch').forEach(b => b.remove());

  await loadAllCandidatesIntoDOM();

  const cards = extractAllCandidateCards();
  if (cards.length === 0) {
    showAutoStatus('❌ 候補者が見つかりません。一覧ページで実行してください。', 4000);
    return;
  }

  // ページをまたいで処理するため、進捗をストレージで管理
  const progress = await loadAutoAddProgress();
  let addedCount = progress.added || 0;
  let totalProcessed = progress.processed || 0;

  // スカウト履歴をまとめて取得（ループ内で何度も呼ばないよう）
  const scoutHistory = await getScoutHistory();

  for (let i = 0; i < cards.length; i++) {
    const { el, text: cardText } = cards[i];
    showAutoStatus(`🤖 ${i + 1}/${cards.length}人処理中 ✅${addedCount}人追加`);

    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    await sleep(500);

    // 3ヶ月チェック：最近スカウト済みならスキップ
    const candidateId = getCandidateId(el);
    const status = scoutStatus(scoutHistory, candidateId);
    if (status.scouted && !status.reScoutable) {
      setBatchBadge(el, 'warn', `⏸ 送信済（${status.daysAgo}日前）`);
      totalProcessed++;
      await sleep(200);
      continue;
    }
    if (status.scouted && status.reScoutable) {
      // 3ヶ月以上経過 → 通常通り処理（バッジに表示）
      setBatchBadge(el, 'checking', `🔄 再追加可（${status.daysAgo}日前）`);
    } else {
      setBatchBadge(el, 'checking', '🔍 判定中...');
    }

    // プロフィール全文取得（プラットフォーム別）
    let profileText = cardText;
    try { profileText = await getFullProfile(el, cardText); } catch (_) {}

    try {
      const overall = await judgeSingleCandidate(apiKey, profileText, criteria);
      setBatchBadge(el,
        overall === 'OK' ? 'ok' : overall === 'NG' ? 'ng' : 'warn',
        overall === 'OK' ? '✅ スカウト候補' : overall === 'NG' ? '❌ 見送り' : '⚠️ 要確認');

      if (overall === 'OK' || overall === '要確認') {
        const added = await clickAddButton(el, criteria.autoTagName || '');
        if (added) {
          addedCount++;
          // リスト追加時点の情報を履歴に仮記録（スカウト送信とは別）
          if (candidateId) {
            scoutHistory[`listed_${candidateId}`] = { date: Date.now(), platform: getPlatform() };
          }
        }
      }
    } catch (_) {
      setBatchBadge(el, 'warn', '⚠️ 判定失敗');
    }

    totalProcessed++;
    await saveAutoAddProgress({ added: addedCount, processed: totalProcessed, running: true });
    await sleep(700);
  }

  // 次のページがあれば自動で移動して処理を続ける
  const nextPage = findNextPageButton();
  if (nextPage) {
    showAutoStatus(`🤖 次ページへ移動中... (累計✅${addedCount}人追加)`);
    await saveAutoAddProgress({ added: addedCount, processed: totalProcessed, running: true });
    await sleep(1000);
    nextPage.click(); // ページ遷移 → 次ページで自動再開
  } else {
    // 全ページ完了
    await saveAutoAddProgress({ running: false });
    showAutoStatus(`🤖 完了！ ✅${addedCount}人を検討リストに追加 (全${totalProcessed}人中)`, 8000);
  }
}

// -------------------------------------------------------
// プロフィール全文取得（プラットフォーム別）
// -------------------------------------------------------
async function getFullProfile(cardEl, fallbackText) {
  const platform = getPlatform();

  // RDS：カードクリック → 右パネルで全文取得
  if (platform === 'rds') {
    cardEl.click();
    await sleep(1500);
    const panel = findRDSDetailPanel();
    if (panel) {
      const full = extractMainText(panel, 3000);
      if (full.length > 200) return full;
    }
    return fallbackText.substring(0, 900);
  }

  // その他：プロフィールURLをフェッチして全文取得
  const profileUrl = findProfileUrl(cardEl);
  if (profileUrl) {
    const fetched = await fetchProfilePage(profileUrl);
    if (fetched && fetched.length > 300) return fetched;
  }

  // フォールバック：一覧カードのテキスト
  return fallbackText.substring(0, 900);
}

// カード内のプロフィールページURLを探す
function findProfileUrl(cardEl) {
  const platform = getPlatform();
  const patterns = {
    dodax:    [/member_search\/detail/, /member_detail/, /\/profile\//],
    ambi:     [/\/scout\/member\//, /\/member\/\d+/, /company\/scout/],
    green:    [/green-japan\.com\/user\//, /\/members\//],
    mynavi:   [/\/candidate\//, /\/resume\//],
    bizreach: [/\/resume\//, /\/candidate\//],
  };

  const platformPatterns = patterns[platform] || [];

  for (const link of cardEl.querySelectorAll('a[href]')) {
    const href = link.href || '';
    if (!href || href === '#' || href.startsWith('javascript')) continue;
    if (platformPatterns.some(p => p.test(href))) return href;
  }

  // フォールバック：カード内の最初の内部リンク
  for (const link of cardEl.querySelectorAll('a[href]')) {
    const href = link.href || '';
    if (href.startsWith(location.origin) && !href.includes('#')) return href;
  }

  return null;
}

// プロフィールページをフェッチしてテキストを返す
async function fetchProfilePage(url) {
  try {
    const res = await fetch(url, {
      credentials: 'include',
      headers: { 'Accept': 'text/html,application/xhtml+xml' }
    });
    if (!res.ok) return null;
    const html = await res.text();
    const doc = new DOMParser().parseFromString(html, 'text/html');

    // 不要要素を除去
    doc.querySelectorAll('script,style,noscript,nav,header,footer,aside,[class*="banner"],[class*="ad"]').forEach(e => e.remove());

    // プロフィールキーワードを含む最大ブロックを探す
    const keywords = ['職務経歴', '職歴', '業務内容', 'スキル', '学歴', '自己PR', '転職理由', '経験'];
    let best = '';
    doc.querySelectorAll('main,[role="main"],#main,.profile,.resume,section,article').forEach(el => {
      const t = (el.innerText || el.textContent || '').trim();
      if (t.length > best.length && keywords.some(kw => t.includes(kw))) best = t;
    });

    if (best.length < 200) {
      best = (doc.body?.innerText || doc.body?.textContent || '').trim();
    }

    return best.replace(/\s+/g, ' ').trim().substring(0, 3000);
  } catch {
    return null;
  }
}

// 候補者カードの追加ボタンを探してクリックする
async function clickAddButton(cardEl, tagName) {
  const platform = getPlatform();
  const labelMap = {
    rds:      '検討中リスト追加',
    ambi:     'この検討人材リストに追加',
    dodax:    'タグ',
    bizreach: 'ラベル',
    green:    '気になる',
    mynavi:   '検討リスト',
  };
  const label = labelMap[platform];
  if (!label) return false;

  // カード→親要素→ページ全体の順で検索
  const roots = [cardEl, cardEl.parentElement, cardEl.closest('li,tr,article,[class*="row"]'), document.body].filter(Boolean);
  let btn = null;
  for (const root of roots) {
    btn = Array.from(root.querySelectorAll('button,a,[role="button"]'))
      .find(el => (el.innerText || '').trim().includes(label));
    if (btn) break;
  }
  if (!btn) return false;

  btn.click();
  await sleep(600);

  // ダイアログが開いた場合：タグ名入力＋確定
  await handleAddDialog(tagName);
  return true;
}

// 追加ダイアログを処理する（タグ名入力にも対応）
async function handleAddDialog(tagName) {
  await sleep(500);

  // 表示中のダイアログ・ドロップダウンを探す
  const dialogs = Array.from(document.querySelectorAll(
    '[role="dialog"],[class*="modal"],[class*="dialog"],[class*="dropdown"],[class*="popup"],[class*="tooltip"]'
  )).filter(el => {
    const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
  });

  for (const dialog of dialogs) {
    // タグ入力欄があれば入力する
    if (tagName) {
      const input = dialog.querySelector('input[type="text"],input:not([type]),textarea');
      if (input) {
        input.focus();
        input.value = tagName;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        await sleep(300);
      }
    }

    // 確定ボタンをクリック
    const confirmTexts = ['追加', '確認', 'OK', 'はい', '保存', '完了', '適用'];
    const btns = Array.from(dialog.querySelectorAll('button,a,[role="button"]'));
    for (const text of confirmTexts) {
      const found = btns.find(b => (b.innerText || '').trim().includes(text));
      if (found) { found.click(); return; }
    }
  }
}

// 1候補者のAI判定（Haiku使用：高速・低コスト）
async function judgeSingleCandidate(apiKey, profileText, criteria) {
  const criteriaLines = buildCriteriaText(criteria);
  const prompt = `転職エージェントの一次選定アシスタントです。

【選定基準】
${criteriaLines}

【候補者情報】
${profileText}

JSON1行のみで出力:
{"o":"OK"} または {"o":"NG"} または {"o":"要確認"}`;

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
      max_tokens: 20,
      messages: [{ role: 'user', content: prompt }]
    })
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error?.message || `APIエラー (${response.status})`);
  }
  const data = await response.json();
  const text = (data.content?.[0]?.text || '').trim();
  const match = text.match(/"o"\s*:\s*"([^"]+)"/);
  return match ? match[1] : '要確認';
}

// バッジをセット（バッチ用）
function setBatchBadge(el, cls, text) {
  el.querySelectorAll('.snow-we-badge.batch').forEach(b => b.remove());
  if (getComputedStyle(el).position === 'static') el.style.position = 'relative';
  const badge = document.createElement('div');
  badge.className = `snow-we-badge batch ${cls}`;
  badge.textContent = text;
  el.appendChild(badge);
}

// 次ページボタンを探す
function findNextPageButton() {
  const nextTexts = ['次へ', '次のページ', '>', '›', 'Next'];
  // ページネーションエリアを優先して探す
  const paginationArea = document.querySelector(
    '[class*="pagination"],[class*="pager"],[class*="page-nav"],[aria-label*="ページ"]'
  ) || document.body;

  for (const el of paginationArea.querySelectorAll('a,button,[role="button"]')) {
    const t = (el.innerText || el.getAttribute('aria-label') || '').trim();
    if (nextTexts.some(kw => t === kw || t.includes(kw))) {
      // 無効化・現在ページでないことを確認
      if (!el.disabled && !el.classList.contains('disabled') &&
          !el.getAttribute('aria-disabled') &&
          !el.classList.contains('active') && !el.classList.contains('current')) {
        return el;
      }
    }
  }
  return null;
}

// 自動追加の進捗をストレージに保存
async function saveAutoAddProgress(data) {
  await chrome.storage.local.set({ autoAddProgress: data });
}

// 自動追加の進捗をストレージから読み込む
async function loadAutoAddProgress() {
  const r = await chrome.storage.local.get(['autoAddProgress']);
  return r.autoAddProgress || {};
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function buildCriteriaText(criteria) {
  const lines = [];
  if (criteria.ageMin || criteria.ageMax) {
    const parts = [];
    if (criteria.ageMin) parts.push(`${criteria.ageMin}歳以上`);
    if (criteria.ageMax) parts.push(`${criteria.ageMax}歳以下`);
    lines.push(`- 年齢: ${parts.join('かつ')}`);
  }
  if (criteria.incomeMin) lines.push(`- 年収: ${criteria.incomeMin}万円以上`);
  if (criteria.companyTiers?.length > 0 && !criteria.companyTiers.includes('不問'))
    lines.push(`- 社格: ${criteria.companyTiers.join('または')}`);
  if (criteria.educationReq && criteria.educationReq !== '不問')
    lines.push(`- 学歴: ${criteria.educationReq}`);
  if (criteria.minTenure) lines.push(`- 在籍期間: 過去の全職歴を含め、${criteria.minTenure}年未満の在籍が明確に確認できる場合のみNG。在籍期間が不明・記載なしの場合はOKとして扱う`);
  if (criteria.requiredKeywords) lines.push(`- 必須経験: ${criteria.requiredKeywords}`);
  if (criteria.excludeKeywords)  lines.push(`- 除外: ${criteria.excludeKeywords}`);
  return lines.length > 0 ? lines.join('\n') : '- 条件未設定';
}

// ページロード後に自動追加が継続中なら再開
window.addEventListener('load', () => {
  setTimeout(async () => {
    injectStyles();
    const progress = await loadAutoAddProgress();
    if (progress.running) {
      await sleep(1500);
      triggerAutoAdd();
    }
  }, 1000);
});

// -------------------------------------------------------
// 一括判定：プラットフォーム別カード検出で全候補者を取得
// -------------------------------------------------------
function extractAllCandidateCards() {
  const cards = findCandidateCardsByPlatform();

  return cards.slice(0, 200).map(el => {
    const text = (el.innerText || '').trim();
    const ageMatch = text.match(/(\d{2})歳/);
    const incomeMatch = text.match(/(\d{3,4})[〜~～](\d{3,4})万円/) ||
                        text.match(/(\d{3,4})万円/) ||
                        text.match(/(\d{4})万/);
    const lines = text.split('\n').map(l => l.trim()).filter(Boolean);

    return {
      el,
      text,
      age:        ageMatch   ? parseInt(ageMatch[1]) : null,
      incomeText: incomeMatch ? incomeMatch[0]       : null,
      summary:    lines.slice(0, 12).join(' / ')
    };
  });
}

// -------------------------------------------------------
// ユーティリティ：セレクターで要素を取得しテキスト結合
// -------------------------------------------------------
function extractBySelectors(selectors, root) {
  root = root || document;
  const seen = new Set();
  const parts = [];
  for (const sel of selectors) {
    try {
      root.querySelectorAll(sel).forEach(el => {
        if (seen.has(el)) return;
        seen.add(el);
        const t = el.innerText || el.textContent || '';
        const trimmed = t.trim();
        if (trimmed.length > 20) parts.push(trimmed);
      });
    } catch (e) {}
  }
  return parts.join('\n');
}

// -------------------------------------------------------
// ユーティリティ：キーワードを含むテキストブロックを収集
// -------------------------------------------------------
function extractByKeywords(keywords, root, minLen, maxLen) {
  root = root || document;
  minLen = minLen || 30;
  maxLen = maxLen || 6000;
  const collected = [];
  const seen = new Set();

  root.querySelectorAll('div, section, article, li, tr, td, dl, dt, dd, p, span').forEach(el => {
    if (seen.has(el)) return;
    const t = (el.innerText || '').trim();
    if (t.length < minLen || t.length > maxLen) return;
    if (!keywords.some(kw => t.includes(kw))) return;

    let dup = false;
    for (const prev of collected) {
      if (prev.includes(t) || t.includes(prev)) { dup = true; break; }
    }
    if (!dup) {
      collected.push(t);
      seen.add(el);
    }
  });

  collected.sort((a, b) => b.length - a.length);
  return collected.slice(0, 5).join('\n\n');
}

// -------------------------------------------------------
// ユーティリティ：メインエリアのテキストをクリーンに取得
// -------------------------------------------------------
// スカウト履歴・評価・メモなど採用管理UIセクションを除去
function removeNonProfileSections(text) {
  const stopMarkers = ['スカウト履歴', 'メモ・備考', '候補者評価', 'スカウト送信履歴'];
  let cutIdx = text.length;
  for (const marker of stopMarkers) {
    const idx = text.indexOf(marker);
    if (idx > 50 && idx < cutIdx) cutIdx = idx;
  }
  return text.substring(0, cutIdx).trim();
}

function extractMainText(root, limit) {
  limit = limit || 2500;
  const excludeTags = ['script','style','noscript','nav','footer','header',
    'aside','button','select','option','meta','link'];
  const excludeRoles = ['navigation','banner','contentinfo','complementary'];

  function shouldExclude(el) {
    if (excludeTags.includes((el.tagName || '').toLowerCase())) return true;
    const role = el.getAttribute ? (el.getAttribute('role') || '') : '';
    if (excludeRoles.includes(role)) return true;
    const cls = (el.className || '').toString().toLowerCase();
    if (/\b(nav|menu|header|footer|sidebar|breadcrumb|pagination)\b/.test(cls)) return true;
    return false;
  }

  const target = root ||
    document.querySelector('main') ||
    document.querySelector('[role="main"]') ||
    document.querySelector('#main') ||
    document.body;

  let text = '';
  target.querySelectorAll('*').forEach(el => {
    if (shouldExclude(el)) return;
    el.childNodes.forEach(node => {
      if (node.nodeType === 3) {
        const t = node.textContent.trim();
        if (t.length > 1) text += t + '\n';
      }
    });
  });

  return text.replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim().substring(0, limit);
}

// -------------------------------------------------------
// プロフィールらしいテキストかを判定
// -------------------------------------------------------
const PROFILE_KEYWORDS = ['職務経歴', '職歴', '学歴', 'スキル', '自己PR', '資格', '語学', '業務内容', '転職理由', '希望年収'];

function hasProfileContent(text) {
  return PROFILE_KEYWORDS.filter(kw => text.includes(kw)).length >= 2;
}

// -------------------------------------------------------
// RDS詳細パネルを特定する
// -------------------------------------------------------
function findRDSDetailPanel() {
  const candidates = [];

  // 方法1: 「候補者詳細」見出しを持つ親コンテナ
  document.querySelectorAll('h1,h2,h3,h4,h5,h6,div,span').forEach(el => {
    const t = (el.innerText || el.textContent || '').trim();
    if (t !== '候補者詳細' && t !== '候補者 詳細') return;
    let parent = el.parentElement;
    for (let i = 0; i < 8; i++) {
      if (!parent) break;
      const rect = parent.getBoundingClientRect();
      const innerText = (parent.innerText || '').trim();
      if (rect.width > 300 && innerText.length > 200) {
        candidates.push({ el: parent, score: innerText.length });
        break;
      }
      parent = parent.parentElement;
    }
  });

  // 方法2: 右側寄りの大きなコンテナをスコアリング
  if (candidates.length === 0) {
    const viewportWidth = window.innerWidth;
    document.querySelectorAll('div, section, article, main').forEach(el => {
      const rect = el.getBoundingClientRect();
      if (rect.left > viewportWidth * 0.35 && rect.width > 300 && rect.height > 400) {
        const innerText = (el.innerText || '').trim();
        if (innerText.length > 200) candidates.push({ el, score: innerText.length });
      }
    });
  }

  if (candidates.length === 0) return null;
  candidates.sort((a, b) => b.score - a.score);
  return candidates[0].el;
}

// -------------------------------------------------------
// マイナビの詳細パネルを特定する
// -------------------------------------------------------
function findMynaviDetailPanel() {
  const keywords = ['職務経歴', '職歴', 'スキル', '自己PR', '保有資格', '最終学歴'];
  const viewportWidth = window.innerWidth;

  const candidates = [];
  document.querySelectorAll('div, section, article, main').forEach(el => {
    const t = (el.innerText || '').trim();
    if (t.length < 200 || t.length > 15000) return;

    const hasKeyword = keywords.some(kw => t.includes(kw));
    if (!hasKeyword) return;

    const rect = el.getBoundingClientRect();
    const isRightPane = rect.left > viewportWidth * 0.3;
    const score = t.length * (isRightPane ? 2 : 1);
    candidates.push({ el, score });
  });

  if (candidates.length === 0) return null;
  candidates.sort((a, b) => b.score - a.score);
  return candidates[0].el;
}

// -------------------------------------------------------
// メイン抽出関数
// -------------------------------------------------------
function extractProfile() {
  const host = location.hostname;
  const url  = location.href;
  let text   = '';
  let detailPanel = null;

  if (host.includes('bizreach') || host.includes('es-support')) {
    text = extractBySelectors([
      '[class*="profile"]', '[class*="career"]',
      '[class*="resume"]', '[class*="skill"]',
      '[class*="pr"]', '[class*="history"]', '[class*="work"]',
      '[class*="scout"]', '[class*="Scout"]',
      'section', 'article'
    ]);

    if (!text || text.trim().length < 100) {
      text = extractByKeywords([
        '職務経歴', '職歴', 'スキル', '業務内容', '実績',
        '学歴', '語学', '資格', '自己PR', '希望条件'
      ]);
    }

  } else if (host.includes('doda-x') || host.includes('dodax') || url.includes('doda-x')) {
    text = extractBySelectors([
      '[class*="workHistory"]', '[class*="work-history"]',
      '[class*="career"]', '[class*="summary"]',
      '[class*="skill"]', '[class*="resume"]',
      '[class*="profile"]', 'section', 'article'
    ]);

  } else if (host.includes('rikunabi') || host.includes('hrtech')) {
    detailPanel = findRDSDetailPanel();

    if (detailPanel) {
      const byKeyword = extractByKeywords([
        '職務経歴', '職歴', '職務要約', '業務内容',
        'スキル', '技術', '開発言語', '資格',
        '学歴', '最終学歴', '大学', '大学院',
        '語学', '英語', 'TOEIC',
        '自己PR', 'PR', 'アピール',
        '希望', '年収', '転職理由',
        '経験業種', '経験職種', '経験社数'
      ], detailPanel);

      const bySelector = extractBySelectors([
        '[class*="resume"]', '[class*="Resume"]',
        '[class*="career"]', '[class*="Career"]',
        '[class*="history"]', '[class*="History"]',
        '[class*="skill"]', '[class*="Skill"]',
        '[class*="profile"]', '[class*="Profile"]',
        '[class*="summary"]', '[class*="Summary"]',
        '[class*="experience"]', '[class*="Experience"]',
        '[class*="education"]', '[class*="Education"]',
        'section', 'article', 'table'
      ], detailPanel);

      text = byKeyword.length >= bySelector.length ? byKeyword : bySelector;
      text = removeNonProfileSections(text);

      if (text.length < 100) {
        text = removeNonProfileSections(extractMainText(detailPanel, 2500));
      }
    } else {
      text = extractByKeywords([
        '職務経歴', '職歴', '職務要約',
        'スキル', '資格', '学歴',
        '語学', '自己PR', 'アピール',
        '希望年収', '年収', '転職理由'
      ]);

      if (text.length < 100) {
        text = extractBySelectors([
          '[class*="resume"]', '[class*="career"]',
          '[class*="history"]', '[class*="skill"]',
          '[class*="profile"]', '[class*="summary"]',
          '[class*="candidate"]', '[class*="detail"]',
          'section', 'article', 'table'
        ]);
      }
    }

  } else if (host.includes('green-japan')) {
    text = extractByKeywords([
      '職務経歴', '経験業種', 'スキル', '最終学歴', '語学',
      '経験業界', '経験職種', '資格', 'スカウト希望', '希望業界',
      '希望職種', '希望勤務地', '転職先に求める', '自己PR'
    ]);

  } else if (host.includes('ambi') || host.includes('en-ambi')) {
    const viewportWidth = window.innerWidth;
    const candidates = [];
    document.querySelectorAll('div, section, article, main').forEach(el => {
      const rect = el.getBoundingClientRect();
      const t = (el.innerText || '').trim();
      if (rect.left > viewportWidth * 0.3 && rect.width > 300 && t.length > 200 && t.length < 15000) {
        const hasKeyword = ['職務経歴', '職歴', 'スキル', '経験職種', '学歴', '語学'].some(kw => t.includes(kw));
        if (hasKeyword) candidates.push({ el, score: t.length });
      }
    });

    if (candidates.length > 0) {
      candidates.sort((a, b) => b.score - a.score);
      detailPanel = candidates[0].el;
      text = extractMainText(detailPanel, 2500);
    }

    if (!text || text.trim().length < 100) {
      text = extractByKeywords([
        '職務経歴', '職歴', 'スキル', '経験職種',
        '学歴', '語学', '資格', '自己PR', '希望条件'
      ]);
    }

  } else if (host.includes('mynavi')) {
    detailPanel = findMynaviDetailPanel();
    const root = detailPanel || null;

    const byKeyword = extractByKeywords([
      '職務経歴', '職歴', '業務内容', '仕事内容',
      'スキル', '保有資格', '資格', '語学',
      '学歴', '最終学歴', '大学',
      '自己PR', 'アピール',
      '希望条件', '希望職種', '希望業界', '希望年収',
      '現在の年収', '転職理由', '直近', '経験職種'
    ], root);

    const bySelector = extractBySelectors([
      '[class*="profile"]', '[class*="Profile"]',
      '[class*="career"]', '[class*="Career"]',
      '[class*="resume"]', '[class*="Resume"]',
      '[class*="skill"]', '[class*="Skill"]',
      '[class*="history"]', '[class*="History"]',
      '[class*="work"]', '[class*="Work"]',
      '[class*="experience"]', '[class*="Experience"]',
      '[class*="education"]', '[class*="Education"]',
      '[class*="candidate"]', '[class*="Candidate"]',
      '[class*="detail"]', '[class*="Detail"]',
      '[class*="info"]', '[class*="Info"]',
      '[class*="summary"]', '[class*="Summary"]',
      'section', 'article', 'table'
    ], root);

    text = byKeyword.length >= bySelector.length ? byKeyword : bySelector;

    if (!text || text.length < 100) {
      text = extractMainText(root, 2500);
    }

  } else if (host.includes('recruitdirect') || host.includes('rds')) {
    text = extractBySelectors([
      '[class*="profile"]', '[class*="career"]',
      '[class*="resume"]', '[class*="skill"]',
      '[class*="history"]', '[class*="work"]',
      '[class*="candidate"]', '[class*="detail"]',
      'section', 'article', 'table'
    ]);

  } else {
    text = extractMainText(null, 2500);
  }

  if (!text || text.trim().length < 80) {
    text = extractMainText(null, 2500);
  }

  return text
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
    .substring(0, 2500);
}

// -------------------------------------------------------
// メッセージリスナー
// -------------------------------------------------------
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  // async処理を含むハンドラはIIFEでラップ
  if (request.action === 'getBatchCandidates') {
    (async () => {
      try {
        injectStyles();
        showAutoStatus('📥 候補者を全件読み込み中...');
        await loadAllCandidatesIntoDOM();
        const cards = extractAllCandidateCards();
        cards.forEach(c => {
          if (getComputedStyle(c.el).position === 'static') c.el.style.position = 'relative';
          c.el.classList.add('snow-we-selected');
          const badge = document.createElement('div');
          badge.className = 'snow-we-badge checking';
          badge.textContent = '🔍 判定中...';
          c.el.appendChild(badge);
        });
        sendResponse({ success: true, cards: cards.map(c => ({ summary: c.summary, age: c.age, incomeText: c.incomeText, text: c.text.substring(0, 900) })) });
      } catch (e) {
        sendResponse({ success: false, error: e.message });
      }
    })();
    return true;
  }
  if (request.action === 'setBatchResults') {
    try {
      const cards = extractAllCandidateCards();
      const results = request.results || [];
      results.forEach((r, i) => {
        if (!cards[i]) return;
        const el = cards[i].el;
        el.querySelectorAll('.snow-we-badge').forEach(b => b.remove());
        const map = { OK: ['ok', '✅ スカウト推奨'], NG: ['ng', '❌ 見送り'], '要確認': ['warn', '⚠️ 要確認'] };
        const [cls, text] = map[r.overall] || ['warn', '⚠️ 要確認'];
        const badge = document.createElement('div');
        badge.className = `snow-we-badge batch ${cls}`;
        badge.textContent = text;
        el.appendChild(badge);
      });
      sendResponse({ success: true });
    } catch (e) {
      sendResponse({ success: false, error: e.message });
    }
  }

  if (request.action === 'showBadgeChecking') {
    injectStyles();
    showBadge('checking', '🔍 判定中...');
    sendResponse({ success: true });
  }

  if (request.action === 'showBadgeResult') {
    const map = { OK: ['ok', '✅ スカウト推奨'], NG: ['ng', '❌ 見送り'], '要確認': ['warn', '⚠️ 要確認'] };
    const [cls, text] = map[request.overall] || ['warn', '⚠️ 要確認'];
    showBadge(cls, text);
    sendResponse({ success: true });
  }

  if (request.action === 'clearBadge') {
    document.querySelectorAll('.snow-we-badge').forEach(b => b.remove());
    document.querySelectorAll('.snow-we-selected').forEach(el => el.classList.remove('snow-we-selected'));
    _selectedCard = null;
    sendResponse({ success: true });
  }

  if (request.action === 'getProfile') {
    try {
      const profileText = extractProfile();
      const isRDS = location.hostname.includes('rikunabi') || location.hostname.includes('hrtech');
      const looksEmpty = !hasProfileContent(profileText);

      if (isRDS && looksEmpty) {
        sendResponse({
          success: false,
          needsCandidateSelection: true,
          profileText: '',
          error: '候補者が選択されていません'
        });
      } else {
        sendResponse({
          success: true,
          profileText,
          url: location.href,
          hostname: location.hostname,
          length: profileText.length
        });
      }
    } catch (e) {
      sendResponse({
        success: false,
        profileText: '',
        error: e.message
      });
    }
  }

  if (request.action === 'triggerAutoAdd') {
    triggerAutoAdd();
    sendResponse({ success: true });
  }

  if (request.action === 'debugDOM') {
    try {
      const info = {
        url: location.href,
        hostname: location.hostname,
        detailPanelFound: !!findRDSDetailPanel(),
        selectorHits: {
          'resume': document.querySelectorAll('[class*="resume"]').length,
          'career': document.querySelectorAll('[class*="career"]').length,
          'history': document.querySelectorAll('[class*="history"]').length,
          'candidate': document.querySelectorAll('[class*="candidate"]').length,
          'detail': document.querySelectorAll('[class*="detail"]').length,
          'section': document.querySelectorAll('section').length,
        },
        headings: Array.from(document.querySelectorAll('h1,h2,h3,h4')).map(h => h.innerText?.trim()).filter(Boolean).slice(0, 20),
        previewText: extractProfile().substring(0, 200)
      };
      sendResponse({ success: true, info });
    } catch (e) {
      sendResponse({ success: false, error: e.message });
    }
  }

  return true;
});
