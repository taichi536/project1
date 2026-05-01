import streamlit as st
import pandas as pd
import os

st.set_page_config(
    page_title="株式売買タイミング分析ツール",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

from modules.data_fetcher import fetch_ohlcv, fetch_info
from modules.technical import compute_all
from modules.signals import evaluate_signals, overall_signal
from modules.charts import build_main_chart
from modules.fundamental import get_fundamental_summary, get_risk_metrics
from modules.screening import screen_single
from modules.diary import add_trade, get_trades, add_review, get_reviews, trade_stats, init_db
from modules.ai_analysis import analyze_five_forces, analyze_chart_ai

init_db()

# ─── サイドバー ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📈 株式分析ツール")
    st.markdown("---")
    page = st.radio(
        "メニュー",
        ["テクニカル分析", "スクリーニング", "ファンダメンタル分析", "投資日記"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.caption("日本株: 7203 → 7203.T 自動変換")
    st.caption("米国株: AAPL, MSFT など")


# ─── テクニカル分析 ───────────────────────────────────────────────────────────
if page == "テクニカル分析":
    st.title("📊 テクニカル分析")

    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    with col1:
        ticker = st.text_input("銘柄コード", value="7203", placeholder="例: 7203 / AAPL")
    with col2:
        period = st.selectbox("期間", ["3mo", "6mo", "1y", "2y"], index=1,
                              format_func=lambda x: {"3mo": "3ヶ月", "6mo": "6ヶ月", "1y": "1年", "2y": "2年"}[x])
    with col3:
        sma_short = st.number_input("短期MA", value=25, min_value=5, max_value=50, step=5)
    with col4:
        sma_long = st.number_input("長期MA", value=75, min_value=20, max_value=200, step=5)

    analyze_btn = st.button("🔍 分析する", type="primary", use_container_width=True)

    if analyze_btn and ticker:
        with st.spinner("データ取得中..."):
            try:
                df = fetch_ohlcv(ticker, period=period)
                df = compute_all(df, sma_short=sma_short, sma_long=sma_long)
                signals = evaluate_signals(df, sma_short=sma_short, sma_long=sma_long)
                verdict, score = overall_signal(signals)
            except Exception as e:
                st.error(f"データ取得エラー: {e}")
                st.stop()

        # 総合シグナル表示
        st.markdown("### 総合シグナル")
        emoji = {"買い": "🟢", "売り": "🔴", "様子見": "🟡"}.get(verdict, "⚪")
        color = {"買い": "#26a69a", "売り": "#ef5350", "様子見": "#ffd54f"}.get(verdict, "#888")

        col_sig, col_price, col_rsi, col_atr = st.columns(4)
        col_sig.metric("シグナル", f"{emoji} {verdict}", f"スコア: {score:+d}")
        col_price.metric("現在値", f"{df['Close'].iloc[-1]:.2f}")
        rsi_val = df["RSI"].dropna().iloc[-1] if "RSI" in df.columns else None
        atr_val = df["ATR"].dropna().iloc[-1] if "ATR" in df.columns else None
        col_rsi.metric("RSI", f"{rsi_val:.1f}" if rsi_val else "N/A")
        col_atr.metric("ATR（ボラティリティ）", f"{atr_val:.2f}" if atr_val else "N/A")

        # チャート
        fig = build_main_chart(df, ticker, sma_short=sma_short, sma_long=sma_long)
        st.plotly_chart(fig, use_container_width=True)

        # 指標テーブル
        st.markdown("### 指標別シグナル一覧")
        sig_df = pd.DataFrame(signals)
        sig_df["判定"] = sig_df.apply(
            lambda r: ("🟢 " if r["スコア"] > 0 else ("🔴 " if r["スコア"] < 0 else "🟡 ")) + r["判定"],
            axis=1,
        )
        st.dataframe(sig_df[["指標", "値", "判定"]], use_container_width=True, hide_index=True)

        # 損切りライン
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

        # AI分析
        st.markdown("### 🤖 AIチャート解説")
        if not os.getenv("ANTHROPIC_API_KEY"):
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


# ─── スクリーニング ────────────────────────────────────────────────────────────
elif page == "スクリーニング":
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
elif page == "ファンダメンタル分析":
    st.title("📋 ファンダメンタル分析")

    ticker_fa = st.text_input("銘柄コード", value="7203", key="fa_ticker")
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
            if not os.getenv("ANTHROPIC_API_KEY"):
                st.warning("ANTHROPIC_API_KEY が未設定です。")
            else:
                with st.spinner("AIがファイブフォース分析中..."):
                    try:
                        ff = analyze_five_forces(summary["企業名"], summary["セクター"], summary["業種"])
                        st.markdown(ff)
                    except Exception as e:
                        st.warning(f"AI分析エラー: {e}")


# ─── 投資日記 ─────────────────────────────────────────────────────────────────
elif page == "投資日記":
    st.title("📔 投資日記")

    tab1, tab2, tab3 = st.tabs(["📝 取引記録", "📊 パフォーマンス", "🔄 振り返り"])

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

    with tab3:
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
