@echo off
rem Windows 用の更新スクリプト。
rem Mac / Linux 用は update.sh（update.command はそれを呼ぶだけ）。
rem 案内文を変えるときは update.sh と両方直すこと。以前、片方だけが
rem 「5分以内に自動更新されます」という古い案内のまま残っており、Chromeの
rem 再読み込みをしないまま「更新できた」と思い込む状態になっていた。
chcp 65001 > nul
setlocal

cd /d %~dp0

echo ================================
echo  Snow-we 拡張機能 アップデート
echo ================================
echo.

rem 取得先を毎回入れ直す。このリポジトリは非公開なので、読み取り専用トークンを
rem 含むURLでないとログイン画面が出る。トークンを入れ替えたときも、この行の
rem おかげで次の更新から自動で新しいURLに切り替わる（入れ替え前に一度でも
rem 更新できていれば、新しいトークン入りのこのファイル自体が届いているため）。
rem 値の入れ方: ./tools/set-github-token.sh --clipboard
set REPO=https://oauth2:__GITHUB_READ_TOKEN__@github.com/taichi536/project1.git
git remote set-url origin %REPO%

rem git pull の成否を必ず見る。以前は失敗しても「更新完了」と表示していたため、
rem ネットワークが切れていても、ローカルに変更が残って pull が止まっていても、
rem 画面上は成功したように見えていた
git pull
if errorlevel 1 (
  echo.
  echo ❌ 更新に失敗しました。
  echo.
  echo 上に表示されているメッセージを、そのまま管理者に伝えてください。
  echo.
  echo よくある原因：
  echo   ・インターネットに接続できていない
  echo   ・このフォルダの中のファイルを直接編集してしまった
  echo   ・フォルダを移動・コピーした
  echo.
  echo ※ このまま Chrome を再読み込みしても、バージョンは変わりません。
  echo.
  pause
  exit /b 1
)

set VER=
for /f "tokens=2 delims=:," %%a in ('findstr /c:"\"version\"" manifest.json') do (
  if not defined VER set VER=%%a
)
set VER=%VER:"=%
set VER=%VER: =%

echo.
echo ✅ 更新完了！（バージョン %VER%）
echo.
echo 次に Chrome で以下を行ってください：
echo   1. アドレスバーに chrome://extensions と入力してEnter
echo   2. 「Snow-we」の「再読み込み」ボタンを押す
echo.
echo ※ 2 を行わないと、新しいバージョンは反映されません。
echo    再読み込み後、サイドパネル右上の表示が v%VER% になっていれば成功です。
echo.
pause
exit /b 0
