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
echo "次に Chrome で以下を行ってください："
echo "  1. アドレスバーに chrome://extensions と入力してEnter"
echo "  2. 「Snow-we」の「再読み込み」ボタンを押す"
echo ""
read -p "Enterキーで閉じる..."
