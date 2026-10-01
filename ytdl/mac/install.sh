#!/bin/bash
# YouTube ダウンローダー（Mac 版）のインストーラー。ターミナルに次の 1 行を貼って Enter:
#
#   curl -fsSL https://raw.githubusercontent.com/Okamotoworkspace1/workspace_auto_create/claude/trusting-rubin-1kunv9/ytdl/mac/install.sh | bash
#
# Homebrew も管理者パスワードも要らない。必要なものはすべて
# ~/Library/Application Support/YouTubeDownloader に入り、アプリは「アプリケーション」に置かれる。
# もう一度実行すると最新版に更新される（設定・履歴・保存した動画はそのまま）。
set -e
BASE="https://raw.githubusercontent.com/Okamotoworkspace1/workspace_auto_create/claude/trusting-rubin-1kunv9/ytdl"

echo "=== YouTubeダウンローダー をインストールします ==="
echo "必要なものを自動でダウンロードします（約 200MB。回線によって数分かかります）。"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
for f in ytdl_app.py launcher.sh make_app.sh make_icon.py; do
  curl -fsSL "$BASE/$f" -o "$TMP/$f" || { echo "ダウンロードに失敗しました: $f（インターネット接続を確認してください）" >&2; exit 1; }
done
chmod +x "$TMP/launcher.sh" "$TMP/make_app.sh"

# 起動中なら、更新のために終わらせる
SUPPORT="$HOME/Library/Application Support/YouTubeDownloader"
pkill -f "$SUPPORT/venv/bin/python" 2>/dev/null || true

"$TMP/make_app.sh"
echo
echo "インストールが完了しました！ ブラウザに画面が開きます。"
echo "次からは Launchpad か Spotlight（⌘ + スペース →「YouTube」）で開けます。"
