@echo off
rem 更新がうまくいかないときに、原因を切り分けるための診断ファイル。
rem 何も変更しない（git fetch までで、pull もファイルの書き換えもしない）。
rem 表示された内容をそのままスクリーンショットで送ってもらう想定。
chcp 65001 > nul
setlocal

cd /d %~dp0

echo ==========================================
echo  Snow-we 更新の診断
echo ==========================================
echo.
echo このファイルは何も変更しません。
echo 表示された内容を全部スクリーンショットで送ってください。
echo.

echo [1] このフォルダの場所
echo     %CD%
echo.

echo [2] いまのバージョン
findstr /c:"\"version\"" manifest.json
echo.

echo [3] Git が使えるか
git --version
if errorlevel 1 (
  echo     ❌ Git がインストールされていません。これが原因です。
  echo.
  pause
  exit /b 1
)
echo.

echo [4] このフォルダが、どこから取得したものか
rem 取得先URLには読み取り専用トークンが入っている。この画面はスクリーンショットで
rem 送ってもらう前提なので、そのまま出すとトークンが漏れる。伏せて表示する
for /f "tokens=2" %%u in ('git remote -v 2^>nul ^| findstr /c:"(fetch)"') do set ORIGIN=%%u
if not defined ORIGIN (
  echo     ❌ このフォルダは Git で取得したものではありません。
  echo        setup.bat を使わずにコピーした可能性があります。これが原因です。
  echo.
  pause
  exit /b 1
)
echo %ORIGIN% | findstr /c:"@github.com" > nul
if errorlevel 1 (
  echo     取得先: github.com ^(トークンなし^)
  echo     ❌ これが原因です。取得先にトークンが入っていません。
  echo        管理者から受け取った新しい update.bat が、このフォルダに
  echo        上書きできていない可能性があります。
  echo        ファイル名が「update (1).bat」などになっていないか確認してください。
) else (
  echo     取得先: github.com ^(トークンあり^)
)
echo.

echo [5] いまいるブランチ（main でないと更新は届きません）
git rev-parse --abbrev-ref HEAD
echo.

echo [6] 手元で書き換わっているファイル（何も出なければ正常）
git status --short
echo.

echo [7] 最新の情報を取得中...
rem 認証が通らないとき、既定ではログイン画面が出て止まってしまう。
rem 診断中に入力を求めても答えようがないので、その場で失敗させる
set GIT_TERMINAL_PROMPT=0
git fetch origin
if errorlevel 1 (
  echo     ❌ GitHub から取得できませんでした。
  echo        [4] が「トークンなし」だった場合は、それが原因です。
  echo        「トークンあり」なのにここで失敗する場合は、ネットワークまたは
  echo        社内プロキシが原因です。
  echo.
  pause
  exit /b 1
)
echo.

echo [8] GitHub の最新と、手元の差
git status -sb
echo.
echo     「behind」と出ていれば、update.bat で更新できます。
echo     「up to date」なのにバージョンが古い場合は、Chrome が別のフォルダを
echo     読んでいます。chrome://extensions の「ロード元」を確認してください。
echo.

echo ==========================================
echo  診断おわり
echo ==========================================
pause
exit /b 0
