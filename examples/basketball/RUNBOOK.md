# ep02 ショートを 1 本完成させる手順

83 秒・9 カット。**Gemini での生成は要りません。** 9 カット全部が
実写 5 枚 ＋ 自作の図解 4 枚で埋まります。

所要：ダウンロードと編集で 1〜2 時間。

---

## Step 0. 準備（初回だけ）

```bash
git clone <このリポジトリ>
cd workspace_auto_create
git checkout claude/nifty-einstein-2t4qul

python3 --version                 # 3.11 以上であること
python3 -m venv .venv && source .venv/bin/activate
python3 -m pip install -e .
```

---

## Step 1. 画像を落とす（5 枚）

```bash
cd examples/basketball/assets
python3 fetch.py
```

`downloads/` に入ります。**ショートで使うのは次の 5 つだけ**です
（他も落ちますが、今回は使いません）。

| ファイル | 中身 |
|---|---|
| `united-center.JPG` | ユナイテッド・センター外観 |
| `curry-2016-wsh.jpg` | カリー 2016 |
| `jordan-1997-ft.jpg` | ジョーダン 1997 |
| `bulls96-wh-1.jpg` | 1996年優勝メンバー集合（ホワイトハウス） |
| `finals96-g6-report.pdf` | 第6戦 公式スコアシート |

**うまくいかないとき**：403 で止まったら社内ネットワーク等が Commons を
塞いでいます。`catalog.tsv` の URL をブラウザで開いて手で保存してください。

### 1-2. PDF を画像にする

`finals96-g6-report.pdf` はそのままでは編集ソフトに置けません。
1 ページ目を PNG にします。

```bash
# macOS なら標準の「プレビュー」で開いて書き出しでも可
pdftoppm -png -r 150 -f 1 -l 1 downloads/finals96-g6-report.pdf downloads/finals96-g6-report
```

---

## Step 2. 図解を書き出す（4 枚）

```bash
cd examples/basketball/assets
python3 make_ep02_short.py --png
```

`ep02_short/` に PNG が出ます（既にコミット済みなので、この手順は
文言を直したときだけで構いません）。

---

## Step 3. 音声と字幕を作る

```bash
cd examples/basketball
```

`jigoe.toml` の `[voice] engine` を `mock` から実際のエンジンに変えます
（`aivisspeech` など）。変えないとダミー音声のままです。

```bash
python3 -m jigoe check scripts/ep02_short.txt --strict   # 要確認 0 件になるはず
python3 -m jigoe speak scripts/ep02_short.txt
```

`out/` に出るもの：

- `ep02_short.wav` … ナレーション（83 秒）
- `ep02_short.srt` … 字幕。台本から作るので固有名詞が化けません
- `ep02_short.report.json` … 全カットのタイムライン

---

## Step 4. 編集ソフトで組む

新規プロジェクトを **1080×1920 / 縦** で作り、`ep02_short.wav` を置きます。
画像をこの表のとおりに並べるだけです。

| # | 時間 | 画像 | 置き方 |
|---|---|---|---|
| 1 | 0:00-0:08 | `ep02_short/01_hook.png` | そのまま |
| 2 | 0:08-0:18 | `ep02_short/02_regular-season.png` | そのまま |
| 3 | 0:18-0:24 | `downloads/united-center.JPG` | 縦に切る。ゆっくり寄る |
| 4 | 0:24-0:30 | `downloads/curry-2016-wsh.jpg` | 縦に切る |
| 5 | 0:30-0:43 | `ep02_short/05a_season-wins.png` | そのまま |
| 6 | 0:43-0:48 | `ep02_short/05b_season-losses.png` | **5 からクロスディゾルブ**。同じ座標なので寄りに見える |
| 7 | 0:48-1:01 | `downloads/jordan-1997-ft.jpg` | 縦に切る |
| 8 | 1:01-1:15 | `downloads/bulls96-wh-1.jpg` | **ロッドマンに寄せて切る**。集合写真のまま出さない |
| 9 | 1:15-1:23 | `downloads/finals96-g6-report-1.png` | スコアシート。ゆっくり寄る |

横位置の写真を縦にするので、**顔が切れていないか 1 枚ずつ確認**してください。

### 動きを付ける

静止画が 8 秒止まると間延びします。全カットに
**ゆっくりした拡大（100% → 108% 程度）**を入れてください。それだけで持ちます。

### 字幕

`out/ep02_short.srt` を読み込みます。自動字幕は使わないでください
（「クーコッチ」などが必ず化けます）。

位置は**下から 25% 以上上**に。下はショートの UI（タイトル・チャンネル名）で
隠れます。`ep02_short/00_safe-area.png` を一番上のレイヤーに一時的に置くと
範囲が見えます。**書き出す前に必ず消してください。**

---

## Step 5. 書き出して投稿

- 1080×1920 / H.264 / 30fps
- タイトル案：`73勝したチームがあるのに、なぜ「72勝」が最強なのか`
- タグ：NBA / シカゴブルズ / マイケルジョーダン / デニスロッドマン / バスケ雑学

概要欄にクレジットを貼ります。

```
【画像クレジット】
1996 Chicago Bulls at the White House — White House photo / Wikimedia Commons — Public Domain
Official Scorer's Report, 1996 NBA Finals Game 6 — Wikimedia Commons
Michael Jordan (1997) — Steve Lipofsky / Wikimedia Commons — CC BY-SA 3.0
  https://creativecommons.org/licenses/by-sa/3.0/
United Center — <ファイルページ記載の著作者> / Wikimedia Commons — CC BY-SA 2.5
  https://creativecommons.org/licenses/by-sa/2.5/
Stephen Curry (2016) — <ファイルページ記載の著作者> / Wikimedia Commons — CC BY-SA 2.0
  https://creativecommons.org/licenses/by-sa/2.0/
図解：本チャンネル制作（出典 Basketball-Reference）
```

`<ファイルページ記載の著作者>` は、Commons のファイルページの「作者」欄を
そのまま写してください。推測で埋めないこと。

---

## 公開前に見ておくこと

**1 本目は出してしまって構いません。** 気になったらここに戻ってください。

- **数字の裏取り**：72-10 / 73-9 / 15-3 / 15-9 / 87-13 / 88-18 を
  Basketball-Reference で確認（`scripts/ep02.outline.md` にリスト）
- **CC BY-SA の継承**：カット 3・4・7 が CC BY-SA です。画像を動画に
  組み込むと動画側にも継承が及び得ます。避けるなら、この 3 カットを
  `bulls96-wh-2`（パブリックドメイン）や b-roll に差し替えると
  CC BY-SA を一切使わずに組めます
- **年代のズレ**：カット 7 のジョーダンは 1997 年です。1996 年の話に
  使っていますが、ユニフォームは同世代なので実用上は問題ありません

---

## 次の回でやること

- `assets/catalog.tsv` に素材を足す（URL を 1 行書くだけ）
- 生成画像を使ったら `種別 = 生成` で足しておくと使い回せる
- カタログが育つほど、探す時間が減ります
