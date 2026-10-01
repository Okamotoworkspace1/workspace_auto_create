"""ytdl_app のテスト。YouTube には接続しない。

    python3 -m pip install pytest "yt-dlp[default]"
    python3 -m pytest ytdl

ffmpeg があれば、ローカルに作った動画を実際にダウンロード・変換するテストも走る。
"""

from __future__ import annotations

import functools
import shutil
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytest.importorskip("yt_dlp")
import ytdl_app as m  # noqa: E402


def test_extract_urls_picks_youtube_only_and_dedupes_same_video():
    text = (
        "これ見て https://youtu.be/abcdefghijk、あと "
        "https://www.youtube.com/watch?v=abcdefghijk&list=PLx "
        "https://example.com/x https://www.youtube.com/shorts/zzzzzzzzzzz."
    )
    assert m.extract_urls(text) == [
        "https://youtu.be/abcdefghijk",
        "https://www.youtube.com/shorts/zzzzzzzzzzz",
    ]


def test_is_youtube_url_rejects_lookalike_hosts():
    assert m.is_youtube_url("https://music.youtube.com/watch?v=abcdefghijk")
    assert not m.is_youtube_url("https://youtube.com.evil.example/watch?v=abcdefghijk")
    assert not m.is_youtube_url("ftp://youtube.com/x")


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=abcdefghijk&t=3",
    "https://youtu.be/abcdefghijk?si=x",
    "https://www.youtube.com/shorts/abcdefghijk",
    "https://www.youtube.com/live/abcdefghijk",
])
def test_video_id(url):
    assert m.video_id(url) == "abcdefghijk"


def test_friendly_error_translates_and_keeps_detail():
    e = m.friendly_error("ERROR: [youtube] abc: Private video. Sign in if you've been granted access")
    assert str(e) == "非公開の動画のため保存できません。"
    assert "Private video" in e.detail
    assert str(m.friendly_error("ERROR: something new")) == "ダウンロードに失敗しました。"


def test_clean_settings_ignores_invalid_values():
    s = m.clean_settings({"fmt": "avi", "q_mp3": "999", "auto_start": "yes", "notify": False}, m.DEFAULT_SETTINGS)
    assert s["fmt"] == "mp4" and s["q_mp3"] == "192" and s["auto_start"] is True and s["notify"] is False


def test_unique_path_never_overwrites(tmp_path):
    (tmp_path / "a.mp4").write_text("x")
    (tmp_path / "a (2).mp4").write_text("x")
    assert m.unique_path(tmp_path / "a.mp4").name == "a (3).mp4"
    assert m.unique_path(tmp_path / "b.mp4").name == "b.mp4"


def test_build_options_rejects_unknown_quality(tmp_path):
    with pytest.raises(m.DownloadError):
        m.build_options("mp3", "best", tmp_path)
    with pytest.raises(m.DownloadError):
        m.build_options("wav", "192", tmp_path)


def test_app_queue_cancel_and_settings(tmp_path, monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def fake_download(url, fmt, quality, out_dir, hook=None, on_info=None):
        started.set()
        release.wait(5)
        p = out_dir / f"{m.video_id(url)}.{fmt}"
        out_dir.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
        return p

    monkeypatch.setattr(m, "download", fake_download)
    monkeypatch.setattr(m, "notify", lambda *a, **k: None)
    app = m.App(tmp_path / "out", state_dir=tmp_path / "state")
    added, skipped = app.submit("https://youtu.be/aaaaaaaaaaa https://youtu.be/bbbbbbbbbbb", "mp4", "best")
    assert len(added) == 2 and skipped == 0
    assert started.wait(5)
    # 同じ動画・形式の二重登録はしない
    assert app.submit("https://youtu.be/aaaaaaaaaaa", "mp4", "best") == ([], 1)
    assert app.cancel(added[1].id)  # 順番待ちのものを取り消す
    release.set()
    for _ in range(50):
        if not app.busy():
            break
        threading.Event().wait(0.1)
    states = {j.vid: j.state for j in app.jobs.values()}
    assert states == {"aaaaaaaaaaa": "done", "bbbbbbbbbbb": "cancelled"}
    assert not app.should_exit(__import__("time").time())

    # 設定と履歴は次回の起動に引き継がれる
    app.update_settings({"fmt": "mp3"})
    again = m.App(state_dir=tmp_path / "state")
    assert again.settings["fmt"] == "mp3"
    assert [j.vid for j in again.jobs.values()] == ["aaaaaaaaaaa"]


@pytest.fixture
def local_video(tmp_path_factory):
    """ffmpeg で短い動画を作り、ローカルの HTTP サーバで配る。"""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg がありません")
    root = tmp_path_factory.mktemp("media")
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=15",
         "-f", "lavfi", "-i", "sine", "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", str(root / "clip.mp4")],
        check=True,
    )
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a: None
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/clip.mp4"
    server.shutdown()


def test_download_mp4_then_mp3_keeps_both(local_video, tmp_path, monkeypatch):
    monkeypatch.setattr(m, "is_youtube_url", lambda u: True)
    out = tmp_path / "out"
    mp4 = m.download(local_video, "mp4", "best", out)
    mp3 = m.download(local_video, "mp3", "128", out)
    again = m.download(local_video, "mp4", "720", out)
    assert (mp4.suffix, mp3.suffix) == (".mp4", ".mp3")
    assert again.name.endswith(" (2).mp4")
    # MP3 化で先に保存した MP4 が消えないこと、作業用フォルダが残らないこと
    assert sorted(p.name for p in out.iterdir()) == sorted([mp4.name, mp3.name, again.name])


def test_download_cancel_leaves_no_files(local_video, tmp_path, monkeypatch):
    monkeypatch.setattr(m, "is_youtube_url", lambda u: True)

    def hook(d):
        raise m.yt_dlp.utils.DownloadCancelled()

    with pytest.raises(m.Cancelled):
        m.download(local_video, "mp4", "best", tmp_path, hook)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("mac, win, keys, filer", [
    (True, False, "⌘", "Finder"),
    (False, True, "Ctrl", "エクスプローラー"),
])
def test_page_labels_follow_os(monkeypatch, mac, win, keys, filer):
    monkeypatch.setattr(m, "IS_MAC", mac)
    monkeypatch.setattr(m, "IS_WIN", win)
    app = m.App.__new__(m.App)
    app.token, app.instance = "tok", "abc"
    page = m.render_page(app).decode()
    assert "{{" not in page
    assert f"<kbd>{keys}</kbd>" in page and f'const FILER = "{filer}";' in page


def test_update_ytdlp_skips_when_recently_updated(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "SUPPORT_DIR", tmp_path)
    (tmp_path / ".updated").touch()
    called = []
    monkeypatch.setattr(m.subprocess, "run", lambda *a, **k: called.append(a))
    m.update_ytdlp()
    assert called == []


def test_update_ytdlp_uses_uv_and_refreshes_stamp(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "SUPPORT_DIR", tmp_path)
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "uv").write_text("")
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return m.subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(m.subprocess, "run", fake_run)
    m.update_ytdlp()
    assert calls and calls[0][0].endswith("uv") and "--upgrade-package" in calls[0]
    assert (tmp_path / ".updated").exists()
    assert not (tmp_path / ".updating").exists()  # 更新が終わったらロックは消える
