# 自分の声のモデルを作る

jigoe は合成エンジンを呼ぶだけのツールなので、「自分の声」そのものは
別途モデルとして用意する必要があります。目的別に 3 つの道があります。

| 重視すること | 方法 | 費用 | 用意する音声 |
|---|---|---|---|
| とにかく無料・日本語 | **AivisSpeech ＋ 自作モデル** | 0 円 | 数分〜20 分（ITA コーパス推奨） |
| まず試す速さ | GPT-SoVITS（ゼロショット） | 0 円 | 5〜15 秒 |
| 手軽さ・品質 | ElevenLabs / Fish Audio | 約 1,650〜3,300 円/月 | 15 秒〜数分 |

---

## A. AivisSpeech で自作モデル（無料・日本語の本命）

AivisSpeech は Style-Bert-VITS2 を VOICEVOX と同じ操作感の GUI にまとめたものです。
ソフト本体は無料（LGPL-3.0）、商用利用可。**自分で作った声モデルは自分が権利者**なので、
ライセンス面で悩むところがありません。

### 1. 収録

1. ITA コーパス（標準文の文集、数百文）を用意する
2. 声質・音量・話速を一定に保って読み上げ、1 文 1 ファイルで録音する
3. マイクは可能な範囲で良いものを。ノイズと口元の距離の揺れが品質に直結します

> 収録は同じ日・同じ環境で一気に済ませたほうが、モデルの安定度が上がります。

### 2. 学習

Google Colab の無料 GPU で Style-Bert-VITS2 を学習させます（数時間規模）。
ローカルで回す場合は NVIDIA GPU（VRAM 6〜8GB 以上）があると快適です。

### 3. モデル化と読み込み

AIVM-Generator で `.aivmx` に変換し、AivisSpeech に読み込ませます。
合成そのものは CPU でも動きます。

### 4. jigoe から使う

AivisSpeech を起動した状態で:

```bash
jigoe voices -e aivisspeech        # 話者 ID を調べる
```

`jigoe.toml` に書きます。

```toml
[voice]
engine = "aivisspeech"

[engines.aivisspeech]
base_url = "http://127.0.0.1:10101"
speaker = 1234567890               # 上で調べた ID
```

```bash
jigoe doctor                       # 接続確認
jigoe say "テストです。" -o test.wav
```

---

## B. Style-Bert-VITS2 を直接使う

AivisSpeech の GUI を挟まず、学習・スタイル指定まで自分で触りたい場合。
`server_fastapi.py` を起動しておきます。

```toml
[voice]
engine = "sbv2"

[engines.sbv2]
base_url = "http://127.0.0.1:5000"
model_id = 0
style = "Neutral"
style_weight = 1.0
```

話速は `[voice] speed` や台本の `@speed` で指定します
（内部では Style-Bert-VITS2 の `length` に逆数で変換されます）。

---

## C. GPT-SoVITS でゼロショット（いちばん速い）

学習させずに、参照音声 5〜15 秒だけで声質を再現します。まず試すには最短です。
`api_v2.py` を起動しておきます。

```toml
[voice]
engine = "gptsovits"

[engines.gptsovits]
base_url = "http://127.0.0.1:9880"
ref_audio_path = "refs/my_voice_10s.wav"
prompt_text = "参照音声で実際に喋っている内容をそのまま書く"
prompt_lang = "ja"
```

> `prompt_text` は参照音声の**実際の発話内容**と一致させてください。
> ここがずれていると再現性が目に見えて落ちます。

---

## D. クラウドサービス（ElevenLabs / Fish Audio）

学習環境を用意せず、手軽さと品質を取る場合。API キーは環境変数で渡します。

```bash
export ELEVENLABS_API_KEY='...'
```

```toml
[voice]
engine = "elevenlabs"

[engines.elevenlabs]
api_key_env = "ELEVENLABS_API_KEY"
voice_id = "..."                 # jigoe voices で確認できる
model_id = "eleven_multilingual_v2"
output_format = "pcm_24000"      # mp3 は連結できないので pcm を使う
```

ElevenLabs のクローンには手軽な **Instant**（Starter〜）と高再現の
**Professional**（Creator〜）があります。ナレーション用途なら Professional、
つまり実質 Creator プランが下限です。

```bash
jigoe doctor      # 残りクレジットも表示されます
```

---

## どの道を選んでも共通の注意

- **クローンできるのは自分の声だけです。** 選手・実況者・配信者など第三者の声を
  無断でクローンすることは、主要サービスの規約で禁止されており、
  パブリシティ権・人格権の侵害にもなり得ます。
- 自分で作った声モデルは自分が権利者なので、YouTube の収益化を含む商用利用に
  権利上の問題はありません。使用する OSS 側のライセンス（多くは商用可）は
  念のため確認してください。
- モデルを作り直したら `jigoe cache clear` でキャッシュを消してください。
  同じ文が古い声のまま再利用されるのを防げます。
