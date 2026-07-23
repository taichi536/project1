# システム構成一覧

「何を作ったか」を、動いているコンポーネント単位で正確に記す。
物語や経緯は `PROJECT_STORY.md`、コミット単位の記録は `PROJECT_HISTORY.md` を参照。

---

## 全体像

```
┌─────────────────────────────────────────────────────────────┐
│  ① Streamlitアプリ（app.py）── 12ページのGUI               │
│     日常の分析・監視・記録に使う母艦                          │
├─────────────────────────────────────────────────────────────┤
│  ② CLI検証エンジン（auto_optimize_stocks.py 他）── 10モード │
│     戦略の統計的検証・フォワードテストに使う                  │
├─────────────────────────────────────────────────────────────┤
│  ③ backtest-verify（独立パッケージ）── pip installable       │
│     検証エンジンをどんな戦略・モデルにも使える形に切り出し    │
├─────────────────────────────────────────────────────────────┤
│  ④ 単発の検証ツール（arb_monitor / fund_check / fund_replica）│
│     外部の主張・商品を解剖する使い切り型スクリプト             │
└─────────────────────────────────────────────────────────────┘
```

---

## ① Streamlitアプリ（`app.py` + `modules/`）

`streamlit run app.py` で起動する、日常使いのGUI。サイドバーから12ページを切替。

| ページ | 主な機能 | 使用モジュール |
|---|---|---|
| 🏠 ダッシュボード | ウォッチリスト一覧・シグナル一覧・保有株の売り時チェック | `dashboard.py` |
| 🔭 銘柄スキャン | ユニバース全銘柄を並列スキャンしスコア順表示 | `screening.py`, `universe.py` |
| 📊 テクニカル分析 | 移動平均・RSI・MACD・BB・一目均衡表・ATR・ストキャスティクス・OBV、AIチャート解説 | `technical.py`, `charts.py`, `ai_analysis.py` |
| 📋 ファンダメンタル分析 | なごちょう式スクリーニング・Piotroski Fスコア・ファイブフォース分析 | `fundamental.py`, `screening.py` |
| 🌐 市場環境 | マクロ経済・ニュース分析（リアルタイム） | `macro_analysis.py`, `news_fetcher.py` |
| 🔬 バックテスト | 単一銘柄／一括／モメンタム／マルチアセット／暗号資産／**最適化**／個別株モメンタム／**検証**の8サブタブ | `backtest.py`, `optimizer.py`, `auto_optimize_stocks.py`（インポート）, `backtest_verify`（インポート） |
| 📐 ポートフォリオ | 相関分析・最小分散最適化・ケリー基準 | `portfolio.py` |
| 📔 投資日記 | 取引記録・FIFO損益・心理スコア・PDCA振り返り（SQLite） | `diary.py` |
| 🔮 予測ノート | 予測の事前登録（ハッシュチェーン）・的中判定・Brierスコア較正 | `forecasts.py` |
| 🔔 通知設定 | Telegram / Slack 通知設定 | `notifier.py` |
| 🤖 自動売買 | 自動売買設定・ポジション管理・ペーパートレード成績 | `auto_trade.py`, `broker.py`, `paper_trader.py`, `risk_filter.py`, `risk_metrics.py` |
| 📖 トレードガイド | 初心者向け解説 | — |

### 裏で動く仕組み
- **`alert_runner.py`**：cron等から定期実行し、シグナル変化を検知してTelegram/Slackに通知（`--dry-run`でテスト可）
- **`modules/signal_tracker.py`**：シグナル発生後の実際の値動きを追跡・的中率集計
- **`modules/auto_watchlist.py`**：スコア上位銘柄でウォッチリストを自動入れ替え（保有株は自動保護）
- **`modules/userstore.py`**：ログインユーザーごとにデータを分離するマルチユーザー基盤。Streamlit Cloud上ではメールアドレスをハッシュ化したIDで `data/users/<id>/` に保存を振り分け、ローカル実行時は既存データを自動移行
- **`modules/company_names.py`**：ティッカーと社名の対応表
- **データソース**：yfinance（価格）、J-Quants（日本株の詳細データ、v2 API・x-api-keyヘッダー認証）

---

## ② CLI検証エンジン（`auto_optimize_stocks.py`）

コマンドライン引数でモードを切替える単一スクリプト。**引数なし**で日本株個別株モメンタムの標準検証を実行。

| コマンド | 内容 |
|---|---|
| `python3 auto_optimize_stocks.py` | 日経225個別株（2010年基準ユニバース）、モメンタム960通り最適化 |
| `--etf` | マルチアセットETF9資産（日本株/米国株/先進国株/新興国株/金/REIT/米国債/先進国債/為替） |
| `--us` | S&P500個別株（2010年基準ユニバース、76銘柄） |
| `--crypto` | 暗号資産12銘柄 |
| `--fx` | FX（USD/JPY, EUR/JPY, GBP/JPY等） |
| `--lowvol` | 低ボラティリティ戦略（32通りの小グリッド、多重テスト抑制） |
| `--lowvol --us` | 低ボラ戦略の米国市場での再現実験 |
| `--freq-test` | リバランス頻度比較（月次/隔週/週次） |
| `--signal` | **フォワードテスト**：今月の推奨ポートフォリオを`results/signal_log.csv`に記録 |
| `--track` | フォワードテストの途中経過を日経平均と比較集計 |

### 検証手法（全モード共通で実装済み）
- **ルックアヘッドバイアス排除**：シグナル計算＝前日終値、執行＝当日価格
- **生存者バイアス対策**：各年代の実際の構成銘柄をユニバースとして使用
- **ウォークフォワード最適化**：訓練期間→テスト期間をスライドさせ最適パラメータを探索
- **DSR（偏向シャープ比）**：Bailey & López de Prado (2014)。試行回数を補正した統計的有意性
- **PBO/CSCV**：Bailey et al. (2015)。12ブロック924分割で「訓練1位パラメータがテストで下位半分に落ちる確率」を算出
- **ホールドアウト検証**：直近1〜2年を最適化から完全隔離し最終検証
- **日次資産曲線**：月次サンプリングでは見えない月中ドローダウンを計測
- **コスト感応度分析**：手数料0%〜0.5%を振って結論の頑健性を確認
- **`REPORT.md`**：全市場・全戦略の検証結果と結論を集約した研究レポート

### 導いた結論（現時点）
5市場・約7万パラメータ評価で、指数（日経平均・S&P500・BTC単独保有等）を上回る回転売買戦略は確認できず。唯一「低ボラティリティ戦略」がリスク調整後（シャープ・最大DD）で日本株の指数を上回ったが、米国市場での再現実験では優位性が再現されず、統計的な証明（DSR≥0.95）には未到達。→現在フォワードテスト（`--signal`/`--track`）で継続検証中。

---

## ③ backtest-verify（独立OSSパッケージ）

`backtest-verify/` 配下、pip installできる独立パッケージ（`pip install -e .`）。

```
backtest-verify/
├── pyproject.toml           # パッケージ定義、CLIコマンド"backtest-verify"を登録
├── src/backtest_verify/
│   ├── core.py              # verify() / deflated_sharpe_ratio() / compute_pbo()
│   ├── selection.py         # verify_selection()（ML汎用版）
│   └── cli.py               # コマンドライン本体
└── tests/                   # pytest（両方向校正済み：ノイズは棄却、本物は合格）
```

| 機能 | 対象 | 使い方 |
|---|---|---|
| `verify()` | 金融のリターン系列 | `backtest-verify returns.csv` |
| `verify_selection()` | MLのモデル/ハイパーパラメータ選択、A/Bテスト | `backtest-verify scores.csv --selection` |
| `--demo` | ランダム戦略100個の判定デモ | 説明・営業用 |

金融専用だった検証ロジック（DSR・PBO）を、「N個の候補から選んだ勝者は本物か、それとも運か」という一般問題として抽象化し、CVフォールドスコアなど金融以外のデータにも適用できるようにしたもの。`app.py`の「🔍 検証」タブからも `sys.path` 経由でインストール不要で利用可能。

---

## ④ 単発の検証ツール（外部への応用）

自社の戦略ではなく、**外部の主張・金融商品を解剖する**ために作った独立スクリプト。

### `arb_monitor.py` — 取引所間アービトラージ検証
5取引所（Binance/Coinbase/Kraken/Bitstamp/Gemini）のBTC bid/askを10秒間隔で監視し、手数料・レイテンシ込みの実現可能な裁定利益を測定。**発注機能なし（観測のみ）**。
```
python3 arb_monitor.py --minutes 60   # 監視
python3 arb_monitor.py --report        # 集計
```
実測結果：1時間360観測で手数料後プラスの機会0回。

### `fund_check.py` — 投資信託の月次リターン検品
販売資料の月次リターン表から、①平滑化検査（シャープ比・勝率・自己相関で非時価評価の兆候を検出）②為替寄与分解 ③信用スプレッド推定（対米国債金利）を実施。任意のCSVでも検品可能。

### `fund_replica.py` — 流動性ETFによる複製検証
ファンドの収益源（金利＋信用スプレッド＋為替）を、上場ETF（BIL・BKLN等）の組み合わせで複製し、相関と累積リターン差を比較。「非流動性・不透明性を受け入れる対価」を実測で価格付けする。

---

## ⑤ ドキュメント群

| ファイル | 内容 |
|---|---|
| `REPORT.md` | 5市場・全戦略の検証結果、研究レポート（継続更新） |
| `DEPLOY.md` | Streamlit Cloudへのデプロイ手順（招待制サイト化） |
| `PROJECT_HISTORY.md` | 全202コミットの詳細記録（事実ベース） |
| `PROJECT_STORY.md` | 開発の経緯を物語形式でまとめたもの |
| `SYSTEM_OVERVIEW.md` | 本ファイル。現在動いているシステムの構成 |

---

## 依存関係の全体図

```
app.py（Streamlit母艦）
  ├─ modules/*.py（24モジュール：分析・売買・通知・記録・マルチユーザー基盤）
  ├─ auto_optimize_stocks.py をインポート（バックテストタブ内）
  └─ backtest_verify をインポート（検証タブ内）

auto_optimize_stocks.py（CLI検証エンジン、単独でも動作）
  └─ REPORT.md に結果を蓄積

backtest-verify/（独立パッケージ、app.pyからも外部からも利用可能）

arb_monitor.py / fund_check.py / fund_replica.py（単独スクリプト、依存なし）
```
