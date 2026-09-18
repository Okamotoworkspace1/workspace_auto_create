"""Web UI の HTTP エンドポイント。実際にサーバーを立てて叩く。"""

import json
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

from jigoe.audio import Pcm
from jigoe.config import AudioConfig, Config, VoiceConfig
from jigoe.web import make_server


@pytest.fixture
def server(tmp_path):
    config = Config(
        project_name="テスト",
        out_dir=tmp_path / "out",
        voice=VoiceConfig(engine="mock"),
        audio=AudioConfig(sample_rate=24000),
    )
    server = make_server(config, port=0)  # 空きポートを自動で取る
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        yield base, opener
    finally:
        server.shutdown()
        server.server_close()


def post(server, path, payload):
    base, opener = server
    request = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    return opener.open(request, timeout=30)


def test_index_serves_the_page(server):
    base, opener = server
    body = opener.open(base + "/", timeout=5).read().decode("utf-8")
    assert "<title>jigoe" in body
    assert "テスト" in body  # プロジェクト名が出る


def test_index_page_declares_a_dark_theme(server):
    base, opener = server
    body = opener.open(base + "/", timeout=5).read().decode("utf-8")
    assert "prefers-color-scheme: dark" in body


def test_engines_endpoint(server):
    base, opener = server
    data = json.loads(opener.open(base + "/api/engines", timeout=5).read())
    names = {e["name"] for e in data["engines"]}
    assert {"mock", "elevenlabs"} <= names


def test_check_endpoint_returns_stats_and_risks(server):
    response = post(server, "/api/check", {"script": "ステフィン・カリーが決めた。", "engine": "mock"})
    data = json.loads(response.read())
    assert data["chars"] > 0
    assert [r["term"] for r in data["risks"]] == ["ステフィン・カリー"]


def test_check_counts_chapters(server):
    data = json.loads(post(server, "/api/check", {"script": "# 章1\n\n本文。\n\n# 章2\n\n本文。"}).read())
    assert data["chapters"] == 2


def test_speak_endpoint_returns_wav_and_summary(server):
    response = post(server, "/api/speak", {"script": "こんにちは。", "engine": "mock"})
    body = response.read()
    assert response.headers["Content-Type"] == "audio/wav"
    assert Pcm.from_wav_bytes(body).duration > 0
    summary = json.loads(urllib.parse.unquote(response.headers["X-Jigoe-Summary"]))
    assert summary["engine"] == "mock"
    assert summary["char_count"] == 6


def test_speak_applies_the_requested_speed(server):
    slow = post(server, "/api/speak", {"script": "同じ文です。", "speed": 0.8})
    fast = post(server, "/api/speak", {"script": "同じ文です。", "speed": 1.6})
    slow_len = json.loads(urllib.parse.unquote(slow.headers["X-Jigoe-Summary"]))["duration_seconds"]
    fast_len = json.loads(urllib.parse.unquote(fast.headers["X-Jigoe-Summary"]))["duration_seconds"]
    assert slow_len > fast_len


def test_empty_script_returns_a_readable_error(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        post(server, "/api/check", {"script": "   "})
    assert exc.value.code == 400
    assert "読み上げる本文" in json.loads(exc.value.read())["error"]


def test_cloning_engine_is_blocked_without_consent(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        post(server, "/api/speak", {"script": "テスト。", "engine": "elevenlabs"})
    assert exc.value.code == 400
    assert "自声であることの宣言" in json.loads(exc.value.read())["error"]


def test_unknown_path_is_404(server):
    base, opener = server
    with pytest.raises(urllib.error.HTTPError) as exc:
        opener.open(base + "/nope", timeout=5)
    assert exc.value.code == 404
