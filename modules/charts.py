import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


COLORS = {
    "up": "#26a69a",
    "down": "#ef5350",
    "sma_short": "#ff9800",
    "sma_long": "#2196f3",
    "bb": "rgba(100,181,246,0.3)",
    "ichimoku_bull": "rgba(38,166,154,0.2)",
    "ichimoku_bear": "rgba(239,83,80,0.2)",
    "macd": "#7e57c2",
    "signal": "#ff7043",
    "hist_pos": "#26a69a",
    "hist_neg": "#ef5350",
    "rsi": "#ffd54f",
    "volume": "rgba(100,181,246,0.5)",
    "obv": "#80cbc4",
}


def build_main_chart(df: pd.DataFrame, ticker: str, sma_short: int = 25, sma_long: int = 75) -> go.Figure:
    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        row_heights=[0.5, 0.15, 0.2, 0.15],
        vertical_spacing=0.02,
        subplot_titles=("株価チャート", "出来高 / OBV", "MACD", "RSI / ストキャスティクス"),
    )

    # ローソク足
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"],
        increasing_line_color=COLORS["up"], decreasing_line_color=COLORS["down"],
        name="株価",
    ), row=1, col=1)

    # ボリンジャーバンド
    if "BB_upper" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["BB_upper"], line=dict(color="rgba(100,181,246,0.5)", width=1),
            name="BB上限", showlegend=False,
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["BB_lower"], line=dict(color="rgba(100,181,246,0.5)", width=1),
            fill="tonexty", fillcolor=COLORS["bb"], name="BB", showlegend=False,
        ), row=1, col=1)

    # 移動平均
    for col, color, name in [
        (f"SMA{sma_short}", COLORS["sma_short"], f"SMA{sma_short}"),
        (f"SMA{sma_long}", COLORS["sma_long"], f"SMA{sma_long}"),
    ]:
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[col], line=dict(color=color, width=1.5),
                name=name,
            ), row=1, col=1)

    # 一目均衡表（雲）
    if "Ichimoku_senkou_a" in df.columns and "Ichimoku_senkou_b" in df.columns:
        senkou_a = df["Ichimoku_senkou_a"]
        senkou_b = df["Ichimoku_senkou_b"]
        bull = senkou_a >= senkou_b
        for is_bull in [True, False]:
            mask = bull if is_bull else ~bull
            color = COLORS["ichimoku_bull"] if is_bull else COLORS["ichimoku_bear"]
            fig.add_trace(go.Scatter(
                x=df.index[mask], y=senkou_a[mask],
                line=dict(color="rgba(0,0,0,0)"), showlegend=False,
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=df.index[mask], y=senkou_b[mask],
                fill="tonexty", fillcolor=color,
                line=dict(color="rgba(0,0,0,0)"),
                name="雲（一目）" if is_bull else None, showlegend=is_bull,
            ), row=1, col=1)

    # 出来高
    colors_vol = [COLORS["up"] if c >= o else COLORS["down"] for c, o in zip(df["Close"], df["Open"])]
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], marker_color=colors_vol, name="出来高", showlegend=False), row=2, col=1)

    # OBV
    if "OBV" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["OBV"], line=dict(color=COLORS["obv"], width=1.5),
            name="OBV", yaxis="y5",
        ), row=2, col=1)

    # MACD
    if "MACD" in df.columns:
        hist_colors = [COLORS["hist_pos"] if v >= 0 else COLORS["hist_neg"] for v in df["MACD_hist"].fillna(0)]
        fig.add_trace(go.Bar(x=df.index, y=df["MACD_hist"], marker_color=hist_colors, name="ヒスト", showlegend=False), row=3, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["MACD"], line=dict(color=COLORS["macd"], width=1.5), name="MACD"), row=3, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["MACD_signal"], line=dict(color=COLORS["signal"], width=1.5, dash="dot"), name="シグナル"), row=3, col=1)

    # RSI
    if "RSI" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["RSI"], line=dict(color=COLORS["rsi"], width=1.5), name="RSI"), row=4, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="rgba(255,100,100,0.5)", row=4, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="rgba(100,255,100,0.5)", row=4, col=1)

    # ストキャスティクス
    if "Stoch_K" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["Stoch_K"], line=dict(color="#e91e63", width=1, dash="dot"), name="%K"), row=4, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["Stoch_D"], line=dict(color="#9c27b0", width=1, dash="dot"), name="%D"), row=4, col=1)

    fig.update_layout(
        title=f"{ticker} テクニカルチャート",
        height=900,
        xaxis_rangeslider_visible=False,
        paper_bgcolor="#0e1117",
        plot_bgcolor="#1a1d23",
        font=dict(color="#fafafa"),
        legend=dict(orientation="h", y=1.02, x=0),
    )
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.05)")
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.05)")

    return fig


def build_backtest_chart(pv: pd.DataFrame, trades_df: pd.DataFrame, ticker: str) -> go.Figure:
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.7, 0.3],
        vertical_spacing=0.03,
        subplot_titles=("資産推移（戦略 vs Buy&Hold）", "ドローダウン (%)"),
    )

    fig.add_trace(go.Scatter(
        x=pv.index, y=pv["総資産"],
        line=dict(color="#26a69a", width=2),
        name="戦略資産",
    ), row=1, col=1)

    if "Buy&Hold" in pv.columns:
        fig.add_trace(go.Scatter(
            x=pv.index, y=pv["Buy&Hold"],
            line=dict(color="#7e57c2", width=1.5, dash="dot"),
            name="Buy & Hold",
        ), row=1, col=1)

    # 取引マーカー
    if not trades_df.empty and "日付" in trades_df.columns:
        buys = trades_df[trades_df["種別"] == "買い"]
        sells = trades_df[trades_df["種別"] == "売り"]
        stoplosses = trades_df[trades_df["種別"] == "損切り売"]

        for subset, color, symbol, name in [
            (buys, "#26a69a", "triangle-up", "買い"),
            (sells, "#7e57c2", "triangle-down", "売り"),
            (stoplosses, "#ef5350", "x", "損切り"),
        ]:
            if not subset.empty:
                dates = pd.to_datetime(subset["日付"])
                vals = [pv.loc[pv.index.asof(d), "総資産"] if d in pv.index else None for d in dates]
                fig.add_trace(go.Scatter(
                    x=dates, y=vals,
                    mode="markers",
                    marker=dict(symbol=symbol, size=10, color=color),
                    name=name,
                ), row=1, col=1)

    # ドローダウン
    if "ドローダウン(%)" in pv.columns:
        fig.add_trace(go.Scatter(
            x=pv.index, y=pv["ドローダウン(%)"],
            fill="tozeroy", fillcolor="rgba(239,83,80,0.2)",
            line=dict(color="#ef5350", width=1),
            name="ドローダウン",
        ), row=2, col=1)
        fig.add_hline(y=0, line_color="rgba(255,255,255,0.2)", row=2, col=1)

    fig.update_layout(
        title=f"{ticker} バックテスト結果",
        height=650,
        paper_bgcolor="#0e1117",
        plot_bgcolor="#1a1d23",
        font=dict(color="#fafafa"),
        legend=dict(orientation="h", y=1.02, x=0),
    )
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.05)")
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.05)")
    return fig


def build_correlation_heatmap(corr: "pd.DataFrame") -> go.Figure:
    import plotly.express as px
    fig = px.imshow(
        corr,
        color_continuous_scale="RdYlGn",
        zmin=-1, zmax=1,
        text_auto=".2f",
        title="銘柄間 相関係数マトリクス",
    )
    fig.update_layout(
        paper_bgcolor="#0e1117",
        plot_bgcolor="#1a1d23",
        font=dict(color="#fafafa"),
        height=450,
    )
    return fig


def build_portfolio_pie(weights: dict, title: str) -> go.Figure:
    fig = go.Figure(go.Pie(
        labels=list(weights.keys()),
        values=list(weights.values()),
        hole=0.4,
        textinfo="label+percent",
    ))
    fig.update_layout(
        title=title,
        paper_bgcolor="#0e1117",
        font=dict(color="#fafafa"),
        height=380,
    )
    return fig
