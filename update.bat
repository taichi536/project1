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

rem 取得先を毎回入れ直す。
rem 一時期このリポジトリを非公開にしており、その間はトークン入りのURLで
rem 取得していた。その設定が手元に残っていると、トークンを失効させたあとに
rem 取得できなくなる。ここで毎回入れ直すことで、古い設定のまま止まらない。
set REPO=https://github.com/taichi536/project1.git
git remote set-url origin %REPO%
echo 取得先を設定しました。
echo.

rem 認証が通らないとき、既定ではGitHubのログイン画面が出る。メンバーは
rem GitHubアカウントを持っていないので答えようがなく、「User cancelled dialog」と
rem 出たまま何が悪いのか分からない状態になる。その場で失敗させて原因を出す
set GIT_TERMINAL_PROMPT=0

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
  echo 「Authentication failed」と出ている場合は、管理者に連絡してください。
  echo 取得用のトークンが期限切れになっている可能性があります。
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
