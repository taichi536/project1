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
rem このリポジトリは公開に戻したため、トークンなしが正常な状態になった。
rem 以前はここで「トークンなし」を失敗の原因として表示していたが、いまは
rem 逆に、古いトークン入りの設定が残っている方が失効していて危ない
echo %ORIGIN% | findstr /c:"@github.com" > nul
if errorlevel 1 (
  echo     取得先: github.com ^(トークンなし・正常^)
) else (
  echo     取得先: github.com ^(トークンあり^)
  echo     ❌ 古い設定が残っています。このトークンは失効しています。
  echo        update.bat を実行すると自動で入れ直されるので、まず試してください。
)
echo.

echo [5] いまいるブランチ（main でないと更新は届きません）
git rev-parse --abbrev-ref HEAD
echo.

echo [6] 手元で書き換わっているファイル（何も出なければ正常）
git status --short
rem git の処理が途中で止まると残る。残っている間、更新は何度やっても
rem 同じエラーで止まり続ける（実際にメンバーの端末で発生した）
if exist ".git\index.lock" (
  echo     ❌ 前回の更新が途中で止まった跡 ^(index.lock^) が残っています。
  echo        これが原因です。update.bat をもう一度実行すれば自動で片付きます。
)
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
