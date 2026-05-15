#!/bin/bash
# MacでCronジョブを設定するスクリプト
# 実行: bash setup_cron_mac.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$(which python3)"

echo "設定内容:"
echo "  スクリプト: $SCRIPT_DIR/run_alert.sh"
echo "  Python: $PYTHON"
echo ""

# run_alert.sh の python パスを Mac の python3 に更新
sed -i '' "s|/usr/local/bin/python3|$PYTHON|g" "$SCRIPT_DIR/run_alert.sh" 2>/dev/null || \
    sed -i "s|/usr/local/bin/python3|$PYTHON|g" "$SCRIPT_DIR/run_alert.sh"

chmod +x "$SCRIPT_DIR/run_alert.sh"
mkdir -p "$SCRIPT_DIR/logs"

# cron に追加（重複チェックあり）
CRON_LINE_1="0 9 * * 1-5 $SCRIPT_DIR/run_alert.sh"
CRON_LINE_2="30 15 * * 1-5 $SCRIPT_DIR/run_alert.sh"
CRON_LINE_3="30 22 * * 1-5 $SCRIPT_DIR/run_alert.sh"

CURRENT=$(crontab -l 2>/dev/null)

NEW_CRON="$CURRENT"

add_if_missing() {
    local line="$1"
    if ! echo "$CURRENT" | grep -qF "$line"; then
        NEW_CRON="$NEW_CRON
$line"
        echo "  追加: $line"
    else
        echo "  スキップ（既存）: $line"
    fi
}

echo "Cronジョブを設定中..."
add_if_missing "$CRON_LINE_1"
add_if_missing "$CRON_LINE_2"
add_if_missing "$CRON_LINE_3"

echo "$NEW_CRON" | crontab -

echo ""
echo "✅ 完了！設定されたCronジョブ:"
crontab -l | grep "run_alert"
echo ""
echo "動作確認（今すぐ手動実行）:"
echo "  bash $SCRIPT_DIR/run_alert.sh"
echo ""
echo "ログ確認:"
echo "  tail -f $SCRIPT_DIR/logs/alert_$(date +%Y%m%d).log"
