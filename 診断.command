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
if ! git remote -v; then
  echo "    ❌ このフォルダは Git で取得したものではありません。"
  echo "       セットアップ用のファイルを使わずにコピーした可能性があります。"
  read -r -p "Enterキーを押すと閉じます..." || true
  exit 1
fi
echo ""

echo "[5] いまいるブランチ（main でないと更新は届きません）"
git rev-parse --abbrev-ref HEAD
echo ""

echo "[6] 手元で書き換わっているファイル（何も出なければ正常）"
git status --short
echo ""

echo "[7] 最新の情報を取得中..."
if ! git fetch origin; then
  echo "    ❌ GitHub に接続できませんでした。"
  echo "       ネットワークまたは社内プロキシが原因です。"
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
