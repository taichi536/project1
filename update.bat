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

rem git の処理が途中で止まると .git\index.lock が残り、それ以降の更新が何度やっても
rem 同じエラーで止まり続ける（「Unable to create ... index.lock: File exists」）。
rem 実際にメンバーの端末で発生した。フォルダが OneDrive の中にあると、同期が
rem ファイルを掴むため残りやすい。
rem git が動いていないことを確かめてから片付ける。動いている最中に消すと
rem そちらの処理を壊すため、その場合は消さずに止める
if exist ".git\index.lock" (
  tasklist /fi "imagename eq git.exe" 2>nul | findstr /i "git.exe" > nul
  if errorlevel 1 (
    del /f /q ".git\index.lock" > nul 2>&1
    echo 前回の更新が途中で止まった跡を片付けました。
    echo.
  ) else (
    echo ❌ 別の更新がまだ動いています。
    echo.
    echo 開いている「アップデート」の黒い画面を全部閉じて、
    echo 1分ほど待ってから、もう一度このファイルを実行してください。
    echo.
    pause
    exit /b 1
  )
)

rem Python を動かすと __pycache__ フォルダが残る。gitの管理対象外なので更新では
rem 消されないが、gitが削除しようとしているフォルダの中に残っていると
rem 「Deletion of directory failed. Should I try again? (y/n)」で更新が止まる。
rem 実際にメンバーの端末で、別プロジェクトの modules フォルダがこれで消せず
rem 止まった。消しても必要になれば作り直されるだけのものなので、先に片付ける
for /d /r %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul

rem git pull の成否を必ず見る。以前は失敗しても「更新完了」と表示していたため、
rem ネットワークが切れていても、ローカルに変更が残って pull が止まっていても、
rem 画面上は成功したように見えていた
git pull
if not errorlevel 1 goto :updated

rem ここに来た＝pullが失敗した。更新を妨げるものを片付けて一度だけやり直す。
rem メンバーはこのフォルダの中身を編集しない前提なので、手元の書き換えは
rem 元に戻してよい（「ファイルを直接編集してしまった」は実際に起きた原因のひとつ）。
rem index.lock は、たった今失敗したgit自身が残したもの（別のgitが動いている
rem 場合は冒頭のチェックで既に止めている）なので、消して安全
echo.
echo 更新を妨げているものを片付けて、もう一度試します...
echo （このフォルダの中で書き換わったファイルは元に戻します）
echo.
if exist ".git\index.lock" del /f /q ".git\index.lock" > nul 2>&1
for /d /r %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
git checkout -- . > nul 2>&1
git pull
if not errorlevel 1 goto :updated

:failed
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
echo 「index.lock」と出ている場合は、OneDrive の同期が邪魔をしています。
echo 画面右下の OneDrive アイコンから「同期の一時停止」をして、
echo もう一度このファイルを実行してください。
echo.
echo 「Authentication failed」と出ている場合は、管理者に連絡してください。
echo.
echo ※ このまま Chrome を再読み込みしても、バージョンは変わりません。
echo.
pause
exit /b 1

:updated
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
