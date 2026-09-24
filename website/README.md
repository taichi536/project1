# Snow-we.Inc コーポレートサイト（www.snow-we.jp）

Google Sites の「埋め込みHTML」で作っていた旧サイトを、検索エンジンが本文を読める普通のHTMLサイトに作り直したものです。
ビルド作業は不要で、`public/` フォルダの中身がそのまま公開されます。

## フォルダ構成

```
website/
├── public/                  ← 公開されるファイル（Cloudflare Pages の公開ディレクトリ）
│   ├── index.html           トップ
│   ├── service/             サービス内容・支援の流れ
│   ├── cases/               転職事例
│   ├── about/               会社情報・代表／顧問紹介
│   ├── column/              コラム一覧（今後の記事もここに置く）
│   ├── contact/             無料相談・お問い合わせ（LINE・フォーム）
│   ├── privacy/             個人情報保護方針（旧サイトのポップアップを独立ページ化）
│   ├── 404.html
│   ├── robots.txt / sitemap.xml / _headers
│   └── assets/              CSS・JS・画像
└── templates/article.html   コラム記事のテンプレート（公開されません）
```

## 旧サイトからの主な変更点

- 本文を iframe の中ではなくページ本体に置き、Google が snow-we.jp の内容として読めるようにした
- 1ページのみの構成から、サービス／転職事例／会社情報／コラム／お問い合わせの複数ページ構成に変更
- 隠しテキスト（透明・1pxの文字）を削除（Google のスパムポリシー違反にあたるため）
- 年収の実績の数値を「30% / 40% / 70%」に統一（旧サイトは「約25%以上」と「30%」が混在）
- 各ページに固有の title・description・canonical を設定し、h1 に「コンサル転職」の語を入れた
- 構造化データ（会社情報・代表と顧問・FAQ・パンくずリスト）を追加
- コラム一覧のリンクタグの崩れ、head 内スクリプトのエラーを修正
- Tailwind の開発用CDN をやめ、軽いCSSファイルに置き換えた
- LINE ボタンとフォーム送信を GA4 の `generate_lead` イベントとして計測するようにした

## 公開前にやること（チェックリスト）

- [ ] **画像を置く**：`public/assets/img/README.md` の一覧どおりに、ロゴ・代表と顧問の写真・OGP画像を配置する
- [ ] **数値を確認する**：実績（39名、30% / 40% / 70%）が最新か
- [ ] **設立年月を確認する**：サイトは「2022年1月」。doda・マイナビなど外部サイトの表記も同じにそろえる
- [ ] **支援の流れを確認する**：`service/` の4ステップが実際の進め方と合っているか
- [ ] **英語ページ**：旧サイトの `/english` は、元のHTMLがないため移行していません。移す場合は元のソースを用意してください
- [ ] **GTM**：旧サイトには GTM（GTM-P9FKKQB2）の noscript 部分だけが残っていました。使うなら設定し直します。今回は GA4（G-TQE620GQ61）と Clarity を直接入れています

## 公開手順（Cloudflare Pages）

ドメイン snow-we.jp の DNS は **Squarespace Domains**（旧 Google Domains）で管理しています。ネームサーバーは移さず、Squarespace のまま使います。

1. Cloudflare のアカウントを作り、「Workers & Pages」→「Create」→「Pages」→ GitHub の `taichi536/project1` を接続する
2. ビルドの設定
   - Production branch：公開に使うブランチ（例：`main`）
   - Build command：空欄のまま
   - Build output directory：`website/public`
3. 発行された `xxxx.pages.dev` のURLで表示とフォーム送信を確認する
4. Cloudflare Pages の「Custom domains」で `www.snow-we.jp` を追加し、案内された CNAME の値（`xxxx.pages.dev`）を控える
5. Squarespace Domains（https://account.squarespace.com/domains）→ snow-we.jp →「DNS」→「DNS Settings」で、`www` の CNAME（現在は Google Sites 向けの `ghs.googlehosted.com`）を手順4の値に変更する
6. `snow-we.jp`（www なし）は、Squarespace の「Domain forwarding（転送）」で `https://www.snow-we.jp` へ転送する
7. 切り替えを確認したら、Google Sites 側のサイトは非公開にする（同じ内容が2か所にあると評価が分散するため）

**Squarespace の DNS で消してはいけないレコード**
- Search Console の所有権確認用 TXT（`google-site-verification=…`）
- Google Workspace のメール用レコード（MX、`v=spf1` の TXT など）

## 公開後にやること

1. Search Console（ドメインプロパティ `snow-we.jp`、2026年9月に登録済み）で `https://www.snow-we.jp/sitemap.xml` を送信する
2. 「URL検査」で各ページをインデックス登録リクエストする
3. GA4 で `generate_lead` イベントをキーイベント（コンバージョン）に設定する
4. 2〜4週間後、Search Console の「ページ」レポートで全ページがインデックスされたか確認する

## よくある更新作業

- **ヘッダー・フッターのメニューを変える**：全ページに同じHTMLが入っているので、`public/` 内の全 `.html` を一括置換する
- **転職事例を追加する**：`public/cases/index.html` の該当する業界の `<ul>` に `<li>` を1行追加する
- **コラム記事を追加する**：`templates/article.html` を `public/column/記事名/index.html` にコピーし、【】の部分を書き換える。そのあと `public/column/index.html` の一覧と `public/sitemap.xml` にURLを追加する
