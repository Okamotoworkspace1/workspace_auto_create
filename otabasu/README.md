# オタバス NBA データ室

YouTube チャンネル「オタバス」の数字の元データを見せる、限定公開のサイトです。
Python 3.11 以上（標準ライブラリのみ）で、データとロゴを埋め込んだ HTML を 1 枚出力します。

## ページ

| URL | 内容 |
| --- | --- |
| `#` | トップ（歴代の上振れ指名 TOP5、DF TOP5 など） |
| `#draft~2016` | 年ごとのドラフト全指名と評価（SSS〜D）、期待値との差 |
| `#steals` | 上振れ・下振れ指名ランキング（期間・巡目で絞り込み） |
| `#curve` | 指名順位ごとの平均得点と近似曲線（期待値）のグラフ、順位帯ごとの評価分布 |
| `#teams` | 初年度所属チーム別の集計 |
| `#defense` | 2025-26 ディフェンス総合ランキング（重み・プリセット・ポジション補正を変えられる） |
| `#p~nikola-jokic` | 選手ページ（ドラフト評価と 2025-26 の DF 指標をまとめて表示） |

## データ（`data/`、リポジトリには含めない）

このリポジトリは public なので、`data/` と出力先の `pages/` は `.gitignore` 済みです。

| ファイル | 作り方 |
| --- | --- |
| `draft.csv` | スプレッドシート「全選手一覧」を CSV でダウンロード（列はシートのまま） |
| `defense_2025_26.json` | DF 指標。選手ごとの `{player, team, pos, g, mp, dbpm, dws, drtg, blkpct, stlpct, drbpct, dfg, diff, dfga, honors, …}` の配列 |
| `logo_mark.webp` / `logo_full.webp` / `favicon.png` | ロゴ画像（ボール部分／文字入り／タブ用） |

- 評価の換算: SSS=6, SS=5, S=4, A=3, B=2, C=1, D=0（シートの「得点」列）
- 期待値 = シートの「フィッティング」、期待値との差 = 「スコア-フィッティング」
- ドラフトと DF の選手は名前で照合します（アクセント・記号・Jr. などは無視）。同名の別人がいる場合は誤リンクを避けてつなぎません。
- `build.py` の `RECENT_FROM`（既定 2023）以降の指名は「評価途中」として注記し、ランキングでは除外を選べます。

## ビルド

```bash
cd otabasu
python build.py --pages pages              # Cloudflare Pages 用（index.html, favicon.png, robots.txt, _headers）
python build.py --single site.html         # claude.ai Artifact 用（<html> 骨組みなし）
python -m unittest discover -s tests       # テスト
```

`pages/` の中身を zip にして、Cloudflare の otabasu プロジェクトの「Create deployment」からアップロードすると、
`https://otabasu.pages.dev` が同じ URL のまま更新されます。
