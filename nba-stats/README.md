# nba-stats — 限定公開の NBA 選手スタッツサイト

basketball-reference 風の選手スタッツサイトを、手元の CSV から生成する静的サイトジェネレーターです。

- **Python 3.11 以上・標準ライブラリのみ**（pip install 不要）
- 出力は素の HTML/CSS/JS。サーバー不要で、どの静的ホスティングにも置ける
- 検索エンジン除外（`noindex` メタタグ ＋ `robots.txt`）を標準で出力

## 生成されるページ

| ページ | 内容 |
| --- | --- |
| トップ `index.html` | 最新シーズンのリーダーボード（PTS/TRB/AST…）、シーズン一覧 |
| 選手 `players/<id>.html` | プロフィール、Per Game / Totals / Advanced のシーズン別表、通算（Career）行 |
| 選手一覧 `players/index.html` | 姓の頭文字ごとの一覧 |
| シーズン `seasons/<season>.html` | 全選手の表。列クリックでソート、最低試合数フィルタ、移籍選手のチーム別行の表示切替 |
| チーム `teams/<TEAM>.html`, `teams/<TEAM>/<season>.html` | チームのシーズン一覧、シーズンごとのロスタースタッツ |

全ページのヘッダーに選手名検索があります（アクセント無視：`doncic` で `Dončić` がヒット。`/` キーで検索欄へ移動）。

## 使い方

```bash
cd nba-stats

# 1. まずサンプル（架空の選手）で見た目を確認
python build.py                      # data/ が無ければ sample_data/ を使う
python -m http.server -d dist 8000   # → http://localhost:8000
#   （dist/index.html をブラウザで直接開いても動きます）

# 2. 本番データを置いてビルド
mkdir data            # ここに CSV を置く（下記フォーマット）
python build.py       # → dist/ に出力
```

オプション: `python build.py --data 別のフォルダ --out 出力先 --config 設定ファイル`

## 1 ファイル版（URL だけで開ける形）

```bash
python build.py --single site.html
```

データ・CSS・JS をすべて埋め込んだ **HTML 1 枚**を出力します。ページ切り替えは `#` 付き URL で行うので、
選手ページなどにも直接リンクできます（例: `…#p~smithjo01`、`…#s~2024-25`、`…#t~LAL~2024-25`）。
claude.ai の Artifact として公開しているのはこの形式です。データを更新したら、これを作り直して同じ Artifact に再公開します。

## Cloudflare Pages に置く（`名前.pages.dev` で公開）

```bash
python build.py --pages pages
```

`pages/` に `index.html`・`robots.txt`・`_headers`（検索除外の HTTP ヘッダー）ができます。

1. Cloudflare ダッシュボード →「Workers & Pages」→「Create application」→ Pages の「Get started」→「Drag and drop your files」
2. プロジェクト名を入力（これが URL になる: `https://プロジェクト名.pages.dev`）
3. `pages/` フォルダ（またはその中身を zip にしたもの）をドラッグ＆ドロップ →「Deploy site」

データを更新したら、`python build.py --pages pages` で作り直し、同じプロジェクトの「Create deployment」から再アップロードします（URL は変わりません）。

## データ形式（CSV）

`data/` に以下を置きます。UTF-8（Excel の BOM 付きも可）、1 行目がヘッダー。
列名・形式の見本は `sample_data/` を参照してください（`python tools/make_sample.py` で再生成できます）。

### スタッツ表（`per_game.csv` / `totals.csv` / `advanced.csv`）

1 行 = 1 選手 × 1 シーズン × 1 チーム。**必須列は `player_id`, `season`, `team` の 3 つ**で、あとは `config.toml` に定義した列が表示されます。

```csv
player_id,season,team,age,pos,g,gs,mp,fg,fga,fg_pct,...,pts
smithjo01,2024-25,LAL,25,SG,72,70,34.1,8.9,18.2,.489,...,25.3
```

- **シーズン途中の移籍**: basketball-reference と同様に、合計行（`team` が `TOT`・`2TM`・`3TM` など）とチーム別行の両方を入れてください。通算やリーダーボードは合計行だけを数え、二重計上しません。
- **通算（Career）行**: 自動計算されます（Totals は合計、Per Game は試合数で加重平均、% は成功数÷試数で再計算）。正確な公式値がある場合は `season` を `Career` にした行を入れると、計算せずその値を表示します。
- 空欄はそのまま空欄表示。ファイルが無い表（例: `advanced.csv` 未作成）はタブごと省略されます。
- 表は何個でも追加できます（例: `per_36.csv`, `playoffs_per_game.csv`）。`config.toml` に `[[tables]]` を 1 ブロック足すだけです。

### `players.csv`（任意だが推奨）

```csv
player_id,name,pos,shoots,height,weight,birth_date,birth_place,college,draft
smithjo01,John Smith,SG,Right,6-5,210lb,1999-03-01,USA,Example Univ.,2019 1st round
```

`player_id` 以外は任意。選手一覧の並び順は姓（最後の単語、`Jr.` などは除外）ですが、`last_name` 列があればそれを使います。

### `teams.csv`（任意）

```csv
team,name,conference,division
LAL,Los Angeles Lakers,Western,Pacific
```

`sample_data/teams.csv` に現 30 チーム分（basketball-reference の略号）が入っているので、そのまま `data/` にコピーして使えます。

## 表示のカスタマイズ（`config.toml`）

- サイト名、リーダーボードの項目・人数・最低試合数
- 各表の列（順番・見出し・書式 `int` / `f1` / `f3` / `pct` / `text`・通算の集計方法）
- 選手プロフィール欄の項目

コードを触らずに変更できます。詳細はファイル内のコメントを参照。

## 「URL を知っている人だけ」に公開するには

`noindex` と `robots.txt` で**検索エンジンには載らなくなります**が、URL が漏れれば誰でも見られる状態です。用途に応じて選んでください。

| 方法 | 手軽さ | 守られ方 |
| --- | --- | --- |
| **Cloudflare Pages ＋ Cloudflare Access**（おすすめ） | ◯ | 許可したメールアドレスの人だけがワンタイムコードでログインして閲覧。無料枠（50 ユーザー）で足ります |
| Netlify / Cloudflare Pages に置くだけ | ◎ | 推測されにくい URL ＋ noindex。URL を知っている人は誰でも見られる |
| Netlify のパスワード保護 / Basic 認証 | ◯ | 共有パスワードを知っている人だけ（Netlify は有料プラン） |

いずれも `dist/` フォルダをアップロード（または `python build.py` をビルドコマンド、`nba-stats/dist` を公開ディレクトリに設定）するだけです。

> **注意**: `data/` は `.gitignore` 済みで、うっかりコミットされないようにしてあります（このリポジトリは public のため）。
>
> GitHub Pages は無料プランだとリポジトリ自体を公開する必要があり、`data/` の CSV も丸見えになります。また、このリポジトリが public の場合、`data/` をコミットするとその時点で誰でも見られます。データを非公開にしたい場合は、`data/` を private リポジトリで管理するか、コミットせずに手元でビルドして `dist/` だけをアップロードしてください。

## テスト

```bash
python -m unittest discover -s tests
```
