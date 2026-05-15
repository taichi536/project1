#!/bin/bash
# alert_runner.py を実行するラッパースクリプト
# cron から呼ばれる。ログを logs/alert_YYYYMMDD.log に記録する。

cd "$(dirname "$0")"

LOG_DIR="$(dirname "$0")/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/alert_$(date +%Y%m%d).log"

echo "===== $(date '+%Y-%m-%d %H:%M:%S') =====" >> "$LOG_FILE"
/usr/local/bin/python3 alert_runner.py --mode all >> "$LOG_FILE" 2>&1
echo "" >> "$LOG_FILE"
