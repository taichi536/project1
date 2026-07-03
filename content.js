// content.js v1.18.108
// 各媒体のプロフィールページからテキストを抽出する

// 複数VMインスタンス競合防止：このインスタンス固有のIDをDOMに刻印し、
// 最新インスタンスのみがクリックイベントを処理する
const _INSTANCE_ID = String(Date.now());
document.documentElement.setAttribute('data-snow-we-id', _INSTANCE_ID);

// Chrome の Extension context invalidated は try-catch をすり抜けて
// グローバルの unhandledrejection として発火することがある → 全体で抑制
window.addEventListener('unhandledrejection', event => {
  const msg = event.reason?.message || String(event.reason || '');
  if (msg.includes('Extension context invalidated') || msg.includes('message channel closed')) {
    event.preventDefault();
  }
});

// Supabase設定
const SUPABASE_URL = 'https://ovwnyivqnqqiagutjxoo.supabase.co';
const SUPABASE_KEY = 'sb_publishable_tEQ4TOve0uCydsGiEm1cDA_D1LQ49wN';

async function supabaseInsert(table, data) {
  try {
    const res = await fetch(`${SUPABASE_URL}/rest/v1/${table}`, {
      method: 'POST',
      headers: {
        'apikey': SUPABASE_KEY,
        'Authorization': `Bearer ${SUPABASE_KEY}`,
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
      },
      body: JSON.stringify(data)
    });
    if (!res.ok) {
      const err = await res.text();
      console.warn(`[Snow-we] Supabase ${table} 保存エラー:`, err);
      return false;
    }
    console.log(`[Snow-we] Supabase ${table} 保存成功`);
    return true;
  } catch (e) {
    console.warn(`[Snow-we] Supabase ${table} 保存失敗:`, e.message);
    return false;
  }
}

// ポジション要件のセッション内キャッシュ（GAS呼び出しを最小化）
const _posReqCache = new Map();

// Bizreach仮想スクロール対応：バッジ状態レジストリ
const _bizreachBadgeRegistry = new Map(); // resumeId → {cls, text, tooltip, profileSummary, aiVerdict}
let _bizreachObserver = null;
let _reapplyBizreachTimer = null;

// バッチ処理中のAPIキー・条件キャッシュ（Extension context invalidated 後の再読み込みを防ぐ）
let _batchApiKey = null;
let _batchCriteria = null;
let _batchIsRunning = false; // chrome.storage失敗時もisFreshStartを誤判定しないためのフラグ
let _triggerAutoAddLock = false; // 外部からの重複起動を防ぐロック（再帰呼び出しは _batchIsRunning=true で区別）
let _batchScoutHistory = null; // スカウト履歴キャッシュ（CDKスクロールごとの再取得を防ぐ）

// 夜間自動実行モード
let _isAutoRunMode = false;
let _autoRunPageCount = 0;
let _autoRunMaxPages = 2;
let _autoRunSlotId = 0;


// -------------------------------------------------------
// プラットフォーム判定
// -------------------------------------------------------
function getPlatform() {
  const h = location.hostname;
  if (h.includes('rikunabi') || h.includes('hrtech') || h.includes('recruitdirect')) return 'rds';
  if (h.includes('bizreach') || h.includes('es-support'))  return 'bizreach';
  if (h.includes('doda-x') || h.includes('dodax') || h.includes('x.doda')) return 'dodax';
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
    .snow-we-fb-reason {
      color: #c7d2fe !important; font-size: 10px !important; font-family: -apple-system, sans-serif !important;
      padding: 2px 2px 4px !important; border-bottom: 1px solid #3730a3 !important; margin-bottom: 2px !important;
      line-height: 1.4 !important; max-width: 200px !important; word-break: break-all !important;
    }
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
    // 実際のDOMから確認した正確なセレクター
    const cards = Array.from(document.querySelectorAll('.js_userSet')).filter(el => {
      // スカウト済みカードも含めてIDを取得するためフィルタは緩く
      return (el.innerText || '').length > 30;
    });
    if (cards.length > 0) {
      console.log('[Snow-we] AMBI カード検出 .js_userSet 件数:', cards.length);
      return dedup(cards);
    }
    return [];
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
    // doda-X (doda-x.jp / x.doda.jp) の候補者カード
    const hits = dedup(Array.from(document.querySelectorAll('div, article, li')).filter(el => {
      const rect = el.getBoundingClientRect();
      const text = (el.innerText || '');
      return rect.width > vw * 0.4 &&
             rect.height > 60 && rect.height < 1000 &&
             agePattern.test(text) &&
             (text.includes('タグ') || text.includes('コメント') ||
              text.includes('万円') || text.includes('年収') ||
              text.includes('経験') || text.includes('スカウト')) &&
             text.length > 80 && text.length < 10000;
    }));
    console.log('[Snow-we] doda-x カード検出数:', hits.length, '/ url:', location.hostname);
    return hits;
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

// 会社名キーワードから業界を簡易判定（GASのgicsAutoClassifyを移植）
function gicsAutoClassify(companyName) {
  if (!companyName) return '';
  const n = companyName.replace(/[株式会社　\s]/g, '').toLowerCase();

  // コンサルティング・専門サービス
  if (/accenture|アクセンチュア/.test(n))                                  return 'コンサルティングサービス';
  if (/マッキンゼー|mckinsey|ボストンコンサル|bcg|roland berger|ローランドベルガー|bain|ベイン/.test(n)) return 'コンサルティングサービス';
  if (/デロイト|deloitte|pwc|kpmg|ey |アーンスト/.test(n))                 return 'コンサルティングサービス';
  if (/ベイカレント|baycurrent/.test(n))                                    return 'コンサルティングサービス';
  if (/アビーム|abeam/.test(n))                                             return 'コンサルティングサービス';

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

  // 電子装置・機器・部品
  if (/東芝|toshiba/.test(n) && !/デバイス/.test(n))                       return '電子装置・機器・部品';
  if (/三菱電機|mitsubishi electric/.test(n))                               return '電子装置・機器・部品';
  if (/キーエンス|keyence/.test(n))                                         return '電子装置・機器・部品';

  // 民生用電子機器
  if (/ソニー|sony/.test(n))                                                return '民生用電子機器';
  if (/パナソニック|panasonic/.test(n))                                     return '民生用電子機器';
  if (/シャープ|sharp/.test(n))                                             return '民生用電子機器';

  // SaaS
  if (/salesforce|セールスフォース/.test(n))                                return 'SaaS';
  if (/freee/.test(n))                                                       return 'SaaS';
  if (/smarthr/.test(n))                                                     return 'SaaS';
  if (/マネーフォワード|money forward/.test(n))                             return 'SaaS';
  if (/sansan/.test(n))                                                      return 'SaaS';
  if (/cybozu|サイボウズ|kintone/.test(n))                                  return 'SaaS';

  // ソフトウェア
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
  if (/ntt(東日本|西日本)/.test(n) || n === 'ntt')                          return '各種電気通信サービス';

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
  if (/川崎重工|川崎車両|川崎車輛|三菱重工|ihiエアロ|ihi|石川島/.test(n))  return '重工業';

  // 半導体・半導体製造装置
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
  if (/jr.*(東日本|西日本|東海|九州|北海道)|鉄道|railway/.test(n))         return '陸上運輸';
  if (/商船三井|日本郵船|川崎汽船|海運/.test(n))                            return '海上運輸';

  // エネルギー・化学
  if (/jxtg|eneos|出光|idemitsu|コスモ石油/.test(n))                        return '石油・ガス・消耗燃料';
  if (/東電|東京電力|関西電力|中部電力|九州電力|電力|北陸電力|東北電力|北海道電力|四国電力/.test(n)) return '電力';
  if (/大阪ガス|東京ガス|東邦ガス|西部ガス|都市ガス/.test(n))               return 'ガス';
  if (/旭化成|住友化学|三菱化学|東レ|toray|化学/.test(n))                   return '化学';

  // 官公庁・教育機関
  if (/省|庁|役所|官公庁|市役所|区役所|町役場|裁判所|警察署|消防署|検察庁|税務署|法務局|国会|議会/.test(n)) return '官公庁';
  if (/大学|高校|中学校|小学校|専門学校|学校法人|教育委員会|幼稚園|保育園/.test(n)) return '教育機関';

  // 汎用キーワード（最後のフォールバック）
  if (/(コンサルティング|コンサルタント|consulting)/.test(n)) return 'コンサルティングサービス';
  if (/(人材|採用サービス|ヘッドハンティング)/.test(n)) return '人事・雇用サービス';
  if (/(フィンテック|fintech|決済サービス|ペイメント)/.test(n)) return '金融サービス';
  if (/(ゲーム会社|ゲーム開発|gaming)/.test(n)) return '娯楽';
  if (/(物流会社|運送会社|配送サービス)/.test(n)) return '航空貨物・物流サービス';
  if (/(医療法人|クリニック|診療所|病院)/.test(n)) return 'ヘルスケアプロバイダー';
  if (/(介護|福祉|ケアサービス)/.test(n)) return 'ヘルスケアプロバイダー';
  if (/(スタートアップ|ベンチャー企業)/.test(n)) return 'その他';

  return '';
}

async function getScoutHistory() {
  try {
    const r = await chrome.storage.local.get([SCOUT_KEY]);
    return r[SCOUT_KEY] || {};
  } catch (e) {
    if (!e.message?.includes('Extension context invalidated'))
      console.warn('[Snow-we] getScoutHistory error:', e.message);
    return {};
  }
}

async function recordScoutSent(candidateId, info, templateName, templateRaw = '', fallbackPosition = '') {
  if (!candidateId) return;
  const now = Date.now();
  const platform = getPlatform();
  const positionName = templateName || fallbackPosition || '';
  const industry = gicsAutoClassify(info.company || '');

  // ① ローカル記録（メイン・必ず保存）
  const history = await getScoutHistory();
  history[candidateId] = {
    date: now,
    platform,
    name: info.name || '',
    company: info.company || '',
    age: info.age || '',
    univ: info.univ || '',
    position: positionName,
    industry,
    gasSent: false,
  };
  try {
    await chrome.storage.local.set({ [SCOUT_KEY]: history });
  } catch (e) {
    if (!e.message?.includes('Extension context invalidated')) console.warn('[Snow-we] recordScoutSent storage error:', e.message);
  }

  // ② GASへの送信（サブ・失敗してもローカル記録には影響しない）
  ;(async () => {
    let r2 = {};
    try { r2 = await chrome.storage.local.get(['gasSettings', 'currentPosition', 'recruiterName']); } catch (_) {}
    const gas = r2.gasSettings || {};
    const recruiterForGas = gas.recruiter || r2.recruiterName || '';
    const primaryGasUrl = gas.url || gas.dbUrl;
    if (!primaryGasUrl || !recruiterForGas || gas.scoutRecordEnabled === false) return;
    const ageNum = (info.age || '').replace(/[歳才]/, '');
    const payload = {
      secret: gas.secret || 'snowwe2024',
      recruiter: recruiterForGas,
      company: info.company || '',
      age: ageNum,
      univ: info.univ || '',
      media: platform,
      position: positionName || r2.currentPosition || '',
      industry,
      ts: now,
    };
    console.log('[Snow-we] GAS送信payload:', JSON.stringify({ recruiter: payload.recruiter, position: payload.position, industry: payload.industry, media: payload.media, ts: payload.ts, age: payload.age, company: payload.company }));
    let sent = false;
    const sendGas = async (url) => {
      try {
        const r = await chrome.runtime.sendMessage({ type: 'gasPost', url, payload });
        if (!r?.ok) throw new Error('GAS returned ok:false');
        console.log('[Snow-we] GAS送信成功:', url.substring(0, 60));
        sent = true;
      } catch (e) {
        console.warn('[Snow-we] GAS送信失敗、リトライ:', e.message);
        await new Promise(resolve => setTimeout(resolve, 1500));
        try {
          const r2 = await chrome.runtime.sendMessage({ type: 'gasPost', url, payload });
          if (r2?.ok) sent = true;
          console.log('[Snow-we] GAS送信リトライ成功');
        } catch (e2) {
          console.warn('[Snow-we] GAS送信リトライも失敗:', e2.message);
        }
      }
    };
    await sendGas(primaryGasUrl);
    if (gas.dbUrl && gas.dbUrl !== primaryGasUrl) await sendGas(gas.dbUrl);
    // GAS送信成功時にフラグを更新
    if (sent) {
      try {
        const h = await getScoutHistory();
        if (h[candidateId]) {
          h[candidateId].gasSent = true;
          await chrome.storage.local.set({ [SCOUT_KEY]: h });
        }
      } catch (_) {}
    }
  })();

  // ③ Supabaseへの保存
  ;(async () => {
    let recruiter = '';
    let currentPosition = '';
    try {
      const s = await chrome.storage.local.get(['gasSettings', 'currentPosition', 'recruiterName']);
      recruiter = s.gasSettings?.recruiter || s.recruiterName || '';
      currentPosition = s.currentPosition || '';
    } catch (_) {}
    const ageNum = parseInt((info.age || '').replace(/[歳才]/g, '')) || null;
    await supabaseInsert('scouts', {
      platform,
      platform_candidate_id: candidateId,
      candidate_name: info.name || '',
      candidate_age: ageNum,
      candidate_industry: industry,
      company_name: info.company || '',
      university: info.univ || '',
      position_name: positionName || currentPosition,
      recruiter_name: recruiter,
      sent_at: new Date(now).toISOString(),
      scout_message: templateRaw || ''
    });
  })();
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
  // AMBI: hidden input.js_sid から候補者ID取得
  if (getPlatform() === 'ambi') {
    const sidInput = cardEl.querySelector('input.js_sid');
    if (sidInput?.value) return `ambi_${sidInput.value}`;
    // フォールバック: No.XXXXXXX テキスト
    const m = (cardEl.innerText || '').match(/No\.(\d{5,})/);
    if (m) return `ambi_${m[1]}`;
    // 最終フォールバック: カードテキストハッシュ
    const lines = (cardEl.innerText || '').split('\n').map(l => l.trim()).filter(Boolean);
    const fp = lines.slice(0, 5).join('|');
    if (fp.length > 10) return `ambi_h${simpleHash(fp)}`;
    return null;
  }

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

  // 大学名を抽出（学歴セクション優先）
  let univ = '';
  const extractUnivFromText = (t) => {
    // 「学歴」「最終学歴」セクション以降から優先的に抽出
    const eduIdx = t.search(/学歴|最終学歴/);
    if (eduIdx >= 0) {
      const eduSection = t.substring(eduIdx, eduIdx + 300);
      const m = eduSection.match(/([^\s\n　]{2,20}(?:大学院|大学|高専|専門学校))/);
      if (m) return cleanUnivName(m[1]);
    }
    // 学歴セクションがない場合は全体から抽出（会社名候補を除外）
    const m = t.match(/([^\s\n　]{2,20}(?:大学院|大学|高専|専門学校))/g) || [];
    const companyWords = /株式会社|合同会社|有限会社|法人|グループ|ホールディングス/;
    const candidate = m.find(s => !companyWords.test(s));
    return candidate ? cleanUnivName(candidate) : '';
  };
  univ = extractUnivFromText(text);
  // RDS/AMBIはカードに大学名が出ないため、詳細パネルからも取得を試みる
  if (!univ) {
    const platform = getPlatform();
    let panel = null;
    if (platform === 'rds') panel = findRDSDetailPanel();
    else if (platform === 'dodax') panel = findDodaxDetailPanel();
    else panel = findAMBIDetailPanel();
    if (panel) {
      univ = extractUnivFromText(panel.innerText || '');
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
  } else if (getPlatform() === 'dodax') {
    // doda-X: 「現職」「在籍」の近くか、会社名キーワードを含む行を優先
    const companyRe2 = /株式会社|合同会社|有限会社|LLC|Inc\.|Co\.,|ホールディングス|グループ|銀行|証券|保険|大学|病院/;
    const idx2 = lines.findIndex(l => l === '現職' || l.includes('在籍'));
    if (idx2 >= 0) {
      for (let i = Math.max(0, idx2 - 3); i < Math.min(lines.length, idx2 + 3); i++) {
        if (i === idx2) continue;
        if (companyRe2.test(lines[i]) || (lines[i].includes('／') && lines[i].length > 4)) {
          company = lines[i].split(/[／/]/)[0].trim(); break;
        }
      }
    }
    if (!company) company = lines.find(l => companyRe2.test(l))?.split(/[／/]/)[0].trim() || '';
    // doda-Xは詳細パネルからも会社名を取得試み
    if (!company) {
      const p = findDodaxDetailPanel();
      if (p) {
        const pLines = (p.innerText || '').split('\n').map(l => l.trim()).filter(Boolean);
        company = pLines.find(l => companyRe2.test(l))?.split(/[／/]/)[0].trim() || '';
      }
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
  // 最新インスタンスのみ処理（古いVMインスタンスはスキップ）
  if (document.documentElement.getAttribute('data-snow-we-id') !== _INSTANCE_ID) return;

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

    // RDS: ボタンが詳細パネル内にある場合は詳細パネルを優先（リストカードと混同しない）
    if (getPlatform() === 'rds') {
      const detailPanel = findRDSDetailPanel();
      if (detailPanel && detailPanel.contains(btn)) {
        card = detailPanel;
      }
    }

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
        // スカウトボタン押下時のポジション名をフォールバック用に保存（照合失敗時も正しいポジションを記録するため）
        (async () => {
          try {
            const { currentPosition } = await chrome.storage.local.get(['currentPosition']);
            if (currentPosition) {
              const raw2 = sessionStorage.getItem('pendingScout');
              if (raw2) {
                const p2 = JSON.parse(raw2);
                if (!p2.fallbackPosition) {
                  p2.fallbackPosition = currentPosition;
                  sessionStorage.setItem('pendingScout', JSON.stringify(p2));
                }
              }
            }
          } catch (_) {}
        })();
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

        // AC）/ BC( で始まるテンプレート名はポジション名そのもの（スプレッドシートのドロップダウンと同形式）
        if (/^[AB]C[）(]/.test(tmplName)) {
          pending.templateRaw = tmplName;
          pending.templateName = tmplName;
          console.log('[Snow-we] AC/BC形式テンプレートを直接採用:', tmplName);
          sessionStorage.setItem('pendingScout', JSON.stringify(pending));
          return;
        }

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
        // 完全一致 → サフィックス除去後一致（一意の場合のみ）の順で照合
        const exactHits = sorted.filter(p => p && normT(tmplName) === normT(p));
        const stripHits = exactHits.length === 0
          ? sorted.filter(p => { const t = stripSuffix(p); return t.length >= 8 && normT(tmplName) === normT(t); })
          : [];
        // 候補が複数ある場合は誤マッチを避けるため採用しない
        const candidates = exactHits.length > 0 ? exactHits : stripHits;
        const matched = candidates.length === 1 ? candidates[0] : '';
        console.log('[Snow-we] テンプレート照合試行: tmplName=', tmplName, '/ matched=', matched || 'なし（templateRawを使用）');

        pending.templateRaw = tmplName;
        if (matched) {
          pending.templateName = matched;
          console.log('[Snow-we] テンプレート名からポジション照合成功:', matched);
        } else {
          console.log('[Snow-we] テンプレート名照合失敗。templateRaw として保存:', tmplName);
        }
        sessionStorage.setItem('pendingScout', JSON.stringify(pending));
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
        // スカウトメール作成モーダル内だけを検索（スカウト履歴パネルを除外するため）
        const modal = document.querySelector('[role="dialog"]') ||
                      document.querySelector('[class*="modal" i]') ||
                      document.querySelector('[class*="dialog" i]');
        const searchRoot = modal || document.body;
        const bodyEl = searchRoot.querySelector('textarea') ||
                       searchRoot.querySelector('[contenteditable="true"]');
        let bodyText = '';
        if (bodyEl) {
          bodyText = bodyEl.value || bodyEl.innerText || '';
        } else {
          // モーダルが見つからない場合はページ全体から「スカウト履歴」以降を除外して使用
          const rawPageText = searchRoot.innerText || '';
          const histIdx = rawPageText.indexOf('スカウト履歴');
          bodyText = histIdx > 50 ? rawPageText.substring(0, histIdx) : rawPageText;
        }

        // モーダル内の選択中テンプレート名を取得（select や data属性）
        let tmplRaw = '';
        const tmplSel = searchRoot.querySelector('select');
        if (tmplSel) {
          const selText = (tmplSel.options[tmplSel.selectedIndex]?.text || '').trim();
          if (selText && selText.length > 3) tmplRaw = selText;
        }
        if (!tmplRaw) {
          // テンプレート名ラベルを探す（selected/active な行のタイトル等）
          const activeLabel = searchRoot.querySelector('[class*="selected"] [class*="title"], [class*="active"] [class*="title"], [class*="template"][class*="name"]');
          if (activeLabel) tmplRaw = (activeLabel.textContent || '').trim();
        }

        let matched = '';
        try {
          const res = await chrome.runtime.sendMessage({ type: 'getPositionList' });
          const positionList = res?.positions || [];
          const sorted = [...positionList].sort((a, b) => b.length - a.length);
          const normStr = s => s
            .replace(/[-–—－]/g, '-').replace(/[（]/g, '(').replace(/[）]/g, ')')
            .replace(/　/g, ' ').trim();
          const stripSuffix2 = p => p
            .replace(/\s*[-–—－]\s*[A-Za-z]{2,}[\s）)]*$/, '')
            .replace(/\s*[-–—－]\s*[゠-ヿ一-鿿]{2,}[\s）)]*$/, '')
            .trim();
          const normBody = normStr(bodyText);
          console.log('[Snow-we] メール本文先頭200字:', bodyText.substring(0, 200));
          // テンプレート名一致（取得できた場合）→ 本文内ポジション一致（一意のみ）の順で照合
          if (tmplRaw) {
            // AC）/ BC( 形式はスプレッドシートのドロップダウンと同形式なので直接採用
            if (/^[AB]C[）(]/.test(tmplRaw)) {
              matched = tmplRaw;
            } else {
              const exactHits = sorted.filter(p => p && normStr(tmplRaw) === normStr(p));
              const stripHits = exactHits.length === 0
                ? sorted.filter(p => { const t = stripSuffix2(p); return t.length >= 8 && normStr(tmplRaw) === normStr(t); })
                : [];
              const tmplCandidates = exactHits.length > 0 ? exactHits : stripHits;
              if (tmplCandidates.length === 1) matched = tmplCandidates[0];
            }
          }
          // 「」引用テキスト照合（BC（FAS）→「FASグループ」等の略称マッチを含む）
          if (!matched) {
            const quotedList = [...bodyText.substring(0, 400).matchAll(/「([^」]+)」/g)].map(m => normStr(m[1].trim()));
            for (const qn of quotedList) {
              if (qn.length < 3) continue;
              const qHits = sorted.filter(p => {
                if (!p || typeof p !== 'string') return false;
                const np = normStr(p), ns = normStr(stripSuffix2(p));
                if (np === qn || ns === qn) return true;
                if (np.startsWith(qn) || ns.startsWith(qn)) return true;
                const inner = (p.match(/[（(]([^）)]{2,6})[）)]/) || [])[1] || '';
                return inner && qn.startsWith(normStr(inner));
              });
              if (qHits.length === 1) { matched = qHits[0]; break; }
            }
          }
          // テンプレート名で照合できなかった場合のみ本文照合（一意チェック付き）
          if (!matched) {
            const bodyHits = sorted.filter(p => p && normBody.includes(normStr(p)));
            if (bodyHits.length === 1) matched = bodyHits[0];
          }
        } catch (_) {}

        // 生テンプレート名・メール本文・照合結果を保存
        if (tmplRaw && !pending.templateRaw) pending.templateRaw = tmplRaw;
        if (bodyText && !pending.bodyText) pending.bodyText = bodyText.substring(0, 2000);
        if (matched) {
          pending.templateName = matched;
          console.log('[Snow-we] ポジション照合成功:', matched);
        } else {
          console.log('[Snow-we] ポジション照合できず。templateRaw:', tmplRaw || 'なし');
        }
        sessionStorage.setItem('pendingScout', JSON.stringify(pending));
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
          // AMBIはテンプレートドロップダウンからポジションを取得、本文も送信時に取得
          if (getPlatform() === 'ambi') {
            // テンプレート名からポジション照合
            if (!pending.templateName) {
              const tmplSel = document.querySelector('select');
              const tmplVal = tmplSel ? (tmplSel.options[tmplSel.selectedIndex]?.text || '').trim() : '';
              if (tmplVal && tmplVal !== 'テンプレートの選択') {
                if (!pending.templateRaw) pending.templateRaw = tmplVal;
                const res = await chrome.runtime.sendMessage({ type: 'getPositionList' });
                const positionList = res?.positions || [];
                const sorted = [...positionList].sort((a, b) => b.length - a.length);
                const normStr = s => s.replace(/[-–—－]/g, '-').replace(/[（]/g, '(').replace(/[）]/g, ')').replace(/　/g, ' ').trim();
                const stripSuffix3 = p => p.replace(/\s*[-–—－]\s*[A-Za-z]{2,}[\s）)]*$/, '').replace(/\s*[-–—－]\s*[゠-ヿ一-鿿]{2,}[\s）)]*$/, '').trim();
                const exactHits = sorted.filter(p => p && normStr(tmplVal) === normStr(p));
                const stripHits = exactHits.length === 0
                  ? sorted.filter(p => { const t = stripSuffix3(p); return t.length >= 8 && normStr(tmplVal) === normStr(t); })
                  : [];
                const candidates2 = exactHits.length > 0 ? exactHits : stripHits;
                pending.templateName = candidates2.length === 1 ? candidates2[0] : '';
              }
            }
            // 確認ステップがないため送信時にメール本文を取得
            if (!pending.bodyText) {
              const ta = document.querySelector('textarea');
              if (ta && ta.value && ta.value !== 'スカウト本文を入力') {
                pending.bodyText = ta.value.substring(0, 2000);
              }
            }
          }
          // 送信直前にインジケーターの最新選択値を読み取る（スカウトボタン押下後に変更した場合も反映）
          let latestPosition = pending.fallbackPosition || '';
          try {
            const posData = await chrome.storage.local.get(['currentPosition']);
            if (posData.currentPosition) latestPosition = posData.currentPosition;
          } catch (_) {}
          console.log('[Snow-we] recordScoutSent 呼び出し id:', pending.id, '/ template:', pending.templateName || 'なし', '/ fallback:', latestPosition || 'なし');
          recordScoutSent(pending.id, pending.info || {}, pending.templateName || '', pending.bodyText || '', latestPosition);
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

  // AMBI: per_page=1000 で全件表示済み → DOMにすでに存在するため何もしない
  // (per_page チェック＆リダイレクトは triggerAutoAdd / autoScreenCandidates で行う)
  if (platform === 'ambi') return;

  const LOAD_MORE_TEXTS = ['さらに読み込む', 'もっと見る', 'Load more', '次の候補者'];
  const MAX_LOADS = 100;
  const TARGET_COUNT = 2000;

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
  let stored = {};
  try { stored = await chrome.storage.local.get(['apiKey', 'screeningCriteria', 'currentPosition']); } catch (_) { return; }
  const apiKey = (stored.apiKey || '').replace(/[^\x21-\x7E]/g, '').trim();
  if (!apiKey || apiKey.length < 20) return; // APIキー未設定なら何もしない

  const criteria = stored.screeningCriteria || {};
  const currentPosition = stored.currentPosition || '';

  // ポジション要件・フィードバックを並列取得（スクリーニング精度向上）
  let posReq = '', companyCriteria = '', feedbacks = [];
  try {
    const [reqRes, fbData] = await Promise.all([
      currentPosition ? fetchPositionRequirements(currentPosition) : Promise.resolve(null),
      loadRecentFeedbacks(5),
    ]);
    posReq = reqRes?.requirements || '';
    companyCriteria = reqRes?.companyCriteria || '';
    feedbacks = fbData;
  } catch (_) {}

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
    const results = await callBatchScreeningAPI(apiKey, cards, criteria, posReq, feedbacks, currentPosition, companyCriteria);

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

function showPreviousResultsBanner(progress) {
  const existing = document.getElementById('snow-we-results-banner');
  if (existing) existing.remove();
  const v = progress.verdicts || {};
  const ok = v.ok || 0;
  const ng = v.ng || 0;
  const pending = v.pending || 0;
  const total = progress.processed || 0;
  if (total === 0) return;
  const banner = document.createElement('div');
  banner.id = 'snow-we-results-banner';
  banner.style.cssText = `position:fixed;top:0;left:0;right:0;z-index:2147483647;background:rgba(30,30,30,0.92);color:#fff;padding:8px 16px;font-size:12px;font-family:-apple-system,sans-serif;display:flex;align-items:center;gap:16px;box-shadow:0 2px 8px rgba(0,0,0,0.3);`;
  banner.innerHTML = `<span style="font-weight:600;">📊 前ページまでの選定結果 (${total}人判定)</span><span>✅ OK: <b>${ok}人</b></span><span>❌ NG: <b>${ng}人</b></span><span>⚠️ 要確認: <b>${pending}人</b></span><button onclick="this.parentElement.remove()" style="margin-left:auto;background:none;border:none;color:#aaa;cursor:pointer;font-size:16px;">×</button>`;
  document.body.appendChild(banner);
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
    if (response.status === 529 || response.status === 429) {
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
async function callBatchScreeningAPI(apiKey, cards, criteria, posReq = '', feedbacks = [], positionName = '', companyCriteria = '') {
  const criteriaLines = buildCriteriaText(criteria, getPlatform());
  const posSection = posReq ? `\n【応募ポジション：${positionName}】\n${posReq.slice(0, 800)}\n` : '';
  const companySection = companyCriteria ? `\n【会社別採用基準（共通基準より優先）】\n${companyCriteria.slice(0, 800)}\n` : '';
  const fbSection = feedbacks.length > 0
    ? '\n【過去の訂正例】\n' + feedbacks.slice(0, 5).map(f =>
        `- 「${(f.profileSummary || '').slice(0, 60)}…」→ 正解:${f.correction}（AI誤判定:${f.aiVerdict}）`
      ).join('\n') + '\n'
    : '';
  const CHUNK = 80;

  const callChunk = async (chunk, offset) => {
    const candidateList = chunk.map((c, i) =>
      `候補者${offset + i + 1}: ${c.summary}`
    ).join('\n');

    const prompt = `あなたは転職エージェントの一次選定アシスタントです。
${companySection}
以下の【選定基準】に照らして、各候補者を判定してください。
カード情報は概要のみのため、読み取れない項目は「情報なし」として扱ってください。
${posSection}
【選定基準】
${criteriaLines}${fbSection}
【候補者一覧】
${candidateList}

以下のJSON形式のみで出力してください（説明不要）:
{"results":[{"i":${offset + 1},"o":"OK"},{"i":${offset + 2},"o":"NG"}]}`;

    const data = await claudeFetch(apiKey, {
      model: 'claude-haiku-4-5-20251001',
      max_tokens: 1200,
      messages: [{ role: 'user', content: prompt }]
    });
    const text = (data.content?.[0]?.text || '').trim();
    const clean = text.replace(/```json|```/g, '').trim();
    const jsonMatch = clean.match(/\{[\s\S]*\}/);
    try {
      const parsed = JSON.parse(jsonMatch ? jsonMatch[0] : clean);
      return (parsed.results || []).map(r => ({ overall: r.overall || r.o || '要確認' }));
    } catch {
      return chunk.map(() => ({ overall: '要確認' }));
    }
  };

  const allResults = [];
  for (let i = 0; i < cards.length; i += CHUNK) {
    if (i > 0) showAutoStatus(`🔍 判定中... (${i}/${cards.length}人完了)`);
    const chunk = cards.slice(i, i + CHUNK);
    const chunkResults = await callChunk(chunk, i);
    allResults.push(...chunkResults);
  }
  return allResults;
}

// -------------------------------------------------------
// 自動リスト追加モード
// -------------------------------------------------------
async function triggerAutoAdd() {
  // 外部からの重複起動を防ぐ（_batchIsRunning=true の再帰呼び出しは通過）
  if (!_batchIsRunning && _triggerAutoAddLock) {
    console.log('[Snow-we] triggerAutoAdd: 二重起動スキップ');
    return;
  }
  if (!_batchIsRunning) _triggerAutoAddLock = true;

  // _batchApiKey が未セットの場合のみ chrome.storage を読む（再帰呼び出し時はキャッシュを使う）
  if (!_batchApiKey) {
    let stored;
    try {
      stored = await chrome.storage.local.get(['apiKey', 'screeningCriteria']);
    } catch (e) {
      console.warn('[Snow-we] triggerAutoAdd: ストレージ読み込みエラー', e.message);
      showAutoStatus('⚠️ 拡張機能が再起動されました。ページをリロードして再度ボタンを押してください。', 10000);
      _triggerAutoAddLock = false;
      return;
    }
    const key = (stored.apiKey || '').replace(/[^\x21-\x7E]/g, '').trim();
    if (!key || key.length < 20) {
      showAutoStatus('⚙️設定タブでAPIキーを保存してください', 4000);
      await saveAutoAddProgress({ running: false });
      return;
    }
    _batchApiKey = key;
    _batchCriteria = stored.screeningCriteria || {};
  }
  const apiKey = _batchApiKey;
  const criteria = _batchCriteria;
  injectStyles();

  // AMBI: per_pageリダイレクトは検討リストページに誤遷移するため削除
  // 現在表示中の候補者のみを処理する

  showAutoStatus('📥 読み込み中...');

  // ページをまたいで処理するため、進捗をストレージで管理（バッジ消去前に確認）
  const progress = await loadAutoAddProgress();
  // _batchIsRunning: chrome.storage失敗でprogress={}になっても誤ってfreshStart扱いにしない
  const isFreshStart = _batchIsRunning ? false : !progress.running;

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
  const _platform = getPlatform();
  console.log('[Snow-we] triggerAutoAdd cards found:', cards.length, 'platform:', _platform, 'url:', location.href);
  if (cards.length === 0) {
    console.warn('[Snow-we] カードが見つかりません。platform=' + _platform + ' hostname=' + location.hostname);
    showAutoStatus('❌ 候補者が見つかりません。一覧ページで実行してください。', 4000);
    await saveAutoAddProgress({ running: false });
    return;
  }

  // カウンターの初期値：chrome.storage失敗時はsessionStorageのバックアップから復元
  let addedCount, totalProcessed, okCount, ngCount, pendingCount;
  if (isFreshStart) {
    addedCount = 0; totalProcessed = 0; okCount = 0; ngCount = 0; pendingCount = 0;
    try { sessionStorage.removeItem('snowWeBatchCounters'); } catch (_) {}
    _batchIsRunning = true; // バッチ開始をマーク
  } else if (progress.added != null) {
    addedCount = progress.added; totalProcessed = progress.processed || 0;
    okCount = progress.verdicts?.ok || 0; ngCount = progress.verdicts?.ng || 0; pendingCount = progress.verdicts?.pending || 0;
    // 前ページの結果バナーを表示
    if (totalProcessed > 0) showPreviousResultsBanner(progress);
  } else {
    // chrome.storage失敗 → sessionStorageのバックアップから復元
    try {
      const ss = JSON.parse(sessionStorage.getItem('snowWeBatchCounters') || '{}');
      addedCount = ss.added || 0; totalProcessed = ss.processed || 0;
      okCount = ss.ok || 0; ngCount = ss.ng || 0; pendingCount = ss.pending || 0;
    } catch (_) { addedCount = 0; totalProcessed = 0; okCount = 0; ngCount = 0; pendingCount = 0; }
  }

  const isRDS = getPlatform() === 'rds';
  // スカウト履歴：初回のみ取得してキャッシュ（CDKスクロール再帰時はchrome.storage不要）
  if (!_batchScoutHistory) {
    _batchScoutHistory = isRDS ? {} : await getScoutHistory();
  }
  const scoutHistory = _batchScoutHistory;

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
  const batchSizeBefore = batchProcessed.size; // 今バッチ開始時点の処理済み数（Bizreach無限ループ検出用）
  for (let i = 0; i < cards.length; i++) {
    const { el, text: cardText } = cards[i];
    showAutoStatus(`📥 ${i + 1}/${cards.length}人 プロフィール取得中...`);

    // Bizreach の仮想スクロール内では scrollIntoView が viewport と競合するためスキップ
    if (getPlatform() !== 'bizreach') {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      await sleep(400);
    }

    // AMBI: スカウト済みカード (userSet--already) はスキップ
    if (getPlatform() === 'ambi' && el.classList.contains('userSet--already')) {
      console.log('[Snow-we] AMBI: スカウト済みスキップ (userSet--already)');
      totalProcessed++;
      continue;
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
        await saveAutoAddProgress({ added: addedCount, processed: totalProcessed, running: true, ts: Date.now(), verdicts: { ok: okCount, ng: ngCount, pending: pendingCount } });
        continue;
      }
    }

    // 年収チェック：IT閾値を下回る場合は即NG確定
    if (checkIncomeNG(profileText)) {
      setBatchBadge(el, 'ng', '❌ 見送り', '年収基準未満', profileText.substring(0, 200), 'NG');
      ngCount++; totalProcessed++;
      await saveAutoAddProgress({ added: addedCount, processed: totalProcessed, running: true, ts: Date.now(), verdicts: { ok: okCount, ng: ngCount, pending: pendingCount } });
      continue;
    }

    // 短期在籍チェック：過去職歴に2年未満の在籍がある場合は即NG確定
    if (checkShortTenureNG(profileText)) {
      setBatchBadge(el, 'ng', '❌ 見送り(短期在籍)', '短期在籍あり', profileText.substring(0, 200), 'NG');
      ngCount++; totalProcessed++;
      await saveAutoAddProgress({ added: addedCount, processed: totalProcessed, running: true, ts: Date.now(), verdicts: { ok: okCount, ng: ngCount, pending: pendingCount } });
      continue;
    }

    // 転職意向チェック（doda Xのみ）
    const intentResult = checkJobChangeIntentNG(profileText);
    if (intentResult === null && getPlatform() === 'dodax') {
      console.log('[Snow-we] doda X 転職意向: 問題なし（or 情報なし）→ AI判定へ');
    }
    if (intentResult === 'ng') {
      setBatchBadge(el, 'ng', '❌ 見送り(転職意向なし)', '転職に興味がない', profileText.substring(0, 200), 'NG');
      ngCount++; totalProcessed++;
      await saveAutoAddProgress({ added: addedCount, processed: totalProcessed, running: true, ts: Date.now(), verdicts: { ok: okCount, ng: ngCount, pending: pendingCount } });
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
      await saveAutoAddProgress({ added: addedCount, processed: totalProcessed, running: true, ts: Date.now(), verdicts: { ok: okCount, ng: ngCount, pending: pendingCount } });
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
    if (overall === 'OK') okCount++;
    else if (overall === 'NG') ngCount++;
    else pendingCount++;

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
    await saveAutoAddProgress({ added: addedCount, processed: totalProcessed, running: true, ts: Date.now(), verdicts: { ok: okCount, ng: ngCount, pending: pendingCount } });
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

    // 今バッチで新規処理ゼロ（全員すでにbatchProcessed済み）→ CDK仮想スクロールが無限ループするため完了扱い
    const newlyProcessedThisBatch = batchProcessed.size - batchSizeBefore;
    if (scrolled && newlyProcessedThisBatch === 0) {
      console.log(`[Snow-we] Bizreach: 今バッチ新規処理ゼロ → 全${totalProcessed}人完了`);
      sessionStorage.removeItem(BATCH_SESSION_KEY);
      showAutoStatus(`🤖 完了！ ✅${addedCount}人を検討リストに追加 (全${totalProcessed}人中)`, 8000);
      await saveAutoAddProgress({ running: false });
      return;
    }

    if (scrolled) {
      await sleep(800); // Angular CDKのレンダリング完了を待つ
      showAutoStatus(`🤖 次の候補者を処理中... (累計✅${addedCount}人追加)`);
      await saveAutoAddProgress({ added: addedCount, processed: totalProcessed, running: true, ts: Date.now(), verdicts: { ok: okCount, ng: ngCount, pending: pendingCount } });
      await triggerAutoAdd();
      return;
    }

    // スクロールしても変化なし＝全候補者処理完了
    sessionStorage.removeItem(BATCH_SESSION_KEY);
    showAutoStatus(`🤖 完了！ ✅${addedCount}人を検討リストに追加 (全${totalProcessed}人中)`, 8000);
    await saveAutoAddProgress({ running: false });
    return;
  }

  // doda-x: 全カード処理後、右パネルが開いたままだとページネーションが隠れるためEscapeで閉じる
  if (getPlatform() === 'dodax') {
    const closeBtn = document.querySelector('[class*="close" i][class*="panel" i], [class*="panel" i] [class*="close" i], [aria-label*="閉じ"], [aria-label*="close" i]');
    if (closeBtn) { closeBtn.click(); await sleep(400); }
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', keyCode: 27, bubbles: true }));
    document.dispatchEvent(new KeyboardEvent('keyup',   { key: 'Escape', keyCode: 27, bubbles: true }));
    await sleep(1200);
    console.log('[Snow-we] doda X: 右パネルをEscapeで閉じてページネーション検索へ');
  }

  // 次のページがあれば自動で移動して処理を続ける
  const nextPage = findNextPageButton();

  // 夜間自動実行: ページ数上限チェック
  if (nextPage && _isAutoRunMode) {
    _autoRunPageCount++;
    if (_autoRunPageCount >= _autoRunMaxPages) {
      showAutoStatus(`🌙 自動実行: ${_autoRunMaxPages}ページ完了 ✅${addedCount}人追加`, 3000);
      await saveAutoAddProgress({ running: false });
      if (_isAutoRunMode !== 'list-inner') {
        chrome.runtime.sendMessage({ type: 'autoRunComplete', slotId: _autoRunSlotId }).catch(() => {});
      }
      _isAutoRunMode = false;
      return;
    }
  }

  if (nextPage) {
    showAutoStatus(`🤖 次ページへ移動中... (累計✅${addedCount}人追加)`);
    // running:true で保存 → 次ページのロード時に isFreshStart=false になる
    await saveAutoAddProgress({ added: addedCount, processed: totalProcessed, running: true, ts: Date.now(), verdicts: { ok: okCount, ng: ngCount, pending: pendingCount } });
    try {
      sessionStorage.setItem('snowWeAutoAdd', JSON.stringify({
        resume: true, added: addedCount, processed: totalProcessed,
        autoRun: _isAutoRunMode ? { maxPages: _autoRunMaxPages, pageCount: _autoRunPageCount } : null,
      }));
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
    if (_isAutoRunMode && _isAutoRunMode !== 'list-inner') { chrome.runtime.sendMessage({ type: 'autoRunComplete', slotId: _autoRunSlotId }).catch(() => {}); }
    _isAutoRunMode = false;
  } else {
    showAutoStatus(`🤖 完了！ ✅${addedCount}人を検討リストに追加 (全${totalProcessed}人中)`, 8000);
    await saveAutoAddProgress({ running: false });
    if (_isAutoRunMode && _isAutoRunMode !== 'list-inner') { chrome.runtime.sendMessage({ type: 'autoRunComplete', slotId: _autoRunSlotId }).catch(() => {}); }
    _isAutoRunMode = false;
  }
}

// ── 検索条件リストページの自動実行（doda-X等） ──────────────────────
// 「表示」ボタンを順番にクリックして各条件の候補者を処理する
async function autoRunListPage(request) {
  const maxPages = request.maxPages || 2;
  const urlIndex = request.urlIndex || 0;
  const totalUrls = request.totalUrls || 1;

  const findShowButtons = () => Array.from(document.querySelectorAll('button, a'))
    .filter(el => el.textContent.trim() === '表示');

  // ボタンが表示されるまで待つ
  let buttons = [];
  for (let w = 0; w < 20; w++) {
    await sleep(500);
    buttons = findShowButtons();
    if (buttons.length > 0) break;
  }
  if (buttons.length === 0) {
    console.warn('[Snow-we] リスト自動実行: 表示ボタンが見つかりません');
    _isAutoRunMode = false;
    chrome.runtime.sendMessage({ type: 'autoRunComplete', slotId: _autoRunSlotId }).catch(() => {});
    return;
  }

  const total = buttons.length;
  console.log(`[Snow-we] リスト自動実行: ${total}件の検索条件を処理`);

  for (let i = 0; i < total; i++) {
    const currentButtons = findShowButtons();
    if (i >= currentButtons.length) break;

    showAutoStatus(`🌙 自動実行 (${urlIndex+1}/${totalUrls}): 条件${i+1}/${total} 処理中...`);
    currentButtons[i].click();

    // 候補者カードが出るまで待つ
    let found = false;
    for (let w = 0; w < 20; w++) {
      await sleep(500);
      if (extractAllCandidateCards().length > 0) { found = true; break; }
    }

    if (found) {
      _batchApiKey = null; _batchCriteria = null; _batchIsRunning = false; _batchScoutHistory = null;
      _isAutoRunMode = 'list-inner';
      _autoRunPageCount = 0;
      _autoRunMaxPages = maxPages;
      await triggerAutoAdd();
      _isAutoRunMode = false;
    } else {
      console.warn(`[Snow-we] 条件${i+1}: 候補者なし、スキップ`);
    }

    // リストに戻る
    history.back();
    await sleep(2000);
    for (let w = 0; w < 10; w++) {
      await sleep(500);
      if (findShowButtons().length > 0) break;
    }
    await sleep(500);
  }

  showAutoStatus(`🌙 自動実行完了: ${total}条件処理済み (${urlIndex+1}/${totalUrls})`, 6000);
  _isAutoRunMode = false;
  chrome.runtime.sendMessage({ type: 'autoRunComplete', slotId: _autoRunSlotId }).catch(() => {});
}

async function autoRunBizreachListPage(request) {
  const maxPages = request.maxPages || 2;
  const urlIndex = request.urlIndex || 0;
  const totalUrls = request.totalUrls || 1;

  // 保存された検索条件タブを探す（新規検索・条件一覧・矢印を除く）
  const findConditionTabs = () => {
    // 方法1: role="tab" 属性（Angular Material 等）
    let tabs = Array.from(document.querySelectorAll('[role="tab"]'))
      .filter(el => {
        const t = (el.textContent || '').trim();
        return t && t !== '新規検索' && t !== '条件一覧' && t.length < 60;
      });
    if (tabs.length > 0) return tabs;

    // 方法2: クラス名に Tab を含む要素（ナビ矢印・close ボタン除く）
    tabs = Array.from(document.querySelectorAll('[class*="Tab"], [class*="tab"]'))
      .filter(el => {
        const t = (el.textContent || '').trim();
        const rect = el.getBoundingClientRect();
        return t && t !== '新規検索' && t !== '条件一覧' && t.length < 60
          && rect.height > 20 && rect.height < 70 && rect.width > 30
          && el.tagName !== 'BUTTON';
      });
    if (tabs.length > 0) return tabs;

    return [];
  };

  // タブが出るまで待つ
  let tabs = [];
  for (let w = 0; w < 20; w++) {
    await sleep(500);
    tabs = findConditionTabs();
    if (tabs.length > 0) break;
  }

  if (tabs.length === 0) {
    // タブが見つからなければ通常の候補者一覧として処理
    console.warn('[Snow-we] Bizreachタブ未検出 → 通常処理');
    _isAutoRunMode = true;
    await triggerAutoAdd();
    _isAutoRunMode = false;
    chrome.runtime.sendMessage({ type: 'autoRunComplete', slotId: _autoRunSlotId }).catch(() => {});
    return;
  }

  console.log(`[Snow-we] Bizreach自動実行: ${tabs.length}件の検索条件タブを処理`);

  for (let i = 0; i < tabs.length; i++) {
    const currentTabs = findConditionTabs();
    if (i >= currentTabs.length) break;

    const tab = currentTabs[i];
    const tabLabel = (tab.textContent || '').replace(/[×✕\xd7×]/g, '').trim().substring(0, 20);
    showAutoStatus(`🌙 自動実行 (${urlIndex+1}/${totalUrls}): 「${tabLabel}」${i+1}/${tabs.length}`);

    // ×(close)ボタン以外の部分をクリック
    const closeBtn = tab.querySelector('[aria-label*="削除"], [aria-label*="close"], [class*="close"], [class*="Close"], [class*="delete"]');
    if (closeBtn) {
      const tabRect = tab.getBoundingClientRect();
      const closeBtnRect = closeBtn.getBoundingClientRect();
      const clickX = tabRect.left + (tabRect.width - closeBtnRect.width) / 2;
      const clickY = tabRect.top + tabRect.height / 2;
      const el = document.elementFromPoint(clickX, clickY);
      if (el && el !== closeBtn && !closeBtn.contains(el)) {
        el.click();
      } else {
        tab.click();
      }
    } else {
      tab.click();
    }

    // 候補者カードが出るまで待つ
    await sleep(1500);
    let found = false;
    for (let w = 0; w < 20; w++) {
      await sleep(500);
      if (findCandidateCardsByPlatform().length > 0) { found = true; break; }
    }

    if (found) {
      _batchApiKey = null; _batchCriteria = null; _batchIsRunning = false; _batchScoutHistory = null;
      _isAutoRunMode = 'list-inner';
      _autoRunPageCount = 0;
      _autoRunMaxPages = maxPages;
      await triggerAutoAdd();
      _isAutoRunMode = false;
    } else {
      console.warn(`[Snow-we] 「${tabLabel}」: 候補者なし、スキップ`);
    }

    await sleep(1000);
  }

  showAutoStatus(`🌙 自動実行完了: ${tabs.length}条件処理済み (${urlIndex+1}/${totalUrls})`, 6000);
  _isAutoRunMode = false;
  chrome.runtime.sendMessage({ type: 'autoRunComplete', slotId: _autoRunSlotId }).catch(() => {});
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

  // Bizreach: カードクリック → 右パネル(ess-resume-detail)からプロフィール取得
  if (platform === 'bizreach') {
    const resumeId = getBizreachResumeNumericId(cardEl);

    // クリック前のパネルテキストを記録（別候補者のパネルと区別するため）
    const prevDetailEl = document.querySelector('ess-resume-detail');
    const prevText = (prevDetailEl?.innerText || '').trim();

    // スター/お気に入りボタン以外の要素をクリック対象とする
    const starPattern = /star|favorite|bookmark|wish|heart|toggle/i;
    const linkEl = Array.from(cardEl.querySelectorAll('a')).find(a => {
      const href = a.getAttribute('href') || '';
      return href.includes('/list/') || href.includes('/resumes/');
    });
    const clickTarget = linkEl ||
      Array.from(cardEl.querySelectorAll('div, span, p')).find(el => {
        const cls = el.getAttribute('class') || '';
        return !starPattern.test(cls) && (el.innerText || '').trim().length > 2 && (el.innerText || '').trim().length < 60;
      }) || cardEl;

    clickTarget.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, pointerId: 1 }));
    clickTarget.dispatchEvent(new PointerEvent('pointerup',   { bubbles: true, cancelable: true, pointerId: 1 }));
    clickTarget.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

    // 右パネル(ess-resume-detail)が更新されるのを待つ
    let detailEl = null;
    for (let i = 0; i < 10; i++) {
      await sleep(i === 0 ? 1800 : 600);
      const el = document.querySelector('ess-resume-detail');
      const txt = (el?.innerText || '').trim();
      if (el && txt.length > 500 && txt !== prevText) {
        // IDが取れる場合は念のため一致確認
        if (!resumeId || txt.includes(resumeId) || txt.includes('BU' + resumeId)) {
          detailEl = el;
          break;
        }
        // IDが含まれなくてもテキスト量が十分なら採用（IDの表示形式が異なるケース対応）
        if (txt.length > 1000) {
          detailEl = el;
          break;
        }
      }
    }

    if (detailEl) {
      const text = extractMainText(detailEl, 5000);
      console.log('[Snow-we] Bizreach右パネルからプロフィール取得:', text.length, '文字');
      return text;
    }

    // フォールバック：カードテキスト
    const text = fallbackText.substring(0, 900);
    console.log('[Snow-we] Bizreachカードテキスト取得(fallback):', text.length, '文字');
    return text;
  }

  // AMBI：カードにプロフィール全文が含まれているためカードテキストを直接使用
  if (platform === 'ambi') {
    const text = fallbackText.trim();
    console.log('[Snow-we] AMBI カードテキスト取得:', text.length, '文字');
    return text.substring(0, 3000);
  }

  // doda X：カードクリック → 右パネルで全文取得（転職意向を含む）
  if (platform === 'dodax') {
    // 星ボタンを除いたカード内の最初のテキスト要素をクリック（LI自体ではReactイベントが発火しない）
    const starCls = /star|c-star/i;
    const innerEl = Array.from(cardEl.querySelectorAll('div, section, article')).find(el => {
      const cls = el.getAttribute('class') || '';
      return !starCls.test(cls) && (el.innerText || '').trim().length > 10;
    });
    const clickTarget = innerEl || cardEl;
    console.log('[Snow-we] doda X クリック対象:', clickTarget.tagName, (clickTarget.getAttribute('class') || '').substring(0, 50));
    // PointerEvent → MouseEvent の順で発火（React 18 はポインタイベントも処理）
    const dispatchClick = (el) => {
      el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, pointerId: 1 }));
      el.dispatchEvent(new PointerEvent('pointerup',   { bubbles: true, cancelable: true, pointerId: 1 }));
      el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    };
    dispatchClick(clickTarget);
    // リトライ付きパネル検出（最大6回）
    let panel = null;
    for (let attempt = 0; attempt < 6; attempt++) {
      await sleep(attempt === 0 ? 1800 : 800);
      panel = findDodaxDetailPanel();
      if (panel && (panel.innerText || '').trim().length > 200) break;
      console.log('[Snow-we] doda X パネル待機中... attempt=' + attempt);
      if (attempt === 0) dispatchClick(clickTarget);   // 1回目待機後に再発火
      if (attempt === 2) dispatchClick(cardEl);        // 3回目はLI自体を試す
    }
    if (panel) {
      const text = (panel.innerText || '').trim();
      if (text.length > 200) {
        console.log('[Snow-we] doda X 右パネル取得成功:', text.length, '文字');
        return text.substring(0, 5000);
      }
    }
    console.log('[Snow-we] doda X 右パネル未取得 → カードテキストで代替');
    return fallbackText.substring(0, 1500);
  }

  // その他：プロフィールURLをフェッチして全文取得
  const profileUrl = findProfileUrl(cardEl);
  if (profileUrl) {
    const fetched = await fetchProfilePage(profileUrl);
    if (fetched && fetched.length > 300) return fetched;
  }

  return fallbackText.substring(0, 900);
}

// カード内のプロフィールページURLを探す
function findProfileUrl(cardEl) {
  const platform = getPlatform();
  const patterns = {
    rds:      [/\/scout\//, /\/candidate\//, /\/member\//, /\/detail\//, /hrtech/, /rikunabi/, /recruitdirect/],
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
    const keywords = ['職務経歴', '職歴', '業務内容', 'スキル', '学歴', '自己PR', '転職理由', '経験', '転職意向'];
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
  try { toggle.checked = true; } catch (_) {}
  try {
    const ng = window.ng;
    if (ng) {
      const comp = ng.getComponent?.(toggle) || ng.getComponent?.(starBtn);
      if (comp && typeof comp.checked === 'boolean') { comp.checked = true; ng.applyChanges?.(toggle); }
    }
  } catch (_) {}
  const icon = toggle.querySelector('b-ui-icon');
  if (icon) {
    const offIcon = toggle.getAttribute('officon') || 'star';
    const onIcon  = toggle.getAttribute('onicon')  || 'star-fill';
    icon.className = icon.className.replace(`bui-icon-${offIcon}`, `bui-icon-${onIcon}`);
  }
}

// API失敗時またはNG再適用時に星のDOM状態を強制的にOFFにする
function forceBizreachStarOff(starBtn) {
  const toggle = starBtn.querySelector('b-ui-icon-toggle') || starBtn;
  toggle.removeAttribute('checked');
  try { toggle.checked = false; } catch (_) {}
  try {
    const ng = window.ng;
    if (ng) {
      const comp = ng.getComponent?.(toggle) || ng.getComponent?.(starBtn);
      if (comp && typeof comp.checked === 'boolean') { comp.checked = false; ng.applyChanges?.(toggle); }
    }
  } catch (_) {}
  const icon = toggle.querySelector('b-ui-icon');
  if (icon) {
    const offIcon = toggle.getAttribute('officon') || 'star';
    const onIcon  = toggle.getAttribute('onicon')  || 'star-fill';
    icon.className = icon.className.replace(`bui-icon-${onIcon}`, `bui-icon-${offIcon}`);
  }
}

// Bizreach カード要素から resume の数値IDを取得する
function getBizreachResumeNumericId(cardEl) {
  // 子孫を先に探す（bui-drawer-trigger等に id="resume-xxx" が設定されているケースが多い）
  const child = cardEl.querySelector?.('[id^="resume-"]');
  if (child) {
    const mc = child.id.match(/^resume-(\d+)$/);
    if (mc) return mc[1];
  }
  // 自身・親要素を順に探す
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
      // DOM再利用でstar状態が古い場合があるため isBizreachStarred を迂回して直接API呼び出し
      const apiOk = await callBizreachFavoriteApi(resumeNumericId);
      if (apiOk) {
        console.log('[Snow-we] APIで星追加成功:', resumeNumericId);
        forceBizreachStarOn(starBtn);
        starredIds.add(resumeNumericId);
        try { sessionStorage.setItem('snowWeBizreachStarred', JSON.stringify([...starredIds])); } catch (_) {}
        return true;
      }
    }
    // IDが取得できないまたはAPIが失敗した場合のフォールバック
    if (isBizreachStarred(starBtn)) {
      console.log('[Snow-we] すでにスター済み（フォールバック確認）、スキップ');
      return false;
    }
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

  // AMBI：「この検討人材リストに追加」ボタンを明示処理
  if (platform === 'ambi') {
    // スカウト済みカードはスキップ
    if (cardEl.classList.contains('userSet--already')) {
      console.log('[Snow-we] AMBI: スカウト済みカードスキップ (userSet--already)');
      return false;
    }
    // .js_consider が確認済みの追加ボタンセレクター
    const btn = cardEl.querySelector('.js_consider') ||
                Array.from(cardEl.querySelectorAll('a,button')).find(el =>
                  (el.innerText || '').includes('この検討人材リストに追加'));
    if (!btn) {
      console.warn('[Snow-we] AMBI: 追加ボタン未発見');
      return false;
    }
    // 既に追加済みの場合はスキップ
    if (btn.disabled || btn.getAttribute('aria-disabled') === 'true' ||
        /disabled|added|済/.test(btn.className || '')) {
      console.log('[Snow-we] AMBI: 既に追加済みとみなしスキップ');
      return false;
    }
    console.log('[Snow-we] AMBI: 追加ボタンをクリック:', (btn.innerText || '').trim().substring(0, 30));
    btn.click();
    await sleep(900);
    // ドロップダウン・モーダルを処理（フォルダ選択 or 確定ボタン）
    await handleAmbiAddDialog();
    return true;
  }

  const labelMap = {
    rds:      '検討中リスト追加',
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

// AMBI検討リスト追加後のダイアログを処理する
async function handleAmbiAddDialog() {
  await sleep(500);
  // 表示中のダイアログ・ドロップダウンを探す
  const dialogs = Array.from(document.querySelectorAll(
    '[role="dialog"],[class*="modal"],[class*="dialog"],[class*="dropdown"],[class*="popup"],[class*="overlay"],[class*="layer"]'
  )).filter(el => {
    const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
  });

  for (const dialog of dialogs) {
    const text = (dialog.innerText || '').trim();
    if (!text) continue;
    // フォルダ選択ドロップダウン：最初の選択肢をクリック
    const folderItems = Array.from(dialog.querySelectorAll('li,option,[role="option"],[class*="item"],[class*="folder"],[class*="category"]'))
      .filter(el => {
        const t = (el.innerText || '').trim();
        return t.length > 0 && t.length < 50;
      });
    if (folderItems.length > 0) {
      console.log('[Snow-we] AMBI: フォルダ選択ドロップダウン検出 -', folderItems[0].innerText?.trim());
      folderItems[0].click();
      await sleep(400);
    }
    // 確定ボタンを探す
    const confirmTexts = ['追加', '確認', '確定', 'OK', 'はい', '保存', '完了', '登録'];
    const btns = Array.from(dialog.querySelectorAll('button,a,[role="button"]'));
    for (const t of confirmTexts) {
      const found = btns.find(b => (b.innerText || '').trim().includes(t));
      if (found) {
        console.log('[Snow-we] AMBI: 確定ボタンをクリック:', t);
        found.click();
        await sleep(500);
        return;
      }
    }
  }
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

// 転職意向チェック（doda Xのみ）：'ng' | null
function checkJobChangeIntentNG(profileText) {
  if (!profileText || getPlatform() !== 'dodax') return null;

  // 転職意向フィールドの行を抽出してログ出力（確認用）
  const _intentLines = profileText.split('\n');
  const _intentIdx = _intentLines.findIndex(l => l.includes('転職意向') || l.includes('転職への'));
  if (_intentIdx >= 0) {
    // 前後2行のコンテキストを出力して構造を把握
    const _ctx = _intentLines.slice(Math.max(0, _intentIdx - 1), _intentIdx + 4)
      .map((l, i) => `[${_intentIdx - 1 + i}]"${l.trim()}"`)
      .join(' / ');
    console.log('[Snow-we] doda X 転職意向コンテキスト:', _ctx);
  } else {
    console.log('[Snow-we] doda X 転職意向: フィールド未検出（プロフィールに記載なし）');
  }

  // NG 判定（転職意向なし系の表現）
  const ngPhrases = [
    '転職に興味がない',
    '転職への興味はない',
    '転職を考えていない',
    'とくに転職は考えていない',
    '特に転職は考えていない',
    '転職の意向はない',
    '転職意向なし',
  ];
  const found = ngPhrases.find(p => profileText.includes(p));
  if (found) {
    console.log('[Snow-we] doda X 転職意向NG:', found);
    return 'ng';
  }
  return null; // 情報なし or 転職意欲あり（検討中・決意済み・興味あり）→ 通常判定へ
}

// 年齢と年収からNG判定を返す（確実にNGの場合のみ 'NG'、それ以外は null）
function checkIncomeNG(profileText) {
  // Bizreach は年収情報が 0 や非公開で取得できないことが多いため Claude に委ねる
  if (getPlatform() === 'bizreach') return null;

  const ageMatch = profileText.match(/(\d{2})歳/);
  if (!ageMatch) return null;
  const age = parseInt(ageMatch[1], 10);

  // 年収範囲（例: 700〜900万円）の場合は上限値を使用してAIと判定基準を一致させる
  // AI prompt（buildStandardCriteria）も「上限値が基準以上であればNGにしない」と指定している
  const numPat = '(?:\\d{1,2},\\d{3}|\\d{3,4})';
  const parseNum = s => parseInt(s.replace(/,/g, ''), 10);
  const labelRangeRe = new RegExp(`(?:現)?年収[^\\d]*${numPat}\\s*[〜~～]\\s*(${numPat})万`);
  const genericRangeRe = new RegExp(`${numPat}\\s*[〜~～]\\s*(${numPat})万`);
  const labelRangeM = profileText.match(labelRangeRe);
  const genericRangeM = labelRangeM ? null : profileText.match(genericRangeRe);
  const incomeUpperFromRange = labelRangeM ? parseNum(labelRangeM[1])
                             : genericRangeM ? parseNum(genericRangeM[1]) : null;

  // 年収取得：範囲の上限値を優先（確実NGは上限でも閾値未満の場合のみ）
  const income = incomeUpperFromRange !== null && incomeUpperFromRange > 0
    ? incomeUpperFromRange
    : extractIncomeFromText(profileText);
  if (income === null || income === 0) return null; // 年収不明・ゼロはClaudeに任せる

  // ITエンジニア系キーワードで職種を判定
  const isIT = /エンジニア|ソフトウェア開発|インフラ|クラウド|システム開発|SE[^\w]|データエンジニア|バックエンド|フロントエンド|DevOps/.test(profileText);

  let threshold;
  if (isIT) {
    if (age < 30)      threshold = 350;
    else if (age <= 35) threshold = 500;
    else if (age <= 39) threshold = 700;
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

  // 現職の在籍期間：開始年月〜現在 から今日までのヶ月数を計算
  function parseCurrentJobTenureMonths(str) {
    const m = str.match(/(\d{4})年(\d{1,2})月\s*[〜~～]\s*(現在|在籍中)/);
    if (!m) return null;
    const now = new Date();
    const months = (now.getFullYear() - parseInt(m[1], 10)) * 12 + (now.getMonth() + 1 - parseInt(m[2], 10));
    return months > 0 ? months : 0;
  }

  const dodaxTenureRe = /^(?:各\d+(?:\.\d+)?年|\d+(?:\.\d+)?年|\d+[ヶか]月)/;
  const lines = profileText.split('\n').map(l => l.trim()).filter(Boolean);

  // 同一会社の全出現箇所から在籍期間を合算（複数行記入対応）
  // 現職（現在/在籍中）が含まれる場合は開始年月から今日までの実在籍月数を加算
  function getTotalTenureForCompanyLine(companyLineStr) {
    if (!companyLineStr) return 0;
    const key = companyLineStr.replace(/\s+/g, '').substring(0, Math.min(8, companyLineStr.replace(/\s+/g, '').length));
    if (key.length < 3) return 0;
    let total = 0;
    for (let k = 0; k < lines.length; k++) {
      const l = lines[k];
      if (!l.replace(/\s+/g, '').includes(key.substring(0, Math.min(6, key.length)))) continue;
      if (shukkoRe.test(l)) continue;
      if (l.includes('現在') || l.includes('在籍中')) {
        const cm = parseCurrentJobTenureMonths(l) ?? parseTenureMonths(l);
        if (cm !== null && cm > 0) total += cm;
        continue;
      }
      const inlineT = parseTenureMonths(l);
      if (inlineT !== null && inlineT > 0) total += inlineT;
      for (let j = k + 1; j < Math.min(k + 8, lines.length); j++) {
        if (lines[j].includes('現在') || lines[j].includes('在籍中')) {
          const cm = parseCurrentJobTenureMonths(lines[j]) ?? parseTenureMonths(lines[j]);
          if (cm !== null && cm > 0) total += cm;
          break;
        }
        if (companyRe.test(lines[j]) && !shukkoRe.test(lines[j])) break;
        const t = parseTenureMonths(lines[j]);
        if (t !== null && t > 0) total += t;
      }
    }
    return total;
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.includes('現在') || line.includes('在籍中')) {
      // 現職の在籍期間チェック：同社の過去役職期間も合算して判断
      if (!shukkoRe.test(line)) {
        const curM = parseCurrentJobTenureMonths(line) ?? parseTenureMonths(line);
        if (curM !== null && curM < 24) {
          const prev = i > 0 ? lines[i - 1] : '';
          const next = i < lines.length - 1 ? lines[i + 1] : '';
          let companyLineForCheck = null;
          if (companyRe.test(line) && !shukkoRe.test(line)) companyLineForCheck = line;
          else if (companyRe.test(prev) && !shukkoRe.test(prev)) companyLineForCheck = prev;
          else if (companyRe.test(next) && !shukkoRe.test(next)) companyLineForCheck = next;
          if (companyLineForCheck) {
            const fullTotal = getTotalTenureForCompanyLine(companyLineForCheck);
            if (fullTotal < 24) {
              console.log(`[Snow-we] 短期在籍NG(現職): ${curM}ヶ月(同社合計${fullTotal}ヶ月) / "${line.substring(0, 60)}"`);
              return 'NG';
            }
          }
        }
      }
      continue;
    }
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
      if (!companyLine) continue;
      if (shukkoRe.test(companyLine)) continue; // 出向先会社はスキップ
      if (isCurrent) {
        // 現職のdoda-x形式：同社の過去役職も合算して判断
        let curTotal = total;
        for (let j = i + 1; j < lines.length; j++) {
          if (!dodaxTenureRe.test(lines[j]) || lines[j].includes('現在') || lines[j].includes('在籍中')) break;
          const t = parseTenureMonths(lines[j]);
          if (t) curTotal += t;
        }
        if (curTotal < 24) {
          const fullTotal = getTotalTenureForCompanyLine(companyLine);
          if (fullTotal < 24) {
            console.log(`[Snow-we] 短期在籍NG(現職dodax): ${curTotal}ヶ月(同社合計${fullTotal}ヶ月) / 会社: "${companyLine.substring(0, 50)}"`);
            return 'NG';
          }
        }
        continue;
      }

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
    if (res?.ok && (res.requirements || res.companyCriteria)) {
      console.log(`[Snow-we] GASデータ取得成功: "${position}" / 要件${(res.requirements||'').length}文字${res.companyCriteria ? ` / 会社別基準${res.companyCriteria.length}文字` : ''}`);
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
  let _posStored = {};
  try { _posStored = await chrome.storage.local.get(['currentPosition']); } catch (_) {}
  const { currentPosition } = _posStored;
  const { requirements: posReq, companyCriteria } = await fetchPositionRequirements(currentPosition || '');
  const posSection     = posReq        ? `\n【応募ポジションの職務内容】\n${posReq}\n`           : '';
  const companySection = companyCriteria ? `\n【会社別採用基準（共通基準より優先）】\n${companyCriteria}\n` : '';

  // 過去の訂正フィードバックをfew-shot examplesとして組み込む
  const feedbacks = await loadRecentFeedbacks(10);
  let fewShotSection = '';
  if (feedbacks.length > 0) {
    const examples = feedbacks
      .map(f => {
        const meta = [f.platform, f.recruiter].filter(Boolean).join('/');
        return `- ${meta ? `[${meta}] ` : ''}「${(f.profileSummary || '').substring(0, 100)}…」\n  AI誤判定:${f.aiVerdict} → 人間正解:${f.correction}`;
      })
      .join('\n');
    fewShotSection = `\n【過去の訂正例（最優先参照）】\n同様パターンの候補者は同じ判断をすること。\n${examples}\n`;
  }

  const prompt = `転職エージェントの一次選定アシスタントです。
${companySection}
【選定基準】
${criteriaLines}${posSection}${fewShotSection}
【重要：職種分類の注意】候補者の職種分類（ITエンジニア系/文系職）は、候補者自身の現在・直近の職種で判断すること。【応募ポジションの職務内容】が文系・ビジネス職であっても、候補者の実際の職種がITエンジニア・技術職であれば「ITエンジニア系」として分類すること。ポジション内容は候補者の職種分類に影響しない。

【候補者情報】
${profileText}

JSON1行のみで出力（rを先に書いてからoを確定し、最後にcで確信度0-100を付けること。rは判定理由を50字以内で）:
{"r":"理由","o":"OK","c":90} または {"r":"理由","o":"NG","c":85} または {"r":"理由","o":"要確認","c":45}
※cは判定の確信度（0〜100の整数）。基準に明確に合致/不合致なら80以上、判断が難しければ60未満。`;

  const data = await claudeFetch(apiKey, {
    model: 'claude-haiku-4-5-20251001',
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
  try {
    const stored = await chrome.storage.local.get(['snowWeFeedbacks']);
    const feedbacks = stored.snowWeFeedbacks || [];
    feedbacks.unshift({ profileSummary, aiVerdict, correction, platform, ts });
    if (feedbacks.length > 50) feedbacks.length = 50;
    await chrome.storage.local.set({ snowWeFeedbacks: feedbacks });
    console.log(`[Snow-we] フィードバック保存: AI=${aiVerdict} → 訂正=${correction} (累計${feedbacks.length}件)`);
  } catch (_) {}

  // GASスプレッドシートにも送信（設定済みかつフィードバック保存が有効な場合）
  try {
    const { gasSettings } = await chrome.storage.local.get(['gasSettings']);
    const gasUrl = gasSettings?.url || gasSettings?.dbUrl;
    const secret = gasSettings?.secret || 'snowwe2024';
    if (gasUrl && gasSettings?.feedbackEnabled !== false) {
      chrome.runtime.sendMessage({
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

  // Supabaseにも保存
  ;(async () => {
    let recruiter = '';
    try {
      const s = await chrome.storage.local.get(['gasSettings']);
      recruiter = s.gasSettings?.recruiter || '';
    } catch (_) {}
    await supabaseInsert('ai_feedback', {
      platform,
      original_verdict: aiVerdict,
      corrected_verdict: correction,
      recruiter_name: recruiter,
    });
  })();
}

async function loadRecentFeedbacks(limit = 10) {
  // ローカルフィードバック
  let local = [];
  try {
    const stored = await chrome.storage.local.get(['snowWeFeedbacks']);
    local = stored.snowWeFeedbacks || [];
  } catch (_) {}

  // GASからチーム全体のフィードバックも取得（30件）
  let team = [];
  try {
    const res = await chrome.runtime.sendMessage({ type: 'getTeamFeedbacks' });
    team = res?.feedbacks || [];
  } catch (_) {}

  // ローカル優先でマージ、重複排除（profileSummary+correction で判定）
  const seen = new Set(local.map(f => (f.profileSummary || '').slice(0, 40) + f.correction));
  const merged = [...local];
  for (const f of team) {
    const key = (f.profileSummary || '').slice(0, 40) + f.correction;
    if (!seen.has(key)) { seen.add(key); merged.push(f); }
  }
  return merged.slice(0, limit);
}

// 訂正ポップアップを表示する
function showFeedbackPopup(badgeEl) {
  // 既存のポップアップを消す
  document.querySelectorAll('.snow-we-fb-popup').forEach(p => p.remove());

  const aiVerdict      = badgeEl.dataset.verdict || '';
  const profileSummary = badgeEl.dataset.profile || '';
  const reason         = badgeEl.dataset.reason  || '';
  const platform       = getPlatform();

  const popup = document.createElement('div');
  popup.className = 'snow-we-fb-popup';
  const reasonHtml = reason ? `<div class="snow-we-fb-reason">💭 ${escapeHtml(reason)}</div>` : '';
  popup.innerHTML = `${reasonHtml}<span>判定を訂正</span><div class="snow-we-fb-row"></div>`;
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

  // ポップアップ内クリックは閉じない
  popup.addEventListener('click', e => e.stopPropagation());

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
    badge.dataset.reason  = tooltip || '';
    badge._fbHandler = (e) => { e.stopPropagation(); showFeedbackPopup(badge); };
    badge.addEventListener('click', badge._fbHandler);
    badge.title = (tooltip ? tooltip + '\n' : '') + '（クリックで判定を訂正）';
  }
  // Bizreach: DOM再利用検出のためresumeIdをバッジに記録
  if (getPlatform() === 'bizreach') {
    const rid = getBizreachResumeNumericId(el);
    if (rid) badge.dataset.resumeId = rid;
  }
  el.appendChild(badge);

  // Bizreach仮想スクロール: checkingを除く確定判定をレジストリに保存（スクロール後の再表示に使用）
  if (getPlatform() === 'bizreach' && cls !== 'checking') {
    const resumeId = getBizreachResumeNumericId(el);
    if (resumeId) {
      _bizreachBadgeRegistry.set(resumeId, {
        cls, text, tooltip: tooltip || '', profileSummary: profileSummary || '', aiVerdict: aiVerdict || ''
      });
    }
  }
}

// Bizreach仮想スクロール: DOM上の全カードにレジストリのバッジを再適用（デバウンス付き）
function reapplyBizreachBadges() {
  if (_bizreachBadgeRegistry.size === 0) return;
  clearTimeout(_reapplyBizreachTimer);
  _reapplyBizreachTimer = setTimeout(() => {
    let starredIds;
    try { starredIds = new Set(JSON.parse(sessionStorage.getItem('snowWeBizreachStarred') || '[]')); }
    catch (_) { starredIds = new Set(); }
    document.querySelectorAll('ess-resume-list-item').forEach(el => {
      const resumeId = getBizreachResumeNumericId(el);
      if (!resumeId) return;

      // DOM再利用検出: 既存バッジのresumeIdが現在のカードと一致しない場合は削除
      const existingBadge = el.querySelector('.snow-we-badge.batch');
      if (existingBadge) {
        if (existingBadge.dataset.resumeId === resumeId) {
          // 正しいバッジが既にある → 星のみ再確認
          const state = _bizreachBadgeRegistry.get(resumeId);
          if (state) {
            const isNg = state.cls === 'ng' || (state.cls === 'corrected' && state.aiVerdict === 'NG');
            const isOk = state.cls === 'ok' || (state.cls === 'corrected' && state.aiVerdict === 'OK');
            const starBtn = findBizreachStarButton(el);
            if (starBtn) {
              if (isNg && isBizreachStarred(starBtn)) forceBizreachStarOff(starBtn);
              if (isOk && starredIds.has(resumeId) && !isBizreachStarred(starBtn)) forceBizreachStarOn(starBtn);
            }
          }
          return;
        }
        existingBadge.remove(); // 古いバッジ（DOM再利用）を削除
      }

      const state = _bizreachBadgeRegistry.get(resumeId);
      if (!state) return;
      setBatchBadge(el, state.cls, state.text, state.tooltip, state.profileSummary, state.aiVerdict);

      const isNg = state.cls === 'ng' || (state.cls === 'corrected' && state.aiVerdict === 'NG');
      const isOk = state.cls === 'ok' || (state.cls === 'corrected' && state.aiVerdict === 'OK');
      const starBtn = findBizreachStarButton(el);
      if (starBtn) {
        if (isNg && isBizreachStarred(starBtn)) forceBizreachStarOff(starBtn);
        if (isOk && starredIds.has(resumeId) && !isBizreachStarred(starBtn)) forceBizreachStarOn(starBtn);
      }
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
      const cls = (p.getAttribute('class') || '').toLowerCase();
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
      console.log('[Snow-we] テキスト次ページボタン発見:', t, el.tagName, (el.getAttribute('class') || '').substring(0, 40));
      return el;
    }
  }

  // 2. 数字ページネーション: アクティブページ番号+1を探す（doda-x等SPA）
  // 結果件数表示（0件・531件・30件表示等）を除外し、ページボタンのみを対象にする
  const isResultCountEl = (el) => {
    for (let p = el.parentElement, i = 0; p && i < 5; p = p.parentElement, i++) {
      const cls = (p.getAttribute('class') || '').toLowerCase();
      // 件数表示コンテナのクラス名パターン（'result'は検索結果リストと区別できないため除外）
      if (cls.includes('cnt') || cls.includes('count') ||
          cls.includes('total') || cls.includes('件数') || cls.includes('hits')) return true;
    }
    return false;
  };

  // AMBI: per_page=1000 で全件を1ページに表示するためページネーション不要
  if (getPlatform() === 'ambi') {
    console.log('[Snow-we] AMBI: per_page=1000 使用中 → ページネーション不要');
    return null;
  }

  // doda-x 専用: prts-paging 構造から次ページを取得
  if (getPlatform() === 'dodax') {
    const paging = document.querySelector('[class*="prts-paging"]');
    if (paging) {
      const items = Array.from(paging.querySelectorAll('li, a'));
      const activeItem = items.find(el => el.classList.contains('active'));
      const currentNum = activeItem ? parseInt((activeItem.innerText || '').trim(), 10) : 1;
      const nextItem = items.find(el => {
        if (el.classList.contains('active') || el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
        const n = parseInt((el.innerText || '').trim(), 10);
        return !isNaN(n) && n === currentNum + 1;
      });
      if (nextItem) {
        console.log(`[Snow-we] dodax prts-paging 次ページ: ${currentNum} → ${currentNum + 1}`);
        return nextItem;
      }
      console.log(`[Snow-we] dodax prts-paging: 最終ページ (currentPage=${currentNum})`);
      return null;
    }
  }

  const allNumericEls = Array.from(document.querySelectorAll('a,button,[role="button"],span,div,li'))
    .filter(el => {
      const t = (el.innerText || '').trim();
      const n = parseInt(t, 10);
      if (!/^\d{1,3}$/.test(t) || el.children.length > 1) return false;
      if (n < 1) return false; // 0 は件数表示の可能性が高いので除外
      if (isInModal(el)) return false;
      if (isResultCountEl(el)) return false;
      return true;
    });

  console.log(`[Snow-we] 数字ページ候補要素数: ${allNumericEls.length}`, allNumericEls.slice(0, 8).map(e => `${e.tagName}:${(e.innerText||'').trim()}:${(e.getAttribute('class')||'').substring(0,30)}`));

  if (allNumericEls.length > 0) {
    let currentPage = null;

    const activeEl = allNumericEls.find(el => {
      if (el.classList.contains('active') || el.classList.contains('current') ||
          el.classList.contains('is-active') || el.classList.contains('is-current') ||
          el.classList.contains('selected') || el.classList.contains('is-selected')) return true;
      if (el.getAttribute('aria-current') === 'page' || el.getAttribute('aria-selected') === 'true') return true;
      if (el.getAttribute('aria-disabled') === 'true' || el.disabled) return true;
      if (parseInt(getComputedStyle(el).fontWeight) >= 700) return true;
      const parent = el.parentElement;
      if (parent && (parent.classList.contains('active') || parent.classList.contains('current') ||
          parent.classList.contains('is-active') || parent.classList.contains('is-current'))) return true;
      return false;
    });

    if (activeEl) {
      currentPage = parseInt((activeEl.innerText || '').trim(), 10);
      console.log(`[Snow-we] アクティブページ検出: ${currentPage} class="${activeEl.getAttribute('class')||''}" parent="${(activeEl.parentElement?.getAttribute('class')||'').substring(0,40)}"`);
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
  if (!data.running) {
    // バッチ終了：モジュールキャッシュとsessionStorageバックアップをリセット
    _batchIsRunning = false;
    _triggerAutoAddLock = false;
    _batchApiKey = null;
    _batchCriteria = null;
    _batchScoutHistory = null;
    try { sessionStorage.removeItem('snowWeBatchCounters'); } catch (_) {}
  } else if (data.added != null) {
    // バッチ進行中：chrome.storage失敗時の復元用にsessionStorageへバックアップ
    try { sessionStorage.setItem('snowWeBatchCounters', JSON.stringify({ added: data.added, processed: data.processed || 0, ok: data.verdicts?.ok || 0, ng: data.verdicts?.ng || 0, pending: data.verdicts?.pending || 0 })); } catch (_) {}
  }
  try {
    await chrome.storage.local.set({ autoAddProgress: data });
  } catch (e) {
    // Extension context invalidated（拡張機能再読み込み時）は無視
    if (!e.message?.includes('Extension context invalidated')) console.warn('[Snow-we] saveAutoAddProgress error:', e.message);
  }
}

// 自動追加の進捗をストレージから読み込む
async function loadAutoAddProgress() {
  try {
    const r = await chrome.storage.local.get(['autoAddProgress']);
    return r.autoAddProgress || {};
  } catch (e) {
    return {};
  }
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function escapeHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

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

    lines.push(`\n▼絶対NG（Bizreach専用追加条件）`);
    lines.push(`- 現職・過去職歴を問わず、アクセンチュア（Accenture）に在籍したことがある場合は即NG`);
    lines.push(`- 現職・過去職歴を問わず、ベイカレント（BayCurrent）に在籍したことがある場合は即NG（年齢・職種・現職問わず例外なし）`);
    lines.push(`- 現職・過去職歴を問わず、野村総合研究所（NRI）に在籍したことがある場合は即NG`);
    lines.push(`- 現職・過去職歴を問わず、BIG4（デロイト トーマツ・PwC・EY・KPMG、およびそれらのコンサルティング・監査法人・グループ会社）に在籍したことがある場合は即NG`);
    lines.push(`- 投資銀行（ゴールドマン・サックス・モルガン・スタンレー・JPモルガン・UBS・クレディ・スイス・野村証券IB部門・大和証券CM部門等）でのIBD・M&A・引受業務等が主なキャリアの場合は即NG`);
    lines.push(`- 金融・証券におけるディーラー（トレーダー・為替ディーラー・債券ディーラー・株式ディーラー・デリバティブトレーダー等）が主な職種・キャリアの場合は即NG`);
    lines.push(`- 特許・知的財産（特許出願・知財管理・ライセンシング・特許調査・特許翻訳等）が主な職種・キャリアの場合は即NG`);
    lines.push(`- 現職の社格（最重要）：以下の【現職OK基準】のいずれかに明確に当てはまる会社に在籍中の場合のみOK。会社名を見て「知らない」「小さそう」と感じたら即NG。判断に迷う場合は必ずNG。ただし④の「業界内大手」については、会社規模・知名度から明らかに大手と判断できる場合はOKとしてよい（過度に厳格にしすぎず、大手なのに落とさないよう注意）。\n  ※「現職」のみで判断すること。過去の在籍企業の社格が低くても、現職がOK基準を満たせば社格でNGにしない。\n  【現職OK基準 ①〜④のいずれか1つに該当すればOK】\n  ① 東証プライム上場企業（旧東証一部相当）。東証スタンダード・グロース上場のみは一般知名度次第でNG判断。株式会社シフト・レバレジーズ株式会社は東証プライムとしてOK。\n  ② 外資系企業またはその日本法人（本社が海外の多国籍企業・グループ会社含む。アクセンチュア・BIG4等は別途絶対NGルール参照）\n  ③ 著名大手・メガベンチャー（以下リスト内の企業のみ。リスト外の未上場ベンチャーは全てNG）：リクルート・パーソル・レバレジーズ（レバテック）・サイバーエージェント・DeNA・MIXI・GMO・メルカリ・SmartHR・freee・マネーフォワード・LayerX・Sansan・Visional・エン・ジャパン・M3等の誰もが知る大手名門企業\n  ④ 業界内で明確に知名度がある大手（大手総合商社・三菱・三井・住友・丸紅・伊藤忠等の大手商社／三菱UFJ・三井住友・みずほ等のメガバンク／野村・大和・SMBC日興等の大手証券／日本生命・第一生命・東京海上・損保ジャパン等の大手保険／トヨタ・ソニー・パナソニック・日立・富士通・NEC・東芝・本田・日産等の大手製造業／NTTグループ（NTT・NTT西日本・NTT東日本・NTTデータ・NTTコミュニケーションズ・NTTドコモ・NTTソフトウェア・NTTロジスコ等）・KDDI・ソフトバンク・楽天モバイル等の通信／JRグループ（JR東日本・JR西日本・JR東海・JR九州・JR北海道・JR四国・JR貨物等）・私鉄大手（東急・小田急・京王・西武・東武・阪急・近鉄・京阪等）等の交通／東京電力・関西電力・中部電力・東北電力・九州電力・北海道電力・中国電力・四国電力・北陸電力・沖縄電力等の地域電力各社／東京ガス・大阪ガス・東邦ガス・西部ガス等の都市ガス会社／ENEOS・出光興産・コスモエネルギー等の石油元売り／その他誰もが名前を知っている上場大手企業）\n  【即NGの例】「〇〇コンサルティング」「〇〇ソリューションズ」等の無名IT・コンサル、非上場で知名度のない中小・スタートアップ（③リスト外は全てNG）`);
    lines.push(`- 現職の会社の従業員数が500人以下の場合は即NG（プロフィールに記載がある場合のみ適用）`);
    lines.push(`- 現職の会社の設立・創業から10年未満の新興企業の場合は即NG（プロフィールに記載がある場合のみ適用）`);

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
    lines.push(`- 社格：東証プライム上場企業・外資系・著名大手・メガベンチャーでの勤務経験が必要。知名度のない中小・無名企業のみのキャリアはNG。判断に迷う会社はNG`);
    lines.push(`- 学歴：以下のいずれかに該当すること（いずれにも該当しない場合はNG）`);
    lines.push(`  ① 早慶上智（早稲田・慶應・上智）`);
    lines.push(`  ② MARCH・東京理科大（明治・青山学院・立教・中央・法政・東京理科大）`);
    lines.push(`  ③ 国立大学（旧帝大・東工大・一橋・筑波・横浜国立・小樽商科・北海道・東北・名古屋・大阪・九州・神戸・広島・岡山・千葉・埼玉・金沢・信州・静岡・熊本・長崎・鹿児島・琉球等、国が設置する全ての大学）`);
    lines.push(`  ④ 関関同立（関西大・関西学院大・同志社大・立命館大）かつ大手企業・外資系・有名上場企業に現在在籍中`);
    lines.push(`  ⑤ 海外大学卒（どの国・地域でも可）`);
    lines.push(`  ⑥ 公立大学（横浜市立大学・大阪市立大学・大阪公立大学・名古屋市立大学・京都府立大学・東京都立大学（首都大学東京）・兵庫県立大学等、都道府県・市区町村が設置する大学）`);
    lines.push(`  ※学歴が不明・記載なしの場合は学歴でNGにしない。社格・経験社数で判断すること`);

    lines.push(`\n▼Bizreach判定方針（迷う場合は必ずNG）`);
    lines.push(`以下の順番で判定すること：`);
    lines.push(`1. 絶対NG条件に該当 → 即NG`);
    lines.push(`2. 経験社数が年齢別上限を超える → NG`);
    lines.push(`3. 社格NG（現職OK基準①〜④のいずれにも当てはまらない）→ NG　※「ITエンジニア・デジタル系」はこのステップをスキップ`);
    lines.push(`4. 「それ以外の全職種」で学歴NG（①〜⑥のいずれにも非該当、かつ学歴が明記されている場合）→ NG`);
    lines.push(`5. 上記1〜4のいずれにも該当しない → OK`);
    lines.push(`※「要確認」は絶対に使用しないこと。必ずOKかNGを返すこと`);
    lines.push(`※「ITエンジニア・デジタル系」は社格チェック（ステップ3）をスキップ。学歴チェック（ステップ4）もスキップ。それ以外の技術職（製造・土木・研究等）はスキップしない`);
  } else {
    lines.push(`\n【職種判定】候補者の「直近・現在の職種」で以下のどちらかに分類し、対応する基準を適用してください。過去の経歴や学歴は分類に影響しません。`);
    lines.push(`- 「ITエンジニア系（IT・理系・技術職）」: 現在の職種がソフトウェアエンジニア・SE・インフラ・クラウド・データエンジニア・データサイエンティスト・データアナリスト・DXコンサル・ITコンサル・PMO・研究職（バイオ・化学・材料等）・建築設計・土木・機械設計・電気設計・製造技術・生産技術・品質管理等の技術職`);
    lines.push(`- 「文系職」: 現在の職種がコンサル（IT以外）・営業・マーケ・経営企画・事業企画・財務・人事・金融・その他ビジネス職。理系出身・研究職経験があっても現職が経営企画等のビジネス職であれば文系職として分類する`);

    const ai2 = criteria.ageIncome || {};
    const inc20s    = ai2.age20s    || 500;
    const inc30to35 = ai2.age30to35 || 700;
    const inc36to39 = ai2.age36to39 || 800;
    const inc40to42 = ai2.age40to42 || 1000;
    const inc43to45 = ai2.age43to45 || 1200;
    lines.push(`\n【文系職の年収基準】`);
    lines.push(`- 20代: ${inc20s}万円未満 → NG`);
    lines.push(`- 30〜35歳: ${inc30to35}万円未満 → NG`);
    lines.push(`- 36〜39歳: ${inc36to39}万円未満 → NG`);
    lines.push(`- 40〜42歳: ${inc40to42}万円未満 → NG`);
    lines.push(`- 43〜45歳: ${inc43to45}万円未満 → NG`);
    lines.push(`- 46歳以上: ${inc43to45}万以上かつ財務・経理・FP&A職歴あり → 要確認、それ以外 → NG`);
    lines.push(`※年収が明記されており基準を下回る場合は必ずNG。年収が不明・記載なしの場合は「要確認」`);
    lines.push(`※年収が幅（例：750〜1000万円）で記載されている場合は上限値（1000万円）で判断すること。上限値が基準以上であればNGにしない。`);

    lines.push(`\n【ITエンジニア系の年収基準】`);
    lines.push(`- 20代: 350万円未満 → NG`);
    lines.push(`- 30〜35歳: 500万円未満 → NG`);
    lines.push(`- 36〜39歳: 700万円未満 → NG`);
    lines.push(`- 40〜45歳: 800万円未満 → NG`);
    lines.push(`※年収が明記されており基準を下回る場合は必ずNG。年収が不明・記載なしの場合は「要確認」`);
    lines.push(`※年収が幅（例：750〜1000万円）で記載されている場合は上限値（1000万円）で判断すること。上限値が基準以上であればNGにしない。`);

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
    lines.push(`5. 不動産売買仲介・賃貸仲介の専業営業職（不動産エージェント・仲介営業のみのキャリア）、または保険外交員専業のキャリアの場合 → 要確認（上記1〜4を通過していても）`);
    lines.push(`6. 上記1〜5のいずれにも該当しない場合 → 必ずOKとすること`);
    lines.push(`7. 年収・在籍期間が不明で判断できない場合のみ「要確認」`);
    lines.push(`※公認会計士・税理士は医師・教授・弁護士・記者とは異なり即NG対象外。年収基準のみ適用`);
  }

  // 追加条件（設定タブで入力された場合）
  if (criteria.ageMin || criteria.ageMax) {
    const parts = [];
    if (criteria.ageMin) parts.push(`${criteria.ageMin}歳以上`);
    if (criteria.ageMax) parts.push(`${criteria.ageMax}歳以下`);
    lines.push(`- 年齢追加条件: ${parts.join('かつ')}`);
  }
  const tiers = (criteria.companyTiers || []).filter(t => t && t !== '不問');
  if (tiers.length > 0) {
    lines.push(`- 社格条件（追加）: 現職が${tiers.join('・')}のいずれかであること`);
  }
  if (criteria.educationReq && criteria.educationReq !== '不問') {
    lines.push(`- 学歴条件（追加）: ${criteria.educationReq}を満たすこと`);
  }
  // minTenure未設定時はデフォルト2年を適用
  const tenureYears = criteria.minTenure || 2;
  lines.push(`- 在籍期間: 異なる会社への転職で${tenureYears}年未満の在籍が1社でもある場合はNG。同一会社内での部署異動・職種変更・昇格・同社への複数行記入は同じ会社の在籍としてまとめて計算すること。出向・兼務の場合は出向元（親会社）の在籍期間に含め、出向先の短期在籍は別会社としてカウントしない。在籍期間が読み取れない場合はスキップ`);
  if (criteria.requiredKeywords) lines.push(`- 必須経験: ${criteria.requiredKeywords}`);
  if (criteria.excludeCompanies) lines.push(`- 除外企業（追加）: 職歴に${criteria.excludeCompanies}が含まれる場合は即NG`);
  if (criteria.excludeKeywords)  lines.push(`- 除外: ${criteria.excludeKeywords}`);
  return lines.join('\n');
}

// -------------------------------------------------------
// AI ポジション提案（セッション内キャッシュ付き）
// -------------------------------------------------------
const _aiSuggestCache = new Map(); // profileKey → suggestions

async function suggestPositionWithAI(candidateProfile, positionsWithDesc) {
  const stored = await chrome.storage.local.get(['apiKey']).catch(() => ({}));
  const apiKey = (stored.apiKey || '').replace(/[^\x21-\x7E]/g, '').trim();
  if (!apiKey || apiKey.length < 20) throw new Error('APIキー未設定');

  // 同じ候補者に対して2回目以降はキャッシュを返す
  const cacheKey = candidateProfile.slice(0, 200);
  if (_aiSuggestCache.has(cacheKey)) return _aiSuggestCache.get(cacheKey);

  const profile = candidateProfile.slice(0, 3000);
  const posList = positionsWithDesc.slice(0, 60).map((p, i) =>
    `${i + 1}. 【${p.name}】${p.description ? p.description.slice(0, 400) : ''}`
  ).join('\n');

  const prompt = `あなたは日本の転職エージェントのアシスタントです。
候補者のプロフィールを分析し、以下のポジション一覧の中からこの候補者の経験・スキルに最もマッチするポジションをトップ3選んでください。

選定ポイント：
- 候補者の直近の職種・業界経験が活かせるか
- 候補者のスキル・資格がポジション要件に合致するか
- キャリアアップとして自然なステップか

【候補者プロフィール】
${profile}

【ポジション一覧】
${posList}

必ず以下のJSON形式のみで回答してください。コードブロック・前置き・説明文は不要。nameは一覧の【】内と完全一致させること。
{"suggestions":[
  {"rank":1,"name":"ポジション名","reason":"マッチ理由を25文字以内で"},
  {"rank":2,"name":"ポジション名","reason":"マッチ理由を25文字以内で"},
  {"rank":3,"name":"ポジション名","reason":"マッチ理由を25文字以内で"}
]}`;

  const data = await claudeFetch(apiKey, {
    model: 'claude-haiku-4-5-20251001',
    max_tokens: 400,
    messages: [{ role: 'user', content: prompt }]
  });

  const text = (data.content?.[0]?.text || '').trim();
  const jsonMatch = text.match(/\{[\s\S]*\}/);
  if (!jsonMatch) throw new Error('AI応答のJSON解析失敗: ' + text.slice(0, 80));
  const parsed = JSON.parse(jsonMatch[0]);
  const suggestions = parsed.suggestions || [];
  if (suggestions.length > 0) _aiSuggestCache.set(cacheKey, suggestions);
  return suggestions;
}

// -------------------------------------------------------
// ポジションインジケーター（RDS/doda-X用）
// -------------------------------------------------------
async function initPositionIndicator() {
  const platform = getPlatform();
  if (!['rds', 'dodax', 'ambi'].includes(platform)) return;

  const existing = document.getElementById('snow-we-pos-indicator');
  if (existing) existing.remove();

  let positions = [];
  try {
    const res = await chrome.runtime.sendMessage({ type: 'getPositionList' });
    positions = res?.positions || [];
  } catch (_) {}

  const stored = await chrome.storage.local.get(['currentPosition']).catch(() => ({}));
  let currentPos = stored.currentPosition || '';

  const indicator = document.createElement('div');
  indicator.id = 'snow-we-pos-indicator';
  indicator.style.cssText = `
    position:fixed;top:12px;right:12px;z-index:2147483647;
    background:#1e293b;color:#fff;padding:7px 12px;border-radius:8px;
    font-size:12px;font-family:sans-serif;box-shadow:0 2px 12px rgba(0,0,0,0.35);
    cursor:pointer;display:flex;align-items:center;gap:8px;min-width:180px;
    border:1px solid #334155;user-select:none;
  `;

  const render = (pos) => {
    indicator.innerHTML = `
      <span style="font-size:14px">📌</span>
      <span style="flex:1;font-weight:500">${escapeHtml(pos || '未設定')}</span>
      <span style="color:#94a3b8;font-size:11px">▼</span>
    `;
  };
  render(currentPos);

  indicator.addEventListener('click', async (e) => {
    e.stopPropagation();
    const existingDrop = document.getElementById('snow-we-pos-dropdown');
    if (existingDrop) { existingDrop.remove(); return; }

    const dropdown = document.createElement('div');
    dropdown.id = 'snow-we-pos-dropdown';
    const rect = indicator.getBoundingClientRect();
    dropdown.style.cssText = `
      position:fixed;top:${rect.bottom + 4}px;right:12px;z-index:2147483647;
      background:#fff;border:1px solid #e2e8f0;border-radius:8px;
      box-shadow:0 4px 20px rgba(0,0,0,0.15);min-width:240px;
    `;

    // 検索ボックス
    const searchBox = document.createElement('input');
    searchBox.type = 'text';
    searchBox.placeholder = 'ポジションを検索...';
    searchBox.style.cssText = `
      width:100%;box-sizing:border-box;padding:9px 12px;
      border:none;border-bottom:1px solid #e2e8f0;font-size:12px;
      font-family:sans-serif;outline:none;border-radius:8px 8px 0 0;color:#1e293b;
    `;
    dropdown.appendChild(searchBox);

    // AI提案ボタン
    const aiBtn = document.createElement('div');
    aiBtn.style.cssText = `
      padding:9px 14px;cursor:pointer;font-size:12px;font-family:sans-serif;
      color:#6366f1;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;gap:6px;
      background:#fafafe;font-weight:500;
    `;
    aiBtn.innerHTML = '<span>✨</span><span>AIがこの候補者に合うポジションを提案</span>';
    aiBtn.addEventListener('mouseenter', () => { aiBtn.style.background = '#f0f0ff'; });
    aiBtn.addEventListener('mouseleave', () => { aiBtn.style.background = '#fafafe'; });
    dropdown.appendChild(aiBtn);

    // AI提案結果エリア
    const aiResults = document.createElement('div');
    aiResults.style.cssText = 'display:none;';
    dropdown.appendChild(aiResults);

    aiBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      aiBtn.innerHTML = '<span>⏳</span><span>分析中...</span>';
      aiBtn.style.pointerEvents = 'none';
      aiResults.style.display = 'block';
      aiResults.innerHTML = '<div style="padding:10px 14px;font-size:11px;color:#94a3b8;font-family:sans-serif;">プロフィールを読み取り中...</div>';
      try {
        const profile = extractProfile();
        if (!profile || profile.trim().length < 50) throw new Error('候補者プロフィールが読み取れませんでした。詳細パネルを開いてください。');

        aiResults.innerHTML = `<div style="padding:8px 14px;font-size:11px;color:#6b7280;font-family:sans-serif;background:#f8fafc;border-bottom:1px solid #e2e8f0;">📄 プロフィール取得済み（${profile.length}文字）— ポジションを分析中...</div>`;

        const posRes = await chrome.runtime.sendMessage({ type: 'getPositionListWithDesc' });
        const posWithDesc = posRes?.positions || [];
        if (posWithDesc.length === 0) throw new Error('ポジション情報を取得できませんでした（ポップアップ設定でGAS URLを確認してください）');

        const suggestions = await suggestPositionWithAI(profile, posWithDesc);
        if (!suggestions || suggestions.length === 0) throw new Error('提案結果が空でした');

        aiResults.innerHTML = '';
        const header = document.createElement('div');
        header.style.cssText = 'padding:6px 14px;font-size:10px;color:#6366f1;font-family:sans-serif;font-weight:600;background:#f5f3ff;border-bottom:1px solid #ede9fe;letter-spacing:0.5px;';
        header.textContent = '✨ AIおすすめポジション';
        aiResults.appendChild(header);

        suggestions.forEach(s => {
          const sItem = document.createElement('div');
          sItem.style.cssText = `
            padding:9px 14px;cursor:pointer;font-size:12px;font-family:sans-serif;
            color:#1e293b;border-bottom:1px solid #ede9fe;background:#faf5ff;
          `;
          sItem.innerHTML = `
            <div style="font-weight:600;color:#4f46e5;">${s.rank}位 ${escapeHtml(s.name || '')}</div>
            <div style="font-size:11px;color:#6b7280;margin-top:2px;">${escapeHtml(s.reason || '')}</div>
          `;
          sItem.addEventListener('mouseenter', () => { sItem.style.background = '#ede9fe'; });
          sItem.addEventListener('mouseleave', () => { sItem.style.background = '#faf5ff'; });
          sItem.addEventListener('click', async (e) => {
            e.stopPropagation();
            currentPos = s.name;
            await chrome.storage.local.set({ currentPosition: s.name }).catch(() => {});
            console.log('[Snow-we] AIポジション選択:', s.name);
            render(s.name);
            dropdown.remove();
          });
          aiResults.appendChild(sItem);
        });

        const divider = document.createElement('div');
        divider.style.cssText = 'padding:6px 14px;font-size:10px;color:#94a3b8;font-family:sans-serif;background:#f8fafc;border-bottom:1px solid #e2e8f0;letter-spacing:0.5px;';
        divider.textContent = '─── 全ポジション ───';
        aiResults.appendChild(divider);
      } catch (err) {
        aiResults.innerHTML = `<div style="padding:10px 14px;font-size:11px;color:#ef4444;font-family:sans-serif;">${escapeHtml(err.message || 'エラーが発生しました')}</div>`;
      }
      aiBtn.innerHTML = '<span>✨</span><span>AIがこの候補者に合うポジションを提案</span>';
      aiBtn.style.pointerEvents = 'auto';
    });

    const list = document.createElement('div');
    list.style.cssText = 'max-height:280px;overflow-y:auto;';
    dropdown.appendChild(list);

    const renderItems = (filter = '') => {
      list.innerHTML = '';
      const filtered = positions.filter(p => !filter || p.toLowerCase().includes(filter.toLowerCase()));
      if (filtered.length === 0) {
        const empty = document.createElement('div');
        empty.style.cssText = 'padding:12px 14px;font-size:12px;color:#94a3b8;font-family:sans-serif;';
        empty.textContent = '該当なし';
        list.appendChild(empty);
        return;
      }
      filtered.forEach(pos => {
        const item = document.createElement('div');
        item.style.cssText = `
          padding:10px 14px;cursor:pointer;font-size:12px;font-family:sans-serif;
          color:#1e293b;border-bottom:1px solid #f1f5f9;
          ${pos === currentPos ? 'background:#eff6ff;font-weight:600;' : ''}
        `;
        item.textContent = pos;
        item.addEventListener('mouseenter', () => { if (pos !== currentPos) item.style.background = '#f8fafc'; });
        item.addEventListener('mouseleave', () => { if (pos !== currentPos) item.style.background = ''; });
        item.addEventListener('click', async (e) => {
          e.stopPropagation();
          currentPos = pos;
          await chrome.storage.local.set({ currentPosition: pos }).catch(e => console.warn('[Snow-we] ポジション保存失敗:', e));
          console.log('[Snow-we] ポジション選択:', pos);
          render(pos);
          dropdown.remove();
        });
        list.appendChild(item);
      });
    };

    renderItems();
    searchBox.addEventListener('input', () => renderItems(searchBox.value));
    searchBox.addEventListener('click', e => e.stopPropagation());

    document.body.appendChild(dropdown);
    setTimeout(() => searchBox.focus(), 0);
    const close = (e) => { if (!dropdown.contains(e.target) && e.target !== indicator) { dropdown.remove(); document.removeEventListener('click', close); } };
    setTimeout(() => document.addEventListener('click', close), 0);
  });

  document.body.appendChild(indicator);
}

// -------------------------------------------------------
// 詳細パネル自動AI判定（候補者を開いた瞬間に判定バッジを表示）
// -------------------------------------------------------
let _detailJudgeTimer = null;
let _lastDetailText = '';

async function runDetailPanelJudge() {
  const platform = getPlatform();
  if (!['rds', 'dodax', 'ambi'].includes(platform)) return;

  let panel = null;
  if (platform === 'rds') panel = findRDSDetailPanel();
  else if (platform === 'dodax') panel = findDodaxDetailPanel();
  else panel = findAMBIDetailPanel();
  if (!panel) return;

  const panelText = (panel.innerText || '').trim();
  if (panelText.length < 100) return;
  // 前回と同じパネルなら再判定しない
  if (panelText.slice(0, 300) === _lastDetailText.slice(0, 300)) return;
  _lastDetailText = panelText;

  // 設定取得
  let stored = {};
  try { stored = await chrome.storage.local.get(['apiKey', 'screeningCriteria', 'currentPosition']); } catch (_) { return; }
  const apiKey = (stored.apiKey || '').replace(/[^\x21-\x7E]/g, '').trim();
  if (!apiKey || apiKey.length < 20) return;
  const criteria = stored.screeningCriteria || {};
  if (!Object.keys(criteria).length) return;

  // 既存バッジを削除・「判定中」バッジを表示
  document.getElementById('snow-we-detail-badge')?.remove();
  const badge = document.createElement('div');
  badge.id = 'snow-we-detail-badge';
  badge.style.cssText = `
    position:fixed;bottom:80px;right:12px;z-index:2147483647;
    background:#1e293b;color:#e2e8f0;padding:8px 14px;border-radius:8px;
    font-size:12px;font-family:sans-serif;box-shadow:0 2px 12px rgba(0,0,0,0.35);
    display:flex;align-items:center;gap:6px;border:1px solid #334155;
    max-width:280px;
  `;
  badge.innerHTML = '<span style="animation:spin 1s linear infinite;display:inline-block">⏳</span><span>AI判定中...</span>';
  document.body.appendChild(badge);

  try {
    // extractProfile() を優先（プラットフォーム別のキーワード抽出が効く）
    let profileText = '';
    try { profileText = extractProfile(); } catch (_) {}
    if (!profileText || profileText.trim().length < 50) {
      profileText = removeNonProfileSections(extractMainText(panel, 5000));
    }
    if (!profileText || profileText.trim().length < 50) { badge.remove(); return; }

    const result = await judgeSingleCandidate(apiKey, profileText, criteria);
    const { verdict, reason, confidence } = result;

    badge.remove();
    const resultBadge = document.createElement('div');
    resultBadge.id = 'snow-we-detail-badge';
    const [bg, border, icon] = verdict === 'OK'
      ? ['#052e16', '#166534', '✅']
      : verdict === 'NG'
      ? ['#450a0a', '#991b1b', '❌']
      : ['#1c1917', '#78716c', '⚠️'];
    resultBadge.style.cssText = `
      position:fixed;bottom:80px;right:12px;z-index:2147483647;
      background:${bg};color:#f1f5f9;padding:8px 14px;border-radius:8px;
      font-size:12px;font-family:sans-serif;box-shadow:0 2px 12px rgba(0,0,0,0.35);
      border:1px solid ${border};max-width:300px;cursor:pointer;
    `;
    const confText = confidence != null ? ` (${confidence}%)` : '';
    resultBadge.innerHTML = `
      <div style="font-weight:600;margin-bottom:3px;">${icon} ${escapeHtml(verdict)}${confText}</div>
      ${reason ? `<div style="font-size:11px;color:#94a3b8;">${escapeHtml(reason)}</div>` : ''}
    `;
    resultBadge.title = 'クリックで閉じる';
    resultBadge.addEventListener('click', () => resultBadge.remove());
    document.body.appendChild(resultBadge);
    // 60秒後に自動削除
    setTimeout(() => resultBadge.remove(), 60000);
  } catch (_) {
    badge.remove();
  }
}

// スカウト済み通知を詳細パネルに表示
async function showScoutedNoticeInPanel(panel) {
  if (!panel) return;
  const existing = document.getElementById('snow-we-scouted-notice');
  if (existing) existing.remove();

  const history = await getScoutHistory();
  if (!Object.keys(history).length) return;

  let matchRecord = null;

  // ① パネル内にプロフィールURLがあればIDとして直接照合
  const pUrl = findProfileUrl(panel);
  if (pUrl) {
    const cleanUrl = pUrl.replace(/[?#].*$/, '');
    if (history[cleanUrl]) matchRecord = history[cleanUrl];
  }

  // ② 現在のページURL（プロフィール専用ページの場合）
  if (!matchRecord) {
    const pageUrl = location.href.replace(/[?#].*$/, '');
    if (history[pageUrl]) matchRecord = history[pageUrl];
  }

  // ③ 会社名の部分一致（リスト画面で同一会社の候補者を検出）
  if (!matchRecord) {
    const panelInfo = extractBasicInfo(panel);
    const panelCompany = (panelInfo.company || '').trim();
    if (panelCompany.length >= 2) {
      const maxAge = 180 * 24 * 60 * 60 * 1000;
      const now = Date.now();
      for (const rec of Object.values(history)) {
        if (!rec.company || !rec.date || now - rec.date > maxAge) continue;
        const stored = rec.company.trim();
        if (stored && (stored.includes(panelCompany) || panelCompany.includes(stored))) {
          matchRecord = rec; break;
        }
      }
    }
  }

  if (!matchRecord) return;

  const daysAgo = Math.floor((Date.now() - matchRecord.date) / (1000 * 60 * 60 * 24));
  const notice = document.createElement('div');
  notice.id = 'snow-we-scouted-notice';
  notice.style.cssText = `
    position:fixed;top:55px;right:12px;z-index:2147483647;
    background:#1e3a5f;color:#bfdbfe;padding:6px 12px;border-radius:6px;
    font-size:11px;font-family:sans-serif;box-shadow:0 2px 8px rgba(0,0,0,0.3);
    border:1px solid #2563eb;cursor:pointer;
  `;
  notice.textContent = `📨 ${daysAgo === 0 ? '本日' : daysAgo + '日前'}にスカウト済み${matchRecord.position ? ' (' + matchRecord.position + ')' : ''}`;
  notice.title = 'クリックで閉じる';
  notice.addEventListener('click', () => notice.remove());
  document.body.appendChild(notice);
  setTimeout(() => notice.remove(), 30000);
}

function initDetailPanelObserver() {
  const platform = getPlatform();
  if (!['rds', 'dodax', 'ambi'].includes(platform)) return;

  // MutationObserver on body は高コストのためポーリングに変更（2秒間隔）
  let _pollTimer = null;
  const poll = () => {
    clearTimeout(_detailJudgeTimer);
    _detailJudgeTimer = setTimeout(async () => {
      const p = platform === 'rds' ? findRDSDetailPanel()
              : platform === 'dodax' ? findDodaxDetailPanel()
              : findAMBIDetailPanel();
      await showScoutedNoticeInPanel(p);
      await runDetailPanelJudge();
    }, 1500);
  };

  // ページクリックを契機にパネル変化を検知（カードクリック = 候補者切り替え）
  document.addEventListener('click', poll, true);
  // 初回チェック（ページロード時に詳細が開いている場合）
  setTimeout(poll, 3000);
}

// ページロード後に自動追加の再開チェック（sessionStorageのみ使用）
window.addEventListener('load', () => {
  setTimeout(async () => {
    injectStyles();
    initPositionIndicator();
    initDetailPanelObserver();
    try {
      const raw = sessionStorage.getItem('snowWeAutoAdd');
      if (!raw) {
        // 再開フラグなし → running フラグをリセットして終了
        await saveAutoAddProgress({ running: false });
        return;
      }
      const resume = JSON.parse(raw);
      sessionStorage.removeItem('snowWeAutoAdd'); // 即座に削除して二重起動防止
      if (resume.resume) {
        // 夜間自動実行モード復元
        if (resume.autoRun) {
          _isAutoRunMode = true;
          _autoRunMaxPages = resume.autoRun.maxPages || 2;
          _autoRunPageCount = resume.autoRun.pageCount || 0;
        }
        // 再開時は進捗を running:true で復元してから triggerAutoAdd を呼ぶ
        // ← これをしないと isFreshStart=true になり最初からやり直しになる
        await saveAutoAddProgress({
          added:     resume.added     || 0,
          processed: resume.processed || 0,
          running:   true,
          ts:        Date.now(),
        });
        await sleep(1500);
        triggerAutoAdd();
      } else {
        await saveAutoAddProgress({ running: false });
      }
    } catch (_) {
      await saveAutoAddProgress({ running: false });
    }
  }, 1000);
});

// -------------------------------------------------------
// 一括判定：プラットフォーム別カード検出で全候補者を取得
// -------------------------------------------------------
function extractAllCandidateCards() {
  const cards = findCandidateCardsByPlatform();

  return cards.slice(0, 2000).map(el => {
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
    const cls = (el.getAttribute ? (el.getAttribute('class') || '') : '').toLowerCase();
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
// doda X 詳細パネルを特定する（カードクリックで開く右パネル）
// -------------------------------------------------------
function findDodaxDetailPanel() {
  const viewportWidth = window.innerWidth;
  const candidates = [];
  const keywords = ['職務経歴', '転職意向', '転職を', '職歴', '業務内容', '学歴', '年収'];
  document.querySelectorAll('div, section, article, aside, main').forEach(el => {
    const rect = el.getBoundingClientRect();
    const t = (el.innerText || '').trim();
    if (rect.left > viewportWidth * 0.35 && rect.width > 200 && t.length > 100 && t.length < 30000) {
      const hasKeyword = keywords.some(kw => t.includes(kw));
      if (hasKeyword) candidates.push({ el, score: t.length, left: Math.round(rect.left) });
    }
  });
  console.log('[Snow-we] findDodaxDetailPanel: 候補数=' + candidates.length,
    candidates.slice(0, 3).map(c => `left=${c.left} len=${c.score}`).join(', '));
  if (candidates.length === 0) {
    // キーワードなしでも右側パネルを探す（ローディング中対策）
    document.querySelectorAll('div, section, aside').forEach(el => {
      const rect = el.getBoundingClientRect();
      const t = (el.innerText || '').trim();
      if (rect.left > viewportWidth * 0.5 && rect.width > 200 && t.length > 50) {
        candidates.push({ el, score: t.length, left: Math.round(rect.left) });
      }
    });
    console.log('[Snow-we] findDodaxDetailPanel(緩): 候補数=' + candidates.length,
      candidates.slice(0, 3).map(c => `left=${c.left} len=${c.score}`).join(', '));
    if (candidates.length === 0) return null;
  }
  candidates.sort((a, b) => b.score - a.score);
  return candidates[0].el;
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
    detailPanel = findBizreachDetailPanel();
    const bzRoot = detailPanel || null;
    const byKeyword = extractByKeywords([
      '職務経歴', '職歴', 'スキル', '業務内容', '実績',
      '学歴', '語学', '資格', '自己PR', '希望条件',
      '経験業種', '経験職種', '希望年収', '年収'
    ], bzRoot, 30, 12000);
    const bySelector = extractBySelectors([
      '[class*="profile"]', '[class*="career"]',
      '[class*="resume"]', '[class*="skill"]',
      '[class*="pr"]', '[class*="history"]', '[class*="work"]',
      '[class*="scout"]', '[class*="Scout"]',
      'section', 'article'
    ], bzRoot);
    text = byKeyword.length >= bySelector.length ? byKeyword : bySelector;
    if (text) text = removeNonProfileSections(text);
    if (!text || text.trim().length < 100) {
      text = detailPanel ? removeNonProfileSections(extractMainText(detailPanel, 5000)) : '';
    }

  } else if (host.includes('doda-x') || host.includes('dodax') || host.includes('x.doda')) {
    detailPanel = findDodaxDetailPanel();
    const ddRoot = detailPanel || null;

    const byKeyword = extractByKeywords([
      '職務経歴', '職歴', '業務内容', '仕事内容',
      'スキル', '技術', '開発言語', '資格',
      '学歴', '最終学歴', '大学', '大学院',
      '語学', '英語', 'TOEIC',
      '自己PR', 'PR', 'アピール',
      '転職理由', '希望年収', '希望職種',
      '経験業種', '経験職種', '経験社数', '年収'
    ], ddRoot, 30, 12000);

    const bySelector = extractBySelectors([
      '[class*="workHistory"]', '[class*="work-history"]',
      '[class*="career"]', '[class*="summary"]',
      '[class*="skill"]', '[class*="resume"]',
      '[class*="profile"]', 'section', 'article'
    ], ddRoot);

    text = byKeyword.length >= bySelector.length ? byKeyword : bySelector;
    if (text) text = removeNonProfileSections(text);

    if (!text || text.trim().length < 100) {
      text = detailPanel ? removeNonProfileSections(extractMainText(detailPanel, 5000)) : '';
    }

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
      text = removeNonProfileSections(extractByKeywords([
        '職務経歴', '職歴', '職務要約',
        'スキル', '資格', '学歴',
        '語学', '自己PR', 'アピール',
        '希望年収', '年収', '転職理由'
      ]));

      if (text.length < 100) {
        text = removeNonProfileSections(extractBySelectors([
          '[class*="resume"]', '[class*="career"]',
          '[class*="history"]', '[class*="skill"]',
          '[class*="profile"]', '[class*="summary"]',
          '[class*="candidate"]', '[class*="detail"]',
          'section', 'article', 'table'
        ]));
      }
    }

  } else if (host.includes('green-japan')) {
    text = extractByKeywords([
      '職務経歴', '経験業種', 'スキル', '最終学歴', '語学',
      '経験業界', '経験職種', '資格', 'スカウト希望', '希望業界',
      '希望職種', '希望勤務地', '転職先に求める', '自己PR'
    ]);
    if (text) text = removeNonProfileSections(text);

  } else if (host.includes('ambi') || host.includes('en-ambi')) {
    detailPanel = findAMBIDetailPanel();
    const ambiRoot = detailPanel || null;
    const byKeyword = extractByKeywords([
      '職務経歴', '職歴', '業務内容', '仕事内容',
      'スキル', '技術', '開発言語', '資格',
      '学歴', '最終学歴', '大学',
      '語学', '英語', 'TOEIC',
      '自己PR', 'PR', 'アピール',
      '希望条件', '希望職種', '希望業界', '希望年収',
      '経験業種', '経験職種', '転職理由'
    ], ambiRoot, 30, 10000);
    const bySelector = extractBySelectors([
      '[class*="career"]', '[class*="resume"]',
      '[class*="profile"]', '[class*="skill"]',
      '[class*="history"]', 'section', 'article'
    ], ambiRoot);
    text = byKeyword.length >= bySelector.length ? byKeyword : bySelector;
    if (text) text = removeNonProfileSections(text);
    if (!text || text.trim().length < 100) {
      text = detailPanel ? removeNonProfileSections(extractMainText(detailPanel, 2500)) : '';
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
    if (text) text = removeNonProfileSections(text);
    if (!text || text.length < 100) {
      text = detailPanel ? removeNonProfileSections(extractMainText(root, 2500)) : '';
    }

  } else if (host.includes('recruitdirect') || host.includes('rds')) {
    detailPanel = findRDSDetailPanel();
    const rdsRoot = detailPanel || null;
    const byKeyword = extractByKeywords([
      '職務経歴', '職歴', '業務内容', '仕事内容',
      'スキル', '技術', '開発言語', '資格',
      '学歴', '最終学歴', '大学',
      '語学', '英語', 'TOEIC',
      '自己PR', 'PR', 'アピール',
      '転職理由', '希望年収', '希望職種',
      '経験業種', '経験職種', '年収'
    ], rdsRoot, 30, 12000);
    const bySelector = extractBySelectors([
      '[class*="profile"]', '[class*="career"]',
      '[class*="resume"]', '[class*="skill"]',
      '[class*="history"]', '[class*="work"]',
      '[class*="candidate"]', '[class*="detail"]',
      'section', 'article', 'table'
    ], rdsRoot);
    text = byKeyword.length >= bySelector.length ? byKeyword : bySelector;
    if (text) text = removeNonProfileSections(text);
    if (!text || text.trim().length < 100) {
      text = detailPanel ? removeNonProfileSections(extractMainText(detailPanel, 5000)) : '';
    }

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
        const isRDS = location.hostname.includes('rikunabi') || location.hostname.includes('hrtech') || location.hostname.includes('recruitdirect');
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
    triggerAutoAdd().catch(e => {
      const msg = e?.message || '';
      if (!msg.includes('Extension context invalidated') && !msg.includes('message channel closed')) {
        console.error('[Snow-we] triggerAutoAdd 予期しないエラー:', msg);
      }
    });
    sendResponse({ success: true });
  }

  if (request.type === 'autoRun') {
    _isAutoRunMode = true;
    _autoRunPageCount = 0;
    _autoRunMaxPages = request.maxPages || 2;
    _autoRunSlotId = request.slotId ?? 0;
    console.log(`[Snow-we] 夜間自動実行開始 スロット${_autoRunSlotId} (最大${_autoRunMaxPages}ページ, ${request.urlIndex + 1}/${request.totalUrls})`);
    showAutoStatus(`🌙 自動実行中... (${request.urlIndex + 1}/${request.totalUrls}件目)`);
    // doda-X 検索条件リストページは専用処理
    if (location.href.includes('search_list')) {
      autoRunListPage(request).catch(e => console.error('[Snow-we] リスト自動実行エラー:', e?.message));
    // BizReach 検索条件タブ一覧ページ（/resumes/{id}/list）
    } else if (getPlatform() === 'bizreach' && /\/resumes\/\d+\/list/.test(location.pathname)) {
      autoRunBizreachListPage(request).catch(e => console.error('[Snow-we] Bizreachリスト自動実行エラー:', e?.message));
    } else {
      triggerAutoAdd().catch(e => console.error('[Snow-we] 自動実行エラー:', e?.message));
    }
    sendResponse({ ok: true });
    return true;
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
