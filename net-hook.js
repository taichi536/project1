// ページ側の通信を見て、「スカウトが実際に送信された」ことを検知する。
//
// ■ なぜ必要か
// これまで送信の検知は、押されたボタンの表示文字列の完全一致で行っていた。
//
//   const isSendBtn = textCore === '送信' || textCore === '送信する' || textCore === 'スカウトを送信';
//
// 掲載側が文言を変えたり、担当者によって通る画面が違ったりすると、その瞬間から
// 記録が止まる。しかも画面には何も出ないので誰も気づけない。実データで、ある担当者の
// RDSだけ送信の36〜52%が記録されておらず、25分間に19件連続で消えた時間帯もあった。
// その前後の別媒体は同じバージョンで正常に記録していた。
//
// 文言を1つずつ足しても、次に画面が変わればまた同じことが起きる。
//
// ■ 何を見るか
// 送信そのもの、つまり掲載側のサーバーへ送信リクエストが飛んで成功したことを見る。
// RDSの実機で確認した送信は次のとおり。
//
//   POST https://ats.hrtech.rikunabi.com/api/client/headhunter/transaction/
//        scouting/scoutroom/1678665/scout   → 200
//
// URLの scoutroom/1678665 が、その候補者とのやり取りを指す識別子になっている。
// ボタンの文言にも画面構成にも依存せず、候補者の識別子も同時に得られる。
//
// ■ なぜ別ファイルなのか
// content.js は拡張機能用の隔離された世界で動くため、そこで window.fetch を
// 包んでもページ自身の通信は捕まえられない。このファイルは manifest の
// world: "MAIN" でページ側の世界に読み込む。
//
// ページの動作を壊さないことを最優先にする。包んだ処理は元の呼び出しを
// そのまま通し、こちらの処理は必ず try で囲んで、失敗しても握り潰す。
(() => {
  'use strict';
  if (window.__snowweNetHook) return;
  window.__snowweNetHook = true;
  // content.js（隔離された世界）から「フックが動いている」ことを見えるようにする。
  // window の変数は世界をまたいで見えないが、DOM は共有されている。
  // 以前は最初の通信を受けて初めて動いていると判断していたため、ページを開いて
  // 最初の通信が送信そのものだった場合に、ボタン経路と通信経路の両方が動いていた
  try { document.documentElement.setAttribute('data-snowwe-net-hook', '1'); } catch (_) {}

  const EVENT = 'snowwe:request';

  // 送信内容は、一括送信で「誰に送ったか」を知るために要る。1回の通信で複数人に
  // 送るため、画面の操作だけでは人数も対象も分からない。
  // 中身をそのまま外に出すことはせず、content.js 側で候補者の識別子だけを取り出す
  const MAX_BODY = 20000;

  function bodyText(body) {
    try {
      if (typeof body === 'string') return body.slice(0, MAX_BODY);
      if (body instanceof URLSearchParams) return body.toString().slice(0, MAX_BODY);
      if (body instanceof FormData) {
        const o = {};
        body.forEach((v, k) => { o[k] = typeof v === 'string' ? v : '(file)'; });
        return JSON.stringify(o).slice(0, MAX_BODY);
      }
    } catch (_) {}
    return '';
  }

  function notify(method, url, status, body) {
    try {
      if (!method || String(method).toUpperCase() !== 'POST') return;
      if (!(status >= 200 && status < 300)) return;
      window.dispatchEvent(new CustomEvent(EVENT, {
        detail: {
          method: String(method).toUpperCase(),
          url: String(url || ''),
          status,
          body: bodyText(body),
        },
      }));
    } catch (_) {}
  }

  // ── XMLHttpRequest ──
  // RDSの送信はこちらを通っていた（実機のNetworkタブで type=xhr を確認）
  try {
    const open = XMLHttpRequest.prototype.open;
    const send = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (method, url) {
      try {
        this.__snowweMethod = method;
        this.__snowweUrl = url;
      } catch (_) {}
      return open.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function (body) {
      try {
        this.addEventListener('load', () => {
          notify(this.__snowweMethod, this.__snowweUrl, this.status, body);
        });
      } catch (_) {}
      return send.apply(this, arguments);
    };
  } catch (_) {}

  // ── fetch ──
  // 媒体によっては fetch を使う。RDS以外への展開に備えて両方包んでおく
  try {
    const origFetch = window.fetch;
    if (typeof origFetch === 'function') {
      window.fetch = function (input, init) {
        const method = (init && init.method) || (input && input.method) || 'GET';
        const url = (typeof input === 'string') ? input : (input && input.url) || '';
        const p = origFetch.apply(this, arguments);
        try {
          const b = (init && init.body) || (input && input.body) || '';
          p.then(res => { try { notify(method, url, res.status, b); } catch (_) {} }, () => {});
        } catch (_) {}
        return p;
      };
    }
  } catch (_) {}
})();
