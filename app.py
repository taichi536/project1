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

from modules.data_fetcher import fetch_ohlcv, fetch_info
from modules.technical import compute_all
from modules.signals import evaluate_signals, overall_signal, generate_action_plan
from modules.charts import build_main_chart
from modules.fundamental import get_fundamental_summary, get_risk_metrics
from modules.screening import screen_single
from modules.diary import add_trade, get_trades, add_review, get_reviews, trade_stats, init_db, calc_pnl, calc_unrealized
from modules.ai_analysis import analyze_five_forces, analyze_chart_ai
from modules.news_fetcher import fetch_market_news, score_macro_relevance
from modules.macro_analysis import get_macro_context, analyze_news_sentiment, quick_market_sentiment
from modules.backtest import run_backtest, STRATEGIES
from modules.portfolio import build_portfolio_summary
from modules.charts import build_backtest_chart, build_correlation_heatmap, build_portfolio_pie
from modules.notifier import send_signal_alert, send_screening_alert, send_stop_loss_alert
from modules.dashboard import load_watchlist, save_watchlist, scan_all
from modules.ml_model import train_model, trend_regression, detect_candlestick_patterns
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

    page = st.radio(
        "メニュー",
        ["🏠 ダッシュボード", "🔭 銘柄スキャン", "📊 テクニカル分析", "🔍 スクリーニング", "📋 ファンダメンタル分析", "🌐 マクロ・ニュース", "🔬 バックテスト", "📐 ポートフォリオ", "📔 投資日記", "🔔 通知設定"],
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
    st.caption("登録銘柄のシグナルを一覧で確認できます")

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
        # シグナル変化を検出
        for r in new_data:
            prev_sig = prev_data.get(r["ticker"])
            r["シグナル変化"] = (prev_sig is not None and prev_sig != r["シグナル"])
            r["前回シグナル"] = prev_sig
        st.session_state["dashboard_data"] = new_data

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
                    st.session_state["menu_page"] = "📊 テクニカル分析"
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
                st.session_state["menu_page"] = "📊 テクニカル分析"
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
                    st.session_state["menu_page"] = "📊 テクニカル分析"
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
        reasons_html = "　".join(
            f"<span style='background:{'#1e3a2f' if s['スコア']>0 else '#3a1e1e'};padding:2px 8px;border-radius:12px;font-size:0.85em'>"
            f"{'✅' if s['スコア']>0 else '⚠️'} {s['指標'].split('(')[0].strip()}: {s['判定']}</span>"
            for s in top2
        )

        st.markdown(
            f"""<div style="background:{sig_color}22;border:2px solid {sig_color};
                border-radius:16px;padding:24px;text-align:center;margin-bottom:16px">
                <div style="font-size:3em">{sig_emoji}</div>
                <div style="font-size:2em;font-weight:bold;color:{sig_color}">{verdict}</div>
                <div style="font-size:1.1em;color:#ccc;margin-top:4px">{sig_msg}</div>
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

        # チャート
        fig = build_main_chart(df, ticker, sma_short=sma_short, sma_long=sma_long)
        st.plotly_chart(fig, use_container_width=True)

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
                f"🔴 **売り・見送りを検討するタイミング：** {plan['sell_trigger']}"
            )
            st.caption("💡 「様子見」は最も多い判定です。相場の70〜80%の時間は様子見が正解です。焦らず待つことも立派な投資判断です。")

        # 初心者モードでは指標テーブルを折りたたみ
        if st.session_state.get("beginner_mode", True):
            with st.expander("📊 各指標の詳細データ（上級者向け）", expanded=False):
                sig_df = pd.DataFrame(signals)
                sig_df["判定"] = sig_df.apply(
                    lambda r: ("🟢 " if r["スコア"] > 0 else ("🔴 " if r["スコア"] < 0 else "🟡 ")) + r["判定"],
                    axis=1,
                )
                st.dataframe(sig_df[["指標", "値", "判定"]], use_container_width=True, hide_index=True)
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
            sig_df = pd.DataFrame(signals)
            sig_df["判定"] = sig_df.apply(
                lambda r: ("🟢 " if r["スコア"] > 0 else ("🔴 " if r["スコア"] < 0 else "🟡 ")) + r["判定"],
                axis=1,
            )
            st.dataframe(sig_df[["指標", "値", "判定"]], use_container_width=True, hide_index=True)
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

        st.markdown("#### 🤖 機械学習シグナル予測（RandomForest + GradientBoosting）")
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

                # 上昇確率ゲージ
                st.markdown(
                    f"""<div style="background:#1a1d23;border-radius:8px;height:20px;margin:8px 0">
                    <div style="width:{prob}%;background:{ml_color};height:20px;border-radius:8px;
                         display:flex;align-items:center;justify-content:center;
                         color:white;font-size:0.8em;font-weight:bold">{prob}%</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
                st.caption("⚠️ 機械学習の予測は参考情報です。過去のパターンが未来に繰り返される保証はありません。")

                # 特徴量重要度
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
                    st.plotly_chart(fig_fi, use_container_width=True)

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
    st.markdown("社会情勢・経済指標・最新ニュースから相場への影響を分析します")

    macro_tab1, macro_tab2 = st.tabs(["📰 市場ニュース＆センチメント", "📊 マクロ経済指標"])

    with macro_tab1:
        col_l, col_r = st.columns([1, 2])
        with col_l:
            ticker_macro = st.text_input("個別銘柄への影響を分析（任意）", placeholder="7203 / AAPL")
        with col_r:
            st.markdown("")  # spacer
        news_btn = st.button("📰 ニュース取得＆分析", type="primary")

        if news_btn:
            with st.spinner("ニュースを収集中..."):
                news = fetch_market_news(max_per_source=5)

            if news:
                st.success(f"{len(news)}件のニュースを取得しました")

                # 市場全体センチメント
                st.markdown("### 🎯 市場センチメント（AI判定）")
                if not (st.session_state.get("ai_enabled") and os.getenv("ANTHROPIC_API_KEY")):
                    st.warning("ANTHROPIC_API_KEY が未設定です。")
                else:
                    with st.spinner("AIが市場センチメントを判定中..."):
                        try:
                            sentiment = quick_market_sentiment(news)
                            lines = sentiment.strip().split("\n")
                            for line in lines:
                                if "強気" in line:
                                    st.success(line)
                                elif "弱気" in line:
                                    st.error(line)
                                elif "中立" in line:
                                    st.warning(line)
                                else:
                                    st.info(line)
                        except Exception as e:
                            st.warning(f"センチメント分析エラー: {e}")

                # ニュース一覧
                st.markdown("### 📋 注目ニュース")
                high = [n for n in news if score_macro_relevance(n["title"], n.get("summary", "")) >= 2]
                other = [n for n in news if score_macro_relevance(n["title"], n.get("summary", "")) < 2]

                if high:
                    st.markdown("**🔴 マクロ高関連ニュース**")
                    for n in high[:8]:
                        st.markdown(f"- **[{n['source']}]** {n['title']}")
                        if n.get("summary"):
                            st.caption(f"  {n['summary'][:120]}...")

                if other:
                    with st.expander(f"その他のニュース（{len(other)}件）"):
                        for n in other[:10]:
                            st.markdown(f"- [{n['source']}] {n['title']}")

                # 個別銘柄への影響分析
                if ticker_macro and st.session_state.get("ai_enabled") and os.getenv("ANTHROPIC_API_KEY"):
                    st.markdown(f"### 🔍 {ticker_macro} への影響分析")
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
            else:
                st.warning("ニュースを取得できませんでした。ネットワーク接続を確認してください。")

    with macro_tab2:
        st.markdown("### 📊 主要マクロ経済指標")
        st.caption("投資判断に使うマクロコンテキスト（手動更新・随時見直し）")

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
        st.markdown("#### 📌 投資に関わる主要イベントカレンダー")
        events = [
            {"日付": "随時", "イベント": "日銀金融政策決定会合", "注目度": "★★★", "影響": "円相場・金融株・REITに直結"},
            {"日付": "毎月初旬", "イベント": "米雇用統計 (NFP)", "注目度": "★★★", "影響": "FRB政策観測・ドル円に影響"},
            {"日付": "毎月中旬", "イベント": "米CPI（消費者物価指数）", "注目度": "★★★", "影響": "インフレ→利下げ観測→グロース株"},
            {"日付": "四半期", "イベント": "決算シーズン（3・6・9・12月）", "注目度": "★★★", "影響": "個別株の最大の変動要因"},
            {"日付": "随時", "イベント": "地政学リスク（中東・台湾海峡等）", "注目度": "★★☆", "影響": "リスクオフ・原油・防衛株"},
            {"日付": "随時", "イベント": "米中貿易摩擦・関税動向", "注目度": "★★☆", "影響": "製造業・半導体・自動車に逆風"},
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
        st.plotly_chart(fig_bt, use_container_width=True)

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
        st.markdown("""
**ステップ1: Bot を作る（1分）**
1. スマホの Telegram で [@BotFather](https://t.me/BotFather) を開く
2. `/newbot` と送信
3. Bot名を入力（例: `MyStockBot`）
4. Bot Token が発行される（例: `1234567890:ABCdef...`）

**ステップ2: Chat ID を取得する**
1. 作った Bot に何かメッセージを送る
2. ブラウザで以下のURLを開く（tokenを置き換える）
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
3. `"chat":{"id": 123456789}` の数字が Chat ID
""")

        st.markdown("### 認証情報を入力")
        tg_token = st.text_input("Bot Token", type="password",
                                  value=os.getenv("TELEGRAM_BOT_TOKEN", ""),
                                  placeholder="1234567890:ABCdefGHI...")
        tg_chat = st.text_input("Chat ID",
                                 value=os.getenv("TELEGRAM_CHAT_ID", ""),
                                 placeholder="123456789")

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
            st.markdown("#### 🇺🇸 米国株：Alpaca Markets（無料）")
            st.markdown("""
**米国株のリアルタイム価格**が無料で取得できます。

**登録手順：**
1. [Alpaca Markets](https://alpaca.markets/) でアカウント作成（無料）
2. ダッシュボード → 「API Keys」でキーを発行
3. 下記に入力（Paper Trading キーでOK）
""")
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
            st.code(f"""export ALPACA_API_KEY="{alp_key or 'your_api_key'}"
export ALPACA_SECRET_KEY="{alp_secret or 'your_secret_key'}"
""", language="bash")

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
