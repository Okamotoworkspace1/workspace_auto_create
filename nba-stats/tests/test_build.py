"""python -m unittest discover -s tests  （nba-stats/ で実行）"""

import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build  # noqa: E402

CONFIG = ROOT / "config.toml"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


class FmtTest(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(build.fmt("0.4567", "pct"), ".457")
        self.assertEqual(build.fmt("1", "pct"), "1.000")
        self.assertEqual(build.fmt("27.25", "f1"), "27.2")  # 偶数丸め（Python 標準）
        self.assertEqual(build.fmt("71.6", "int"), "72")
        self.assertEqual(build.fmt("", "f1"), "")
        self.assertEqual(build.fmt("N/A", "f1"), "N/A")
        self.assertEqual(build.fmt(None, "f1"), "")


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = self.tmp / "data"
        write(self.data / "players.csv", """
player_id,name,pos
aaa01,Alpha Able,PG
bbb01,Bravo Baker Jr.,C
""")
        write(self.data / "teams.csv", """
team,name,conference
AAA,Alpha Team,Eastern
BBB,Bravo Team,Western
""")
        # bbb01 は 2024-25 に移籍（2TM 行あり）
        write(self.data / "totals.csv", """
player_id,season,team,g,mp,fg,fga,pts
aaa01,2023-24,AAA,50,1500,300,600,800
aaa01,2024-25,AAA,30,900,200,400,500
bbb01,2024-25,2TM,60,1200,240,480,600
bbb01,2024-25,AAA,20,400,80,160,200
bbb01,2024-25,BBB,40,800,160,320,400
""")
        write(self.data / "per_game.csv", """
player_id,season,team,g,mp,fg,fga,fg_pct,pts
aaa01,2023-24,AAA,50,30.0,6.0,12.0,.500,16.0
aaa01,2024-25,AAA,30,30.0,6.667,13.333,.500,16.667
aaa01,Career,,,,,,,99.9
bbb01,2024-25,2TM,60,20.0,4.0,8.0,.500,10.0
bbb01,2024-25,AAA,20,20.0,4.0,8.0,.500,10.0
bbb01,2024-25,BBB,40,20.0,4.0,8.0,.500,10.0
""")
        self.out = self.tmp / "dist"
        build.build(self.data, self.out, CONFIG)

    def read(self, rel: str) -> str:
        return (self.out / rel).read_text(encoding="utf-8")

    def test_pages_exist(self):
        for rel in (
            "index.html", "robots.txt", "assets/style.css", "assets/app.js", "assets/search-index.js",
            "players/index.html", "players/aaa01.html", "players/bbb01.html",
            "seasons/index.html", "seasons/2024-25.html",
            "teams/index.html", "teams/AAA.html", "teams/AAA/2024-25.html", "teams/BBB/2024-25.html",
        ):
            self.assertTrue((self.out / rel).exists(), rel)
        # 2TM はチームページを作らない
        self.assertFalse((self.out / "teams/2TM.html").exists())

    def test_noindex(self):
        self.assertIn('name="robots" content="noindex', self.read("index.html"))
        self.assertIn("Disallow: /", self.read("robots.txt"))

    def footer(self, rel: str, table_id: str) -> list[str]:
        page = self.read(rel)
        table = page[page.index(f'id="t-{table_id}"'):]
        foot = table[table.index("<tfoot>"):table.index("</tfoot>")]
        return re.findall(r"<td[^>]*>([^<]*)</td>", foot)

    def test_career_totals_skip_team_rows_of_traded_season(self):
        # 2TM 行だけを数える: G=60（AAA 20 + BBB 40 を二重に足さない）
        cells = self.footer("players/bbb01.html", "totals")
        self.assertEqual(cells[0], "60")

    def test_career_ratio_and_wavg(self):
        cells = self.footer("players/aaa01.html", "totals")
        # g, mp, fg, fga, fg_pct, pts
        self.assertEqual(cells, ["80", "2400", "500", "1000", ".500", "1300"])

    def test_career_row_from_csv_overrides(self):
        cells = self.footer("players/aaa01.html", "per_game")
        self.assertEqual(cells[-1], "99.9")

    def test_partial_rows_marked(self):
        page = self.read("seasons/2024-25.html")
        self.assertEqual(page.count('class="partial"'), 4)  # 2 行 × per_game/totals

    def test_leaders_use_total_row(self):
        page = self.read("index.html")
        self.assertIn("2TM", page)

    def test_last_name_suffix(self):
        self.assertIn('id="letter-B"', self.read("players/index.html"))
        self.assertIn("Bravo Baker Jr.", self.read("assets/search-index.js"))

    def test_refuses_foreign_output_dir(self):
        foreign = self.tmp / "important"
        write(foreign / "keep.txt", "do not delete")
        with self.assertRaises(SystemExit):
            build.build(self.data, foreign, CONFIG)
        self.assertTrue((foreign / "keep.txt").exists())
        # 自分の出力先は再ビルドできる
        build.build(self.data, self.out, CONFIG)


class SingleFileTest(unittest.TestCase):
    setUp = BuildTest.setUp

    def test_single_file(self):
        import json
        out = build.build_single(self.data, self.tmp / "one.html", CONFIG)
        text = out.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("<title>"))
        self.assertNotIn("<html", text)  # Artifact 側が骨組みを付ける
        self.assertIn('name="robots" content="noindex', text)
        payload = text[text.index("window.NBA_DATA = ") + 18:text.index(";</script>")]
        data = json.loads(payload)
        totals = next(t for t in data["tables"] if t["id"] == "totals")
        g = [c[0] for c in totals["cols"]].index("g")
        self.assertEqual(totals["career"]["bbb01"][g], 60)  # 2TM 行だけを数える
        per_game = next(t for t in data["tables"] if t["id"] == "per_game")
        self.assertEqual(per_game["career"]["aaa01"][-1], "99.9")  # CSV の Career 行
        self.assertEqual(data["leaders"]["season"], "2024-25")


class PagesTest(unittest.TestCase):
    setUp = BuildTest.setUp

    def test_pages_folder(self):
        out = build.build_pages(self.data, self.tmp / "pages", CONFIG)
        html = (out / "index.html").read_text(encoding="utf-8")
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertIn('<meta name="robots" content="noindex', html)
        self.assertNotIn("claude:viewport-fit-sides", html)
        self.assertEqual(html.count("<body>"), 1)
        self.assertIn('<div id="app"></div>', html)
        self.assertIn("X-Robots-Tag: noindex", (out / "_headers").read_text(encoding="utf-8"))
        self.assertTrue((out / "robots.txt").exists())
        build.build_pages(self.data, out, CONFIG)  # 再出力できる


class SampleDataTest(unittest.TestCase):
    def test_sample_builds_and_career_per_game_matches_totals(self):
        sample = ROOT / "sample_data"
        if not sample.exists():
            self.skipTest("sample_data がありません（python tools/make_sample.py で生成）")
        out = Path(tempfile.mkdtemp()) / "dist"
        build.build(sample, out, CONFIG)
        site = build.load_site(sample, CONFIG)
        tables = {t.id: t for t in site.tables}
        for pid in list(site.players)[:20]:
            pg = [r for r in tables["per_game"].rows if r["player_id"] == pid]
            tot = [r for r in tables["totals"].rows if r["player_id"] == pid]
            c_pg = build.career_row(site, tables["per_game"], pid, pg)
            c_tot = build.career_row(site, tables["totals"], pid, tot)
            self.assertAlmostEqual(c_pg["pts"], c_tot["pts"] / c_tot["g"], delta=0.06, msg=pid)
            self.assertAlmostEqual(c_pg["fg_pct"], c_tot["fg_pct"], delta=0.005, msg=pid)


if __name__ == "__main__":
    unittest.main()
