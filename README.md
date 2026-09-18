# jigoe（自声）

**自分の声のクローンで台本を読み上げる、動画ナレーション向けのツールです。**

台本のテキストを渡すと、ナレーション音声（WAV）・字幕（SRT / VTT）・
YouTube のチャプター一覧をまとめて書き出します。無料のローカルモデルから
ElevenLabs のようなクラウドサービスまで、同じ台本のままエンジンを差し替えられます。

```
台本.txt ──▶ 読み辞書で読みを固定 ──▶ 音声合成エンジン ──▶ narration.wav
                                                        narration.srt / .vtt
                                                        narration.chapters.txt
                                                        narration.report.json
```

---

## はじめに：このツールで「できないこと」

ひろゆきさんやヒカキンさんの声で喋らせる類のツールを見かけますが、**本ツールは
それをしません。** 他人の声を無断でクローンする行為は、

- ElevenLabs をはじめ主要サービスの規約で**全プラン禁止**
- 日本ではパブリシティ権・人格権の侵害になり得る
- YouTube のなりすましポリシー違反として削除・収益化剥奪の対象になり得る

ためです。そこで jigoe は、クローン系エンジンを初めて使う前に一度だけ
「合成に使うのは自分の声である」という宣言を求めます（`jigoe consent`）。

自分の声であれば、この制約はまったく邪魔になりません。むしろ**自声クローンは
独自性・視聴維持率・収益化ポリシーのすべてで有利**です。合成音声の既製キャラクター
（VOICEVOX 等）は他チャンネルと被りますが、自分の声は被りません。

---

## クイックスタート

**Python 3.11 以上が必要です**（`tomllib` を使うため）。まず確認してください。

```bash
python3 --version
```

3.11 未満、または `command not found` なら先に Python を入れます。
macOS に最初から入っている Python は 3.9 系のことが多く、そのままでは動きません。

```bash
brew install python@3.12          # Homebrew の場合
# または https://www.python.org/downloads/ の公式インストーラ
```

インストール:

```bash
git clone <このリポジトリ> && cd workspace_auto_create

python3 -m venv .venv             # 仮想環境を作る（システムの Python を汚さない）
source .venv/bin/activate         # Windows は .venv\Scripts\activate
python3 -m pip install -e .
```

> `pip: command not found` と出る場合は `python3 -m pip` を使ってください。
> `externally-managed-environment` というエラーが出る場合は、上の仮想環境を作る手順を飛ばしています。

仮想環境を有効にしなくても `jigoe` を使えるようにするには、エイリアスを登録します。

```bash
echo "alias jigoe='$PWD/.venv/bin/jigoe'" >> ~/.zshrc && source ~/.zshrc
```

動作確認:

```bash
mkdir ~/my-channel && cd ~/my-channel
jigoe init --name "バスケ雑学ch"     # jigoe.toml / 台本 / 読み辞書の雛形を作る

jigoe check scripts/sample.txt       # 合成せずに誤読と尺だけ確認
jigoe speak scripts/sample.txt       # 音声・字幕・チャプターを生成
```

初期エンジンは `mock`（API もサーバーも要らないダミー音声）なので、
**何も用意しなくてもパイプライン全体がその場で動きます。**
動きを確認したら、`jigoe.toml` の `[voice] engine` を実際のエンジンに切り替えてください。

ブラウザから使いたい場合:

```bash
jigoe serve      # http://127.0.0.1:8765 が開く
```

---

## エンジンを選ぶ

| エンジン | 費用 | 自声 | 特徴 |
|---|---|---|---|
| `aivisspeech` | **0 円** | ○ | 日本語 × 無料 × 自分の声なら本命。VOICEVOX と同じ操作感の GUI で、自作の `.aivmx` モデルを読み込める |
| `sbv2` | 0 円 | ○ | Style-Bert-VITS2。AivisSpeech の中身。学習やスタイル指定まで自分で触りたい場合 |
| `gptsovits` | 0 円 | ○ | 参照音声 5〜15 秒のゼロショット。まず試すのが速い |
| `fishaudio` | 約 1,650 円/月 | ○ | クラウドで最安クラス。15 秒でクローン、Plus 以上で商用可 |
| `elevenlabs` | 約 3,300 円/月 | ○ | 品質最優先。高再現の Professional クローンは Creator 以上 |
| `voicevox` | 0 円 | × | 配布キャラクター音声のみ。自声クローンは不可 |
| `mock` | 0 円 | – | オフライン確認用のダミー音声 |

迷ったら **`aivisspeech`（無料で始める）か `elevenlabs`（品質で選ぶ）** の二択です。

月額の試算はツールに入っています:

```bash
$ jigoe cost --chars 3300 --videos 12 -e elevenlabs
1 本の文字数   : 3,300 字（約 10.0 分相当）
月のクレジット  : 39,600
推奨プラン      : Creator — 月 $22（約 3,300 円） / 自声ナレーションの本命
```

10 分のナレーションは日本語でおよそ 3,000〜3,600 字です。
為替は `--usd-jpy` で変更できます（既定 150 円）。
**料金は改定が多い領域なので、契約前に必ず公式サイトで確認してください。**

自分の声のモデルを作る手順は [docs/voice-model.md](docs/voice-model.md) にまとめています。

---

## 台本の書き方

プレーンテキスト（`.txt` / `.md`）です。覚える記法は 4 つだけです。

```
# オープニング                    ← 見出し。読み上げずチャプターになる
// これはコメント。無視される

@speed 1.05                      ← 以降の行に効く（speed / pitch / volume / style / pause）

NBAの歴史には、記録よりも語り継がれた選手がいます。[[0.8]]その名はピストル・ピート。
                                                 ↑ 行内の無音（秒）
@pause 1.2                       ← 明示的な無音
```

- 空行は段落の区切りになり、少し長めの無音が入ります。
- 文は `。！？` で自動的に区切られ、そのあいだにも無音が入ります（既定 0.35 秒）。
- **`[[0.8]]` や `@pause` で明示した「間」は、既定値より短くてもそのまま採用されます。**
  重要な一言の前で 0.3〜0.8 秒空ける、という調整は台本側に残せます。
- 無音の既定値は `jigoe.toml` の `[audio]` で変更できます。

---

## 誤読チェックと読み辞書

固有名詞とスコアの読みは、合成音声で最も事故が起きる箇所です。
`jigoe check` は、読み辞書に未登録の**カタカナの固有名詞・英字・スコア表記・小数**を
「人が確認すべき箇所」として並べます。

```
$ jigoe check scripts/ep01.txt
誤読チェック : 要確認 3 件
  ! ステフィン・カリー        ×4   katakana  固有名詞なら読み辞書に登録して読みを固定する
  ! 118-110              ×1   score     「118-110」は「118対110」など読み方を明示する
  ! 27.4                 ×2   decimal   小数は「27.4」→「27てん4」など読みを確認する
```

読み辞書の雛形はコマンドで作れます。

```bash
jigoe lexicon scan scripts/ep01.txt -o lexicon/ep01.tsv   # 表記だけ書き出す → 読みを埋める
jigoe lexicon add --surface "ステフィン・カリー" --reading "ステフィンカリー"
```

辞書は `表記<TAB>読み<TAB>メモ` の TSV（または JSON）で、`jigoe.toml` の
`[lexicon] paths` に並べます。**辞書は合成の直前にだけ適用され、字幕には元の表記が残ります。**
「読みはカタカナ、字幕は漢字」が両立します。

クラウド API のクレジットを使う前に止めたい場合は `--strict` を付けます。
未確認の項目が残っていれば合成せず終了コード 2 で終わります。

```bash
jigoe check scripts/ep01.txt --strict && jigoe speak scripts/ep01.txt
```

---

## 出力されるもの

`jigoe speak scripts/ep01.txt` で `out/` 以下に生成されます。

| ファイル | 用途 |
|---|---|
| `ep01.wav` | ナレーション本体（16bit PCM・ピークを揃えて出力） |
| `ep01.srt` / `ep01.vtt` | 字幕。実測の尺から作るので台本と必ず一致する |
| `ep01.chapters.txt` | YouTube の概要欄にそのまま貼れるチャプター一覧 |
| `ep01.report.json` | 全セグメントのタイムライン、適用した辞書、誤読候補 |
| `ep01_lines/` | `--segments` を付けたとき、1 文ずつの WAV |

字幕を編集ソフトの自動字幕に頼らず台本から作るので、固有名詞が誤変換されません。

### 合成キャッシュ

同じ文・同じ設定なら再合成しません。台本の一部を直して作り直すとき、
**変えた文だけが課金対象**になります。

```
合成 / 再利用: 3 / 52 セグメント
```

設定の話速などを変えた場合はキャッシュも作り直されます。
`jigoe cache clear` で消せます。

---

## 動画制作フローの中での位置づけ

このツールが担うのは、ナレーション音声の工程だけです。

```
企画 → リサーチ → 台本 → [ 音声 ] → 画像/素材 → 編集 → サムネ → メタデータ → 投稿
                            ↑ jigoe
```

音声工程は AI でほぼ自動化できますが、**固有名詞の誤読チェック**と
**重要箇所の「間」の調整**だけは人の担当として残ります。
jigoe がこの 2 つを機能として持っているのはそのためです
（読み辞書＋誤読チェック、`[[0.8]]` 記法）。

台本の事実確認、画像の著作権処理、独自性の注入は、このツールの範囲外です。
詳しくは [docs/workflow.md](docs/workflow.md) を参照してください。

---

## コマンド一覧

| コマンド | 説明 |
|---|---|
| `jigoe init [DIR]` | 設定・台本・読み辞書の雛形を作る |
| `jigoe doctor` | 設定とエンジン接続の確認 |
| `jigoe engines` | 使えるエンジンの一覧 |
| `jigoe voices` | エンジンが持つ話者の一覧 |
| `jigoe consent` | 自声であることの宣言を記録する |
| `jigoe check SCRIPT` | 合成せずに誤読・尺・コストを確認 |
| `jigoe speak SCRIPT` | 音声・字幕・チャプターを生成 |
| `jigoe say "テキスト"` | 短い文をその場で WAV にする |
| `jigoe cost [SCRIPT]` | クラウド TTS の月額を試算 |
| `jigoe lexicon list\|scan\|add` | 読み辞書の操作 |
| `jigoe cache status\|clear` | 合成キャッシュの確認と削除 |
| `jigoe serve` | ブラウザ UI を起動 |

`jigoe <コマンド> --help` で各オプションが見られます。

---

## 設定ファイル

`jigoe.toml`（カレント）または `~/.config/jigoe/config.toml` を読みます。
**API キーは設定ファイルに書きません。** 環境変数名だけを指定します。

```toml
[voice]
engine = "elevenlabs"
speed = 1.0

[audio]
sentence_pause = 0.35    # 文と文のあいだ
paragraph_pause = 0.7    # 段落のあいだ
peak_dbfs = -1.5         # ピークノーマライズの目標

[lexicon]
paths = ["lexicon/names.tsv"]

[engines.elevenlabs]
api_key_env = "ELEVENLABS_API_KEY"   # 値ではなく変数名
voice_id = "..."
output_format = "pcm_24000"          # 連結のため mp3 ではなく pcm を使う
```

---

## 開発

Python 3.11 以上。必須依存はありません。標準ライブラリだけで動きます
（`requests` があれば HTTP に使いますが、無ければ `urllib` にフォールバックします）。

```bash
pip install -e ".[dev]"
pytest
```

エンジンを追加するには、`Engine` を継承して `@register` を付けるだけです。

```python
@register
class MyEngine(Engine):
    name = "myengine"
    clones_voice = True

    def synthesize(self, text, *, speed=None, pitch=None, volume=None, style=None) -> Pcm:
        ...
```

台本の解析・ポーズ・音量・連結・字幕はすべてパイプライン側が持っているので、
エンジンが担うのは「テキスト 1 片 → PCM」だけです。

---

## 数値の出典について

エンジンの比較表と料金の試算は、同梱のリサーチ文書
（バスケ系 AI 動画チャンネル 立ち上げ 総合リサーチ・2026 年時点）に基づいています。
**サービスの料金・プラン内容は改定が頻繁なので、契約前に必ず公式サイトで最新をご確認ください。**
本ツールの試算は目安であり、正確性を保証するものではありません。

## ライセンス

MIT
