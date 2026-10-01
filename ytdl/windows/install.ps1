# YouTube ダウンローダー（Windows 版）のインストーラー
#
# 管理者権限は不要。必要なもの（Python・yt-dlp・ffmpeg）をすべて自動でダウンロードして
# %LOCALAPPDATA%\YouTubeDownloader に入れ、スタートメニューとデスクトップにショートカットを作る。
# パソコン全体の設定（PATH など）は変えない。
#
# 実行方法（どちらでも同じ）:
#   1) 「インストール.bat」をダブルクリック
#   2) Win + R に次の 1 行を貼って Enter
#      powershell -ep bypass -c "irm https://raw.githubusercontent.com/Okamotoworkspace1/workspace_auto_create/claude/trusting-rubin-1kunv9/ytdl/windows/install.ps1 | iex"
#
# もう一度実行すると最新版に更新される（設定・履歴・保存した動画はそのまま）。
#
# 注意: どちらの方法も、このファイルを UTF-8 として読み込んでから実行する
# （Windows PowerShell 5.1 は BOM の無い .ps1 を Shift_JIS として読むため -File は使わない）。

& {
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'  # Invoke-WebRequest の進捗表示は非常に遅いので消す
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$AppName   = 'YouTubeダウンローダー'
$RepoRaw   = 'https://raw.githubusercontent.com/Okamotoworkspace1/workspace_auto_create/claude/trusting-rubin-1kunv9/ytdl'
$PyVersion = '3.12.10'
$PyUrl     = "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-embed-amd64.zip"
$GetPipUrl = 'https://bootstrap.pypa.io/get-pip.py'
# yt-dlp 向けに調整された ffmpeg（yt-dlp 公式の推奨ビルド）
$FfmpegUrl = 'https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'

$Root    = Join-Path $env:LOCALAPPDATA 'YouTubeDownloader'
$PyDir   = Join-Path $Root 'python'
$FfDir   = Join-Path $Root 'ffmpeg'
$AppDir  = Join-Path $Root 'app'
$Python  = Join-Path $PyDir 'python.exe'
$PythonW = Join-Path $PyDir 'pythonw.exe'
$AppPy   = Join-Path $AppDir 'ytdl_app.py'
$Tmp     = Join-Path ([IO.Path]::GetTempPath()) ('ytdl-setup-' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
$UninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\YouTubeDownloader'

# 「インストール.bat」から実行したときは ytdl フォルダの場所が入る。ネットから直接実行したときは空
$Src = $env:YTDL_SRC

function Step($n, $msg) {
  Write-Host ''
  Write-Host "[$n/6] $msg" -ForegroundColor Cyan
}

function Download($url, $dest) {
  # Windows 10 以降に標準で入っている curl.exe の方が速く、進み具合も出る
  $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
  if ($curl) {
    & $curl.Source -L --fail --retry 3 --progress-bar -o $dest $url
    if ($LASTEXITCODE -ne 0) { throw "ダウンロードに失敗しました: $url" }
  } else {
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
  }
}

function Get-AppFile($rel, $dest) {
  # ZIP から実行したなら手元のファイルを、ネットから実行したなら GitHub から取ってくる
  if ($Src) {
    Copy-Item -LiteralPath (Join-Path $Src $rel) -Destination $dest -Force
  } else {
    Download "$RepoRaw/$rel" $dest
  }
}

function Stop-App {
  # 更新・削除の前に、このアプリの Python・deno・ffmpeg を止める（ほかの Python には触れない）
  Get-Process python, pythonw, deno, ffmpeg, ffprobe -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($Root, [StringComparison]::OrdinalIgnoreCase) } |
    Stop-Process -Force -ErrorAction SilentlyContinue
}

try {
  Write-Host "=== $AppName をインストールします ===" -ForegroundColor Green
  Write-Host '必要なものを自動でダウンロードします（約 250MB。回線によって数分〜10 分ほどかかります）。'
  Write-Host 'このウィンドウは閉じずに、そのままお待ちください。'

  if (-not [Environment]::Is64BitOperatingSystem) { throw '64 ビット版の Windows が必要です。' }
  New-Item -ItemType Directory -Force -Path $Root, $AppDir, $Tmp | Out-Null
  Stop-App

  # ---- 1. Python（埋め込み版。パソコンにすでにある Python とは別に、このアプリ専用に置く）----
  Step 1 'Python を準備しています…'
  $needPy = $true
  if (Test-Path -LiteralPath $Python) {
    try {
      $v = & $Python -c "import sys, pip; print('%d.%d.%d' % sys.version_info[:3])"
      if ($LASTEXITCODE -eq 0 -and $v -eq $PyVersion) { $needPy = $false; Write-Host "  インストール済みです（$v）" }
    } catch { }
  }
  if ($needPy) {
    if (Test-Path -LiteralPath $PyDir) { Remove-Item -LiteralPath $PyDir -Recurse -Force }
    $zip = Join-Path $Tmp 'python.zip'
    Download $PyUrl $zip
    Expand-Archive -LiteralPath $zip -DestinationPath $PyDir -Force
    # 埋め込み版は既定で追加ライブラリを読まないので、site を有効にして pip を使えるようにする
    $pth = Get-ChildItem -LiteralPath $PyDir -Filter 'python*._pth' | Select-Object -First 1
    (Get-Content -LiteralPath $pth.FullName) -replace '^#\s*import site', 'import site' |
      Set-Content -LiteralPath $pth.FullName -Encoding ASCII
    $getPip = Join-Path $Tmp 'get-pip.py'
    Download $GetPipUrl $getPip
    & $Python $getPip --no-warn-script-location --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { throw 'pip の準備に失敗しました。' }
  }

  # ---- 2. yt-dlp（[default] で YouTube の解読部品、[deno] でそれを動かす実行環境も入る）----
  Step 2 'ダウンロード部品（yt-dlp）を入れています…'
  & $Python -m pip install -U --disable-pip-version-check --no-warn-script-location 'yt-dlp[default,deno]'
  if ($LASTEXITCODE -ne 0) { throw 'yt-dlp のインストールに失敗しました。' }
  New-Item -ItemType File -Force -Path (Join-Path $Root '.updated') | Out-Null

  # ---- 3. ffmpeg（MP3 への変換と、映像・音声の結合に使う）----
  Step 3 'ffmpeg（変換ソフト）を準備しています…'
  if ((Test-Path -LiteralPath (Join-Path $FfDir 'ffmpeg.exe')) -and (Test-Path -LiteralPath (Join-Path $FfDir 'ffprobe.exe'))) {
    Write-Host '  インストール済みです'
  } else {
    $zip = Join-Path $Tmp 'ffmpeg.zip'
    Download $FfmpegUrl $zip
    New-Item -ItemType Directory -Force -Path $FfDir | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $z = [IO.Compression.ZipFile]::OpenRead($zip)
    try {
      # 中身は 400MB 近くあるので、必要な 2 つだけ取り出す
      foreach ($name in 'ffmpeg.exe', 'ffprobe.exe') {
        $entry = $z.Entries | Where-Object { $_.FullName -like "*/bin/$name" } | Select-Object -First 1
        if (-not $entry) { throw "ffmpeg の中に $name が見つかりませんでした。" }
        [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, (Join-Path $FfDir $name), $true)
      }
    } finally {
      $z.Dispose()
    }
  }

  # ---- 4. アプリ本体 ----
  Step 4 'アプリ本体をコピーしています…'
  Get-AppFile 'ytdl_app.py' $AppPy
  Get-AppFile 'windows/icon.ico' (Join-Path $AppDir 'icon.ico')
  Get-AppFile 'windows/uninstall.ps1' (Join-Path $AppDir 'uninstall.ps1')

  # ---- 5. ショートカットと「アプリと機能」への登録 ----
  Step 5 'ショートカットを作っています…'
  $shell = New-Object -ComObject WScript.Shell
  $links = @(
    (Join-Path ([Environment]::GetFolderPath('Programs')) "$AppName.lnk"),
    (Join-Path ([Environment]::GetFolderPath('Desktop')) "$AppName.lnk")
  )
  foreach ($path in $links) {
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = $PythonW  # pythonw は黒い窓を出さない
    $lnk.Arguments = "`"$AppPy`" --auto-update"
    $lnk.WorkingDirectory = $AppDir
    $lnk.IconLocation = (Join-Path $AppDir 'icon.ico') + ',0'
    $lnk.Description = 'YouTube の動画を MP4 / MP3 で保存します'
    $lnk.Save()
    Write-Host "  $path"
  }

  # 設定 →「アプリ」の一覧に出して、そこからアンインストールできるようにする
  $uninstallPs1 = (Join-Path $AppDir 'uninstall.ps1') -replace "'", "''"
  $sizeKB = [int]((Get-ChildItem -LiteralPath $Root -Recurse -File | Measure-Object Length -Sum).Sum / 1KB)
  New-Item -Path $UninstallKey -Force | Out-Null
  $props = @{
    DisplayName     = $AppName
    DisplayVersion  = '2.0'
    Publisher       = $AppName
    DisplayIcon     = (Join-Path $AppDir 'icon.ico')
    InstallLocation = $Root
    UninstallString = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command `"iex ([IO.File]::ReadAllText('$uninstallPs1'))`""
  }
  foreach ($k in $props.Keys) { Set-ItemProperty -Path $UninstallKey -Name $k -Value $props[$k] }
  foreach ($k in 'NoModify', 'NoRepair') { Set-ItemProperty -Path $UninstallKey -Name $k -Value 1 -Type DWord }
  Set-ItemProperty -Path $UninstallKey -Name 'EstimatedSize' -Value $sizeKB -Type DWord

  # ---- 6. 起動 ----
  Step 6 '起動します'
  Start-Process -FilePath $PythonW -ArgumentList "`"$AppPy`"" -WorkingDirectory $AppDir

  Write-Host ''
  Write-Host 'インストールが完了しました！' -ForegroundColor Green
  Write-Host 'ブラウザに画面が開きます。次からはデスクトップかスタートメニューの'
  Write-Host "「$AppName」から開けます。"
} catch {
  Write-Host ''
  Write-Host "インストールに失敗しました: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host 'インターネット接続を確認して、もう一度実行してください。'
  Write-Host '何度も失敗する場合は、この画面の内容を作者に伝えてください。'
} finally {
  Remove-Item -LiteralPath $Tmp -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ''
Read-Host 'Enter キーでこのウィンドウを閉じます' | Out-Null
}
