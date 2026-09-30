#!/bin/bash
# 起動の下準備をしてから ytdl_app.py を実行する。
#   - Python 3.10 以上と ffmpeg があるか確認（無ければ入れ方を案内）
#   - 専用の Python 環境を作り、yt-dlp を入れる／1 日 1 回最新にする
#
# --gui を付けると .app から起動されたものとして、案内をダイアログと通知で出す。
# それ以外の引数はそのまま ytdl_app.py に渡す。

GUI=0
if [ "$1" = "--gui" ]; then GUI=1; shift; fi

HERE="$(cd "$(dirname "$0")" && pwd)"
SUPPORT="$HOME/Library/Application Support/YouTubeDownloader"
VENV="$SUPPORT/venv"
LOG="$SUPPORT/launcher.log"
TITLE="YouTube ダウンローダー"
# Finder から起動した .app には Homebrew の PATH が通っていない
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
mkdir -p "$SUPPORT"
# ログが増えすぎないよう 1MB を超えたら空にする
[ -f "$LOG" ] && [ "$(wc -c <"$LOG")" -gt 1000000 ] && : > "$LOG"

# 文字列は引数で渡す（AppleScript に埋め込むと引用符でこわれるため）
dialog() { # メッセージ ボタン... → 押したボタン名を出力
  local msg="$1"; shift
  local buttons="" b
  for b in "$@"; do buttons="$buttons\"$b\", "; done
  buttons="{${buttons%, }}"
  osascript -e 'on run argv' \
    -e "button returned of (display dialog (item 1 of argv) with title (item 2 of argv) buttons $buttons default button $# with icon note)" \
    -e 'end run' "$msg" "$TITLE" 2>/dev/null
}

notify() {
  [ $GUI = 1 ] || { echo "$1"; return; }
  osascript -e 'on run argv' -e 'display notification (item 1 of argv) with title (item 2 of argv)' \
    -e 'end run' "$1" "$TITLE" >/dev/null 2>&1
}

fail() {
  if [ $GUI = 1 ]; then dialog "$1" "OK" >/dev/null; else echo "$1" >&2; fi
  exit 1
}

python_ok() { [ -x "$1" ] && "$1" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; }

find_python() {
  local c
  for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
           /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
           $(command -v python3.14 python3.13 python3.12 python3.11 python3.10 2>/dev/null); do
    python_ok "$c" && { echo "$c"; return 0; }
  done
  # /usr/bin/python3 はコマンドラインツールが無いとインストール画面が出るので、入っているときだけ試す
  if xcode-select -p >/dev/null 2>&1 && python_ok /usr/bin/python3; then
    echo /usr/bin/python3; return 0
  fi
  return 1
}

# ---- 足りないソフトの案内（Homebrew で入れる） ----
PY="$(find_python)"
MISSING=""
[ -n "$PY" ] || MISSING="python"
command -v ffmpeg >/dev/null 2>&1 || MISSING="$MISSING ffmpeg"
MISSING="${MISSING# }"

if [ -n "$MISSING" ]; then
  SETUP="$SUPPORT/準備.command"
  {
    echo '#!/bin/bash'
    echo 'echo "=== YouTube ダウンローダーの準備 ==="'
    if ! command -v brew >/dev/null 2>&1; then
      echo 'echo "Homebrew をインストールします。Mac のログインパスワードを聞かれたら入力してください（画面には表示されません）。"'
      echo '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || exit 1'
      echo 'eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv)"'
    fi
    echo "brew install $MISSING || exit 1"
    echo 'echo; echo "準備ができました。このウィンドウを閉じて、もう一度 YouTube ダウンローダーを開いてください。"'
  } > "$SETUP"
  chmod +x "$SETUP"

  if [ $GUI = 1 ]; then
    MSG="はじめに、必要なソフト（$MISSING）をインストールします。

「準備する」を押すとターミナルが開いて自動で進みます（数分かかります）。終わったら、もう一度このアプリを開いてください。"
    [ "$(dialog "$MSG" "やめる" "準備する")" = "準備する" ] && open "$SETUP"
    exit 0
  fi
  echo "必要なソフト（$MISSING）が足りないので、インストールします。"
  "$SETUP" || exit 1
  PY="$(find_python)" || fail "Python 3.10 以上が見つかりません。"
fi

# ---- 専用の Python 環境と yt-dlp ----
# Homebrew で Python を更新すると古い環境は壊れるので作り直す
if ! python_ok "$VENV/bin/python"; then
  rm -rf "$VENV"
  "$PY" -m venv "$VENV" >>"$LOG" 2>&1 || fail "Python の環境を作れませんでした。くわしくは $LOG を見てください。"
fi

# yt-dlp は YouTube の仕様変更に合わせて頻繁に直るので、1 日 1 回は最新にする。
# [default] で YouTube の解読部品（yt-dlp-ejs）、[deno] でそれを動かす JavaScript 実行環境が入る
FRESH=1
"$VENV/bin/python" -c 'import yt_dlp, yt_dlp_ejs' >/dev/null 2>&1 || FRESH=0
if [ $FRESH = 0 ] || [ -z "$(find "$SUPPORT/.updated" -mtime -1 2>/dev/null)" ]; then
  [ $FRESH = 0 ] && notify "初回の準備をしています（1〜2 分かかります）…"
  if "$VENV/bin/python" -m pip install -q --disable-pip-version-check -U "yt-dlp[default,deno]" >>"$LOG" 2>&1; then
    touch "$SUPPORT/.updated"
  elif [ $FRESH = 0 ]; then
    fail "部品のダウンロードに失敗しました。インターネット接続を確認して、もう一度開いてください。"
  fi
  # 更新に失敗しても、入っている版で動くならそのまま起動する
fi

if [ $GUI = 1 ]; then
  exec "$VENV/bin/python" "$HERE/ytdl_app.py" "$@" >>"$LOG" 2>&1
fi
exec "$VENV/bin/python" "$HERE/ytdl_app.py" "$@"
