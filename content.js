// content.js v1.3.0
// 各媒体のプロフィールページからテキストを抽出する

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
// RDS詳細パネルを特定する
// -------------------------------------------------------
function findRDSDetailPanel() {
  const candidates = [];

  document.querySelectorAll('h1, h2, h3, h4, h5, h6, div, span').forEach(el => {
    const t = (el.innerText || el.textContent || '').trim();
    if (t === '候補者詳細' || t === '候補者 詳細') {
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
    }
  });

  if (candidates.length === 0) {
    const viewportWidth = window.innerWidth;
    document.querySelectorAll('div, section, article, main').forEach(el => {
      const rect = el.getBoundingClientRect();
      if (rect.left > viewportWidth * 0.35 &&
          rect.width > 300 &&
          rect.height > 400) {
        const innerText = (el.innerText || '').trim();
        if (innerText.length > 200) {
          candidates.push({ el, score: innerText.length });
        }
      }
    });
  }

  const urlMatch = location.href.match(/\/scoutroom\/(\d+)\//);
  if (urlMatch && candidates.length === 0) {
    const candidateId = urlMatch[1];
    document.querySelectorAll(`[data-id="${candidateId}"], [data-candidate-id="${candidateId}"]`).forEach(el => {
      const parent = el.closest('[class*="detail"]') || el.closest('[class*="panel"]') || el.parentElement;
      if (parent) candidates.push({ el: parent, score: (parent.innerText || '').length });
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
  if (request.action === 'getProfile') {
    try {
      const profileText = extractProfile();
      sendResponse({
        success: true,
        profileText,
        url: location.href,
        hostname: location.hostname,
        length: profileText.length
      });
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
