import streamlit as st
import pandas as pd
import os
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="株式売買タイミング分析ツール",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

from modules.data_fetcher import fetch_ohlcv, fetch_info, fetch_earnings_date
from modules.technical import compute_all
from modules.signals import evaluate_signals, overall_signal, generate_action_plan, evaluate_hold_signal, evaluate_watch_signal, detect_breakout, calc_signal_accuracy, multi_timeframe_signal, calc_signal_confidence, get_signal_detail
from modules.charts import build_main_chart
from modules.fundamental import get_fundamental_summary, get_risk_metrics
from modules.screening import screen_single
from modules.diary import add_trade, get_trades, add_review, get_reviews, trade_stats, init_db, calc_pnl, calc_unrealized
from modules.ai_analysis import analyze_five_forces, analyze_chart_ai
from modules.news_fetcher import fetch_market_news, score_macro_relevance
from modules.macro_analysis import get_macro_context, analyze_news_sentiment, quick_market_sentiment, fetch_live_market_data, get_market_sentiment_rule, get_sector_impact
from modules.backtest import run_backtest, STRATEGIES
from modules.portfolio import build_portfolio_summary
from modules.charts import build_backtest_chart, build_correlation_heatmap, build_portfolio_pie
from modules.notifier import send_signal_alert, send_screening_alert, send_stop_loss_alert, send_strong_buy_alert
from modules.dashboard import load_watchlist, save_watchlist, scan_all
from modules.ml_model import train_model, trend_regression, detect_candlestick_patterns, ml_score_signal
from modules.risk_filter import assess_signal_risk
from modules.market_utils import market_status

init_db()

# ─── サイドバー ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📈 株式分析ツール")
    st.markdown("---")

    # 市場ステータス
    mst = market_status()
    jp_color = "#26a69a" if "開場" in mst["jp_label"] else "#888"
    us_color = "#26a69a" if "開場" in mst["us_label"] else "#888"
    st.markdown(
        f"<span style='color:{jp_color}'>●</span> **東証** {mst['jp_label']}　"
        f"<span style='color:{us_color}'>●</span> **NYSE** {mst['us_label']}",
        unsafe_allow_html=True,
    )
    st.caption(mst["now_jst"])
    st.markdown("---")

    # ── グローバル銘柄選択（全ページ共通） ───────────────────────────────
    _wl = load_watchlist()
    st.markdown("**📌 分析銘柄**")
    _ticker_options = _wl + ["✏️ 直接入力"]
    _cur = st.session_state.get("current_ticker", _wl[0] if _wl else "")
    _def_idx = _wl.index(_cur) if _cur in _wl else len(_wl)
    _sel = st.selectbox(
        "銘柄を選択",
        _ticker_options,
        index=_def_idx,
        label_visibility="collapsed",
        key="sidebar_ticker_select",
    )
    if _sel == "✏️ 直接入力":
        _manual = st.text_input(
            "銘柄コード（例: 7203 / AAPL）",
            value="" if _cur in _wl else _cur,
            label_visibility="collapsed",
            placeholder="7203 / AAPL",
        )
        if _manual:
            st.session_state["current_ticker"] = _manual.strip().upper()
    else:
        st.session_state["current_ticker"] = _sel

    _ct = st.session_state.get("current_ticker", "")
    if _ct:
        st.caption(f"選択中: **{_ct}**　← 全ページで共通")
    st.markdown("---")

    _PAGES = ["🏠 ダッシュボード", "🔭 銘柄スキャン", "📊 テクニカル分析", "🔍 スクリーニング", "📋 ファンダメンタル分析", "🌐 マクロ・ニュース", "🔬 バックテスト", "📐 ポートフォリオ", "📔 投資日記", "🔔 通知設定", "🤖 自動売買", "📖 トレードガイド"]
    if "_nav_target" in st.session_state:
        _target = st.session_state.pop("_nav_target")
        if _target in _PAGES:
            st.session_state["menu_page"] = _target

    page = st.radio(
        "メニュー",
        _PAGES,
        label_visibility="collapsed",
        key="menu_page",
    )
    st.markdown("---")

    # 初心者モード
    beginner_mode = st.toggle(
        "🔰 初心者モード",
        value=st.session_state.get("beginner_mode", True),
        help="オンにすると専門用語を減らし、具体的な行動提案を優先表示します",
    )
    st.session_state["beginner_mode"] = beginner_mode

    # AI機能のオンオフ（コスト管理）
    ai_enabled = st.toggle(
        "🤖 AI分析機能",
        value=st.session_state.get("ai_enabled", False),
        help="オフにするとClaude APIを呼び出しません（コスト0円）",
    )
    st.session_state["ai_enabled"] = ai_enabled
    if ai_enabled:
        st.caption("✅ AI有効（API料金が発生します）")
    else:
        st.caption("⏸ AI無効（無料モード）")

    # 今月のコスト表示
    from modules.ai_analysis import get_cost_summary
    cost_data = get_cost_summary()
    month = __import__("time").strftime("%Y-%m")
    if month in cost_data:
        m = cost_data[month]
        usd = m.get("estimated_usd", 0)
        jpy = usd * 150
        cached = m.get("cached_calls", 0)
        total = m.get("calls", 0)
        st.caption(f"今月のAI: {total}回（キャッシュ{cached}回）/ 推定¥{jpy:.0f}")


# ─── ダッシュボード ───────────────────────────────────────────────────────────
if page == "🏠 ダッシュボード":
    st.title("🏠 ダッシュボード")
    _notif_active = bool(os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("SLACK_WEBHOOK_URL"))
    if _notif_active:
        st.caption("登録銘柄のシグナルを一覧で確認できます　🔔 シグナル変化の自動通知: **有効**")
    else:
        st.caption("登録銘柄のシグナルを一覧で確認できます　🔕 自動通知: 未設定（🔔通知設定で設定できます）")

    # ウォッチリスト編集
    watchlist = load_watchlist()
    with st.expander("⚙️ 監視銘柄を編集", expanded=False):
        wl_input = st.text_area(
            "1行1銘柄（日本株は4桁、米国株はティッカー）",
            value="\n".join(watchlist),
            height=150,
            key="wl_edit",
        )
        if st.button("💾 保存", key="wl_save"):
            new_list = [t.strip() for t in wl_input.strip().split("\n") if t.strip()]
            save_watchlist(new_list)
            watchlist = new_list
            st.success("保存しました")
            st.rerun()

    # 市場状況と更新間隔
    mst = market_status()
    col_r1, col_r2 = st.columns([2, 2])
    with col_r1:
        auto_refresh = st.toggle("🔄 自動更新", value=False)
    with col_r2:
        interval_label = st.selectbox(
            "間隔",
            ["1分", "3分", "5分", "15分"],
            index=1,
            disabled=not auto_refresh,
            label_visibility="collapsed",
        )
    interval_map = {"1分": 60, "3分": 180, "5分": 300, "15分": 900}
    interval_sec = interval_map[interval_label]

    if auto_refresh:
        st_autorefresh(interval=interval_sec * 1000, key="dashboard_refresh")
        if not mst["any_open"]:
            st.info("💤 現在は市場閉場中です。価格データは変動しません（次の開場まで更新不要）")

    # スキャン実行
    if st.button("🔍 今すぐ更新", type="primary", use_container_width=True) or \
       "dashboard_data" not in st.session_state:
        prev_data = {r["ticker"]: r["シグナル"]
                     for r in st.session_state.get("dashboard_data", [])}
        with st.spinner(f"{len(watchlist)}銘柄をスキャン中..."):
            new_data = scan_all(watchlist)
        # シグナル変化を検出 + 自動通知
        changed_for_notif = []
        for r in new_data:
            prev_sig = prev_data.get(r["ticker"])
            r["シグナル変化"] = (prev_sig is not None and prev_sig != r["シグナル"])
            r["前回シグナル"] = prev_sig
            if r["シグナル変化"] and r["シグナル"] in ("買い", "売り"):
                changed_for_notif.append(r)
        st.session_state["dashboard_data"] = new_data

        # 買い/売りシグナルに変化があればTelegram/Slack通知
        _tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
        _tg_chat = os.getenv("TELEGRAM_CHAT_ID")
        _sl_url = os.getenv("SLACK_WEBHOOK_URL")
        if changed_for_notif and (_tg_token or _sl_url):
            for _r in changed_for_notif:
                try:
                    _price = _r["現在値"] or 0
                    _score = _r["スコア"]
                    _rsi = _r.get("RSI")
                    # 強い買いシグナル（スコア4以上）は専用の詳細通知を送る
                    if _r["シグナル"] == "買い" and _score >= 4:
                        _reasons = [_r["理由"]] if _r.get("理由") and _r["理由"] != "-" else ["複数の指標が上昇を示しています"]
                        _ed_days = None
                        try:
                            _ed_days = fetch_earnings_date(_r["ticker"]).get("days_until")
                        except Exception:
                            pass
                        send_strong_buy_alert(
                            ticker=_r["ticker"],
                            price=_price,
                            score=_score,
                            reasons=_reasons,
                            stop_loss=_price * 0.95,
                            target=_price * 1.10,
                            rsi=_rsi,
                            earnings_days=_ed_days,
                            telegram_token=_tg_token,
                            telegram_chat_id=_tg_chat,
                            slack_webhook=_sl_url,
                        )
                    else:
                        send_signal_alert(
                            ticker=_r["ticker"],
                            verdict=_r["シグナル"],
                            score=_score,
                            price=_price,
                            signals=[],
                            rsi=_rsi,
                            atr=None,
                            telegram_token=_tg_token,
                            telegram_chat_id=_tg_chat,
                            slack_webhook=_sl_url,
                        )
                except Exception:
                    pass

    rows = st.session_state.get("dashboard_data", [])

    if rows:
        # 集計バッジ
        buy_count = sum(1 for r in rows if r["シグナル"] == "買い")
        sell_count = sum(1 for r in rows if r["シグナル"] == "売り")
        watch_count = sum(1 for r in rows if r["シグナル"] == "様子見")
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("監視銘柄数", len(rows))
        b2.metric("🟢 買いシグナル", buy_count)
        b3.metric("🟡 様子見", watch_count)
        b4.metric("🔴 売りシグナル", sell_count)

        st.markdown("---")
        st.markdown("### 銘柄別シグナル一覧")
        st.caption("行をクリックした銘柄はテクニカル分析で詳細確認できます")

        # シグナル変化があれば先にまとめて表示
        changed = [r for r in rows if r.get("シグナル変化")]
        if changed:
            st.markdown("### 🚨 シグナル変化あり")
            for r in changed:
                arrow = {"買い": "🟢", "売り": "🔴", "様子見": "🟡"}.get(r["シグナル"], "⚪")
                prev = {"買い": "🟢", "売り": "🔴", "様子見": "🟡"}.get(r["前回シグナル"], "⚪")
                st.warning(f"**{r['ticker']}**　{prev} {r['前回シグナル']} → {arrow} **{r['シグナル']}**　（{r['理由']}）")
            st.markdown("---")

        for r in rows:
            sig = r["シグナル"]
            emoji = {"買い": "🟢", "売り": "🔴", "様子見": "🟡", "エラー": "⚫"}.get(sig, "⚪")
            score = r["スコア"]
            price = r["現在値"]
            chg = r["前日比(%)"]
            rsi = r["RSI"]

            chg_str = f"{chg:+.2f}%" if chg is not None else "N/A"
            chg_color = "color:#26a69a" if chg and chg >= 0 else "color:#ef5350"
            price_str = f"{price:,.2f}" if price else "N/A"
            rsi_str = f"{rsi:.0f}" if rsi else "-"
            changed_badge = " 🔔NEW" if r.get("シグナル変化") else ""
            sig_bg = {"買い": "#1e3a2f", "売り": "#3a1e1e", "様子見": "#2e2a14"}.get(sig, "#1a1d23")

            with st.container():
                c1, c2, c3, c4, c5, c6, c7 = st.columns([1.5, 1.5, 1.5, 1.5, 1, 2.5, 1])
                c1.markdown(f"**{r['ticker']}**{changed_badge}")
                c2.markdown(f"**{price_str}**")
                c3.markdown(f"<span style='{chg_color}'>{chg_str}</span>", unsafe_allow_html=True)
                c4.markdown(
                    f"<span style='background:{sig_bg};padding:2px 8px;border-radius:8px'>"
                    f"{emoji} **{sig}**</span>",
                    unsafe_allow_html=True,
                )
                c5.markdown(f"<small>RSI {rsi_str}</small>", unsafe_allow_html=True)
                c6.markdown(f"<small style='color:#999'>{r['理由']}</small>", unsafe_allow_html=True)
                if c7.button("📊 分析", key=f"goto_{r['ticker']}", help=f"{r['ticker']}をテクニカル分析で開く"):
                    st.session_state["current_ticker"] = r["ticker"]
                    st.session_state["_nav_target"] = "📊 テクニカル分析"
                    st.rerun()

            # スコアバー
            bar_pct = min(max((score + 14) / 28 * 100, 0), 100)
            bar_color = "#26a69a" if score > 0 else ("#ef5350" if score < 0 else "#ffd54f")
            st.markdown(
                f"""<div style="background:#1a1d23;border-radius:4px;height:5px;margin-bottom:6px">
                <div style="width:{bar_pct}%;background:{bar_color};height:5px;border-radius:4px"></div>
                </div>""",
                unsafe_allow_html=True,
            )

    # ── 保有銘柄の売り時チェック ──────────────────────────────────────────
    st.markdown("---")
    st.markdown("## 📊 保有銘柄の売り時チェック")
    st.caption("投資日記に記録した保有ポジションに対して、今売るべきかを自動判定します")

    from modules.data_fetcher import fetch_realtime_price
    _trades_df = get_trades(limit=10000)
    _pnl_data = calc_pnl(_trades_df)
    _positions = _pnl_data["positions"]

    if not _positions:
        st.info("📝 保有銘柄がありません。「📔 投資日記」タブで購入記録を入力すると、ここで売り時を自動チェックします。")
    else:
        for _tk, _lots in _positions.items():
            _total_qty = sum(lot[2] for lot in _lots)
            _avg_price = sum(lot[1] * lot[2] for lot in _lots) / _total_qty

            # 日記から損切り・目標価格を取得
            _buys = _trades_df[(_trades_df["ticker"].str.upper() == _tk.upper()) & (_trades_df["action"] == "買い")]
            _stop = _target = None
            if not _buys.empty:
                _last_buy = _buys.iloc[0]
                _stop = _last_buy["stop_loss"] if pd.notna(_last_buy["stop_loss"]) and _last_buy["stop_loss"] > 0 else None
                _target = _last_buy["target_price"] if pd.notna(_last_buy["target_price"]) and _last_buy["target_price"] > 0 else None

            # 現在価格を取得
            try:
                _price_info = fetch_realtime_price(_tk)
                _cur_price = _price_info.get("price")
            except Exception:
                _cur_price = None

            _pnl_pct = (_cur_price - _avg_price) / _avg_price * 100 if _cur_price else None
            _pnl_yen = (_cur_price - _avg_price) * _total_qty if _cur_price else None

            # 売り時判定
            _urgency = "🟡 様子見継続"
            _urgency_detail = "現在のポジションを維持してください。"
            _card_color = "#2e2a14"
            _border_color = "#ffd54f"

            if _cur_price and _stop and _cur_price <= _stop:
                _urgency = "🚨 損切りライン到達！今すぐ売ることを検討"
                _urgency_detail = f"損切りライン（{_stop:,.0f}円）を下回りました。ルール通り損切りを実行してください。"
                _card_color = "#3a1a1a"
                _border_color = "#ef5350"
            elif _cur_price and _target and _cur_price >= _target:
                _urgency = "🎯 目標価格達成！利確を検討"
                _urgency_detail = f"目標価格（{_target:,.0f}円）に到達しました。利確のタイミングです。"
                _card_color = "#1a3a2a"
                _border_color = "#26a69a"
            elif _pnl_pct and _pnl_pct <= -10:
                _urgency = "⚠️ 含み損 -10% 超 損切り要検討"
                _urgency_detail = f"含み損が{_pnl_pct:.1f}%に拡大。損切りラインを確認し、必要なら実行してください。"
                _card_color = "#3a2214"
                _border_color = "#ff7043"
            elif _pnl_pct and _pnl_pct >= 20:
                _urgency = "💰 含み益 +20% 超 一部利確も選択肢"
                _urgency_detail = f"含み益が{_pnl_pct:.1f}%です。利益確保のため一部売却も検討できます。"
                _card_color = "#1a3a2a"
                _border_color = "#26a69a"

            _pnl_str = f"¥{_pnl_yen:+,.0f}（{_pnl_pct:+.1f}%）" if _pnl_yen is not None else "取得中..."
            _pnl_color = "#26a69a" if (_pnl_pct or 0) >= 0 else "#ef5350"
            _price_str = f"{_cur_price:,.2f}" if _cur_price else "取得中..."

            st.markdown(
                f"""<div style="background:{_card_color};border:1px solid {_border_color};
                    border-radius:12px;padding:16px;margin-bottom:12px">
                    <div style="display:flex;justify-content:space-between;align-items:center">
                        <div>
                            <span style="font-size:1.2em;font-weight:bold">{_tk}</span>
                            <span style="color:#999;margin-left:12px;font-size:0.9em">
                                {_total_qty}株 @ 取得{_avg_price:,.0f}円 → 現在<b>{_price_str}</b>
                            </span>
                        </div>
                        <span style="color:{_pnl_color};font-weight:bold">{_pnl_str}</span>
                    </div>
                    <div style="margin-top:10px;font-size:1.05em;font-weight:bold;color:{_border_color}">{_urgency}</div>
                    <div style="color:#ccc;margin-top:4px;font-size:0.9em">{_urgency_detail}</div>
                    {'<div style="color:#888;font-size:0.85em;margin-top:6px">損切ライン: ' + f'{_stop:,.0f}円' + '</div>' if _stop else ''}
                    {'<div style="color:#888;font-size:0.85em">目標価格: ' + f'{_target:,.0f}円' + '</div>' if _target else ''}
                </div>""",
                unsafe_allow_html=True,
            )
            if st.button(f"📊 {_tk} を詳しく分析", key=f"sell_goto_{_tk}"):
                st.session_state["current_ticker"] = _tk
                st.session_state["_nav_target"] = "📊 テクニカル分析"
                st.rerun()


# ─── 銘柄スキャン ────────────────────────────────────────────────────────────
elif page == "🔭 銘柄スキャン":
    from modules.universe import UNIVERSE, get_ticker_name
    st.title("🔭 銘柄スキャン")
    st.caption("銘柄コードを知らなくても、カテゴリを選ぶだけで「今買えそうな銘柄」を自動発見できます")

    # カテゴリ選択
    cat_col1, cat_col2 = st.columns([3, 1])
    with cat_col1:
        selected_cat = st.selectbox(
            "スキャンするカテゴリを選択",
            list(UNIVERSE.keys()),
            help="スキャンしたい銘柄カテゴリを選択してください",
        )
    with cat_col2:
        st.markdown("")
        sort_by = st.selectbox("並べ替え", ["買いシグナル優先", "スコア順", "前日比順"])

    cat_info = UNIVERSE[selected_cat]
    st.info(f"📋 {cat_info['説明']}　（{len(cat_info['tickers'])}銘柄）")

    scan_btn = st.button("🔍 スキャン実行", type="primary", use_container_width=True)

    if scan_btn or f"scan_result_{selected_cat}" in st.session_state:
        if scan_btn:
            prog = st.progress(0, text="スキャン中...")
            results = []
            tickers = cat_info["tickers"]
            for i, tk in enumerate(tickers):
                prog.progress((i + 1) / len(tickers), text=f"スキャン中... {tk} ({i+1}/{len(tickers)})")
                from modules.dashboard import scan_ticker
                r = scan_ticker(tk)
                r["企業名"] = get_ticker_name(selected_cat, tk)
                results.append(r)
            prog.empty()
            st.session_state[f"scan_result_{selected_cat}"] = results

        results = st.session_state.get(f"scan_result_{selected_cat}", [])
        if not results:
            st.info("スキャン結果がありません。「スキャン実行」ボタンを押してください。")
        else:
            # ソート
            if sort_by == "買いシグナル優先":
                sig_order = {"買い": 0, "様子見": 1, "売り": 2, "エラー": 3}
                results = sorted(results, key=lambda r: (sig_order.get(r["シグナル"], 9), -r["スコア"]))
            elif sort_by == "スコア順":
                results = sorted(results, key=lambda r: -r["スコア"])
            elif sort_by == "前日比順":
                results = sorted(results, key=lambda r: -(r["前日比(%)"] or 0))

            # 集計
            buy_n = sum(1 for r in results if r["シグナル"] == "買い")
            watch_n = sum(1 for r in results if r["シグナル"] == "様子見")
            sell_n = sum(1 for r in results if r["シグナル"] == "売り")
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("スキャン銘柄数", len(results))
            sc2.metric("🟢 買い候補", buy_n)
            sc3.metric("🟡 様子見", watch_n)
            sc4.metric("🔴 売りシグナル", sell_n)

            if buy_n == 0:
                st.warning("現在このカテゴリに買いシグナルが出ている銘柄はありません。別カテゴリを試すか、時間をおいて再スキャンしてください。")

            st.markdown("---")
            st.markdown("### スキャン結果一覧")
            st.caption("「📊 分析」ボタンで詳細なテクニカル分析を確認できます")

            for r in results:
                sig = r["シグナル"]
                emoji = {"買い": "🟢", "売り": "🔴", "様子見": "🟡", "エラー": "⚫"}.get(sig, "⚪")
                sig_bg = {"買い": "#1e3a2f", "売り": "#3a1e1e", "様子見": "#2a2a1a"}.get(sig, "#1a1d23")
                border = {"買い": "#26a69a", "売り": "#ef5350", "様子見": "#888"}.get(sig, "#444")
                price = r["現在値"]
                chg = r["前日比(%)"]
                chg_str = f"{chg:+.2f}%" if chg is not None else "N/A"
                chg_color = "#26a69a" if (chg or 0) >= 0 else "#ef5350"
                rsi = r["RSI"]
                score = r["スコア"]

                # スコアバー（±14範囲）
                bar_pct = min(max((score + 14) / 28 * 100, 0), 100)
                bar_color = "#26a69a" if score > 0 else ("#ef5350" if score < 0 else "#ffd54f")

                col_name, col_price, col_chg, col_sig, col_rsi, col_reason, col_btn = st.columns([1.8, 1.4, 1.2, 1.5, 0.9, 3, 1])
                col_name.markdown(f"**{r['ticker']}**  \n<small style='color:#999'>{r['企業名']}</small>", unsafe_allow_html=True)
                col_price.markdown(f"**{price:,.2f}**" if price else "N/A")
                col_chg.markdown(f"<span style='color:{chg_color}'>{chg_str}</span>", unsafe_allow_html=True)
                col_sig.markdown(
                    f"<span style='background:{sig_bg};border:1px solid {border};padding:2px 8px;border-radius:8px'>{emoji} **{sig}**</span>",
                    unsafe_allow_html=True,
                )
                col_rsi.markdown(f"<small>RSI {rsi:.0f}</small>" if rsi else "<small>-</small>", unsafe_allow_html=True)
                col_reason.markdown(f"<small style='color:#999'>{r['理由']}</small>", unsafe_allow_html=True)

                if col_btn.button("📊 分析", key=f"scan_goto_{r['ticker']}", help="テクニカル分析で詳細確認"):
                    st.session_state["current_ticker"] = r["ticker"]
                    st.session_state["_nav_target"] = "📊 テクニカル分析"
                    st.rerun()

                st.markdown(
                    f'<div style="background:#1a1d23;border-radius:3px;height:4px;margin-bottom:8px">'
                    f'<div style="width:{bar_pct}%;background:{bar_color};height:4px;border-radius:3px"></div></div>',
                    unsafe_allow_html=True,
                )

            # 買い候補まとめ
            buy_results = [r for r in results if r["シグナル"] == "買い"]
            if buy_results:
                st.markdown("---")
                st.markdown("### 🟢 今すぐ検討できる買い候補")
                st.caption("複数の指標が上昇を示している銘柄です。詳細分析の上で判断してください。")
                for r in buy_results:
                    st.markdown(
                        f"- **{r['ticker']}**（{r['企業名']}）　現在値 {r['現在値']:,.2f} / "
                        f"スコア {r['スコア']:+d} / {r['理由']}"
                    )


# ─── テクニカル分析 ───────────────────────────────────────────────────────────
elif page == "📊 テクニカル分析":
    st.title("📊 テクニカル分析")

    watchlist = load_watchlist()

    # ── 取引モード選択 ────────────────────────────────────────────────────
    MODE_CONFIG = {
        "📅 中長期（日足）":   {"interval": "1d",  "periods": ["6mo", "1y", "2y"],         "period_labels": {"6mo": "6ヶ月", "1y": "1年", "2y": "2年"},           "sma_default": (25, 75),  "period_default": 0},
        "📈 スイング（1時間足）": {"interval": "1h",  "periods": ["5d", "14d", "30d", "60d"], "period_labels": {"5d": "5日", "14d": "2週間", "30d": "1ヶ月", "60d": "2ヶ月"}, "sma_default": (9, 21),   "period_default": 1},
        "⚡ デイトレ（5分足）": {"interval": "5m",  "periods": ["1d", "3d", "5d"],          "period_labels": {"1d": "今日", "3d": "3日間", "5d": "5日間"},         "sma_default": (5, 20),   "period_default": 1},
    }

    mode = st.radio(
        "取引モード",
        list(MODE_CONFIG.keys()),
        horizontal=True,
        help="デイトレ=当日〜数日の短期売買 / スイング=数日〜数週間 / 中長期=数ヶ月以上",
    )
    cfg = MODE_CONFIG[mode]

    if mode == "⚡ デイトレ（5分足）":
        st.info("⚡ **デイトレモード**: 5分足チャートを表示します。当日〜5日間のデータを使用。VWAP（白点線）が特に重要な指標になります。")
    elif mode == "📈 スイング（1時間足）":
        st.info("📈 **スイングモード**: 1時間足チャートを表示します。数日〜数週間のトレードに適しています。")

    # ── 銘柄はサイドバーのグローバル選択を使用 ────────────────────────
    ticker = st.session_state.get("current_ticker", "")
    _ta_col1, _ta_col2 = st.columns([3, 1])
    with _ta_col1:
        if ticker:
            st.success(f"📌 分析銘柄: **{ticker}**　　← サイドバーで変更できます")
        else:
            st.warning("サイドバーで銘柄を選択してください")
    with _ta_col2:
        period = st.selectbox(
            "期間",
            cfg["periods"],
            index=cfg["period_default"],
            format_func=lambda x: cfg["period_labels"].get(x, x),
        )

    # 詳細設定（折りたたみ）
    sma_short, sma_long = cfg["sma_default"]
    with st.expander("⚙️ 詳細設定（移動平均の期間など）", expanded=False):
        c3, c4 = st.columns(2)
        sma_short = c3.number_input("短期MA", value=cfg["sma_default"][0], min_value=3, max_value=100, step=1)
        sma_long = c4.number_input("長期MA", value=cfg["sma_default"][1], min_value=5, max_value=300, step=1)

    analyze_btn = st.button("🔍 分析する", type="primary", use_container_width=True)

    if analyze_btn and ticker:
        with st.spinner("データ取得中..."):
            try:
                df = fetch_ohlcv(ticker, period=period, interval=cfg["interval"])
                df = compute_all(df, sma_short=sma_short, sma_long=sma_long)
                signals = evaluate_signals(df, sma_short=sma_short, sma_long=sma_long)
                verdict, score = overall_signal(signals, df=df, sma_long=sma_long)
            except Exception as e:
                st.error(f"データ取得エラー: {e}")
                st.stop()

        rsi_val = df["RSI"].dropna().iloc[-1] if "RSI" in df.columns else None
        atr_val = df["ATR"].dropna().iloc[-1] if "ATR" in df.columns else None
        close_val = df["Close"].iloc[-1]
        prev_val = df["Close"].iloc[-2] if len(df) >= 2 else close_val
        chg_pct = (close_val - prev_val) / prev_val * 100

        # 決算日を取得（バックグラウンドで）
        try:
            _earnings = fetch_earnings_date(ticker)
        except Exception:
            _earnings = {"date": None, "days_until": None}

        # ── 決算接近警告（最優先で表示） ──────────────────────
        if _earnings.get("days_until") is not None and _earnings["days_until"] <= 14:
            _ed = _earnings["days_until"]
            _color = "#ef5350" if _ed <= 7 else "#ff7043"
            st.markdown(
                f"""<div style="background:{_color}22;border:2px solid {_color};
                    border-radius:10px;padding:12px;margin-bottom:12px;text-align:center">
                    ⚠️ <b>決算発表まであと{_ed}日（{_earnings['date']}）</b><br>
                    <span style="color:#ccc;font-size:0.9em">
                    決算前後は予測困難な急変動が起きやすいため、ポジションを小さくするか見送りを検討してください</span>
                </div>""",
                unsafe_allow_html=True,
            )

        # ── 大きなシグナル表示 ──────────────────────────────
        sig_color = {"買い": "#26a69a", "売り": "#ef5350", "様子見": "#ffd54f"}.get(verdict, "#888")
        sig_emoji = {"買い": "🟢", "売り": "🔴", "様子見": "🟡"}.get(verdict, "⚪")
        sig_msg = {
            "買い": "買いのタイミングです",
            "売り": "売りを検討してください",
            "様子見": "まだ動かず待ちましょう",
        }.get(verdict, "")

        # シンプルな理由（上位2つ）
        top2 = sorted(signals, key=lambda x: abs(x["スコア"]), reverse=True)[:2]
        def _reason_span(s):
            bg = "#1e3a2f" if s["スコア"] > 0 else "#3a1e1e"
            icon = "✅" if s["スコア"] > 0 else "⚠️"
            name = s["指標"].split("(")[0].strip()
            return f"<span style='background:{bg};padding:2px 8px;border-radius:12px;font-size:0.85em'>{icon} {name}: {s['判定']}</span>"
        reasons_html = "　".join(_reason_span(s) for s in top2)

        _detail = get_signal_detail(signals, verdict, df=df, sma_long=sma_long)
        _grade = _detail["grade"]
        _grade_color = _detail["grade_color"]
        _conf = _detail["confidence"]
        _wpct = _detail["weighted_pct"]
        _conf_color = "#26a69a" if _conf >= 70 else ("#ffd54f" if _conf >= 50 else "#ef5350")

        # 横ばい・下落フィルター発動時の警告メッセージ
        _filter_msg = ""
        if _detail.get("adx_down"):
            _filter_msg = "<div style='color:#ef5350;font-size:0.85em;margin-top:6px'>⛔ ADXが強い下落トレンドを確認 → 買いシグナルは封鎖中</div>"
        elif _detail.get("sideways"):
            _filter_msg = "<div style='color:#ffd54f;font-size:0.85em;margin-top:6px'>⚠️ 横ばい相場（ADX低水準）→ シグナルの信頼性が低下中</div>"

        st.markdown(
            f"""<div style="background:{sig_color}22;border:2px solid {sig_color};
                border-radius:16px;padding:24px;text-align:center;margin-bottom:16px">
                <div style="font-size:3em">{sig_emoji}</div>
                <div style="font-size:2em;font-weight:bold;color:{sig_color}">{verdict}</div>
                <div style="font-size:1.1em;color:#ccc;margin-top:4px">{sig_msg}</div>
                <div style="margin-top:10px;display:flex;justify-content:center;gap:10px;flex-wrap:wrap">
                  {"<span style='background:" + _grade_color + "33;border:1px solid " + _grade_color + ";padding:3px 12px;border-radius:20px;font-size:0.9em;color:" + _grade_color + "'>" + _grade + "</span>" if _grade else ""}
                  <span style="background:{_conf_color}33;border:1px solid {_conf_color};padding:3px 12px;border-radius:20px;font-size:0.9em;color:{_conf_color}">
                    一致率 {_conf}%
                  </span>
                  <span style="background:#33333366;border:1px solid #555;padding:3px 12px;border-radius:20px;font-size:0.9em;color:#aaa">
                    加重スコア {_wpct:+.0f}%
                  </span>
                </div>
                {_filter_msg}
                <div style="margin-top:12px">{reasons_html}</div>
            </div>""",
            unsafe_allow_html=True,
        )

        col_price, col_chg, col_rsi, col_atr = st.columns(4)
        col_price.metric("現在値", f"{close_val:,.2f}")
        col_chg.metric("前日比", f"{chg_pct:+.2f}%")
        col_rsi.metric("RSI", f"{rsi_val:.1f}" if rsi_val else "N/A",
                       help="30以下=売られすぎ（買い候補）/ 70以上=買われすぎ（売り候補）")
        col_atr.metric("ATR（値幅目安）", f"{atr_val:.2f}" if atr_val else "N/A",
                       help="1日の平均的な値動き幅。損切り幅の基準に使います")

        # チャート（マウスホイール・ピンチでズーム可能）
        fig = build_main_chart(df, ticker, sma_short=sma_short, sma_long=sma_long)
        st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True})

        # ── チャートの見方ガイド ──────────────────────────────
        with st.expander("📖 チャートの見方（各線・指標の説明）", expanded=False):
            st.markdown("""
#### 🕯️ ローソク足（上段メイン）
| 色 | 意味 |
|----|------|
| 🟩 緑のローソク | 前日より株価が**上がった**日 |
| 🟥 赤のローソク | 前日より株価が**下がった**日 |
| ローソクの上下のヒゲ | その日の最高値・最安値の範囲 |

#### 📈 移動平均線（上段）
| 線 | 意味 |
|----|------|
| 🟠 オレンジ線（SMA25） | 過去**25日間**の平均株価。短期トレンド |
| 🔵 青線（SMA75） | 過去**75日間**の平均株価。長期トレンド |
| ✅ オレンジが青を下から上に抜いた（ゴールデンクロス） | **買いサイン** |
| ⚠️ オレンジが青を上から下に抜いた（デッドクロス） | **売りサイン** |

#### 🌥️ 雲（薄い緑・赤の帯）
一目均衡表の「雲」です。
- 株価が**雲の上** → 強い上昇トレンド
- 株価が**雲の下** → 弱い下落トレンド
- 株価が**雲の中** → 方向感なし・様子見

#### 📊 ボリンジャーバンド（薄い青の帯）
平均株価を中心に、値動きの範囲を示します。
- 株価が**帯の下限に触れた** → 売られすぎ・反発の可能性
- 株価が**帯の上限に触れた** → 買われすぎ・反落の可能性

---

#### 📉 出来高 / OBV（2段目）
| | 意味 |
|----|------|
| 棒グラフ（出来高） | その日に売買された株の量。多いほど注目されている |
| OBVライン | 出来高の積み上げ。大口投資家の動きを反映 |

#### 📉 MACD（3段目）
トレンドの方向と勢いを見る指標。
- **MACDライン（紫）が シグナルライン（橙の点線）を下から上に抜けた** → 買いサイン
- **上から下に抜けた** → 売りサイン
- ヒストグラム（棒）がプラス圏 → 上昇の勢い、マイナス圏 → 下落の勢い

#### 📉 RSI・ストキャスティクス（4段目）
売られすぎ・買われすぎを0〜100で表示。
- **RSIが30以下** → 売られすぎ（買いの候補）
- **RSIが70以上** → 買われすぎ（売りの候補）
- 緑の破線（30）と赤の破線（70）が目安
""")

        # ── 投資プラン（初心者向け具体的提案） ─────────────────
        plan = generate_action_plan(df, signals, verdict, ticker)

        st.markdown("### 📋 具体的な投資プラン")
        st.markdown(
            f"""<div style="background:#1a1d23;border-radius:12px;padding:20px;margin-bottom:16px">
            <div style="font-size:1.2em;font-weight:bold;margin-bottom:12px">{plan['timing']}</div>
            <div style="color:#ccc;margin-bottom:16px">{plan['timing_detail']}</div>
            </div>""",
            unsafe_allow_html=True,
        )

        pc1, pc2, pc3, pc4 = st.columns(4)
        pc1.metric("📍 現在値（エントリー目安）", f"{plan['entry_price']:,.1f}",
                   help="今この価格で買うとしたら")
        pc2.metric("🎯 利確ライン", f"{plan['target1']:,.1f}",
                   help="ここまで上がったら売ることを検討",
                   delta=f"+{plan['target1']-plan['entry_price']:,.0f}")
        pc3.metric("🛑 損切りライン", f"{plan['stop_loss']:,.1f}",
                   help="ここを下回ったら迷わず売る",
                   delta=f"{plan['stop_loss']-plan['entry_price']:,.0f}",
                   delta_color="inverse")
        rr_color = "✅" if plan["risk_reward"] >= 2 else ("⚠️" if plan["risk_reward"] >= 1 else "❌")
        pc4.metric(f"リスクリワード比 {rr_color}", f"1 : {plan['risk_reward']:.1f}",
                   help="2以上が理想。損1に対してどれだけ利益が見込めるか")

        # 様子見のときは「次にどうなったら動くか」を表示
        if verdict == "様子見":
            st.info(
                f"**⏳ 今は待つ時期です。次のサインが出たら行動しましょう**\n\n"
                f"🟢 **買いを検討するタイミング：** {plan['buy_trigger']}\n\n"
                f"🔴 **売り・見通しを検討するタイミング：** {plan['sell_trigger']}"
            )
            st.caption("💡 「様子見」は最も多い判定です。相場の70〜80%の時間は様子見が正解です。焦らず待つことも立派な投資判断です。")

        # ── 決算日（メトリクス近くにも表示） ──────────────────────
        if _earnings.get("date") and _earnings.get("days_until") is not None and _earnings["days_until"] > 14:
            st.caption(f"📅 次回決算発表予定: {_earnings['date']}（あと{_earnings['days_until']}日）")

        # ── リスク評価 + ML統合スコア ───────────────────────────────
        st.markdown("---")
        st.markdown("### 🛡️ リスク評価 ＆ ML予測（自動）")
        st.caption("エントリー前に必ず確認してください。リスクが高い場合は通知も自動でスキップされます。")

        _risk = assess_signal_risk(
            ticker, df,
            earnings_days=_earnings.get("days_until"),
        )
        _ml_sig = ml_score_signal(df)

        _rc1, _rc2, _rc3 = st.columns(3)

        # リスクレベル
        _rl_color = {"LOW": "#26a69a", "MEDIUM": "#ffd54f", "HIGH": "#ef5350"}.get(_risk["risk_level"], "#888")
        _rl_label = {"LOW": "🟢 LOW（低リスク）", "MEDIUM": "🟡 MEDIUM（中リスク）", "HIGH": "🔴 HIGH（高リスク）"}.get(_risk["risk_level"], _risk["risk_level"])
        with _rc1:
            st.markdown(
                f"""<div style='border:2px solid {_rl_color};border-radius:10px;padding:14px;text-align:center'>
                <div style='font-size:12px;color:#aaa'>リスクレベル</div>
                <div style='font-size:1.2em;font-weight:bold;color:{_rl_color}'>{_rl_label}</div>
                </div>""",
                unsafe_allow_html=True,
            )

        # エントリー上限
        _el_pct = _risk.get("entry_limit_pct", 0)
        _entry_limit = plan["entry_price"] * (1 + _el_pct / 100) if _el_pct > 0 else None
        with _rc2:
            if _risk["should_skip"]:
                st.markdown(
                    """<div style='border:2px solid #ef5350;border-radius:10px;padding:14px;text-align:center'>
                    <div style='font-size:12px;color:#aaa'>エントリー判定</div>
                    <div style='font-size:1.2em;font-weight:bold;color:#ef5350'>🚫 見送り推奨</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
            elif _entry_limit:
                st.markdown(
                    f"""<div style='border:2px solid #26a69a;border-radius:10px;padding:14px;text-align:center'>
                    <div style='font-size:12px;color:#aaa'>エントリー上限価格</div>
                    <div style='font-size:1.2em;font-weight:bold;color:#26a69a'>{_entry_limit:,.1f}円以下</div>
                    <div style='font-size:11px;color:#aaa'>現在値+{_el_pct:.0f}%以内なら買いOK</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    """<div style='border:1px solid #555;border-radius:10px;padding:14px;text-align:center'>
                    <div style='font-size:12px;color:#aaa'>エントリー上限価格</div>
                    <div style='font-size:1.1em;color:#888'>設定なし</div>
                    </div>""",
                    unsafe_allow_html=True,
                )

        # ML予測
        with _rc3:
            if _ml_sig:
                _mc = {"上昇": "#26a69a", "下落": "#ef5350"}.get(
                    "上昇" if "上昇" in _ml_sig["judge"] else ("下落" if "下落" in _ml_sig["judge"] else "中"), "#ffd54f"
                )
                st.markdown(
                    f"""<div style='border:2px solid {_mc};border-radius:10px;padding:14px;text-align:center'>
                    <div style='font-size:12px;color:#aaa'>ML予測（10日後）</div>
                    <div style='font-size:1.1em;font-weight:bold;color:{_mc}'>{_ml_sig['judge']}</div>
                    <div style='font-size:11px;color:#aaa'>上昇確率 {_ml_sig['up_probability']:.0f}% / 信頼度 {_ml_sig['confidence']:.0f}%</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    """<div style='border:1px solid #555;border-radius:10px;padding:14px;text-align:center'>
                    <div style='font-size:12px;color:#aaa'>ML予測</div>
                    <div style='font-size:1.1em;color:#888'>データ不足</div>
                    </div>""",
                    unsafe_allow_html=True,
                )

        # リスク要因の詳細
        if _risk["reasons"]:
            with st.expander(f"⚠️ リスク要因（{len(_risk['reasons'])}件）"):
                for r in _risk["reasons"]:
                    st.warning(r)
        else:
            st.caption("✅ 特段のリスク要因は検出されませんでした")

        # ── ポジションサイズ計算 ────────────────────────────────────
        st.markdown("---")
        st.markdown("### 🧮 ポジションサイズ計算（何株買えばいいか）")
        st.caption("リスク管理の基本: 1回の取引で資金の何%を失っても大丈夫かを先に決め、そこから株数を逆算します")

        _ps_col1, _ps_col2, _ps_col3 = st.columns(3)
        with _ps_col1:
            _total_funds = st.number_input(
                "💰 投資に使える総資金（円）",
                value=1_000_000, min_value=10_000, step=100_000,
                help="口座残高全体ではなく、株式投資に充てる金額",
                key="ps_funds",
            )
        with _ps_col2:
            _risk_pct = st.slider(
                "⚠️ 1回の取引で許容する損失（%）",
                min_value=0.5, max_value=5.0, value=1.0, step=0.5,
                help="プロは1〜2%が標準。初心者は1%以下を推奨",
                key="ps_risk",
            )
        with _ps_col3:
            _stop_price = st.number_input(
                "🛑 損切りライン（円）",
                value=float(plan["stop_loss"]),
                min_value=1.0, step=1.0,
                help="ここを割ったら必ず売る価格",
                key="ps_stop",
            )

        _max_loss_yen = _total_funds * (_risk_pct / 100)
        _loss_per_share = close_val - _stop_price
        if _loss_per_share > 0:
            _recommend_shares = int(_max_loss_yen / _loss_per_share)
            _invest_yen = _recommend_shares * close_val
            _invest_pct = _invest_yen / _total_funds * 100
            _p1, _p2, _p3, _p4 = st.columns(4)
            _p1.metric("📊 推奨購入株数", f"{_recommend_shares:,} 株",
                       help="損切りライン×株数 = 許容損失額になる株数")
            _p2.metric("💴 投資金額", f"¥{_invest_yen:,.0f}",
                       delta=f"資金の{_invest_pct:.1f}%",
                       help="推奨株数 × 現在値")
            _p3.metric("📉 最大損失額", f"¥{_max_loss_yen:,.0f}",
                       delta=f"-{_risk_pct}%",
                       delta_color="inverse",
                       help="損切りラインで売った場合の損失")
            _p4.metric("🎯 利確時の利益（目標1）", f"¥{_recommend_shares * (plan['target1'] - close_val):,.0f}",
                       delta=f"リワード×{plan['risk_reward']:.1f}",
                       help="利確ラインで売った場合の利益")
            if _invest_pct > 20:
                st.warning(f"⚠️ 投資金額が総資金の{_invest_pct:.0f}%になります。集中しすぎに注意してください（1銘柄は10〜20%以内が目安）。")
        else:
            st.info("損切りラインが現在値より高いか、現在値と同じです。損切りラインを現在値より低く設定してください。")

        # ── シグナル的中率（過去データから算出） ─────────────────────
        st.markdown("---")
        with st.expander("📊 シグナル的中率（過去データでどのくらい当たったか）", expanded=False):
            st.caption("過去のデータで「買い条件が揃った日の翌5/10/20日後に上昇していた確率」を算出します")
            _acc = calc_signal_accuracy(df, sma_short=sma_short, sma_long=sma_long)
            if _acc:
                _a1, _a2, _a3, _a4 = st.columns(4)
                _a1.metric("過去のシグナル発生回数", f"{_acc['signal_count']} 回",
                           help="分析期間中に買い条件が揃った回数")
                if _acc["win_rate_5d"] is not None:
                    _a2.metric("5日後の上昇確率", f"{_acc['win_rate_5d']:.0f}%",
                               help="買いシグナル後5営業日で株価が上昇した割合")
                if _acc["win_rate_10d"] is not None:
                    _a3.metric("10日後の上昇確率", f"{_acc['win_rate_10d']:.0f}%",
                               help="買いシグナル後10営業日で株価が上昇した割合")
                if _acc["win_rate_20d"] is not None:
                    _a4.metric("20日後の上昇確率", f"{_acc['win_rate_20d']:.0f}%",
                               help="買いシグナル後20営業日で株価が上昇した割合")
                _rates = [v for v in [_acc["win_rate_10d"], _acc["win_rate_20d"]] if v is not None]
                _best = max(_rates) if _rates else 0
                if _best >= 60:
                    st.success(f"✅ この銘柄はシグナルの信頼性が高め（10日後的中率{_acc['win_rate_10d']:.0f}%）")
                elif _best >= 50:
                    st.info(f"🟡 シグナルの信頼性は中程度。他の指標との組み合わせで判断してください。")
                else:
                    st.warning(f"⚠️ シグナルの的中率が低め。この銘柄への適用には注意が必要です。")
                st.caption("⚠️ 過去の成績は将来を保証しません。あくまで参考値です。")
            else:
                st.info("的中率の計算に必要なデータが不足しています（最低80日分のデータが必要）")

        # ── マルチタイムフレーム分析 ─────────────────────────────────
        st.markdown("---")
        with st.expander("🕐 マルチタイムフレーム分析（週足・日足・1時間足の一致確認）", expanded=False):
            st.caption("3つのタイムフレームが「買い」で一致するほど信頼性が高い。日足だけで判断するのは危険。")
            if st.button("🔍 マルチタイムフレームを分析（数秒かかります）", key="mtf_btn"):
                with st.spinner("3つの時間足でデータ取得・分析中..."):
                    st.session_state[f"mtf_{ticker}"] = multi_timeframe_signal(
                        ticker, sma_short=sma_short, sma_long=sma_long
                    )
            _mtf = st.session_state.get(f"mtf_{ticker}")
            if _mtf:
                _mtf_cols = st.columns(3)
                _agree_count = 0
                for i, row in enumerate(_mtf):
                    _vc = {"買い": "#26a69a", "売り": "#ef5350", "様子見": "#ffd54f"}.get(row["verdict"], "#888")
                    _ve = {"買い": "🟢", "売り": "🔴", "様子見": "🟡"}.get(row["verdict"], "⚪")
                    if row["verdict"] == "買い":
                        _agree_count += 1
                    with _mtf_cols[i]:
                        st.markdown(
                            f"""<div style="background:{_vc}22;border:2px solid {_vc};
                                border-radius:10px;padding:14px;text-align:center">
                                <div style="font-size:0.85em;color:#999">{row['timeframe']}</div>
                                <div style="font-size:1.6em">{_ve}</div>
                                <div style="font-weight:bold;color:{_vc}">{row['verdict']}</div>
                                <div style="font-size:0.85em;color:#aaa;margin-top:4px">
                                    スコア {row['score']:+d} / RSI {row['rsi'] or '-'} / {row['trend']}トレンド
                                </div>
                            </div>""",
                            unsafe_allow_html=True,
                        )
                st.markdown("")
                if _agree_count == 3:
                    st.success("✅ **3時間足すべて「買い」一致** → 最も信頼性の高いエントリーサイン")
                elif _agree_count == 2:
                    st.info("🟡 **2時間足で一致** → 信頼性は中程度。ズレている時間足の方向に注意")
                elif _agree_count == 0 and all(r["verdict"] == "売り" for r in _mtf):
                    st.error("🔴 **全時間足が「売り」** → エントリーは見送りを強く推奨")
                else:
                    st.warning("⚠️ **時間足間でシグナルが不一致** → エントリーは慎重に。一致するまで待つのが安全")
            else:
                st.info("上のボタンを押すとマルチタイムフレーム分析を実行します。")

        # ── すでに保有している方向けの継続判定 ────────────────────
        st.markdown("---")
        st.markdown("### 📦 すでに保有中の方へ：今売るべき？まだ持つべき？")
        st.caption("新規エントリーの判定とは別に、保有継続・利確・損切りを専用ロジックで判定します")

        hold = evaluate_hold_signal(df, signals, verdict, sma_long=sma_long)

        st.markdown(
            f"""<div style="background:{hold['color']}22;border:2px solid {hold['color']};
                border-radius:14px;padding:20px;margin-bottom:12px">
                <div style="font-size:1.6em;font-weight:bold;color:{hold['color']}">{hold['hold_verdict']}</div>
                <div style="color:#ccc;margin-top:6px;font-size:1.0em">{hold['hold_detail']}</div>
            </div>""",
            unsafe_allow_html=True,
        )

        # 判定根拠
        with st.expander("📋 判定根拠を見る（なぜそう判断したか）", expanded=True):
            for r in hold["reasons"]:
                st.markdown(f"- {r}")

        hc1, hc2, hc3, hc4 = st.columns(4)
        hc1.metric(
            "直近高値まで",
            f"{hold['dist_to_resistance_pct']:.1f}%",
            help=f"直近60日の高値 {hold['resistance']:,.0f} まであと何%か。5%以上残っていれば上値余地あり",
        )
        hc2.metric(
            "次の目標価格",
            f"{hold['next_target']:,.0f}",
            delta=f"+{hold['next_target'] - close_val:,.0f}",
            help="ATR×3の水準。トレンドが続いた場合の次の利確候補",
        )
        hc3.metric(
            "保有継続の損切りライン",
            f"{hold['hold_stop']:,.0f}",
            delta=f"{hold['hold_stop'] - close_val:,.0f}",
            delta_color="inverse",
            help="この価格を終値で下回ったら、トレンド崩壊と見て撤退を検討",
        )
        hc4.metric(
            "現在のRSI",
            f"{hold['rsi']:.0f}",
            help="70超=買われすぎ（利確圏）/ 50〜70=適正（保有継続） / 50未満=弱め（要注意）",
        )

        st.caption(
            "⚠️ **注意:** この判定はテクニカル指標のみに基づきます。決算発表・地政学リスク等のファンダメンタル要因は含みません。"
            "最終判断は必ずご自身で行ってください。"
        )

        # ── 下落トレンド中の「いつ買えるか」監視判定 ────────────────
        st.markdown("---")
        st.markdown("### 📡 これから買いたい方へ：今が買いのタイミング？まだ早い？")
        st.caption("下落中の銘柄を「いつ買えるか」監視しているときに使ってください。底打ちの条件が揃っているかを判定します。")

        watch = evaluate_watch_signal(df, sma_long=sma_long)

        st.markdown(
            f"""<div style="background:{watch['color']}22;border:2px solid {watch['color']};
                border-radius:14px;padding:20px;margin-bottom:12px">
                <div style="font-size:1.5em;font-weight:bold;color:{watch['color']}">{watch['verdict']}</div>
                <div style="color:#ccc;margin-top:6px">{watch['detail']}</div>
                <div style="background:rgba(0,0,0,0.3);border-radius:8px;padding:10px;margin-top:10px;color:#ffd54f">
                    💡 <b>次のアクション:</b> {watch['action']}
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

        wc1, wc2, wc3 = st.columns(3)
        wc1.metric("RSI（売られすぎ判定）", f"{watch['rsi']:.0f}",
                   help="30以下=売られすぎ圏（反発しやすい）/ 40以下=底値圏に近づいている")
        wc2.metric("直近安値（サポート）", f"{watch['support']:,.0f}",
                   help="この価格より下に損切りを設定する。ここを維持できるかが鍵")
        wc3.metric("損切り候補ライン", f"{watch['stop_loss']:,.0f}",
                   delta=f"{watch['stop_loss'] - close_val:,.0f}",
                   delta_color="inverse",
                   help="エントリーした場合の損切り候補（直近安値の3%下）")

        with st.expander("📋 エントリー条件チェックリスト（何が揃って何が足りないか）", expanded=True):
            if watch["conditions_met"]:
                st.markdown("**✅ 揃っている条件**")
                for c in watch["conditions_met"]:
                    st.markdown(f"- {c}")
            if watch["conditions_missing"]:
                st.markdown("**⏳ まだ揃っていない条件**")
                for c in watch["conditions_missing"]:
                    st.markdown(f"- {c}")

        # ── ブレイクアウト・出来高急増の検出 ──────────────────────
        bo = detect_breakout(df)
        if bo and bo["alerts"]:
            st.markdown("---")
            st.markdown("### ⚡ 特殊シグナル検出")
            for alert in bo["alerts"]:
                reliability = "（出来高の裏付けあり ✅）" if alert.get("reliable") else "（出来高不足 → 信頼性低）"
                st.markdown(
                    f"""<div style="background:{alert['color']}22;border:2px solid {alert['color']};
                        border-radius:10px;padding:14px;margin-bottom:8px">
                        <div style="font-size:1.2em;font-weight:bold;color:{alert['color']}">
                            {alert['emoji']} {alert['title']} {reliability if alert['type']=='breakout_up' else ''}
                        </div>
                        <div style="color:#ccc;margin-top:6px">{alert['detail']}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )

        # 初心者モードでは指標テーブルを折りたたみ
        from modules.signals import INDICATOR_WEIGHTS
        def _make_sig_df(sigs):
            rows = []
            for s in sigs:
                w = INDICATOR_WEIGHTS.get(s["指標"], 1.0)
                star = "★★★" if w >= 3 else ("★★☆" if w >= 2 else "★☆☆")
                rows.append({
                    "重要度": star,
                    "指標": s["指標"],
                    "値": s["値"],
                    "判定": ("🟢 " if s["スコア"] > 0 else ("🔴 " if s["スコア"] < 0 else "🟡 ")) + s["判定"],
                    "加重スコア": f"{s['スコア'] * w:+.0f}",
                })
            return pd.DataFrame(rows)

        if st.session_state.get("beginner_mode", True):
            with st.expander("📊 各指標の詳細データ（上級者向け）", expanded=False):
                st.dataframe(_make_sig_df(signals), use_container_width=True, hide_index=True)
                st.caption("★★★=最重要(×3)　★★☆=重要(×2)　★☆☆=補助(×1)")
                if atr_val:
                    st.markdown("**損切りラインの詳細（ATRベース）**")
                    risk = get_risk_metrics(ticker, df["Close"].iloc[-1], atr_val)
                    r1, r2, r3, r4 = st.columns(4)
                    r1.metric("現在値", f"{risk['現在値']:.2f}")
                    r2.metric("損切り×1", f"{risk['損切りライン (ATR×1)']:.2f}",
                              f"-{risk['リスク率 (ATR×1)']:.1f}%", delta_color="inverse")
                    r3.metric("損切り×2", f"{risk['損切りライン (ATR×2)']:.2f}",
                              f"-{risk['リスク率 (ATR×2)']:.1f}%", delta_color="inverse")
                    r4.metric("ATR", f"{risk['ATR']:.2f}")
        else:
            st.markdown("### 指標別シグナル一覧")
            st.dataframe(_make_sig_df(signals), use_container_width=True, hide_index=True)
            st.caption("★★★=最重要(×3)　★★☆=重要(×2)　★☆☆=補助(×1)")
            if atr_val:
                st.markdown("### 損切りライン（ATRベース）")
                risk = get_risk_metrics(ticker, df["Close"].iloc[-1], atr_val)
                r1, r2, r3, r4 = st.columns(4)
                r1.metric("現在値", f"{risk['現在値']:.2f}")
                r2.metric("損切りライン (×1 ATR)", f"{risk['損切りライン (ATR×1)']:.2f}",
                          f"-{risk['リスク率 (ATR×1)']:.1f}%", delta_color="inverse")
                r3.metric("損切りライン (×2 ATR)", f"{risk['損切りライン (ATR×2)']:.2f}",
                          f"-{risk['リスク率 (ATR×2)']:.1f}%", delta_color="inverse")
                r4.metric("ATR", f"{risk['ATR']:.2f}")

        # ── 金融工学リスク分析 ──────────────────────────────────
        st.markdown("---")
        st.markdown("### 📐 金融工学リスク分析")
        st.caption("価格予測ではなく「リスクの大きさ」を数値化します。エントリー判断とポジションサイズ決定に使ってください。")

        from modules.risk_metrics import calc_var, monte_carlo, volatility_regime
        from modules.charts import build_montecarlo_chart, build_volatility_chart

        _var = calc_var(df)
        _vol = volatility_regime(df)
        _mc  = monte_carlo(df, n_simulations=300, horizon=30)

        # ボラティリティレジーム（最優先で表示）
        if _vol:
            st.markdown("#### 🌡️ ボラティリティレジーム（今は動きやすい時期か？）")
            st.markdown(
                f"""<div style="background:{_vol['color']}22;border:2px solid {_vol['color']};
                    border-radius:12px;padding:16px;margin-bottom:8px">
                    <div style="font-size:1.4em;font-weight:bold;color:{_vol['color']}">
                        {_vol['emoji']} {_vol['regime']}
                    </div>
                    <div style="color:#ccc;margin-top:6px">{_vol['advice']}</div>
                    <div style="background:rgba(0,0,0,0.3);border-radius:8px;padding:10px;margin-top:8px;color:#ffd54f">
                        💡 <b>行動指針:</b> {_vol['action']}
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )
            vc1, vc2, vc3, vc4 = st.columns(4)
            vc1.metric("現在のボラティリティ（年率）", f"{_vol['current_vol']:.1f}%",
                       help="20日間の日次リターンの標準偏差を年率換算")
            vc2.metric("過去比較（パーセンタイル）", f"{_vol['pct_rank']:.0f}位/100",
                       help="過去1年間の中で何番目に高い水準か。75以上は高ボラ")
            vc3.metric("推奨ポジションサイズ係数", f"×{_vol['position_size_factor']:.2f}",
                       help="通常のポジションサイズにこの係数をかける。高ボラ時はリスクが大きいため小さくする")
            vc4.metric("通常水準", f"{_vol['vol_p50']:.1f}%",
                       help="過去1年の中央値（50パーセンタイル）")
            with st.expander("📊 ボラティリティ推移チャートを見る", expanded=False):
                st.caption("白点線を境に低・高ボラ圏を区分。現在位置（●）がどのゾーンにあるか確認してください。")
                fig_vol = build_volatility_chart(_vol)
                st.plotly_chart(fig_vol, use_container_width=True, config={"scrollZoom": True})

        # VaR
        if _var:
            st.markdown("#### 📉 VaR（バリュー・アット・リスク）— 損失リスクの見積もり")
            st.markdown("""
<div style="background:#1a1d23;border-radius:8px;padding:12px;margin-bottom:12px;font-size:0.9em;color:#aaa">
📖 <b>読み方:</b> 「95% VaR 1日 = -2.5%」なら、<b>翌日に-2.5%以上の損失が発生する確率は5%</b>。
20回に1回はその水準を超える損失が起きると理解してください。<br>
⚠️ <b>注意:</b> 暴落・ショック時はVaRを大幅に超えることがあります（CVaRも参照）。
</div>""", unsafe_allow_html=True)

            v1, v2, v3, v4 = st.columns(4)
            v1.metric(
                "📌 95% VaR（1日）",
                f"{_var['var_95_1d_pct']*100:+.2f}%",
                f"≈ ¥{_var['var_95_1d_yen']:,.0f}",
                delta_color="inverse",
                help="翌日に5%の確率でこれ以上損する。20回に1回の想定最悪値",
            )
            v2.metric(
                "📌 99% VaR（1日）",
                f"{_var['var_99_1d_pct']*100:+.2f}%",
                f"≈ ¥{_var['var_99_1d_yen']:,.0f}",
                delta_color="inverse",
                help="翌日に1%の確率でこれ以上損する。100回に1回の想定最悪値",
            )
            v3.metric(
                "🔥 CVaR（平均損失額）",
                f"{_var['cvar_95_pct']*100:+.2f}%",
                f"≈ ¥{_var['cvar_95_yen']:,.0f}",
                delta_color="inverse",
                help="VaRを超えた損失が発生したとき、平均でどれだけ損するか。VaRより悲観的な値。暴落時の参考に。",
            )
            v4.metric(
                "📊 最大ドローダウン（過去）",
                f"{_var['max_drawdown']*100:+.1f}%",
                help="過去データの中で最も大きかった下落幅。これを超える損失には停止線を設けてください。",
                delta_color="inverse",
            )

        # モンテカルロ
        if _mc:
            st.markdown("#### 🎲 モンテカルロシミュレーション（今後30日の価格の幅）")
            st.markdown("""
<div style="background:#1a1d23;border-radius:8px;padding:12px;margin-bottom:12px;font-size:0.9em;color:#aaa">
📖 <b>読み方:</b> 過去のリターン・ボラティリティを使って300通りの価格経路をシミュレーション。<br>
濃い青帯 = 50%の確率でこの範囲に収まる。薄い青帯 = 90%の確率でこの範囲。<br>
⚠️ <b>重要:</b> <b>これは予測ではありません。</b> リスクの幅を理解するためのツールです。
</div>""", unsafe_allow_html=True)

            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("30日後 中央値", f"{_mc['final_median']:,.1f}",
                       delta=f"{(_mc['final_median']/_mc['S0']-1)*100:+.1f}%",
                       help="最も起こりやすい価格水準")
            mc2.metric("上振れシナリオ（上位5%）", f"{_mc['final_p95']:,.1f}",
                       delta=f"{(_mc['final_p95']/_mc['S0']-1)*100:+.1f}%",
                       help="運良く上振れた場合")
            mc3.metric("下振れシナリオ（下位5%）", f"{_mc['final_p5']:,.1f}",
                       delta=f"{(_mc['final_p5']/_mc['S0']-1)*100:+.1f}%",
                       delta_color="inverse",
                       help="最悪ケースに近い水準（損切りラインの参考に）")
            prob_color = "#26a69a" if _mc['prob_profit'] > 0.5 else "#ef5350"
            mc4.metric("上昇確率（モデル推定）", f"{_mc['prob_profit']*100:.0f}%",
                       help="30日後に現在より高い値を付ける確率（過去のドリフトに基づく推定）")

            fig_mc = build_montecarlo_chart(_mc, ticker)
            st.plotly_chart(fig_mc, use_container_width=True, config={"scrollZoom": True})

            with st.expander("💡 モンテカルロシミュレーションの使い方（初心者向け）"):
                st.markdown(f"""
**このグラフの正しい使い方:**

1. **下振れシナリオ（{_mc['final_p5']:,.0f}円）を損切りの参考に**
   → モデルが推定する最悪ケースに近い価格。ここを下回るような損切りラインを設けると良い

2. **上振れシナリオ（{_mc['final_p95']:,.0f}円）を利確の参考に**
   → 楽観シナリオの上限。これを超えて目標を設定すると実現しにくい

3. **幅が広い = リスクが高い**
   → 帯の幅はボラティリティに比例します。帯が広いほど読みにくい相場

4. **これは予測ツールではない**
   → 決算・市場ショックなどのイベントリスクは捉えられません

**「上昇確率 {_mc['prob_profit']*100:.0f}%」について:**
過去のリターンの傾向（ドリフト）を反映しています。50%より高くても必ず上がるわけではありません。
""")

        # AI分析タブ
        # ── ML分析 ─────────────────────────────────────────────
        st.markdown("### 🧠 機械学習分析")
        ml_col1, ml_col2 = st.columns(2)

        with ml_col1:
            st.markdown("#### 価格トレンド（回帰分析）")
            trend = trend_regression(df, window=20)
            st.markdown(
                f"""<div style="background:{trend['trend_color']}22;border:1px solid {trend['trend_color']};
                    border-radius:10px;padding:12px;text-align:center">
                    <div style="font-size:1.3em;color:{trend['trend_color']};font-weight:bold">{trend['trend']}</div>
                    <div style="color:#aaa;margin-top:4px">日次変化率: {trend['slope_pct_per_day']:+.3f}% / 当てはまり度 R²: {trend['r2']:.2f}</div>
                </div>""",
                unsafe_allow_html=True,
            )

        with ml_col2:
            st.markdown("#### ローソク足パターン（直近3本）")
            patterns = detect_candlestick_patterns(df)
            if patterns:
                for p in patterns:
                    p_color = {"買い": "#26a69a", "売り": "#ef5350", "中立": "#ffd54f"}.get(p["方向"], "#888")
                    st.markdown(
                        f"""<div style="background:{p_color}22;border-left:3px solid {p_color};
                            padding:8px 12px;margin-bottom:6px;border-radius:4px">
                            <b>{p['パターン']}</b>（{p['日付']}）<br>
                            <small>{p['意味']}</small>
                        </div>""",
                        unsafe_allow_html=True,
                    )
            else:
                st.info("直近3本で特定のパターンは検出されませんでした")

        with st.expander("🤖 機械学習シグナル予測（参考）", expanded=False):
          st.caption("⚠️ データ量が少ない銘柄では精度が低くなります。テクニカル分析の補助としてのみ使用してください。")
          ml_horizon = st.slider("予測期間（日）", min_value=3, max_value=20, value=5, step=1,
                                 help="何日後の価格が上昇しているかを予測します")
          if st.button("🔮 ML予測を実行", type="secondary"):
              with st.spinner("モデルを学習中...（初回は30秒ほどかかります）"):
                  ml_result = train_model(df, horizon=ml_horizon)

              if ml_result.get("error"):
                  st.warning(ml_result["error"])
              else:
                  prob = ml_result["up_probability"]
                  ml_color = ml_result["ml_color"]
                  mc1, mc2, mc3, mc4 = st.columns(4)
                  mc1.metric(f"{ml_horizon}日後の予測", ml_result["ml_verdict"])
                  mc2.metric("上昇確率", f"{prob}%")
                  mc3.metric("モデル精度（検証）", f"{ml_result['ensemble_accuracy']}%",
                             help="過去データのテスト期間での正解率。50%以上なら参考になります")
                  mc4.metric("信頼度", f"{ml_result['confidence']:.0f}%",
                             help="50%から離れるほど確信が強い予測です")

                  st.markdown(
                      f"""<div style="background:#1a1d23;border-radius:8px;height:20px;margin:8px 0">
                      <div style="width:{prob}%;background:{ml_color};height:20px;border-radius:8px;
                           display:flex;align-items:center;justify-content:center;
                           color:white;font-size:0.8em;font-weight:bold">{prob}%</div>
                      </div>""",
                      unsafe_allow_html=True,
                  )

                  with st.expander("📊 予測に使われた指標の重要度"):
                      fi = ml_result["feature_importance"]
                      import plotly.express as px
                      fig_fi = px.bar(
                          x=fi.values * 100, y=fi.index, orientation="h",
                          labels={"x": "重要度 (%)", "y": "指標"},
                          color=fi.values,
                          color_continuous_scale="teal",
                      )
                      fig_fi.update_layout(
                          paper_bgcolor="#0e1117", plot_bgcolor="#1a1d23",
                          font=dict(color="#fafafa"), height=300,
                          showlegend=False, coloraxis_showscale=False,
                      )
                      st.plotly_chart(fig_fi, use_container_width=True, config={"scrollZoom": True})

        st.markdown("---")
        ai_tab1, ai_tab2 = st.tabs(["🤖 テクニカルAI解説", "🌐 マクロ・ニュース影響"])

        with ai_tab1:
            if not (st.session_state.get("ai_enabled") and os.getenv("ANTHROPIC_API_KEY")):
                st.warning("ANTHROPIC_API_KEY が未設定です。AI分析をスキップします。")
            else:
                with st.spinner("AIが分析中..."):
                    try:
                        ai_comment = analyze_chart_ai(
                            ticker, signals, verdict, score,
                            df["Close"].iloc[-1], rsi_val, atr_val,
                        )
                        st.info(ai_comment)
                    except Exception as e:
                        st.warning(f"AI分析エラー: {e}")

        with ai_tab2:
            if not (st.session_state.get("ai_enabled") and os.getenv("ANTHROPIC_API_KEY")):
                st.warning("ANTHROPIC_API_KEY が未設定です。")
            else:
                with st.spinner("ニュースを取得してマクロ分析中..."):
                    try:
                        news = fetch_market_news(max_per_source=5)
                        try:
                            info = fetch_info(ticker)
                            company_name = info.get("longName") or info.get("shortName", ticker)
                            sector = info.get("sector", "不明")
                        except Exception:
                            company_name = ticker
                            sector = "不明"
                        macro_comment = analyze_news_sentiment(ticker, company_name, sector, news)
                        st.markdown(macro_comment)
                        if news:
                            with st.expander("取得したニュース一覧"):
                                for n in news[:15]:
                                    relevance = score_macro_relevance(n["title"], n.get("summary", ""))
                                    badge = "🔴" if relevance >= 3 else ("🟡" if relevance >= 1 else "⚪")
                                    st.markdown(f"{badge} **[{n['source']}]** {n['title']}")
                    except Exception as e:
                        st.warning(f"マクロ分析エラー: {e}")


# ─── スクリーニング ────────────────────────────────────────────────────────────
elif page == "🔍 スクリーニング":
    st.title("🔍 バリュー株スクリーニング")
    st.markdown("**なごちょう式** 6条件 + Piotroski Fスコアで評価します")

    tickers_input = st.text_area(
        "銘柄コードを入力（1行1銘柄）",
        value="7203\n9984\nTOYOTA\nAAPL",
        height=150,
    )
    screen_btn = st.button("🔍 スクリーニング実行", type="primary")

    if screen_btn:
        tickers = [t.strip() for t in tickers_input.strip().split("\n") if t.strip()]
        results = []
        progress = st.progress(0)
        for i, t in enumerate(tickers):
            with st.spinner(f"{t} を確認中..."):
                try:
                    r = screen_single(t)
                    results.append(r)
                except Exception as e:
                    st.warning(f"{t}: 取得失敗 ({e})")
            progress.progress((i + 1) / len(tickers))

        if results:
            st.markdown("### スクリーニング結果")
            for r in results:
                pass_mark = "✅ 合格" if r["合否"] else "❌ 不合格"
                with st.expander(f"**{r['ticker']}** — {pass_mark}"):
                    rows = []
                    for key, detail in r["詳細"].items():
                        val = detail["値"]
                        if isinstance(val, float):
                            val_str = f"{val:.2f}"
                        elif val is None:
                            val_str = "N/A"
                        else:
                            val_str = str(val)
                        rows.append({
                            "項目": key,
                            "値": val_str,
                            "基準": detail["基準"],
                            "判定": "✅" if detail["合否"] else "❌",
                        })
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ─── ファンダメンタル分析 ─────────────────────────────────────────────────────
elif page == "📋 ファンダメンタル分析":
    st.title("📋 ファンダメンタル分析")

    ticker_fa = st.session_state.get("current_ticker", "7203")
    st.success(f"📌 分析銘柄: **{ticker_fa}**　← サイドバーで変更できます")
    fa_btn = st.button("📋 分析する", type="primary")

    if fa_btn and ticker_fa:
        with st.spinner("財務データ取得中..."):
            try:
                summary = get_fundamental_summary(ticker_fa)
            except Exception as e:
                st.error(f"取得エラー: {e}")
                st.stop()

        st.markdown(f"### {summary['企業名']}")
        st.caption(f"{summary['セクター']} / {summary['業種']}")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### バリュエーション指標")
            val_items = {
                "PBR": summary["PBR"],
                "PER（実績）": summary["PER（実績）"],
                "PER（予想）": summary["PER（予想）"],
                "PEGレシオ": summary["PEGレシオ"],
                "配当利回り (%)": summary["配当利回り"],
                "ベータ": summary["ベータ"],
            }
            for k, v in val_items.items():
                col_k, col_v = st.columns([2, 1])
                col_k.write(k)
                col_v.write(f"{v:.2f}" if isinstance(v, float) else str(v or "N/A"))

        with col2:
            st.markdown("#### 収益性・成長性指標")
            prof_items = {
                "ROE (%)": summary["ROE"],
                "ROA (%)": summary["ROA"],
                "営業利益率 (%)": summary["営業利益率"],
                "純利益率 (%)": summary["純利益率"],
                "売上成長率 (%)": summary["売上成長率"],
                "利益成長率 (%)": summary["利益成長率"],
            }
            for k, v in prof_items.items():
                col_k, col_v = st.columns([2, 1])
                col_k.write(k)
                col_v.write(f"{v:.2f}" if isinstance(v, float) else str(v or "N/A"))

        st.markdown(f"**アナリスト推奨:** `{summary['アナリスト推奨']}`")
        st.markdown(f"**52週レンジ:** {summary['52週安値']} 〜 {summary['52週高値']}")

        # ファイブフォース（AI）
        if summary["セクター"] != "N/A":
            st.markdown("### 🤖 ファイブフォース分析（AI）")
            if not (st.session_state.get("ai_enabled") and os.getenv("ANTHROPIC_API_KEY")):
                st.warning("ANTHROPIC_API_KEY が未設定です。")
            else:
                with st.spinner("AIがファイブフォース分析中..."):
                    try:
                        ff = analyze_five_forces(summary["企業名"], summary["セクター"], summary["業種"])
                        st.markdown(ff)
                    except Exception as e:
                        st.warning(f"AI分析エラー: {e}")


# ─── マクロ・ニュース分析 ─────────────────────────────────────────────────────
elif page == "🌐 マクロ・ニュース":
    st.title("🌐 マクロ経済・ニュース分析")
    st.markdown("リアルタイムの市場データと経済ニュースから、今日の相場環境を把握します")

    macro_tab1, macro_tab2, macro_tab3 = st.tabs([
        "📡 リアルタイム市場データ",
        "📰 市場ニュース",
        "📊 金融政策・経済指標",
    ])

    with macro_tab1:
        st.markdown("### 📡 主要市場指標（リアルタイム）")
        st.caption("yfinanceで取得した最新値です。15分程度の遅延があります。")

        if st.button("🔄 今すぐ更新", key="refresh_market"):
            st.session_state.pop("_live_market_cache", None)

        if "_live_market_cache" not in st.session_state:
            with st.spinner("市場データを取得中..."):
                st.session_state["_live_market_cache"] = fetch_live_market_data()

        live_data = st.session_state.get("_live_market_cache", [])

        if live_data:
            # センチメント判定
            sentiment = get_market_sentiment_rule(live_data)
            label = sentiment["label"]
            score_val = sentiment["score"]
            if "強気" in label:
                st.success(f"### 🎯 市場センチメント: **{label}**（スコア: {score_val:+d}）")
            elif "弱気" in label:
                st.error(f"### 🎯 市場センチメント: **{label}**（スコア: {score_val:+d}）")
            else:
                st.warning(f"### 🎯 市場センチメント: **{label}**（スコア: {score_val:+d}）")

            for reason in sentiment["reasons"]:
                st.caption(f"  ・{reason}")

            st.markdown("---")

            # 指標テーブル
            _cols = st.columns(3)
            for i, d in enumerate(live_data):
                c = d.get("change_pct", 0) or 0
                color = "#26a69a" if c >= 0 else "#ef5350"
                arrow = "▲" if c >= 0 else "▼"
                with _cols[i % 3]:
                    st.markdown(
                        f"""<div style='border:1px solid #333;border-radius:8px;padding:10px 14px;margin-bottom:8px'>
                        <div style='font-size:12px;color:#aaa'>{d['指標']}</div>
                        <div style='font-size:22px;font-weight:bold'>{d['現在値']}</div>
                        <div style='font-size:13px;color:{color}'>{arrow} {c:+.2f}%</div>
                        </div>""",
                        unsafe_allow_html=True,
                    )

            # セクター影響
            st.markdown("---")
            st.markdown("### 🏭 セクター別・今日の注目点")
            impacts = get_sector_impact(live_data)
            if impacts:
                df_impact = pd.DataFrame(impacts)
                st.dataframe(df_impact, use_container_width=True, hide_index=True)
                st.caption("⚠️ これは機械的なルールによる参考情報です。最終判断は自己責任でお願いします。")
            else:
                st.info("現在のデータでは特筆すべきセクター影響はありません（市場が落ち着いている状態）")

            # 投資判断への使い方ガイド
            with st.expander("💡 この情報を投資判断にどう使う？"):
                st.markdown("""
**マクロ環境は「追い風/向かい風」の確認に使います。**

| センチメント | 推奨アクション |
|---|---|
| 強気・やや強気 | テクニカル分析でエントリーポイントを積極探索。シグナルが「買い」なら信頼度UP |
| 中立 | シグナルに従って通常通り判断。ポジション大きくしすぎない |
| やや弱気・弱気 | 新規買いは慎重に。損切りラインをいつもより厳しく設定 |

**セクター影響の読み方:**
- 円安 → 輸出株（トヨタ・ソニー等）に有利。買いシグナルが重なれば信頼度UP
- 金利上昇 → 銀行株に有利、グロース株に不利
- VIX高 → リスクオフ。新規買いを控え、キャッシュポジション増やす

**使い方のポイント:**
1. 毎朝この画面を開いてセンチメントを確認（30秒）
2. 「弱気」なら今日はその銘柄の新規買いを見送る
3. 「強気」なら通常の判断でOK
""")
        else:
            st.warning("市場データを取得できませんでした。しばらくしてから再度お試しください。")

    with macro_tab2:
        st.markdown("### 📰 最新市場ニュース")
        col_l, col_r = st.columns([1, 2])
        with col_l:
            ticker_macro = st.text_input("個別銘柄への影響を分析（任意）", placeholder="7203 / AAPL", key="macro_ticker")
        news_btn = st.button("📰 ニュース取得", type="primary")

        if news_btn:
            with st.spinner("ニュースを収集中..."):
                news = fetch_market_news(max_per_source=5)

            if news:
                st.success(f"{len(news)}件のニュースを取得しました")

                # ニュース一覧
                high = [n for n in news if score_macro_relevance(n["title"], n.get("summary", "")) >= 2]
                other = [n for n in news if score_macro_relevance(n["title"], n.get("summary", "")) < 2]

                if high:
                    st.markdown("**🔴 市場への影響が大きいニュース**")
                    for n in high[:8]:
                        st.markdown(f"- **[{n['source']}]** {n['title']}")
                        if n.get("summary"):
                            st.caption(f"  {n['summary'][:150]}")

                if other:
                    with st.expander(f"その他のニュース（{len(other)}件）"):
                        for n in other[:10]:
                            st.markdown(f"- [{n['source']}] {n['title']}")

                # AI分析（オプション）
                if ticker_macro and st.session_state.get("ai_enabled") and os.getenv("ANTHROPIC_API_KEY"):
                    st.markdown(f"### 🔍 {ticker_macro} への影響分析（AI）")
                    with st.spinner(f"{ticker_macro} への影響を分析中..."):
                        try:
                            try:
                                info = fetch_info(ticker_macro)
                                company_name = info.get("longName") or info.get("shortName", ticker_macro)
                                sector = info.get("sector", "不明")
                            except Exception:
                                company_name = ticker_macro
                                sector = "不明"
                            impact = analyze_news_sentiment(ticker_macro, company_name, sector, news)
                            st.markdown(impact)
                        except Exception as e:
                            st.warning(f"影響分析エラー: {e}")
                elif ticker_macro and not os.getenv("ANTHROPIC_API_KEY"):
                    st.info("個別銘柄への詳細AI分析はANTHROPIC_API_KEY設定後に利用可能です。上の「リアルタイム市場データ」タブのセクター影響を参考にしてください。")
            else:
                st.warning("ニュースを取得できませんでした。ネットワーク接続を確認してください。")

    with macro_tab3:
        st.markdown("### 📊 金融政策・主要経済指標")
        st.caption("※ 下記は定期的に手動更新している参考値です。正確な値は日銀・FRBの公式発表をご確認ください。")

        macro_ctx = get_macro_context()
        for region, indicators in macro_ctx.items():
            st.markdown(f"#### {region}")
            rows = []
            for name, data in indicators.items():
                rows.append({
                    "指標": name,
                    "現在値": data["値"],
                    "方向性": data["方向"],
                    "投資への影響": data["投資影響"],
                })
            df_macro = pd.DataFrame(rows)
            st.dataframe(df_macro, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("#### 📌 今後の主要イベントカレンダー")
        events = [
            {"タイミング": "随時", "イベント": "日銀金融政策決定会合", "注目度": "★★★", "影響": "円相場・金融株・REITに直結"},
            {"タイミング": "毎月初旬", "イベント": "米雇用統計 (NFP)", "注目度": "★★★", "影響": "FRB政策観測・ドル円に影響"},
            {"タイミング": "毎月中旬", "イベント": "米CPI（消費者物価指数）", "注目度": "★★★", "影響": "インフレ→利下げ観測→グロース株"},
            {"タイミング": "四半期", "イベント": "決算シーズン（3・6・9・12月）", "注目度": "★★★", "影響": "個別株の最大の変動要因"},
            {"タイミング": "随時", "イベント": "地政学リスク（中東・台湾海峡等）", "注目度": "★★☆", "影響": "リスクオフ・原油・防衛株"},
            {"タイミング": "随時", "イベント": "米中貿易摩擦・関税動向", "注目度": "★★☆", "影響": "製造業・半導体・自動車に逆風"},
        ]
        st.dataframe(pd.DataFrame(events), use_container_width=True, hide_index=True)


# ─── バックテスト ─────────────────────────────────────────────────────────────
elif page == "🔬 バックテスト":
    st.title("🔬 バックテスト")
    st.markdown("過去データで売買戦略の有効性を検証します")

    bt_ticker = st.session_state.get("current_ticker", "7203")
    st.success(f"📌 検証銘柄: **{bt_ticker}**　← サイドバーで変更できます")
    _btc1, _btc2, _btc3 = st.columns([2, 1, 1])
    with _btc1:
        st.markdown("")  # spacer
    c2, c3 = _btc2, _btc3
    with c2:
        bt_period = st.selectbox("検証期間", ["1y", "2y", "5y"], index=1,
                                 format_func=lambda x: {"1y": "1年", "2y": "2年", "5y": "5年"}[x])
    with c3:
        bt_strategy_label = st.selectbox("戦略", list(STRATEGIES.keys()))

    with st.expander("⚙️ 詳細パラメータ"):
        pc1, pc2, pc3, pc4 = st.columns(4)
        bt_short = pc1.number_input("短期MA", value=25, min_value=5, max_value=50)
        bt_long = pc2.number_input("長期MA", value=75, min_value=20, max_value=200)
        bt_rsi_buy = pc3.number_input("RSI買いライン", value=35, min_value=10, max_value=50)
        bt_rsi_sell = pc4.number_input("RSI売りライン", value=65, min_value=50, max_value=90)
        bt_cash = st.number_input("初期資金 (円)", value=1_000_000, min_value=100_000, step=100_000)
        bt_stop_atr = st.slider("損切り幅 (ATR倍)", min_value=1.0, max_value=4.0, value=2.0, step=0.5)

    bt_btn = st.button("▶ バックテスト実行", type="primary", use_container_width=True)

    if bt_btn and bt_ticker:
        with st.spinner("データ取得・バックテスト実行中..."):
            try:
                df_raw = fetch_ohlcv(bt_ticker, period=bt_period)
                strategy_key = STRATEGIES[bt_strategy_label]
                result = run_backtest(
                    df_raw,
                    strategy=strategy_key,
                    sma_short=bt_short,
                    sma_long=bt_long,
                    rsi_buy=bt_rsi_buy,
                    rsi_sell=bt_rsi_sell,
                    initial_cash=bt_cash,
                    stop_loss_atr=bt_stop_atr,
                )
            except Exception as e:
                st.error(f"エラー: {e}")
                st.stop()

        m = result["metrics"]
        st.markdown("### 📊 パフォーマンス指標")
        cols = st.columns(7)
        metrics = [
            ("最終資産", f"¥{m['最終資産']:,.0f}", None),
            ("総リターン", f"{m['総リターン(%)']:+.1f}%",
             f"B&H: {m['B&Hリターン(%)']:+.1f}%"),
            ("最大DD", f"{m['最大ドローダウン(%)']:.1f}%", None),
            ("シャープ", f"{m['シャープレシオ']:.2f}", None),
            ("取引回数", f"{m['総取引回数']}回", None),
            ("勝率", f"{m['勝率(%)']}%", None),
            ("戦略 vs B&H", "優位" if m['総リターン(%)'] > m['B&Hリターン(%)'] else "劣後", None),
        ]
        for col, (label, val, delta) in zip(cols, metrics):
            col.metric(label, val, delta)

        fig_bt = build_backtest_chart(result["portfolio"], result["trades"], bt_ticker)
        st.plotly_chart(fig_bt, use_container_width=True, config={"scrollZoom": True})

        if not result["trades"].empty:
            st.markdown("### 📋 取引履歴")
            trades_display = result["trades"].copy()
            trades_display["損益"] = trades_display["損益"].apply(
                lambda x: f"¥{x:+,.0f}" if x != 0 else "-"
            )
            st.dataframe(trades_display, use_container_width=True, hide_index=True)

            st.markdown("### 💡 AIによる戦略評価")
            if st.session_state.get("ai_enabled") and os.getenv("ANTHROPIC_API_KEY"):
                with st.spinner("AIが戦略を評価中..."):
                    try:
                        from modules.ai_analysis import _get_client
                        prompt = f"""バックテスト結果を評価してください。
銘柄: {bt_ticker} / 戦略: {bt_strategy_label} / 期間: {bt_period}
総リターン: {m['総リターン(%)']:+.1f}% (B&H: {m['B&Hリターン(%)']:+.1f}%)
最大ドローダウン: {m['最大ドローダウン(%)']:.1f}% / シャープレシオ: {m['シャープレシオ']:.2f}
勝率: {m['勝率(%)']}% / 取引回数: {m['総取引回数']}回

この戦略の強み・弱み・改善提案を200字以内で日本語で述べてください。"""
                        client = _get_client()
                        resp = client.messages.create(
                            model="claude-sonnet-4-6",
                            max_tokens=400,
                            messages=[{"role": "user", "content": prompt}],
                        )
                        st.info(resp.content[0].text)
                    except Exception as e:
                        st.warning(f"AI評価エラー: {e}")


# ─── ポートフォリオ最適化 ─────────────────────────────────────────────────────
elif page == "📐 ポートフォリオ":
    st.title("📐 ポートフォリオ最適化")
    st.markdown("相関分析・最小分散・ケリー基準で分散投資を最適化します")

    tickers_input = st.text_area(
        "保有・検討銘柄を入力（1行1銘柄、2銘柄以上）",
        value="7203\n9984\n6758\nAAPL",
        height=120,
    )
    pf_period = st.selectbox("分析期間", ["1y", "2y"], index=0,
                              format_func=lambda x: {"1y": "1年", "2y": "2年"}[x])
    pf_btn = st.button("📐 最適化実行", type="primary", use_container_width=True)

    if pf_btn:
        tickers = [t.strip() for t in tickers_input.strip().split("\n") if t.strip()]
        if len(tickers) < 2:
            st.error("2銘柄以上入力してください")
        else:
            dfs = {}
            with st.spinner("データ取得中..."):
                for t in tickers:
                    try:
                        dfs[t] = fetch_ohlcv(t, period=pf_period)
                    except Exception as e:
                        st.warning(f"{t}: スキップ ({e})")

            if len(dfs) < 2:
                st.error("有効なデータが2銘柄未満です")
            else:
                trades_df = get_trades()
                pf_result = build_portfolio_summary(list(dfs.keys()), dfs, trades_df)

                if "error" in pf_result:
                    st.error(pf_result["error"])
                else:
                    st.markdown("### 🔗 相関係数マトリクス")
                    st.caption("値が低い（青）ほど分散効果が高い。0.7以上（赤）は集中リスク")
                    fig_corr = build_correlation_heatmap(pf_result["corr"])
                    st.plotly_chart(fig_corr, use_container_width=True)

                    st.markdown("### ⚖️ 最適ウェイト比較")
                    col_mv, col_eq = st.columns(2)
                    with col_mv:
                        st.markdown("**最小分散ポートフォリオ**")
                        st.caption("リスクを最小化する配分")
                        fig_mv = build_portfolio_pie(pf_result["weights_min_var"], "最小分散")
                        st.plotly_chart(fig_mv, use_container_width=True)
                        s = pf_result["stats_min_var"]
                        st.metric("期待リターン", f"{s['期待リターン(%)']:+.1f}%")
                        st.metric("リスク（年率）", f"{s['リスク（年率ボラ%）']:.1f}%")
                        st.metric("シャープレシオ", f"{s['シャープレシオ']:.2f}")

                    with col_eq:
                        st.markdown("**均等配分**")
                        st.caption("単純均等割り（参考）")
                        fig_eq = build_portfolio_pie(pf_result["weights_equal"], "均等配分")
                        st.plotly_chart(fig_eq, use_container_width=True)
                        s = pf_result["stats_equal"]
                        st.metric("期待リターン", f"{s['期待リターン(%)']:+.1f}%")
                        st.metric("リスク（年率）", f"{s['リスク（年率ボラ%）']:.1f}%")
                        st.metric("シャープレシオ", f"{s['シャープレシオ']:.2f}")

                    # ケリー基準
                    if pf_result["kelly"]:
                        st.markdown("### 🎯 ケリー基準（投資日記の取引実績より）")
                        st.caption("過去の勝率・損益比から算出した理論上の最適投資比率")
                        kelly_data = [
                            {"銘柄": t, "ケリー推奨比率": f"{v*100:.1f}%",
                             "ハーフケリー（安全版）": f"{v*50:.1f}%"}
                            for t, v in pf_result["kelly"].items()
                        ]
                        st.dataframe(pd.DataFrame(kelly_data), use_container_width=True, hide_index=True)
                        st.caption("※ ハーフケリー（推奨比率の半分）が実用的とされています")
                    else:
                        st.info("投資日記に取引履歴を記録するとケリー基準が計算されます")

                    # リターン時系列
                    st.markdown("### 📈 銘柄別リターン推移（累積）")
                    returns = pf_result["returns"]
                    cumulative = (1 + returns).cumprod() - 1
                    import plotly.express as px
                    fig_ret = px.line(
                        cumulative * 100,
                        title="累積リターン (%)",
                        labels={"value": "リターン (%)", "variable": "銘柄"},
                        color_discrete_sequence=px.colors.qualitative.Set2,
                    )
                    fig_ret.update_layout(
                        paper_bgcolor="#0e1117", plot_bgcolor="#1a1d23",
                        font=dict(color="#fafafa"), height=400,
                    )
                    st.plotly_chart(fig_ret, use_container_width=True)


# ─── 投資日記 ─────────────────────────────────────────────────────────────────
elif page == "📔 投資日記":
    st.title("📔 投資日記")

    tab1, tab2, tab3, tab4 = st.tabs(["📝 取引記録", "💰 損益サマリー", "📊 パフォーマンス", "🔄 振り返り"])

    with tab1:
        st.markdown("### 取引を記録する")
        with st.form("trade_form"):
            c1, c2, c3 = st.columns(3)
            t_ticker = c1.text_input("銘柄コード", placeholder="7203")
            t_action = c2.selectbox("売買", ["買い", "売り"])
            t_price = c3.number_input("価格", min_value=0.0, step=0.1)

            c4, c5, c6 = st.columns(3)
            t_qty = c4.number_input("株数", min_value=1, step=1)
            t_fee = c5.number_input("手数料", min_value=0.0, step=1.0)
            t_stop = c6.number_input("損切りライン", min_value=0.0, step=0.1)
            t_target = st.number_input("目標価格", min_value=0.0, step=0.1)

            st.markdown("**取引の根拠**")
            t_tech = st.text_area("テクニカル根拠", placeholder="例: MACD ゴールデンクロス + RSI 35で反発")
            t_fund = st.text_area("ファンダメンタル根拠", placeholder="例: PBR 0.8以下で割安、配当利回り4%")

            st.markdown("**心理・感情ログ**")
            emotion_labels = {
                1: "😨 強い恐怖", 2: "😟 不安", 3: "😐 中立",
                4: "😊 やや強気", 5: "😤 興奮・FOMO",
            }
            t_emotion_score = st.slider("感情スコア（プロスペクト理論）", 1, 5, 3,
                                        format="%d",
                                        help="1=恐怖 → 5=興奮（FOMOに注意）")
            st.caption(emotion_labels[t_emotion_score])
            t_emotion = st.text_input("感情メモ", placeholder="例: 下落が続き怖かったが指標は買いシグナル")
            t_notes = st.text_area("その他メモ")

            submitted = st.form_submit_button("💾 記録する", type="primary")
            if submitted and t_ticker and t_price > 0:
                add_trade(
                    ticker=t_ticker, action=t_action, price=t_price,
                    quantity=int(t_qty), fee=t_fee,
                    technical_reason=t_tech, fundamental_reason=t_fund,
                    emotion=t_emotion, emotion_score=t_emotion_score,
                    stop_loss=t_stop if t_stop > 0 else None,
                    target_price=t_target if t_target > 0 else None,
                    notes=t_notes,
                )
                st.success(f"✅ {t_ticker} の{t_action}を記録しました！")

        st.markdown("### 取引履歴")
        trades_df = get_trades()
        if not trades_df.empty:
            display_cols = ["created_at", "ticker", "action", "price", "quantity",
                            "technical_reason", "emotion_score", "stop_loss"]
            st.dataframe(trades_df[display_cols], use_container_width=True, hide_index=True)
        else:
            st.info("まだ取引記録がありません。")

    with tab2:
        import plotly.express as px
        import plotly.graph_objects as go_pnl

        st.markdown("### 💰 損益サマリー")
        trades_df = get_trades(limit=10000)
        pnl_data = calc_pnl(trades_df)
        realized = pnl_data["realized"]
        positions = pnl_data["positions"]
        summary_by_ticker = pnl_data["summary_by_ticker"]
        monthly = pnl_data["monthly"]

        if not realized and not positions:
            st.info("取引記録がまだありません。「取引記録」タブから入力してください。")
        else:
            # ─ 全体サマリー ─
            total_realized = sum(r["実現損益"] for r in realized)
            total_wins = sum(1 for r in realized if r["実現損益"] > 0)
            total_trades = len(realized)
            win_rate = total_wins / total_trades * 100 if total_trades else 0
            avg_win = sum(r["実現損益"] for r in realized if r["実現損益"] > 0) / total_wins if total_wins else 0
            total_loss_count = total_trades - total_wins
            avg_loss = sum(r["実現損益"] for r in realized if r["実現損益"] <= 0) / total_loss_count if total_loss_count else 0

            m1, m2, m3, m4, m5 = st.columns(5)
            pnl_color = "normal" if total_realized >= 0 else "inverse"
            m1.metric("確定損益合計", f"¥{total_realized:+,.0f}")
            m2.metric("勝率", f"{win_rate:.1f}%", f"{total_wins}勝 {total_loss_count}敗")
            m3.metric("平均利益", f"¥{avg_win:,.0f}")
            m4.metric("平均損失", f"¥{avg_loss:,.0f}")
            rr = abs(avg_win / avg_loss) if avg_loss else 0
            m5.metric("損益比 (RR比)", f"{rr:.2f}",
                      help="1以上が理想。勝率×RR比 > 1で期待値プラス")

            st.markdown("---")

            # ─ 月別損益チャート ─
            if monthly:
                st.markdown("#### 📅 月別実現損益")
                months = sorted(monthly.keys())
                values = [monthly[m] for m in months]
                colors = ["#26a69a" if v >= 0 else "#ef5350" for v in values]
                fig_monthly = go_pnl.Figure(go_pnl.Bar(
                    x=months, y=values,
                    marker_color=colors,
                    text=[f"¥{v:+,.0f}" for v in values],
                    textposition="outside",
                ))
                fig_monthly.update_layout(
                    title="月別実現損益",
                    paper_bgcolor="#0e1117", plot_bgcolor="#1a1d23",
                    font=dict(color="#fafafa"), height=350,
                    yaxis_title="損益 (円)",
                )
                st.plotly_chart(fig_monthly, use_container_width=True)

            col_a, col_b = st.columns(2)

            # ─ 銘柄別損益 ─
            with col_a:
                st.markdown("#### 🏷️ 銘柄別損益")
                if summary_by_ticker:
                    ticker_rows = [
                        {
                            "銘柄": t,
                            "実現損益": f"¥{s['実現損益合計']:+,.0f}",
                            "取引回数": s["取引回数"],
                            "勝率": f"{s['勝率(%)']}%",
                            "勝/負": f"{s['勝ち']}勝 {s['負け']}敗",
                        }
                        for t, s in sorted(summary_by_ticker.items(),
                                           key=lambda x: x[1]["実現損益合計"], reverse=True)
                    ]
                    st.dataframe(pd.DataFrame(ticker_rows), use_container_width=True, hide_index=True)

                    # 銘柄別損益バー
                    tickers_sorted = sorted(summary_by_ticker.keys(),
                                            key=lambda t: summary_by_ticker[t]["実現損益合計"])
                    pnl_vals = [summary_by_ticker[t]["実現損益合計"] for t in tickers_sorted]
                    fig_tk = go_pnl.Figure(go_pnl.Bar(
                        x=pnl_vals, y=tickers_sorted, orientation="h",
                        marker_color=["#26a69a" if v >= 0 else "#ef5350" for v in pnl_vals],
                    ))
                    fig_tk.update_layout(
                        paper_bgcolor="#0e1117", plot_bgcolor="#1a1d23",
                        font=dict(color="#fafafa"), height=300,
                        xaxis_title="損益 (円)",
                    )
                    st.plotly_chart(fig_tk, use_container_width=True)

            # ─ 含み損益（保有中） ─
            with col_b:
                st.markdown("#### 📂 含み損益（保有中ポジション）")
                if positions:
                    # 現在値をyfinanceから取得
                    current_prices = {}
                    for t in positions:
                        try:
                            info = fetch_info(t)
                            current_prices[t] = info.get("currentPrice") or info.get("regularMarketPrice")
                        except Exception:
                            pass
                    unrealized = calc_unrealized(positions, current_prices)
                    if unrealized:
                        ur_total = sum(
                            r["含み損益"] for r in unrealized
                            if isinstance(r["含み損益"], (int, float))
                        )
                        st.metric("含み損益合計", f"¥{ur_total:+,.0f}")
                        ur_df = pd.DataFrame(unrealized)
                        st.dataframe(ur_df, use_container_width=True, hide_index=True)
                else:
                    st.info("現在保有中のポジションはありません")

            # ─ 取引明細 ─
            st.markdown("#### 📋 確定済み取引一覧")
            if realized:
                realized_df = pd.DataFrame(realized)
                realized_df["実現損益"] = realized_df["実現損益"].apply(
                    lambda x: f"¥{x:+,.0f}"
                )
                realized_df["損益率(%)"] = realized_df["損益率(%)"].apply(
                    lambda x: f"{x:+.2f}%"
                )
                st.dataframe(realized_df, use_container_width=True, hide_index=True)

                # 損益推移（累積）
                st.markdown("#### 📈 確定損益の累積推移")
                cumulative_pnl = pd.DataFrame(realized)[["日付", "実現損益"]].copy()
                cumulative_pnl["実現損益"] = pd.to_numeric(
                    pd.DataFrame(realized)["実現損益"]
                )
                cumulative_pnl = cumulative_pnl.sort_values("日付")
                cumulative_pnl["累積損益"] = cumulative_pnl["実現損益"].cumsum()
                fig_cum = go_pnl.Figure()
                fig_cum.add_trace(go_pnl.Scatter(
                    x=cumulative_pnl["日付"],
                    y=cumulative_pnl["累積損益"],
                    fill="tozeroy",
                    fillcolor="rgba(38,166,154,0.15)",
                    line=dict(color="#26a69a", width=2),
                    name="累積損益",
                ))
                fig_cum.add_hline(y=0, line_color="rgba(255,255,255,0.3)", line_dash="dash")
                fig_cum.update_layout(
                    paper_bgcolor="#0e1117", plot_bgcolor="#1a1d23",
                    font=dict(color="#fafafa"), height=320,
                    yaxis_title="累積損益 (円)",
                )
                st.plotly_chart(fig_cum, use_container_width=True)

    with tab3:
        st.markdown("### パフォーマンス統計")
        trades_df = get_trades()
        stats = trade_stats(trades_df)
        if stats:
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("総取引数", stats["総取引数"])
            sc2.metric("買い回数", stats["買い"])
            sc3.metric("売り回数", stats["売り"])
            sc4.metric("平均感情スコア", stats["平均感情スコア"])

            st.markdown("#### 感情スコアの分布")
            if not trades_df.empty:
                import plotly.express as px
                fig_e = px.histogram(
                    trades_df, x="emotion_score", nbins=5,
                    title="取引時の感情スコア分布",
                    labels={"emotion_score": "感情スコア"},
                    color_discrete_sequence=["#7e57c2"],
                )
                fig_e.update_layout(paper_bgcolor="#0e1117", plot_bgcolor="#1a1d23", font=dict(color="#fafafa"))
                st.plotly_chart(fig_e, use_container_width=True)
                st.caption("スコア5（興奮・FOMO）での取引は損失リスクが高い傾向があります（プロスペクト理論）")
        else:
            st.info("取引データが不足しています。")

    with tab4:
        st.markdown("### 週次・月次振り返り")
        with st.form("review_form"):
            r_period = st.text_input("対象期間", placeholder="例: 2026年5月第1週")
            r_good = st.text_area("✅ うまくいったこと")
            r_bad = st.text_area("❌ うまくいかなかったこと")
            r_lessons = st.text_area("💡 学んだこと・改善点")
            r_missed = st.text_area("🔍 見落としていたシグナル（失敗分析）")
            r_submitted = st.form_submit_button("💾 記録する", type="primary")
            if r_submitted and r_period:
                add_review(r_period, r_good, r_bad, r_lessons, r_missed)
                st.success("振り返りを保存しました！")

        st.markdown("### 過去の振り返り")
        reviews_df = get_reviews()
        if not reviews_df.empty:
            for _, row in reviews_df.iterrows():
                with st.expander(f"**{row['period']}** — {row['created_at'][:10]}"):
                    st.markdown(f"**✅ うまくいったこと:** {row['good_points']}")
                    st.markdown(f"**❌ うまくいかなかったこと:** {row['bad_points']}")
                    st.markdown(f"**💡 学んだこと:** {row['lessons']}")
                    st.markdown(f"**🔍 見落としシグナル:** {row['missed_signals']}")
        else:
            st.info("まだ振り返りがありません。")


# ─── 通知設定 ─────────────────────────────────────────────────────────────────
elif page == "🔔 通知設定":
    st.title("🔔 通知設定")
    st.markdown("シグナルをスマホに届けます。**Telegram**（推奨）または **Slack** を設定してください。")

    ntab1, ntab2, ntab3, ntab4 = st.tabs(["📱 Telegram設定", "💬 Slack設定", "⚡ リアルタイムデータ設定", "🚀 今すぐ送信テスト"])

    with ntab1:
        st.markdown("### Telegram Bot の設定手順")
        with st.expander("📋 手順を見る（まだ設定していない方）", expanded=False):
            st.markdown("""
**ステップ1: Bot を作る（約1分）**
1. スマホの Telegram で **[@BotFather](https://t.me/BotFather)** を検索して開く
2. `Start` または `/start` と送信
3. `/newbot` と送信
4. Bot名を入力（例: `MyStockBot`）
5. Bot Token が発行される（例: `1234567890:ABCdefGHI...`） → 下の欄に貼り付け

**ステップ2: Chat ID を取得する**
1. 作った Bot のページを開き、**「START」または何かメッセージを送る**（← 重要！先に送らないとIDが取得できません）
2. 下の「🔍 Chat ID を自動取得」ボタンを押す
   - または手動取得: `https://api.telegram.org/bot【TOKEN】/getUpdates` をブラウザで開き、`"chat":{"id": 数字}` の数字をコピー

**よくある失敗:**
- ❌ Bot にメッセージを送る前に Chat ID 取得 → `result: []` が返ってきて取得できない
- ❌ Token に余分なスペースが入っている → コピー時に注意
""")

        st.markdown("### 認証情報を入力")
        tg_token = st.text_input("Bot Token", type="password",
                                  value=os.getenv("TELEGRAM_BOT_TOKEN", ""),
                                  placeholder="1234567890:ABCdefGHI...")
        tg_chat_default = os.getenv("TELEGRAM_CHAT_ID", "")
        tg_chat = st.text_input("Chat ID（わからない場合は下のボタンで自動取得）",
                                 value=tg_chat_default,
                                 placeholder="123456789")

        # Chat ID 自動取得ボタン
        if st.button("🔍 Chat ID を自動取得（Bot に先にメッセージを送ってから押す）"):
            if not tg_token:
                st.warning("先に Bot Token を入力してください")
            else:
                try:
                    import requests as _req
                    _res = _req.get(
                        f"https://api.telegram.org/bot{tg_token.strip()}/getUpdates",
                        timeout=10,
                    )
                    _data = _res.json()
                    if not _data.get("ok"):
                        st.error(f"Telegram APIエラー: {_data.get('description', '不明')}\n\nToken が正しいか確認してください。")
                    elif not _data.get("result"):
                        st.warning("""Chat ID が見つかりませんでした。

**次の手順を試してください:**
1. Telegram で作った Bot を検索して開く
2. 「START」ボタンを押す（または「/start」と送信）
3. もう一度このボタンを押す""")
                    else:
                        _updates = _data["result"]
                        _found_ids = []
                        for _upd in _updates:
                            _msg = _upd.get("message") or _upd.get("channel_post", {})
                            _chat = _msg.get("chat", {})
                            _cid = _chat.get("id")
                            _cname = _chat.get("first_name") or _chat.get("title") or _chat.get("username", "")
                            if _cid and _cid not in [x[0] for x in _found_ids]:
                                _found_ids.append((_cid, _cname))
                        if _found_ids:
                            st.success(f"Chat ID を取得しました！")
                            for _cid, _cname in _found_ids:
                                st.info(f"👤 {_cname}　Chat ID: **`{_cid}`**")
                            st.markdown("上の数字を「Chat ID」欄にコピーしてください。")
                        else:
                            st.warning("メッセージは届いていますが、Chat ID を抽出できませんでした。手動で確認してください。")
                except Exception as _e:
                    st.error(f"取得エラー: {_e}")

        st.markdown("---")

        col_tg1, col_tg2 = st.columns(2)
        with col_tg1:
            if st.button("✅ Telegram接続テスト", type="primary"):
                if tg_token and tg_chat:
                    from modules.notifier import _telegram
                    ok = _telegram(tg_token, tg_chat,
                                    "✅ 株式分析ツールからの接続テストです！通知設定が完了しました。")
                    if ok:
                        st.success("送信成功！スマホを確認してください 📱")
                    else:
                        st.error("送信失敗。Token と Chat ID を確認してください。")
                else:
                    st.warning("Token と Chat ID を入力してください")

        st.markdown("---")
        st.markdown("### 環境変数に設定する（常時起動用）")
        st.code(f"""# .env ファイルまたはターミナルで設定
export TELEGRAM_BOT_TOKEN="{tg_token or 'your_token_here'}"
export TELEGRAM_CHAT_ID="{tg_chat or 'your_chat_id'}"
export WATCH_TICKERS="7203,9984,AAPL"   # 監視銘柄
export SIGNAL_THRESHOLD="2"              # スコア±2以上でアラート
""", language="bash")

    with ntab2:
        st.markdown("### Slack Webhook の設定手順")
        st.markdown("""
1. [Slack API](https://api.slack.com/apps) → 「Create New App」
2. 「Incoming Webhooks」を有効化
3. 「Add New Webhook to Workspace」でチャンネルを選択
4. Webhook URL をコピー（`https://hooks.slack.com/services/...`）
""")

        slack_url = st.text_input("Slack Webhook URL", type="password",
                                   value=os.getenv("SLACK_WEBHOOK_URL", ""),
                                   placeholder="https://hooks.slack.com/services/...")
        if st.button("✅ Slack接続テスト", type="primary"):
            if slack_url:
                from modules.notifier import _slack
                ok = _slack(slack_url, "✅ 株式分析ツールからの接続テストです！通知設定が完了しました。")
                if ok:
                    st.success("送信成功！Slackを確認してください 💬")
                else:
                    st.error("送信失敗。Webhook URLを確認してください。")
            else:
                st.warning("Webhook URLを入力してください")

        st.markdown("---")
        st.code(f"""export SLACK_WEBHOOK_URL="{slack_url or 'your_webhook_url'}"
""", language="bash")

    with ntab3:
        st.markdown("### ⚡ リアルタイムデータの設定")
        st.markdown("""
現在のyfinanceは**最大15分遅延**ですが、以下を設定すると遅延を大幅に短縮できます。
""")

        rt_col1, rt_col2 = st.columns(2)

        with rt_col1:
            st.markdown("#### 🇯🇵 日本株：J-Quants API（無料）")
            st.markdown("""
**JPX（日本取引所グループ）公式のAPI**です。無料プランで日次データが取得できます。

**登録手順：**
1. [J-Quants登録ページ](https://application.jpx-jquants.com/) でメールアドレスを登録
2. メール認証後、ログインしてAPIを有効化
3. 下記にメールアドレスとパスワードを入力
""")
            jq_email = st.text_input("J-Quants メールアドレス",
                                      value=os.getenv("JQUANTS_EMAIL", ""),
                                      placeholder="example@email.com")
            jq_pass = st.text_input("J-Quants パスワード", type="password",
                                     value=os.getenv("JQUANTS_PASSWORD", ""))
            if st.button("✅ J-Quants 接続テスト"):
                if jq_email and jq_pass:
                    try:
                        from modules.data_fetcher import JQuantsClient
                        client = JQuantsClient(jq_email, jq_pass)
                        client._get_refresh_token()
                        st.success("接続成功！日本株がJ-Quantsで取得されます ✅")
                    except Exception as e:
                        st.error(f"接続失敗: {e}")
                else:
                    st.warning("メールアドレスとパスワードを入力してください")
            st.code(f"""# 環境変数に設定
export JQUANTS_EMAIL="{jq_email or 'your@email.com'}"
export JQUANTS_PASSWORD="your_password"
""", language="bash")

        with rt_col2:
            st.markdown("#### 🇺🇸 米国株データ")
            st.info("米国株はyfinanceで自動取得されます。現時点では追加設定不要です。")
            with st.expander("Alpaca Markets（リアルタイム価格・オプション）", expanded=False):
                st.markdown("米国株のリアルタイム価格が必要な場合のみ設定してください。")
                alp_key = st.text_input("Alpaca API Key",
                                         value=os.getenv("ALPACA_API_KEY", ""),
                                         type="password",
                                         placeholder="PKxxxxxx...")
                alp_secret = st.text_input("Alpaca Secret Key",
                                            value=os.getenv("ALPACA_SECRET_KEY", ""),
                                            type="password")
                if st.button("✅ Alpaca 接続テスト"):
                    if alp_key and alp_secret:
                        try:
                            import requests as req
                            resp = req.get(
                                "https://data.alpaca.markets/v2/stocks/AAPL/quotes/latest",
                                headers={"APCA-API-KEY-ID": alp_key,
                                         "APCA-API-SECRET-KEY": alp_secret},
                                timeout=8,
                            )
                            if resp.status_code == 200:
                                price = resp.json().get("quote", {})
                                mid = (price.get("ap", 0) + price.get("bp", 0)) / 2
                                st.success(f"接続成功！AAPL 現在値: ${mid:.2f} ✅")
                            else:
                                st.error(f"接続失敗: {resp.status_code}")
                        except Exception as e:
                            st.error(f"エラー: {e}")
                    else:
                        st.warning("APIキーを入力してください")

        st.markdown("---")
        st.markdown("#### 📊 現在のデータソース状況")
        from modules.data_fetcher import _get_jquants_client
        jq_active = _get_jquants_client() is not None
        alp_active = bool(os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET_KEY"))
        status_data = [
            {"データソース": "yfinance (デフォルト)", "対象": "日米全銘柄",
             "遅延": "最大15分", "状態": "✅ 常時有効"},
            {"データソース": "yfinance fast_info", "対象": "日米全銘柄",
             "遅延": "数分〜ほぼリアル", "状態": "✅ 常時有効（現在価格に使用）"},
            {"データソース": "J-Quants API", "対象": "日本株",
             "遅延": "リアルタイム（翌日分も）",
             "状態": "✅ 設定済み" if jq_active else "❌ 未設定"},
            {"データソース": "Alpaca Markets", "対象": "米国株",
             "遅延": "リアルタイム",
             "状態": "✅ 設定済み" if alp_active else "❌ 未設定"},
        ]
        st.dataframe(pd.DataFrame(status_data), use_container_width=True, hide_index=True)

    with ntab4:
        st.markdown("### 手動でアラートを送信")
        st.caption("設定が正しいか確認するために、任意の銘柄でテスト送信できます")

        test_ticker = st.text_input("銘柄コード", value="7203", key="notif_ticker")
        notif_tg_token = st.text_input("Bot Token（省略時は環境変数）",
                                        type="password", key="notif_tg_token")
        notif_tg_chat = st.text_input("Chat ID（省略時は環境変数）",
                                       key="notif_tg_chat")
        notif_slack = st.text_input("Slack Webhook（省略時は環境変数）",
                                     type="password", key="notif_slack")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("📊 シグナルアラートを送信", type="primary", use_container_width=True):
                with st.spinner(f"{test_ticker} を分析して送信中..."):
                    try:
                        df = fetch_ohlcv(test_ticker, period="3mo")
                        df = compute_all(df)
                        sigs = evaluate_signals(df)
                        verdict, score = overall_signal(sigs)
                        price = df["Close"].iloc[-1]
                        rsi = df["RSI"].dropna().iloc[-1] if "RSI" in df.columns else None
                        atr = df["ATR"].dropna().iloc[-1] if "ATR" in df.columns else None

                        results = send_signal_alert(
                            ticker=test_ticker,
                            verdict=verdict,
                            score=score,
                            price=price,
                            signals=sigs,
                            rsi=rsi,
                            atr=atr,
                            telegram_token=notif_tg_token or None,
                            telegram_chat_id=notif_tg_chat or None,
                            slack_webhook=notif_slack or None,
                        )
                        for ch, ok in results.items():
                            if ok:
                                st.success(f"{ch}: 送信成功 ✅")
                            else:
                                st.error(f"{ch}: 送信失敗 ❌")
                        if not results:
                            st.warning("通知先が設定されていません（環境変数またはフォームに入力）")
                    except Exception as e:
                        st.error(f"エラー: {e}")

        with col_b:
            if st.button("🔍 スクリーニング結果を送信", use_container_width=True):
                with st.spinner("スクリーニング中..."):
                    try:
                        result = screen_single(test_ticker)
                        passed = [test_ticker] if result["合否"] else []
                        results = send_screening_alert(
                            passed,
                            telegram_token=notif_tg_token or None,
                            telegram_chat_id=notif_tg_chat or None,
                            slack_webhook=notif_slack or None,
                        )
                        for ch, ok in results.items():
                            if ok:
                                st.success(f"{ch}: 送信成功 ✅")
                            else:
                                st.error(f"{ch}: 送信失敗 ❌")
                        if not results:
                            st.warning("通知先が設定されていません")
                    except Exception as e:
                        st.error(f"エラー: {e}")

        st.markdown("---")
        st.markdown("### ⏰ 定期自動通知の設定（cron）")
        st.markdown("""
アプリを起動していなくても、定期的にアラートを受け取れます。

**Mac / Linux の場合（crontab）:**
```bash
# crontab を開く
crontab -e

# 平日の朝9時と夕方15時に実行
0 9,15 * * 1-5 cd /path/to/project1 && \\
  TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy \\
  WATCH_TICKERS=7203,9984,AAPL \\
  python alert_runner.py --mode all
```

**Windows の場合（タスクスケジューラ）:**
```
タスクスケジューラ → 基本タスクの作成
→ 毎日 9:00 / 15:00
→ プログラム: python
→ 引数: alert_runner.py --mode all
→ 開始場所: C:\\path\\to\\project1
```

**手動で今すぐ実行:**
```bash
python alert_runner.py                   # 全チェック1回
python alert_runner.py --loop 60         # 60分ごとに繰り返す
python alert_runner.py --mode signal     # シグナルのみ
python alert_runner.py --tickers 7203,AAPL  # 銘柄を指定
```
""")


# ─── 自動売買 ─────────────────────────────────────────────────────────────────
elif page == "🤖 自動売買":
    st.title("🤖 自動売買設定")
    st.caption("シグナルが出たとき、自動で証券会社に注文を送る機能です。まずはペーパートレードで動作確認してください。")

    from modules.auto_trade import AutoTrader
    from modules.broker import PaperBroker
    trader = AutoTrader()
    status = trader.get_status()

    # ── 接続状態 ──────────────────────────────────────────────────────────────
    st.markdown("### 🔌 ブローカー接続状態")
    conn_color = "#26a69a" if status["connected"] else "#ef5350"
    conn_label = "接続中" if status["connected"] else "未接続"
    enabled_color = "#26a69a" if status["enabled"] else "#888"
    enabled_label = "有効" if status["enabled"] else "無効"
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"<div style='background:#1e1e2e;border-radius:10px;padding:14px;text-align:center'>"
                f"<div style='color:#888;font-size:0.8em'>ブローカー</div>"
                f"<div style='font-size:1.1em;font-weight:bold'>{status['broker_name']}</div></div>",
                unsafe_allow_html=True)
    c2.markdown(f"<div style='background:#1e1e2e;border-radius:10px;padding:14px;text-align:center'>"
                f"<div style='color:#888;font-size:0.8em'>接続</div>"
                f"<div style='font-size:1.2em;font-weight:bold;color:{conn_color}'>{conn_label}</div></div>",
                unsafe_allow_html=True)
    c3.markdown(f"<div style='background:#1e1e2e;border-radius:10px;padding:14px;text-align:center'>"
                f"<div style='color:#888;font-size:0.8em'>自動売買</div>"
                f"<div style='font-size:1.2em;font-weight:bold;color:{enabled_color}'>{enabled_label}</div></div>",
                unsafe_allow_html=True)
    c4.markdown(f"<div style='background:#1e1e2e;border-radius:10px;padding:14px;text-align:center'>"
                f"<div style='color:#888;font-size:0.8em'>現金残高</div>"
                f"<div style='font-size:1.2em;font-weight:bold'>{status['cash']:,.0f}円</div></div>",
                unsafe_allow_html=True)

    st.markdown("---")

    # ── タブ ──────────────────────────────────────────────────────────────────
    tab_settings, tab_positions, tab_log, tab_perf, tab_watchlist = st.tabs(["⚙️ 設定", "📊 ポジション", "📋 取引ログ", "📈 成績分析", "🔍 自動ウォッチリスト"])

    with tab_settings:
        broker_choice = "paper"
        st.info("💡 現在はペーパートレード（仮想取引）モードで動作しています。実口座への切り替えはSBI証券のAPI対応後に対応予定です。")

        st.markdown("---")
        st.markdown("#### 取引ルール")
        col_a, col_b = st.columns(2)
        with col_a:
            risk_pct = st.slider(
                "1取引の許容損失（資金の%）",
                min_value=0.5, max_value=5.0, step=0.5,
                value=float(status["settings"].get("risk_pct", 2.0)),
                help="例: 2% → 100万円の場合、1回の損失上限は2万円"
            )
            min_score = st.slider(
                "自動買い発動スコア（最低）",
                min_value=3, max_value=6, step=1,
                value=int(status["settings"].get("min_score", 4)),
                help="スコアがこの値以上のとき自動で買い注文"
            )
        with col_b:
            max_pos_pct = st.slider(
                "1銘柄への最大投資比率（%）",
                min_value=5, max_value=30, step=5,
                value=int(status["settings"].get("max_position_pct", 10)),
                help="1銘柄に資金の何%まで投入するか"
            )
            use_limit = st.checkbox(
                "指値注文を使用（推奨）",
                value=status["settings"].get("use_limit_order", True),
                help="成行注文より不利な価格での約定を防ぐ"
            )

        st.markdown("---")
        st.markdown("#### 自動売買のON/OFF")
        st.warning("⚠️ 実口座で有効にする前に、必ずペーパートレードで動作確認してください。")
        new_enabled = st.toggle(
            "自動売買を有効にする",
            value=status["enabled"],
        )

        if st.button("設定を保存", type="primary"):
            trader.save_settings({
                "broker": broker_choice,
                "risk_pct": risk_pct,
                "max_position_pct": float(max_pos_pct),
                "min_score": min_score,
                "use_limit_order": use_limit,
                "enabled": new_enabled,
            })
            os.environ["BROKER"] = broker_choice
            st.success("設定を保存しました。alert_runner.py を再起動すると反映されます。")

        st.markdown("---")
        st.markdown("#### ペーパートレードのリセット")
        init_cash = st.number_input("初期資金（円）", min_value=100_000, max_value=100_000_000,
                                     value=1_000_000, step=100_000)
        if st.button("ペーパートレードをリセット", type="secondary"):
            from modules.broker import PaperBroker
            pb = PaperBroker(initial_cash=init_cash)
            pb.reset(initial_cash=init_cash)
            st.success(f"リセット完了。初期資金: {init_cash:,.0f}円")
            st.rerun()

    with tab_positions:
        st.markdown("#### 現在のポジション")
        positions = status["positions"]
        if positions:
            pos_df = pd.DataFrame(positions)
            pos_df.columns = ["銘柄", "保有株数", "平均取得価格", "時価評価額", "含み損益"]
            pos_df["含み損益"] = pos_df["含み損益"].apply(
                lambda x: f"+{x:,.0f}" if x > 0 else f"{x:,.0f}"
            )
            st.dataframe(pos_df, use_container_width=True, hide_index=True)
            total_val = sum(p["market_value"] for p in positions)
            total_pnl = sum(p["unrealized_pnl"] for p in positions)
            pnl_color = "#26a69a" if total_pnl >= 0 else "#ef5350"
            m1, m2, m3 = st.columns(3)
            m1.metric("時価評価額合計", f"{total_val:,.0f}円")
            m1.metric("含み損益合計", f"{'+' if total_pnl>=0 else ''}{total_pnl:,.0f}円")
            m2.metric("現金残高", f"{status['cash']:,.0f}円")
            m3.metric("総資産（概算）", f"{status['cash']+total_val:,.0f}円")
        else:
            st.info("現在保有中のポジションはありません。")

    with tab_log:
        st.markdown("#### 取引ログ（ペーパートレードのみ）")
        if status["settings"].get("broker", "paper") == "paper":
            from modules.broker import PaperBroker
            pb = PaperBroker()
            log = pb.get_trade_log()
            if log:
                log_df = pd.DataFrame(log)
                log_df = log_df[["timestamp", "ticker", "side", "qty", "price", "order_type", "status"]]
                log_df.columns = ["日時", "銘柄", "売買", "株数", "価格", "注文種別", "状態"]
                log_df["売買"] = log_df["売買"].map({"buy": "買い", "sell": "売り"})
                st.dataframe(log_df[::-1], use_container_width=True, hide_index=True)
            else:
                st.info("まだ取引履歴がありません。")
        else:
            st.info("取引ログはペーパートレードモードでのみ表示されます。")

    with tab_perf:
        st.markdown("#### 📈 ペーパートレード成績分析")
        from modules.broker import PaperBroker
        import plotly.graph_objects as go
        pb_perf = PaperBroker()
        log_raw = pb_perf.get_trade_log()
        INITIAL_CASH = 1_000_000.0

        if not log_raw:
            st.info("まだ取引履歴がありません。シグナルが出て自動売買が動くと成績が表示されます。")
        else:
            # ── 売買ペアを組み合わせてP&L計算 ──────────────────────────────
            buys = {}   # ticker → [{"price", "qty", "timestamp"}]
            trades_closed = []  # 決済済みトレード
            cash_curve = [{"timestamp": log_raw[0]["timestamp"], "cash": INITIAL_CASH}]
            running_cash = INITIAL_CASH

            for entry in sorted(log_raw, key=lambda x: x["timestamp"]):
                ticker = entry["ticker"]
                qty = entry["qty"]
                price = entry["price"]
                ts = entry["timestamp"]

                if entry["side"] == "buy":
                    buys.setdefault(ticker, []).append({"price": price, "qty": qty, "timestamp": ts})
                    running_cash -= price * qty
                    cash_curve.append({"timestamp": ts, "cash": running_cash})

                elif entry["side"] == "sell":
                    buy_list = buys.get(ticker, [])
                    remaining_sell = qty
                    while remaining_sell > 0 and buy_list:
                        b = buy_list[0]
                        matched = min(b["qty"], remaining_sell)
                        pnl = (price - b["price"]) * matched
                        hold_days = (
                            pd.Timestamp(ts) - pd.Timestamp(b["timestamp"])
                        ).days
                        trades_closed.append({
                            "銘柄": ticker,
                            "買値": b["price"],
                            "売値": price,
                            "株数": matched,
                            "損益": pnl,
                            "保有日数": hold_days,
                            "勝敗": "勝" if pnl > 0 else "負",
                            "決済日時": ts,
                        })
                        b["qty"] -= matched
                        remaining_sell -= matched
                        if b["qty"] == 0:
                            buy_list.pop(0)
                    running_cash += price * qty
                    cash_curve.append({"timestamp": ts, "cash": running_cash})

            # 総資産（現金 + 含み）
            total_unrealized = sum(p["unrealized_pnl"] for p in status["positions"])
            total_assets = status["cash"] + sum(p["market_value"] for p in status["positions"])

            # ── サマリー指標 ──────────────────────────────────────────────
            total_pnl = sum(t["損益"] for t in trades_closed)
            win_count = sum(1 for t in trades_closed if t["損益"] > 0)
            lose_count = sum(1 for t in trades_closed if t["損益"] <= 0)
            total_closed = len(trades_closed)
            win_rate = win_count / total_closed * 100 if total_closed > 0 else 0
            avg_win = (
                sum(t["損益"] for t in trades_closed if t["損益"] > 0) / win_count
                if win_count > 0 else 0
            )
            avg_loss = (
                sum(t["損益"] for t in trades_closed if t["損益"] <= 0) / lose_count
                if lose_count > 0 else 0
            )
            avg_hold = (
                sum(t["保有日数"] for t in trades_closed) / total_closed
                if total_closed > 0 else 0
            )
            pnl_pct = (total_assets - INITIAL_CASH) / INITIAL_CASH * 100

            # ── メトリクス表示 ────────────────────────────────────────────
            sm1, sm2, sm3, sm4 = st.columns(4)
            pnl_delta = f"{'+' if total_pnl>=0 else ''}{total_pnl:,.0f}円"
            sm1.metric("総資産", f"{total_assets:,.0f}円",
                       delta=f"{'+' if pnl_pct>=0 else ''}{pnl_pct:.1f}%")
            sm2.metric("確定損益", pnl_delta)
            sm3.metric("勝率", f"{win_rate:.0f}%",
                       delta=f"{win_count}勝 {lose_count}敗" if total_closed > 0 else "未決済")
            sm4.metric("平均保有日数", f"{avg_hold:.1f}日" if total_closed > 0 else "-")

            sm5, sm6, sm7, sm8 = st.columns(4)
            sm5.metric("平均利益/トレード", f"{avg_win:+,.0f}円" if win_count > 0 else "-")
            sm6.metric("平均損失/トレード", f"{avg_loss:+,.0f}円" if lose_count > 0 else "-")
            rr = abs(avg_win / avg_loss) if avg_loss != 0 else 0
            sm7.metric("リスクリワード比", f"1:{rr:.1f}" if rr > 0 else "-")
            sm8.metric("総取引数（決済済）", f"{total_closed}件")

            st.markdown("---")

            # ── 資産推移グラフ ────────────────────────────────────────────
            st.markdown("##### 資産推移")
            curve_df = pd.DataFrame(cash_curve)
            # 現在の総資産を末尾に追加
            curve_df = pd.concat([
                curve_df,
                pd.DataFrame([{"timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                               "cash": total_assets}])
            ], ignore_index=True)
            curve_df["timestamp"] = pd.to_datetime(curve_df["timestamp"])

            fig_curve = go.Figure()
            fig_curve.add_trace(go.Scatter(
                x=curve_df["timestamp"], y=curve_df["cash"],
                mode="lines+markers",
                line=dict(color="#26a69a", width=2),
                marker=dict(size=6),
                fill="tozeroy",
                fillcolor="rgba(38,166,154,0.1)",
                name="総資産",
            ))
            fig_curve.add_hline(y=INITIAL_CASH, line_dash="dash",
                                line_color="#888", annotation_text="初期資金 100万円")
            fig_curve.update_layout(
                paper_bgcolor="#0e1117", plot_bgcolor="#1a1d23",
                font=dict(color="#fafafa"), height=280,
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis=dict(gridcolor="#2a2d35"),
                yaxis=dict(gridcolor="#2a2d35", tickformat=",.0f"),
                showlegend=False,
            )
            st.plotly_chart(fig_curve, use_container_width=True)

            # ── 銘柄別成績 ────────────────────────────────────────────────
            if trades_closed:
                st.markdown("---")
                st.markdown("##### 銘柄別損益")
                ticker_pnl = {}
                for t in trades_closed:
                    tk = t["銘柄"]
                    ticker_pnl[tk] = ticker_pnl.get(tk, 0) + t["損益"]

                tk_df = pd.DataFrame([
                    {"銘柄": tk, "損益": pnl}
                    for tk, pnl in sorted(ticker_pnl.items(), key=lambda x: x[1], reverse=True)
                ])
                colors = ["#26a69a" if v >= 0 else "#ef5350" for v in tk_df["損益"]]
                fig_tk = go.Figure(go.Bar(
                    x=tk_df["銘柄"], y=tk_df["損益"],
                    marker_color=colors,
                    text=[f"{'+' if v>=0 else ''}{v:,.0f}円" for v in tk_df["損益"]],
                    textposition="outside",
                ))
                fig_tk.update_layout(
                    paper_bgcolor="#0e1117", plot_bgcolor="#1a1d23",
                    font=dict(color="#fafafa"), height=260,
                    margin=dict(l=0, r=0, t=10, b=0),
                    yaxis=dict(gridcolor="#2a2d35", tickformat=",.0f"),
                    xaxis=dict(gridcolor="#2a2d35"),
                    showlegend=False,
                )
                st.plotly_chart(fig_tk, use_container_width=True)

                # ── 決済済みトレード一覧 ──────────────────────────────────
                st.markdown("---")
                st.markdown("##### 決済済みトレード一覧")
                closed_df = pd.DataFrame(trades_closed)
                closed_df["損益"] = closed_df["損益"].apply(
                    lambda x: f"+{x:,.0f}" if x >= 0 else f"{x:,.0f}"
                )
                closed_df = closed_df[["決済日時", "銘柄", "買値", "売値", "株数", "損益", "保有日数", "勝敗"]]
                st.dataframe(closed_df[::-1], use_container_width=True, hide_index=True)

    with tab_watchlist:
        st.markdown("#### 🔍 自動ウォッチリスト管理")
        st.markdown("ユニバースから強いシグナルが出た銘柄を自動でウォッチリストに追加・削除します。")

        from modules.auto_watchlist import load_settings as aw_load, save_settings as aw_save, get_universe_tickers, run_auto_watchlist, load_last_result
        from modules.universe import UNIVERSE
        aw_settings = aw_load()

        # ── ON/OFF ────────────────────────────────────────────────────────
        aw_enabled = st.toggle("自動ウォッチリスト更新を有効にする",
                               value=aw_settings["enabled"],
                               help="毎週月曜朝9時にユニバースをスキャンしてウォッチリストを更新します")

        st.markdown("---")

        # ── スキャン対象カテゴリ ──────────────────────────────────────────
        st.markdown("##### スキャン対象カテゴリ")
        all_categories = list(UNIVERSE.keys())
        selected_cats = st.multiselect(
            "スキャンするカテゴリを選択",
            options=all_categories,
            default=aw_settings.get("categories", ["🇯🇵 日本株メジャー", "🇺🇸 米国大型株（S&P500）"]),
            help="選択したカテゴリの銘柄をシグナルチェックの対象にします",
        )
        if selected_cats:
            n_tickers = len(get_universe_tickers(selected_cats))
            st.caption(f"対象銘柄数: {n_tickers}銘柄（重複除外）")

        st.markdown("---")

        # ── 追加・削除のルール ────────────────────────────────────────────
        st.markdown("##### 追加・削除ルール")
        col_aw1, col_aw2 = st.columns(2)
        with col_aw1:
            add_thresh = st.slider("追加スコア閾値", min_value=2, max_value=6, step=1,
                                   value=aw_settings.get("add_score_threshold", 3),
                                   help="このスコア以上の銘柄をウォッチリストに追加")
            max_size = st.slider("ウォッチリスト最大件数", min_value=5, max_value=50, step=5,
                                 value=aw_settings.get("max_watchlist_size", 20))
        with col_aw2:
            remove_thresh = st.slider("削除スコア閾値", min_value=-6, max_value=-1, step=1,
                                      value=aw_settings.get("remove_score_threshold", -2),
                                      help="このスコア以下が続いた銘柄をウォッチリストから削除")
            remove_days = st.slider("削除までの連続回数", min_value=1, max_value=7, step=1,
                                    value=aw_settings.get("remove_consecutive_days", 3),
                                    help="N回連続で弱シグナルなら削除")

        # ── 保護銘柄（削除しない） ────────────────────────────────────────
        st.markdown("---")
        st.markdown("##### 自動削除しない銘柄（保護）")
        current_watchlist = load_watchlist()
        protected = st.multiselect(
            "削除しない銘柄を選択",
            options=current_watchlist,
            default=aw_settings.get("protected_tickers", []),
            help="手動で追加した銘柄など、自動削除されたくない銘柄を指定",
        )

        # ── 設定保存 ──────────────────────────────────────────────────────
        if st.button("設定を保存", type="primary", key="aw_save"):
            aw_save({
                "enabled": aw_enabled,
                "categories": selected_cats,
                "add_score_threshold": add_thresh,
                "remove_score_threshold": remove_thresh,
                "remove_consecutive_days": remove_days,
                "max_watchlist_size": max_size,
                "protected_tickers": protected,
            })
            st.success("設定を保存しました。次の月曜朝9時から自動スキャンが始まります。")

        st.markdown("---")

        # ── 今すぐスキャン ────────────────────────────────────────────────
        st.markdown("##### 今すぐスキャンを実行")
        n_targets = len(get_universe_tickers(selected_cats))
        st.caption(f"選択中のカテゴリ: {len(selected_cats)}カテゴリ / {n_targets}銘柄 ── 完了まで約{max(1, n_targets // 15)}〜{max(2, n_targets // 8)}分かかります")
        if st.button("🔍 今すぐスキャン実行", type="secondary", key="aw_scan"):
            if not selected_cats:
                st.error("スキャンするカテゴリを1つ以上選択してください")
            else:
                aw_save({
                    "enabled": True,
                    "categories": selected_cats,
                    "add_score_threshold": add_thresh,
                    "remove_score_threshold": remove_thresh,
                    "remove_consecutive_days": remove_days,
                    "max_watchlist_size": max_size,
                    "protected_tickers": protected,
                })
                try:
                    with st.spinner(f"{n_targets}銘柄をスキャン中... しばらくお待ちください（{max(1, n_targets // 15)}〜{max(2, n_targets // 8)}分）"):
                        run_auto_watchlist(verbose=False)
                    aw_save({"enabled": aw_enabled})
                    st.rerun()
                except Exception as e:
                    aw_save({"enabled": aw_enabled})
                    st.error(f"スキャン中にエラーが発生しました: {e}")

        # 前回のスキャン結果をファイルから常時表示
        last = load_last_result()
        if last:
            st.markdown("---")
            st.markdown(f"##### 📋 前回のスキャン結果　`{last.get('timestamp', '')}`")
            if last.get("added") or last.get("removed"):
                if last.get("added"):
                    st.success(f"✅ 追加: {', '.join(last['added'])}（{len(last['added'])}銘柄）")
                if last.get("removed"):
                    st.warning(f"❌ 削除: {', '.join(last['removed'])}（{len(last['removed'])}銘柄）")
                if last.get("skipped", 0) > 0:
                    st.caption(f"上限のため{last['skipped']}銘柄をスキップ")
            else:
                st.info(f"変更なし（{last.get('scanned', 0)}銘柄をスキャン済み）")
            scores = last.get("scores", {})
            if scores:
                score_rows = sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True)
                score_df = pd.DataFrame([
                    {"銘柄": t, "シグナル": v["verdict"], "スコア": f"{v['score']:+d}"}
                    for t, v in score_rows
                ])
                st.dataframe(score_df, use_container_width=True, hide_index=True, height=300)


# ─── トレードガイド ───────────────────────────────────────────────────────────
elif page == "📖 トレードガイド":
    st.title("📖 トレードガイド")
    st.markdown("通知を受けてから購入・保有・売却まで、このシステムをどう使うかをステップで説明します。")

    guide_tab1, guide_tab2, guide_tab3 = st.tabs([
        "🗺️ 全体フロー",
        "📋 各ステップ詳細",
        "❓ よくある疑問",
    ])

    with guide_tab1:
        st.markdown("### 🗺️ 売買の全体フロー")
        st.markdown("""
```
【毎朝・毎夕 2分チェック】
       ↓
  🌐 マクロ・ニュース
  「今日の市場は強気？弱気？」を確認
       ↓
  🏠 ダッシュボード
  ウォッチリスト銘柄のシグナルを一覧確認
       ↓
  🔔 強い買いシグナル通知（スマホ）
  スコア+4以上で自動的にTelegramに届く
       ↓
  📊 テクニカル分析で確認（2〜3分）
  シグナル・チャート・マルチタイムフレームを見る
       ↓
  ✅ エントリー判断（買うか見送るか）
       ↓
  📔 投資日記に購入記録（必ず損切りライン設定）
       ↓
  🏠 ダッシュボードで毎日監視
  損切りライン近づくと🚨通知が届く
       ↓
  📊 売りシグナル確認（テクニカル分析）
       ↓
  📔 投資日記に売却記録・損益確認
```
""")

        st.markdown("---")
        st.markdown("### ⏱️ 1日の時間配分（目安）")
        time_table = [
            {"時間帯": "朝 8:50〜9:00（10分）", "やること": "マクロ確認 → ダッシュボードでシグナル確認",
             "ページ": "🌐 マクロ・ニュース → 🏠 ダッシュボード"},
            {"時間帯": "必要時のみ（5〜10分）", "やること": "買いシグナルが来た銘柄のテクニカル分析",
             "ページ": "📊 テクニカル分析"},
            {"時間帯": "夕方 15:30〜（5分）", "やること": "ダッシュボード確認・損切りラインの確認",
             "ページ": "🏠 ダッシュボード"},
            {"時間帯": "週末（15〜30分）", "やること": "週次振り返り・ポートフォリオ確認",
             "ページ": "📔 投資日記 → 📐 ポートフォリオ"},
        ]
        st.dataframe(pd.DataFrame(time_table), use_container_width=True, hide_index=True)

    with guide_tab2:
        st.markdown("### 📋 各ステップの詳細")

        with st.expander("**STEP 1: マクロ確認（毎朝30秒）**", expanded=True):
            st.markdown("""
**ページ: 🌐 マクロ・ニュース → 「リアルタイム市場データ」タブ**

1. **「🔄 今すぐ更新」** ボタンを押す
2. **市場センチメント** を確認
   - 🟢 **強気・やや強気** → 通常通り判断してOK
   - 🟡 **中立** → 新規買いは慎重に。小さめポジションで
   - 🔴 **弱気** → 新規買いは見送り。既存保有の損切りラインを確認
3. **セクター影響** を確認 → 今日注目するセクターを把握

**ポイント:** 市場全体が弱い日はいくら良いシグナルが出ても確率が下がります
""")

        with st.expander("**STEP 2: ダッシュボード確認（毎朝1分）**"):
            st.markdown("""
**ページ: 🏠 ダッシュボード**

1. ウォッチリストの一覧を確認
2. **スコアが高い（+3以上）** 銘柄に注目
3. **「強い買い」シグナル** が出ている銘柄を次のステップへ

**補足:** スマホのTelegramに通知が届いた場合も同じ銘柄を確認しに来ます
""")

        with st.expander("**STEP 3: テクニカル分析で詳細確認（5〜10分）**"):
            st.markdown("""
**ページ: 📊 テクニカル分析**

サイドバーで銘柄を選択してから:

1. **チャート** で現在のトレンドを目視確認
   - 移動平均線（SMA25/SMA75）の向き
   - 最近の高値・安値の動き

2. **シグナル一覧** でスコアを確認
   - +4以上: 強い買いサイン
   - +2〜3: 買い候補（様子見もあり）
   - マイナス: まだ早い

3. **マルチタイムフレーム** ボタンを押す
   - 週足・日足・1時間足が同じ方向か確認
   - 3つ揃ってたら信頼度大

4. **決算日** に注意（赤バナーが出たら決算直前 → ポジション小さく）

5. **ポジションサイズ計算** で何株買うか計算
""")

        with st.expander("**STEP 4: エントリー判断チェックリスト**"):
            st.markdown("""
以下の条件を確認してから注文を出してください:

| 確認項目 | 基準 |
|---|---|
| ① マクロセンチメント | 中立以上（弱気なら見送り推奨） |
| ② シグナルスコア | +3以上 |
| ③ RSI | 30〜65の範囲（70超は過熱） |
| ④ 移動平均線 | 株価がSMA25・SMA75より上 |
| ⑤ マルチタイムフレーム | 週足・日足が同じ方向 |
| ⑥ 決算日 | 14日以内でないこと（リスク高） |
| ⑦ 損切りライン | 買値の-5〜-8%を事前に決めた |

**「5つ以上OK」なら買い。3つ以下なら見送り。**
""")

        with st.expander("**STEP 5: 購入後 → 投資日記に記録（必須）**"):
            st.markdown("""
**ページ: 📔 投資日記**

記録する内容:
- 銘柄コード
- 購入価格・株数
- **損切りライン（← これが最重要！）**
  - 目安: 購入価格の-5〜-8%
  - ATRの2倍分下に設定するのも有効（テクニカル分析画面で確認）
- 購入理由（シグナルのスコア、主な根拠）

**なぜ記録が必要か:**
損切りラインを決めておかないと、「もう少し待てば上がるかも」と判断が揺れて大損します。
事前に決めたルールを守ることが長期的な利益につながります。
""")

        with st.expander("**STEP 6: 保有中の管理（毎夕1分）**"):
            st.markdown("""
**ページ: 🏠 ダッシュボード**

毎日確認すること:
1. 保有銘柄の現在値と前日比
2. **損切りラインに近づいていないか**
   - 通知設定済みなら🚨アラートが届く
3. テクニカル分析で **「保有継続判定」** を確認
   - 「継続保有OK」: 何もしない
   - 「注意」: 損切りラインを引き上げることを検討
   - 「売り検討」: 売却の準備

**保有の目安期間:**
- スイング取引: 1〜3週間
- 長期: 3ヶ月以上（ファンダメンタル面も確認）
""")

        with st.expander("**STEP 7: 売却判断**"):
            st.markdown("""
以下のいずれかに該当したら売却を検討:

| 売却サイン | 対応 |
|---|---|
| 🚨 **損切りライン到達** | 迷わず売る（損を小さく抑える最重要ルール） |
| 🔴 **シグナルスコアがマイナスに転落** | 売り検討（トレンド転換の可能性） |
| 📉 **RSIが75以上の過熱** | 一部利確を検討 |
| 🎯 **目標価格到達** | 利確（または損切りラインを引き上げて継続） |
| ⚠️ **決算前14日以内** | ポジションを半分に減らすのが無難 |

**最も大切なルール:**
「損切りラインに来たら必ず売る」。この一つを守るだけで大損は防げます。
""")

        with st.expander("**STEP 8: 売却後 → 日記に記録・振り返り**"):
            st.markdown("""
**ページ: 📔 投資日記**

売却後にやること:
1. 売却価格・損益を記録
2. **振り返りタブで週次レビューを書く**
   - うまくいったこと
   - うまくいかなかったこと
   - 次回改善すること

振り返りを続けることで、自分がどのシグナルで勝率が高いかが見えてきます。
""")

    with guide_tab3:
        st.markdown("### ❓ よくある疑問")

        with st.expander("**Q: 通知が来たら必ず買わないといけないの？**"):
            st.markdown("""
**A: いいえ、通知は「候補を教えてくれるもの」です。**

通知が来てからテクニカル分析画面で確認し、自分でOKと判断してから買ってください。
以下のどれかに当てはまる場合は見送りが賢明です:
- マクロが弱気
- RSIが70以上（過熱）
- 決算が2週間以内
- チャートを見て「なんかおかしい」と感じる
""")

        with st.expander("**Q: シグナルが「買い」でも下がることはある？**"):
            st.markdown("""
**A: はい、あります。シグナルは確率を上げるツールです。**

どんな優れた指標でも正解率は60〜70%程度です。
だから **損切りライン** が重要です。

- 勝率70%・利益率10%・損切り5% で計算すると:
  - 10回中7回勝ち → +70%
  - 10回中3回負け → -15%
  - 合計: +55%（十分な利益）

負けを小さく抑えれば、勝率70%で長期的には必ずプラスになります。
""")

        with st.expander("**Q: 1日に何銘柄まで保有すればいい？**"):
            st.markdown("""
**A: 初心者は2〜3銘柄、慣れてきたら5銘柄程度が目安です。**

多すぎると管理できなくなり、損切りのタイミングを逃します。
少ない銘柄数で確実な管理をする方が長期的に有利です。
""")

        with st.expander("**Q: どのくらいの資金で始めればいい？**"):
            st.markdown("""
**A: 最初は「失っても生活に支障のない金額」で始めてください。**

ポジションサイズの計算ツール（テクニカル分析ページ）を使えば、
総資金の何%を1銘柄に投入するかを計算できます。

目安:
- 1銘柄あたり総資金の10〜20%まで
- 損切り設定: 総資金の1〜2%以内のリスクになるよう調整
""")

        with st.expander("**Q: このシステムは完璧に機能するの？**"):
            st.markdown("""
**A: 完璧ではありません。ツールは判断を助けるものです。**

このシステムが提供するのは:
- ✅ 見落としを減らす（複数の指標を自動チェック）
- ✅ 感情的な判断を減らす（ルールベースのシグナル）
- ✅ 損切りリマインダー（ダッシュボードでの監視）
- ✅ 振り返りによる自己改善

このシステムが補えないもの:
- ❌ 突発的なニュース・事件（ブラックスワン）
- ❌ 市場の急変動
- ❌ 最終的な投資判断

**投資は自己責任です。損失リスクを理解した上でご利用ください。**
""")

        st.markdown("---")
        st.info("💡 **最初の1ヶ月は「少額で試してみる」期間と割り切って、ルールに従って実際に操作することを優先しましょう。**")
