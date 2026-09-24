#!/bin/bash
# ポジションAPIのトークンを background.js に書き込む。
#
# ■ なぜスクリプトにしてあるか
# トークンは拡張機能とサーバーの両方で同じ値になっている必要がある。手で
# 書き換えると、片方だけ変わったまま気づきにくい（症状は「ポジション提案が
# 401で止まる」だけで、原因が見えない）。
#
# ■ 使い方
#   新しく作って入れる:   ./tools/set-api-token.sh --generate
#   既にある値を入れる:   ./tools/set-api-token.sh <トークン>
#
# --generate の場合、作った値を最後に表示する。サーバー側にも同じ値を入れること。
# 表示された値はチャットやメール本文に貼らないこと。
#
# ■ 置き場所について
# このリポジトリは非公開なので、トークンをコミットしてよい。
# 公開リポジトリに移す場合は、この仕組みごと変える必要がある。
set -euo pipefail

cd "$(dirname "$0")/.."

if [ $# -lt 1 ]; then
  echo "使い方: ./tools/set-api-token.sh --generate"
  echo "        ./tools/set-api-token.sh <トークン>"
  exit 1
fi

if [ "$1" = "--generate" ]; then
  TOKEN="$(openssl rand -hex 32)"
  GENERATED=1
else
  TOKEN="$1"
  GENERATED=0
fi

# 英数字だけに限る。記号が混じると sed の置換で壊れる
if ! printf '%s' "$TOKEN" | grep -Eq '^[A-Za-z0-9]{32,}$'; then
  echo "❌ トークンは英数字32文字以上にしてください。"
  exit 1
fi

if ! grep -q "^const POSITIONS_API_TOKEN = '" background.js; then
  echo "❌ background.js に POSITIONS_API_TOKEN の行が見つかりません。"
  exit 1
fi

sed "s|^const POSITIONS_API_TOKEN = '.*';|const POSITIONS_API_TOKEN = '${TOKEN}';|" background.js > background.js.tmp
mv background.js.tmp background.js

echo "✅ background.js に書き込みました（先頭6文字: ${TOKEN:0:6}…）"

if [ "$GENERATED" = "1" ]; then
  echo ""
  echo "サーバー側にも同じ値を入れてください。"
  echo ""
  echo "  ssh root@143.198.195.132"
  echo "  cd /root/scout"
  echo "  grep -v '^POSITIONS_API_TOKEN=' .env > .env.tmp"
  echo "  printf '%s\\n' 'POSITIONS_API_TOKEN=${TOKEN}' >> .env.tmp"
  echo "  mv .env.tmp .env"
  echo "  ./scripts/deploy.sh"
  echo ""
  echo "そのあと、この変更をコミットして main に反映してください。"
fi
