#!/bin/bash
# 更新がうまくいかないときに、原因を切り分けるための診断ファイル（Mac用）。
# 何も変更しない（git fetch までで、pull もファイルの書き換えもしない）。
# 表示された内容をそのままスクリーンショットで送ってもらう想定。
cd "$(dirname "$0")" || exit 1

echo "=========================================="
echo " Snow-we 更新の診断"
echo "=========================================="
echo ""
echo "このファイルは何も変更しません。"
echo "表示された内容を全部スクリーンショットで送ってください。"
echo ""

echo "[1] このフォルダの場所"
echo "    $(pwd)"
echo ""

echo "[2] いまのバージョン"
grep -m1 '"version"' manifest.json
echo ""

echo "[3] Git が使えるか"
if ! git --version; then
  echo "    ❌ Git が使えません。これが原因です。"
  read -r -p "Enterキーを押すと閉じます..." || true
  exit 1
fi
echo ""

echo "[4] このフォルダが、どこから取得したものか"
# 取得先URLには読み取り専用トークンが入っている。この画面はスクリーンショットで
# 送ってもらう前提なので、そのまま出すとトークンが漏れる。伏せて表示する
ORIGIN="$(git remote get-url origin 2>/dev/null || true)"
if [ -z "$ORIGIN" ]; then
  echo "    ❌ このフォルダは Git で取得したものではありません。"
  echo "       セットアップ用のファイルを使わずにコピーした可能性があります。"
  read -r -p "Enterキーを押すと閉じます..." || true
  exit 1
fi
case "$ORIGIN" in
  *@github.com*)
    echo "    取得先: github.com （トークンあり）"
    ;;
  *)
    echo "    取得先: github.com （トークンなし）"
    echo "    ❌ これが原因です。取得先にトークンが入っていません。"
    echo "       管理者から受け取った新しい update.sh が、このフォルダに"
    echo "       上書きできていない可能性があります。"
    ;;
esac
echo ""

echo "[5] いまいるブランチ（main でないと更新は届きません）"
git rev-parse --abbrev-ref HEAD
echo ""

echo "[6] 手元で書き換わっているファイル（何も出なければ正常）"
git status --short
echo ""

echo "[7] 最新の情報を取得中..."
# 認証が通らないとき、既定ではログイン画面が出て止まってしまう。
# 診断中に入力を求めても答えようがないので、その場で失敗させる
export GIT_TERMINAL_PROMPT=0
if ! git fetch origin; then
  echo "    ❌ GitHub から取得できませんでした。"
  echo "       [4] が「トークンなし」だった場合は、それが原因です。"
  echo "       「トークンあり」なのにここで失敗する場合は、ネットワークまたは"
  echo "       社内プロキシが原因です。"
  read -r -p "Enterキーを押すと閉じます..." || true
  exit 1
fi
echo ""

echo "[8] GitHub の最新と、手元の差"
git status -sb
echo ""
echo "    「behind」と出ていれば、update.command で更新できます。"
echo "    「up to date」なのにバージョンが古い場合は、Chrome が別のフォルダを"
echo "    読んでいます。chrome://extensions の「ロード元」を確認してください。"
echo ""

echo "=========================================="
echo " 診断おわり"
echo "=========================================="
read -r -p "Enterキーを押すと閉じます..." || true
exit 0
