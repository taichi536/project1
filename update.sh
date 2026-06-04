#!/bin/bash
echo "================================"
echo " Snow-we 拡張機能 アップデート"
echo "================================"
echo ""

cd "$(dirname "$0")"
git pull

echo ""
echo "✅ 更新完了！"
echo ""
echo "Chromeが開いていれば5分以内に自動で最新版になります。"
echo ""
read -p "Enterキーで閉じる..."
