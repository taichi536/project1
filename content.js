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

  if (platform === 'ambi') {
    // AMBIは全幅カード。年齢・会社名を含む大きなブロック
    return Array.from(document.querySelectorAll('div, article, li')).filter(el => {
      const rect = el.getBoundingClientRect();
      const text = (el.innerText || '');
      return rect.width > window.innerWidth * 0.5 &&
             rect.height > 100 && rect.height < 800 &&
             agePattern.test(text) &&
             text.length > 100 && text.length < 5000;
    }).filter((el, _, arr) => !arr.some(p => p !== el && p.contains(el)));
  }

  if (platform === 'bizreach') {
    // Bizreachは全幅カード。ラベルなし・コメントなしを含む
    return Array.from(document.querySelectorAll('div, article, li')).filter(el => {
      const rect = el.getBoundingClientRect();
      const text = (el.innerText || '');
      return rect.width > window.innerWidth * 0.5 &&
             rect.height > 80 && rect.height < 600 &&
             agePattern.test(text) &&
             (text.includes('ラベル') || text.includes('コメント') || text.includes('万円')) &&
             text.length > 80 && text.length < 4000;
    }).filter((el, _, arr) => !arr.some(p => p !== el && p.contains(el)));
  }

  if (platform === 'dodax') {
    // doda-Xはカードにタグ・コメントボタンがある
    return Array.from(document.querySelectorAll('div, article, li')).filter(el => {
      const rect = el.getBoundingClientRect();
      const text = (el.innerText || '');
      return rect.width > window.innerWidth * 0.4 &&
             rect.height > 80 && rect.height < 700 &&
             agePattern.test(text) &&
             (text.includes('タグ') || text.includes('コメント') || text.includes('万円')) &&
             text.length > 80 && text.length < 5000;
    }).filter((el, _, arr) => !arr.some(p => p !== el && p.contains(el)));
  }

  // RDS・その他：左側リストのカード
  const vw = window.innerWidth;
  return Array.from(document.querySelectorAll('div, li, article')).filter(el => {
    const rect = el.getBoundingClientRect();
    const text = (el.innerText || '');
    return rect.left < vw * 0.55 &&
           rect.width > 180 && rect.width < vw * 0.6 &&
           rect.height > 50 && rect.height < 500 &&
           agePattern.test(text) &&
           text.length > 40 && text.length < 2000;
  }).filter((el, _, arr) => !arr.some(p => p !== el && p.contains(el)));
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

  // 10秒後に自動解除
  setTimeout(() => {
    btn.classList.remove('snow-we-btn-highlight');
    tip.remove();
  }, 10000);
}

function setupClickTracking() {
  injectStyles();
  document.addEventListener('click', e => {
    const cards = findCandidateCardsByPlatform();
    const clicked = cards.find(c => c.contains(e.target) || c === e.target);
    if (!clicked) return;

    document.querySelectorAll('.snow-we-badge').forEach(b => b.remove());
    document.querySelectorAll('.snow-we-selected').forEach(el => el.classList.remove('snow-we-selected'));

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
// 一括判定：一覧の候補者カードを全て取得
// -------------------------------------------------------
function extractAllCandidateCards() {
  const agePattern = /(\d{2})歳/;
  const vw = window.innerWidth;
  const seen = new Set();
  const results = [];

  // 候補者カードの候補要素を収集（左側リストエリア限定）
  const allEls = Array.from(document.querySelectorAll('div, li, article'));

  for (const el of allEls) {
    const rect = el.getBoundingClientRect();
    // 左側エリア・適度なサイズのカードに限定
    if (rect.left > vw * 0.55) continue;
    if (rect.width < 180 || rect.width > vw * 0.6) continue;
    if (rect.height < 60 || rect.height > 500) continue;
    if (rect.top < 0 || rect.bottom > window.innerHeight + 200) continue;

    const text = (el.innerText || '').trim();
    if (!agePattern.test(text)) continue;
    if (text.length < 40 || text.length > 2000) continue;

    // 親子関係で重複除外
    let isDup = false;
    for (const r of results) {
      if (r.el.contains(el) || el.contains(r.el)) { isDup = true; break; }
    }
    if (isDup || seen.has(el)) continue;
    seen.add(el);

    // カードから基本情報を抽出
    const ageMatch = text.match(/(\d{2})歳/);
    const incomeMatch = text.match(/(\d{3,4})[〜~～](\d{3,4})万円/) ||
                        text.match(/(\d{3,4})万円/) ||
                        text.match(/(\d{4})万/);
    const lines = text.split('\n').map(l => l.trim()).filter(Boolean);

    results.push({
      el,
      text,
      age: ageMatch ? parseInt(ageMatch[1]) : null,
      incomeText: incomeMatch ? incomeMatch[0] : null,
      summary: lines.slice(0, 8).join(' / ')
    });
  }

  // カード面積が近いものをグループ化して最小単位を選ぶ
  return results.slice(0, 20);
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
// RDS詳細パネルを特定する（プロフィール内容を必須条件に）
// -------------------------------------------------------
function findRDSDetailPanel() {
  const vw = window.innerWidth;
  const candidates = [];

  // 方法1: 「職務経歴」など複数のプロフィールキーワードを含む右側パネルを探す
  document.querySelectorAll('div, section, article, main').forEach(el => {
    const rect = el.getBoundingClientRect();
    if (rect.left < vw * 0.3 || rect.width < 250 || rect.height < 300) return;
    const text = (el.innerText || '').trim();
    if (text.length < 200 || text.length > 20000) return;
    if (!hasProfileContent(text)) return;
    candidates.push({ el, score: text.length });
  });

  // 方法2: 「候補者詳細」見出しを持つ親コンテナ
  if (candidates.length === 0) {
    document.querySelectorAll('h1,h2,h3,h4,h5,h6,div,span').forEach(el => {
      const t = (el.innerText || el.textContent || '').trim();
      if (t !== '候補者詳細' && t !== '候補者 詳細') return;
      let parent = el.parentElement;
      for (let i = 0; i < 10; i++) {
        if (!parent) break;
        const text = (parent.innerText || '').trim();
        if (text.length > 300 && hasProfileContent(text)) {
          candidates.push({ el: parent, score: text.length });
          break;
        }
        parent = parent.parentElement;
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

      if (text.length < 100) {
        text = extractMainText(detailPanel, 2500);
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
  if (request.action === 'getBatchCandidates') {
    try {
      injectStyles();
      const cards = extractAllCandidateCards();
      // 判定中バッジを全カードに表示
      cards.forEach(c => {
        if (getComputedStyle(c.el).position === 'static') c.el.style.position = 'relative';
        c.el.classList.add('snow-we-selected');
        const badge = document.createElement('div');
        badge.className = 'snow-we-badge checking';
        badge.textContent = '🔍 判定中...';
        c.el.appendChild(badge);
      });
      sendResponse({ success: true, cards: cards.map(c => ({ summary: c.summary, age: c.age, incomeText: c.incomeText, text: c.text.substring(0, 600) })) });
    } catch (e) {
      sendResponse({ success: false, error: e.message });
    }
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
        badge.className = `snow-we-badge ${cls}`;
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
