# デプロイ手順書 ─ サイトとして公開する

このファイルの手順どおりに進めれば、約10分でこのアプリが
`https://＜アプリ名＞.streamlit.app` というサイトになります。
**コードは誰にも見えません**（GitHubはPrivateリポジトリ＝非公開の倉庫として使うだけ。
訪問者が見るのはサイトのURLだけです）。

---

## 事前に決めること

- [ ] アプリ名（URLになる。例: `taichi-stock-lab` → `taichi-stock-lab.streamlit.app`）
- [ ] 公開範囲: **招待制**（メールで指定した人だけ）から始めることを推奨

---

## Step 1: GitHubにPrivateリポジトリを作る（3分）

1. https://github.com/new を開く
2. Repository name: `stock-lab`（任意）
3. **Private を選択**（ここ重要。Publicにしない限りコードは誰にも見えない）
4. 「Create repository」

ターミナルで（project1の中から）:

```bash
cd ~/project1
git checkout claude/stock-trading-analyzer-7XUbN   # 開発ブランチにいることを確認
git remote add deploy https://github.com/taichi536/stock-lab.git
git push deploy claude/stock-trading-analyzer-7XUbN:main
```

以後、更新を反映したいときは最後の1行を再実行するだけ。

## Step 2: Streamlit Community Cloudでデプロイ（5分）

1. https://share.streamlit.io を開き、**GitHubアカウントでログイン**
2. 「Create app」→「Deploy a public app from GitHub」
3. Repository: `taichi536/stock-lab` / Branch: `main` / Main file path: `app.py`
4. 「Advanced settings」→ Python version は 3.11 以上を選択
5. 「Deploy」→ 数分待つとURLが発行される

## Step 3: 公開範囲を「招待制」にする（2分）

1. デプロイ後の画面右下「Manage app」→「Settings」→「Sharing」
2. **「Only specific people can view this app」を選択**
3. 使ってほしい人のメールアドレスを追加
4. 相手にURLを送る → 相手はそのメールでログインして利用開始

→ 各利用者のデータは `modules/userstore.py` により**アカウントごとに完全分離**されます
（サイドバーに本人のメールが表示され、他人のウォッチリスト・記録は一切見えません）。

将来「世界中の誰でも」にしたくなったら、同じ画面で
「This app is public and searchable」に切り替えるだけです（下の注意を読んでから）。

## Step 4: （任意）AI解説機能を使う場合のみ

アプリのAI解説タブを使うには、Manage app → Settings → **Secrets** に以下を貼り付け:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
```

Telegram/Slack通知を使う場合も同様に `TELEGRAM_BOT_TOKEN` 等を追加。

---

## 既知の制約（正直な現状）

| 制約 | 内容 | 対策（今後の段階） |
|---|---|---|
| **データの永続性** | 無料枠はアプリ再起動（再デプロイ・数日間アイドル）で `data/users/` が消える | 第2段階: userstoreの保存先を外部DB（Supabase等）に差し替え。設計上この1ファイルの改修で済む |
| **データ取得制限** | 利用者が増えるとyfinanceのレート制限に当たる | 公開規模になったら有料データソースへ |
| **法務** | 招待した知人に使わせる範囲では問題は小さいが、**一般公開・収益化の前には投資助言該当性の弁護士確認が必須** | public切り替え前に実施 |

## トラブルシューティング

- **デプロイが失敗する** → Manage app のログを確認。多くは requirements.txt の
  ライブラリ不足（現在は全ライブラリ記載済みを確認済み）
- **「モジュールが見つからない」** → Main file path が `app.py` になっているか確認
- **データが消えた** → 上の永続性の制約どおりの挙動。第2段階のDB化で解決する
