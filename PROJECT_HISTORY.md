# プロジェクト全史（詳細版）

このリポジトリで行われた全ての作業を、時系列・全202コミットにわたって記録する。
「今後使うか使わないか」を問わず、実際に行ったことをすべて残す。

---

## 2026-04-02：起点

- `Initial commit` — README.md 1行のみ。ここがリポジトリの出発点。

---

## 2026-05-01：株式分析ツールの誕生（Phase 1-5）

1日で以下を一気に構築：

- **`feat: 株式売買タイミング分析ツール Phase 1-5 初期実装`**
  テクニカル分析（移動平均・RSI・MACD・ボリンジャーバンド・一目均衡表・ATR・ストキャスティクス・OBV）、
  バリュー株スクリーニング（なごちょう式6条件＋Piotroski Fスコア）、
  ファンダメンタル分析＋ファイブフォース分析（Claude AI活用）、
  AIチャート解説（Claude Sonnet）、
  投資日記（取引ログ・心理スコア・PDCA振り返り、SQLite保存）、
  Streamlitダークテーマ UI、Plotlyインタラクティブチャート。
  `app.py`・`modules/{ai_analysis,charts,data_fetcher,diary,fundamental,screening,signals,technical}.py` を新規作成。

- **`feat: マクロ経済・ニュース分析モジュールを追加`**
- **`feat: バックテスト・ポートフォリオ最適化を追加`**
- **`feat: 損益サマリー機能を追加（FIFO方式）`**
- **`feat: スマホ通知機能を追加（Telegram / Slack）`**

## 2026-05-02：ダッシュボードとUXの土台

- **`feat: ダッシュボード追加・UI大幅改善`**
- **`feat: 機械学習分析・市場時間対応・UI改善`**
- **`feat: データ遅延問題を大幅改善`**
- **`feat: APIコスト管理機能を追加`**
- **`feat: テクニカル分析のUX改善`**
- **`初心者向けUX改善: 投資プラン表示・3ヶ月エラー修正・様子見改善`**

## 2026-05-03：分析機能の拡充

- **`短期対応・グローバル銘柄選択・売り時チェック・UI改善`**
- **`銘柄スキャン機能追加・分析手法の改善`**
- **`金融工学リスク分析・チャートズーム機能追加`**
- **`エラー修正・銘柄拡充・マウスズーム・TelegramChatID改善`**
- **`保有継続判定機能追加・注目セクター銘柄拡充`**

## 2026-05-04：監視とアラートの強化

- **`下降トレンド監視判定・ブレイクアウト検出・自動通知を追加`**
- **`ポジションサイズ計算・決算日警告・マルチタイムフレーム・的中率・強い買い通知を追加`**

## 2026-05-06：品質監査とガイド整備

- **`バグ修正7件（システム監査結果対応）`**
- **`マクロ/ニュース機能をリアルタイムデータ対応に刷新、トレードガイドページを追加`**
- **`alert_runner.pyをシグナル変化検知・重複通知防止・強い買い対応に改善`**

---

## 2026-05-15：シグナル精度向上とインフラ整備（14コミット）

- **`シグナル精度向上: MLモデル強化・リスクフィルター追加・エントリー上限表示`**
- **`シグナル精度向上: ADX追加・買い条件厳格化・シグナル一致率表示`**
- **`判断ロジック全面刷新: 重み付きスコア・シグナルグレード・フィルター表示`**
- **`Fix 6 bugs: duplicate table, code dup, sell alert, ATR fallback, backtest fees, dead code`**
- **`Add broker API integration, ML data expansion, multi-timeframe confirmation`**
- **`Add requirements.txt`**（依存関係の明文化）
- **`Fix Telegram chat_id type: cast to int for large IDs`**
- **`Load .env automatically in alert_runner.py`**
- **`Fix Streamlit session_state navigation error for newer versions`**
- **`Fix HTML rendering bug in signal card reasons_html`**
- **`Add paper trading config and scheduled alert runner`**
- **`Simplify UI: remove unused broker options and collapse ML section`**
- **`Add paper trading performance analytics tab`**
- **`Add automatic watchlist management from stock universe`**

## 2026-05-17：自動ウォッチリストの安定化

- **`Fix auto watchlist scan: save settings before scanning`**
- **`Add error handling to auto watchlist scan button`**
- **`Add auto watchlist settings file`**
- **`Fix scan result display: persist via session_state, show score table`**
- **`Fix scan result persistence: save to file instead of session_state`**
- **`Fix scan result disappearing: remove st.rerun(), use if/else pattern`**
- **`Fix asset curve and positions to show real market value`**

## 2026-05-20：バックテスト精度とJ-Quants認証の試行錯誤（12コミット）

- **`Add batch backtest: test strategy across all watchlist stocks at once`**
- **`Fix position management: prevent over-buying, add auto stop-loss and take-profit`**
- **`Fix three systemic issues: backtest accuracy, position limits, market holiday check`**
- **`Make paper trading more realistic: slippage and pending limit orders`**
- **`Add paper trade state file with initial state`**
- **`Reset paper trade state to clean initial state after verification`**
- **`Fix auto-refresh toggle not persisting: use session_state for value`**
- **`Support J-Quants refresh token auth (new dashboard method)`**
- **`Add run_app.sh: one-command update and launch script`**
- **`Support J-Quants API key auth (latest dashboard method)`**
- **`Migrate J-Quants to v2 API (x-api-key header, /equities/bars/daily endpoint)`**
- **`Fix J-Quants v2 response parsing: correct field names and date params`**

## 2026-05-21：最大規模の1日（29コミット）— 自動売買・ウォッチリスト・バグ潰しの総力戦

- **`Fix: 指値注文による取引停滞を解消、UIから手動シグナル実行を追加`**
- **`Fix: ダッシュボードの自動更新設定をファイルに永続化`**
- **`Add: 社名表示・cron自動設定スクリプト・company_namesモジュール`**
- **`Fix: 成行注文で価格が0円になるバグを修正`**
- **`Add: ウォッチリスト編集画面に社名表示・自動スキャンで5銘柄追加`**
- **`Add: 自動ウォッチリストのスキャン結果・状態ファイル`**
- **`Fix: サイドバーの分析銘柄セレクタを社名表示に変更`**
- **`Update: ウォッチリストを20銘柄に拡張・自動更新カテゴリを4種に設定`**
- **`Perf: スキャンを並列化・結果キャッシュで高速化`**
- **`Fix: ウォッチリストをスコア上位N銘柄で自動入れ替え・並列スキャン`**
- **`Feat: 保有株を自動保護してウォッチリストを構築`**
- **`Perf: 銘柄スキャンを8並列化・時間見積もりを修正`**
- **`Fix: ウォッチリスト最大件数の上限を50→100に変更`**
- **`Perf: バッチダウンロードで全銘柄を1リクエスト取得・キャッシュ30分`**
- **`Perf: 自動ウォッチリストのスキャンをバッチ取得＋並列処理に最適化`**
- **`Fix: システム見直し - 売買ロジック・アラート・精度トラッキング改善`**
- **`Fix: 米国株の損益計算にUSD/JPY為替換算を追加（問題11）`**
- **`Chore: .fx_rate_cache.json を .gitignore に追加`**
- **`Fix: ユニバース全銘柄の社名を登録（111件追加）`**
- **`Fix: バグ修正 - ゼロ除算・P&L計算ミス・未定義変数・inf値の流入`**
- **`Fix: screening must_passをNAGOCHOU_CRITERIAと連動・モンテカルロのシード固定を解除`**
- **`Fix: 9件のバグ修正（クラッシュ・キャッシュ誤動作・損益計算・表示崩れ）`**
- **`Fix: USD/JPY取得をyfinance download方式でも試みるよう追加`**
- **`Fix: USD/JPY自動取得を複数APIフォールバック方式に改善`**
- **`Fix: use_container_width を width='stretch'/'content' に置換（Streamlit非推奨警告解消）`**
- **`Fix: 自動更新トグルの状態がリロード後に消える問題を修正`**
- **`Feat: ダッシュボード/スキャンの「分析」ボタンでテクニカル分析を自動実行`**
- **`UI/UX改善: 確認ダイアログ・無効ボタン説明・スキャン所要時間の追加`**
- **`Fix: 分析ボタンで遷移後も銘柄がデフォルトに戻る問題を修正`**

## 2026-05-22：UI総点検とバグ総ざらい（9コミット）

- **`UI/UX全面改善: 様子見区別・エラー表示・スキャン日時・バックテスト進捗など10項目`**
- **`Fix: メインチャートのUI改善（スパイクライン・日本語hover・一目非表示化など）`**
- **`Fix: シグナルカードのHTML raw表示バグと理由表示の矛盾を修正`**
- **`Fix: 全体バグ総ざらい修正（ゼロ除算・None比較・空DataFrame・bounds check等）`**
- **`修正: 残りの監査問題を解決`**
- **`修正: risk_metrics.pyの不要な変数を削除`**
- **`改良: キャッシュ追加・ダッシュボードタブ分割・バックテストCSVエクスポート`**
- **`改良: エラーメッセージ具体化・ティッカーバリデーション・backtest高速化・ポートフォリオタブ`**
- **`改良: 売買シグナル品質向上・バックテスト利確ロジック追加`**

## 2026-05-24：レビュー対応

- **`fix: replace ^TOPIX (404) with 1306.T ETF in macro_analysis`**
- **`fix: 5件のレビュー指摘バグを修正`**
- **`fix: 土日・市場時間外の自動売買を防止`**

## 2026-05-27：バッチバックテストの安定化とマクロページ再設計

- **`feat: バッチバックテストにプリセット銘柄選択と取引回数警告を追加`**
- **`fix: バッチバックテストのスレッドからUI更新を除去し結果が表示されないバグを修正`**
- **`fix: st.rerun()削除 — タブが切り替わって結果が見えなくなるバグを修正`**
- **`Fix batch backtest results not displaying`**
- **`Propagate ScriptRunContext to ThreadPoolExecutor workers`**（Streamlitのスレッド関連の既知の落とし穴への対応）
- **`Relax batch backtest defaults for more trades`**
- **`Redesign macro page + add trend_follow strategy + expose fee_rate`**（同一内容で2回コミット）

## 2026-05-29：モメンタム戦略、最初の実装

- **`Add weekly (週足) backtest option`**
- **`Add momentum portfolio backtest strategy`** — このリポジトリで初めてモメンタム戦略が登場
- **`Add monthly momentum rebalance alert`**
- **`Add daily stop-loss and emergency exit monitoring for momentum holdings`**

## 2026-05-30：J-Quants認証の連続格闘（14コミット）

同日中に認証方式を何度も切り替えており、外部APIの仕様理解に苦戦した跡が残る：

- **`モメンタム通知に社名・株価を表示するよう改善`**
- **`J-Quants認証修正: APIキーをリフレッシュトークンとして使用`**
- **`J-Quants APIキー認証修正: Bearer tokenとしてv2エンドポイントで使用`**
- **`J-Quants v2エンドポイント修正とエラー詳細表示`**
- **`J-Quants v2認証: APIキーをPOSTでIDトークンに交換してから使用`**
- **`J-Quants v2: x-api-keyヘッダーで直接認証（トークン交換不要）`**
- **`J-Quants v2エンドポイントを正しいパスに修正`**
- **`J-Quants Freeプランエンドポイントを活用`**
- **`is_trading_day: J-Quantsカレンダーを削除、元の方法に戻す`**（試行錯誤の末に一部ロールバック）
- **`J-Quants社名フィールド修正: CompanyName→CoName、5桁コード対応`**
- **`J-Quantsを活用したユニバース拡張とセクター分散`**
- **`momentumモードは休場日チェックをスキップ`**
- **`モメンタム戦略タブにTOPIX100/500オプション追加`**
- **`モメンタムバックテストボタン定義の欠落を修正`**

---

## 2026-06-04：運用の安全策

- **`--dry-runオプション追加: テスト時は状態保存・通知をスキップ`**

## 2026-06-06：戦略パラメータの調整

- **`戦略改善: TOPIX500・12ヶ月モメンタム・10銘柄・ボラ逆数加重`**
- **`yfinance警告を静音化・新規IPOのスキップを無音化`**

## 2026-06-08：分散フィルターの強化

- **`相関フィルター追加: 高相関銘柄を除外して実質的な分散を改善`**
- **`3つのフィルター追加: レジーム・品質・流動性`**
- **`レジームフィルターを日経225(^N225)に変更・直接yfinance取得に修正`**
- **`J-Quants: 期限切れキャッシュをフォールバックとして使用・エラー表示追加`**
- **`銘柄名をjq_stocksキャッシュから直接取得・J-Quants二重呼び出し解消`**
- **`分散強化: MAX_PER_SECTOR 3→2、相関閾値 0.70→0.55`**
- **`バックテストを本番戦略と同一ロジックに更新`**（本番とバックテストのロジック乖離を解消）

## 2026-06-10：デュアルモメンタムとCLI/Streamlit分離

- **`デュアルモメンタム戦略を実装 + 相関閾値を0.70に最適化`**
- **`損益確認(pnl)とバリュースクリーニング(value)モードを追加`**
- **`streamlit WARNINGログを抑制`**
- **`streamlit WARNING抑制をインポート前に移動`**
- **`CLIモードでstreamlit WARNINGを完全に抑制`**
- **`streamlit WARNING完全解消: sys.modulesでランタイム判定`**
- **`streamlitをCLIモードでは一切インポートしないよう修正`**
  （CLI実行時にStreamlitの警告ログを完全に黙らせるまで5回の反復）

## 2026-06-11：マルチアセット・暗号資産への拡張

- **`マルチアセット・モメンタム戦略を実装（NISA成長投資枠対応）`**
- **`Fix: remove duplicate bt_tab_multi block from portfolio section`**
- **`Add custom date range to multi-asset backtest`**
- **`Expand multi-asset universe from 5 to 8 assets`**
- **`Add stop-loss (-15%) to multi-asset strategy`**
- **`Add run_crypto_backtest: 4-strategy crypto comparison`**
- **`Add 暗号資産 tab to backtest UI`**
- **`feat: 暗号資産バックテスト機能を追加（4戦略比較）`**
- **`Add crypto weekly MA check and monthly multi-asset rebalance`**
- **`Add paper trading for BTC/FX/株 comparison (RSI+MACD signals)`**

## 2026-06-13 / 2026-06-16：ペーパートレードの調整

- **`Fix: allow paper/crypto modes to run on weekends and holidays`**
- **`Loosen paper trading RSI thresholds: 35/65 → 45/55`**

---

## 2026-07-12：ウォークフォワード最適化への着手

ここから、以降のセッションで語ってきた「検証プロジェクト」が本格的に始まる。

- **`Add FX strategy backtest (USD/JPY, EUR/JPY, GBP/JPY)`**
- **`Add USD/JPY (ドル円) as 9th asset to multi-asset universe`**
- **`Add walk-forward optimization tab for multi-asset momentum strategy`**
- **`Add auto_optimize.py: fully automated walk-forward parameter search`**
  — ETF9資産の全自動ウォークフォワード最適化。ユーザーの「もっと評価パターンを増やしたい」との要望で拡張していった原型。

## 2026-07-13：個別株モメンタムへの転換、そして最初の3つの誠実性修正

- **`Fix: filter -999 sentinel values from walk-forward averages`**（-999センチネル値が平均値を汚染するバグの修正）
- **`Switch to stocks-only 4-asset universe (Japan/US/Developed/Emerging)`**
- **`Add auto_optimize_stocks.py: Nikkei 225 individual stock momentum`**
  — ユーザー発案「個別株を都度選択すれば良いのでは」から、日経225個別株モメンタム戦略の専用スクリプトが誕生。
- **`Implement A/B/C improvements for individual stock momentum`**
- **`Fix 3 backtest honesty issues in auto_optimize_stocks.py`**
  — 外部記事（PBOフレームワーク・DSR）に触発された、ルックアヘッドバイアス修正・DSR実装・ホールドアウト設定の3点セット。
- **`Fix equal-weight rebalancing bug in simulate()`**
  — 既存保有銘柄を放置していた実装ミスの発見と修正（ユーザーの「利益率がおかしい」との指摘による）。

## 2026-07-14：生存者バイアスの発見と5市場検証の開始

- **`Add survivorship bias benchmarks to full-period comparison`**
- **`Fix N225 benchmark: squeeze Close column before float conversion`**
- **`Add 2010-era universe and vectorize simulate() for ~27x speedup`**
  — 「2025年の勝者リスト」から「2010年時点の構成銘柄」への切り替えで生存者バイアスの真因を特定。同時にnumpyベクトル化で12分→43秒に高速化。
- **`Add volatility filter (momentum crash protection) as grid parameter`**
- **`Add CPCV/PBO analysis (Bailey et al. 2015 CSCV method)`**
  — 924分割の擬似歴史パス検証を実装。
- **`Add residual momentum (Blitz, Huij & Martens 2011) as grid parameter`**
- **`Add --etf mode: multi-asset ETF momentum with full verification suite`**
- **`Fix MIN_STOCKS check for small universes (--etf mode has only 9)`**
- **`Fix universe-specific labels in optimizer header and B&H benchmark`**
- **`Add --us mode: S&P 500 individual stock momentum (2010-era universe)`**
- **`Add final research report; genericize summary header`**
  — REPORT.md 初版。

## 2026-07-15：5市場検証の完成、低ボラティリティ戦略の発見、フォワードテスト開始

- **`Add --crypto and --fx modes to the verification harness`**
- **`Complete REPORT.md with crypto and FX results (5-market map)`**
  — 日本株・米国株・ETF・暗号資産・FXの5市場、約7万パラメータ評価が完結。全市場でモメンタム戦略は指数に勝てずという結論。
- **`Add --lowvol mode: low-volatility anomaly on Japan stocks`**
  — 唯一有望だった低ボラティリティ戦略の検証開始（意図的に32通りの小グリッド）。
- **`Fix structural bias against long lookbacks: warm-started evaluation`**
  — 長期lookbackパラメータが構造的に評価不能だった重大バグを`simulate_period()`で修正。
- **`Add risk-adjusted holdout comparison (Sharpe and max drawdown vs bench)`**
- **`Make holdout drawdown comparison sampling-fair (monthly vs monthly)`**
- **`Document low-volatility campaign in REPORT.md`**
- **`Add --signal mode: forward-test signal generator and log`**
  — フォワードテストの仕組み（毎月のシグナル記録）を実装、7/15開始。

## 2026-07-16：日次資産曲線とコスト感応度

- **`Add daily equity curve for true intramonth drawdown measurement`**
  — 月中の真のドローダウンを測定できるよう日次資産曲線を追加。
- **`Update report with daily-basis drawdown verdict for low-vol strategy`**
- **`Add transaction cost sensitivity analysis to holdout report`**
  — 手数料を0%〜0.5%まで振った感応度分析。

## 2026-07-17：フォワードテスト追跡、OSS化、頻度検証、バイラル投稿の反証（10コミット）

- **`Record cost sensitivity and forward-test kickoff in report`**
- **`Add --track mode: live forward-test scoreboard`**
  — シグナル以降の実績を追跡するスコアボード。
- **`Fix --track crash on day-one data (single-point squeeze to scalar)`**
- **`Add verify_backtest.py: standalone backtest overfitting checker`**
- **`Add backtest-verify: pip-installable OSS package`**
  — 検証エンジンを独立したpipパッケージとして切り出し。
- **`Remove committed build artifacts, add package .gitignore`**
- **`Remove origin-story section and public repo URL from package`**
  — 非公開共有の方針に合わせてREADMEを調整。
- **`Add verification tab to Streamlit app (integrates backtest-verify)`**
- **`Add per-user data isolation layer for multi-user deployment`**
  — `modules/userstore.py`。マルチユーザーSaaS化の基盤。
- **`Add DEPLOY.md: 10-minute path from repo to invite-only website`**

## 2026-07-20：頻度実験、米国再現検証、アービトラージ反証、ML汎用化、予測ノート、ファンド解剖（6コミット）

- **`Add rebalance frequency support and --freq-test comparison mode`**
  — 月次/隔週/週次比較。結論：月次が最適。
- **`Enable --lowvol --us: out-of-universe replication test for low-vol`**
- **`Record US replication result: low-vol Sharpe edge did not replicate`**
  — 低ボラの米国再現実験は失敗、信頼度を下方修正。
- **`Add arb_monitor.py: paper-only cross-exchange arbitrage verifier`**
  — 「$68→$750,000」系バイラル投稿の実測反証ツール。5取引所×360観測、機会ゼロ。
- **`Generalize backtest-verify to ML model selection (v0.2.0)`**
  — 金融専用ツールをMLモデル選択の汎用検証（permutation検定・CSCV）に拡張。
- **`Add forecast pre-registration page (prediction note with hash chain)`**
  — ハッシュチェーン付き予測事前登録ページ。Brierスコアによる較正測定。
- **`Add fund_check.py: mutual fund inspection tool (GSCF case study)`**
  — 実在の投資信託販売資料（グローバル・サプライチェーン・ファンド）の平滑化検査・為替分解・信用スプレッド推定。
- **`Add fund_replica.py: liquid-ETF replication test for the GSCF`**
  — BIL/BKLN等の流動性ETFでファンドの収益源を複製し比較。
- **`Fix replica gap annualization: report CAGR differences, not cum/years`**

---

## 全体を通じての定量的な特徴

- **総コミット数**：202
- **開発が行われた月**：2026年4月（1件）、5月（121件）、6月（29件）、7月（51件）
- **最も活発だった1日**：2026-05-21（29コミット、自動売買・ウォッチリスト・バグ修正の総力戦）
- **繰り返しパターン**：機能追加のたびに直後にバグ修正コミットが続く構成が一貫している
  （例：J-Quants認証だけで14回、CLIのStreamlit警告抑制だけで5回の反復）
- **戦略の系譜**：
  テクニカル分析ツール（5月1日）→ モメンタムポートフォリオ初実装（5/29）→
  デュアルモメンタム（6/10）→ マルチアセット・暗号資産・FX拡張（6/11）→
  ウォークフォワード最適化自動化（7/12）→ 日経225個別株専用スクリプト（7/13）→
  誠実性検証・5市場全滅・低ボラ発見・フォワードテスト・SaaS化（7/13〜7/20）
- **副産物として生まれた独立ツール**：
  `backtest-verify`（OSSパッケージ、金融からML一般へ汎用化）、
  `arb_monitor.py`（バイラル投稿反証）、
  `fund_check.py`／`fund_replica.py`（投信解剖）、
  予測ノート（ハッシュチェーン付き事前登録）

このプロジェクトは、単一のテクニカル分析ツールとして始まり、
自動売買・自動ウォッチリスト・多資産バックテストへと有機的に拡大したのち、
「本当にこの戦略は機能するのか」という一点の疑いをきっかけに、
統計的検証という別の軸へと大きく舵を切った記録である。
