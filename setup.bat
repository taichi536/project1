@echo off
chcp 65001 > nul
echo ================================
echo  Snow-we 拡張機能 初回セットアップ
echo ================================
echo.
echo このスクリプトは初回のみ実行してください。
echo.

:: Gitがインストールされているか確認
git --version > nul 2>&1
if %errorlevel% neq 0 (
  echo ❌ Gitがインストールされていません。
  echo.
  echo 以下のURLからGitをダウンロードしてインストールしてください：
  echo   https://git-scm.com/download/win
  echo.
  echo インストール後、このファイルを再度実行してください。
  pause
  exit /b 1
)

echo ✅ Gitを確認しました。
echo.
echo 拡張機能をダウンロードします...
echo.

:: デスクトップに保存先フォルダを作成
set DEST=%USERPROFILE%\Desktop\snow-we

:: 公開リポジトリなので、GitHubアカウントもログインも不要。
set REPO=https://github.com/taichi536/project1.git

rem 認証が通らないときにGitHubのログイン画面を出さない。メンバーはアカウントを
rem 持っていないので答えようがなく、原因も分からないまま止まってしまう
set GIT_TERMINAL_PROMPT=0

if exist "%DEST%" (
  echo フォルダが既に存在します: %DEST%
  echo 既存のフォルダを更新します...
  cd /d "%DEST%"
  rem 既にあるフォルダは、取得先にトークンが入っていないことがある。
  rem ここで入れ直さないと git pull がログイン画面を出す
  git remote set-url origin %REPO%
  git pull
) else (
  git clone %REPO% "%DEST%"
)

if %errorlevel% neq 0 (
  echo.
  echo ❌ ダウンロードに失敗しました。
  echo ネットワーク接続を確認して、もう一度お試しください。
  pause
  exit /b 1
)

echo.
echo ✅ ダウンロード完了！
echo.
echo フォルダの場所: %DEST%
echo.
echo 次に Chrome で以下を行ってください：
echo   1. アドレスバーに chrome://extensions と入力してEnter
echo   2. 右上の「デベロッパーモード」をオンにする
echo   3. 「パッケージ化されていない拡張機能を読み込む」をクリック
echo   4. %DEST% フォルダを選択してOK
echo.
echo ※ 今後の更新は update.bat をダブルクリックするだけです。
echo.
pause
