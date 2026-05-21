#!/bin/bash
# alert_runner.py の cron 自動実行を設定するスクリプト
# 使い方: bash ~/project1/setup_cron.sh

PYTHON=$(which python3)
PROJECT_DIR="$HOME/project1"
LOG_FILE="$PROJECT_DIR/alert_runner.log"

echo "🔧 cron 設定を開始します..."
echo "  Python: $PYTHON"
echo "  プロジェクト: $PROJECT_DIR"
echo "  ログ: $LOG_FILE"
echo ""

# 現在のcrontabを取得
CURRENT=$(crontab -l 2>/dev/null || echo "")

# すでに設定済みか確認
if echo "$CURRENT" | grep -q "alert_runner.py"; then
    echo "⚠️  alert_runner.py のcron設定がすでに存在します:"
    echo "$CURRENT" | grep "alert_runner.py"
    echo ""
    read -p "上書きしますか？ (y/N): " yn
    if [[ "$yn" != "y" && "$yn" != "Y" ]]; then
        echo "キャンセルしました"
        exit 0
    fi
    # 既存のalert_runner行を削除
    CURRENT=$(echo "$CURRENT" | grep -v "alert_runner.py")
fi

# 新しいcronエントリを追加
# 平日15:45 → 日本株終値確定後にシグナルチェック
# 平日08:30 → 寄り付き前に損切り・利確チェック
NEW_ENTRIES="
# 株式アラート: 平日15:45 シグナルチェック＆取引実行
45 15 * * 1-5 cd $PROJECT_DIR && $PYTHON alert_runner.py --mode all >> $LOG_FILE 2>&1
# 株式アラート: 平日08:30 損切り・利確チェック
30 8 * * 1-5 cd $PROJECT_DIR && $PYTHON alert_runner.py --mode stoploss >> $LOG_FILE 2>&1
"

echo "$CURRENT
$NEW_ENTRIES" | crontab -

echo "✅ cron 設定完了！"
echo ""
echo "設定内容:"
crontab -l | grep "alert_runner"
echo ""
echo "ログの確認: tail -f $LOG_FILE"
echo "cron削除:   crontab -e で該当行を削除"
