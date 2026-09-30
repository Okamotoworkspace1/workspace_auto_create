#!/bin/bash
# ダブルクリックで YouTube ダウンローダーを起動する（ターミナル版）。
# ターミナルを出さずに使いたいときは「アプリを作る.command」でアプリにしてください。
exec "$(dirname "$0")/launcher.sh" "$@"
