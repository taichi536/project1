// background.js — 拡張機能コンテキストからGASへのリクエストを中継する
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type !== 'gasPost') return false;

  const { url, payload } = msg;
  if (!url) { sendResponse({ ok: false }); return true; }

  fetch(url, { method: 'POST', body: JSON.stringify(payload) })
    .then(() => sendResponse({ ok: true }))
    .catch(() => sendResponse({ ok: false }));

  return true; // 非同期レスポンスを使う
});
