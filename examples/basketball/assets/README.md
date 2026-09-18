# ep02_short 素材リスト

`scripts/ep02_short.txt`（縦型ショート・83 秒）用。

素材は**探してくるのが原則**です。このディレクトリに自分で作ったものが 5 点ありますが、
それは「探してこられない絵」＝数字の図解だけに絞ってあります。
人物・会場・試合の画は、下の素材表のとおり外部から持ってきてください。

> **重要：このリポジトリに画像の実体は入っていません。**
> 作業環境から commons.wikimedia.org・unsplash・pexels などへの通信が
> 組織のネットワークポリシーで遮断されており、ファイルを取得できませんでした。
> 下の表の URL を開いて、手元でダウンロードしてください。
> あわせて、**著作者名とライセンスは必ずファイルページの表示をそのまま写してください。**
> 表の「ライセンス」欄は検索結果に出ていた表示であり、こちらで原本を開いて
> 確認できていません。改名・再ライセンス・削除が起きている可能性があります。

---

## 1. 探すときの前提（先に読む）

### 1995-96 シーズンの試合写真・映像は、実質的に手に入りません

当時の試合映像の著作権は NBA が持ち、Content ID に全試合分が登録されています。
写真も NBAE / Getty の管理で、エディトリアル契約は収益化 YouTube を通常カバーしません。
**「1996年ファイナルの映像を貼る」は選択肢から外してください。**

代わりに使えるものは 3 種類です。

| 種類 | 入手先 | 備考 |
|---|---|---|
| 自由ライセンスの人物写真 | Wikimedia Commons | 1996年のものはほぼ無い。**年代違いを承知で使う** |
| 一次資料（記録） | Commons ほか | 公式記録は絵として強い。下の Game 6 スコアシート |
| 汎用 b-roll | Pexels / Pixabay | 選手は写らない。画をつなぐ用 |

### CC BY-SA を動画に入れると、動画側にも SA が及ぶ可能性があります

下の候補はほぼ全部 **CC BY-SA**（継承）です。画像を動画に組み込んだものが
「二次的著作物」と評価されると、**動画全体を同じ CC BY-SA で公開する義務**が
生じ得ます。解釈が割れている論点で、判例で固まってはいません。

収益化チャンネルでこれを避けたいなら、選択肢は次のどれかです。

1. **CC BY-SA を使わない。** Pexels / Pixabay の b-roll と自作図解だけで組む
   （このショートは数字が主役なので、これでも成立します）
2. **SA を受け入れる。** 概要欄で動画を CC BY-SA として明示する
3. **権利者から直接ライセンスを得る。** 下の Lipofsky 氏は自身のサイトで
   写真をライセンスしています（basketballphoto.com）。個別交渉が最も安全

**判断は法務リスクの取り方なので、こちらでは決められません。** 1 を既定にしてあります。

### ロゴは別問題です

`File:Chicago Bulls logo.svg` などは Commons にありますが、**商標**です。
ライセンス表記が緩くても、チームロゴの使用は商標・パブリシティの問題が残ります。
サムネイルでの使用は特に避けてください。

---

## 2. 素材表（カット順）

タイムコードは `out/ep02_short.srt` の実測値です。

| 時間 | 必要な絵 | 素材 | 出所 | ライセンス（要確認） |
|---|---|---|---|---|
| 0:00-0:08 | 72勝10敗を置く | `ep02_short/01_hook.png` | **自作** | — |
| 〃 | 下地のジョーダン | [File:Jordan by Lipofsky 16577.jpg](https://commons.wikimedia.org/wiki/File:Jordan_by_Lipofsky_16577.jpg) | Commons / Steve Lipofsky | CC BY-SA 3.0 |
| 0:08-0:18 | 72 対 73 の比較 | `ep02_short/02_regular-season.png` | **自作** | — |
| 〃 | ウォリアーズ側の顔 | [File:Stephen Curry (24180454343).jpg](https://commons.wikimedia.org/wiki/File:Stephen_Curry_(24180454343).jpg) | Commons（2015-16シーズン） | CC BY-SA 2.0 |
| 0:18-0:24 | 「なぜか」のテロップ下地 | [File:United Center, Chicago.JPG](https://commons.wikimedia.org/wiki/File:United_Center,_Chicago.JPG) | Commons | CC BY-SA 2.5 |
| 0:24-0:30 | ウォリアーズ敗退 / ブルズ優勝 | [File:Stephen Curry vs Washington 2016.jpg](https://commons.wikimedia.org/wiki/File:Stephen_Curry_vs_Washington_2016.jpg) ＋ [File:Jordan Lipofsky.jpg](https://commons.wikimedia.org/wiki/File:Jordan_Lipofsky.jpg) | Commons | CC BY-SA 2.0 / 3.0 |
| 0:30-0:43 | 87-13 と 88-18 | `ep02_short/05a_season-wins.png` | **自作** | — |
| 0:43-0:48 | 負けた数を強調 | `ep02_short/05b_season-losses.png` | **自作**（05a と同座標。ディゾルブで寄りになる） | — |
| 0:48-1:01 | 前年の敗退・背番号45 | [File:Jordan Lipofsky.jpg](https://commons.wikimedia.org/wiki/File:Jordan_Lipofsky.jpg) | Commons / Steve Lipofsky | CC BY-SA 3.0 |
| 1:01-1:15 | ロッドマン | [Category:Dennis Rodman](https://commons.wikimedia.org/wiki/Category:Dennis_Rodman) から選ぶ | Commons | 個別に確認 |
| 1:15-1:23 | 落ち | [File:Official Scorer's Report - Game 6 of 1996 NBA Finals.pdf](https://commons.wikimedia.org/wiki/File:Official_Scorer%27s_Report_-_Game_6_of_1996_NBA_Finals.pdf) | Commons | **要確認** |
| 全編 | つなぎの b-roll | [Pexels basketball](https://www.pexels.com/search/videos/basketball/) / [Pixabay basketball](https://pixabay.com/videos/search/basketball/) | 各サイト | 独自ライセンス・帰属不要 |

### 特筆したい 1 点

**Game 6 の公式スコアラーズレポート**（1996年6月16日）が Commons にあります。
実際のボックススコアなので、選手写真より強い一次資料です。落ちに紙の記録を出すのは
このネタと相性が良いので、まずここのライセンス確認を勧めます。

### 年代のズレについて

自由ライセンスで手に入るジョーダンは **1987年と1997年**、ロッドマンは
**引退後**のものが中心です。1995-96 シーズンの写真はありません。

- ジョーダンの 1997 年はユニフォームが同世代なので、**そのまま使えます**
- ロッドマンの引退後写真を「1995年に加入した問題児」として出すのは**無理があります**。
  この区間は自作のタイポグラフィか b-roll で逃げるほうが誠実です
- 写真に年が写り込む場合、テロップで「写真は1997年」と添えると事故になりません

---

## 3. クレジット（概要欄に貼る）

CC BY-SA は**著作者名・ライセンス名・ライセンスへのリンク**の 3 点が必須です。
動画内表示だけでなく、概要欄にも残してください。

```
【画像クレジット】
Michael Jordan (1997) — Steve Lipofsky / Wikimedia Commons — CC BY-SA 3.0
  https://creativecommons.org/licenses/by-sa/3.0/
United Center — <ファイルページ記載の著作者> / Wikimedia Commons — CC BY-SA 2.5
  https://creativecommons.org/licenses/by-sa/2.5/
Stephen Curry (2016) — <ファイルページ記載の著作者> / Wikimedia Commons — CC BY-SA 2.0
  https://creativecommons.org/licenses/by-sa/2.0/

b-roll: Pexels / Pixabay
図解: 本チャンネル制作（出典 Basketball-Reference）
```

`<ファイルページ記載の著作者>` は、こちらで原本を開けなかった箇所です。
**推測で埋めず、ファイルページの「作者」欄をそのまま写してください。**

---

## 4. 自作した 5 点について

数字の図解は探してこられないので、ここだけ自作しています。
`docs/workflow.md` が求める「動画ごと最低 1 点の独自図解」も兼ねます。

```bash
python3 make_ep02_short.py --png      # SVG と PNG を書き出す
JIGOE_FONT="Noto Sans JP" python3 make_ep02_short.py --png   # フォントを差し替える
```

| ファイル | 内容 |
|---|---|
| `00_safe-area` | ショートの UI が乗る範囲のガイド。書き出しには乗せない |
| `01_hook` | 72勝10敗のヒーロー数字 |
| `02_regular-season` | レギュラーシーズン勝利数 72 対 73 |
| `05a_season-wins` | 通年 87勝13敗 と 88勝18敗 |
| `05b_season-losses` | 同じ座標で敗戦を強調した状態 |

- 1080×1920。内容はセーフエリア（x 80-880 / y 200-1480）に収めてあります
- 配色は青と赤の 2 色。色覚多様性の検証済み（CVD ΔE 19.2、全チェック PASS）で、
  かつ**色だけに意味を持たせず全ての棒に直接ラベル**を置いています
- 棒はゼロ基点です。72 と 73 の差が小さく見えるのは事実どおりで、そこが要点です
- SVG が原本なので、フォント・文言はテキストエディタで直せます

---

## 5. 未確認事項

公開前に潰してください。

- [ ] 各ファイルページを開き、**著作者名・ライセンス・現存**を確認する
- [ ] Game 6 スコアラーズレポートのライセンス根拠を確認する
- [ ] CC BY-SA を使うか（1 / 2 / 3 のどれを取るか）を決める
- [ ] ロッドマンの区間を、写真で行くか自作で行くか決める
- [ ] 数字（72-10 / 73-9 / 15-3 / 15-9 / 87-13 / 88-18）を
      Basketball-Reference で再確認する → `scripts/ep02.outline.md`
