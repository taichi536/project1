# Snow-we 拡張機能 セットアップガイド（Windows版）

Macをお使いの方は `docs/setup-guide.md` を参照してください。

---

## 【初回のみ】インストール手順

### ① Git をインストールする

Windowsには標準でGitが入っていないため、最初に一度だけインストールが必要です。

**方法A: コマンドで入れる（推奨）**

スタートメニューで **「PowerShell」** と検索して開き、以下を貼り付けてEnter。

```powershell
winget install --id Git.Git -e
```

インストール後、**PowerShellを一度閉じて開き直してください**（そうしないとgitコマンドが認識されません）。

**方法B: インストーラーを使う**

https://gitforwindows.org/ からダウンロードし、表示される選択肢はすべて既定のまま「Next」で進めます。

インストールできたか確認するには、PowerShellで以下を実行します。

```powershell
git --version
```

`git version 2.xx.x` のように表示されればOKです。

### ② リポジトリを取得する

PowerShellで以下を貼り付けてEnter。

```powershell
git clone https://github.com/taichi536/project1.git "$env:USERPROFILE\Desktop\project1"
```

デスクトップに `project1` フォルダができます。

### ③ Chrome に読み込む

1. Chromeのアドレスバーに `chrome://extensions` と入力してEnter
2. 右上の **「デベロッパーモード」** をON
3. **「パッケージ化されていない拡張機能を読み込む」** をクリック
4. デスクトップの **`project1`** フォルダを選択

### ④ 設定する

1. 拡張機能アイコンをクリック → 設定タブ
2. **担当者名**: 自分の名前を選択
3. **GASウェブアプリURL**: たいちから受け取ったURLを入力
4. **「設定を保存」** をクリック

---

## 【2回目以降】更新手順

### ① PowerShellで実行

```powershell
cd "$env:USERPROFILE\Desktop\project1"
git pull
findstr "version" manifest.json
```

最後の行で **`"version": "1.18.319"`** のように表示されます。
たいちから連絡されたバージョンと一致していることを確認してください。

※ `"manifest_version": 3` という行も一緒に表示されますが、確認するのは
`"version"` の方です。

### ② Chromeで更新

1. `chrome://extensions` を開く
2. 拡張機能カードの **再読み込みボタン（🔄）** を押す
3. カードのバージョン表示が最新になっていることを確認

---

## トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| `git は認識されていません` | Gitが未インストール、または再起動していない | 手順①をやり直し、PowerShellを開き直す |
| `not a git repository` | フォルダの外でコマンドを実行した | `cd "$env:USERPROFILE\Desktop\project1"` を先に実行する |
| `Your local changes would be overwritten` | ローカルでファイルを変更している | `git stash` を実行してから `git pull` |
| `git pull` は成功するがバージョンが古い | 別のブランチにいる | `git checkout main` を実行してから `git pull` |
| 再読み込みしてもバージョンが変わらない | 別の場所のフォルダを読み込んでいる | `chrome://extensions` のカードに表示されるパスがデスクトップの `project1` か確認 |
| 拡張機能が動かない | 読み込み後に再読み込みが必要 | `chrome://extensions` で再読み込みボタンを押す |

---

## 補足: パスについて

`$env:USERPROFILE` は「自分のユーザーフォルダ」を表します
（例: `C:\Users\taro`）。ユーザー名が日本語でも動作します。

デスクトップの場所を変更している場合（OneDriveと同期している等）は、
`project1` フォルダの実際の場所に読み替えてください。
エクスプローラーでフォルダを開き、アドレスバーをクリックすると
フルパスが確認できます。
