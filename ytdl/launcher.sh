#!/bin/bash
# 起動の下準備をしてから ytdl_app.py を実行する（Mac 用）。Homebrew も管理者パスワードも要らない。
#   - uv（Python の管理ツール）をこのアプリ専用に入れ、それで Python を用意する
#   - yt-dlp・deno・ffmpeg（imageio-ffmpeg に入っている署名済みの ffmpeg）を専用環境に入れる
#   - yt-dlp の 1 日 1 回の更新は、ytdl_app.py --auto-update が起動時に行う
# すべて ~/Library/Application Support/YouTubeDownloader の中に入り、Mac の他の部分には触れない。
#
#   --gui      .app から起動されたとき。進み具合やエラーを通知・ダイアログで出す
#   --prepare  準備だけして終わる（インストーラーがターミナルで進み具合を見せるため）
# それ以外の引数はそのまま ytdl_app.py に渡す。

GUI=0
PREPARE=0
while :; do
  case "$1" in
    --gui) GUI=1; shift ;;
    --prepare) PREPARE=1; shift ;;
    *) break ;;
  esac
done

HERE="$(cd "$(dirname "$0")" && pwd)"
SUPPORT="$HOME/Library/Application Support/YouTubeDownloader"
VENV="$SUPPORT/venv"
UV="$SUPPORT/bin/uv"
LOG="$SUPPORT/launcher.log"
TITLE="YouTube ダウンローダー"
PACKAGES=("yt-dlp[default,deno]" "imageio-ffmpeg")
# uv が落とす Python やキャッシュも、このアプリのフォルダにまとめる（削除はフォルダごとで済む）
export UV_PYTHON_INSTALL_DIR="$SUPPORT/python"
export UV_CACHE_DIR="$SUPPORT/cache"
export UV_NO_CONFIG=1
mkdir -p "$SUPPORT"
# ログが増えすぎないよう 1MB を超えたら空にする
[ -f "$LOG" ] && [ "$(wc -c <"$LOG")" -gt 1000000 ] && : > "$LOG"

say() { if [ $GUI = 1 ]; then echo "$1" >>"$LOG"; else echo "$1"; fi; }
run() { if [ $GUI = 1 ]; then "$@" >>"$LOG" 2>&1; else "$@"; fi; }

# 文字列は引数で渡す（AppleScript に埋め込むと引用符でこわれるため）
notify() {
  [ $GUI = 1 ] || return 0
  osascript -e 'on run argv' -e 'display notification (item 1 of argv) with title (item 2 of argv)' \
    -e 'end run' "$1" "$TITLE" >/dev/null 2>&1
}

fail() {
  if [ $GUI = 1 ]; then
    osascript -e 'on run argv' \
      -e 'display dialog (item 1 of argv) with title (item 2 of argv) buttons {"OK"} default button 1 with icon caution' \
      -e 'end run' "$1" "$TITLE" >/dev/null 2>&1
  else
    echo "$1" >&2
  fi
  exit 1
}

NET_ERROR="必要な部品をダウンロードできませんでした。インターネット接続を確認して、もう一度開いてください。"

# ---- 1. uv ----
if [ ! -x "$UV" ]; then
  case "$(uname -m)" in
    arm64) ARCH=aarch64 ;;
    x86_64) ARCH=x86_64 ;;
    *) fail "この Mac（$(uname -m)）には対応していません。" ;;
  esac
  notify "初回の準備をしています（数分かかります）…"
  say "Python の管理ツール（uv）をダウンロードしています…"
  TMP="$(mktemp -d)"
  if [ $GUI = 1 ]; then PROGRESS=-s; else PROGRESS=--progress-bar; fi
  curl -fL $PROGRESS "https://github.com/astral-sh/uv/releases/latest/download/uv-$ARCH-apple-darwin.tar.gz" \
    | tar xz -C "$TMP" || { rm -rf "$TMP"; fail "$NET_ERROR"; }
  mkdir -p "$(dirname "$UV")"
  mv "$TMP"/*/uv "$UV" || { rm -rf "$TMP"; fail "$NET_ERROR"; }
  rm -rf "$TMP"
fi

# ---- 2. 専用の Python 環境 ----
# 目印の無い環境（以前の版が Homebrew の Python で作ったもの）や壊れた環境は作り直す
if [ ! -f "$VENV/.uv" ] || ! "$VENV/bin/python" -c 'import sys' >/dev/null 2>&1; then
  notify "初回の準備をしています（数分かかります）…"
  say "Python を準備しています…"
  rm -rf "$VENV"
  run "$UV" venv --quiet --managed-python --python 3.12 "$VENV" || fail "$NET_ERROR"
  touch "$VENV/.uv"
fi

# ---- 3. yt-dlp・deno・ffmpeg ----
if ! "$VENV/bin/python" -c 'import yt_dlp, yt_dlp_ejs, imageio_ffmpeg' >/dev/null 2>&1; then
  notify "初回の準備をしています（数分かかります）…"
  say "ダウンロード部品（yt-dlp・ffmpeg など）を入れています…"
  run "$UV" pip install --quiet --python "$VENV/bin/python" -U "${PACKAGES[@]}" || fail "$NET_ERROR"
  touch "$SUPPORT/.updated"
fi

# ytdl_app.py は「ffmpeg」フォルダを PATH の先頭に足すので、そこに ffmpeg という名前で置く。
# ハードリンクにするのは、更新で元のファイルが消えても使い続けられるようにするため
FF="$("$VENV/bin/python" -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())' 2>/dev/null)"
if [ -n "$FF" ] && [ -x "$FF" ]; then
  mkdir -p "$SUPPORT/ffmpeg"
  ln -f "$FF" "$SUPPORT/ffmpeg/ffmpeg" 2>/dev/null || cp -f "$FF" "$SUPPORT/ffmpeg/ffmpeg"
fi

if [ $PREPARE = 1 ]; then
  say "準備ができました。"
  exit 0
fi
# 画面を開くときだけ、起動前に yt-dlp を最新にする（URL を渡したときは待たせない）
[ $# -eq 0 ] && set -- --auto-update
if [ $GUI = 1 ]; then
  exec "$VENV/bin/python" "$HERE/ytdl_app.py" "$@" >>"$LOG" 2>&1
fi
exec "$VENV/bin/python" "$HERE/ytdl_app.py" "$@"
