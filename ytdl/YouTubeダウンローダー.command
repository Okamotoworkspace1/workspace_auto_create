#!/bin/bash
# ダブルクリックで YouTube ダウンローダーを起動する Mac 用スクリプト。
# 初回だけ専用の Python 環境（.venv）を作り、yt-dlp を入れる。
set -e
cd "$(dirname "$0")"

echo "=== YouTube ダウンローダー ==="

# ffmpeg（MP3 変換・映像と音声の結合に必要）
if ! command -v ffmpeg >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "ffmpeg をインストールします（初回のみ、数分かかります）…"
    brew install ffmpeg
  else
    echo "ffmpeg が見つかりません。先に Homebrew を入れてから、次を実行してください:"
    echo "  brew install ffmpeg"
    echo "Homebrew: https://brew.sh/ja/"
    read -r -p "Enter キーで閉じます"
    exit 1
  fi
fi

PY=python3
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "python3 が見つかりません。ターミナルで次を実行してください:"
  echo "  brew install python"
  read -r -p "Enter キーで閉じます"
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "初回セットアップ中…"
  "$PY" -m venv .venv
fi

# yt-dlp は YouTube 側の変更に合わせて頻繁に更新されるので、毎回最新にする
.venv/bin/python -m pip install -q --disable-pip-version-check -U yt-dlp

exec .venv/bin/python ytdl_app.py "$@"
