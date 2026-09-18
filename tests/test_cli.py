import json

import pytest

from jigoe.cli import main


@pytest.fixture
def project(tmp_path, monkeypatch):
    """init 済みのプロジェクトディレクトリに移動した状態。"""
    monkeypatch.chdir(tmp_path)
    assert main(["init", ".", "--name", "テスト", "--engine", "mock"]) == 0
    return tmp_path


def test_init_creates_config_script_and_lexicon(project):
    assert (project / "jigoe.toml").is_file()
    assert (project / "scripts" / "sample.txt").is_file()
    assert (project / "lexicon" / "names.tsv").is_file()


def test_init_refuses_to_overwrite(project, capsys):
    assert main(["init", "."]) == 1
    assert "既に存在" in capsys.readouterr().err


def test_engines_lists_every_backend(capsys):
    assert main(["engines"]) == 0
    out = capsys.readouterr().out
    for name in ("mock", "aivisspeech", "elevenlabs", "sbv2"):
        assert name in out


def test_doctor_reports_configuration(project, capsys):
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "mock" in out
    assert "読み辞書" in out


def test_check_reports_stats_without_synthesizing(project, capsys):
    assert main(["check", "scripts/sample.txt"]) == 0
    out = capsys.readouterr().out
    assert "読み上げ文字数" in out
    assert "誤読チェック" in out
    assert not (project / "out").exists()


def test_check_strict_fails_on_unresolved_readings(project, capsys):
    (project / "risky.txt").write_text("ステフィン・カリーが118-110で勝利。", encoding="utf-8")
    assert main(["check", "risky.txt", "--strict"]) == 2


def test_check_strict_passes_once_readings_are_registered(project):
    (project / "risky.txt").write_text("ステフィン・カリーが勝利。", encoding="utf-8")
    assert main(["lexicon", "add", "--surface", "ステフィン・カリー", "--reading", "ステフカリー"]) == 0
    assert main(["check", "risky.txt", "--strict"]) == 0


def test_speak_writes_all_outputs(project, capsys):
    assert main(["speak", "scripts/sample.txt", "-q"]) == 0
    out_dir = project / "out"
    for suffix in (".wav", ".srt", ".vtt", ".chapters.txt", ".report.json"):
        assert (out_dir / f"sample{suffix}").is_file()


def test_speak_honours_basename_and_out(project):
    assert main(["speak", "scripts/sample.txt", "-q", "-o", "custom", "--basename", "ep01"]) == 0
    assert (project / "custom" / "ep01.wav").is_file()


def test_speak_strict_blocks_before_spending_credits(project):
    (project / "risky.txt").write_text("ステフィン・カリーの話。", encoding="utf-8")
    assert main(["speak", "risky.txt", "--strict", "-q"]) == 2
    assert not (project / "out" / "risky.wav").exists()


def test_speak_reuses_cache_on_the_second_run(project, capsys):
    main(["speak", "scripts/sample.txt", "-q"])
    capsys.readouterr()
    main(["speak", "scripts/sample.txt", "-q"])
    assert "合成 / 再利用: 0 /" in capsys.readouterr().out


def test_speak_no_cache_forces_resynthesis(project, capsys):
    main(["speak", "scripts/sample.txt", "-q"])
    capsys.readouterr()
    main(["speak", "scripts/sample.txt", "-q", "--no-cache"])
    assert "合成 / 再利用: 0 /" not in capsys.readouterr().out


def test_report_json_is_valid(project):
    main(["speak", "scripts/sample.txt", "-q"])
    report = json.loads((project / "out" / "sample.report.json").read_text(encoding="utf-8"))
    assert report["engine"] == "mock"
    assert report["char_count"] > 0


def test_say_writes_a_wav(project):
    assert main(["say", "短いテスト。", "-o", "one.wav"]) == 0
    assert (project / "one.wav").is_file()


def test_cost_recommends_a_plan(capsys):
    assert main(["cost", "--chars", "3300", "--videos", "12", "-e", "elevenlabs"]) == 0
    assert "Creator" in capsys.readouterr().out


def test_cost_from_a_script(project, capsys):
    assert main(["cost", "scripts/sample.txt", "-e", "fishaudio"]) == 0
    assert "fishaudio" in capsys.readouterr().out


def test_lexicon_scan_writes_a_starter_file(project, capsys):
    (project / "risky.txt").write_text("ステフィン・カリーが118-110で勝利。", encoding="utf-8")
    assert main(["lexicon", "scan", "risky.txt", "-o", "new.tsv"]) == 0
    body = (project / "new.tsv").read_text(encoding="utf-8")
    assert "ステフィン・カリー" in body


def test_lexicon_scan_requires_a_script(capsys):
    with pytest.raises(SystemExit):
        main(["lexicon", "scan"])


def test_lexicon_add_requires_both_fields():
    with pytest.raises(SystemExit):
        main(["lexicon", "add", "--surface", "のみ"])


def test_lexicon_list(project, capsys):
    assert main(["lexicon", "list"]) == 0
    assert "NBA" in capsys.readouterr().out


def test_cache_status_and_clear(project, capsys):
    main(["speak", "scripts/sample.txt", "-q"])
    capsys.readouterr()
    assert main(["cache", "status"]) == 0
    assert "件" in capsys.readouterr().out
    assert main(["cache", "clear"]) == 0


def test_consent_status_without_record(capsys):
    assert main(["consent", "--status"]) == 1
    assert "未同意" in capsys.readouterr().out


def test_consent_yes_then_status(capsys):
    assert main(["consent", "--yes"]) == 0
    assert main(["consent", "--status"]) == 0


def test_consent_revoke(capsys):
    main(["consent", "--yes"])
    assert main(["consent", "--revoke"]) == 0
    assert main(["consent", "--status"]) == 1


def test_cloning_engine_is_blocked_without_consent(project, capsys):
    assert main(["speak", "scripts/sample.txt", "-e", "elevenlabs", "-q"]) == 3
    assert "自声であることの宣言" in capsys.readouterr().err


def test_missing_script_reports_cleanly(project, capsys):
    assert main(["check", "nope.txt"]) == 1
    assert "台本が見つかりません" in capsys.readouterr().err


def test_unknown_engine_reports_cleanly(project, capsys):
    assert main(["doctor", "-e", "nope"]) == 4
    assert "未知のエンジン" in capsys.readouterr().err
