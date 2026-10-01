#!/usr/bin/env python3
"""YouTube の URL を貼るだけで MP4（動画）か MP3（音声）に保存するツール（Mac / Windows）。

ブラウザで開く操作画面（標準ライブラリの http.server）と、ターミナルから直接
使う CLI の両方を備える。実際のダウンロードは yt-dlp、変換・結合は ffmpeg に任せる。

    python3 ytdl_app.py                       # 画面を開く
    python3 ytdl_app.py URL                   # MP4 で保存
    python3 ytdl_app.py URL --mp3             # MP3 で保存
    python3 ytdl_app.py URL -o ~/Movies       # 保存先を指定

画面は ``127.0.0.1`` にしか bind せず、ページに埋め込んだトークンの無い POST は
受け付けない（他サイトから localhost を叩かれるのを防ぐため）。
すでに起動していれば新しく立ち上げず、既存の画面を開くだけにする。
ブラウザのタブを閉じると、ダウンロードが終わりしだい自動で終了する。
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import queue
import re
import secrets
import shutil
import subprocess
import tempfile
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    import yt_dlp
except ImportError:  # pragma: no cover - 起動スクリプトが入れるはずだが念のため
    sys.exit(
        "yt-dlp が見つかりません。次のコマンドで入れてください:\n"
        '  python3 -m pip install -U "yt-dlp[default,deno]"'
    )

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"
DEFAULT_DIR = Path.home() / "Downloads" / "YouTube"
if IS_MAC:
    SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "YouTubeDownloader"
elif IS_WIN:
    SUPPORT_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "YouTubeDownloader"
else:
    SUPPORT_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "youtube-downloader"
# Windows のインストーラーは ffmpeg をここに置く。PATH を通さずに使えるようにする
BUNDLED_FFMPEG = SUPPORT_DIR / "ffmpeg"
if BUNDLED_FFMPEG.is_dir():
    os.environ["PATH"] = str(BUNDLED_FFMPEG) + os.pathsep + os.environ.get("PATH", "")
# Windows で子プロセス（PowerShell など）を起動したときに黒い窓を出さない
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PREFERRED_PORT = 8765
MAX_BODY = 256 * 1024
HISTORY_LIMIT = 100
BYE_GRACE = 5  # タブを閉じてから終了するまでの猶予（再読み込みと区別するため）
IDLE_TIMEOUT = 30 * 60  # 画面から一度も問い合わせが無いまま、この秒数たったら終了

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
URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")
VIDEO_ID_RE = re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/|/live/|/embed/)([\w-]{11})")

# yt-dlp の英語エラーを、利用者が次に何をすればよいか分かる日本語に置き換える
FRIENDLY_ERRORS = [
    (("Private video",), "非公開の動画のため保存できません。"),
    (("confirm your age", "age-restricted", "inappropriate for some users"),
     "年齢制限のある動画のため保存できません。"),
    (("not a bot", "HTTP Error 429", "Too Many Requests"),
     "YouTube に一時的に制限されています。しばらく待ってから「再試行」を押してください。"),
    (("members-only", "Join this channel", "channel's members"),
     "メンバー限定の動画のため保存できません。"),
    (("not available in your country", "geo restrict", "The uploader has not made this video available"),
     "お住まいの地域では公開されていない動画です。"),
    (("live event will begin", "Premieres in", "is upcoming"),
     "まだ公開・配信が始まっていない動画です。"),
    (("Video unavailable", "This video has been removed", "This video is not available", "Incomplete YouTube ID"),
     "動画が見つかりません（削除・非公開・URL の間違いの可能性があります）。"),
    (("No space left", "There is not enough space"), "ディスクの空き容量が足りません。"),
    (("Permission denied", "Operation not permitted", "Read-only file system", "Access is denied"),
     "保存先フォルダに書き込めません。保存先を変更してください。"),
    (("urlopen error", "timed out", "Temporary failure in name resolution", "nodename nor servname",
      "Connection reset", "Network is unreachable", "Failed to resolve"),
     "インターネットに接続できませんでした。接続を確認して「再試行」を押してください。"),
    (("Requested format is not available", "Only images are available", "n challenge", "signature"),
     "この動画の形式を取得できませんでした。アプリを開き直すと部品が更新され、直ることがあります。"),
]


class DownloadError(Exception):
    """利用者に見せてよい失敗理由。detail には元の英語メッセージを入れる。"""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.detail = detail


class Cancelled(Exception):
    pass


class _QuietLogger:
    def debug(self, msg: str) -> None:
        pass

    info = warning = error = debug


def friendly_error(raw: str) -> DownloadError:
    raw = raw.removeprefix("ERROR: ").split("; please report this issue")[0].strip()
    for needles, message in FRIENDLY_ERRORS:
        if any(n.lower() in raw.lower() for n in needles):
            return DownloadError(message, raw)
    return DownloadError("ダウンロードに失敗しました。", raw)


def is_youtube_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url.strip())
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return parsed.scheme in ("http", "https") and any(
        host == h or host.endswith("." + h) for h in YOUTUBE_HOSTS
    )


def extract_urls(text: str) -> list[str]:
    """貼り付けられた文章から YouTube の URL をすべて取り出す（重複は除く）。"""
    seen: dict[str, str] = {}
    for m in URL_RE.finditer(text or ""):
        url = m.group(0).rstrip(".,)]}!'")
        if is_youtube_url(url):
            seen.setdefault(video_id(url) or url, url)  # 同じ動画の別表記もまとめる
    return list(seen.values())


def video_id(url: str) -> str:
    m = VIDEO_ID_RE.search(url)
    return m.group(1) if m else ""


def build_options(fmt: str, quality: str, work_dir: Path, hook=None) -> dict:
    """yt-dlp に渡すオプションを組み立てる。"""
    if fmt not in ("mp4", "mp3"):
        raise DownloadError(f"未対応の形式です: {fmt}")
    opts: dict = {
        # yt-dlp には作業用フォルダだけを見せ、完成品は download() が保存先へ移す。
        # 保存先を見せると、同名の MP4 を「ダウンロード済み」とみなして MP3 化の
        # 元にし、変換後に消してしまうため
        "outtmpl": str(work_dir / "%(title).150B [%(id)s].%(ext)s"),
        "noplaylist": True,  # &list= 付きの URL でもその 1 本だけ
        "windowsfilenames": True,  # / : などファイル名に使いにくい文字を置換
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": _QuietLogger(),  # エラーは例外として受け取り、日本語で表示する
        "retries": 5,
        "fragment_retries": 5,
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
        if IS_WIN:
            raise DownloadError("ffmpeg が見つかりません。インストーラーをもう一度実行してください。")
        raise DownloadError(
            "ffmpeg が見つかりません。ターミナルで `brew install ffmpeg` を実行してください。"
        )


def download(url: str, fmt: str, quality: str, out_dir: Path, hook=None, on_info=None) -> Path:
    """1 本ダウンロードして、できあがったファイルのパスを返す。

    on_info はダウンロード前に動画情報（タイトルなど）が分かった時点で呼ばれる。
    """
    url = url.strip()
    if not is_youtube_url(url):
        raise DownloadError("YouTube の URL を入力してください。")
    check_ffmpeg()
    out_dir = out_dir.expanduser()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise friendly_error(str(e)) from None
    try:
        temp_dir = Path(tempfile.mkdtemp(prefix=".ytdl-", dir=out_dir))
    except OSError as e:
        raise friendly_error(str(e)) from None
    opts = build_options(fmt, quality, temp_dir, hook)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            # 先に情報だけ取り、再生リストや配信中のライブを弾いてから保存する
            info = ydl.extract_info(url, download=False, process=False)
            if info is None:
                raise DownloadError("動画情報を取得できませんでした。")
            if info.get("_type") == "playlist":
                raise DownloadError("再生リストではなく、動画 1 本の URL を貼ってください。")
            if info.get("is_live") or info.get("live_status") == "is_live":
                raise DownloadError("配信中のライブは保存できません。配信が終わってから試してください。")
            if on_info is not None:
                on_info(info)
            info = ydl.process_ie_result(info, download=True)
            # 変換後の最終パスは requested_downloads に入る（古い版向けに推測も用意）
            done = (info or {}).get("requested_downloads") or [{}]
            final = done[-1].get("filepath")
            made = Path(final) if final else Path(ydl.prepare_filename(info)).with_suffix("." + fmt)
            if not made.exists():
                raise DownloadError("変換後のファイルが見つかりませんでした。")
            path = unique_path(out_dir / made.name)
            shutil.move(str(made), path)
    except yt_dlp.utils.DownloadCancelled:
        raise Cancelled() from None
    except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError) as e:
        raise friendly_error(str(e)) from None
    except OSError as e:
        raise friendly_error(str(e)) from None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)  # キャンセル・失敗時の途中ファイルも消える
    return path


def unique_path(path: Path) -> Path:
    """同名のファイルがあれば「名前 (2).mp4」のようにずらす（上書きしない）。"""
    n = 2
    candidate = path
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    return candidate


# --------------------------------------------------------------------------
# OS との連携（通知・フォルダ選択・Finder / エクスプローラー）
# --------------------------------------------------------------------------


def osascript(lines: list[str], *args: str, timeout: float | None = 10) -> subprocess.CompletedProcess | None:
    if not IS_MAC or shutil.which("osascript") is None:
        return None
    cmd = ["osascript"]
    for line in lines:
        cmd += ["-e", line]
    try:
        return subprocess.run([*cmd, *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def powershell(script: str, env: dict[str, str] | None = None, sta: bool = False,
               timeout: float | None = 15) -> subprocess.CompletedProcess | None:
    """Windows で PowerShell を窓なしで動かす。文字列は環境変数で渡す（埋め込むと引用符でこわれるため）。"""
    if not IS_WIN:
        return None
    # 日本語を含むスクリプトを確実に渡すため UTF-16 の Base64 にする
    encoded = base64.b64encode(
        ("[Console]::OutputEncoding = [Text.Encoding]::UTF8\n" + script).encode("utf-16-le")
    ).decode()
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass"]
    if sta:
        cmd.append("-STA")
    try:
        return subprocess.run(
            [*cmd, "-EncodedCommand", encoded], capture_output=True, timeout=timeout,
            env={**os.environ, **(env or {})}, creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


WIN_TOAST = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$x = New-Object Windows.Data.Xml.Dom.XmlDocument
$x.LoadXml('<toast><visual><binding template="ToastGeneric"><text></text><text></text></binding></visual></toast>')
$t = $x.GetElementsByTagName('text')
$t.Item(0).AppendChild($x.CreateTextNode($env:YTDL_TITLE)) > $null
$t.Item(1).AppendChild($x.CreateTextNode($env:YTDL_MESSAGE)) > $null
$id = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($id).Show(
  [Windows.UI.Notifications.ToastNotification]::new($x))
"""

WIN_CHOOSE_FOLDER = r"""
Add-Type -AssemblyName System.Windows.Forms
$d = New-Object System.Windows.Forms.FolderBrowserDialog
$d.Description = '保存先のフォルダを選んでください'
$d.ShowNewFolderButton = $true
if (Test-Path -LiteralPath $env:YTDL_DIR) { $d.SelectedPath = $env:YTDL_DIR }
# ブラウザの裏に隠れないよう、最前面の見えない窓を親にする
$owner = New-Object System.Windows.Forms.Form -Property @{ TopMost = $true; ShowInTaskbar = $false }
if ($d.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Out.Write($d.SelectedPath) }
"""


def notify(title: str, message: str, sound: bool = True) -> None:
    if IS_WIN:
        env = {"YTDL_TITLE": title, "YTDL_MESSAGE": message[:200]}
        threading.Thread(target=powershell, args=(WIN_TOAST, env), daemon=True).start()
        return
    # 文字列は引数で渡す（AppleScript に埋め込むと引用符でこわれるため）
    script = ["on run argv", "display notification (item 2 of argv) with title (item 1 of argv)"
              + (' sound name "Glass"' if sound else ""), "end run"]
    threading.Thread(target=osascript, args=(script, title, message[:200]), daemon=True).start()


def choose_folder(current: Path) -> Path | None:
    if IS_WIN:
        res = powershell(WIN_CHOOSE_FOLDER, {"YTDL_DIR": str(current)}, sta=True, timeout=None)
        out = res.stdout.decode("utf-8", "replace").strip() if res is not None else ""
        return Path(out) if out else None
    script = [
        "on run argv",
        'set p to "保存先のフォルダを選んでください"',
        "activate",
        "try",
        "set d to (POSIX file (item 1 of argv)) as alias",
        "set f to choose folder with prompt p default location d",
        "on error number n",
        "if n is -128 then error number -128",
        "set f to choose folder with prompt p",
        "end try",
        "return POSIX path of f",
        "end run",
    ]
    res = osascript(script, str(current), timeout=None)
    if res is None or res.returncode != 0 or not res.stdout.strip():
        return None
    return Path(res.stdout.strip())


def open_path(path: Path, reveal: bool = False) -> None:
    if IS_WIN:
        if reveal:
            # explorer は /select,"パス" を 1 つの引数として受け取る（パスに " は使えない）
            subprocess.run(f'explorer /select,"{path}"', check=False)
        else:
            os.startfile(path)  # type: ignore[attr-defined]  # 既定のアプリで開く
        return
    if IS_MAC:
        subprocess.run(["open", "-R", str(path)] if reveal else ["open", str(path)], check=False)
    elif shutil.which("xdg-open"):
        subprocess.run(["xdg-open", str(path.parent if reveal else path)], check=False)


# --------------------------------------------------------------------------
# 設定と履歴の保存
# --------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "fmt": "mp4",
    "q_mp4": "best",
    "q_mp3": "192",
    "out_dir": str(DEFAULT_DIR),
    "auto_start": True,  # 貼り付けたらすぐダウンロード
    "notify": True,  # 完了したら OS の通知を出す
}


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def clean_settings(data: dict, base: dict) -> dict:
    s = dict(base)
    if data.get("fmt") in ("mp4", "mp3"):
        s["fmt"] = data["fmt"]
    if data.get("q_mp4") in QUALITY_FORMATS:
        s["q_mp4"] = data["q_mp4"]
    if data.get("q_mp3") in MP3_BITRATES:
        s["q_mp3"] = data["q_mp3"]
    if isinstance(data.get("out_dir"), str) and data["out_dir"].strip():
        s["out_dir"] = str(Path(data["out_dir"].strip()).expanduser())
    for key in ("auto_start", "notify"):
        if isinstance(data.get(key), bool):
            s[key] = data[key]
    return s


# --------------------------------------------------------------------------
# ダウンロードの順番待ちと進み具合
# --------------------------------------------------------------------------

ACTIVE_STATES = ("queued", "fetching", "downloading", "converting")


class Job:
    def __init__(self, url: str, fmt: str, quality: str, out_dir: Path):
        self.id = secrets.token_hex(6)
        self.url = url
        self.fmt = fmt
        self.quality = quality
        self.out_dir = out_dir
        self.vid = video_id(url)
        self.title = ""
        self.duration = 0
        self.thumbnail = f"https://i.ytimg.com/vi/{self.vid}/mqdefault.jpg" if self.vid else ""
        self.state = "queued"  # queued / fetching / downloading / converting / done / error / cancelled
        self.percent = 0.0
        self.speed = ""
        self.eta = ""
        self.message = ""
        self.detail = ""
        self.path: Path | None = None
        self.size = 0
        self.created = time.time()
        self.cancel = threading.Event()
        self._parts = 0  # MP4 は映像と音声を別々に落とすので何本目か数える

    def reset(self) -> None:
        self.state = "queued"
        self.percent = 0.0
        self.speed = self.eta = self.message = self.detail = ""
        self.path = None
        self.cancel = threading.Event()
        self._parts = 0

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "fmt": self.fmt,
            "quality": self.quality,
            "title": self.title,
            "duration": self.duration,
            "thumbnail": self.thumbnail,
            "state": self.state,
            "percent": round(self.percent, 1),
            "speed": self.speed,
            "eta": self.eta,
            "message": self.message,
            "detail": self.detail,
            "filename": self.path.name if self.path else "",
            "folder": str(self.path.parent) if self.path else str(self.out_dir),
            "size": self.size,
        }

    def to_history(self) -> dict:
        return {
            "id": self.id, "url": self.url, "fmt": self.fmt, "quality": self.quality,
            "title": self.title, "duration": self.duration, "thumbnail": self.thumbnail,
            "path": str(self.path), "size": self.size, "created": self.created,
        }

    @classmethod
    def from_history(cls, d: dict) -> Job | None:
        try:
            path = Path(d["path"])
            if not path.exists():
                return None
            job = cls(d["url"], d["fmt"], d["quality"], path.parent)
            job.id = d["id"]
            job.title = d.get("title", "")
            job.duration = int(d.get("duration") or 0)
            job.thumbnail = d.get("thumbnail") or job.thumbnail
            job.path = path
            job.size = int(d.get("size") or 0)
            job.created = float(d.get("created") or 0)
            job.state = "done"
            job.percent = 100.0
            return job
        except (KeyError, TypeError, ValueError):
            return None

    def on_info(self, info: dict) -> None:
        self.title = info.get("title") or self.title
        self.duration = int(info.get("duration") or 0)
        if info.get("thumbnail") and not self.vid:
            self.thumbnail = info["thumbnail"]

    def hook(self, d: dict) -> None:
        if self.cancel.is_set():
            raise yt_dlp.utils.DownloadCancelled()
        status = d.get("status")
        if "postprocessor" in d:
            # 変換中（MP3 化・映像と音声の結合など）
            if status == "started":
                self.state = "converting"
                self.speed = self.eta = ""
            return
        if status == "downloading":
            self.state = "downloading"
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes") or 0
            if total:
                pct = min(100.0, done * 100.0 / total)
                # MP4 は映像→音声の 2 本。バーが 2 回満ちないよう配分する
                if self.fmt == "mp4" and d.get("info_dict", {}).get("requested_formats"):
                    pct = (90.0 if self._parts == 0 else 10.0) * pct / 100 + (90.0 if self._parts else 0)
                self.percent = max(self.percent, pct)
            speed = d.get("speed")
            self.speed = f"{speed / 1024 / 1024:.1f} MB/s" if speed else ""
            eta = d.get("eta")
            self.eta = format_eta(eta) if eta is not None else ""
        elif status == "finished":
            self._parts += 1
            self.speed = self.eta = ""


def format_eta(sec: float) -> str:
    sec = int(sec)
    if sec >= 60:
        return f"残り約 {sec // 60} 分 {sec % 60} 秒"
    return f"残り約 {sec} 秒"


class App:
    def __init__(self, out_dir: Path | None = None, state_dir: Path = SUPPORT_DIR):
        self.state_dir = state_dir
        self.settings_path = state_dir / "settings.json"
        self.history_path = state_dir / "history.json"
        self.settings = clean_settings(read_json(self.settings_path, {}), DEFAULT_SETTINGS)
        if out_dir is not None:
            self.settings["out_dir"] = str(out_dir.expanduser())
        self.token = secrets.token_urlsafe(24)
        self.instance = secrets.token_hex(4)
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self.queue: queue.Queue[str] = queue.Queue()
        self.last_seen = time.time()
        self.bye_at = 0.0
        self.quit_requested = False
        for d in read_json(self.history_path, []):
            job = Job.from_history(d) if isinstance(d, dict) else None
            if job is not None:
                self.jobs[job.id] = job
        threading.Thread(target=self._worker, daemon=True).start()

    # --- 設定 ---
    def update_settings(self, data: dict) -> dict:
        with self.lock:
            self.settings = clean_settings(data, self.settings)
            write_json(self.settings_path, self.settings)
            return dict(self.settings)

    @property
    def out_dir(self) -> Path:
        return Path(self.settings["out_dir"]).expanduser()

    # --- ジョブ ---
    def submit(self, text: str, fmt: str, quality: str) -> tuple[list[Job], int]:
        urls = extract_urls(text)
        if not urls:
            raise DownloadError("YouTube の URL が見つかりませんでした。")
        build_options(fmt, quality, self.out_dir)  # 不正な形式・画質はここで弾く
        added, skipped = [], 0
        with self.lock:
            active = {(j.url, j.fmt) for j in self.jobs.values() if j.state in ACTIVE_STATES}
            for url in urls:
                if (url, fmt) in active:
                    skipped += 1
                    continue
                job = Job(url, fmt, quality, self.out_dir)
                self.jobs[job.id] = job
                added.append(job)
        for job in added:
            self.queue.put(job.id)
        return added, skipped

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None or job.state not in ACTIVE_STATES:
            return False
        job.cancel.set()
        if job.state == "queued":
            job.state = "cancelled"
        return True

    def retry(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None or job.state not in ("error", "cancelled"):
            return False
        job.reset()
        job.out_dir = self.out_dir
        self.queue.put(job.id)
        return True

    def remove(self, job_id: str) -> None:
        with self.lock:
            job = self.jobs.get(job_id)
            if job is not None and job.state not in ACTIVE_STATES:
                del self.jobs[job_id]
        self._save_history()

    def clear_finished(self) -> None:
        with self.lock:
            for jid in [j.id for j in self.jobs.values() if j.state not in ACTIVE_STATES]:
                del self.jobs[jid]
        self._save_history()

    def busy(self) -> bool:
        with self.lock:
            return any(j.state in ACTIVE_STATES for j in self.jobs.values())

    def _worker(self) -> None:
        # yt-dlp を並列に走らせると回線もファイル名も競合しやすいので 1 本ずつ
        while True:
            job = self.get(self.queue.get())
            if job is None or job.state != "queued":
                continue
            if job.cancel.is_set():
                job.state = "cancelled"
                continue
            self._run(job)

    def _run(self, job: Job) -> None:
        try:
            job.state = "fetching"
            job.path = download(job.url, job.fmt, job.quality, job.out_dir, job.hook, job.on_info)
            job.title = job.title or job.path.stem
            job.size = job.path.stat().st_size
            job.percent = 100.0
            job.state = "done"
            self._save_history()
            if self.settings.get("notify"):
                notify("ダウンロード完了", f"{job.title}（{job.fmt.upper()}）")
        except Cancelled:
            job.state = "cancelled"
        except DownloadError as e:
            job.state = "error"
            job.message = str(e)
            job.detail = e.detail
            if self.settings.get("notify"):
                notify("ダウンロードできませんでした", job.title or job.url, sound=False)
        except Exception as e:  # noqa: BLE001 - 画面に理由を出して落ちないようにする
            job.state = "error"
            job.message = "予期しないエラーが起きました。"
            job.detail = repr(e)
        finally:
            job.speed = job.eta = ""

    def _save_history(self) -> None:
        with self.lock:
            done = sorted(
                (j for j in self.jobs.values() if j.state == "done" and j.path),
                key=lambda j: j.created, reverse=True,
            )[:HISTORY_LIMIT]
            write_json(self.history_path, [j.to_history() for j in done])

    def list_jobs(self) -> list[dict]:
        with self.lock:
            jobs = sorted(self.jobs.values(), key=lambda j: j.created, reverse=True)
        return [j.to_json() for j in jobs]

    def get(self, job_id: str) -> Job | None:
        with self.lock:
            return self.jobs.get(job_id)

    # --- 自動終了 ---
    def should_exit(self, now: float) -> bool:
        if self.quit_requested:
            return True
        if self.busy():
            return False
        if self.bye_at and self.last_seen < self.bye_at and now - self.bye_at > BYE_GRACE:
            return True
        return now - self.last_seen > IDLE_TIMEOUT


def render_page(app: App) -> bytes:
    if IS_MAC:
        keys, filer = "<kbd>⌘</kbd> <kbd>V</kbd>", "Finder"
    elif IS_WIN:
        keys, filer = "<kbd>Ctrl</kbd> + <kbd>V</kbd>", "エクスプローラー"
    else:
        keys, filer = "<kbd>Ctrl</kbd> + <kbd>V</kbd>", "フォルダ"
    page = (
        PAGE.replace("{{TOKEN}}", html.escape(app.token))
        .replace("{{INSTANCE}}", app.instance)
        .replace("{{PASTE_KEYS}}", keys)
        .replace("{{PASTE_TEXT}}", "⌘V" if IS_MAC else "Ctrl+V")
        .replace("{{FILER}}", filer)
    )
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
            if path == "/api/ping":
                return self._json(200, {"app": "ytdl"})
            if path == "/api/state":
                app.last_seen = time.time()
                return self._json(200, {
                    "instance": app.instance,
                    "settings": app.settings,
                    "jobs": app.list_jobs(),
                    "mac": IS_MAC,
                })
            return self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:
            if not self._host_ok():
                return self._send(403, b"forbidden", "text/plain")
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            if path == "/api/bye":
                # タブを閉じたときの sendBeacon。ヘッダを付けられないのでトークンは URL で受ける
                if urllib.parse.parse_qs(parsed.query).get("t", [""])[0] == app.token:
                    app.bye_at = time.time()
                return self._send(204, b"", "text/plain")
            if self.headers.get("X-Token") != app.token:
                return self._json(403, {"error": "reload"})
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                return self._json(413, {"error": "リクエストが大きすぎます。"})
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return self._json(400, {"error": "JSON が不正です。"})
            if not isinstance(data, dict):
                return self._json(400, {"error": "JSON が不正です。"})
            job_id = str(data.get("id", ""))

            if path == "/api/download":
                try:
                    added, skipped = app.submit(
                        str(data.get("text", "")),
                        str(data.get("fmt", "mp4")),
                        str(data.get("quality", "best")),
                    )
                except DownloadError as e:
                    return self._json(400, {"error": str(e)})
                return self._json(200, {"added": len(added), "skipped": skipped})
            if path == "/api/settings":
                return self._json(200, {"settings": app.update_settings(data)})
            if path == "/api/choose-folder":
                chosen = choose_folder(app.out_dir)
                if chosen is not None:
                    app.update_settings({"out_dir": str(chosen)})
                return self._json(200, {"settings": app.settings})
            if path == "/api/open-folder":
                app.out_dir.mkdir(parents=True, exist_ok=True)
                open_path(app.out_dir)
                return self._json(200, {"ok": True})
            if path == "/api/cancel":
                return self._json(200, {"ok": app.cancel(job_id)})
            if path == "/api/retry":
                return self._json(200, {"ok": app.retry(job_id)})
            if path == "/api/remove":
                app.remove(job_id)
                return self._json(200, {"ok": True})
            if path == "/api/clear":
                app.clear_finished()
                return self._json(200, {"ok": True})
            if path in ("/api/open", "/api/reveal"):
                job = app.get(job_id)
                # 完了したジョブのファイルだけを開く（任意パスは受け付けない）
                if job is None or job.path is None or not job.path.exists():
                    return self._json(404, {"error": "ファイルが見つかりません。移動・削除された可能性があります。"})
                open_path(job.path, reveal=(path == "/api/reveal"))
                return self._json(200, {"ok": True})
            if path == "/api/quit":
                for job in list(app.jobs.values()):
                    job.cancel.set()
                app.quit_requested = True
                return self._json(200, {"ok": True})
            return self._json(404, {"error": "not found"})

    return Handler


def redirect_output_if_windowless() -> None:
    """pythonw（窓なし）で起動されたときは出力先が無いので、ログファイルに書く。"""
    if sys.stdout is not None and sys.stderr is not None:
        return
    log = SUPPORT_DIR / "app.log"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        if log.exists() and log.stat().st_size > 1_000_000:
            log.unlink()
        f = open(log, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - 終了まで開いたまま
    except OSError:
        return
    sys.stdout = sys.stderr = f


def update_ytdlp_in_background() -> None:
    """yt-dlp を 1 日 1 回、裏で最新にする（反映されるのは次に起動したとき）。

    YouTube の仕様変更に合わせて頻繁に直るため。Mac では launcher.sh が同じことをする。
    """
    stamp = SUPPORT_DIR / ".updated"
    try:
        if time.time() - stamp.stat().st_mtime < 24 * 3600:
            return
    except OSError:
        pass
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and (exe.parent / "python.exe").exists():
        exe = exe.parent / "python.exe"

    def run() -> None:
        cmd = [str(exe), "-m", "pip", "install", "-q", "-U", "--disable-pip-version-check",
               "--no-warn-script-location", "yt-dlp[default,deno]"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=600, creationflags=NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired) as e:
            print(f"yt-dlp の更新に失敗しました: {e}")
            return
        if res.returncode == 0:
            stamp.touch()
        else:
            print(f"yt-dlp の更新に失敗しました:\n{res.stderr[-2000:]}")

    threading.Thread(target=run, daemon=True).start()


def find_running() -> str | None:
    """すでに起動している画面があれば、その URL を返す。"""
    info = read_json(SUPPORT_DIR / "server.json", {})
    port = info.get("port") if isinstance(info, dict) else None
    if not isinstance(port, int):
        return None
    url = f"http://127.0.0.1:{port}/"
    try:
        with urllib.request.urlopen(url + "api/ping", timeout=1.5) as res:
            if json.loads(res.read()).get("app") == "ytdl":
                return url
    except (OSError, ValueError):
        pass
    return None


def serve(out_dir: Path | None, port: int, open_browser: bool) -> None:
    if port == 0 and (running := find_running()):
        print(f"すでに起動しています。画面を開きます: {running}")
        if open_browser:
            webbrowser.open(running)
        return

    app = App(out_dir)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port or PREFERRED_PORT), make_handler(app))
    except OSError:
        if port:
            raise
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    server.daemon_threads = True
    actual = server.server_address[1]
    url = f"http://127.0.0.1:{actual}/"
    write_json(SUPPORT_DIR / "server.json", {"port": actual, "pid": os.getpid()})

    def watchdog() -> None:
        while True:
            time.sleep(1)
            if app.should_exit(time.time()):
                server.shutdown()
                return

    threading.Thread(target=watchdog, daemon=True).start()
    print(f"YouTube ダウンローダーを開きました: {url}")
    print(f"保存先: {app.out_dir}")
    print("ブラウザのタブを閉じると自動で終了します（Ctrl+C でも終了できます）。")
    if open_browser:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        info = read_json(SUPPORT_DIR / "server.json", {})
        if isinstance(info, dict) and info.get("pid") == os.getpid():
            try:
                (SUPPORT_DIR / "server.json").unlink()
            except OSError:
                pass
        print("\n終了しました。")


PAGE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YouTube ダウンローダー</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect x='4' y='12' width='56' height='40' rx='12' fill='%23e5322d'/%3E%3Cpath d='M32 22v16m-7-7 7 7 7-7' stroke='white' stroke-width='5' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E">
<style>
  :root {
    --bg: #f6f5f3; --fg: #1d1c1a; --muted: #6b6864; --line: #e2ded8;
    --card: #ffffff; --soft: #f1efec; --accent: #d93025; --accent-fg: #ffffff;
    --ok: #1e7b45; --err: #b3261e; --bar: #ece9e4; --drop: #fdeceb;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #17161a; --fg: #ece9e4; --muted: #9b968f; --line: #33302f;
      --card: #201f23; --soft: #29272b; --accent: #f06a5f; --accent-fg: #17161a;
      --ok: #6fcf97; --err: #f28b82; --bar: #2d2b2f; --drop: #3a2220;
    }
  }
  * { box-sizing: border-box; }
  html, body { min-height: 100%; }
  body {
    margin: 0; background: var(--bg); color: var(--fg);
    font-family: -apple-system, "Hiragino Sans", "Noto Sans JP", system-ui, sans-serif;
    line-height: 1.6;
  }
  .wrap { max-width: 760px; margin: 0 auto; padding: 32px 16px 64px; }
  header { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 20px; }
  h1 { font-size: 1.35rem; margin: 0; }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 20px; }
  .drop {
    border: 2px dashed var(--line); border-radius: 14px; padding: 18px;
    transition: background .15s, border-color .15s;
  }
  body.dragging .drop { border-color: var(--accent); background: var(--drop); }
  .hint { text-align: center; color: var(--muted); font-size: .9rem; margin: 0 0 12px; }
  .hint b { color: var(--fg); }
  kbd {
    font: inherit; font-size: .8rem; padding: 1px 6px; border-radius: 6px;
    border: 1px solid var(--line); background: var(--soft);
  }
  .urlrow { display: flex; gap: 8px; }
  input[type=text] {
    flex: 1; min-width: 0; font: inherit; padding: 12px 14px; border-radius: 10px;
    border: 1px solid var(--line); background: var(--bg); color: var(--fg);
  }
  input[type=text]:focus, select:focus, button:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
  button {
    font: inherit; font-weight: 700; border: 0; border-radius: 10px; cursor: pointer;
    padding: 12px 20px; background: var(--accent); color: var(--accent-fg); white-space: nowrap;
  }
  button:disabled { opacity: .5; cursor: default; }
  button.ghost {
    background: transparent; color: var(--fg); border: 1px solid var(--line);
    padding: 6px 12px; font-weight: 600; font-size: .85rem;
  }
  button.ghost:hover { background: var(--soft); }
  button.link { background: none; color: var(--muted); padding: 4px 8px; font-weight: 500; font-size: .85rem; }
  button.link:hover { color: var(--fg); }
  .opts { display: flex; flex-wrap: wrap; gap: 12px 20px; align-items: center; margin-top: 18px; }
  .seg { display: inline-flex; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
  .seg input { position: absolute; opacity: 0; pointer-events: none; }
  .seg label { padding: 8px 18px; cursor: pointer; font-weight: 600; user-select: none; }
  .seg input:checked + label { background: var(--accent); color: var(--accent-fg); }
  .seg input:focus-visible + label { outline: 2px solid var(--accent); outline-offset: -2px; }
  select {
    font: inherit; padding: 8px 10px; border-radius: 10px;
    border: 1px solid var(--line); background: var(--bg); color: var(--fg);
  }
  .checks { display: flex; flex-wrap: wrap; gap: 6px 20px; margin-top: 14px; font-size: .9rem; }
  .checks label { display: inline-flex; gap: 6px; align-items: center; cursor: pointer; }
  input[type=checkbox] { width: 16px; height: 16px; accent-color: var(--accent); }
  .folder {
    display: flex; align-items: center; gap: 8px; margin-top: 14px; padding-top: 14px;
    border-top: 1px solid var(--line); font-size: .9rem; flex-wrap: wrap;
  }
  .folder .path { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); }
  .toast { min-height: 1.5em; margin-top: 10px; font-size: .9rem; text-align: center; }
  .toast.err { color: var(--err); } .toast.ok { color: var(--ok); }
  .listhead { display: flex; justify-content: space-between; align-items: center; margin: 28px 0 10px; }
  h2 { font-size: 1rem; margin: 0; }
  .job {
    display: grid; grid-template-columns: 128px 1fr; gap: 14px;
    background: var(--card); border: 1px solid var(--line); border-radius: 14px;
    padding: 12px; margin-bottom: 10px;
  }
  .thumb {
    width: 128px; aspect-ratio: 16 / 9; border-radius: 8px; background: var(--soft);
    object-fit: cover; display: block; position: relative;
  }
  .thumbwrap { position: relative; }
  .dur {
    position: absolute; right: 4px; bottom: 4px; font-size: .7rem; font-weight: 700;
    background: rgba(0,0,0,.75); color: #fff; padding: 0 5px; border-radius: 4px;
  }
  .body { min-width: 0; display: flex; flex-direction: column; }
  .jobhead { display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; }
  .title { font-weight: 600; overflow-wrap: anywhere; line-height: 1.4; }
  .badge {
    font-size: .7rem; font-weight: 700; padding: 1px 8px; border-radius: 999px;
    border: 1px solid var(--line); flex: none; margin-top: 2px;
  }
  .meta { color: var(--muted); font-size: .8rem; overflow-wrap: anywhere; }
  .bar { height: 6px; background: var(--bar); border-radius: 999px; margin-top: 8px; overflow: hidden; }
  .bar > div { height: 100%; background: var(--accent); width: 0; transition: width .4s; }
  .bar.indet > div { width: 30% !important; animation: slide 1.1s ease-in-out infinite; }
  @keyframes slide { from { transform: translateX(-100%); } to { transform: translateX(340%); } }
  .job.done .bar, .job.error .bar, .job.cancelled .bar { display: none; }
  .foot { display: flex; justify-content: space-between; align-items: center; margin-top: auto; padding-top: 6px; gap: 8px; flex-wrap: wrap; }
  .actions { display: flex; gap: 6px; flex-wrap: wrap; }
  .state-ok { color: var(--ok); } .state-err { color: var(--err); }
  .job.cancelled { opacity: .65; }
  details.why { font-size: .75rem; color: var(--muted); }
  details.why summary { cursor: pointer; }
  .empty { color: var(--muted); font-size: .9rem; text-align: center; padding: 24px 0; }
  .note { color: var(--muted); font-size: .75rem; margin-top: 40px; }
  #closed {
    display: none; position: fixed; inset: 0; background: color-mix(in srgb, var(--bg) 92%, transparent);
    align-items: center; justify-content: center; text-align: center; padding: 16px; z-index: 10;
  }
  #closed.show { display: flex; }
  @media (max-width: 560px) {
    .urlrow { flex-wrap: wrap; } .urlrow input { flex-basis: 100%; } .urlrow button { flex: 1; }
    .job { grid-template-columns: 96px 1fr; } .thumb { width: 96px; }
  }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>YouTube ダウンローダー</h1>
    <button class="ghost" id="quit" type="button">終了</button>
  </header>

  <section class="card">
    <form class="drop" id="form">
      <p class="hint">YouTube の URL を <b>コピーして {{PASTE_KEYS}}</b>　または　リンクをここへドラッグ</p>
      <div class="urlrow">
        <input type="text" id="url" placeholder="https://www.youtube.com/watch?v=..." autocomplete="off" spellcheck="false" aria-label="YouTube の URL">
        <button type="button" class="ghost" id="paste">📋 貼り付け</button>
        <button type="submit" id="go">ダウンロード</button>
      </div>
    </form>

    <div class="opts">
      <div class="seg" role="radiogroup" aria-label="保存する形式">
        <input type="radio" name="fmt" id="fmt-mp4" value="mp4"><label for="fmt-mp4">🎬 動画 MP4</label>
        <input type="radio" name="fmt" id="fmt-mp3" value="mp3"><label for="fmt-mp3">🎵 音声 MP3</label>
      </div>
      <label>画質 <select id="quality"></select></label>
    </div>
    <div class="checks">
      <label><input type="checkbox" id="auto_start"> 貼り付けたらすぐダウンロード</label>
      <label><input type="checkbox" id="notify"> 終わったら通知</label>
    </div>
    <div class="folder">
      <span>📁 保存先</span>
      <span class="path" id="outdir" title=""></span>
      <button class="ghost" id="choose" type="button">変更…</button>
      <button class="ghost" id="openfolder" type="button">開く</button>
    </div>
    <div class="toast" id="toast" role="status" aria-live="polite"></div>
  </section>

  <div class="listhead">
    <h2>ダウンロード一覧</h2>
    <button class="link" id="clear" type="button">完了・エラーを一覧から消す</button>
  </div>
  <div id="jobs"><p class="empty">ここにダウンロードした動画が表示されます。</p></div>

  <p class="note">著作権者の許可がある動画や、ご自身の動画など、保存が認められたものにだけ使ってください。</p>
</div>

<div id="closed"><div><h2>アプリは終了しました</h2><p class="meta">もう一度使うときは、アプリを開き直してください。<br>このタブは閉じてかまいません。</p></div></div>

<script>
const TOKEN = "{{TOKEN}}";
const INSTANCE = "{{INSTANCE}}";
const PASTE = "{{PASTE_TEXT}}";
const FILER = "{{FILER}}";
const QUALITIES = {
  mp4: [["best", "最高画質"], ["1080", "1080p まで"], ["720", "720p まで"], ["480", "480p まで（軽量）"]],
  mp3: [["192", "192 kbps（標準）"], ["320", "320 kbps（高音質）"], ["128", "128 kbps（軽量）"]],
};
const STATE = {
  queued: "順番待ち", fetching: "動画情報を確認中…", downloading: "ダウンロード中",
  converting: "変換中…", done: "保存しました", error: "", cancelled: "キャンセルしました",
};
const ACTIVE = ["queued", "fetching", "downloading", "converting"];
const $ = (id) => document.getElementById(id);
let settings = null;
let closed = false;

// ---------- サーバとのやりとり ----------
async function post(path, body = {}) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Token": TOKEN },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (data.error === "reload") { location.reload(); throw new Error(""); }
  if (!res.ok) throw new Error(data.error || "エラーが発生しました。");
  return data;
}

let toastTimer;
function toast(msg, kind = "") {
  const t = $("toast");
  t.textContent = msg; t.className = "toast " + kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.textContent = ""; }, 5000);
}

// ---------- 設定 ----------
function currentFmt() { return document.querySelector("input[name=fmt]:checked")?.value || "mp4"; }

function applySettings(s) {
  settings = s;
  $("fmt-" + s.fmt).checked = true;
  fillQuality();
  $("auto_start").checked = s.auto_start;
  $("notify").checked = s.notify;
  $("outdir").textContent = s.out_dir;
  $("outdir").title = s.out_dir;
}

function fillQuality() {
  const fmt = currentFmt();
  const sel = $("quality");
  sel.innerHTML = "";
  for (const [v, label] of QUALITIES[fmt]) {
    const o = document.createElement("option");
    o.value = v; o.textContent = label; sel.appendChild(o);
  }
  sel.value = settings ? settings["q_" + fmt] : QUALITIES[fmt][0][0];
  sel.previousSibling.textContent = fmt === "mp4" ? "画質 " : "音質 ";
}

async function saveSettings(patch) {
  try { applySettings((await post("/api/settings", patch)).settings); } catch (e) { if (e.message) toast(e.message, "err"); }
}

document.querySelectorAll("input[name=fmt]").forEach((r) =>
  r.addEventListener("change", () => { fillQuality(); saveSettings({ fmt: currentFmt() }); }));
$("quality").addEventListener("change", () => saveSettings({ ["q_" + currentFmt()]: $("quality").value }));
$("auto_start").addEventListener("change", () => saveSettings({ auto_start: $("auto_start").checked }));
$("notify").addEventListener("change", () => saveSettings({ notify: $("notify").checked }));
$("choose").addEventListener("click", async () => {
  $("choose").disabled = true;
  try { applySettings((await post("/api/choose-folder")).settings); } catch (e) { if (e.message) toast(e.message, "err"); }
  $("choose").disabled = false;
});
$("openfolder").addEventListener("click", () => post("/api/open-folder").catch((e) => toast(e.message, "err")));

// ---------- 追加 ----------
async function submit(text) {
  if (!text.trim()) { toast("URL を貼り付けてください。", "err"); $("url").focus(); return; }
  $("go").disabled = true;
  try {
    const r = await post("/api/download", { text, fmt: currentFmt(), quality: $("quality").value });
    $("url").value = "";
    let msg = r.added > 1 ? `${r.added} 本を追加しました。` : r.added ? "ダウンロードを始めます。" : "";
    if (r.skipped) msg += ` ${r.skipped} 本はすでにダウンロード中です。`;
    toast(msg.trim(), "ok");
    refresh();
  } catch (e) {
    if (e.message) toast(e.message, "err");
  } finally {
    $("go").disabled = false;
  }
}

// 貼り付け・ドロップされた文字列を処理する。すぐ始めない設定なら欄に入れるだけ。
// YouTube の URL かどうかはサーバ側で判定する（文章ごと貼っても URL だけ拾う）
function handleText(text) {
  if (!/https?:\/\//.test(text)) { toast("URL が見つかりませんでした。", "err"); return; }
  if (settings?.auto_start) submit(text);
  else { $("url").value = text.trim(); $("url").focus(); }
}

$("form").addEventListener("submit", (e) => { e.preventDefault(); submit($("url").value); });

// ページのどこで ⌘V / Ctrl+V しても受け取る
document.addEventListener("paste", (e) => {
  const text = e.clipboardData?.getData("text") || "";
  const inInput = e.target === $("url");
  if (inInput && !settings?.auto_start) return; // 通常の貼り付け
  if (!inInput && e.target.closest?.("input, select, textarea")) return;
  e.preventDefault();
  handleText(text);
});

$("paste").addEventListener("click", async () => {
  try { handleText(await navigator.clipboard.readText()); }
  catch (_) { toast(`クリップボードを読めませんでした。${PASTE} で貼り付けてください。`, "err"); $("url").focus(); }
});

let dragDepth = 0;
document.addEventListener("dragenter", (e) => { e.preventDefault(); dragDepth++; document.body.classList.add("dragging"); });
document.addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; document.body.classList.remove("dragging"); } });
document.addEventListener("dragover", (e) => e.preventDefault());
document.addEventListener("drop", (e) => {
  e.preventDefault(); dragDepth = 0; document.body.classList.remove("dragging");
  const dt = e.dataTransfer;
  handleText(dt.getData("text/uri-list") || dt.getData("text/plain") || "");
});

// ---------- 一覧 ----------
function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}
function fmtDur(s) {
  if (!s) return "";
  const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, sec = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}
function fmtSize(b) {
  if (!b) return "";
  return b >= 1024 ** 3 ? (b / 1024 ** 3).toFixed(2) + " GB" : (b / 1024 ** 2).toFixed(1) + " MB";
}
function button(label, cls, fn) {
  const b = el("button", cls, label); b.type = "button";
  b.addEventListener("click", () => fn().then(refresh).catch((e) => e.message && toast(e.message, "err")));
  return b;
}

const cards = new Map();
function makeCard(j) {
  const c = { root: el("div", "job") };
  const tw = el("div", "thumbwrap");
  c.img = el("img", "thumb"); c.img.alt = ""; c.img.loading = "lazy";
  c.img.onerror = () => { c.img.style.visibility = "hidden"; };
  c.dur = el("span", "dur"); c.dur.hidden = true;
  tw.append(c.img, c.dur);
  const body = el("div", "body");
  const head = el("div", "jobhead");
  c.title = el("div", "title"); c.badge = el("span", "badge");
  head.append(c.title, c.badge);
  c.sub = el("div", "meta");
  c.bar = el("div", "bar"); c.fill = el("div"); c.bar.appendChild(c.fill);
  c.foot = el("div", "foot");
  c.status = el("div", "meta"); c.actions = el("div", "actions");
  c.foot.append(c.status, c.actions);
  body.append(head, c.sub, c.bar, c.foot);
  c.root.append(tw, body);
  return c;
}

function updateCard(c, j) {
  c.root.className = "job " + j.state;
  if (j.thumbnail && c.img.getAttribute("src") !== j.thumbnail) c.img.src = j.thumbnail;
  c.dur.textContent = fmtDur(j.duration); c.dur.hidden = !j.duration;
  c.title.textContent = j.title || j.url;
  c.badge.textContent = j.fmt.toUpperCase();
  c.sub.textContent = j.state === "done" ? [j.filename, fmtSize(j.size)].filter(Boolean).join("　") : (j.title ? j.url : "");
  c.bar.classList.toggle("indet", j.state === "fetching" || j.state === "converting" || (j.state === "downloading" && !j.percent));
  c.fill.style.width = j.percent + "%";

  c.status.className = "meta" + (j.state === "done" ? " state-ok" : j.state === "error" ? " state-err" : "");
  c.status.textContent = "";
  if (j.state === "downloading") {
    c.status.textContent = [`${STATE.downloading} ${Math.floor(j.percent)}%`, j.speed, j.eta].filter(Boolean).join("　");
  } else if (j.state === "error") {
    c.status.append(el("div", "", j.message));
    if (j.detail) {
      const d = el("details", "why"); d.append(el("summary", "", "くわしく"), el("div", "", j.detail));
      c.status.append(d);
    }
  } else {
    c.status.textContent = (j.state === "done" ? "✓ " : "") + STATE[j.state];
  }

  if (c.actionsFor === j.state) return; // ボタンは状態が変わったときだけ作り直す
  c.actionsFor = j.state;
  c.actions.innerHTML = "";
  if (ACTIVE.includes(j.state)) {
    c.actions.append(button("キャンセル", "ghost", () => post("/api/cancel", { id: j.id })));
  } else if (j.state === "done") {
    c.actions.append(
      button(j.fmt === "mp3" ? "▶︎ 再生" : "▶︎ 再生", "ghost", () => post("/api/open", { id: j.id })),
      button(`${FILER} で表示`, "ghost", () => post("/api/reveal", { id: j.id })),
      button("✕", "link", () => post("/api/remove", { id: j.id })),
    );
  } else {
    c.actions.append(
      button("↻ 再試行", "ghost", () => post("/api/retry", { id: j.id })),
      button("✕", "link", () => post("/api/remove", { id: j.id })),
    );
  }
}

function renderJobs(jobs) {
  const box = $("jobs");
  const ids = new Set(jobs.map((j) => j.id));
  for (const [id, c] of cards) if (!ids.has(id)) { c.root.remove(); cards.delete(id); }
  if (!jobs.length) {
    if (!box.querySelector(".empty")) box.innerHTML = '<p class="empty">ここにダウンロードした動画が表示されます。</p>';
    return;
  }
  box.querySelector(".empty")?.remove();
  jobs.forEach((j, i) => {
    let c = cards.get(j.id);
    if (!c) { c = makeCard(j); cards.set(j.id, c); }
    updateCard(c, j);
    if (box.children[i] !== c.root) box.insertBefore(c.root, box.children[i] || null);
  });
  const active = jobs.filter((j) => ACTIVE.includes(j.state)).length;
  document.title = active ? `(${active}) YouTube ダウンローダー` : "YouTube ダウンローダー";
}

$("clear").addEventListener("click", () => post("/api/clear").then(refresh).catch(() => {}));
$("quit").addEventListener("click", async () => {
  const busy = [...cards.values()].some((c) => ACTIVE.includes(c.actionsFor));
  if (busy && !confirm("ダウンロード中のものがあります。中断して終了しますか？")) return;
  try { await post("/api/quit"); } catch (_) {}
  showClosed();
});

function showClosed() { closed = true; $("closed").classList.add("show"); document.title = "（終了）YouTube ダウンローダー"; }

let failures = 0;
async function refresh() {
  if (closed) return;
  try {
    const res = await fetch("/api/state", { cache: "no-store" });
    const data = await res.json();
    if (data.instance !== INSTANCE) { location.reload(); return; }
    failures = 0;
    if (!settings) applySettings(data.settings);
    renderJobs(data.jobs);
  } catch (_) {
    if (++failures >= 3) showClosed();
  }
}
setInterval(refresh, 1000);
refresh();

// タブを閉じたらアプリも終わらせる（再読み込みなら数秒以内に戻るので終了しない）
addEventListener("pagehide", () => navigator.sendBeacon("/api/bye?t=" + encodeURIComponent(TOKEN), ""));
$("url").focus();
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
            print("\n変換中…", end="", flush=True)
        return
    if d.get("status") == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        done = d.get("downloaded_bytes") or 0
        pct = f"{done * 100 / total:5.1f}%" if total else "   ?  "
        print(f"\rダウンロード中 {pct}", end="", flush=True)
    elif d.get("status") == "finished":
        print(flush=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="YouTube の動画を MP4（動画）か MP3（音声）で保存します。"
        " URL を省略するとブラウザで操作画面を開きます。"
    )
    p.add_argument("url", nargs="*", help="YouTube の URL（複数可）")
    p.add_argument("--mp3", action="store_true", help="音声だけを MP3 で保存する")
    p.add_argument(
        "-q", "--quality",
        help="MP4: best / 1080 / 720 / 480（既定 best）、MP3: 320 / 192 / 128（既定 192）",
    )
    p.add_argument("-o", "--output", type=Path, help=f"保存先（既定 {DEFAULT_DIR}）")
    p.add_argument("--port", type=int, default=0, help="画面モードのポート番号（既定: 自動）")
    p.add_argument("--no-browser", action="store_true", help="画面モードでブラウザを自動で開かない")
    p.add_argument("--auto-update", action="store_true", help="起動時に yt-dlp を裏で最新にする（1 日 1 回）")
    redirect_output_if_windowless()
    args = p.parse_args(argv)

    if not args.url:
        if args.auto_update and not find_running():
            update_ytdlp_in_background()
        serve(args.output, args.port, not args.no_browser)
        return 0

    fmt = "mp3" if args.mp3 else "mp4"
    quality = args.quality or ("192" if args.mp3 else "best")
    out_dir = (args.output or DEFAULT_DIR).expanduser()
    failed = 0
    for url in args.url:
        try:
            path = download(url, fmt, quality, out_dir, cli_hook,
                            lambda info: print(f"▶ {info.get('title') or url}"))
            print(f"保存しました: {path}")
        except DownloadError as e:
            failed += 1
            print(f"\n{e}" + (f"\n  ({e.detail})" if e.detail else ""), file=sys.stderr)
        except KeyboardInterrupt:
            print("\n中断しました。", file=sys.stderr)
            return 130
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
