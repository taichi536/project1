"""
auto_optimize_stocks.py  ─  日経225 個別株モメンタム戦略 全自動最適化
======================================================================
実行: python3 auto_optimize_stocks.py
結果: results/ フォルダに CSV・サマリーを保存

【戦略】
  日経225主要60銘柄から、毎月モメンタム上位N銘柄を選択して保有
  全銘柄がマイナスモメンタム → 現金待機（絶対モメンタムフィルター）

【注意】
  バックテストは現在の構成銘柄を使用するため「生存者バイアス」があります
  （倒産・上場廃止した銘柄が除外される）。実際の成績は過大評価の可能性あり。

【誠実性の取り組み】
  1. ルックアヘッドバイアス修正: シグナルは前日終値、執行は当日価格
  2. DSR（偏向シャープ比）: 多重テストによる過学習を統計的に検出
  3. ホールドアウト期間: 2024-2025年のデータは最適化に一切使用しない

【パラメータ最適化】
  lookback_months × top_n × skip_days の組み合わせを
  ウォークフォワードで評価（訓練3年→テスト1年→半年スライド）
"""

import os
import sys
import warnings
import time
from datetime import datetime
from itertools import product

import numpy as np
import pandas as pd
import yfinance as yf
from scipy import stats

warnings.filterwarnings("ignore")

# ── 設定 ────────────────────────────────────────────────────────────────────
DATA_START      = "2010-01-01"
DATA_END_OPT    = "2023-12-31"   # 最適化に使うデータの終端（ホールドアウト前）
HOLDOUT_START   = "2024-01-01"   # ホールドアウト開始（最適化中は絶対に触らない）
HOLDOUT_END     = "2025-12-31"   # ホールドアウト終端
TRAIN_DAYS      = 3 * 252
TEST_DAYS       = 1 * 252
STEP_DAYS       = 126            # 半年スライド
FEE_RATE        = 0.001          # 往復0.2%（ネット証券想定）
INITIAL_CASH    = 1_000_000.0
OUTPUT_DIR      = "results"
MIN_STOCKS      = 10             # データ取得できる最低銘柄数

# ── 日経225 主要60銘柄 ────────────────────────────────────────────────────────
NIKKEI_UNIVERSE = {
    "トヨタ":         "7203.T",
    "ソフトバンクG":  "9984.T",
    "ソニーG":        "6758.T",
    "NTT":           "9432.T",
    "三菱UFJ":        "8306.T",
    "任天堂":         "7974.T",
    "信越化学":       "4063.T",
    "キーエンス":     "6861.T",
    "KDDI":          "9433.T",
    "リクルート":     "6098.T",
    "東京エレクトロン": "8035.T",
    "中外製薬":       "4519.T",
    "ファナック":     "6954.T",
    "ホンダ":         "7267.T",
    "JR東日本":       "9020.T",
    "武田薬品":       "4502.T",
    "日立":           "6501.T",
    "ブリヂストン":   "5108.T",
    "三井物産":       "8031.T",
    "キヤノン":       "7751.T",
    "JR東海":         "9022.T",
    "塩野義製薬":     "4507.T",
    "三菱商事":       "8058.T",
    "オリエンタルランド": "4661.T",
    "富士通":         "6702.T",
    "三菱重工":       "7011.T",
    "JT":            "2914.T",
    "富士フイルム":   "4901.T",
    "アドバンテスト": "6857.T",
    "ファーストリテイリング": "9983.T",
    "三井住友FG":     "8316.T",
    "セブン&アイ":    "3382.T",
    "JR西日本":       "9021.T",
    "アステラス製薬": "4503.T",
    "パナソニック":   "6752.T",
    "日本製鉄":       "5401.T",
    "三菱地所":       "8802.T",
    "日本郵船":       "9101.T",
    "スズキ":         "7269.T",
    "資生堂":         "4911.T",
    "川崎汽船":       "9107.T",
    "ダイキン":       "6367.T",
    "オリンパス":     "7733.T",
    "第一三共":       "4568.T",
    "コマツ":         "6301.T",
    "伊藤忠商事":     "8001.T",
    "日産自動車":     "7201.T",
    "みずほFG":       "8411.T",
    "東京海上":       "8766.T",
    "三菱電機":       "6503.T",
    "テルモ":         "4543.T",
    "住友商事":       "8053.T",
    "マツダ":         "7261.T",
    "京セラ":         "6971.T",
    "野村HD":         "8604.T",
    "MS&AD":          "8725.T",
    "東レ":           "3401.T",
    "SCREENホールディングス": "7735.T",
    "エーザイ":       "4523.T",
    "東京電力HD":     "9501.T",
}

# ── 2010年時点の日経225主要銘柄（生存者バイアス低減版）─────────────────────
# 「2010年当時に大型だった銘柄」で構成。その後の勝敗を知らずに選んだリスト。
# シャープ・東芝・NEC・日産・野村・東電など「後の敗者」も意図的に含む。
# ※ 完全な上場廃止銘柄（JAL旧株など）はデータ取得不能なため含められない。
#   その分のバイアスは残る（実際の成績はさらに低かった可能性がある）。
NIKKEI_2010_UNIVERSE = {
    # 自動車・輸送機器
    "トヨタ": "7203.T", "ホンダ": "7267.T", "日産自動車": "7201.T",
    "スズキ": "7269.T", "マツダ": "7261.T", "デンソー": "6902.T",
    # 電機（2010年当時の主役。後の敗者を多数含む）
    "ソニー": "6758.T", "パナソニック": "6752.T", "シャープ": "6753.T",
    "東芝": "6502.T", "日立": "6501.T", "三菱電機": "6503.T",
    "NEC": "6701.T", "富士通": "6702.T", "キヤノン": "7751.T",
    "リコー": "7752.T", "京セラ": "6971.T", "村田製作所": "6981.T",
    "TDK": "6762.T", "ファナック": "6954.T",
    # 機械
    "コマツ": "6301.T", "クボタ": "6326.T", "ダイキン": "6367.T",
    # ゲーム（2010年はWii全盛期）
    "任天堂": "7974.T",
    # 鉄鋼・素材（2010年は中国需要で花形）
    "日本製鉄": "5401.T", "JFE": "5411.T", "神戸製鋼": "5406.T",
    "日本板硝子": "5202.T", "東レ": "3401.T", "帝人": "3402.T",
    "住友化学": "4005.T", "三菱ケミカル": "4188.T", "信越化学": "4063.T",
    "花王": "4452.T", "資生堂": "4911.T", "富士フイルム": "4901.T",
    # 医薬品
    "武田薬品": "4502.T", "アステラス製薬": "4503.T", "エーザイ": "4523.T",
    "第一三共": "4568.T", "塩野義製薬": "4507.T",
    # 食品
    "キリンHD": "2503.T", "アサヒ": "2502.T", "JT": "2914.T",
    # 金融
    "三菱UFJ": "8306.T", "三井住友FG": "8316.T", "みずほFG": "8411.T",
    "野村HD": "8604.T", "東京海上": "8766.T", "オリックス": "8591.T",
    # 商社
    "三菱商事": "8058.T", "三井物産": "8031.T", "伊藤忠商事": "8001.T",
    "住友商事": "8053.T", "丸紅": "8002.T",
    # 不動産
    "三菱地所": "8802.T", "三井不動産": "8801.T",
    # 通信
    "NTT": "9432.T", "KDDI": "9433.T", "ソフトバンクG": "9984.T",
    # 運輸
    "JR東日本": "9020.T", "JR東海": "9022.T", "ANA": "9202.T",
    "日本郵船": "9101.T", "商船三井": "9104.T",
    # 電力・ガス（2010年は安定株の代表。後に東電が暴落）
    "東京電力HD": "9501.T", "関西電力": "9503.T", "東京ガス": "9531.T",
    # 小売
    "セブン&アイ": "3382.T", "イオン": "8267.T", "ファーストリテイリング": "9983.T",
}

# バックテストに使うユニバース（生存者バイアス低減のため2010年版を使用）
BACKTEST_UNIVERSE = NIKKEI_2010_UNIVERSE

# ベンチマーク指数（--usモードではS&P500に切り替え）
BENCH_TICKER = "^N225"
BENCH_LABEL  = "日経平均"

# ── マルチアセットETFユニバース（--etf モード）──────────────────────────────
# 資産クラス間モメンタムは相関が低くトレンドが持続しやすい（学術的に最も頑健）。
# 個別株と違い生存者バイアスの心配もない（資産クラスは倒産しない）。
MULTI_ASSET_UNIVERSE = {
    "日本株":   "1306.T",
    "米国株":   "2558.T",
    "先進国株": "1657.T",
    "新興国株": "1658.T",
    "金":       "1540.T",
    "J-REIT":   "1343.T",
    "米国債":   "1482.T",
    "先進国債": "2511.T",
    "ドル円":   "USDJPY=X",
}

# ── 暗号資産ユニバース（--crypto モード）─────────────────────────────────────
# ※ 生存者バイアスが極めて強い点に注意: 死んだ数千のコインは取得不能で、
#   ここにあるのは「生き残った」メジャーコインのみ。結果は過大評価される。
# ※ 日本の税制では雑所得（最大55%課税・損失繰越不可・NISA対象外）。
CRYPTO_UNIVERSE = {
    "Bitcoin":      "BTC-USD",
    "Ethereum":     "ETH-USD",
    "XRP":          "XRP-USD",
    "Litecoin":     "LTC-USD",
    "BitcoinCash":  "BCH-USD",
    "Cardano":      "ADA-USD",
    "Dogecoin":     "DOGE-USD",
    "Stellar":      "XLM-USD",
    "Monero":       "XMR-USD",
    "EthereumClassic": "ETC-USD",
    "Zcash":        "ZEC-USD",
    "Dash":         "DASH-USD",
}
CRYPTO_PARAM_GRID = {
    "lookback_months": [1, 2, 3, 4, 5, 6, 8, 9, 10, 12],
    "top_n":           [1, 2, 3, 5],
    "skip_days":       [0, 5, 10, 21],
    "use_vol_filter":  [0, 1],
    "use_residual":    [0, 1],
}

# ── FXユニバース（--fx モード、円建てクロス）────────────────────────────────
# 「円に対して最も強い通貨を保有、全て弱ければ円のまま」という円建てモメンタム。
# ※ スワップポイント（金利差損益）は含まれない。実際のFX運用とは乖離あり。
FX_UNIVERSE = {
    "米ドル":       "USDJPY=X",
    "ユーロ":       "EURJPY=X",
    "英ポンド":     "GBPJPY=X",
    "豪ドル":       "AUDJPY=X",
    "NZドル":       "NZDJPY=X",
    "カナダドル":   "CADJPY=X",
    "スイスフラン": "CHFJPY=X",
    "シンガポールドル": "SGDJPY=X",
}
FX_PARAM_GRID = {
    "lookback_months": [1, 2, 3, 4, 5, 6, 8, 9, 10, 12],
    "top_n":           [1, 2, 3],
    "skip_days":       [0, 5, 10, 21],
    "use_vol_filter":  [0, 1],
    "use_residual":    [0, 1],
}

# ── 低ボラティリティ戦略グリッド（--lowvol モード）──────────────────────────
# 「過去のボラティリティが低い銘柄」を保有する。日本株で有効性の報告が
# 複数あるアノマリー（低リスク・アノマリー）。
# ★ 多重テストを抑えるため意図的に小さいグリッド（32通り）にしている。
LOWVOL_PARAM_GRID = {
    "lookback_months": [3, 6, 12, 24],    # ボラ推定期間
    "top_n":           [5, 10, 15, 20],   # 低ボラ上位N銘柄を保有
    "skip_days":       [0],
    "use_vol_filter":  [0, 1],
    "use_residual":    [0],
    "use_lowvol":      [1],
}

# ── 2010年時点のS&P500主要銘柄（--us モード、生存者バイアス低減版）──────────
# 「2010年当時に大型だった銘柄」で構成。GE・シティ・AIG・ゼロックス・
# インテル・フォードなど「後の敗者・停滞組」を意図的に含む。
# ※ 完全上場廃止銘柄（コダック旧株・シアーズ等）は取得不能でバイアスは残る。
# ※ USD建て。日本の投資家には為替リスクが別途加わる。
SP500_2010_UNIVERSE = {
    # テック（2010年の主役。勝者も敗者も含む）
    "Apple": "AAPL", "Microsoft": "MSFT", "IBM": "IBM", "Intel": "INTC",
    "Cisco": "CSCO", "Oracle": "ORCL", "HP": "HPQ", "Qualcomm": "QCOM",
    "TI": "TXN", "Google": "GOOGL", "Amazon": "AMZN", "eBay": "EBAY",
    "Xerox": "XRX", "AMD": "AMD", "Micron": "MU",
    # 金融（金融危機直後の生き残り）
    "JPMorgan": "JPM", "BofA": "BAC", "Citi": "C", "WellsFargo": "WFC",
    "GoldmanSachs": "GS", "MorganStanley": "MS", "Amex": "AXP",
    "USBancorp": "USB", "AIG": "AIG", "Berkshire": "BRK-B",
    # エネルギー
    "Exxon": "XOM", "Chevron": "CVX", "ConocoPhillips": "COP",
    "Schlumberger": "SLB", "Halliburton": "HAL", "Occidental": "OXY",
    # 資本財・自動車
    "GE": "GE", "Caterpillar": "CAT", "Boeing": "BA", "3M": "MMM",
    "UPS": "UPS", "FedEx": "FDX", "UnionPacific": "UNP", "Honeywell": "HON",
    "Emerson": "EMR", "Deere": "DE", "Ford": "F", "GM": "GM",
    # ヘルスケア
    "J&J": "JNJ", "Pfizer": "PFE", "Merck": "MRK", "Abbott": "ABT",
    "BMS": "BMY", "EliLilly": "LLY", "Amgen": "AMGN", "Gilead": "GILD",
    "UnitedHealth": "UNH", "CVS": "CVS",
    # 生活必需品・一般消費財
    "Walmart": "WMT", "P&G": "PG", "CocaCola": "KO", "Pepsi": "PEP",
    "McDonalds": "MCD", "Disney": "DIS", "HomeDepot": "HD", "Nike": "NKE",
    "Starbucks": "SBUX", "Target": "TGT", "Lowes": "LOW", "Costco": "COST",
    "Altria": "MO", "PhilipMorris": "PM", "Colgate": "CL",
    "KimberlyClark": "KMB", "GeneralMills": "GIS", "Kellogg": "K",
    # 通信・公益
    "AT&T": "T", "Verizon": "VZ", "Duke": "DUK", "SouthernCo": "SO",
    "Exelon": "EXC",
}

# ── パラメータグリッド ──────────────────────────────────────────────────────
PARAM_GRID = {
    "lookback_months": [1, 2, 3, 4, 5, 6, 8, 9, 10, 12],  # 10個
    "top_n":           [3, 5, 7, 10, 15, 20],               # 6個（保有銘柄数）
    "skip_days":       [0, 5, 10, 21],                       # 4個
    "use_vol_filter":  [0, 1],                                # 2個（クラッシュ対策）
    "use_residual":    [0, 1],                                # 2個（残差モメンタム）
}
# 合計: 10 × 6 × 4 × 2 × 2 = 960 組み合わせ

# ETFモード用グリッド（9資産なのでtop_nを小さく）
ETF_PARAM_GRID = {
    "lookback_months": [1, 2, 3, 4, 5, 6, 8, 9, 10, 12],
    "top_n":           [1, 2, 3, 4],
    "skip_days":       [0, 5, 10, 21],
    "use_vol_filter":  [0, 1],
    "use_residual":    [0, 1],
}
# 合計: 10 × 4 × 4 × 2 × 2 = 640 組み合わせ

# ── ボラティリティ・フィルター設定（モメンタムクラッシュ対策）──────────────
# 市場（ユニバース等加重指数）が「高ボラ かつ 下落トレンド」のとき現金退避。
# モメンタムクラッシュは暴落後の反発局面で起きるため、この2条件で予兆を捉える。
VOL_WINDOW     = 21     # ボラ計測期間（1ヶ月）
VOL_THRESHOLD  = 0.25   # 年率25%超で「高ボラ」
TREND_WINDOW   = 63     # トレンド計測期間（3ヶ月）

# ── 残差モメンタム設定（Blitz, Huij & Martens 2011）─────────────────────────
# 各銘柄のβ（市場感応度）を推定し、市場の影響を除いた「銘柄固有の強さ」で
# ランキングする。日本株ではこの分解により有意なリターンが得られるとの研究報告あり。
BETA_WINDOW = 252   # β推定期間（1年）


# ── データ取得 ────────────────────────────────────────────────────────────────
def fetch_prices(start: str = DATA_START, end: str = DATA_END_OPT,
                 label: str = "") -> pd.DataFrame:
    period_label = label or f"{start}〜{end}"
    print(f"📡 価格データを取得中... ({period_label})")
    print(f"   対象: {len(BACKTEST_UNIVERSE)} 銘柄")
    prices = {}
    failed = []

    tickers = list(BACKTEST_UNIVERSE.values())
    labels  = {v: k for k, v in BACKTEST_UNIVERSE.items()}

    # まとめてダウンロード（高速）
    try:
        raw = yf.download(
            tickers, start=start, end=end,
            interval="1d", auto_adjust=True, progress=False,
        )
        if "Close" in raw.columns:
            close = raw["Close"]
        else:
            close = raw

        for ticker in tickers:
            if ticker in close.columns:
                s = close[ticker].dropna()
                if len(s) > 200:
                    prices[ticker] = s
                else:
                    failed.append(labels.get(ticker, ticker))
            else:
                failed.append(labels.get(ticker, ticker))
    except Exception as e:
        print(f"  ⚠️  一括取得失敗: {e}、個別取得に切り替えます...")
        for ticker in tickers:
            lab = labels.get(ticker, ticker)
            try:
                df = yf.download(ticker, start=start, end=end,
                                 interval="1d", auto_adjust=True, progress=False)
                if df is not None and len(df) > 200:
                    prices[ticker] = df["Close"].squeeze()
                else:
                    failed.append(lab)
            except Exception:
                failed.append(lab)

    if failed:
        print(f"  ⚠️  取得失敗 ({len(failed)}銘柄): {', '.join(failed[:10])}{'...' if len(failed) > 10 else ''}")

    price_df = pd.DataFrame(prices).ffill().dropna(how="all")
    n_ok = len(price_df.columns)
    print(f"  → {n_ok} 銘柄取得成功（{price_df.index[0].date()} 〜 {price_df.index[-1].date()}）\n")

    min_required = min(MIN_STOCKS, max(len(BACKTEST_UNIVERSE) - 2, 3))
    if n_ok < min_required:
        print(f"❌ 取得できた銘柄が少なすぎます（{n_ok} < {min_required}）")
        sys.exit(1)

    return price_df


# ── シミュレーション ──────────────────────────────────────────────────────────
def simulate(price_df: pd.DataFrame,
             lookback_months: int,
             top_n: int,
             skip_days: int,
             use_vol_filter: int = 0,
             use_residual: int = 0,
             use_lowvol: int = 0) -> tuple[float, float, pd.Series]:
    """
    クロスセクショナル戦略をシミュレート（numpy高速版）。
    毎月リバランス、等金額配分、上位top_n銘柄を保有。
    use_vol_filter=1: 市場が高ボラ＋下落トレンドのとき現金退避（クラッシュ対策）
    use_residual=1:   残差モメンタム（β調整後の銘柄固有リターン）でランキング
    use_lowvol=1:     低ボラティリティ戦略（過去ボラが低い順に保有・常時投資）
    returns: (sharpe, total_return_pct, portfolio_series)
    """
    lookback_days = lookback_months * 21
    vals = price_df.to_numpy(dtype=float)
    n_rows, n_cols = vals.shape
    actual_top_n = min(top_n, n_cols)

    # 毎月最初の営業日を高速に抽出
    months = price_df.index.to_period("M").astype(str).to_numpy()
    is_month_start = np.r_[True, months[1:] != months[:-1]]
    rebal_indices = np.flatnonzero(is_month_start)

    # 日次リターンと市場プロキシ（ユニバース等加重）
    # ret[i] = i-1日目 → i日目 のリターン。i日目までの情報しか使わない。
    need_returns = use_vol_filter or use_residual or use_lowvol
    if need_returns:
        with np.errstate(invalid="ignore", divide="ignore"):
            ret = np.full((n_rows, n_cols), np.nan)
            ret[1:] = vals[1:] / vals[:-1] - 1
        mkt_ret = np.nanmean(ret, axis=1)

    cash = INITIAL_CASH
    shares = np.zeros(n_cols)          # 銘柄ごとの保有株数
    rec_dates, rec_pv = [], []

    # +2: シグナルは前日(idx-1)の価格を使うため1日余分に必要
    required = max(lookback_days + skip_days + 2,
                   TREND_WINDOW + 2 if use_vol_filter else 0,
                   BETA_WINDOW + skip_days + 2 if use_residual else 0)

    for idx in rebal_indices:
        if idx < required:
            continue

        # ★ ルックアヘッドバイアス修正
        # シグナル計算: 前日終値（idx-1）/ 執行: 当日価格（idx）
        exec_p = vals[idx]
        sig    = vals[idx - 1]
        past   = vals[idx - 1 - lookback_days - skip_days]
        recent = vals[idx - 1 - skip_days] if skip_days > 0 else sig

        # ★ 生存者バイアス対策: ルックバック開始時点でデータが存在する銘柄のみ
        valid = (
            ~np.isnan(past) & (past > 0)
            & ~np.isnan(recent) & (recent > 0)
            & ~np.isnan(sig) & (sig > 0)
        )
        if not valid.any():
            continue

        if use_lowvol:
            # ── 低ボラティリティ戦略 ──────────────────────────────────────
            # 過去lookback期間の日次ボラが低い銘柄ほど高スコア
            Rm = ret[idx - lookback_days - skip_days:idx - skip_days] if skip_days > 0 \
                 else ret[idx - lookback_days:idx]
            with np.errstate(invalid="ignore"):
                vol = np.nanstd(Rm, axis=0)
            enough = (~np.isnan(Rm)).sum(axis=0) >= int(len(Rm) * 0.8)
            mom = np.where(valid & enough & (vol > 0), -vol, -np.inf)
        elif use_residual:
            # ── 残差モメンタム ────────────────────────────────────────────
            # β推定: 直近BETA_WINDOW日（前日まで）の日次リターンで回帰
            Rw = ret[idx - BETA_WINDOW:idx]          # 最終行は idx-1 日のリターン
            mw = mkt_ret[idx - BETA_WINDOW:idx]
            obs_ok = ~np.isnan(Rw)
            with np.errstate(invalid="ignore", divide="ignore"):
                mw_col = np.where(obs_ok, mw[:, None], np.nan)
                cov  = np.nanmean(Rw * mw[:, None], axis=0) - np.nanmean(Rw, axis=0) * np.nanmean(mw_col, axis=0)
                varm = np.nanvar(mw_col, axis=0)
                beta = np.where(varm > 0, cov / varm, 1.0)

            # 残差リターン = 銘柄リターン − β × 市場リターン（ルックバック期間分）
            Rm = ret[idx - lookback_days - skip_days:idx - skip_days] if skip_days > 0 \
                 else ret[idx - lookback_days:idx]
            mm = mkt_ret[idx - lookback_days - skip_days:idx - skip_days] if skip_days > 0 \
                 else mkt_ret[idx - lookback_days:idx]
            resid = Rm - beta[None, :] * mm[:, None]
            with np.errstate(invalid="ignore", divide="ignore"):
                r_sum = np.nansum(resid, axis=0)
                r_std = np.nanstd(resid, axis=0)
                # ボラ調整済み残差モメンタム（Blitzの標準化）
                score = np.where(r_std > 0, r_sum / r_std, -np.inf)
            # 観測数が不足する銘柄は除外
            enough = obs_ok.sum(axis=0) >= int(BETA_WINDOW * 0.8)
            mom = np.where(valid & enough & np.isfinite(score), score, -np.inf)
        else:
            mom = np.where(valid, recent / past - 1, -np.inf)

        # ★ ボラティリティ・フィルター（モメンタムクラッシュ対策）
        # 前日(idx-1)までの市場リターンのみ使用 → ルックアヘッドなし
        crash_risk = False
        if use_vol_filter:
            vol_win   = mkt_ret[idx - VOL_WINDOW:idx]
            trend_win = mkt_ret[idx - TREND_WINDOW:idx]
            mkt_vol   = float(np.nanstd(vol_win)) * np.sqrt(252)
            mkt_trend = float(np.nansum(trend_win))
            crash_risk = (mkt_vol > VOL_THRESHOLD) and (mkt_trend < 0)

        if crash_risk:
            sel = np.array([], dtype=int)   # 全額現金退避
        else:
            order = np.argsort(mom)[::-1][:actual_top_n]
            if use_lowvol:
                # 低ボラ戦略は常時投資（市場タイミングは取らない）
                sel = order[np.isfinite(mom[order])]
            else:
                # 絶対モメンタムフィルター（上位でもマイナスなら現金）
                sel = order[mom[order] > 0]

        price_ok = ~np.isnan(exec_p) & (exec_p > 0)

        # 現在の総資産（当日執行価格で評価）
        pv = cash + float(np.sum(np.where(price_ok, shares * exec_p, 0.0)))

        # Step1: 選択外の銘柄を全売却
        sel_mask = np.zeros(n_cols, dtype=bool)
        sel_mask[sel] = True
        to_sell = (shares > 0) & ~sel_mask
        cash += float(np.sum(shares[to_sell & price_ok] * exec_p[to_sell & price_ok])) * (1 - FEE_RATE)
        shares[to_sell] = 0.0

        # Step2: 等金額リバランス
        if len(sel) > 0:
            target = pv / len(sel)
            sp = exec_p[sel]
            ok = price_ok[sel]

            # 過剰保有を先に売る
            cur_val = np.where(ok, shares[sel] * sp, 0.0)
            excess = np.where(ok & (cur_val > target), cur_val - target, 0.0)
            if excess.any():
                cash += float(np.sum(excess)) * (1 - FEE_RATE)
                shares[sel] -= np.where(excess > 0, excess / np.where(ok, sp, 1.0), 0.0)

            # 不足分を買い増し・新規購入（キャッシュ制約があるため順次）
            cur_val = np.where(ok, shares[sel] * sp, 0.0)
            for j in range(len(sel)):
                if ok[j] and cur_val[j] < target:
                    buy_amt = min(target - cur_val[j], cash)
                    if buy_amt > 0:
                        shares[sel[j]] += buy_amt * (1 - FEE_RATE) / sp[j]
                        cash -= buy_amt

        rec_dates.append(price_df.index[idx])
        rec_pv.append(pv)

    if len(rec_pv) < 3:
        return -999.0, -999.0, pd.Series(dtype=float)

    pv_series = pd.Series(rec_pv, index=rec_dates, name="総資産")
    monthly_ret = pv_series.pct_change().dropna()
    sharpe = float(monthly_ret.mean() / monthly_ret.std() * (12 ** 0.5)) if monthly_ret.std() > 0 else 0.0
    total_ret = float((pv_series.iloc[-1] / INITIAL_CASH - 1) * 100)
    return sharpe, total_ret, pv_series


# ── ウォームアップ付き期間評価 ───────────────────────────────────────────────
def _required_days(params: dict) -> int:
    """指定パラメータが取引を開始するために必要なウォームアップ日数。"""
    lb = params["lookback_months"] * 21
    skip = params.get("skip_days", 0)
    req = lb + skip + 2
    if params.get("use_vol_filter"):
        req = max(req, TREND_WINDOW + 2)
    if params.get("use_residual"):
        req = max(req, BETA_WINDOW + skip + 2)
    return req


def simulate_period(price_df: pd.DataFrame, start_idx: int, end_idx: int,
                    **params) -> tuple[float, float, pd.Series]:
    """
    [start_idx, end_idx) を評価期間としてシミュレートする。
    評価期間の前にウォームアップデータを与えるため、長いlookbackの
    パラメータでも期間の初日から取引できる（成績集計は評価期間のみ）。
    ※ ウォームアップは評価期間より過去のデータなのでルックアヘッドではない。
    """
    warmup = _required_days(params)
    s = max(0, start_idx - warmup)
    sharpe_raw, ret_raw, eq = simulate(price_df.iloc[s:end_idx], **params)
    if eq.empty:
        return sharpe_raw, ret_raw, eq

    start_date = price_df.index[start_idx]
    eq2 = eq[eq.index >= start_date]
    if len(eq2) < 3:
        return -999.0, -999.0, pd.Series(dtype=float)

    mr = eq2.pct_change().dropna()
    sharpe = float(mr.mean() / mr.std() * np.sqrt(12)) if mr.std() > 0 else 0.0
    ret = float((eq2.iloc[-1] / eq2.iloc[0] - 1) * 100)
    return sharpe, ret, eq2


# ── DSR（偏向シャープ比）────────────────────────────────────────────────────
def deflated_sharpe_ratio(sr_annualized: float, n_trials: int, n_obs: int,
                          skew: float = 0.0, excess_kurt: float = 0.0) -> tuple:
    """
    Bailey & Lopez de Prado (2014) Deflated Sharpe Ratio.
    多重テストによる過学習を補正し、真のシャープ比が0より大きい確率を返す。

    sr_annualized: 年率換算シャープ比
    n_trials:      試したパラメータ組み合わせの総数
    n_obs:         月次リターンの観測数
    Returns: (dsr, e_max_sr) - DSRと期待最大シャープ比
    """
    if n_trials <= 1 or n_obs <= 1:
        return 0.0, 0.0

    # ノイズだけで期待される最大シャープ比（Euler-Mascheroni定数 ≈ 0.5772）
    e_max_sr = (
        (1 - np.euler_gamma) * stats.norm.ppf(1 - 1.0 / n_trials)
        + np.euler_gamma * stats.norm.ppf(1 - 1.0 / (n_trials * np.e))
    )

    # 月次シャープに変換して分散を計算
    sr_m = sr_annualized / np.sqrt(12)
    e_max_m = e_max_sr / np.sqrt(12)
    variance = (1 - skew * sr_m + (excess_kurt / 4) * sr_m ** 2) / max(n_obs - 1, 1)
    sigma = np.sqrt(max(variance, 1e-10))

    z = (sr_m - e_max_m) / sigma
    dsr = float(stats.norm.cdf(z))
    return dsr, float(e_max_sr)


# ── CPCV / PBO 分析 ─────────────────────────────────────────────────────────
def compute_pbo(price_df: pd.DataFrame, n_blocks: int = 12) -> dict:
    """
    CSCV法によるPBO（バックテスト過学習確率）の計算。
    Bailey, Borwein, Lopez de Prado & Zhu (2015)

    手順:
      1. 全パラメータの月次リターン行列 M (Tヶ月 × N組み合わせ) を作成
      2. Tヶ月を n_blocks ブロックに分割
      3. 半分を訓練(IS)・残り半分をテスト(OOS)とする全組み合わせ C(12,6)=924通り
      4. 各分割で「IS最良パラメータのOOS順位」を記録
      5. PBO = OOS順位が中央値以下だった割合（高い = 過学習）

    ウォークフォワード（1本の歴史パス）と違い、924通りの擬似パスで検証する。
    """
    from itertools import combinations

    keys   = list(PARAM_GRID.keys())
    combos = list(product(*[PARAM_GRID[k] for k in keys]))

    print(f"🔀 CPCV/PBO分析: {len(combos)}パラメータの月次リターン行列を構築中...")

    ret_series = {}
    for i, combo in enumerate(combos):
        params = dict(zip(keys, combo))
        try:
            _, _, eq = simulate(price_df, **params)
        except Exception:
            continue
        if eq.empty or len(eq) < 24:
            continue
        ret_series[i] = eq.pct_change().dropna()

    if len(ret_series) < 10:
        return {"error": "有効なパラメータが少なすぎます"}

    # 全パラメータ共通の月のみ使用（ルックバック長の違いで開始月が異なるため）
    M_df = pd.concat(ret_series.values(), axis=1, join="inner", keys=ret_series.keys())
    M = M_df.to_numpy()          # T × N
    T, N = M.shape
    if T < n_blocks * 2:
        return {"error": f"共通観測月が少なすぎます（{T}ヶ月）"}

    # ブロック分割
    block_bounds = np.linspace(0, T, n_blocks + 1, dtype=int)
    blocks = [np.arange(block_bounds[b], block_bounds[b + 1]) for b in range(n_blocks)]

    def _sharpe_cols(rows):
        sub = M[rows]
        mu = sub.mean(axis=0)
        sd = sub.std(axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            sr = np.where(sd > 0, mu / sd * np.sqrt(12), -np.inf)
        return sr

    logits = []
    is_oos_pairs = []
    n_below_median = 0
    splits = list(combinations(range(n_blocks), n_blocks // 2))

    for is_blk in splits:
        oos_blk = [b for b in range(n_blocks) if b not in is_blk]
        is_rows  = np.concatenate([blocks[b] for b in is_blk])
        oos_rows = np.concatenate([blocks[b] for b in oos_blk])

        sr_is  = _sharpe_cols(is_rows)
        sr_oos = _sharpe_cols(oos_rows)

        best = int(np.argmax(sr_is))
        # IS最良パラメータのOOS順位（0〜1、1が最上位）
        rank = float(np.mean(sr_oos <= sr_oos[best]))
        omega = min(max(rank, 1e-6), 1 - 1e-6)
        logit = np.log(omega / (1 - omega))
        logits.append(logit)
        if rank <= 0.5:
            n_below_median += 1
        is_oos_pairs.append((sr_is[best], sr_oos[best]))

    pbo = n_below_median / len(splits)

    # IS→OOS 劣化スロープ（記事1と同じ分析。負なら「IS好成績ほどOOSが悪い」）
    pairs = np.array(is_oos_pairs)
    finite = np.isfinite(pairs).all(axis=1)
    slope = float(np.polyfit(pairs[finite, 0], pairs[finite, 1], 1)[0]) if finite.sum() > 2 else float("nan")
    mean_oos_of_best = float(np.nanmean(pairs[finite, 1])) if finite.sum() > 0 else float("nan")

    return {
        "pbo": pbo,
        "n_splits": len(splits),
        "n_params": N,
        "n_months": T,
        "is_oos_slope": slope,
        "mean_oos_sharpe_of_is_best": mean_oos_of_best,
    }


# ── ウォークフォワード最適化 ─────────────────────────────────────────────────
def walk_forward(price_df: pd.DataFrame) -> dict:
    keys   = list(PARAM_GRID.keys())
    combos = list(product(*[PARAM_GRID[k] for k in keys]))
    n_combos = len(combos)

    n = len(price_df)
    window_starts = list(range(0, n - TRAIN_DAYS - TEST_DAYS + 1, STEP_DAYS))
    n_windows = len(window_starts)
    total_evals = n_combos * n_windows

    print(f"🔬 最適化開始（クロスセクショナル・モメンタム）")
    print(f"   対象銘柄数: {len(price_df.columns)} 銘柄")
    print(f"   パラメータ組み合わせ: {n_combos:,} 通り")
    print(f"   時間窓: {n_windows} 個")
    print(f"   総評価回数: {total_evals:,} 回\n")

    all_results = []
    oos_parts   = []
    fix_parts   = []
    running_oos = INITIAL_CASH
    running_fix = INITIAL_CASH
    best_history = []

    t_start = time.time()

    for wi, ws in enumerate(window_starts):
        train_end = ws + TRAIN_DAYS
        test_end  = train_end + TEST_DAYS
        if test_end > n:
            break

        train_df = price_df.iloc[ws:train_end]
        test_df  = price_df.iloc[train_end:test_end]

        if len(train_df) < 100 or len(test_df) < 20:
            continue

        # 訓練期間でグリッドサーチ
        best_train_sharpe = -999.0
        best_params = None
        for combo in combos:
            params = dict(zip(keys, combo))
            try:
                sharpe, _, _ = simulate(train_df, **params)
            except Exception:
                continue
            if sharpe > best_train_sharpe:
                best_train_sharpe = sharpe
                best_params = params

        if best_params is None:
            continue

        # テスト期間（OOS）評価
        # ★ ウォームアップ付き: 長いlookbackのパラメータもテスト初日から取引できる
        try:
            oos_sharpe, oos_ret, oos_eq = simulate_period(
                price_df, train_end, test_end, **best_params
            )
        except Exception:
            continue

        if oos_sharpe <= -100:
            continue

        # 固定パラメータ（lookback=12m, top_n=10, skip=21d）との比較
        try:
            fix_sharpe, fix_ret, fix_eq = simulate_period(
                price_df, train_end, test_end,
                lookback_months=12, top_n=10, skip_days=21,
            )
        except Exception:
            fix_sharpe, fix_ret, fix_eq = -999.0, -999.0, pd.Series(dtype=float)

        # 資産推移の接続
        if not oos_eq.empty:
            scale = running_oos / float(oos_eq.iloc[0])
            oos_parts.append(oos_eq * scale)
            running_oos = float((oos_eq * scale).iloc[-1])

        if not fix_eq.empty and fix_sharpe > -100:
            scale = running_fix / float(fix_eq.iloc[0])
            fix_parts.append(fix_eq * scale)
            running_fix = float((fix_eq * scale).iloc[-1])

        period = (f"{test_df.index[0].strftime('%Y/%m')}"
                  f"〜{test_df.index[-1].strftime('%Y/%m')}")
        all_results.append({
            "テスト期間":       period,
            "lookback_months":  best_params["lookback_months"],
            "top_n":            best_params["top_n"],
            "skip_days":        best_params["skip_days"],
            "use_vol_filter":   best_params.get("use_vol_filter", 0),
            "use_residual":     best_params.get("use_residual", 0),
            "訓練Sharpe":       round(best_train_sharpe, 3),
            "OOSシャープ":      round(oos_sharpe, 3),
            "OOSリターン(%)":   round(oos_ret, 2),
            "固定Sharpe":       round(fix_sharpe, 3) if fix_sharpe > -100 else None,
            "固定リターン(%)":  round(fix_ret, 2) if fix_ret > -100 else None,
            "最適化優位":       oos_sharpe > fix_sharpe if fix_sharpe > -100 else True,
        })
        best_history.append(best_params)

        elapsed = time.time() - t_start
        done = wi + 1
        eta  = elapsed / done * (n_windows - done)
        bar  = "█" * int(done / n_windows * 30) + "░" * (30 - int(done / n_windows * 30))
        sys.stdout.write(
            f"\r  [{bar}] {done}/{n_windows}窓  "
            f"OOS Sharpe: {oos_sharpe:.2f}  ETA: {int(eta)}s   "
        )
        sys.stdout.flush()

    print("\n")

    if not all_results:
        return {"error": "有効な結果がありませんでした"}

    windows_df = pd.DataFrame(all_results)

    # パラメータ別集計
    param_rows = []
    for r in all_results:
        param_rows.append({
            "lookback_months": r["lookback_months"],
            "top_n":           r["top_n"],
            "skip_days":       r["skip_days"],
            "use_vol_filter":  r["use_vol_filter"],
            "use_residual":    r["use_residual"],
            "OOSシャープ":     r["OOSシャープ"],
            "OOSリターン(%)":  r["OOSリターン(%)"],
        })
    param_df = pd.DataFrame(param_rows)
    param_summary = (
        param_df.groupby(["lookback_months", "top_n", "skip_days", "use_vol_filter", "use_residual"])
        .agg(平均OOSシャープ=("OOSシャープ", "mean"),
             平均OOSリターン=("OOSリターン(%)", "mean"),
             採用回数=("OOSシャープ", "count"))
        .reset_index()
        .sort_values("平均OOSシャープ", ascending=False)
        .reset_index(drop=True)
    )

    def _concat(parts):
        if not parts:
            return pd.Series(dtype=float)
        c = pd.concat(parts)
        return c[~c.index.duplicated(keep="last")].sort_index()

    oos_equity = _concat(oos_parts)

    # ── DSR計算 ─────────────────────────────────────────────────────────────
    avg_oos_sharpe = float(windows_df["OOSシャープ"].mean())
    n_obs_oos = len(oos_equity.pct_change().dropna()) if not oos_equity.empty else 1
    dsr, e_max_sr = deflated_sharpe_ratio(
        sr_annualized=avg_oos_sharpe,
        n_trials=total_evals,
        n_obs=n_obs_oos,
    )

    return {
        "windows":       windows_df,
        "oos_equity":    oos_equity,
        "fixed_equity":  _concat(fix_parts),
        "param_summary": param_summary,
        "best_history":  best_history,
        "dsr":           round(dsr, 4),
        "e_max_sr":      round(e_max_sr, 3),
        "n_trials":      total_evals,
        "summary": {
            "総評価回数":         total_evals,
            "有効窓数":           len(windows_df),
            "平均OOSシャープ":    round(avg_oos_sharpe, 3),
            "平均固定Sharpe":     round(windows_df["固定Sharpe"].dropna().mean(), 3),
            "最適化優位率(%)":    round(windows_df["最適化優位"].mean() * 100, 1),
            "過学習比率":         round(
                avg_oos_sharpe / windows_df["訓練Sharpe"].mean(), 3
            ) if windows_df["訓練Sharpe"].mean() > 0 else "N/A",
            "最終OOS資産":        round(running_oos),
            "最終固定資産":       round(running_fix),
            "DSR":                round(dsr, 4),
            "期待最大Sharpe":     round(e_max_sr, 3),
        },
    }


# ── ホールドアウト検証 ───────────────────────────────────────────────────────
def run_holdout(best_params: dict) -> dict:
    """
    2024-2025年の完全未接触データで最良パラメータを一回だけ検証する。
    この検証は最適化の後に一度だけ実施し、結果を見てパラメータを調整してはならない。
    """
    print(f"\n🔒 ホールドアウト検証（{HOLDOUT_START} 〜 {HOLDOUT_END}）")
    print(f"   ※ このデータは最適化中に一切使用していません")
    print(f"   検証パラメータ: {best_params}\n")

    # ★ ウォームアップ: 2022年からのデータを与え、成績集計は2024年以降のみ。
    #   ホールドアウト開始時点で過去データを持っているのは現実と同じ条件。
    holdout_df = fetch_prices(start="2022-01-01", end=HOLDOUT_END,
                              label="ホールドアウト期間（ウォームアップ込み）")

    if holdout_df.empty or len(holdout_df) < 60:
        return {"error": "ホールドアウトデータが不足しています"}

    start_mask = holdout_df.index >= HOLDOUT_START
    if not start_mask.any():
        return {"error": "ホールドアウト期間のデータがありません"}
    start_idx = int(np.argmax(start_mask))

    try:
        sharpe, ret, eq = simulate_period(holdout_df, start_idx, len(holdout_df), **best_params)
    except Exception as e:
        return {"error": str(e)}

    return {
        "sharpe": round(sharpe, 3),
        "return_pct": round(ret, 2),
        "equity": eq,
        "params": best_params,
    }


# ── フォワードテスト: 今月のシグナル出力 ─────────────────────────────────────
def rank_lowvol(price_df: pd.DataFrame, lookback_months: int, top_n: int):
    """直近データで低ボラランキングを計算し、上位top_nの(ticker, 年率ボラ%)を返す。"""
    vals = price_df.to_numpy(dtype=float)
    lookback_days = lookback_months * 21
    if len(vals) < lookback_days + 2:
        return []
    with np.errstate(invalid="ignore", divide="ignore"):
        ret = vals[1:] / vals[:-1] - 1
    window = ret[-lookback_days:]
    vol = np.nanstd(window, axis=0) * np.sqrt(252) * 100
    enough = (~np.isnan(window)).sum(axis=0) >= int(lookback_days * 0.8)
    score = np.where(enough & (vol > 0), vol, np.inf)
    order = np.argsort(score)[:top_n]
    cols = list(price_df.columns)
    return [(cols[i], float(vol[i])) for i in order if np.isfinite(score[i])]


def run_signal():
    """
    フォワードテスト用: 今日時点の低ボラポートフォリオを出力し、ログに追記する。
    毎月月初に実行 → results/signal_log.csv に記録が蓄積 → 数ヶ月後に
    「事前に記録したシグナル」対「実際の成績」という汚染ゼロの検証ができる。
    ※ ユニバースは現在の日経225主要銘柄（実際に今日買える銘柄）を使う。
      フォワードテストでは生存者バイアスは発生しない（未来は誰にも見えない）。
    """
    global BACKTEST_UNIVERSE
    BACKTEST_UNIVERSE = NIKKEI_UNIVERSE   # 現在の投資可能銘柄

    today = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - pd.Timedelta(days=365 * 3)).strftime("%Y-%m-%d")

    print("\n" + "=" * 60)
    print("  📮 フォワードテスト・シグナル（低ボラティリティ戦略）")
    print(f"  実行日: {today}")
    print("=" * 60 + "\n")

    price_df = fetch_prices(start=start, end=today, label="直近3年")
    labels = {v: k for k, v in NIKKEI_UNIVERSE.items()}

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    log_path = os.path.join(OUTPUT_DIR, "signal_log.csv")
    log_rows = []

    configs = [
        {"name": "低ボラ(12m/15銘柄)", "lookback_months": 12, "top_n": 15},
        {"name": "低ボラ(24m/20銘柄)", "lookback_months": 24, "top_n": 20},
    ]
    for cfg in configs:
        ranked = rank_lowvol(price_df, cfg["lookback_months"], cfg["top_n"])
        print(f"  ── {cfg['name']} ─────────────────────────────")
        if not ranked:
            print("    データ不足で計算できませんでした")
            continue
        for i, (t, v) in enumerate(ranked):
            print(f"    {i+1:2d}. {labels.get(t, t):16s} ({t})  年率ボラ {v:5.1f}%")
        print()
        for i, (t, v) in enumerate(ranked):
            log_rows.append({
                "実行日": today, "戦略": cfg["name"], "順位": i + 1,
                "銘柄": labels.get(t, t), "ティッカー": t,
                "年率ボラ(%)": round(v, 2),
            })

    if log_rows:
        log_df = pd.DataFrame(log_rows)
        header = not os.path.exists(log_path)
        log_df.to_csv(log_path, mode="a", header=header,
                      index=False, encoding="utf-8-sig")
        print(f"  📄 シグナルを記録しました: {log_path}")
        print(f"     毎月月初に実行し続けると、汚染ゼロのフォワードテスト記録になります。")
        print(f"     ※ これは検証記録であり、投資判断はご自身で行ってください。\n")


# ── 結果保存 ──────────────────────────────────────────────────────────────────
def save_results(result: dict):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d_%H%M")

    csv1 = os.path.join(OUTPUT_DIR, f"stocks_windows_{today}.csv")
    result["windows"].to_csv(csv1, index=False, encoding="utf-8-sig")
    print(f"  📄 時間窓別結果: {csv1}")

    csv2 = os.path.join(OUTPUT_DIR, f"stocks_best_params_{today}.csv")
    result["param_summary"].head(30).to_csv(csv2, index=False, encoding="utf-8-sig")
    print(f"  📄 パラメータ集計: {csv2}")


# ── 推奨パラメータを表示 ──────────────────────────────────────────────────────
def print_recommendation(result: dict):
    s  = result["summary"]
    ps = result["param_summary"]

    print("\n" + "=" * 60)
    print("  📊 最適化サマリー")
    print("=" * 60)
    print(f"  最適化データ期間:  {DATA_START} 〜 {DATA_END_OPT}")
    print(f"  総評価回数:        {s['総評価回数']:,} 回")
    print(f"  有効時間窓:        {s['有効窓数']} 窓")
    print(f"  平均OOSシャープ:   {s['平均OOSシャープ']}")
    print(f"  平均固定Sharpe:    {s['平均固定Sharpe']}")
    print(f"  最適化優位率:      {s['最適化優位率(%)']:.1f}%")
    print(f"  過学習比率:        {s['過学習比率']}  ← 1.0が理想")
    print(f"  最終OOS資産:       ¥{s['最終OOS資産']:,}")
    print(f"  最終固定資産:      ¥{s['最終固定資産']:,}")
    print(f"")
    print(f"  ── DSR（偏向シャープ比）─────────────────────────")
    dsr_val = s['DSR']
    e_max   = s['期待最大Sharpe']
    verdict = "✅ 統計的に有意（過学習リスク低）" if dsr_val >= 0.95 else \
              "⚠️  境界的（要注意）"              if dsr_val >= 0.80 else \
              "❌ 統計的に有意でない（過学習の可能性大）"
    print(f"  DSR:               {dsr_val:.4f}  {verdict}")
    print(f"  期待最大Sharpe:    {e_max:.3f}  ← {s['総評価回数']:,}試行のノイズ期待値")
    print(f"  OOSシャープ:       {s['平均OOSシャープ']}  vs 期待最大 {e_max:.3f}")

    print("\n" + "-" * 60)
    print("  🏆 OOSシャープ TOP 10 パラメータ")
    print("-" * 60)
    for i, row in ps.head(10).iterrows():
        print(
            f"  #{i+1:2d}  lookback={int(row['lookback_months']):2d}m  "
            f"top_n={int(row['top_n']):2d}銘柄  "
            f"skip={int(row['skip_days']):2d}d  "
            f"volフィルタ={'有' if int(row['use_vol_filter']) else '無'}  "
            f"{'残差' if int(row['use_residual']) else '通常'}  "
            f"→ OOS Sharpe: {row['平均OOSシャープ']:.3f}  "
            f"リターン: {row['平均OOSリターン']:+.1f}%"
        )

    best = ps.iloc[0]
    print("\n" + "-" * 60)
    print("  ✅ 推奨パラメータ")
    print("-" * 60)
    print(f"  lookback_months:  {int(best['lookback_months'])} ヶ月")
    print(f"  top_n:            {int(best['top_n'])} 銘柄を保有")
    print(f"  skip_days:        {int(best['skip_days'])} 日")
    print(f"  volフィルタ:      {'有効' if int(best['use_vol_filter']) else '無効'}")
    print(f"  モメンタム種別:   {'残差モメンタム' if int(best['use_residual']) else '通常モメンタム'}")
    print(f"  平均OOSシャープ:  {best['平均OOSシャープ']:.3f}")
    print(f"\n  ⚠️  注意: 生存者バイアス対策済み（ルックバック開始時に上場していた銘柄のみ対象）")
    print(f"         ただし上場廃止・倒産銘柄は含まれないため過大評価の可能性あり")
    print("=" * 60 + "\n")


# ── メイン ────────────────────────────────────────────────────────────────────
def main():
    global BACKTEST_UNIVERSE, PARAM_GRID, BENCH_TICKER, BENCH_LABEL

    # --signal: フォワードテスト（今月のシグナル出力のみ）
    if "--signal" in sys.argv:
        run_signal()
        return

    # --etf: ETF / --us: 米国株 / --crypto: 暗号資産 / --fx: 為替 / --lowvol: 低ボラ日本株
    etf_mode    = "--etf" in sys.argv
    us_mode     = "--us" in sys.argv
    crypto_mode = "--crypto" in sys.argv
    fx_mode     = "--fx" in sys.argv
    lowvol_mode = "--lowvol" in sys.argv
    asset_class_mode = etf_mode or crypto_mode or fx_mode   # 少数資産モード
    if lowvol_mode:
        PARAM_GRID = LOWVOL_PARAM_GRID
        title = "日本株 低ボラティリティ戦略"
        uni_desc = (f"2010年時点の日経225主要 {len(BACKTEST_UNIVERSE)} 銘柄"
                    f"（生存者バイアス低減版）★ グリッドを32通りに限定し多重テストを抑制")
    elif etf_mode:
        BACKTEST_UNIVERSE = MULTI_ASSET_UNIVERSE
        PARAM_GRID = ETF_PARAM_GRID
        title = "マルチアセットETF モメンタム戦略"
        uni_desc = "9資産ETF（株4地域・金・REIT・債券2種・為替）"
    elif us_mode:
        BACKTEST_UNIVERSE = SP500_2010_UNIVERSE
        BENCH_TICKER = "^GSPC"
        BENCH_LABEL  = "S&P500"
        title = "米国S&P500 個別株モメンタム戦略"
        uni_desc = (f"2010年時点のS&P500主要 {len(BACKTEST_UNIVERSE)} 銘柄"
                    f"（生存者バイアス低減版・USD建て）")
    elif crypto_mode:
        BACKTEST_UNIVERSE = CRYPTO_UNIVERSE
        PARAM_GRID = CRYPTO_PARAM_GRID
        BENCH_TICKER = "BTC-USD"
        BENCH_LABEL  = "BTC単独保有"
        title = "暗号資産 モメンタム戦略"
        uni_desc = (f"主要 {len(BACKTEST_UNIVERSE)} コイン（USD建て）"
                    f"⚠️ 生存者バイアス大・雑所得課税に注意")
    elif fx_mode:
        BACKTEST_UNIVERSE = FX_UNIVERSE
        PARAM_GRID = FX_PARAM_GRID
        BENCH_TICKER = "USDJPY=X"
        BENCH_LABEL  = "米ドル単独保有"
        title = "FX（円建てクロス）モメンタム戦略"
        uni_desc = (f"対円 {len(BACKTEST_UNIVERSE)} 通貨 "
                    f"⚠️ スワップポイントは未考慮")
    else:
        title = "日経225 個別株モメンタム戦略"
        uni_desc = f"2010年時点の日経225主要 {len(BACKTEST_UNIVERSE)} 銘柄（生存者バイアス低減版）"

    print("\n" + "=" * 60)
    print(f"  🎯 {title} 全自動最適化")
    print(f"  対象: {uni_desc}")
    print(f"  最適化データ: {DATA_START} 〜 {DATA_END_OPT}")
    print(f"  ホールドアウト: {HOLDOUT_START} 〜 {HOLDOUT_END}（最適化外）")
    print(f"  訓練: {TRAIN_DAYS//252}年  テスト: {TEST_DAYS//252}年  スライド: {STEP_DAYS}日")
    print(f"  ルックアヘッドバイアス修正: シグナル=前日終値 / 執行=当日価格")
    print("=" * 60 + "\n")

    t0 = time.time()

    # ── 最適化（ホールドアウト期間を除いたデータのみ） ───────────────────────
    price_df = fetch_prices(start=DATA_START, end=DATA_END_OPT)
    result = walk_forward(price_df)

    if "error" in result:
        print(f"❌ {result['error']}")
        sys.exit(1)

    print("💾 結果を保存中...")
    save_results(result)
    print_recommendation(result)

    # ── CPCV / PBO 分析（924通りの擬似歴史パスで過学習を測定） ──────────────
    pbo_result = compute_pbo(price_df)
    print("\n" + "=" * 60)
    print("  🔀 CPCV / PBO 分析結果")
    print("=" * 60)
    if "error" in pbo_result:
        print(f"  ❌ {pbo_result['error']}")
    else:
        pbo = pbo_result["pbo"]
        verdict = "✅ 過学習リスク低い" if pbo < 0.2 else \
                  "⚠️  境界的"          if pbo < 0.5 else \
                  "❌ 過学習の可能性大（IS最良≒OOSでは中央値以下）"
        print(f"  分割数:            {pbo_result['n_splits']} 通り（12ブロックCSCV）")
        print(f"  有効パラメータ数:  {pbo_result['n_params']}")
        print(f"  共通観測月数:      {pbo_result['n_months']} ヶ月")
        print(f"  PBO:               {pbo:.3f}  {verdict}")
        print(f"     → 訓練で1位のパラメータがテストで下位半分に落ちる確率")
        print(f"  IS→OOS スロープ:   {pbo_result['is_oos_slope']:+.3f}  ← マイナスなら「IS好成績ほどOOSが悪い」")
        print(f"  IS最良のOOS平均Sharpe: {pbo_result['mean_oos_sharpe_of_is_best']:+.3f}")
    print("=" * 60 + "\n")

    # ── ホールドアウト検証（一回だけ、最良パラメータで） ───────────────────
    best_params_hist = result.get("best_history", [])
    if best_params_hist:
        # 最も頻出したパラメータを推奨パラメータとする
        from collections import Counter
        param_keys = list(PARAM_GRID.keys())
        param_tuples = [tuple(p[k] for k in param_keys) for p in best_params_hist]
        most_common = Counter(param_tuples).most_common(1)[0][0]
        best_params = dict(zip(param_keys, most_common))

        holdout_result = run_holdout(best_params)
        print("\n" + "=" * 60)
        print("  🔒 ホールドアウト検証結果")
        print("=" * 60)
        if "error" in holdout_result:
            print(f"  ❌ {holdout_result['error']}")
        else:
            h_sharpe = holdout_result["sharpe"]
            h_ret    = holdout_result["return_pct"]
            verdict  = "✅ 汎化できている" if h_sharpe > 0.5 else \
                       "⚠️  弱い（要注意）" if h_sharpe > 0.0 else \
                       "❌ マイナス（過学習または戦略の限界）"
            print(f"  対象期間:  {HOLDOUT_START} 〜 {HOLDOUT_END}")
            print(f"  パラメータ: {best_params}")
            print(f"  OOSシャープ: {h_sharpe}  {verdict}")
            print(f"  リターン:    {h_ret:+.1f}%")
            print(f"  最終資産:    ¥{round(holdout_result['equity'].iloc[-1]):,}" if not holdout_result['equity'].empty else "")
            # 同期間のベンチマーク指数と比較（市場に勝てているかが本当の基準）
            try:
                bench_h = yf.download(BENCH_TICKER, start=HOLDOUT_START, end=HOLDOUT_END,
                                      interval="1d", auto_adjust=True, progress=False)["Close"].squeeze().dropna()
                bench_h_ret = float(bench_h.iloc[-1] / bench_h.iloc[0] - 1) * 100
                diff = h_ret - bench_h_ret
                print(f"  {BENCH_LABEL}:    {bench_h_ret:+.1f}%  → 戦略との差: {diff:+.1f}pt "
                      f"{'✅ 市場に勝利' if diff > 0 else '❌ 市場に敗北（インデックスの方が良かった）'}")

                # リスク調整後の比較（低ボラ系戦略の正しい評価軸）
                # ★ 公平性: 戦略の資産曲線は月次サンプリングなので、
                #   ベンチマークも月次サンプリングに揃えてDDを比較する
                bench_level_m = bench_h.resample("MS").first().dropna()
                bench_m = bench_level_m.pct_change().dropna()
                bench_sharpe = float(bench_m.mean() / bench_m.std() * np.sqrt(12)) if bench_m.std() > 0 else 0.0
                bench_dd_m = float((bench_level_m / bench_level_m.cummax() - 1).min()) * 100
                bench_dd_d = float((bench_h / bench_h.cummax() - 1).min()) * 100
                eq_h = holdout_result["equity"]
                strat_dd = float((eq_h / eq_h.cummax() - 1).min()) * 100 if not eq_h.empty else float("nan")
                sharpe_diff = h_sharpe - bench_sharpe
                print(f"")
                print(f"  ── リスク調整後比較（月次サンプリングで統一）──────")
                print(f"  シャープ:  戦略 {h_sharpe:.3f} vs {BENCH_LABEL} {bench_sharpe:.3f} "
                      f"→ {sharpe_diff:+.3f} {'✅ リスク調整後は勝利' if sharpe_diff > 0 else '❌ リスク調整後も敗北'}")
                print(f"  最大DD:    戦略 {strat_dd:.1f}% vs {BENCH_LABEL} {bench_dd_m:.1f}% "
                      f"{'✅ 下落耐性あり' if strat_dd > bench_dd_m else '❌ 下落も大きい'}")
                print(f"  （参考: {BENCH_LABEL}の日次ベース最大DD {bench_dd_d:.1f}%。"
                      f"戦略の月中DDは月次データでは測定不能）")
            except Exception as e:
                print(f"  {BENCH_LABEL}比較: 取得失敗 ({e})")
        print("=" * 60 + "\n")

    # ── 参考: 推奨パラメータと固定パラメータの全期間比較（2010-2023） ────────
    print("\n" + "=" * 60)
    print(f"  📊 全期間比較（{DATA_START} 〜 {DATA_END_OPT}）")
    print("=" * 60)

    if lowvol_mode:
        configs = [
            {"label": "低ボラ（12m/10銘柄）",       "top_n": 10, "lookback_months": 12, "skip_days": 0, "use_lowvol": 1},
            {"label": "低ボラ（12m/20銘柄）",       "top_n": 20, "lookback_months": 12, "skip_days": 0, "use_lowvol": 1},
            {"label": "低ボラ（24m/10銘柄）",       "top_n": 10, "lookback_months": 24, "skip_days": 0, "use_lowvol": 1},
            {"label": "低ボラ＋volフィルタ",         "top_n": 10, "lookback_months": 12, "skip_days": 0, "use_lowvol": 1, "use_vol_filter": 1},
            {"label": "参考:通常モメンタム(2m/10)", "top_n": 10, "lookback_months": 2, "skip_days": 21},
        ]
    elif asset_class_mode:
        configs = [
            {"label": "TOP1資産（12m/skip21d）",   "top_n": 1, "lookback_months": 12, "skip_days": 21},
            {"label": "TOP2資産（12m/skip21d）",   "top_n": 2, "lookback_months": 12, "skip_days": 21},
            {"label": "TOP3資産（6m/skip21d）",    "top_n": 3, "lookback_months": 6,  "skip_days": 21},
            {"label": "TOP2＋volフィルタ",          "top_n": 2, "lookback_months": 12, "skip_days": 21, "use_vol_filter": 1},
            {"label": "残差モメンタム（TOP2/11m）", "top_n": 2, "lookback_months": 11, "skip_days": 21, "use_residual": 1},
        ]
    else:
        configs = [
            {"label": "集中型（3銘柄/lookback=2m）", "top_n": 3,  "lookback_months": 2, "skip_days": 21},
            {"label": "分散型（10銘柄/lookback=2m）", "top_n": 10, "lookback_months": 2, "skip_days": 21},
            {"label": "分散型＋volフィルタ",          "top_n": 10, "lookback_months": 2, "skip_days": 21, "use_vol_filter": 1},
            {"label": "残差モメンタム（10銘柄/11m）",  "top_n": 10, "lookback_months": 11, "skip_days": 21, "use_residual": 1},
            {"label": "固定パラメータ（12m/10銘柄）",  "top_n": 10, "lookback_months": 12, "skip_days": 21},
        ]
    for cfg in configs:
        label = cfg.pop("label")
        sharpe, ret, _ = simulate(price_df, **cfg)
        print(f"  {label:30s}  Sharpe: {sharpe:+.3f}  リターン: {ret:+.1f}%")
        cfg["label"] = label

    # ── ベンチマーク: 生存者バイアスの定量化 ────────────────────────────────
    # この60銘柄を「ただ均等に持ち続けた」場合のリターン。
    # 銘柄リスト自体が現在の勝者で構成されているため、この数字が高いほど
    # モメンタム戦略のリターンも銘柄選択バイアスで底上げされている。
    bh_rets = []
    for t in price_df.columns:
        s = price_df[t].dropna()
        if len(s) > 252:
            bh_rets.append(float(s.iloc[-1] / s.iloc[0] - 1) * 100)
    if bh_rets:
        bh_avg = float(np.mean(bh_rets))
        print(f"  【B&H】全{len(bh_rets)}銘柄を均等保有（売買なし）      リターン: {bh_avg:+.1f}%")

    # ベンチマーク指数そのもの（銘柄選択バイアスなしの市場全体）
    try:
        bench = yf.download(BENCH_TICKER, start=DATA_START, end=DATA_END_OPT,
                            interval="1d", auto_adjust=True, progress=False)["Close"].squeeze().dropna()
        bench_ret = float(bench.iloc[-1] / bench.iloc[0] - 1) * 100
        print(f"  【指数】{BENCH_LABEL} ({BENCH_TICKER})        リターン: {bench_ret:+.1f}%")
    except Exception as e:
        print(f"  【指数】{BENCH_LABEL}: 取得失敗 ({e})")

    print()
    print("  💡 Sharpeが高い = リスク対比のリターンが良い")
    print("     ※ ルックアヘッドバイアス修正済み・ホールドアウト期間除外済み")
    print(f"  ⚠️  B&Hと{BENCH_LABEL}の差 = 生存者バイアスの大きさ")
    print("     モメンタム戦略とB&Hの差 = 戦略が本当に生み出した価値")
    print("=" * 60 + "\n")

    print(f"  ⏱  総実行時間: {time.time()-t0:.0f} 秒（{(time.time()-t0)/60:.1f} 分）\n")


if __name__ == "__main__":
    main()
