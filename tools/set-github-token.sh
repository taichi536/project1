#!/bin/bash
# setup.bat に、GitHubの読み取り専用トークンを書き込む。
#
# ■ 何のために要るか
# このリポジトリは非公開なので、そのまま clone するとGitHubのログイン画面が
# 出る。メンバーにGitHubアカウントを作ってもらわずに済ませるため、読み取り
# 専用のトークンを含むURLで clone する。トークンは clone したフォルダに
# 記録されるので、以降の update.bat はそのまま通る。
#
# ■ トークンの作り方
#   https://github.com/settings/personal-access-tokens
#   - Repository access: Only select repositories → taichi536/project1
#   - Permissions: Repository permissions → Contents → Read-only
#   - それ以外の権限は付けない
#
# ■ 使い方
#   ./tools/set-github-token.sh <トークン>
#
# 表示された値や作ったトークンは、チャットに貼らないこと。
#
# ■ 入れ替えるとき
# GitHubで古いトークンを失効させ、新しいトークンでこのスクリプトを実行し、
# 新しい setup.bat をメンバーに配り直す。既にセットアップ済みの人は、
# 古いトークンが .git/config に残っているため、失効させると update.bat が
# 通らなくなる。入れ替えは全員の再セットアップとセットで行うこと。
set -euo pipefail

cd "$(dirname "$0")/.."

if [ $# -lt 1 ]; then
  echo "使い方: ./tools/set-github-token.sh <トークン>"
  exit 1
fi

TOKEN="$1"

# 接頭辞が二重になっているのを先に弾く。コピーした値自体が github_pat_ で
# 始まるので、案内を読み違えて前に付け足してしまうことがある。素通しすると
# 不正な値のまま書き込まれ、メンバーのセットアップが失敗してから気づくことになる
if printf '%s' "$TOKEN" | grep -Eq '^(github_pat_|ghp_){2}'; then
  echo "❌ 接頭辞が二重になっています。コピーした値をそのまま渡してください。"
  echo "   （値は github_pat_ で始まっているので、前に付け足す必要はありません）"
  exit 1
fi

# GitHubのトークンは github_pat_... / ghp_... の形。記号が混じると
# sed の置換で壊れるので、英数字とアンダースコアだけに限る
if ! printf '%s' "$TOKEN" | grep -Eq '^(github_pat_|ghp_)[A-Za-z0-9_]{20,}$'; then
  echo "❌ トークンの形が想定と違います。"
  echo "   github_pat_ または ghp_ で始まる、英数字とアンダースコアだけの値を渡してください。"
  exit 1
fi

if ! grep -q "^set REPO=https://oauth2:" setup.bat; then
  echo "❌ setup.bat に REPO の行が見つかりません。"
  exit 1
fi

sed "s|^set REPO=https://oauth2:.*@github.com/|set REPO=https://oauth2:${TOKEN}@github.com/|" setup.bat > setup.bat.tmp
mv setup.bat.tmp setup.bat

echo "✅ setup.bat に書き込みました（先頭10文字: ${TOKEN:0:10}…）"
echo ""
echo "動作確認（一時フォルダに取得してすぐ消します）:"
echo "  rm -rf /tmp/clone-test && git clone --depth 1 \"\$(grep '^set REPO=' setup.bat | cut -d= -f2-)\" /tmp/clone-test && rm -rf /tmp/clone-test"
echo ""
echo "確認できたら、この変更をコミットして main に反映し、"
echo "setup.bat をメンバーに配ってください。"
