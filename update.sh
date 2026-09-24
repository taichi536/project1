#!/bin/bash
# Mac / Linux 用の更新スクリプト。
# update.command はこのファイルを呼ぶだけなので、案内文はここだけ直せばよい。
# Windows 用の update.bat だけは別言語のため内容が重複している。文言を変えるときは
# 両方直すこと（以前、update.sh だけ案内が食い違っており、Chromeの再読み込みを
# しないまま「更新できた」と思い込む状態になっていた）。
cd "$(dirname "$0")" || exit 1

echo "================================"
echo " Snow-we 拡張機能 アップデート"
echo "================================"
echo ""

# 取得先を毎回入れ直す。このリポジトリは非公開なので、読み取り専用トークンを
# 含むURLでないとログイン画面が出る。トークンを入れ替えたときも、この行の
# おかげで次の更新から自動で新しいURLに切り替わる（入れ替え前に一度でも
# 更新できていれば、新しいトークン入りのこのファイル自体が届いているため）。
# 値の入れ方: ./tools/set-github-token.sh --clipboard
REPO="https://oauth2:__GITHUB_READ_TOKEN__@github.com/taichi536/project1.git"
git remote set-url origin "$REPO"

# git pull の成否を必ず見る。以前は失敗しても「更新完了」と表示していたため、
# ネットワークが切れていても、ローカルに変更が残って pull が止まっていても、
# 画面上は成功したように見えていた
if ! git pull; then
  echo ""
  echo "❌ 更新に失敗しました。"
  echo ""
  echo "上に表示されているメッセージを、そのまま管理者に伝えてください。"
  echo ""
  echo "よくある原因："
  echo "  ・インターネットに接続できていない"
  echo "  ・このフォルダの中のファイルを直接編集してしまった"
  echo "  ・フォルダを移動・コピーした"
  echo ""
  echo "※ このまま Chrome を再読み込みしても、バージョンは変わりません。"
  echo ""
  read -r -p "Enterキーを押すと閉じます..."
  exit 1
fi

VERSION=$(grep -m1 '"version"' manifest.json | sed -E 's/.*"version"[^"]*"([^"]+)".*/\1/')

echo ""
echo "✅ 更新完了！（バージョン ${VERSION}）"
echo ""
echo "次に Chrome で以下を行ってください："
echo "  1. アドレスバーに chrome://extensions と入力してEnter"
echo "  2. 「Snow-we」の「再読み込み」ボタンを押す"
echo ""
echo "※ 2 を行わないと、新しいバージョンは反映されません。"
echo "   再読み込み後、サイドパネル右上の表示が v${VERSION} になっていれば成功です。"
echo ""
# read は端末が無い場合にEOFで失敗する。ここは待つためだけなので成否を見ない
read -r -p "Enterキーを押すと閉じます..." || true
exit 0
