# 拡張機能の自己ホスト配布（審査なしで自動更新）

Chromeの管理ポリシーを使い、自前のサーバーから拡張機能を配布して自動更新する手順。
ウェブストアを経由しないため**更新のたびの審査が不要**になる。

前提: 配布サーバーは既存のDigitalOceanドロップレット（Caddyが動いている）を使う。

---

## 全体像

```
たいちさんのMac                     ドロップレット                 メンバーのMac
  拡張機能をパッケージ化   ──→   snowwe.crx        ──→   Chromeが自動で取得・更新
  （.crxと.pemができる）         updates.xml              （ポリシーで指定済み）
```

- `.pem`（署名鍵）は**絶対に紛失しない**こと。失うと拡張機能IDが変わり、全員が再設定になる
- `.pem` は**リポジトリに入れない**（`.gitignore` 済み）

---

## 初回のみ

### 1. 拡張機能をパッケージ化する（たいちさんのMac）

1. `chrome://extensions` を開く
2. 「デベロッパーモード」をON
3. **「拡張機能をパッケージ化」**をクリック
4. 「拡張機能のルートディレクトリ」に `project1` フォルダを指定
5. 「秘密鍵ファイル」は**空欄のまま**（初回のみ。2回目以降は作られた `.pem` を指定する）
6. 「拡張機能をパッケージ化」を押す

`project1.crx` と `project1.pem` が `project1` の親フォルダにできる。

`project1.pem` は安全な場所（1Passwordなど）に保管する。

### 2. 拡張機能IDを調べる

`chrome://extensions` で、できた `.crx` をドラッグ＆ドロップして一度読み込むとIDが表示される。
英小文字32文字の文字列（例: `abcdefghijklmnopabcdefghijklmnop`）。

このIDは `.pem` が同じである限り変わらない。

### 3. 配布サーバーを用意する（ドロップレット）

```bash
sudo mkdir -p /var/www/ext

sudo tee -a /etc/caddy/Caddyfile > /dev/null <<'CADDY'

ext.143-198-195-132.nip.io {
    root * /var/www/ext
    file_server
    # .crx を確実に配信するため明示する（既定のoctet-streamでも動くが安全側に倒す）
    @crx path *.crx
    header @crx Content-Type application/x-chrome-extension
}
CADDY

sudo caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy
```

`reload` を使うこと（`restart` は既存の scout.service に影響しうる）。

### 4. 各メンバーのMacにポリシーを設定する

**各メンバーのMacで1回だけ**実行する（管理者パスワードが必要）。
`<拡張機能ID>` は手順2で調べたものに置き換える。

```bash
sudo defaults write /Library/Preferences/com.google.Chrome ExtensionInstallForcelist -array \
  "<拡張機能ID>;https://ext.143-198-195-132.nip.io/updates.xml"

sudo defaults write /Library/Preferences/com.google.Chrome ExtensionInstallSources -array \
  "https://ext.143-198-195-132.nip.io/*"
```

設定後、**Chromeを完全に終了して再起動**する。
`chrome://policy` を開いて上記が反映されていれば成功。

以降、この拡張機能は自動でインストール・更新される。

### 5. 古い拡張機能を削除し、設定を入れ直す

ポリシー版は別IDになるため、**今までの設定（担当者名・GAS URL・APIキー等）は引き継がれない**。

1. `chrome://extensions` で今までの「パッケージ化されていない拡張機能」を削除
2. 設定画面を開き、以下を入力し直す
   - **担当者名**（各自ちがう。未設定だと記録が空欄になる）
   - GAS URL / GAS DB URL / シークレット / ポジションGAS URL
   - APIキー
   - スカウト記録のON/OFF、自動実行の設定
3. 実際に1件スカウトを送り、記録されることを確認する

---

## 2回目以降（更新のたび）

### たいちさんのMacで

1. `chrome://extensions` →「拡張機能をパッケージ化」
   - ルートディレクトリ: `project1`
   - **秘密鍵ファイル: 保管してある `project1.pem` を指定する**（重要）
2. できた `project1.crx` を `snowwe.crx` にリネーム

### updates.xml を作る

```bash
python3 tools/make_updates_xml.py <拡張機能ID> https://ext.143-198-195-132.nip.io
```

`manifest.json` のバージョンを自動で読み取って `updates.xml` ができる。

### ドロップレットへ置く

`snowwe.crx` と `updates.xml` を `/var/www/ext/` に配置する。

GitHub経由で配る場合（`.crx` をリポジトリにコミットしてから）:

```bash
cd /var/www/ext
sudo curl -fsSL -o updates.xml https://raw.githubusercontent.com/taichi536/project1/main/updates.xml
sudo curl -fsSL -o snowwe.crx  https://raw.githubusercontent.com/taichi536/project1/main/snowwe.crx
```

### 反映

各メンバーのChromeが数時間以内に自動更新する。
すぐ反映したい場合は `chrome://extensions` の**「拡張機能を更新」ボタン**を押す。

反映されたかは**ダッシュボードの「拡張機能のバージョン(担当者別)」**で確認できる。

---

## 注意点

- **バージョンを必ず上げること**。`manifest.json` の `version` が上がっていないとChromeは更新しない
- ポリシーで強制インストールされた拡張機能は、メンバーが手動で削除できない（意図した挙動）
- ポリシーを消すと拡張機能も消える
- `.pem` を紛失すると同じIDで更新できなくなり、全員が手順1〜5をやり直しになる
