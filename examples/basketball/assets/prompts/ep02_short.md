# ep02_short 画像生成プロンプト（Gemini 用）

**基本は実写です。** 各カットの「実写（第一候補）」を先に当てて、
埋まらなかったところだけ生成してください。

タイムコードは `out/ep02_short.srt` の実測値（全 83 秒・9 カット）。

---

## 先に：生成では作れないもの

| 作れない | 理由 | どうするか |
|---|---|---|
| **実在人物**（ジョーダン、ロッドマン、カリー） | 画像生成は実在人物の肖像を作らない。作れても肖像権・パブリシティ権が残る | カタログの実写を使う |
| **チームのロゴ・ユニフォーム** | 商標 | ロゴなしの無地で生成し、必要な記号はテロップで足す |
| **日本語のテロップ** | 文字が崩れる | 編集ソフトで乗せる |

つまり**人物が要るカットは実写、雰囲気をつなぐカットは生成**という切り分けになります。
下の 9 カットのうち、7・8 は人物が主題なので実写を優先してください。

## 共通のスタイル（全カットの先頭に必ず付ける）

これを付けないと 9 枚が別々の動画のように見えます。

```
Cinematic still, vertical 9:16 aspect ratio, 1990s American basketball arena.
Shot on 35mm film, warm tungsten lighting, deep shadows, fine film grain,
muted palette of deep red, amber and near-black. Shallow depth of field.
No faces, no text, no numbers, no logos, no brand marks.
Keep the lower third dark and uncluttered so subtitles stay readable.
```

9:16 が無視されるようなら正方形で出してから縦に切ってください。

---

## カット 1 — 0:00-0:08

> NBAで歴代最強のチームは、72勝10敗のシカゴ・ブルズ。1996年です。

映すもの：掴み。誰もいない会場に一筋の光。

実写（第一候補）：`bulls96-wh-1`（1996年優勝メンバーの集合写真）／`united-center`

```
An empty basketball arena seen from the mouth of a dark player tunnel.
A single hard spotlight falls on the center circle of polished hardwood.
Thousands of empty seats fade into blackness. Dust drifting in the light beam.
```

## カット 2 — 0:08-0:18

> でも、この記録、もう破られています。2016年のウォリアーズが、73勝。1つ上です。

映すもの：記録が古びる感じ。数字は自作図解で乗せるので、絵に数字は要りません。

実写（第一候補）：`curry-201516`（73勝シーズンのカリー）

```
A low-angle view of an old hanging arena scoreboard, its bulbs dark and dusty,
against the black ceiling rigging of an empty arena.
Cold blue light from one side, warm amber from the other.
```

## カット 3 — 0:18-0:24

> なのに、最強と呼ばれるのは、いまだにブルズのほう。なぜか。

映すもの：問いの間。人の気配だけ残して誰もいない。

実写（第一候補）：`united-center`

```
An empty 1990s locker room. A row of wooden lockers, one door left open,
a folded white towel on the bench. Dim overhead light, long shadows on the floor.
```

## カット 4 — 0:24-0:30

> ウォリアーズは、そのシーズン、ファイナルで負けました。

映すもの：終わった後の会場。**2枚作って優勝側と対比させると効きます。**

実写（第一候補）：`curry-2016-wsh`

敗退側:
```
A dark, empty basketball court after a game. Scattered confetti lies unswept
on the hardwood, lit only by a single distant work light.
Cold, desaturated blue-grey. The feeling of an ending that went wrong.
```

優勝側（カット 5 の頭で一瞬入れる）:
```
Golden confetti falling through the air of a basketball arena, caught in warm
spotlights above an empty hardwood court. Bright, celebratory, background out of focus.
```

## カット 5 — 0:30-0:43

> ブルズは、プレーオフも15勝3敗で通過して、優勝しています。合計、87勝13敗。
> 勝った数だけなら、じつはウォリアーズが上です。

映すもの：**自作図解 `05a_season-wins` が主役。** これはその下地です。

```
Extreme close-up of polished basketball hardwood, a painted boundary line
running diagonally, scuffed with sneaker marks. Warm overhead light.
Very shallow depth of field, most of the frame clean and dark.
```

## カット 6 — 0:43-0:48

> 88勝18敗。違うのは、負けた数でした。

映すもの：**自作図解 `05b_season-losses` が主役。** カット 5 と同じ絵を暗くした下地。

```
The same polished hardwood close-up, lit only by a narrow amber slash of light,
most of the frame in deep shadow.
```

## カット 7 — 0:48-1:01 ★実写を優先

> しかも、このチームは前の年、プレーオフで負けているんです。
> ジョーダンが野球から戻って、背番号45で、オーランドに敗退した年。

映すもの：ジョーダン本人。**ここは生成で代替しないでください。**

実写（第一候補）：`jordan-1997-ft`（1997年。ユニフォームは同世代）

生成で逃げる場合（背番号「45」はテロップで乗せる）:
```
A plain white basketball jersey hanging alone on a hook in a dim locker room,
seen from behind, the fabric worn and creased.
No numbers, no lettering, no logos. Single warm light from above, deep shadow around it.
```

## カット 8 — 1:01-1:15 ★実写を優先

> そこに足したのが、デニス・ロッドマン。審判と揉め、監督と衝突し、
> どこも持て余していた男です。翌年、ブルズは87勝13敗で終わりました。

映すもの：ロッドマン本人。**ここも生成では作れません。**

実写（第一候補）：`bulls96-wh-1` から抜く（1996年当時の本人が写っている）

つなぎに生成を挟む場合:
```
A basketball striking the rim and bouncing away, frozen mid-air, shot from below
against dark arena rafters and hard white lights. Motion blur on the net. No people.
```

## カット 9 — 1:15-1:23

> 最強って、勝った数の話じゃないのかもしれません。取りこぼさなかった、という話です。

映すもの：落ち。静かに引く。

実写（第一候補）：`finals96-g6-report`（第6戦の公式スコアシート）／`bulls96-wh-video`

```
A single basketball resting alone at the center circle of an empty, dimly lit
hardwood court, shot from a low angle. The arena lights are dimming.
Quiet and final, warm amber falling off into black.
```

---

## 使うときの注意

- **1 カットにつき 3〜4 枚出して選ぶ。** 1 枚目が当たることは少ないです
- **カット 5・6 の下地は暗めに。** 図解を乗せるので、絵が強いと数字が読めません
- **生成画像だけで組まない。** 実在の人物・記録が一枚も入らないと、
  どのチャンネルでも作れる映像になります。カタログの実写を最低 2〜3 枚は混ぜてください
- 生成画像は `assets/generated/ep02_short/` に置き、カタログに
  `種別 = 生成` で追記しておくと次回使い回せます
