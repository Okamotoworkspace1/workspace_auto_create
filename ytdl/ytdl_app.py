#!/usr/bin/env python3
"""YouTube の URL を貼るだけで MP4（動画）か MP3（音声）に保存する Mac 向けツール。

ブラウザで開く簡易画面（標準ライブラリの http.server）と、ターミナルから直接
使う CLI の両方を備える。実際のダウンロードは yt-dlp、変換・結合は ffmpeg に任せる。

    python3 ytdl_app.py                       # 画面を開く
    python3 ytdl_app.py URL                   # MP4 で保存
    python3 ytdl_app.py URL --mp3             # MP3 で保存
    python3 ytdl_app.py URL -o ~/Movies       # 保存先を指定

画面は ``127.0.0.1`` にしか bind せず、ページに埋め込んだトークンの無い POST は
受け付けない（他サイトから localhost を叩かれるのを防ぐため）。
"""

from __future__ import annotations

import argparse
import html
import json
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    import yt_dlp
except ImportError:  # pragma: no cover - 起動スクリプトが入れるはずだが念のため
    sys.exit(
        "yt-dlp が見つかりません。次のコマンドで入れてください:\n"
        "  python3 -m pip install -U yt-dlp"
    )

DEFAULT_DIR = Path.home() / "Downloads" / "YouTube"
MAX_BODY = 64 * 1024

# QuickTime / 写真アプリで再生できるよう H.264 (avc1) + AAC (m4a) を優先する。
# YouTube の高画質版は VP9 / AV1 のことが多く、そのまま mp4 に入れると Mac 標準の
# プレイヤーでは再生できない。H.264 が無い動画だけ最後の候補にフォールバックする。
QUALITY_FORMATS = {
    "best": "bv*[vcodec^=avc1]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
    "1080": "bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/b[height<=1080][ext=mp4]/bv*[height<=1080]+ba/b[height<=1080]/b",
    "720": "bv*[height<=720][vcodec^=avc1]+ba[ext=m4a]/b[height<=720][ext=mp4]/bv*[height<=720]+ba/b[height<=720]/b",
    "480": "bv*[height<=480][vcodec^=avc1]+ba[ext=m4a]/b[height<=480][ext=mp4]/bv*[height<=480]+ba/b[height<=480]/b",
}
MP3_BITRATES = ("320", "192", "128")

YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")


class DownloadError(Exception):
    """利用者に見せてよい失敗理由。"""


class _QuietLogger:
    def debug(self, msg: str) -> None:
        pass

    info = warning = error = debug


def is_youtube_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url.strip())
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return parsed.scheme in ("http", "https") and any(
        host == h or host.endswith("." + h) for h in YOUTUBE_HOSTS
    )


def build_options(fmt: str, quality: str, out_dir: Path, hook=None) -> dict:
    """yt-dlp に渡すオプションを組み立てる。"""
    if fmt not in ("mp4", "mp3"):
        raise DownloadError(f"未対応の形式です: {fmt}")
    opts: dict = {
        "outtmpl": str(out_dir / "%(title).150B [%(id)s].%(ext)s"),
        "noplaylist": True,  # &list= 付きの URL でもその 1 本だけ
        "windowsfilenames": True,  # / : などファイル名に使いにくい文字を置換
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": _QuietLogger(),  # エラーは例外として受け取り、日本語で表示する
    }
    if hook is not None:
        opts["progress_hooks"] = [hook]
        opts["postprocessor_hooks"] = [hook]
    if fmt == "mp4":
        if quality not in QUALITY_FORMATS:
            raise DownloadError(f"未対応の画質です: {quality}")
        opts["format"] = QUALITY_FORMATS[quality]
        opts["merge_output_format"] = "mp4"
        opts["postprocessors"] = [{"key": "FFmpegMetadata"}]
    else:
        if quality not in MP3_BITRATES:
            raise DownloadError(f"未対応の音質です: {quality}")
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": quality,
            },
            {"key": "FFmpegMetadata"},
        ]
    return opts


def check_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise DownloadError(
            "ffmpeg が見つかりません。ターミナルで `brew install ffmpeg` を実行してください。"
        )


def download(url: str, fmt: str, quality: str, out_dir: Path, hook=None) -> Path:
    """1 本ダウンロードして、できあがったファイルのパスを返す。"""
    url = url.strip()
    if not is_youtube_url(url):
        raise DownloadError("YouTube の URL を入力してください。")
    check_ffmpeg()
    out_dir = out_dir.expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    opts = build_options(fmt, quality, out_dir, hook)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                raise DownloadError("動画情報を取得できませんでした。")
            if info.get("_type") == "playlist":
                raise DownloadError("再生リストではなく、動画 1 本の URL を貼ってください。")
            # 変換後の最終パスは requested_downloads に入る（古い版向けに推測も用意）
            done = info.get("requested_downloads") or [{}]
            final = done[-1].get("filepath")
            path = Path(final) if final else Path(ydl.prepare_filename(info)).with_suffix("." + fmt)
    except yt_dlp.utils.DownloadError as e:
        msg = str(e).removeprefix("ERROR: ").split("; please report this issue")[0].strip()
        raise DownloadError(f"ダウンロードに失敗しました: {msg}") from None
    if not path.exists():
        raise DownloadError("保存先のファイルが見つかりませんでした。")
    return path


# --------------------------------------------------------------------------
# ブラウザ画面
# --------------------------------------------------------------------------


class Job:
    def __init__(self, job_id: str, url: str, fmt: str, quality: str, out_dir: Path):
        self.id = job_id
        self.url = url
        self.fmt = fmt
        self.quality = quality
        self.out_dir = out_dir
        self.title = ""
        self.state = "queued"  # queued / downloading / converting / done / error
        self.percent = 0.0
        self.speed = ""
        self.eta = ""
        self.message = ""
        self.path: Path | None = None
        self.created = time.time()

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "fmt": self.fmt,
            "title": self.title,
            "state": self.state,
            "percent": round(self.percent, 1),
            "speed": self.speed,
            "eta": self.eta,
            "message": self.message,
            "filename": self.path.name if self.path else "",
        }

    def hook(self, d: dict) -> None:
        info = d.get("info_dict") or {}
        if info.get("title"):
            self.title = info["title"]
        status = d.get("status")
        if "postprocessor" in d:
            # 変換中（MP3 化・映像と音声の結合など）
            if status == "started":
                self.state = "converting"
            return
        if status == "downloading":
            self.state = "downloading"
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes") or 0
            if total:
                self.percent = min(100.0, done * 100.0 / total)
            speed = d.get("speed")
            self.speed = f"{speed / 1024 / 1024:.1f} MB/s" if speed else ""
            eta = d.get("eta")
            self.eta = f"残り {int(eta)} 秒" if eta is not None else ""
        elif status == "finished":
            self.percent = 100.0
            self.speed = self.eta = ""


class App:
    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.token = secrets.token_urlsafe(24)
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        # yt-dlp を並列に走らせると回線もファイル名も競合しやすいので 1 本ずつ
        self.worker_lock = threading.Lock()

    def submit(self, url: str, fmt: str, quality: str, out_dir: Path) -> Job:
        if not is_youtube_url(url):
            raise DownloadError("YouTube の URL を入力してください。")
        job = Job(secrets.token_hex(6), url.strip(), fmt, quality, out_dir)
        build_options(fmt, quality, out_dir)  # 不正な指定はここで弾く
        with self.lock:
            self.jobs[job.id] = job
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def _run(self, job: Job) -> None:
        with self.worker_lock:
            try:
                job.state = "downloading"
                job.path = download(job.url, job.fmt, job.quality, job.out_dir, job.hook)
                job.title = job.title or job.path.stem
                job.state = "done"
                job.percent = 100.0
            except DownloadError as e:
                job.state = "error"
                job.message = str(e)
            except Exception as e:  # noqa: BLE001 - 画面に理由を出して落ちないようにする
                job.state = "error"
                job.message = f"予期しないエラー: {e}"

    def list_jobs(self) -> list[dict]:
        with self.lock:
            jobs = sorted(self.jobs.values(), key=lambda j: j.created, reverse=True)
        return [j.to_json() for j in jobs]

    def get(self, job_id: str) -> Job | None:
        with self.lock:
            return self.jobs.get(job_id)


def reveal_in_finder(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", str(path)], check=False)
    elif shutil.which("xdg-open"):
        subprocess.run(["xdg-open", str(path.parent)], check=False)


def render_page(app: App) -> bytes:
    token = html.escape(app.token)
    out_dir = html.escape(str(app.out_dir))
    page = PAGE.replace("{{TOKEN}}", token).replace("{{OUT_DIR}}", out_dir)
    return page.encode("utf-8")


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ytdl"

        def log_message(self, *args) -> None:  # アクセスログは不要
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self._send(code, body, "application/json; charset=utf-8")

        def _host_ok(self) -> bool:
            # DNS リバインディング対策: localhost 以外の Host は拒否
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            return host in ("127.0.0.1", "localhost")

        def do_GET(self) -> None:
            if not self._host_ok():
                return self._send(403, b"forbidden", "text/plain")
            path = urllib.parse.urlparse(self.path).path
            if path == "/":
                return self._send(200, render_page(app), "text/html; charset=utf-8")
            if path == "/api/jobs":
                return self._json(200, {"jobs": app.list_jobs()})
            return self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:
            if not self._host_ok():
                return self._send(403, b"forbidden", "text/plain")
            if self.headers.get("X-Token") != app.token:
                return self._json(403, {"error": "トークンが不正です。ページを再読み込みしてください。"})
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                return self._json(413, {"error": "リクエストが大きすぎます。"})
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return self._json(400, {"error": "JSON が不正です。"})

            path = urllib.parse.urlparse(self.path).path
            if path == "/api/download":
                out_dir = Path(str(data.get("out_dir") or app.out_dir)).expanduser()
                try:
                    job = app.submit(
                        str(data.get("url", "")),
                        str(data.get("fmt", "mp4")),
                        str(data.get("quality", "best")),
                        out_dir,
                    )
                except DownloadError as e:
                    return self._json(400, {"error": str(e)})
                return self._json(200, {"job": job.to_json()})
            if path == "/api/reveal":
                job = app.get(str(data.get("id", "")))
                # 完了したジョブのファイルだけを開く（任意パスは受け付けない）
                if job is None or job.path is None or not job.path.exists():
                    return self._json(404, {"error": "ファイルが見つかりません。"})
                reveal_in_finder(job.path)
                return self._json(200, {"ok": True})
            return self._json(404, {"error": "not found"})

    return Handler


def serve(out_dir: Path, port: int, open_browser: bool) -> None:
    app = App(out_dir)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"YouTube ダウンローダーを開きました: {url}")
    print(f"保存先: {out_dir}")
    print("終了するには、このウィンドウで Ctrl+C を押してください。")
    if open_browser:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n終了しました。")
    finally:
        server.server_close()


PAGE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YouTube ダウンローダー</title>
<style>
  :root {
    --bg: #f6f5f3; --fg: #1d1c1a; --muted: #6b6864; --line: #e2ded8;
    --card: #ffffff; --accent: #d93025; --accent-fg: #ffffff;
    --ok: #1e7b45; --err: #b3261e; --bar: #ece9e4;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #17161a; --fg: #ece9e4; --muted: #9b968f; --line: #33302f;
      --card: #201f23; --accent: #f06a5f; --accent-fg: #17161a;
      --ok: #6fcf97; --err: #f28b82; --bar: #2d2b2f;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--fg);
    font-family: -apple-system, "Hiragino Sans", "Noto Sans JP", system-ui, sans-serif;
    line-height: 1.6;
  }
  .wrap { max-width: 720px; margin: 0 auto; padding: 40px 16px 64px; }
  h1 { font-size: 1.4rem; margin: 0 0 4px; }
  .sub { color: var(--muted); font-size: .85rem; margin: 0 0 24px; }
  .card {
    background: var(--card); border: 1px solid var(--line); border-radius: 14px;
    padding: 20px;
  }
  .urlrow { display: flex; gap: 8px; }
  input[type=text] {
    flex: 1; min-width: 0; font: inherit; padding: 12px 14px; border-radius: 10px;
    border: 1px solid var(--line); background: var(--bg); color: var(--fg);
  }
  input[type=text]:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
  .seg { display: inline-flex; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
  .seg input { display: none; }
  .seg label { padding: 8px 18px; cursor: pointer; font-weight: 600; user-select: none; }
  .seg input:checked + label { background: var(--accent); color: var(--accent-fg); }
  .opts { display: flex; flex-wrap: wrap; gap: 16px; align-items: center; margin-top: 16px; }
  select {
    font: inherit; padding: 8px 10px; border-radius: 10px;
    border: 1px solid var(--line); background: var(--bg); color: var(--fg);
  }
  button {
    font: inherit; font-weight: 700; border: 0; border-radius: 10px; cursor: pointer;
    padding: 12px 20px; background: var(--accent); color: var(--accent-fg);
  }
  button:disabled { opacity: .5; cursor: default; }
  button.ghost {
    background: transparent; color: var(--fg); border: 1px solid var(--line);
    padding: 6px 12px; font-weight: 600; font-size: .85rem;
  }
  details { margin-top: 14px; font-size: .85rem; color: var(--muted); }
  details input { width: 100%; margin-top: 6px; }
  .err { color: var(--err); font-size: .9rem; margin-top: 10px; min-height: 1.2em; }
  h2 { font-size: 1rem; margin: 32px 0 10px; }
  .job {
    background: var(--card); border: 1px solid var(--line); border-radius: 12px;
    padding: 14px 16px; margin-bottom: 10px;
  }
  .jobhead { display: flex; justify-content: space-between; gap: 12px; align-items: baseline; }
  .title { font-weight: 600; overflow-wrap: anywhere; }
  .badge {
    font-size: .75rem; font-weight: 700; padding: 2px 8px; border-radius: 999px;
    border: 1px solid var(--line); flex: none;
  }
  .meta { color: var(--muted); font-size: .8rem; margin-top: 4px; overflow-wrap: anywhere; }
  .bar { height: 6px; background: var(--bar); border-radius: 999px; margin-top: 10px; overflow: hidden; }
  .bar > div { height: 100%; background: var(--accent); width: 0; transition: width .3s; }
  .done .bar > div { background: var(--ok); }
  .state-ok { color: var(--ok); } .state-err { color: var(--err); }
  .foot { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; gap: 8px; }
  .empty { color: var(--muted); font-size: .9rem; }
  .note { color: var(--muted); font-size: .75rem; margin-top: 40px; }
  @media (max-width: 520px) { .urlrow { flex-direction: column; } }
</style>
</head>
<body>
<div class="wrap">
  <h1>YouTube ダウンローダー</h1>
  <p class="sub">URL を貼って「ダウンロード」を押すだけ。保存先: <span id="dirlabel">{{OUT_DIR}}</span></p>

  <form class="card" id="form">
    <div class="urlrow">
      <input type="text" id="url" placeholder="https://www.youtube.com/watch?v=..." autocomplete="off" autofocus>
      <button type="submit" id="go">ダウンロード</button>
    </div>
    <div class="opts">
      <div class="seg" role="radiogroup" aria-label="形式">
        <input type="radio" name="fmt" id="fmt-mp4" value="mp4" checked><label for="fmt-mp4">🎬 動画 MP4</label>
        <input type="radio" name="fmt" id="fmt-mp3" value="mp3"><label for="fmt-mp3">🎵 音声 MP3</label>
      </div>
      <label>画質・音質
        <select id="quality"></select>
      </label>
    </div>
    <details>
      <summary>保存先を変更</summary>
      <input type="text" id="outdir" value="{{OUT_DIR}}">
    </details>
    <div class="err" id="err"></div>
  </form>

  <h2>履歴</h2>
  <div id="jobs"><p class="empty">まだダウンロードはありません。</p></div>

  <p class="note">著作権者の許可がある動画や、ご自身の動画など、保存が認められたものにだけ使ってください。</p>
</div>
<script>
const TOKEN = "{{TOKEN}}";
const QUALITIES = {
  mp4: [["best", "最高画質"], ["1080", "1080p まで"], ["720", "720p まで"], ["480", "480p まで"]],
  mp3: [["192", "192 kbps（標準）"], ["320", "320 kbps（高音質）"], ["128", "128 kbps（軽量）"]],
};
const STATE = {
  queued: "待機中", downloading: "ダウンロード中", converting: "変換中",
  done: "完了", error: "エラー",
};
const $ = (id) => document.getElementById(id);

function fillQuality() {
  const fmt = document.querySelector("input[name=fmt]:checked").value;
  $("quality").innerHTML = "";
  for (const [v, label] of QUALITIES[fmt]) {
    const o = document.createElement("option");
    o.value = v; o.textContent = label;
    $("quality").appendChild(o);
  }
}
document.querySelectorAll("input[name=fmt]").forEach((r) => r.addEventListener("change", fillQuality));
fillQuality();

async function post(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Token": TOKEN },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "エラーが発生しました。");
  return data;
}

$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("err").textContent = "";
  const url = $("url").value.trim();
  if (!url) { $("err").textContent = "URL を貼り付けてください。"; return; }
  $("go").disabled = true;
  try {
    await post("/api/download", {
      url,
      fmt: document.querySelector("input[name=fmt]:checked").value,
      quality: $("quality").value,
      out_dir: $("outdir").value.trim(),
    });
    $("url").value = "";
    refresh();
  } catch (err) {
    $("err").textContent = err.message;
  } finally {
    $("go").disabled = false;
    $("url").focus();
  }
});

// URL 欄が空のときにフォーカスしたら、クリップボードの YouTube URL を自動で入れる
$("url").addEventListener("focus", async () => {
  if ($("url").value || !navigator.clipboard?.readText) return;
  try {
    const t = (await navigator.clipboard.readText()).trim();
    if (/^https?:\\/\\/([\\w-]+\\.)?(youtube\\.com|youtu\\.be)\\//.test(t)) $("url").value = t;
  } catch (_) { /* 許可されなければ何もしない */ }
});

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

function renderJobs(jobs) {
  const box = $("jobs");
  if (!jobs.length) return;
  box.innerHTML = "";
  for (const j of jobs) {
    const card = el("div", "job" + (j.state === "done" ? " done" : ""));
    const head = el("div", "jobhead");
    head.appendChild(el("div", "title", j.title || j.url));
    head.appendChild(el("span", "badge", j.fmt.toUpperCase()));
    card.appendChild(head);
    if (j.title) card.appendChild(el("div", "meta", j.url));
    if (j.state !== "error") {
      const bar = el("div", "bar"); const fill = el("div");
      fill.style.width = (j.state === "done" ? 100 : j.percent) + "%";
      bar.appendChild(fill); card.appendChild(bar);
    }
    const foot = el("div", "foot");
    let status = STATE[j.state] || j.state;
    if (j.state === "downloading") status += ` ${j.percent}%  ${j.speed}  ${j.eta}`;
    if (j.state === "done") status += ` — ${j.filename}`;
    if (j.state === "error") status = j.message;
    foot.appendChild(el("span", "meta " + (j.state === "done" ? "state-ok" : j.state === "error" ? "state-err" : ""), status));
    if (j.state === "done") {
      const b = el("button", "ghost", "Finder で表示");
      b.type = "button";
      b.onclick = () => post("/api/reveal", { id: j.id }).catch((e) => alert(e.message));
      foot.appendChild(b);
    }
    card.appendChild(foot);
    box.appendChild(card);
  }
}

async function refresh() {
  try {
    const res = await fetch("/api/jobs");
    renderJobs((await res.json()).jobs);
  } catch (_) { /* サーバ停止中 */ }
}
setInterval(refresh, 800);
refresh();
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def cli_hook(d: dict) -> None:
    if "postprocessor" in d:
        if d.get("status") == "started":
            print("\n変換中…", flush=True)
        return
    if d.get("status") == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        done = d.get("downloaded_bytes") or 0
        pct = f"{done * 100 / total:5.1f}%" if total else "   ?  "
        print(f"\rダウンロード中 {pct}", end="", flush=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="YouTube の動画を MP4（動画）か MP3（音声）で保存します。"
        " URL を省略するとブラウザで操作画面を開きます。"
    )
    p.add_argument("url", nargs="?", help="YouTube の URL")
    p.add_argument("--mp3", action="store_true", help="音声だけを MP3 で保存する")
    p.add_argument(
        "-q", "--quality",
        help="MP4: best / 1080 / 720 / 480（既定 best）、MP3: 320 / 192 / 128（既定 192）",
    )
    p.add_argument("-o", "--output", type=Path, default=DEFAULT_DIR, help=f"保存先（既定 {DEFAULT_DIR}）")
    p.add_argument("--port", type=int, default=0, help="画面モードのポート番号（既定: 空きポート）")
    p.add_argument("--no-browser", action="store_true", help="画面モードでブラウザを自動で開かない")
    args = p.parse_args(argv)

    out_dir = args.output.expanduser()
    if args.url is None:
        serve(out_dir, args.port, not args.no_browser)
        return 0

    fmt = "mp3" if args.mp3 else "mp4"
    quality = args.quality or ("192" if args.mp3 else "best")
    try:
        path = download(args.url, fmt, quality, out_dir, cli_hook)
    except DownloadError as e:
        print(f"\n{e}", file=sys.stderr)
        return 1
    print(f"\n保存しました: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
