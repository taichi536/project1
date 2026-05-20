#!/bin/bash
# 最新コードに更新してStreamlitを起動するスクリプト
# 使い方: bash run_app.sh

cd "$(dirname "$0")"

BRANCH="claude/stock-trading-analyzer-7XUbN"

echo "📦 最新コードを取得中..."
git pull origin "$BRANCH"
if [ $? -ne 0 ]; then
    echo "⚠️  git pull に失敗しました。手動で確認してください。"
    exit 1
fi

echo "🔄 Streamlit を再起動中..."
pkill -f "streamlit run" 2>/dev/null
sleep 1

echo "🚀 起動します..."
streamlit run app.py
