"""python -m unittest discover -s tests  （otabasu/ で実行）"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build  # noqa: E402

HEADER = ",".join(build.DRAFT_HEADER)
# 1x1 の透明 PNG（ロゴの代わり）
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d6a4f40000000049454e44ae426082"
)


def make_data(tmp: Path) -> Path:
    d = tmp / "data"
    d.mkdir()
    (d / "draft.csv").write_text("\n".join([
        HEADER,
        '2014,2,41,Nikola Jokic,SSS,DEN,8,0,2,6,0,0,0,3,1,"25,914",32.0,6,0.762,0.731,5.238,5.269',
        "2006,1,1,Marcus Williams,C,NJN,0,0,0,0,0,0,0,0,0,1000,10.0,1,3.714,3.263,-2.714,-2.263",
        "2007,1,2,Marcus Williams,D,-,0,0,0,0,0,0,0,0,0,-,-,0,3.048,3.145,-3.048,-3.145",
    ]) + "\n", encoding="utf-8")
    (d / "defense_2025_26.json").write_text(json.dumps([
        {"player": "Nikola Jokić", "team": "DEN", "pos": "C", "g": 65, "mp": 2265, "dbpm": 4.1, "honors": ""},
        {"player": "Marcus Williams", "team": "SAS", "pos": "PG", "g": 1, "mp": 5, "dbpm": 0.0, "honors": ""},
        {"player": "Alex Caruso", "team": "OKC", "pos": "SG", "g": 56, "mp": 1020, "dbpm": 3.3, "honors": "</script>"},
    ]), encoding="utf-8")
    for name in ("logo_mark.webp", "logo_full.webp"):
        (d / name).write_bytes(PNG)
    (d / "favicon.png").write_bytes(PNG)
    return d


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = make_data(self.tmp)

    def test_parse_and_link(self):
        out = build.build_data(self.data)
        jokic = out["draft"][0]
        self.assertEqual(jokic[15], 25914)          # "25,914" → 25914
        self.assertEqual(jokic[17], 6)              # SSS = 6 点
        self.assertEqual(jokic[21], "nikola-jokic")
        self.assertEqual(jokic[22], 0)              # アクセント違いでも DF とつながる
        self.assertEqual(out["defense"][0]["di"], 0)
        no_play = out["draft"][2]
        self.assertIsNone(no_play[15])               # "-" → None
        self.assertIsNone(no_play[16])

    def test_same_name_is_not_linked(self):
        out = build.build_data(self.data)
        ids = [r[21] for r in out["draft"]]
        self.assertIn("marcus-williams-2006", ids)
        self.assertIn("marcus-williams-2007", ids)
        mw = out["defense"][1]
        self.assertIsNone(mw["di"])                  # 同名が2人いるので推測でつながない
        self.assertNotIn(mw["id"], ids)

    def test_bad_grade_is_rejected(self):
        p = self.data / "draft.csv"
        p.write_text(p.read_text(encoding="utf-8").replace(",SSS,", ",X,"), encoding="utf-8")
        with self.assertRaises(SystemExit):
            build.build_data(self.data)

    def test_pages_output(self):
        out = build.build_pages(self.data, self.tmp / "pages")
        html = (out / "index.html").read_text(encoding="utf-8")
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertEqual(html.count("<body>"), 1)
        self.assertIn('name="robots" content="noindex', html)
        self.assertNotIn("{{", html)                  # 置き換え漏れがない
        self.assertNotIn("</script>\"", html)         # データ内の </script> はエスケープ済み
        self.assertIn("X-Robots-Tag: noindex", (out / "_headers").read_text(encoding="utf-8"))
        self.assertTrue((out / "favicon.png").exists())
        build.build_pages(self.data, out)            # 同じ出力先に再ビルドできる

    def test_refuses_foreign_dir(self):
        foreign = self.tmp / "keep"
        foreign.mkdir()
        (foreign / "important.txt").write_text("x")
        with self.assertRaises(SystemExit):
            build.build_pages(self.data, foreign)
        self.assertTrue((foreign / "important.txt").exists())

    def test_single_output_has_no_document_shell(self):
        html = build.render(self.data, full_document=False)
        self.assertTrue(html.startswith("<title>"))
        self.assertNotIn("<html", html)


if __name__ == "__main__":
    unittest.main()
