#!/bin/bash
# 「YouTubeダウンローダー.app」を作って /Applications（書けなければ ~/Applications）に置く。
# アプリは ytdl_app.py と launcher.sh のコピーを中に持つので、このフォルダを
# 動かしたり消したりしても動く。ytdl_app.py を更新したら、もう一度実行すれば置き換わる。
#
#   ./make_app.sh            # 作ってすぐ起動
#   DEST=~/Desktop ./make_app.sh --no-open
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
NAME="YouTubeダウンローダー"
BUNDLE_ID="local.youtube-downloader"

if [ -z "$DEST" ]; then
  if [ -w /Applications ]; then DEST=/Applications; else DEST="$HOME/Applications"; fi
fi
mkdir -p "$DEST"
APP="$DEST/$NAME.app"

# 同名の別アプリを消してしまわないよう、自分が作ったものだけ置き換える
if [ -e "$APP" ]; then
  if grep -q "$BUNDLE_ID" "$APP/Contents/Info.plist" 2>/dev/null; then
    rm -rf "$APP"
  else
    echo "$APP はこのツールで作ったものではないため、置き換えません。" >&2
    exit 1
  fi
fi

mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$HERE/ytdl_app.py" "$HERE/launcher.sh" "$APP/Contents/Resources/"
chmod +x "$APP/Contents/Resources/launcher.sh"

cat > "$APP/Contents/MacOS/YouTubeDownloader" <<'EOF'
#!/bin/bash
exec "$(dirname "$0")/../Resources/launcher.sh" --gui
EOF
chmod +x "$APP/Contents/MacOS/YouTubeDownloader"

# LSUIElement: 画面はブラウザなので Dock にアイコンを出さない
cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>YouTubeDownloader</string>
  <key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
  <key>CFBundleName</key><string>$NAME</string>
  <key>CFBundleDisplayName</key><string>$NAME</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>2.0</string>
  <key>CFBundleVersion</key><string>2</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>LSUIElement</key><true/>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
EOF

# 必要な部品（Python・yt-dlp・ffmpeg）をここで入れておく。進み具合をターミナルに出せるので、
# アプリの初回起動で黙って待たせるより分かりやすい
echo
echo "必要な部品を準備しています（初回は数分かかります）…"
"$APP/Contents/Resources/launcher.sh" --prepare

# アイコン（sips・iconutil が無ければ、標準のアイコンのまま）
PY="$HOME/Library/Application Support/YouTubeDownloader/venv/bin/python"
if [ -x "$PY" ] && command -v sips >/dev/null && command -v iconutil >/dev/null; then
  TMP="$(mktemp -d)"
  ICONSET="$TMP/AppIcon.iconset"
  mkdir "$ICONSET"
  echo "アイコンを作っています…"
  if "$PY" "$HERE/make_icon.py" "$TMP/icon.png"; then
    for s in 16 32 128 256 512; do
      sips -z $s $s "$TMP/icon.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
      sips -z $((s * 2)) $((s * 2)) "$TMP/icon.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
    done
    iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns" || true
  fi
  rm -rf "$TMP"
fi

# Finder に新しいアイコンを反映させる
touch "$APP"
LSREGISTER=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
[ -x "$LSREGISTER" ] && "$LSREGISTER" -f "$APP" >/dev/null 2>&1 || true

echo
echo "アプリを作りました: $APP"
echo "Launchpad や Spotlight（⌘ + スペース →「YouTube」）から開けます。"

if [ "$1" != "--no-open" ] && command -v open >/dev/null; then
  open -R "$APP"
  open "$APP"
fi
