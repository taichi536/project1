// content.js v1.5.10
// 各媒体のプロフィールページからテキストを抽出する

// ポジション要件のセッション内キャッシュ（GAS呼び出しを最小化）
const _posReqCache = new Map();

// Bizreach仮想スクロール対応：バッジ状態レジストリ
const _bizreachBadgeRegistry = new Map(); // resumeId → {cls, text, tooltip, profileSummary, aiVerdict}
let _bizreachObserver = null;
let _reapplyBizreachTimer = null;


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
    .snow-we-badge.ok       { background: #059669 !important; color: #fff !important; cursor: pointer !important; pointer-events: auto !important; }
    .snow-we-badge.ng       { background: #DC2626 !important; color: #fff !important; cursor: pointer !important; pointer-events: auto !important; }
    .snow-we-badge.warn     { background: #D97706 !important; color: #fff !important; cursor: pointer !important; pointer-events: auto !important; }
    .snow-we-badge.corrected { background: #6366F1 !important; color: #fff !important; }
    .snow-we-badge.ok:hover, .snow-we-badge.ng:hover, .snow-we-badge.warn:hover {
      filter: brightness(1.15) !important;
    }
    .snow-we-fb-popup {
      position: absolute !important; top: 28px !important; right: 6px !important;
      background: #1e1b4b !important; border-radius: 8px !important; padding: 6px 8px !important;
      z-index: 9999999 !important; display: flex !important; flex-direction: column !important;
      gap: 4px !important; box-shadow: 0 4px 16px rgba(0,0,0,.5) !important; min-width: 130px !important;
    }
    .snow-we-fb-popup span {
      color: #a5b4fc !important; font-size: 10px !important; font-weight: 600 !important;
      padding: 0 2px 2px !important; font-family: -apple-system, sans-serif !important;
    }
    .snow-we-fb-row { display: flex !important; gap: 4px !important; }
    .snow-we-fb-btn {
      flex: 1 !important; font-size: 11px !important; font-weight: 700 !important;
      padding: 5px 0 !important; border-radius: 12px !important; border: none !important;
      cursor: pointer !important; color: #fff !important; font-family: -apple-system, sans-serif !important;
    }
    .snow-we-fb-btn.ok { background: #059669 !important; }
    .snow-we-fb-btn.ng { background: #DC2626 !important; }
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
    // ess-resume-list-item を直接選択（broad selector による phantom element を排除）
    const items = Array.from(document.querySelectorAll('ess-resume-list-item'));
    if (items.length > 0) {
      return dedup(items.filter(el => {
        const text = el.innerText || '';
        return agePattern.test(text) && text.length > 50;
      }));
    }
    // フォールバック：ess-resume-list-item が見つからない場合は旧ロジック
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
  // Bizreach: 星ボタン（ess-star-icon-toggle）をハイライト
  if (platform === 'bizreach') {
    const btn = findBizreachStarButton(cardEl);
    if (!btn) return;
    btn.classList.add('snow-we-btn-highlight');
    if (getComputedStyle(btn).position === 'static') btn.style.position = 'relative';
    const tip = document.createElement('span');
    tip.className = 'snow-we-btn-tip';
    tip.textContent = '★';
    btn.appendChild(tip);
    return;
  }

  // doda-x: 星ボタンをハイライト
  if (platform === 'dodax') {
    const searchRoot = cardEl.closest('li, [class*="result"], [class*="member"], [class*="item"]') || cardEl;
    const starBtn = searchRoot.querySelector('.c-star-cts');
    if (!starBtn) return;
    starBtn.classList.add('snow-we-btn-highlight');
    return;
  }

  const btnTextMap = {
    ambi:     'この検討人材リストに追加',
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
    // アクションボタン（スカウト送信など）のクリックでは選択カードを上書きしない
    const btn = e.target.closest('button, a');
    const btnText = (btn?.innerText || '').trim();
    if (btnText === 'スカウト' || btnText.includes('スカウトを送る') || btnText.includes('スカウトする')) return;

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
const RESCOUNT_DAYS = 7; // 1週間 = 7日

async function getScoutHistory() {
  const r = await chrome.storage.local.get([SCOUT_KEY]);
  return r[SCOUT_KEY] || {};
}

async function recordScoutSent(candidateId, info, templateName) {
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
    const payload = {
      secret: gas.secret,
      recruiter: gas.recruiter,
      company: info.company || '',
      age: ageNum,
      univ: info.univ || '',
      media: platform,
      position: templateName || r2.currentPosition || '',
      ts: now,
    };

    // バックグラウンド経由でGASへ送信（content.jsから直接fetchするとCORS/401になるため）
    chrome.runtime.sendMessage({ type: 'gasPost', url: gas.url, payload })
      .catch(err => console.error('[Snow-we] GAS送信エラー (daily):', err));
    if (gas.dbUrl) {
      chrome.runtime.sendMessage({ type: 'gasPost', url: gas.dbUrl, payload })
        .catch(err => console.error('[Snow-we] GAS送信エラー (db):', err));
    }
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
  // Bizreach: cardEl が ess-resume-list-item 自身（新セレクタ）または祖先に持つ場合
  if (getPlatform() === 'bizreach') {
    // 直接 id を持つ場合
    if (cardEl.id && cardEl.id.startsWith('resume-')) return `bizreach_${cardEl.id}`;
    // 子要素の bui-drawer-trigger に id がある（実際のBizreach構造）
    const drawer = cardEl.querySelector('bui-drawer-trigger[id^="resume-"]');
    if (drawer?.id) return `bizreach_${drawer.id}`;
    // 祖先を探す（念のため）
    let el = cardEl.parentElement;
    for (let i = 0; i < 8; i++) {
      if (!el) break;
      if (el.id?.startsWith('resume-')) return `bizreach_${el.id}`;
      el = el.parentElement;
    }
    // フォールバック：カードテキストのフィンガープリント
    const fpLines = (cardEl.innerText || '').split('\n').map(l => l.trim()).filter(l => l.length > 3);
    const fp = fpLines.slice(0, 8).join('|');
    if (fp.length > 20) return `bizreach_fp_${simpleHash(fp)}`;
    return null;
  }

  const url = findProfileUrl(cardEl);
  if (url) return url.replace(/[?#].*$/, ''); // クエリ・ハッシュを除去

  const text = (cardEl.innerText || '');

  // フォールバック1：カードテキストから候補者番号を抽出
  const m = text.match(/No\.(\d{5,})|^(\d{6,})\s/m) ||
            text.match(/\b([0-9]{6,10})\b/);
  if (m) return `${getPlatform()}_${m[1] || m[2]}`;

  // フォールバック2：年齢+会社名+経歴先頭のハッシュ（RDS等URL取得不可の場合）
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
  const fingerprint = lines.slice(0, 5).join('|');
  if (fingerprint.length > 10) return `${getPlatform()}_h${simpleHash(fingerprint)}`;

  return null;
}

// カードから基本情報を抽出（履歴保存用）
function extractBasicInfo(cardEl) {
  const text = (cardEl.innerText || '');
  const ageMatch = text.match(/(\d{2,3})歳/);
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);

  // 大学名を抽出
  let univ = '';
  const univMatch = text.match(/([^\s\n　]{1,20}(?:大学院|大学|高専|専門学校))/);
  if (univMatch) {
    univ = cleanUnivName(univMatch[1]);
  }
  // RDS/AMBIはカードに大学名が出ないため、詳細パネルからも取得を試みる
  if (!univ) {
    const platform = getPlatform();
    const panel = platform === 'rds' ? findRDSDetailPanel() : findAMBIDetailPanel();
    if (panel) {
      const panelText = panel.innerText || '';
      const panelUnivMatch = panelText.match(/([^\s\n　]{1,20}(?:大学院|大学|高専|専門学校))/);
      if (panelUnivMatch) {
        univ = cleanUnivName(panelUnivMatch[1]);
      }
    }
  }

  // 会社名を抽出
  let company = '';
  if (getPlatform() === 'ambi') {
    // AMBIカード: 「業界 / 部署」行の直前が会社名
    const industryIdx = lines.slice().reverse().findIndex(l => l.includes(' / '));
    if (industryIdx >= 0) {
      const realIdx = lines.length - 1 - industryIdx;
      if (realIdx > 0) company = lines[realIdx - 1];
    }
    // フォールバック: 株式会社等を含む行
    if (!company) {
      company = lines.find(l => /株式会社|合同会社|有限会社|LLC|Inc\.|Co\.,/.test(l)) || '';
    }
  } else if (getPlatform() === 'rds') {
    const idx = lines.findIndex(l => l === '現職' || l === '前職');
    const companyRe = /株式会社|合同会社|有限会社|LLC|Inc\.|Co\.,|ホールディングス|グループ|銀行|証券|保険|大学|病院/;
    if (idx >= 0) {
      // 現職/前職の前後5行で、会社名キーワードを含む最も近い行を使う
      let bestLine = '';
      let bestDist = Infinity;
      for (let i = Math.max(0, idx - 5); i < Math.min(lines.length, idx + 5); i++) {
        if (i === idx) continue;
        const line = lines[i];
        if (!line || line.length < 2) continue;
        if (companyRe.test(line) || (line.includes('／') && line.length > 4)) {
          const dist = Math.abs(i - idx);
          if (dist < bestDist) { bestDist = dist; bestLine = line; }
        }
      }
      if (bestLine) company = bestLine.split(/[／/]/)[0].trim();
    }
    if (!company) {
      // フォールバック：ページ全体で会社名キーワードを含む行
      company = lines.find(l => companyRe.test(l))?.split(/[／/]/)[0].trim() || '';
    }
  } else {
    company = lines[0] || '';
  }

  return {
    age: ageMatch ? `${ageMatch[1]}歳` : '',
    company,
    univ,
    name: '',
  };
}

// スカウトボタンのクリックを検知して履歴に記録
document.addEventListener('click', e => {
  const btn = e.target.closest('button, a');
  if (!btn) return;
  const text = (btn.innerText || '').trim();

  const isScoutBtn           = text === 'スカウト' || text.includes('スカウトを送る') || text.includes('スカウトする');
  const isConfirmBtn         = text === '確認';
  const isSendBtn            = text === '送信' || text === '送信する';
  const isTemplateConfirmBtn = text === '確定';
  if (!isScoutBtn && !isConfirmBtn && !isSendBtn && !isTemplateConfirmBtn) return;

  console.log('[Snow-we] スカウト系ボタン検知:', JSON.stringify(text));

  // ── スカウトボタン：候補者カードを特定して保存 ──
  if (isScoutBtn) {
    const cards = findCandidateCardsByPlatform();
    let card = cards.find(c => c.contains(btn) || c === btn.closest('[class*="card"],[class*="row"],li,article'));

    if (!card) {
      if (_selectedCard) {
        card = _selectedCard;
      } else {
        const btnRect = btn.getBoundingClientRect();
        const btnCenter = btnRect.top + btnRect.height / 2;
        let minDist = Infinity;
        for (const c of cards) {
          const r = c.getBoundingClientRect();
          const dist = Math.abs((r.top + r.height / 2) - btnCenter);
          if (dist < minDist) { minDist = dist; card = c; }
        }
        if (minDist > 300) card = null;
      }
    }

    console.log('[Snow-we] カード検出:', card ? 'あり' : 'なし', '/ _selectedCard:', _selectedCard ? 'あり' : 'なし', '/ カード総数:', cards.length);

    if (card) {
      const id = getCandidateId(card);
      console.log('[Snow-we] 1回目クリック candidateId:', id);
      console.log('[Snow-we] カードテキスト行:', (card.innerText || '').split('\n').map(l=>l.trim()).filter(Boolean).slice(0,10));
      if (id) {
        sessionStorage.setItem('pendingScout', JSON.stringify({
          id, info: extractBasicInfo(card), ts: Date.now()
        }));
        console.log('[Snow-we] pendingScout を sessionStorage に保存しました');
      } else {
        console.log('[Snow-we] candidateId が取得できなかったため保存スキップ');
      }
    }
    return;
  }

  // ── 確定ボタン：テンプレート選択モーダルからポジション照合（RDS等） ──
  if (isTemplateConfirmBtn) {
    const raw = sessionStorage.getItem('pendingScout');
    if (!raw) return;

    // ★ モーダルが閉じる前に同期的にテンプレート名を取得する（非同期にすると消える）
    const checkedRadio = document.querySelector('input[type="radio"]:checked');
    let tmplName = '';
    if (checkedRadio) {
      const row = checkedRadio.closest('tr, [role="row"]') || checkedRadio.closest('li, [class*="row"], [class*="item"]');
      if (row) {
        for (const cell of row.querySelectorAll('td, [role="cell"]')) {
          if (cell.querySelector('input')) continue;
          const t = cell.textContent?.trim() || '';
          if (t.length > 3) { tmplName = t; break; }
        }
        if (!tmplName) {
          for (const el of row.querySelectorAll('div, span, p')) {
            if (el.querySelector('input, button')) continue;
            const t = el.textContent?.trim() || '';
            if (t.length > 3 && t.length < 80) { tmplName = t; break; }
          }
        }
      }
    }
    if (!tmplName) return;
    console.log('[Snow-we] テンプレート名検出 (同期取得):', tmplName);

    (async () => {
      try {
        const pending = JSON.parse(raw);
        if (pending.templateName) return;

        const res = await chrome.runtime.sendMessage({ type: 'getPositionList' });
        const positionList = res?.positions || [];
        const normT = s => s
          .replace(/^[A-Za-z]+[）)]\s*/u, '')
          .replace(/[（]/g, '(').replace(/[）]/g, ')')
          .replace(/　/g, ' ').replace(/\s*[-－–—]\s*/g, '-')
          .trim().toLowerCase();
        // 末尾の部署コード・チーム名を除去（大文字小文字・日本語対応）
        const stripSuffix = p => p
          .replace(/\s*[-–—－]\s*[A-Za-z]{2,}[\s）)]*$/, '')
          .replace(/\s*[-–—－]\s*[゠-ヿ一-鿿]{2,}[\s）)]*$/, '')
          .trim();

        const sorted = [...positionList].sort((a, b) => b.length - a.length);
        const matched = sorted.find(p => {
          if (!p) return false;
          // 1. 完全一致
          if (normT(tmplName) === normT(p)) return true;
          // 2. 部署コード等のサフィックスを除いたタイトルで照合
          const title = stripSuffix(p);
          if (title.length >= 8 && normT(tmplName).includes(normT(title))) return true;
          // 3. " - " で分割した先頭コア部分で照合（最終手段）
          const core = p.split(/\s[-–—－]\s/)[0].trim();
          if (core.length >= 8 && normT(tmplName).includes(normT(core))) return true;
          return false;
        }) || '';
        console.log('[Snow-we] テンプレート照合試行: tmplName=', tmplName, '/ matched=', matched || 'なし');

        if (matched) {
          pending.templateName = matched;
          sessionStorage.setItem('pendingScout', JSON.stringify(pending));
          console.log('[Snow-we] テンプレート名からポジション照合成功:', matched);
        } else {
          console.log('[Snow-we] テンプレート名照合失敗. tmplName=', tmplName);
        }
      } catch (err) {
        console.log('[Snow-we] 確定ハンドラエラー:', err);
      }
    })();
    return;
  }

  // ── 確認ボタン：メール本文からポジションを照合 ──
  if (isConfirmBtn) {
    const raw = sessionStorage.getItem('pendingScout');
    if (!raw) return;
    (async () => {
      try {
        const pending = JSON.parse(raw);
        const bodyEl = document.querySelector('textarea') ||
                       document.querySelector('[contenteditable="true"]');
        const bodyText = bodyEl ? bodyEl.value || bodyEl.innerText || '' : document.body.innerText;

        let matched = '';
        try {
          const res = await chrome.runtime.sendMessage({ type: 'getPositionList' });
          const positionList = res?.positions || [];
          console.log('[Snow-we] ポジション一覧件数:', positionList.length, '/ 先頭3件:', positionList.slice(0, 3));
          console.log('[Snow-we] メール本文先頭200字:', bodyText.substring(0, 200));
          const sorted = [...positionList].sort((a, b) => b.length - a.length);
          const stripSuffix2 = p => p
            .replace(/\s*[-–—－]\s*[A-Za-z]{2,}[\s）)]*$/, '')
            .replace(/\s*[-–—－]\s*[゠-ヿ一-鿿]{2,}[\s）)]*$/, '')
            .trim();
          // 1. 完全一致 → 2. サフィックス除いたタイトルで照合 → 3. コア部分で照合
          matched = sorted.find(p => {
            if (!p) return false;
            if (bodyText.includes(p)) return true;
            const title = stripSuffix2(p);
            if (title && title.length >= 8 && bodyText.includes(title)) return true;
            const core = p.split(/\s[-–—－]\s/)[0].trim();
            if (core && core.length >= 8 && bodyText.includes(core)) return true;
            return false;
          }) || '';
        } catch (_) {}

        if (matched) {
          pending.templateName = matched;
          sessionStorage.setItem('pendingScout', JSON.stringify(pending));
          console.log('[Snow-we] ポジション照合成功:', matched);
        } else {
          console.log('[Snow-we] ポジション照合できず（本文にポジション名が見つかりません）');
        }
      } catch (_) {}
    })();
    return;
  }

  // ── 送信ボタン：スカウト記録 ──
  const raw = sessionStorage.getItem('pendingScout');
  console.log('[Snow-we] 送信クリック / pendingScout:', raw ? 'あり' : 'なし');
  sessionStorage.removeItem('pendingScout');
  if (raw) {
    (async () => {
      try {
        const pending = JSON.parse(raw);
        if (pending && pending.id && Date.now() - pending.ts < 30 * 60 * 1000) {
          // AMBIはテンプレートドロップダウンからポジションを取得
          if (!pending.templateName && getPlatform() === 'ambi') {
            const tmplSel = document.querySelector('select');
            const tmplVal = tmplSel ? (tmplSel.options[tmplSel.selectedIndex]?.text || '').trim() : '';
            if (tmplVal && tmplVal !== 'テンプレートの選択') {
              const res = await chrome.runtime.sendMessage({ type: 'getPositionList' });
              const positionList = res?.positions || [];
              const sorted = [...positionList].sort((a, b) => b.length - a.length);
              pending.templateName = sorted.find(p => {
                if (!p) return false;
                if (tmplVal.includes(p)) return true;
                const core = p.split(/[（(【]/)[0].split(/\s[-–—]\s|\s[-–—]$/)[0].trim();
                return core.length >= 6 && tmplVal.includes(core);
              }) || '';
            }
          }
          console.log('[Snow-we] recordScoutSent 呼び出し id:', pending.id, '/ template:', pending.templateName || 'なし');
          recordScoutSent(pending.id, pending.info || {}, pending.templateName || '');
        }
      } catch (_) {}
    })();
  }
}, true);

// -------------------------------------------------------
// 「さらに読み込む」ボタンを押して全候補者をDOMに展開
// -------------------------------------------------------
async function loadAllCandidatesIntoDOM() {
  const platform = getPlatform();
  // BizreachはCDK仮想スクロールのため window.scrollTo では新カードをロードできない
  // 仮想スクロールの制御はtriggerAutoAdd内の再帰スクロールループで行う
  if (platform === 'bizreach') return;

  const LOAD_MORE_TEXTS = ['さらに読み込む', 'もっと見る', 'Load more', '次の候補者'];
  const MAX_LOADS = 40;
  const TARGET_COUNT = 700; // 600人目標 + バッファ

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
    const countBefore = findCandidateCardsByPlatform().length;
    if (countBefore >= TARGET_COUNT) break; // 目標人数に達したら終了

    showAutoStatus(`📥 さらに読み込み中... (${countBefore}人 読み込み済み)`);
    await scrollToBottom();

    const btn = findLoadMoreBtn();
    if (btn) btn.click();

    await new Promise(r => setTimeout(r, 2000));
    const countAfter = findCandidateCardsByPlatform().length;

    loaded++;
    if (countAfter <= countBefore) break; // 増えなければ終了（全員読み込み済み）
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
  const apiKey = (stored.apiKey || '').replace(/[^\x21-\x7E]/g, '').trim();
  if (!apiKey || apiKey.length < 20) return; // APIキー未設定なら何もしない

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

      const [cls, text] = r.overall === 'OK' ? ['ok', '✅ スカウト候補']
                        : r.overall === 'NG' ? ['ng', '❌ 見送り']
                        : ['warn', '⚠️ 要確認'];
      setBatchBadge(el, cls, text, '', cards[i].summary?.substring(0, 200) || '', r.overall);

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

// Claude API fetch with retry on 529 (overloaded)
async function claudeFetch(apiKey, body, maxRetries = 4) {
  let delay = 3000;
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true'
      },
      body: JSON.stringify(body)
    });
    if (response.status === 529) {
      if (attempt === maxRetries) throw new Error('APIが混み合っています。しばらく待ってから再試行してください。');
      showAutoStatus(`APIが混み合っています。${delay / 1000}秒後にリトライ... (${attempt + 1}/${maxRetries})`, delay - 200);
      await sleep(delay);
      delay = Math.min(delay * 2, 30000);
      continue;
    }
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.error?.message || `APIエラー (${response.status})`);
    }
    return response.json();
  }
}

// プロフィールテキストの配列をバッチ判定する
async function judgeProfileBatch(apiKey, profileTexts, criteria) {
  const criteriaLines = buildCriteriaText(criteria, getPlatform());
  const candidateList = profileTexts.map((t, i) =>
    `候補者${i + 1}:\n${t.slice(0, 2000)}`
  ).join('\n\n');

  const prompt = `転職エージェントの一次選定アシスタントです。

【選定基準】
${criteriaLines}

【候補者一覧】
${candidateList}

必ず以下のJSON形式のみで出力してください。説明・前置き・コードブロック不要。
{"results":[{"i":1,"o":"OK"},{"i":2,"o":"NG"}]}
※必ず${profileTexts.length}人分出力すること。oはOK/NG/要確認のいずれか。`;

  const data = await claudeFetch(apiKey, {
    model: 'claude-haiku-4-5-20251001',
    max_tokens: 600,
    messages: [{ role: 'user', content: prompt }]
  });
  const text = (data.content?.[0]?.text || '').trim();
  // コードブロックや前後のテキストを除去してJSONオブジェクト部分だけ抽出
  const jsonMatch = text.match(/\{[\s\S]*\}/);
  if (!jsonMatch) throw new Error('JSON not found: ' + text.slice(0, 80));
  const parsed = JSON.parse(jsonMatch[0]);
  return (parsed.results || []).map(r => r.overall || r.o || '要確認');
}

// Claude APIを呼び出す（content.js内から直接）
async function callBatchScreeningAPI(apiKey, cards, criteria) {
  const criteriaLines = buildCriteriaText(criteria, getPlatform());
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

  const data = await claudeFetch(apiKey, {
    model: 'claude-sonnet-4-6',
    max_tokens: 2000,
    messages: [{ role: 'user', content: prompt }]
  });
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
    await saveAutoAddProgress({ running: false });
    return;
  }

  const criteria = stored.screeningCriteria || {};
  injectStyles();

  showAutoStatus('📥 読み込み中...');

  // ページをまたいで処理するため、進捗をストレージで管理（バッジ消去前に確認）
  const progress = await loadAutoAddProgress();
  const isFreshStart = !progress.running; // running=true なら再帰呼び出し

  // Bizreach再帰呼び出し時はバッジを消去しない（仮想スクロールで再表示されたカードのバッジが消えるため）
  if (getPlatform() !== 'bizreach' || isFreshStart) {
    document.querySelectorAll('.snow-we-badge.batch').forEach(b => b.remove());
    if (getPlatform() === 'bizreach') {
      _bizreachBadgeRegistry.clear();
      if (_bizreachObserver) { _bizreachObserver.disconnect(); _bizreachObserver = null; }
    }
  }

  // Bizreachは仮想スクロール監視を開始
  if (getPlatform() === 'bizreach') startBizreachBadgeObserver();

  await loadAllCandidatesIntoDOM();

  const cards = extractAllCandidateCards();
  console.log('[Snow-we] triggerAutoAdd cards found:', cards.length, 'platform:', getPlatform(), 'url:', location.href);
  if (cards.length === 0) {
    showAutoStatus('❌ 候補者が見つかりません。一覧ページで実行してください。', 4000);
    await saveAutoAddProgress({ running: false });
    return;
  }

  let addedCount = progress.added || 0;
  let totalProcessed = progress.processed || 0;

  const isRDS = getPlatform() === 'rds';
  // RDSはパネルを信頼するためストレージ不要。他媒体のみ取得
  const scoutHistory = isRDS ? {} : await getScoutHistory();

  // ─── 仮想スクロール用：セッション内の処理済みIDセット ───
  // 再帰呼び出し時に前バッチの候補者を再処理しないための dedup
  const BATCH_SESSION_KEY = 'snowWeBatchProcessed';
  if (isFreshStart) {
    sessionStorage.removeItem(BATCH_SESSION_KEY);
    sessionStorage.removeItem('snowWeBizreachStarred');
  }
  let batchProcessed;
  try {
    batchProcessed = new Set(JSON.parse(sessionStorage.getItem(BATCH_SESSION_KEY) || '[]'));
  } catch (_) { batchProcessed = new Set(); }

  // ─── 候補者を1人ずつ処理 ───
  const pending = []; // 処理済み記録用
  for (let i = 0; i < cards.length; i++) {
    const { el, text: cardText } = cards[i];
    showAutoStatus(`📥 ${i + 1}/${cards.length}人 プロフィール取得中...`);

    // Bizreach の仮想スクロール内では scrollIntoView が viewport と競合するためスキップ
    if (getPlatform() !== 'bizreach') {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      await sleep(400);
    }

    const candidateId = getCandidateId(el);

    // 仮想スクロール再帰時：前バッチで処理済みなら即スキップ
    if (candidateId && batchProcessed.has(candidateId)) {
      console.log('[Snow-we] 処理済みスキップ:', candidateId);
      continue;
    }
    // 処理開始前にマーク（失敗しても再処理しない）
    if (candidateId) {
      batchProcessed.add(candidateId);
      try { sessionStorage.setItem(BATCH_SESSION_KEY, JSON.stringify([...batchProcessed])); } catch (_) {}
    }

    if (!isRDS) {
      const status = scoutStatus(scoutHistory, candidateId);
      if (status.scouted && !status.reScoutable) {
        setBatchBadge(el, 'warn', `⏸ 送信済（${status.daysAgo}日前）`);
        totalProcessed++;
        continue;
      }
    }

    setBatchBadge(el, 'checking', '📥 取得中...');
    let profileText = cardText;
    try { profileText = await getFullProfile(el, cardText); } catch (_) {}

    if (isRDS) {
      // パネル内のみスクロール（リストをスクロールするとスカウト履歴検索が不正確になる）
      const rdsAutoPanel = findRDSDetailPanel();
      if (rdsAutoPanel) {
        let autoScrollTarget = rdsAutoPanel;
        rdsAutoPanel.querySelectorAll('*').forEach(el => {
          const s = window.getComputedStyle(el);
          if (s.overflowY !== 'scroll' && s.overflowY !== 'auto') return;
          if (el.getBoundingClientRect().height > 200) autoScrollTarget = el;
        });
        autoScrollTarget.scrollTop = autoScrollTarget.scrollHeight;
        await sleep(800);
      }
      const daysAgo = checkScoutSentInBody();
      if (daysAgo !== null && daysAgo < RESCOUNT_DAYS) {
        setBatchBadge(el, 'warn', `⏸ 送信済（${daysAgo}日前）`);
        totalProcessed++;
        await saveAutoAddProgress({ added: addedCount, processed: totalProcessed, running: true, ts: Date.now() });
        continue;
      }
    }

    // 年収チェック：IT閾値を下回る場合は即NG確定
    if (checkIncomeNG(profileText)) {
      setBatchBadge(el, 'ng', '❌ 見送り', '年収基準未満', profileText.substring(0, 200), 'NG');
      totalProcessed++;
      await saveAutoAddProgress({ added: addedCount, processed: totalProcessed, running: true, ts: Date.now() });
      continue;
    }

    // 短期在籍チェック：過去職歴に2年未満の在籍がある場合は即NG確定
    if (checkShortTenureNG(profileText)) {
      setBatchBadge(el, 'ng', '❌ 見送り(短期在籍)', '短期在籍あり', profileText.substring(0, 200), 'NG');
      totalProcessed++;
      await saveAutoAddProgress({ added: addedCount, processed: totalProcessed, running: true, ts: Date.now() });
      continue;
    }

    // ─── AI判定（1人ずつ）───
    setBatchBadge(el, 'checking', '🤖 判定中...');
    showAutoStatus(`🤖 判定中 (${totalProcessed + 1}人目)... ✅${addedCount}人追加`);
    let overall, judgeReason, judgeConfidence;
    try {
      const result = await judgeSingleCandidate(apiKey, profileText, criteria);
      overall         = result.verdict;
      judgeReason     = result.reason     || '';
      judgeConfidence = result.confidence ?? null;
    } catch (err) {
      console.error('[Snow-we] judgeSingleCandidate error:', err);
      setBatchBadge(el, 'warn', `⚠️ 判定失敗: ${(err.message || '').slice(0, 30)}`);
      totalProcessed++;
      await saveAutoAddProgress({ added: addedCount, processed: totalProcessed, running: true, ts: Date.now() });
      await sleep(500);
      continue;
    }

    const isLowConfidence = judgeConfidence != null && judgeConfidence < 60;
    const badgeCls = isLowConfidence ? 'warn'
                   : overall === 'OK' ? 'ok'
                   : overall === 'NG' ? 'ng'
                   : 'warn';
    const confLabel = judgeConfidence != null ? ` ${judgeConfidence}%` : '';
    const badgeText = overall === 'OK' ? `✅ スカウト候補${confLabel}`
                    : overall === 'NG' ? `❌ 見送り${confLabel}`
                    : `⚠️ 要確認${confLabel}`;
    const tooltipText = isLowConfidence
      ? `[低確信度] ${judgeReason}`
      : judgeReason;
    setBatchBadge(el, badgeCls, badgeText, tooltipText, profileText.substring(0, 200), overall);

    const shouldAdd = getPlatform() === 'bizreach' ? overall === 'OK' : (overall === 'OK' || overall === '要確認');
    if (shouldAdd) {
      const tagName = getPlatform() === 'bizreach' ? (criteria.autoTagName || 'KOJI→礼士郎スカウト') : (criteria.autoTagName || '');
      try {
        const added = await clickAddButton(el, tagName);
        if (added) {
          addedCount++;
          if (candidateId) {
            scoutHistory[`listed_${candidateId}`] = { date: Date.now(), platform: getPlatform() };
          }
        }
      } catch (err) {
        console.error('[Snow-we] clickAddButton error:', err);
      }
    }

    totalProcessed++;
    pending.push(el); // 処理済みとして記録
    await saveAutoAddProgress({ added: addedCount, processed: totalProcessed, running: true, ts: Date.now() });
    await sleep(500);
  }

  // ビズリーチ：仮想スクロールで次バッチへ
  if (getPlatform() === 'bizreach') {
    // CDK仮想スクロール：viewport要素またはwindowスクロールの両方に対応
    let viewport = document.querySelector('cdk-virtual-scroll-viewport');
    // フォールバック：viewport未検出時はカードリストの親スクロール要素を探す
    if (!viewport) {
      const firstCard = document.querySelector('ess-resume-list-item');
      if (firstCard) {
        let el = firstCard.parentElement;
        for (let i = 0; i < 8 && el; i++, el = el.parentElement) {
          const s = window.getComputedStyle(el);
          if ((s.overflowY === 'scroll' || s.overflowY === 'auto') && el.scrollHeight > el.clientHeight + 50) {
            viewport = el;
            break;
          }
        }
      }
    }

    // 現在DOMに存在するカードのIDテキスト指紋（新カード出現を検出するため）
    const getCardFingerprint = () => {
      const items = document.querySelectorAll('ess-resume-list-item');
      if (!items.length) return '';
      const texts = Array.from(items).map(it => (it.innerText || '').substring(0, 20));
      return texts.join('|');
    };

    const prevFingerprint = getCardFingerprint();
    const prevViewportTop = viewport ? viewport.scrollTop : window.scrollY;
    const scrollAmt = (viewport && viewport.clientHeight > 50) ? viewport.clientHeight * 0.8 : (window.innerHeight || 800);

    // scrollBy() を優先（ネイティブscrollイベントを発火→AngularCDKがDOMを再レンダリング）
    if (viewport) {
      if (typeof viewport.scrollBy === 'function') {
        viewport.scrollBy({ top: scrollAmt, behavior: 'smooth' });
      } else {
        viewport.scrollTop += scrollAmt;
        viewport.dispatchEvent(new Event('scroll', { bubbles: true }));
      }
    } else {
      window.scrollBy({ top: scrollAmt, behavior: 'smooth' });
    }

    // Angular CDKがDOMを更新するまで最大10秒待機（指紋変化 or scrollTop変化を検出）
    let scrolled = false;
    for (let w = 0; w < 40; w++) {
      await sleep(250);
      const newFp = getCardFingerprint();
      const newViewportTop = viewport ? viewport.scrollTop : window.scrollY;
      if (newFp !== prevFingerprint || newViewportTop > prevViewportTop + 50) {
        scrolled = true;
        break;
      }
    }

    // スクロール後にレジストリのバッジを再適用（仮想スクロールで消えたバッジを復元）
    reapplyBizreachBadges();

    console.log(`[Snow-we] Bizreach scroll: prevTop=${prevViewportTop} newTop=${viewport?.scrollTop ?? window.scrollY} scrolled=${scrolled} fp_changed=${getCardFingerprint() !== prevFingerprint}`);

    if (scrolled) {
      await sleep(800); // Angular CDKのレンダリング完了を待つ
      showAutoStatus(`🤖 次の候補者を処理中... (累計✅${addedCount}人追加)`);
      await saveAutoAddProgress({ added: addedCount, processed: totalProcessed, running: true, ts: Date.now() });
      await triggerAutoAdd();
      return;
    }

    // スクロールしても変化なし＝全候補者処理完了
    sessionStorage.removeItem(BATCH_SESSION_KEY);
    showAutoStatus(`🤖 完了！ ✅${addedCount}人を検討リストに追加 (全${totalProcessed}人中)`, 8000);
    await saveAutoAddProgress({ running: false });
    return;
  }

  // 次のページがあれば自動で移動して処理を続ける
  const nextPage = findNextPageButton();
  if (nextPage) {
    showAutoStatus(`🤖 次ページへ移動中... (累計✅${addedCount}人追加)`);
    // 進捗を保存（フルページロード時・SPA再開用）
    await saveAutoAddProgress({ added: addedCount, processed: totalProcessed, running: false });
    try {
      sessionStorage.setItem('snowWeAutoAdd', JSON.stringify({ resume: true, added: addedCount, processed: totalProcessed }));
    } catch (_) {}

    await sleep(300);

    // <a href> でかつ別URLへのリンクならlocation.href移動（フルページロード確定・最も確実）
    const nextHref = nextPage.href || nextPage.getAttribute('href');
    const baseHref = (u) => u.split('#')[0];
    if (nextHref && nextHref !== '#' && !nextHref.startsWith('javascript') &&
        nextHref !== location.href && baseHref(nextHref) !== baseHref(location.href)) {
      console.log(`[Snow-we] 次ページ: location.href移動 → ${nextHref}`);
      location.href = nextHref;
      return; // フルページロード後にsessionStorageから再開される
    }

    // href なし（SPA内クリック）→ クリック後URL変化またはDOM変化を検出
    const getCardFingerprint = () => {
      const first = document.querySelector('li[id^="search-result-"]');
      return first ? (first.innerText || '').substring(0, 120) : '';
    };
    const prevUrl = location.href;
    const prevFingerprint = getCardFingerprint();
    nextPage.click();

    // SPA ナビゲーション検出: URLまたはカードDOM内容が変わったら続行（doda-x等URLが変わらないSPA対応）
    for (let w = 0; w < 40; w++) {
      await sleep(250);
      if (location.href !== prevUrl) {
        showAutoStatus(`🤖 次ページ読込中... (累計✅${addedCount}人追加)`);
        await sleep(2500);
        try { sessionStorage.removeItem('snowWeAutoAdd'); } catch (_) {}
        await triggerAutoAdd();
        return;
      }
      const fp = getCardFingerprint();
      if (fp && fp !== prevFingerprint) {
        console.log('[Snow-we] 次ページ: DOM内容変化検出（URL変化なしSPA）');
        showAutoStatus(`🤖 次ページ読込中... (累計✅${addedCount}人追加)`);
        await sleep(2000);
        await triggerAutoAdd();
        return;
      }
    }
    // タイムアウト：URL変化もDOM変化もなし
    console.warn('[Snow-we] 次ページ遷移タイムアウト（URL・DOM変化なし）');
    await saveAutoAddProgress({ running: false });
  } else {
    showAutoStatus(`🤖 完了！ ✅${addedCount}人を検討リストに追加 (全${totalProcessed}人中)`, 8000);
    await saveAutoAddProgress({ running: false });
  }
}

// RDSのプロフィール/レジュメタブに切り替える
// 条件に関わらずレジュメ系タブを強制クリック
async function forceClickRDSResumeTab() {
  // 詳細パネル・モーダル内に限定して検索（ページ全体検索だと別候補者カードをクリックする危険がある）
  const panel = findRDSDetailPanel()
    || document.querySelector('[role="dialog"]')
    || document.querySelector('[class*="modal" i]')
    || document.querySelector('[class*="dialog" i]');
  if (!panel) return false; // パネルが見つからない場合はドキュメント全体を検索しない

  const tabLabels = ['レジュメ', 'プロフィール', '基本情報', '職務経歴'];
  for (const label of tabLabels) {
    // button/role=tab/li/a/span をパネル内限定で検索（span はタブラベルによく使われる）
    const tab = Array.from(panel.querySelectorAll('button, [role="tab"], li, span, a'))
      .find(el => {
        const t = (el.innerText || '').trim();
        return (t === label || t.startsWith(label)) && t.length < label.length + 6;
      });
    if (tab) { tab.click(); await sleep(800); return true; }
  }
  return false;
}

async function tryClickRDSResumeTab() {
  // 詳細パネル・モーダル内に限定して検索（ページ全体検索だと別候補者カードをクリックする危険がある）
  const panel = findRDSDetailPanel()
    || document.querySelector('[role="dialog"]')
    || document.querySelector('[class*="modal" i]')
    || document.querySelector('[class*="dialog" i]');
  if (!panel) return false;

  const panelText = (panel.innerText || '').trim();
  const hasScoutHistoryTab = panelText.includes('スカウト履歴') && !panelText.includes('職務経歴');
  if (!hasScoutHistoryTab) return false; // すでにレジュメ表示中なら何もしない

  const tabLabels = ['レジュメ', 'プロフィール', '基本情報', '職務経歴'];
  for (const label of tabLabels) {
    const tab = Array.from(panel.querySelectorAll('button, [role="tab"], li, span, a'))
      .find(el => {
        const t = (el.innerText || '').trim();
        return (t === label || t.startsWith(label)) && t.length < label.length + 6;
      });
    if (tab) {
      tab.click();
      await sleep(700);
      return true;
    }
  }
  return false;
}


// Bizreach APIレスポンスJSONからプロフィールテキストを抽出する
function extractBizreachProfileText(data) {
  if (!data || typeof data !== 'object') return '';
  const lines = [];

  // 再帰的に文字列値を収集（ラベルフィールドを特定して整形）
  const labelKeys = /name|title|company|school|university|education|career|skill|summary|description|reason|position|department|industry|role|job|work|experience|history|business|project|achievement|pr|appeal|content|detail|年収|会社|学歴|職歴|スキル|経験|業務|担当|在籍|退職|勤務|期間|役職|従業員|年齢|出身|卒業|大学|高校/i;
  const skipKeys = /id$|Id$|flag|flg|bool|count|num|code|status|type|sort|order|page|limit|offset|created|updated|deleted|token|hash|url|path|icon|image|avatar|photo|thumb|color|style|class|version|timestamp/i;

  function collect(obj, depth) {
    if (depth > 8) return;
    if (Array.isArray(obj)) {
      obj.forEach(item => collect(item, depth + 1));
      return;
    }
    if (typeof obj === 'object' && obj !== null) {
      for (const [k, v] of Object.entries(obj)) {
        if (skipKeys.test(k)) continue;
        if (typeof v === 'string' && v.trim().length > 1) {
          if (labelKeys.test(k) || v.length > 10) lines.push(v.trim());
        } else if (typeof v === 'number' && labelKeys.test(k)) {
          lines.push(`${k}: ${v}`);
        } else {
          collect(v, depth + 1);
        }
      }
    }
  }

  collect(data, 0);
  const result = [...new Set(lines)].join('\n');
  return result.substring(0, 5000);
}

async function getFullProfile(cardEl, fallbackText) {
  const platform = getPlatform();

  // RDS：カードクリック → 右パネルで全文取得
  if (platform === 'rds') {
    cardEl.click();
    await sleep(1500);
    // スカウト履歴タブが表示されている場合はレジュメタブに切り替える
    await tryClickRDSResumeTab();
    const panel = findRDSDetailPanel();
    if (panel) {
      const full = removeNonProfileSections(extractMainText(panel, 5000));
      if (full.length > 200) return full;
      // まだ短い場合は強制的にタブ切り替えを再試行
      const switched = await forceClickRDSResumeTab();
      if (switched) {
        const full2 = removeNonProfileSections(extractMainText(findRDSDetailPanel(), 5000));
        if (full2.length > 200) return full2;
      }
    }
    return fallbackText.substring(0, 900);
  }

  // Bizreach: APIでフルプロフィール取得（カードクリックはCDK仮想スクロールを破壊するため使用不可）
  if (platform === 'bizreach') {
    const resumeId = getBizreachResumeNumericId(cardEl);
    if (resumeId) {
      let xsrfToken = '';
      for (const part of document.cookie.split(';')) {
        const [k, ...vParts] = part.trim().split('=');
        if (k === 'XSRF-TOKEN') { xsrfToken = decodeURIComponent(vParts.join('=')); break; }
      }
      const headers = { 'Accept': 'application/json' };
      if (xsrfToken) headers['X-XSRF-TOKEN'] = xsrfToken;
      const endpoints = [
        `${location.origin}/v1/api/resume/${resumeId}`,
        `${location.origin}/v1/api/resumes/${resumeId}`,
        `${location.origin}/v1/api/scout/resume/${resumeId}`,
      ];
      for (const endpoint of endpoints) {
        try {
          const res = await fetch(endpoint, { credentials: 'include', headers });
          if (res.ok) {
            const contentType = res.headers.get('content-type') || '';
            if (contentType.includes('application/json')) {
              const data = await res.json();
              const profileText = extractBizreachProfileText(data);
              if (profileText && profileText.length > 300) {
                console.log(`[Snow-we] Bizreachプロフィール取得成功 (${endpoint}):`, profileText.length, '文字');
                return profileText;
              }
            } else if (contentType.includes('text/html')) {
              const html = await res.text();
              const doc = new DOMParser().parseFromString(html, 'text/html');
              doc.querySelectorAll('script,style,noscript,nav,header,footer').forEach(e => e.remove());
              const text = (doc.body?.innerText || doc.body?.textContent || '').replace(/\s+/g, ' ').trim();
              if (text.length > 300) {
                console.log(`[Snow-we] BizreachプロフィールHTML取得成功 (${endpoint}):`, text.length, '文字');
                return text.substring(0, 5000);
              }
            }
            console.log(`[Snow-we] Bizreachプロフィール取得: テキスト不足 (${endpoint}) status=${res.status}`);
            break;
          } else {
            console.log(`[Snow-we] Bizreachプロフィール取得: status=${res.status} (${endpoint})`);
          }
        } catch (e) {
          console.warn(`[Snow-we] Bizreachプロフィール取得失敗 (${endpoint}):`, e.message);
        }
      }
    }
    // フォールバック：カードテキスト
    const text = fallbackText.substring(0, 900);
    console.log('[Snow-we] Bizreachカードテキスト取得(fallback):', text.length, '文字');
    return text;
  }

  // その他：プロフィールURLをフェッチして全文取得
  const profileUrl = findProfileUrl(cardEl);
  if (profileUrl) {
    const fetched = await fetchProfilePage(profileUrl);
    if (fetched && fetched.length > 300) return fetched;
  }

  // フォールバック：一覧カードのテキスト（doda-xは職歴が長いため1500文字）
  const fallbackLimit = platform === 'dodax' ? 1500 : 900;
  return fallbackText.substring(0, fallbackLimit);
}

// カード内のプロフィールページURLを探す
function findProfileUrl(cardEl) {
  const platform = getPlatform();
  const patterns = {
    rds:      [/\/scout\//, /\/candidate\//, /\/member\//, /\/detail\//, /hrtech/, /rikunabi/],
    dodax:    [/member_search\/detail/, /member_detail/, /\/profile\//],
    ambi:     [/\/scout\/member\//, /\/member\/\d+/, /company\/scout/],
    green:    [/green-japan\.com\/user\//, /\/members\//],
    mynavi:   [/\/candidate\//, /\/resume\//],
    bizreach: [/\/resume\//, /\/candidate\//],
  };

  const platformPatterns = patterns[platform] || [];

  const matchesPattern = (href) => {
    if (!href || href === '#' || href.startsWith('javascript')) return false;
    return platformPatterns.length === 0 || platformPatterns.some(p => p.test(href));
  };

  // カード内部のリンクを検索
  for (const link of cardEl.querySelectorAll('a[href]')) {
    if (matchesPattern(link.href)) return link.href;
  }

  // Reactカードではカード要素がリンクの子要素になることがある → 祖先を遡って検索
  for (let el = cardEl.parentElement, depth = 0; el && depth < 5; el = el.parentElement, depth++) {
    if (el.tagName === 'A' && el.href && matchesPattern(el.href)) {
      console.log(`[Snow-we] findProfileUrl: 祖先<a>で発見 depth=${depth} href=${el.href.substring(0, 70)}`);
      return el.href;
    }
    for (const link of el.querySelectorAll(':scope > a[href], :scope > * > a[href]')) {
      if (matchesPattern(link.href)) {
        console.log(`[Snow-we] findProfileUrl: 祖先内リンク発見 depth=${depth} href=${link.href.substring(0, 70)}`);
        return link.href;
      }
    }
    if (['UL', 'OL', 'MAIN', 'BODY', 'SECTION', 'ARTICLE'].includes(el.tagName)) break;
  }

  // フォールバック：カード内の最初の内部リンク
  for (const link of cardEl.querySelectorAll('a[href]')) {
    const href = link.href || '';
    if (href.startsWith(location.origin) && !href.includes('#')) return href;
  }

  // doda-x: React fiberのpropsからmemberId/candidateIdを探してURLを構築
  if (platform === 'dodax') {
    const tryFiberForId = (el) => {
      try {
        const fKey = Object.keys(el).find(k => k.startsWith('__reactFiber') || k.startsWith('__reactInternalInstance'));
        if (!fKey) return null;
        let fiber = el[fKey];
        for (let depth = 0; fiber && depth < 20; fiber = fiber.return, depth++) {
          const props = fiber.memoizedProps || {};
          // memberId / candidateId / userId 等を探す
          for (const key of Object.keys(props)) {
            const v = props[key];
            if (typeof v === 'string' && /^\d{6,12}$/.test(v) &&
                /id|member|candidate|user|resume/i.test(key)) {
              return v;
            }
            if (typeof v === 'number' && v > 100000 && /id|member|candidate|user|resume/i.test(key)) {
              return String(v);
            }
          }
        }
      } catch (_) {}
      return null;
    };
    const memberId = tryFiberForId(cardEl) ||
                     tryFiberForId(cardEl.firstElementChild) ||
                     tryFiberForId(cardEl.querySelector('.c-star-cts') || cardEl);
    if (memberId) {
      const url = `${location.origin}/member_search/detail/${memberId}`;
      console.log(`[Snow-we] findProfileUrl: doda-x fiberからID取得 memberId=${memberId} → ${url}`);
      return url;
    }
    console.log(`[Snow-we] findProfileUrl: doda-x ID未取得 cardId=${cardEl.id}`);
  }

  // AMBI: js_userSet カードは<a>タグを持たない → No.XXXXXXからメンバーIDを抽出してURL構築
  if (platform === 'ambi') {
    const cardText = cardEl.textContent || '';
    const noMatch = cardText.match(/No\.(\d{5,})/);
    if (noMatch) {
      const memberId = noMatch[1];
      const params = new URLSearchParams(location.search);
      const searchId = params.get('SearchID') || '';
      const pk = params.get('PK') || '';
      const qs = [searchId && `SearchID=${searchId}`, pk && `PK=${pk}`].filter(Boolean).join('&');
      const url = `${location.origin}/company/scout/member/?MemberID=${memberId}${qs ? '&' + qs : ''}`;
      console.log(`[Snow-we] findProfileUrl: AMBI No.${memberId} → ${url}`);
      return url;
    }
    // data属性からIDを試みる
    const idEl = cardEl.querySelector('[data-member-id],[data-id],[data-user-id]');
    if (idEl) {
      const mid = idEl.dataset.memberId || idEl.dataset.id || idEl.dataset.userId;
      if (mid) {
        const url = `${location.origin}/company/scout/member/?MemberID=${mid}`;
        console.log(`[Snow-we] findProfileUrl: AMBI data属性 MemberID=${mid} → ${url}`);
        return url;
      }
    }
  }

  console.log(`[Snow-we] findProfileUrl: URL未発見 platform=${platform} cardTag=${cardEl.tagName} cardClass=${cardEl.className.substring(0, 50)}`);
  return null;
}

// テキストから簡易ハッシュを生成（URLが取れない場合の候補者ID代替）
function simpleHash(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = (Math.imul(31, h) + str.charCodeAt(i)) | 0;
  }
  return Math.abs(h).toString(36);
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

    return best.replace(/\s+/g, ' ').trim().substring(0, 5000);
  } catch {
    return null;
  }
}

// Bizreach の星ボタン（ess-star-icon-toggle）をカード要素から探して返す
function findBizreachStarButton(cardEl) {
  // 自身から最大6段階上の親まで順番にquerySelectorで探す
  let el = cardEl;
  for (let i = 0; i < 6; i++) {
    if (!el) break;
    const star = el.querySelector('ess-star-icon-toggle');
    if (star) {
      console.log('[Snow-we] 星ボタン発見 深さ', i, el.tagName);
      return star;
    }
    el = el.parentElement;
  }
  console.warn('[Snow-we] 星ボタン未発見 cardEl:', cardEl?.tagName, cardEl?.className?.substring(0, 40));
  return null;
}

// Bizreach の星ボタンが既スター済みかどうかを返す
// Angular は JS property を更新する（attribute は初期値のみ反映のことがある）
function isBizreachStarred(starEl) {
  const toggle = starEl.querySelector('b-ui-icon-toggle') || starEl;
  // Angular は JS property を優先的に更新する
  if (toggle.checked === true)  return true;
  if (toggle.checked === false) return false;
  // aria-checked（Angular が DOM attribute として反映する場合）
  const aria = toggle.getAttribute('aria-checked');
  if (aria === 'true')  return true;
  if (aria === 'false') return false;
  // フォールバック：HTML attribute
  return toggle.getAttribute('checked') === 'true';
}

// Bizreach 星ボタンを実際にクリックする（API応答を待ってポーリングでチェック）
async function clickBizreachStar(starBtn) {
  const innerToggle = starBtn.querySelector('b-ui-icon-toggle') || starBtn;
  const innerIcon   = innerToggle.querySelector('b-ui-icon') || innerToggle;
  const opts = { bubbles: true, cancelable: true, composed: true, view: window, button: 0, buttons: 0 };

  // クリック後にポーリングで starred を確認（API応答が遅い場合に対応）
  async function pollStarred(maxMs = 3000) {
    const end = Date.now() + maxMs;
    while (Date.now() < end) {
      if (isBizreachStarred(starBtn)) return true;
      await sleep(300);
    }
    return false;
  }

  // 手法1: b-ui-icon（最内部）にポインター→マウス→クリック完全シーケンス
  const downOpts = {...opts, buttons: 1};
  innerIcon.dispatchEvent(new PointerEvent('pointerover', opts));
  innerIcon.dispatchEvent(new MouseEvent  ('mouseover',   opts));
  innerIcon.dispatchEvent(new PointerEvent('pointerdown', downOpts));
  innerIcon.dispatchEvent(new MouseEvent  ('mousedown',   downOpts));
  await sleep(50);
  innerIcon.dispatchEvent(new PointerEvent('pointerup',   opts));
  innerIcon.dispatchEvent(new MouseEvent  ('mouseup',     opts));
  innerIcon.dispatchEvent(new MouseEvent  ('click',       opts));
  if (await pollStarred(3000)) return true;

  // 手法2: b-ui-icon-toggle に click（手法1が無効だった場合のみ試す）
  innerToggle.dispatchEvent(new MouseEvent('click', opts));
  if (await pollStarred(3000)) return true;

  // 手法3: ess-star-icon-toggle 自体に click
  starBtn.dispatchEvent(new MouseEvent('click', opts));
  if (await pollStarred(3000)) return true;

  // 手法4: Angular ng.getComponent() API
  try {
    const ngApi = window.ng;
    if (ngApi) {
      for (const el of [innerToggle, starBtn]) {
        const comp = ngApi.getComponent?.(el);
        if (!comp) continue;
        if (typeof comp.toggle   === 'function') comp.toggle();
        else if (typeof comp.onClick === 'function') comp.onClick();
        else comp.checked = true;
        ngApi.applyChanges?.(el);
        if (await pollStarred(2000)) return true;
      }
    }
  } catch (_) {}

  // 手法5: 内部 button/a 要素
  const innerBtn = starBtn.querySelector('button,[role="button"],a');
  if (innerBtn) {
    innerBtn.click();
    if (await pollStarred(2000)) return true;
  }

  console.warn('[Snow-we] 星クリック全手法失敗（isTrusted制限またはAPI拒否の可能性）');
  return false;
}

// API成功後に星のDOM状態を強制的にONにする
// b-ui-icon-toggle: checked属性 + 内部 b-ui-icon のCSSクラスを onicon に切り替える
function forceBizreachStarOn(starBtn) {
  const toggle = starBtn.querySelector('b-ui-icon-toggle') || starBtn;
  toggle.setAttribute('checked', 'true');
  const icon = toggle.querySelector('b-ui-icon');
  if (icon) {
    const offIcon = toggle.getAttribute('officon') || 'star';
    const onIcon  = toggle.getAttribute('onicon')  || 'star-fill';
    icon.className = icon.className.replace(`bui-icon-${offIcon}`, `bui-icon-${onIcon}`);
  }
}

// Bizreach カード要素から resume の数値IDを取得する
function getBizreachResumeNumericId(cardEl) {
  let el = cardEl;
  for (let i = 0; i < 8; i++) {
    if (!el) break;
    const m = el.id?.match(/^resume-(\d+)$/);
    if (m) return m[1];
    el = el.parentElement;
  }
  return null;
}

// Bizreach お気に入りAPIを直接呼び出す（isTrusted 制限を回避）
async function callBizreachFavoriteApi(resumeNumericId) {
  if (!resumeNumericId) return false;
  let xsrfToken = '';
  for (const part of document.cookie.split(';')) {
    const [k, ...vParts] = part.trim().split('=');
    if (k === 'XSRF-TOKEN') { xsrfToken = decodeURIComponent(vParts.join('=')); break; }
  }
  const headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };
  if (xsrfToken) headers['X-XSRF-TOKEN'] = xsrfToken;
  try {
    const res = await fetch(
      `${location.origin}/v1/api/resume-favorite/${resumeNumericId}`,
      { method: 'PUT', credentials: 'include', headers, body: JSON.stringify({ favorite: true }) }
    );
    console.log('[Snow-we] お気に入りAPI:', res.status, resumeNumericId);
    return res.status === 204 || res.status === 200 || res.ok;
  } catch (e) {
    console.warn('[Snow-we] お気に入りAPI失敗:', e.message);
    return false;
  }
}

// 候補者カードの追加ボタンを探してクリックする
async function clickAddButton(cardEl, tagName) {
  const platform = getPlatform();

  // Bizreach: お気に入りAPIを直接呼び出す（合成イベントの isTrusted 制限を回避）
  if (platform === 'bizreach') {
    const starBtn = findBizreachStarButton(cardEl);
    if (!starBtn) return false;
    if (isBizreachStarred(starBtn)) {
      console.log('[Snow-we] すでにスター済み、スキップ');
      return false;
    }
    // APIを直接呼び出す（最優先）
    const resumeNumericId = getBizreachResumeNumericId(cardEl);
    if (resumeNumericId) {
      // セッション内で既にスター済み（別DOM要素での重複防止）
      let starredIds;
      try { starredIds = new Set(JSON.parse(sessionStorage.getItem('snowWeBizreachStarred') || '[]')); }
      catch (_) { starredIds = new Set(); }
      if (starredIds.has(resumeNumericId)) {
        console.log('[Snow-we] セッション内スター済みスキップ:', resumeNumericId);
        forceBizreachStarOn(starBtn);
        return false;
      }
      const apiOk = await callBizreachFavoriteApi(resumeNumericId);
      if (apiOk) {
        console.log('[Snow-we] APIで星追加成功:', resumeNumericId);
        forceBizreachStarOn(starBtn);
        starredIds.add(resumeNumericId);
        try { sessionStorage.setItem('snowWeBizreachStarred', JSON.stringify([...starredIds])); } catch (_) {}
        return true;
      }
    }
    // APIが失敗した場合は合成イベントにフォールバック
    const result = await clickBizreachStar(starBtn);
    console.log('[Snow-we] 星クリック結果:', result, '/ checked後:', isBizreachStarred(starBtn));
    return result;
  }

  // doda-x: 星ボタン（c-star-cts）をクリック
  if (platform === 'dodax') {
    const searchRoot = cardEl.closest('li, [class*="result"], [class*="member"], [class*="item"]') || cardEl;
    const starBtn = searchRoot.querySelector('.c-star-cts');
    if (!starBtn) { console.warn('[Snow-we] dodax 星ボタン未発見'); return false; }

    const icon = starBtn.querySelector('i');
    // aria属性・コンテナクラス・アイコンクラスの複数手段でスター済みを判定
    const isStarred = () => {
      if (starBtn.getAttribute('aria-pressed') === 'true' ||
          starBtn.getAttribute('aria-checked') === 'true') return true;
      if (/\b(?:active|starred|is-active|is-starred|on|is-checked)\b/.test(starBtn.className)) return true;
      if (!icon) return false;
      // is-checked-star クラスはスター済みを示す
      if (icon.className.includes('is-checked-star')) return true;
      return icon.className.includes('icon-star') && !icon.className.includes('icon-star_border');
    };
    console.log(`[Snow-we] dodax 星診断 btn:"${starBtn.className}" icon:"${icon?.className || 'なし'}" aria-pressed:"${starBtn.getAttribute('aria-pressed')}" → starred:${isStarred()}`);
    if (isStarred()) { console.log('[Snow-we] dodax すでにスター済み、スキップ'); return false; }

    // fiber walkは使わない（親カードのonClick=ページ遷移を誤発火させるため）
    // ネイティブイベントのみ使用 → ReactのルートへのイベントデリゲーションでstopPropagationが効く
    const currentUrl = location.href;
    const opts = { bubbles: true, cancelable: true, view: window };
    const target = icon || starBtn;

    // Try 1: PointerEvent シーケンス（React はpointerイベントを優先）
    try { target.dispatchEvent(new PointerEvent('pointerdown', { ...opts, pointerId: 1, isPrimary: true })); } catch (_) {}
    try { target.dispatchEvent(new PointerEvent('pointerup',   { ...opts, pointerId: 1, isPrimary: true })); } catch (_) {}
    target.dispatchEvent(new MouseEvent('click', opts));
    await sleep(600);
    // ページ遷移してしまった場合は中断
    if (location.href !== currentUrl) {
      console.warn('[Snow-we] dodax 星クリック後にページ遷移が発生 → 中断');
      return false;
    }
    if (isStarred()) { console.log('[Snow-we] dodax 星クリック成功(pointer)'); return true; }

    // Try 2: starBtn直接 .click()
    starBtn.click();
    await sleep(600);
    if (location.href !== currentUrl) { console.warn('[Snow-we] dodax 遷移発生'); return false; }
    if (isStarred()) { console.log('[Snow-we] dodax 星クリック成功(native click)'); return true; }

    // Try 3: MouseEvent シーケンス
    target.dispatchEvent(new MouseEvent('mousedown', opts));
    target.dispatchEvent(new MouseEvent('mouseup',   opts));
    target.dispatchEvent(new MouseEvent('click',     opts));
    await sleep(600);
    if (location.href !== currentUrl) { console.warn('[Snow-we] dodax 遷移発生'); return false; }

    const success = isStarred();
    console.log('[Snow-we] dodax 星クリック完了, スター済み:', success);
    return success;
  }

  const labelMap = {
    rds:      '検討中リスト追加',
    ambi:     'この検討人材リストに追加',
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
    // タグ入力欄があれば入力する（他媒体）
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

// プロフィールテキストから年収（万円）を抽出する
// カンマ区切り（1,000 ～ 1,199万円）に対応。範囲の場合は下限値を使用
function extractIncomeFromText(text) {
  const num = '(?:\\d{1,2},\\d{3}|\\d{3,4})'; // 1,000 or 1000 形式
  const parseNum = s => parseInt(s.replace(/,/g, ''), 10);

  // 「現年収」「年収」に続く数値（範囲 or 単値）を優先
  const labelPatterns = [
    new RegExp(`現年収[^\\d]*(${num})\\s*[〜~～]`),
    new RegExp(`現年収[^\\d]*(${num})万`),
    new RegExp(`年収[^\\d]*(${num})\\s*[〜~～]`),
    new RegExp(`年収[^\\d]*(${num})万`),
  ];
  for (const re of labelPatterns) {
    const m = text.match(re);
    if (m) return parseNum(m[1]);
  }

  // 範囲形式（下限を採用）: 1,000 ～ 1,199万円 → 1000
  const rangeRe = new RegExp(`(${num})\\s*[〜~～]\\s*${num}万`);
  const rangeM = text.match(rangeRe);
  if (rangeM) return parseNum(rangeM[1]);

  // 単値: 800万円
  const singleRe = new RegExp(`(${num})万円?(?:程度|前後|台)?(?:\\s|　|$|\\/|・)`);
  const singleM = text.match(singleRe);
  if (singleM) return parseNum(singleM[1]);

  return null;
}

// 年齢と年収からNG判定を返す（確実にNGの場合のみ 'NG'、それ以外は null）
function checkIncomeNG(profileText) {
  // Bizreach は年収情報が 0 や非公開で取得できないことが多いため Claude に委ねる
  if (getPlatform() === 'bizreach') return null;

  const ageMatch = profileText.match(/(\d{2})歳/);
  if (!ageMatch) return null;
  const age = parseInt(ageMatch[1], 10);
  const income = extractIncomeFromText(profileText);
  if (income === null || income === 0) return null; // 年収不明・ゼロはClaudeに任せる

  // ITエンジニア系キーワードで職種を判定
  const isIT = /エンジニア|ソフトウェア開発|インフラ|クラウド|システム開発|SE[^\w]|データエンジニア|バックエンド|フロントエンド|DevOps/.test(profileText);

  let threshold;
  if (isIT) {
    if (age < 30)      threshold = 350;
    else if (age <= 35) threshold = 500;
    else if (age <= 40) threshold = 700;
    else if (age <= 45) threshold = 800;
    else threshold = null;
  } else {
    // 文系職（またはIT判定できない場合）は文系基準で判定
    if (age < 30)      threshold = 500;
    else if (age <= 35) threshold = 700;
    else if (age <= 39) threshold = 800;
    else if (age <= 42) threshold = 1000;
    else if (age <= 45) threshold = 1200;
    else threshold = null;
  }

  if (threshold !== null && income < threshold) {
    console.log(`[Snow-we] 年収NG: ${age}歳 ${income}万 < 閾値${threshold}万 (${isIT ? 'IT' : '文系'})`);
    return 'NG';
  }
  return null;
}

// 在籍期間チェック：過去職歴に2年（24ヶ月）未満の会社エントリーがある場合NG
// ・出向先・兼務先はカウントしない（出向元の在籍期間に含む）
// ・同一会社を複数行に分けて記入している場合は合算する
function checkShortTenureNG(profileText) {
  if (!profileText) return null;

  const companyRe = /株式会社|有限会社|合同会社|ホールディングス|LLC|Inc\b|Corp\b|Ltd\b|銀行[^員振]|証券[^取]|生命保険|損害保険|病院|クリニック|㈱|（株）|\(株\)/;
  const shukkoRe  = /出向|兼務|派遣先/; // 出向・兼務行はスキップ

  function parseTenureMonths(str) {
    const m1 = str.match(/[（(](\d+)年(?:(\d+)[ヶか]月)?[）)]/);
    if (m1) return parseInt(m1[1], 10) * 12 + parseInt(m1[2] || '0', 10);
    const m2 = str.match(/[（(](\d+)[ヶか]月[）)]/);
    if (m2) return parseInt(m2[1], 10);
    const m3 = str.match(/^(\d+(?:\.\d+)?)年/);
    if (m3) return Math.round(parseFloat(m3[1]) * 12);
    const m4 = str.match(/^(\d+)[ヶか]月/);
    if (m4) return parseInt(m4[1], 10);
    const m5 = str.match(/各(\d+(?:\.\d+)?)年/);
    if (m5) return Math.round(parseFloat(m5[1]) * 12);
    return null;
  }

  function parseDateRangeMonths(str) {
    const m = str.match(/(\d{4})年(\d{1,2})月\s*[〜~～]\s*(\d{4})年(\d{1,2})月/);
    if (!m) return null;
    const months = (parseInt(m[3]) - parseInt(m[1])) * 12 + (parseInt(m[4]) - parseInt(m[2]));
    return months > 0 ? months : null;
  }

  const dodaxTenureRe = /^(?:各\d+(?:\.\d+)?年|\d+(?:\.\d+)?年|\d+[ヶか]月)/;
  const lines = profileText.split('\n').map(l => l.trim()).filter(Boolean);

  // 同一会社の全出現箇所から在籍期間を合算（複数行記入対応）
  // 現職（現在/在籍中）が含まれる場合は Infinity を返す（チェック対象外）
  function getTotalTenureForCompanyLine(companyLineStr) {
    if (!companyLineStr) return 0;
    const key = companyLineStr.replace(/\s+/g, '').substring(0, Math.min(8, companyLineStr.replace(/\s+/g, '').length));
    if (key.length < 3) return 0;
    let total = 0;
    for (let k = 0; k < lines.length; k++) {
      const l = lines[k];
      if (!l.replace(/\s+/g, '').includes(key.substring(0, Math.min(6, key.length)))) continue;
      if (shukkoRe.test(l)) continue;
      if (l.includes('現在') || l.includes('在籍中')) return Infinity;
      const inlineT = parseTenureMonths(l);
      if (inlineT !== null && inlineT > 0) total += inlineT;
      for (let j = k + 1; j < Math.min(k + 8, lines.length); j++) {
        if (lines[j].includes('現在') || lines[j].includes('在籍中')) return Infinity;
        if (companyRe.test(lines[j]) && !shukkoRe.test(lines[j])) break;
        const t = parseTenureMonths(lines[j]);
        if (t !== null && t > 0) total += t;
      }
    }
    return total;
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.includes('現在') || line.includes('在籍中')) continue;
    if (shukkoRe.test(line)) continue; // 出向・兼務行は全てスキップ

    // ── A: 日付範囲形式（"YYYY年MM月 〜 YYYY年MM月"）──
    const dateMonths = parseDateRangeMonths(line);
    if (dateMonths !== null && dateMonths < 24) {
      const prevLine2 = i > 0 ? lines[i - 1] : '';
      const nextLine2 = i < lines.length - 1 ? lines[i + 1] : '';
      if (!shukkoRe.test(prevLine2) && !shukkoRe.test(nextLine2) &&
          (companyRe.test(line) || companyRe.test(prevLine2) || companyRe.test(nextLine2))) {
        console.log(`[Snow-we] 短期在籍NG(date): ${dateMonths}ヶ月 / "${line.substring(0, 60)}"`);
        return 'NG';
      }
    }

    // ── B: テキスト在籍期間形式 ──
    const total = parseTenureMonths(line);
    if (total === null || total <= 0 || total >= 24) continue;

    // ① 同行に会社名 → 全プロフィール合算チェック後NG
    if (companyRe.test(line)) {
      const fullTotal = getTotalTenureForCompanyLine(line);
      if (fullTotal >= 24) continue;
      console.log(`[Snow-we] 短期在籍NG: ${fullTotal || total}ヶ月 / "${line.substring(0, 50)}"`);
      return 'NG';
    }

    // ② 同行に部署・役職キーワード → サブエントリー
    const roleRe = /部長|課長|係長|主任|マネージャー|ディレクター|リーダー|担当|チーフ|シニア|ジュニア|エンジニア|営業部|開発部|総務部|人事部|経営企画|事業部|本部|センター|グループ|チーム|課$|室$|部$/;
    if (roleRe.test(line)) continue;

    // ③ doda-x形式の在籍期間行（行頭が数字+年/月）
    if (dodaxTenureRe.test(line)) {
      if (i > 0 && dodaxTenureRe.test(lines[i - 1])) continue;

      let companyLine = null;
      let isCurrent = false;
      for (let k = i - 1; k >= Math.max(0, i - 5); k--) {
        if (lines[k].includes('現在') || lines[k].includes('在籍中') || lines[k].includes('現職')) isCurrent = true;
        if (companyRe.test(lines[k])) { companyLine = lines[k]; break; }
        if (dodaxTenureRe.test(lines[k])) break;
      }
      if (!companyLine || isCurrent) continue;
      if (shukkoRe.test(companyLine)) continue; // 出向先会社はスキップ

      let companyTotal = total;
      for (let j = i + 1; j < lines.length; j++) {
        if (!dodaxTenureRe.test(lines[j]) || lines[j].includes('現在') || lines[j].includes('在籍中')) break;
        const t = parseTenureMonths(lines[j]);
        if (t) companyTotal += t;
      }
      if (companyTotal >= 24) continue;

      // 同一会社の別エントリーと合算して基準クリアか確認
      const fullTotal = getTotalTenureForCompanyLine(companyLine);
      if (fullTotal >= 24) continue;

      console.log(`[Snow-we] 短期在籍NG(dodax): 合計${companyTotal}ヶ月 / 会社: "${companyLine.substring(0, 50)}"`);
      return 'NG';
    }

    // ④ Bizreach形式: 直前行を確認
    const prevLine = i > 0 ? lines[i - 1] : '';
    if (companyRe.test(prevLine)) {
      if (shukkoRe.test(prevLine)) continue; // 出向先はスキップ
      const prevTenure = parseTenureMonths(prevLine);
      if (prevTenure !== null && prevTenure >= 24) continue;

      const fullTotal = getTotalTenureForCompanyLine(prevLine);
      if (fullTotal >= 24) continue;

      console.log(`[Snow-we] 短期在籍NG: ${total}ヶ月 / 会社名行: "${prevLine.substring(0, 50)}"`);
      return 'NG';
    }
  }
  return null;
}

// ポジション要件をGASから取得（キャッシュ付き）
async function fetchPositionRequirements(position) {
  if (!position) return { requirements: '', companyCriteria: '' };
  if (_posReqCache.has(position)) return _posReqCache.get(position);
  try {
    const res = await chrome.runtime.sendMessage({ type: 'getPositionRequirements', position });
    if (res?.ok && res.requirements) {
      console.log(`[Snow-we] GASデータ取得成功: "${position}" / 要件${res.requirements.length}文字${res.companyCriteria ? ` / 会社別基準${res.companyCriteria.length}文字` : ''}`);
      _posReqCache.set(position, res);
      return res;
    } else {
      console.warn(`[Snow-we] GASデータなし: "${position}" → 共通基準のみで判定します (ok=${res?.ok}, requirements="${res?.requirements}")`);
      const result = { requirements: '', companyCriteria: '' };
      _posReqCache.set(position, result);
      return result;
    }
  } catch (e) {
    console.error(`[Snow-we] GASデータ取得エラー: "${position}"`, e);
    return { requirements: '', companyCriteria: '' };
  }
}

// 1候補者のAI判定
async function judgeSingleCandidate(apiKey, profileText, criteria) {
  const criteriaLines = buildCriteriaText(criteria, getPlatform());

  // ポジション要件をGASから取得
  const { currentPosition } = await chrome.storage.local.get(['currentPosition']);
  const { requirements: posReq, companyCriteria } = await fetchPositionRequirements(currentPosition || '');
  const posSection     = posReq        ? `\n【応募ポジションの職務内容】\n${posReq}\n`           : '';
  const companySection = companyCriteria ? `\n【会社別採用基準（共通基準より優先）】\n${companyCriteria}\n` : '';

  // 過去の訂正フィードバックをfew-shot examplesとして組み込む
  const feedbacks = await loadRecentFeedbacks(10);
  let fewShotSection = '';
  if (feedbacks.length > 0) {
    const examples = feedbacks
      .map(f => `- 「${f.profileSummary.substring(0, 80)}…」 → 正解: ${f.correction}（AIの誤判定: ${f.aiVerdict}）`)
      .join('\n');
    fewShotSection = `\n【過去の訂正例（優先参照）】\n以下はAIが誤判定して人間が訂正した実例です。同様のケースは同じ判断をしてください。\n${examples}\n`;
  }

  const prompt = `転職エージェントの一次選定アシスタントです。
${companySection}
【選定基準】
${criteriaLines}${posSection}${fewShotSection}

【候補者情報】
${profileText}

JSON1行のみで出力（rを先に書いてからoを確定し、最後にcで確信度0-100を付けること。rは判定理由を50字以内で）:
{"r":"理由","o":"OK","c":90} または {"r":"理由","o":"NG","c":85} または {"r":"理由","o":"要確認","c":45}
※cは判定の確信度（0〜100の整数）。基準に明確に合致/不合致なら80以上、判断が難しければ60未満。`;

  const data = await claudeFetch(apiKey, {
    model: 'claude-sonnet-4-6',
    max_tokens: 250,
    messages: [{ role: 'user', content: prompt }]
  });
  const text = (data.content?.[0]?.text || '').trim();
  const verdictMatch    = text.match(/"o"\s*:\s*"([^"]+)"/);
  const reasonMatch     = text.match(/"r"\s*:\s*"([^"]+)"/);
  const confidenceMatch = text.match(/"c"\s*:\s*(\d+)/);
  const verdict    = verdictMatch    ? verdictMatch[1]        : '要確認';
  const reason     = reasonMatch     ? reasonMatch[1]         : '';
  const confidence = confidenceMatch ? parseInt(confidenceMatch[1], 10) : null;
  console.log(`[Snow-we] AI判定: ${verdict}${confidence != null ? ` (${confidence}%)` : ''}${reason ? ` / ${reason}` : ''}`);
  return { verdict, reason, confidence };
}

// ── フィードバック保存・読み込み ──────────────────────────────────────
async function saveFeedback(profileSummary, aiVerdict, correction, platform) {
  const ts = Date.now();

  // ローカルに保存
  const stored = await chrome.storage.local.get(['snowWeFeedbacks']);
  const feedbacks = stored.snowWeFeedbacks || [];
  feedbacks.unshift({ profileSummary, aiVerdict, correction, platform, ts });
  if (feedbacks.length > 50) feedbacks.length = 50;
  await chrome.storage.local.set({ snowWeFeedbacks: feedbacks });
  console.log(`[Snow-we] フィードバック保存: AI=${aiVerdict} → 訂正=${correction} (累計${feedbacks.length}件)`);

  // GASスプレッドシートにも送信（設定済みの場合）
  const { gasSettings, screeningCriteria } = await chrome.storage.local.get(['gasSettings', 'screeningCriteria']);
  const gasUrl = gasSettings?.dbUrl || gasSettings?.url;
  const secret = gasSettings?.secret;
  if (gasUrl && secret) {
    chrome.runtime.sendMessage({
      type: 'gasPost',
      url: gasUrl,
      payload: {
        action: 'saveFeedback',
        secret,
        recruiter: screeningCriteria?.recruiterName || '',
        platform,
        aiVerdict,
        correction,
        profileSummary,
        ts,
      }
    }).catch(err => console.error('[Snow-we] フィードバックGAS送信エラー:', err));
  }
}

async function loadRecentFeedbacks(limit = 10) {
  const stored = await chrome.storage.local.get(['snowWeFeedbacks']);
  return (stored.snowWeFeedbacks || []).slice(0, limit);
}

// 訂正ポップアップを表示する
function showFeedbackPopup(badgeEl) {
  // 既存のポップアップを消す
  document.querySelectorAll('.snow-we-fb-popup').forEach(p => p.remove());

  const aiVerdict     = badgeEl.dataset.verdict  || '';
  const profileSummary = badgeEl.dataset.profile || '';
  const platform      = getPlatform();

  const popup = document.createElement('div');
  popup.className = 'snow-we-fb-popup';
  popup.innerHTML = `<span>判定を訂正</span><div class="snow-we-fb-row"></div>`;
  const row = popup.querySelector('.snow-we-fb-row');

  const options = aiVerdict === 'OK'
    ? [{ label: '❌ 実はNG', cls: 'ng', value: 'NG' }]
    : aiVerdict === 'NG'
    ? [{ label: '✅ 実はOK', cls: 'ok', value: 'OK' }]
    : [{ label: '✅ OK', cls: 'ok', value: 'OK' }, { label: '❌ NG', cls: 'ng', value: 'NG' }];

  options.forEach(({ label, cls, value }) => {
    const btn = document.createElement('button');
    btn.className = `snow-we-fb-btn ${cls}`;
    btn.textContent = label;
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      popup.remove();
      try {
        await saveFeedback(profileSummary, aiVerdict, value, platform);
      } catch (_) {}
      // saveFeedbackが失敗してもバッジは必ず更新する
      badgeEl.className = badgeEl.className.replace(/\b(ok|ng|warn)\b/, 'corrected');
      badgeEl.textContent = value === 'OK' ? '↩ 訂正: OK' : '↩ 訂正: NG';
      badgeEl.style.cursor = 'default';
      badgeEl.removeEventListener('click', badgeEl._fbHandler);
    });
    row.appendChild(btn);
  });

  // ポップアップ外クリックで閉じる
  setTimeout(() => {
    document.addEventListener('click', function closePopup() {
      popup.remove();
      document.removeEventListener('click', closePopup);
    });
  }, 0);

  badgeEl.parentElement.appendChild(popup);
}

// バッジをセット（バッチ用）
function setBatchBadge(el, cls, text, tooltip, profileSummary, aiVerdict) {
  el.querySelectorAll('.snow-we-badge.batch').forEach(b => b.remove());
  if (getComputedStyle(el).position === 'static') el.style.position = 'relative';
  const badge = document.createElement('div');
  badge.className = `snow-we-badge batch ${cls}`;
  badge.textContent = text;
  if (tooltip) badge.title = tooltip;
  // ok/ng/warn 判定済みバッジにのみ訂正ハンドラを付与
  if ((cls === 'ok' || cls === 'ng' || cls === 'warn') && profileSummary) {
    badge.dataset.verdict = aiVerdict || cls.toUpperCase();
    badge.dataset.profile = profileSummary;
    badge._fbHandler = (e) => { e.stopPropagation(); showFeedbackPopup(badge); };
    badge.addEventListener('click', badge._fbHandler);
    badge.title = (tooltip ? tooltip + '\n' : '') + '（クリックで判定を訂正）';
  }
  el.appendChild(badge);

  // Bizreach仮想スクロール: checkingを除く確定判定をレジストリに保存（スクロール後の再表示に使用）
  if (getPlatform() === 'bizreach' && cls !== 'checking') {
    const resumeId = getBizreachResumeNumericId(el);
    const key = resumeId || ('fp:' + el.textContent.trim().substring(0, 60));
    _bizreachBadgeRegistry.set(key, {
      cls, text, tooltip: tooltip || '', profileSummary: profileSummary || '', aiVerdict: aiVerdict || ''
    });
  }
}

// Bizreach仮想スクロール: DOM上の全カードにレジストリのバッジを再適用（デバウンス付き）
function reapplyBizreachBadges() {
  if (_bizreachBadgeRegistry.size === 0) return;
  clearTimeout(_reapplyBizreachTimer);
  _reapplyBizreachTimer = setTimeout(() => {
    document.querySelectorAll('ess-resume-list-item').forEach(el => {
      if (el.querySelector('.snow-we-badge.batch')) return;
      const resumeId = getBizreachResumeNumericId(el);
      const key = resumeId || ('fp:' + el.textContent.trim().substring(0, 60));
      const state = _bizreachBadgeRegistry.get(key);
      if (!state) return;
      setBatchBadge(el, state.cls, state.text, state.tooltip, state.profileSummary, state.aiVerdict);
    });
  }, 300);
}

// Bizreach仮想スクロール監視を開始（初回のみ・viewport未検出時は監視しない）
function startBizreachBadgeObserver() {
  if (_bizreachObserver) return;
  const target = document.querySelector('cdk-virtual-scroll-viewport');
  if (!target) {
    console.log('[Snow-we] cdk-virtual-scroll-viewport 未検出のため監視スキップ');
    return;
  }
  _bizreachObserver = new MutationObserver(() => reapplyBizreachBadges());
  _bizreachObserver.observe(target, { childList: true, subtree: true });
  console.log('[Snow-we] Bizreachバッジ監視開始');
}

// 次ページボタンを探す
function findNextPageButton() {
  const nextTexts = ['次へ', '次のページ', '>', '›', 'Next'];

  // 1. テキストベースの「次へ」ボタン
  // モーダル・カレンダー内の要素や長いテキストを含む要素は除外する
  const isInModal = (el) => {
    for (let p = el.parentElement; p; p = p.parentElement) {
      const cls = (p.className || '').toLowerCase();
      if (cls.includes('modal') || cls.includes('calendar') || cls.includes('dialog') ||
          p.getAttribute('role') === 'dialog') return true;
    }
    return false;
  };
  for (const el of document.querySelectorAll('a,button,[role="button"],span,div,li')) {
    const t = (el.innerText || el.getAttribute('aria-label') || '').trim();
    // テキストが短い（< 20文字）場合のみ。'>'や'›'は完全一致のみ
    const matches = nextTexts.some(kw => {
      if (kw === '>' || kw === '›') return t === kw;
      return (t === kw || t.includes(kw)) && t.length < 20;
    });
    if (matches && !el.disabled && !el.classList.contains('disabled') &&
        el.getAttribute('aria-disabled') !== 'true' &&
        !el.classList.contains('active') && !el.classList.contains('current') &&
        !isInModal(el)) {
      console.log('[Snow-we] テキスト次ページボタン発見:', t, el.tagName, el.className.substring(0, 40));
      return el;
    }
  }

  // 2. 数字ページネーション: アクティブページ番号+1を探す（doda-x等SPA）
  // 結果件数表示（0件・531件・30件表示等）を除外し、ページボタンのみを対象にする
  const isResultCountEl = (el) => {
    for (let p = el.parentElement, i = 0; p && i < 5; p = p.parentElement, i++) {
      const cls = (p.className || '').toLowerCase();
      // 件数表示コンテナのクラス名パターン（'result'は検索結果リストと区別できないため除外）
      if (cls.includes('cnt') || cls.includes('count') ||
          cls.includes('total') || cls.includes('件数') || cls.includes('hits')) return true;
    }
    return false;
  };

  const allNumericEls = Array.from(document.querySelectorAll('a,button,[role="button"],span,div,li'))
    .filter(el => {
      const t = (el.innerText || '').trim();
      const n = parseInt(t, 10);
      if (!/^\d{1,3}$/.test(t) || el.children.length !== 0) return false;
      if (n < 1) return false; // 0 は件数表示の可能性が高いので除外
      if (isInModal(el)) return false;
      if (isResultCountEl(el)) return false;
      return true;
    });

  console.log(`[Snow-we] 数字ページ候補要素数: ${allNumericEls.length}`, allNumericEls.slice(0, 8).map(e => `${e.tagName}:${(e.innerText||'').trim()}:${e.className.substring(0,30)}`));

  if (allNumericEls.length > 0) {
    let currentPage = null;

    // Pass 1: 明示的なアクティブクラスで検出（fontWeightより先に判定することで誤検出を防ぐ）
    // 'on' はAMBIのアクティブページクラス
    let activeEl = allNumericEls.find(el => {
      if (el.classList.contains('active') || el.classList.contains('current') ||
          el.classList.contains('is-active') || el.classList.contains('is-current') ||
          el.classList.contains('selected') || el.classList.contains('is-selected') ||
          el.classList.contains('on')) return true;
      if (el.getAttribute('aria-current') === 'page' || el.getAttribute('aria-selected') === 'true') return true;
      if (el.getAttribute('aria-disabled') === 'true' || el.disabled) return true;
      const parent = el.parentElement;
      if (parent && (parent.classList.contains('active') || parent.classList.contains('current') ||
          parent.classList.contains('is-active') || parent.classList.contains('is-current'))) return true;
      return false;
    });
    // Pass 2: fontWeightフォールバック（明示クラスで見つからなかった場合のみ）
    if (!activeEl) {
      activeEl = allNumericEls.find(el => parseInt(getComputedStyle(el).fontWeight) >= 700);
    }

    if (activeEl) {
      currentPage = parseInt((activeEl.innerText || '').trim(), 10);
      console.log(`[Snow-we] アクティブページ検出: ${currentPage} class="${activeEl.className}" parent="${activeEl.parentElement?.className?.substring(0,40)}"`);
    } else {
      const m = location.href.match(/[?&](?:page|p)=(\d+)/);
      currentPage = m ? parseInt(m[1], 10) : 1;
      console.log(`[Snow-we] URLからページ推定: ${currentPage} url="${location.href.substring(0, 80)}"`);
    }

    const nextBtn = allNumericEls.find(el => {
      const n = parseInt((el.innerText || '').trim(), 10);
      if (n !== currentPage + 1) return false;
      if (el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
      if (el.classList.contains('active') || el.classList.contains('current') ||
          el.classList.contains('is-active') || el.classList.contains('is-current')) return false;
      return true;
    });

    if (nextBtn) {
      console.log(`[Snow-we] 数字ページネーション: ${currentPage} → ${currentPage + 1} tag=${nextBtn.tagName} href=${nextBtn.href || 'なし'}`);
      return nextBtn;
    }
    console.log(`[Snow-we] 次ページボタン未発見 currentPage=${currentPage}`);
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

// リクナビHRTechのカード上の「送済（X日前）」バッジからスカウト送信日数を取得
function getRikunabiScoutDays(cardEl) {
  // カード自身 → 親 → 祖父母 と広げて探す（バッジがDOM外にある場合の対策）
  for (let el = cardEl, depth = 0; el && depth < 4; el = el.parentElement, depth++) {
    const text = el.innerText || '';
    const m = text.match(/送(?:信)?済[（(]\s*(\d+)\s*日前\s*[）)]/);
    if (m) {
      return parseInt(m[1], 10);
    }
  }
  // 座標でバッジ要素を探す（絶対配置で親外に出ている場合）
  const rect = cardEl.getBoundingClientRect();
  const allEls = document.querySelectorAll('span, div, p');
  for (const el of allEls) {
    const t = (el.innerText || '').trim();
    const m = t.match(/^送(?:信)?済[（(]\s*(\d+)\s*日前\s*[）)]$/);
    if (!m) continue;
    const r = el.getBoundingClientRect();
    if (r.top >= rect.top - 10 && r.bottom <= rect.bottom + 10) {
      return parseInt(m[1], 10);
    }
  }
  return null;
}

// モーダル（候補者詳細ポップアップ）またはパネルを下までスクロール
async function scrollModalToBottom() {
  // role="dialog" やクラス名でモーダルを優先して探す
  const modalRoot =
    document.querySelector('[role="dialog"]') ||
    document.querySelector('[class*="modal" i]') ||
    document.querySelector('[class*="dialog" i]') ||
    document.querySelector('[class*="overlay" i]');

  const searchRoot = modalRoot || document.body;
  // スクロール可能な子要素を探す
  let best = null;
  let bestH = 0;
  searchRoot.querySelectorAll('*').forEach(el => {
    const style = window.getComputedStyle(el);
    if (style.overflowY !== 'scroll' && style.overflowY !== 'auto') return;
    const rect = el.getBoundingClientRect();
    if (rect.height > bestH) { best = el; bestH = rect.height; }
  });
  if (best) {
    best.scrollTop = best.scrollHeight;
  } else if (modalRoot) {
    modalRoot.scrollTop = modalRoot.scrollHeight;
  } else {
    window.scrollTo(0, document.body.scrollHeight);
  }
  await sleep(1200);
}

// ページ内の「スカウト送信」テキスト直後の日付から最近の送信日数を返す
function checkScoutSentInBody() {
  // モーダル（候補者詳細）内だけを検索する（ページ全体だと誤検出する）
  const modal = findRDSDetailPanel() ||
    document.querySelector('[role="dialog"]') ||
    document.querySelector('[class*="modal" i]') ||
    document.querySelector('[class*="dialog" i]');

  const searchRoot = modal || document.body;
  const bodyText = searchRoot.innerText || '';

  let minDays = Infinity;
  const now = Date.now();
  let searchFrom = 0;
  while (true) {
    const idx = bodyText.indexOf('スカウト送信', searchFrom);
    if (idx === -1) break;
    const nextChars = bodyText.slice(idx + 6, idx + 10);
    // 「スカウト送信済み」タブ・「スカウト送信履歴」見出し・「スカウト送信する」ボタンはスキップ
    if (nextChars[0] === '済' || nextChars.startsWith('履歴') || nextChars.startsWith('する') || nextChars.startsWith('ボタン')) {
      searchFrom = idx + 7;
      continue;
    }
    // 日付は直後100文字以内に限定（遠い日付=職務経歴日付の誤検出を防ぐ）
    const section = bodyText.slice(idx, idx + 100);
    const dates = section.match(/\d{4}\/\d{2}\/\d{2}/g) || [];
    for (const ds of dates) {
      const d = new Date(`${ds.replace(/\//g, '-')}T00:00:00+09:00`);
      if (isNaN(d.getTime())) continue;
      const daysAgo = Math.floor((now - d.getTime()) / (1000 * 60 * 60 * 24));
      if (daysAgo >= 0 && daysAgo < minDays) minDays = daysAgo;
    }
    searchFrom = idx + 7;
  }
  const result = minDays === Infinity ? null : minDays;
  console.log('[Snow-we] checkScoutSentInBody result:', result);
  return result;
}

// 右パネルのスクロール可能要素を下までスクロールして返す
async function scrollRightPanelToBottom() {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  let best = null;
  let bestArea = 0;
  document.querySelectorAll('*').forEach(el => {
    const rect = el.getBoundingClientRect();
    if (rect.left < vw * 0.4) return; // 右半分のみ
    if (rect.height < vh * 0.3) return;
    const style = window.getComputedStyle(el);
    if (style.overflowY !== 'scroll' && style.overflowY !== 'auto') return;
    const area = rect.width * rect.height;
    if (area > bestArea) { best = el; bestArea = area; }
  });
  if (best) {
    best.scrollTop = best.scrollHeight;
    await sleep(1000);
    return best; // スクロールした要素を返す（スカウト履歴の検索範囲として使う）
  } else {
    window.scrollTo(0, document.body.scrollHeight);
    await sleep(1000);
    return null;
  }
}

// 指定要素（右パネル）内のスカウト履歴セクションから最近の送信日数を返す（なければnull）
function checkScoutHistoryInElement(root) {
  const searchRoot = root || document.body;
  const text = searchRoot.innerText || '';
  const idx = text.indexOf('スカウト履歴');


  if (idx === -1) return null;
  const section = text.slice(idx, idx + 2000);
  const dates = section.match(/\d{4}\/\d{2}\/\d{2}/g) || [];

  let minDays = Infinity;
  const now = Date.now();
  for (const ds of dates) {
    const d = new Date(`${ds.replace(/\//g, '-')}T00:00:00+09:00`);
    if (isNaN(d.getTime())) continue;
    const daysAgo = Math.floor((now - d.getTime()) / (1000 * 60 * 60 * 24));
    if (daysAgo >= 0 && daysAgo < minDays) minDays = daysAgo;
  }
  const result = minDays === Infinity ? null : minDays;
  return result;
}

function buildCriteriaText(criteria, platform) {
  platform = platform || getPlatform();
  const isBizreach = platform === 'bizreach';
  const lines = [];

  // 常時適用される標準基準
  lines.push(`【絶対NG】`);
  lines.push(`- 職歴にアクセンチュアが含まれる場合は即NG`);
  lines.push(`- 職歴にベイカレントが含まれる場合は原則即NG。ただし43歳以上かつ財務・経理・FP&A等の職歴がある場合は「要確認」`);
  lines.push(`- 秘書が実際の職歴・業務内容・職種として含まれる場合は即NG。ただし「総務・法務・知財・秘書」のようなカテゴリ名に秘書が含まれるだけで、実際の職種（「/」以降や業務内容）が法務・総務・人事等の場合はNG対象外`);
  lines.push(`- ITエンジニア系で保守運用のみの場合は即NG`);
  lines.push(`- 46歳以上で文系職（コンサル・営業・マーケ・経営企画・人事・金融営業・システム営業・IT営業等）かつ財務・経理・FP&A・CFO・財務戦略等の職歴が一切ない場合は即NG（年収が高くても）`);
  lines.push(`- ★重要★ 「財務・経理・FP&A職歴あり」の定義: 財務部・経理部・FP&A部門・Treasury・経営管理部（財務担当）等で実際に財務経理業務を担当した経験があること。以下はNG対象外外の例外にはならない：サステナビリティ/ESG担当として経理的な仕組みを設計した、非財務情報開示（SSBJ・TCFD等）を担当した、カーボン会計・GHG会計の仕組みを作った、経理部門と連携しただけ`);
  lines.push(`- 46歳以上でIT・理系・技術職（ソフトウェアエンジニア・インフラ・クラウド・SE・データサイエンティスト・データアナリスト・DXコンサル・PMO・研究職・建築設計・土木・機械設計・電気設計・製造技術・生産技術・品質管理等のIT以外の理工系技術職を含む）は即NG`);
  lines.push(`- 医師・医者・歯科医・歯科医師・薬剤師等の医療資格職が主なキャリアの場合は即NG`);
  lines.push(`- 大学教授・准教授・講師・助教等のアカデミア（学術職）が主なキャリアの場合は即NG`);
  lines.push(`- 弁護士・法律事務所勤務が主なキャリアの場合は即NG`);
  lines.push(`- 記者・ジャーナリスト（新聞・テレビ・雑誌等のメディア記者）が主なキャリアの場合は即NG`);
  lines.push(`- テレビ・映画・ラジオ・出版等のメディア制作職（プロデューサー・ディレクター・編集者・放送作家・カメラマン等）が主なキャリアの場合は即NG`);
  lines.push(`- 自衛官・自衛隊員が主なキャリアの場合は即NG`);
  lines.push(`- 司法書士・行政書士・社会保険労務士・土地家屋調査士等の士業（公認会計士・税理士・弁護士を除く）が主なキャリアの場合は即NG`);
  lines.push(`- フリーランス・個人事業主が主なキャリアで文系職の場合は即NG（ただし理系・IT・技術職のフリーランスはOK）`);
  lines.push(`- 中小企業・無名企業・スタートアップの代表取締役・社長・経営者（自社設立・オーナー経営）が現在の主な活動の場合は即NG。大手・外資・有名上場企業に正社員として勤務中の人のみOK対象`);
  lines.push(`- パチンコ・消費者金融・サラ金・マルチ商法（MLM・ネットワークビジネス）・風俗・ギャンブル関連業界が主なキャリアの場合は即NG`);
  lines.push(`- 現在離職中（無職・求職中・退職済み）の場合は即NG。現在も正社員として在籍中の人のみOK対象`);
  lines.push(`- 現在の雇用形態が契約社員・派遣社員・業務委託・パート・アルバイト等の非正規雇用の場合は即NG。正社員のみOK対象`);

  if (isBizreach) {
    lines.push(`\n【Bizreach専用基準】`);
    lines.push(`※年収はBizreachサイト側のフィルターで1000万円以上に絞り込み済みのため、年収チェックは不要`);

    lines.push(`\n▼経験社数（転職回数）`);
    lines.push(`- 36歳以上：3社まで OK、4社以上 → NG`);
    lines.push(`- 28〜35歳：2社まで OK、3社以上 → NG`);
    lines.push(`- 27歳以下：1社のみ OK、2社以上 → NG`);
    lines.push(`  ※同一グループ・親子会社間の異動・出向は1社としてカウントする`);
    lines.push(`  ※経験社数が読み取れない場合は経験社数でNGにしない`);

    lines.push(`\n▼職種の分類（最初にこれを確認する）`);
    lines.push(`「ITエンジニア・デジタル系」に該当するのは以下のみ：`);
    lines.push(`  ソフトウェアエンジニア・SE・Webエンジニア・インフラエンジニア・クラウドエンジニア・データエンジニア・データサイエンティスト・データアナリスト・DXコンサル・ITコンサル・ITプロジェクトマネージャー（IT系PM）`);
    lines.push(`「それ以外の全職種」は学歴・社格の審査対象：`);
    lines.push(`  営業・コンサル（IT以外）・マーケ・経営企画・財務・人事・金融・テレビ制作・出版・MR・医療営業・製造技術・生産技術・土木・機械設計・電気設計・臨床開発・研究職（製薬・化学・材料等）・品質管理・その他すべて`);

    lines.push(`\n▼学歴・社格基準（「それ以外の全職種」に適用）`);
    lines.push(`- 社格：大手企業・外資系・有名上場企業での勤務経験が必要。中小・無名企業のみはNG`);
    lines.push(`- 学歴：以下のいずれかに該当すること（いずれにも該当しない場合はNG）`);
    lines.push(`  ① 早慶上智（早稲田・慶應・上智）`);
    lines.push(`  ② MARCH・東京理科大（明治・青山学院・立教・中央・法政・東京理科大）`);
    lines.push(`  ③ 国立大学（旧帝大・東工大・一橋・筑波・横浜国立・小樽商科・北海道・東北・名古屋・大阪・九州・神戸・広島・岡山・千葉・埼玉・金沢・信州・静岡・熊本・長崎・鹿児島・琉球等、国が設置する全ての大学）`);
    lines.push(`  ④ 関関同立（関西大・関西学院大・同志社大・立命館大）かつ大手企業・外資系・有名上場企業に現在在籍中`);
    lines.push(`  ⑤ 海外大学卒（どの国・地域でも可）`);
    lines.push(`  ※学歴が不明・記載なしの場合は学歴でNGにしない。社格・経験社数で判断すること`);

    lines.push(`\n▼Bizreach判定方針（迷う場合は必ずNG）`);
    lines.push(`以下の順番で判定すること：`);
    lines.push(`1. 絶対NG条件に該当 → 即NG`);
    lines.push(`2. 経験社数が年齢別上限を超える → NG`);
    lines.push(`3. 「それ以外の全職種」で社格NG（中小・無名企業のみ）→ NG`);
    lines.push(`4. 「それ以外の全職種」で学歴NG（①〜⑤のいずれにも非該当、かつ学歴が明記されている場合）→ NG`);
    lines.push(`5. 上記1〜4のいずれにも該当しない → OK`);
    lines.push(`※「要確認」は絶対に使用しないこと。必ずOKかNGを返すこと`);
    lines.push(`※「ITエンジニア・デジタル系」のみステップ3・4をスキップ。それ以外の技術職（製造・土木・研究等）はスキップしない`);
  } else {
    lines.push(`\n【職種判定】候補者の「直近・現在の職種」で以下のどちらかに分類し、対応する基準を適用してください。過去の経歴や学歴は分類に影響しません。`);
    lines.push(`- 「ITエンジニア系（IT・理系・技術職）」: 現在の職種がソフトウェアエンジニア・SE・インフラ・クラウド・データエンジニア・データサイエンティスト・データアナリスト・DXコンサル・ITコンサル・PMO・研究職（バイオ・化学・材料等）・建築設計・土木・機械設計・電気設計・製造技術・生産技術・品質管理等の技術職`);
    lines.push(`- 「文系職」: 現在の職種がコンサル（IT以外）・営業・マーケ・経営企画・事業企画・財務・人事・金融・その他ビジネス職。理系出身・研究職経験があっても現職が経営企画等のビジネス職であれば文系職として分類する`);

    lines.push(`\n【文系職の年収基準】`);
    lines.push(`- 20代: 500万円未満 → NG`);
    lines.push(`- 30〜35歳: 700万円未満 → NG`);
    lines.push(`- 36〜39歳: 800万円未満 → NG`);
    lines.push(`- 40〜42歳: 1000万円未満 → NG`);
    lines.push(`- 43〜45歳: 1200万円未満 → NG`);
    lines.push(`- 46歳以上: 1200万以上かつ財務・経理・FP&A職歴あり → 要確認、それ以外 → NG`);
    lines.push(`※年収が明記されており基準を下回る場合は必ずNG。年収が不明・記載なしの場合は「要確認」`);

    lines.push(`\n【ITエンジニア系の年収基準】`);
    lines.push(`- 20代: 350万円未満 → NG`);
    lines.push(`- 30〜35歳: 500万円未満 → NG`);
    lines.push(`- 36〜40歳: 700万円未満 → NG`);
    lines.push(`- 40〜45歳: 800万円未満 → NG`);
    lines.push(`※年収が明記されており基準を下回る場合は必ずNG。年収が不明・記載なしの場合は「要確認」`);

    lines.push(`\n【文系職の社格・学歴・転職回数】`);
    lines.push(`- 社格: 職歴全体を通じて上場企業・大手グループ・外資系企業での勤務経験が1社以上あることが必要。中小企業・無名企業のみのキャリアで大手経験が一切ない場合は即NG（年収が高くても）`);
    lines.push(`- 例外: 公認会計士・税理士（監査法人・会計事務所勤務）は業態上、上場企業勤務がないのが通常のため社格要件を問わない。ただし年収基準は適用する`);
    lines.push(`- 学歴: 国立大学・早慶上智・MARCH・東京理科大はOK。それ以外は社格・年収でカバーされればOK`);
    lines.push(`- 転職回数: 20代最大2社、30代最大3社（3社目は年収高ければOK）、40代最大4社`);

    lines.push(`\n【ITエンジニア系の社格・学歴・転職回数】`);
    lines.push(`- 社格: 問わない（大手でなくてもOK）`);
    lines.push(`- 学歴: 問わない（高卒以上OK、スキル重視）`);
    lines.push(`- 転職回数: 20代最大3社、30代最大4社、40代最大5社。1社の在籍が1年未満の場合は注意`);
  }

  if (!isBizreach) {
    lines.push(`\n【判定方針】`);
    lines.push(`以下の順番で判定すること：`);
    lines.push(`1. 絶対NG条件（アクセンチュア・ベイカレント・秘書・保守運用のみ・46歳以上IT理系技術職・46歳以上文系で財務経理歴なし・医師・教授・弁護士・記者・自衛官・士業・文系フリーランス・特定業界・離職中・非正規雇用）に該当する → 即NG`);
    lines.push(`2. 年収が明記されており基準を明確に下回る → NG`);
    lines.push(`3. 在籍期間基準に明確に違反している → NG`);
    lines.push(`4. 文系職で大手・上場・外資勤務経験が一切ない（公認会計士・税理士は除く） → NG`);
    lines.push(`5. 上記1〜4のいずれにも該当しない場合 → 必ずOKとすること`);
    lines.push(`6. 年収・在籍期間が不明で判断できない場合のみ「要確認」`);
    lines.push(`※公認会計士・税理士は医師・教授・弁護士・記者とは異なり即NG対象外。年収基準のみ適用`);
  }

  // 追加条件（設定タブで入力された場合）
  const ai = criteria.ageIncome || {};
  if (criteria.ageMin || criteria.ageMax) {
    const parts = [];
    if (criteria.ageMin) parts.push(`${criteria.ageMin}歳以上`);
    if (criteria.ageMax) parts.push(`${criteria.ageMax}歳以下`);
    lines.push(`- 年齢追加条件: ${parts.join('かつ')}`);
  }
  // minTenure未設定時はデフォルト2年を適用
  const tenureYears = criteria.minTenure || 2;
  lines.push(`- 在籍期間: 異なる会社への転職で${tenureYears}年未満の在籍が1社でもある場合はNG。同一会社内での部署異動・職種変更・昇格・同社への複数行記入は同じ会社の在籍としてまとめて計算すること。出向・兼務の場合は出向元（親会社）の在籍期間に含め、出向先の短期在籍は別会社としてカウントしない。在籍期間が読み取れない場合はスキップ`);
  if (criteria.requiredKeywords) lines.push(`- 必須経験: ${criteria.requiredKeywords}`);
  if (criteria.excludeCompanies) lines.push(`- 除外企業（追加）: 職歴に${criteria.excludeCompanies}が含まれる場合は即NG`);
  if (criteria.excludeKeywords)  lines.push(`- 除外: ${criteria.excludeKeywords}`);
  return lines.join('\n');
}

// ページロード後に自動追加の再開チェック（sessionStorageのみ使用）
window.addEventListener('load', () => {
  setTimeout(async () => {
    injectStyles();
    // chrome.storage.localの古いrunningフラグを常にリセット
    await saveAutoAddProgress({ running: false });
    // sessionStorageの再開フラグのみ信頼する
    try {
      const raw = sessionStorage.getItem('snowWeAutoAdd');
      if (!raw) return;
      const resume = JSON.parse(raw);
      sessionStorage.removeItem('snowWeAutoAdd'); // 即座に削除して二重起動防止
      if (resume.resume) {
        await sleep(1500);
        triggerAutoAdd();
      }
    } catch (_) {}
  }, 1000);
});

// -------------------------------------------------------
// 一括判定：プラットフォーム別カード検出で全候補者を取得
// -------------------------------------------------------
function extractAllCandidateCards() {
  const cards = findCandidateCardsByPlatform();

  return cards.slice(0, 700).map(el => {
    const text = (el.innerText || '').trim();
    const ageMatch = text.match(/(\d{2})歳/);
    // カンマ区切り対応（1,000 ～ 1,199万円 → 1000）
    const numPat = '(?:\\d{1,2},\\d{3}|\\d{3,4})';
    const incomeMatch = text.match(new RegExp(`(${numPat})\\s*[〜~～]\\s*${numPat}万`)) ||
                        text.match(new RegExp(`(${numPat})万円?`)) ||
                        text.match(/(\d{4})万/);
    const lines = text.split('\n').map(l => l.trim()).filter(Boolean);

    return {
      el,
      text,
      age:        ageMatch   ? parseInt(ageMatch[1]) : null,
      incomeText: incomeMatch ? incomeMatch[1].replace(/,/g, '') + '万' : null,
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
  const stopMarkers = [
    'スカウト履歴', 'メモ・備考', '候補者評価', 'スカウト送信履歴',
    'スカウトメール', '送信したメール', 'スカウト文面', 'スカウト送信文',
    'エージェントからのメッセージ', 'この度はご連絡', '貴方様のご経歴を拝見',
    'ご経歴を拝見し', '採用担当者からのメッセージ', 'メッセージ履歴',
    '送信済みテンプレート', '前回スカウト', 'スカウト送信日', '送信日時',
    'スカウト済み', '選考ステータス', 'エージェントメモ', '社内メモ',
  ];
  // マーカーが先頭200文字以内に現れる場合の判断：
  //   テキスト全体にプロフィールキーワード(≥2個)あり → タブラベル（スキップ）
  //   なし → パネル全体がスカウト履歴 → 空を返す
  const profileKws = ['職務経歴', '職歴', 'スキル', '学歴', '業務内容', '自己PR', '資格', '転職理由'];
  // 全文でのキーワード数を先に計算（ループ内で再利用）
  const totalKwHits = profileKws.filter(kw => text.includes(kw)).length;
  let cutIdx = text.length;
  for (const marker of stopMarkers) {
    let idx = text.indexOf(marker);
    if (idx < 0) continue;

    if (idx < 200) {
      if (totalKwHits >= 2) {
        // 全文にプロフィールキーワードが2個以上 → タブラベル: スキップして次の出現を探す
        idx = text.indexOf(marker, idx + marker.length);
        while (idx >= 0 && idx < 200) idx = text.indexOf(marker, idx + marker.length);
      } else {
        // パネルがスカウト履歴そのもの → 空を返す
        return '';
      }
    }

    if (idx >= 0 && idx < cutIdx) cutIdx = idx;
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

// 大学名から学部・研究科サフィックスを除去する
function cleanUnivName(raw) {
  let s = raw.replace(/[（(（(].*/, '').trim();
  // [\S]*(?:大学院|大学|高専|専門学校) をグリーディに使うと
  // "早稲田大学法学部" → "早稲田大学"、"東京大学大学院工学系研究科" → "東京大学大学院" になる
  const m = s.match(/[\S]*(?:大学院|大学|高専|専門学校)/);
  return m ? m[0] : s;
}

// -------------------------------------------------------
// AMBI詳細パネルを特定する
// -------------------------------------------------------
function findAMBIDetailPanel() {
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
  if (candidates.length === 0) return null;
  candidates.sort((a, b) => b.score - a.score);
  return candidates[0].el;
}

// -------------------------------------------------------
// Bizreach詳細パネルを特定する（カードクリックで開く右パネル）
// -------------------------------------------------------
function findBizreachDetailPanel() {
  // 方法1: Bizreach固有のAngularコンポーネント名で直接特定
  const componentSelectors = [
    'ess-resume-detail', 'ess-resume-view', 'ess-resume-detail-content',
    '[class*="resume-detail"]', '[class*="resume-view"]', '[class*="candidate-detail"]',
  ];
  for (const sel of componentSelectors) {
    const el = document.querySelector(sel);
    if (el) {
      const t = (el.innerText || '').trim();
      if (t.length > 100) return el;
    }
  }

  // 方法2: キーワード＋位置ヒューリスティック（位置条件を緩和）
  const viewportWidth = window.innerWidth;
  const keywords = ['在籍企業名', '学歴', '経験職種', '希望年収', '経験業種', '職務経歴', '資格', '年収', '在籍', '職歴'];
  const candidates = [];
  document.querySelectorAll('div, section, article, main').forEach(el => {
    const rect = el.getBoundingClientRect();
    const t = (el.innerText || '').trim();
    // 位置条件を 0.4 → 0.25 に緩和（レイアウト差異を吸収）
    if (rect.left > viewportWidth * 0.25 && rect.width > 250 && t.length > 150 && t.length < 25000) {
      const matchCount = keywords.filter(kw => t.includes(kw)).length;
      if (matchCount >= 2) candidates.push({ el, score: t.length + matchCount * 500 });
    }
  });
  if (candidates.length === 0) return null;
  candidates.sort((a, b) => b.score - a.score);
  return candidates[0].el;
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

  // 方法3: モーダル・ダイアログ（中央配置レイアウト対応）
  if (candidates.length === 0) {
    const profileKeywords = ['職務経歴', '職歴', 'スキル', '学歴', '自己PR'];
    document.querySelectorAll('[role="dialog"],[class*="modal" i],[class*="dialog" i],[class*="overlay" i]').forEach(modal => {
      const innerText = (modal.innerText || '').trim();
      if (innerText.length > 200 && profileKeywords.some(kw => innerText.includes(kw))) {
        candidates.push({ el: modal, score: innerText.length });
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
      ], detailPanel, 30, 12000);

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
        text = removeNonProfileSections(extractMainText(detailPanel, 5000));
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
        const [cls, text] = r.overall === 'OK' ? ['ok', '✅ スカウト推奨']
                          : r.overall === 'NG' ? ['ng', '❌ 見送り']
                          : ['warn', '⚠️ 要確認'];
        setBatchBadge(el, cls, text, '', cards[i]?.summary?.substring(0, 200) || '', r.overall);
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
    (async () => {
      try {
        const isRDS = location.hostname.includes('rikunabi') || location.hostname.includes('hrtech');
        if (isRDS) {
          // スカウト履歴タブが表示されている場合はレジュメタブに切り替える
          await tryClickRDSResumeTab();
          await sleep(500);
          // 詳細パネル内のみスクロール（パネルが見つからない場合は全体スクロールしない）
          const rdsPanel = findRDSDetailPanel();
          if (rdsPanel) {
            let scrollTarget = rdsPanel;
            rdsPanel.querySelectorAll('*').forEach(el => {
              const s = window.getComputedStyle(el);
              if (s.overflowY !== 'scroll' && s.overflowY !== 'auto') return;
              const rect = el.getBoundingClientRect();
              if (rect.height > 200) scrollTarget = el;
            });
            scrollTarget.scrollTop = scrollTarget.scrollHeight;
            await sleep(1000);
          }
        } else {
          await scrollRightPanelToBottom();
        }
        const profileText = extractProfile();
        const panel = findRDSDetailPanel();
        console.log('[Snow-we] extractProfile 結果:', profileText.length, '文字');
        console.log('[Snow-we] detailPanel:', panel ? `あり (${(panel.innerText||'').trim().length}文字)` : 'なし');
        console.log('[Snow-we] プロフィール先頭100文字:', profileText.substring(0, 100));

        // RDSで取得できなかった場合の判定
        const looksEmpty = profileText.trim().length < 50;
        // スカウト履歴タブが開いたままの場合（removeNonProfileSectionsが空を返した）
        const rdsPanel2 = isRDS ? findRDSDetailPanel() : null;
        const rdsPanel2Text = rdsPanel2 ? (rdsPanel2.innerText || '') : '';
        const profileKwsForPanel = ['職務経歴', '職歴', 'スキル', '学歴', '業務内容', '自己PR', '資格', '経験'];
        const panelHasProfileContent = profileKwsForPanel.some(kw => rdsPanel2Text.includes(kw));
        const panelIsScoutHistory = isRDS && rdsPanel2
          && rdsPanel2Text.includes('スカウト履歴')
          && !panelHasProfileContent;

        if (isRDS && (looksEmpty || panelIsScoutHistory)) {
          const errMsg = panelIsScoutHistory
            ? 'レジュメタブを開いてから文生成してください（現在スカウト履歴タブが表示中）'
            : '候補者が選択されていません';
          sendResponse({
            success: false,
            needsCandidateSelection: true,
            profileText: '',
            error: errMsg
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
    })();
    return true; // 非同期レスポンスのためtrueを返す
  }

  if (request.action === 'ping') {
    sendResponse({ ok: true });
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
