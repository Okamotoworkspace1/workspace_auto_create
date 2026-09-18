import pytest

from jigoe import consent as consent_mod
from jigoe.config import Config, load_config, write_template
from jigoe.errors import ConfigError, ConsentError


def write(tmp_path, body):
    path = tmp_path / "jigoe.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_defaults_when_no_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    assert cfg.voice.engine == "mock"
    assert cfg.source is None


def test_loads_sections(tmp_path):
    path = write(
        tmp_path,
        '[project]\nname = "テスト"\nout_dir = "音声"\n'
        '[voice]\nengine = "aivisspeech"\nspeed = 1.1\n'
        "[audio]\nsample_rate = 48000\n"
        '[lexicon]\npaths = ["dict.tsv"]\n'
        "[engines.aivisspeech]\nspeaker = 42\n",
    )
    cfg = load_config(path)
    assert cfg.project_name == "テスト"
    assert cfg.out_dir == tmp_path / "音声"
    assert cfg.voice.engine == "aivisspeech"
    assert cfg.voice.speed == 1.1
    assert cfg.audio.sample_rate == 48000
    assert cfg.lexicon_paths == [tmp_path / "dict.tsv"]
    assert cfg.engine_options() == {"speaker": 42}


def test_missing_file_raises():
    with pytest.raises(ConfigError, match="見つかりません"):
        load_config("/nonexistent/jigoe.toml")


def test_unknown_key_is_reported(tmp_path):
    path = write(tmp_path, "[voice]\nengin = 1\n")
    with pytest.raises(ConfigError, match="未知のキー"):
        load_config(path)


def test_invalid_toml_is_reported(tmp_path):
    path = write(tmp_path, "[voice\n")
    with pytest.raises(ConfigError, match="TOML"):
        load_config(path)


def test_negative_pause_rejected(tmp_path):
    path = write(tmp_path, "[audio]\nsentence_pause = -1\n")
    with pytest.raises(ConfigError, match="負の値"):
        load_config(path)


def test_overrides_only_replace_given_values():
    cfg = Config().with_overrides(engine="elevenlabs", speed=None)
    assert cfg.voice.engine == "elevenlabs"
    assert cfg.voice.speed == 1.0


def test_template_is_loadable(tmp_path):
    path = tmp_path / "jigoe.toml"
    write_template(path, name="てすと", engine="mock")
    cfg = load_config(path)
    assert cfg.project_name == "てすと"
    assert "elevenlabs" in cfg.engines


def test_template_refuses_to_overwrite(tmp_path):
    path = tmp_path / "jigoe.toml"
    write_template(path, name="a", engine="mock")
    with pytest.raises(ConfigError, match="既に存在"):
        write_template(path, name="b", engine="mock")


def test_api_keys_are_not_stored_in_the_template(tmp_path):
    path = tmp_path / "jigoe.toml"
    write_template(path, name="a", engine="mock")
    body = path.read_text(encoding="utf-8")
    assert "api_key_env" in body
    assert "api_key =" not in body


# --- 同意ゲート ---------------------------------------------------------


def test_cloning_engines_need_consent():
    with pytest.raises(ConsentError, match="自声であることの宣言"):
        consent_mod.ensure_consent("elevenlabs")


def test_non_cloning_engines_do_not():
    consent_mod.ensure_consent("voicevox")
    consent_mod.ensure_consent("mock")


def test_recorded_consent_unlocks_cloning():
    consent_mod.record_consent(note="テスト")
    consent_mod.ensure_consent("elevenlabs")


def test_assume_yes_records_consent():
    consent_mod.ensure_consent("fishaudio", assume_yes=True)
    assert consent_mod.load_consent() is not None


def test_env_override(monkeypatch):
    monkeypatch.setenv(consent_mod.ENV_OVERRIDE, "1")
    consent_mod.ensure_consent("elevenlabs")
    assert consent_mod.load_consent() is None  # 記録は残さない


def test_revoke():
    consent_mod.record_consent()
    assert consent_mod.revoke_consent() is True
    assert consent_mod.revoke_consent() is False
    with pytest.raises(ConsentError):
        consent_mod.ensure_consent("sbv2")


def test_declaration_names_the_prohibited_use():
    assert "第三者の声" in consent_mod.DECLARATION


def test_corrupt_consent_file_is_treated_as_absent():
    path = consent_mod.consent_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ broken", encoding="utf-8")
    assert consent_mod.load_consent() is None
