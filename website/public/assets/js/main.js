// Snow-we.Inc コーポレートサイト 共通スクリプト
(function () {
  // モバイルメニュー
  var toggle = document.querySelector('.menu-toggle');
  var nav = document.getElementById('global-nav');
  if (toggle && nav) {
    toggle.addEventListener('click', function () {
      var open = nav.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    nav.querySelectorAll('a').forEach(function (link) {
      link.addEventListener('click', function () {
        nav.classList.remove('is-open');
        toggle.setAttribute('aria-expanded', 'false');
      });
    });
  }

  // トップページのヒーローに雪を降らせる
  var snow = document.getElementById('snow-container');
  if (snow && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    for (var i = 0; i < 20; i++) {
      var flake = document.createElement('div');
      flake.className = 'snowflake';
      flake.setAttribute('aria-hidden', 'true');
      flake.innerHTML = '<svg width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0L13.5 6.5L20 8L13.5 9.5L12 16L10.5 9.5L4 8L10.5 6.5L12 0Z"/></svg>';
      flake.style.left = Math.random() * 100 + '%';
      flake.style.animationDuration = (8 + Math.random() * 10) + 's';
      flake.style.animationDelay = (Math.random() * 5) + 's';
      flake.style.fontSize = (10 + Math.random() * 14) + 'px';
      snow.appendChild(flake);
    }
  }

  // LINE 相談ボタンのクリックを GA4 のコンバージョンとして計測
  document.querySelectorAll('a[href^="https://lin.ee/"]').forEach(function (link) {
    link.addEventListener('click', function () {
      if (typeof window.gtag === 'function') window.gtag('event', 'generate_lead', { method: 'line', page_path: location.pathname });
    });
  });

  // お問い合わせフォーム（Formspree に送信）
  var ENDPOINT = 'https://formspree.io/f/mlgpyzoe';
  var form = document.getElementById('snow-contact-form');
  if (!form) return;
  // フォームが画面に入ったら、下部固定の LINE ボタンを隠して送信ボタンに重ならないようにする
  var floating = document.querySelector('.floating-cta');
  if (floating && 'IntersectionObserver' in window) {
    new IntersectionObserver(function (entries) {
      floating.classList.toggle('is-hidden', entries[0].isIntersecting);
    }).observe(form);
  }

  var btn = document.getElementById('snow-submit-btn');
  var msgBox = document.getElementById('snow-form-message');
  var btnLabel = btn.textContent;

  function showMsg(text, type) {
    msgBox.textContent = text;
    msgBox.className = 'cform-message ' + type;
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    msgBox.className = 'cform-message';
    var lastName = form.last_name.value.trim();
    var firstName = form.first_name.value.trim();
    var email = form.email.value.trim();
    if (!lastName || !firstName) return showMsg('お名前を入力してください。', 'error');
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return showMsg('有効なメールアドレスを入力してください。', 'error');
    if (!form.privacy.checked) return showMsg('個人情報の取り扱いへの同意をチェックしてください。', 'error');

    btn.disabled = true;
    btn.textContent = '送信中…';
    fetch(ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({
        '姓': lastName,
        '名': firstName,
        '姓_ふりがな': form.last_kana.value.trim(),
        '名_ふりがな': form.first_kana.value.trim(),
        '電話番号': form.phone.value.trim(),
        'メールアドレス': email,
        '相談内容': form.message.value.trim(),
        '送信元ページ': location.pathname,
        '_replyto': email,
        '_subject': '【Snow-we.jp】お問い合わせがありました'
      })
    }).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      form.reset();
      showMsg('お問い合わせありがとうございます。担当者より折り返しご連絡いたします。', 'success');
      if (typeof window.gtag === 'function') window.gtag('event', 'generate_lead', { method: 'form' });
    }).catch(function () {
      showMsg('送信に失敗しました。時間をおいて再度お試しいただくか、LINEからご連絡ください。', 'error');
    }).finally(function () {
      btn.disabled = false;
      btn.textContent = btnLabel;
    });
  });
})();
