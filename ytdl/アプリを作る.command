#!/bin/bash
# ダブルクリックすると「YouTubeダウンローダー」アプリを作って、アプリケーションフォルダに入れる。
"$(dirname "$0")/make_app.sh"
echo
read -r -p "Enter キーでこのウィンドウを閉じます"
