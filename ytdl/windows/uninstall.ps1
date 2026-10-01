# YouTube ダウンローダー（Windows 版）のアンインストーラー。
# 設定 →「アプリ」から「アンインストール」を押すと実行される。保存した動画は消さない。

& {
$AppName = 'YouTubeダウンローダー'
$Root = Join-Path $env:LOCALAPPDATA 'YouTubeDownloader'
Add-Type -AssemblyName System.Windows.Forms

$answer = [System.Windows.Forms.MessageBox]::Show(
  "$AppName を削除しますか？`n`n設定と履歴も削除されます。保存した動画は消えません。",
  $AppName, 'YesNo', 'Question')
if ($answer -ne 'Yes') { return }

# 起動中なら止める（このアプリの Python・deno・ffmpeg だけ）
Get-Process python, pythonw, deno, ffmpeg, ffprobe -ErrorAction SilentlyContinue |
  Where-Object { $_.Path -and $_.Path.StartsWith($Root, [StringComparison]::OrdinalIgnoreCase) } |
  Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800

foreach ($dir in [Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop')) {
  Remove-Item -LiteralPath (Join-Path $dir "$AppName.lnk") -Force -ErrorAction SilentlyContinue
}
Remove-Item -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\YouTubeDownloader' -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue

if (Test-Path -LiteralPath $Root) {
  [System.Windows.Forms.MessageBox]::Show(
    "一部のファイルを削除できませんでした。パソコンを再起動してから、次のフォルダを削除してください。`n`n$Root",
    $AppName, 'OK', 'Warning') | Out-Null
} else {
  [System.Windows.Forms.MessageBox]::Show("$AppName を削除しました。", $AppName, 'OK', 'Information') | Out-Null
}
}
