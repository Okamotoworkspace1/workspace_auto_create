"""ブラウザから使う簡易 UI。

標準ライブラリの :mod:`http.server` だけで動く。台本を貼って再生ボタンを押す、
という日常の使い方を CLI より速く回すためのもの。外部に公開する前提は無いので
既定は ``127.0.0.1`` にしか bind しない。
"""

from __future__ import annotations

import json
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import consent as consent_mod
from .config import Config
from .cost import CHARS_PER_SECOND
from .engines.base import available_engines, get_engine
from .errors import JigoeError
from .lexicon import Lexicon, find_risky_terms
from .pipeline import Cache, CACHE_DIRNAME, synthesize
from .script import parse_script

MAX_BODY = 4 * 1024 * 1024  # 台本の上限（4MB）


def _page(config: Config, engines: list[tuple[str, str]]) -> bytes:
    options = "\n".join(
        f'<option value="{name}"{" selected" if name == config.voice.engine else ""}>'
        f"{name} — {desc}</option>"
        for name, desc in engines
    )
    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>jigoe — 自声読み上げ</title>
<style>
  :root {{
    --bg: #fbfaf8; --fg: #1d1c1a; --muted: #6b6864; --line: #e2ded8;
    --card: #ffffff; --accent: #b4522d; --warn: #8a5a00; --warn-bg: #fdf6e3;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg: #17161a; --fg: #ece9e4; --muted: #9b968f; --line: #33302f;
      --card: #201f23; --accent: #e08a63; --warn: #e0b060; --warn-bg: #2a2317;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--fg);
    font-family: "Hiragino Sans", "Noto Sans JP", system-ui, sans-serif;
    line-height: 1.7;
  }}
  .wrap {{ max-width: 860px; margin: 0 auto; padding: 32px 16px 64px; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 4px; letter-spacing: .02em; }}
  .sub {{ color: var(--muted); font-size: .85rem; margin: 0 0 24px; }}
  .card {{
    background: var(--card); border: 1px solid var(--line);
    border-radius: 10px; padding: 18px; margin-bottom: 16px;
  }}
  label {{ display: block; font-size: .8rem; color: var(--muted); margin-bottom: 6px; }}
  textarea, select, input {{
    width: 100%; font: inherit; color: inherit; background: transparent;
    border: 1px solid var(--line); border-radius: 6px; padding: 10px;
  }}
  textarea {{ min-height: 240px; resize: vertical; font-size: .95rem; line-height: 1.8; }}
  .row {{ display: flex; gap: 12px; flex-wrap: wrap; }}
  .row > div {{ flex: 1 1 180px; }}
  button {{
    font: inherit; border: 0; border-radius: 6px; padding: 10px 20px;
    background: var(--accent); color: #fff; cursor: pointer;
  }}
  button.ghost {{ background: transparent; color: var(--fg); border: 1px solid var(--line); }}
  button:disabled {{ opacity: .5; cursor: progress; }}
  .actions {{ display: flex; gap: 10px; align-items: center; margin-top: 14px; flex-wrap: wrap; }}
  .stat {{ display: flex; gap: 20px; flex-wrap: wrap; font-size: .85rem; color: var(--muted); }}
  .stat b {{ color: var(--fg); font-weight: 600; }}
  .warn {{ background: var(--warn-bg); border-color: var(--warn); }}
  .warn h2 {{ color: var(--warn); font-size: .9rem; margin: 0 0 8px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .85rem; }}
  td {{ padding: 4px 8px 4px 0; border-bottom: 1px solid var(--line); vertical-align: top; }}
  audio {{ width: 100%; margin-top: 12px; }}
  .hint {{ font-size: .78rem; color: var(--muted); margin-top: 8px; }}
  code {{ background: rgba(128,128,128,.15); padding: 1px 5px; border-radius: 4px; font-size: .85em; }}
  .err {{ color: #c0392b; font-size: .85rem; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>jigoe — 自声読み上げ</h1>
  <p class="sub">{config.project_name} ／ 合成できるのは自分の声だけです</p>

  <div class="card">
    <label for="script">台本</label>
    <textarea id="script" spellcheck="false"># 見出しはチャプターになります

ここに台本を貼り付けます。[[0.6]]二重角括弧の中は無音の秒数です。

@pause 1.0

@speed 1.05 のように話速も行単位で指定できます。</textarea>
    <div class="row" style="margin-top:14px">
      <div>
        <label for="engine">エンジン</label>
        <select id="engine">{options}</select>
      </div>
      <div>
        <label for="speed">話速（{config.voice.speed} が既定）</label>
        <input id="speed" type="number" step="0.05" min="0.5" max="2" value="{config.voice.speed}">
      </div>
    </div>
    <div class="actions">
      <button class="ghost" id="check">チェックのみ</button>
      <button id="speak">読み上げる</button>
      <span id="status" class="hint"></span>
    </div>
    <p class="hint">
      チェックは合成せずに誤読候補と尺だけを出します。クラウド API のクレジットを使う前に一度通すと安全です。
    </p>
  </div>

  <div class="card" id="result" hidden>
    <div class="stat" id="stats"></div>
    <audio id="player" controls></audio>
    <p class="hint" id="download"></p>
  </div>

  <div class="card warn" id="risks" hidden>
    <h2>誤読を確認したい箇所</h2>
    <table id="riskTable"></table>
    <p class="hint">
      読みを固定するには読み辞書（<code>表記&lt;TAB&gt;読み</code>）に追加して
      <code>jigoe.toml</code> の <code>[lexicon] paths</code> に並べます。
    </p>
  </div>
</div>
<script>
const $ = (id) => document.getElementById(id);
let lastUrl = null;

function payload() {{
  return {{
    script: $("script").value,
    engine: $("engine").value,
    speed: parseFloat($("speed").value) || 1.0,
  }};
}}

function showRisks(risks) {{
  const box = $("risks"), table = $("riskTable");
  if (!risks || risks.length === 0) {{ box.hidden = true; return; }}
  table.innerHTML = risks.map(r =>
    `<tr><td><b>${{r.term}}</b></td><td>×${{r.count}}</td><td>${{r.advice}}</td></tr>`
  ).join("");
  box.hidden = false;
}}

function showStats(s) {{
  $("stats").innerHTML = Object.entries(s)
    .map(([k, v]) => `<span>${{k}} <b>${{v}}</b></span>`).join("");
  $("result").hidden = false;
}}

async function run(path, busyLabel) {{
  const buttons = [$("check"), $("speak")];
  buttons.forEach(b => b.disabled = true);
  $("status").textContent = busyLabel;
  try {{
    const res = await fetch(path, {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(payload()),
    }});
    if (!res.ok) {{
      const detail = await res.json().catch(() => ({{ error: res.statusText }}));
      throw new Error(detail.error || res.statusText);
    }}
    return res;
  }} finally {{
    buttons.forEach(b => b.disabled = false);
    $("status").textContent = "";
  }}
}}

$("check").onclick = async () => {{
  try {{
    const data = await (await run("/api/check", "解析中…")).json();
    $("player").removeAttribute("src");
    $("download").textContent = "";
    showStats({{
      "文字数": data.chars.toLocaleString(),
      "推定尺": data.estimated_minutes + " 分",
      "章": data.chapters,
      "要確認": data.risks.length,
    }});
    showRisks(data.risks);
  }} catch (e) {{ $("status").innerHTML = `<span class="err">${{e.message}}</span>`; }}
}};

$("speak").onclick = async () => {{
  try {{
    const res = await run("/api/speak", "合成中… 長い台本は時間がかかります");
    const summary = JSON.parse(decodeURIComponent(res.headers.get("X-Jigoe-Summary") || "%7B%7D"));
    const blob = await res.blob();
    if (lastUrl) URL.revokeObjectURL(lastUrl);
    lastUrl = URL.createObjectURL(blob);
    $("player").src = lastUrl;
    $("download").innerHTML = `<a href="${{lastUrl}}" download="narration.wav">narration.wav をダウンロード</a>`;
    showStats({{
      "尺": summary.duration_display,
      "文字数": (summary.char_count || 0).toLocaleString(),
      "合成": summary.synthesized,
      "再利用": summary.from_cache,
      "ピーク": summary.peak_dbfs + " dBFS",
    }});
    showRisks(summary.risky_terms);
  }} catch (e) {{ $("status").innerHTML = `<span class="err">${{e.message}}</span>`; }}
}};
</script>
</body>
</html>
"""
    return html.encode("utf-8")


class _Handler(BaseHTTPRequestHandler):
    server_version = "jigoe"
    config: Config
    lexicon: Lexicon

    def log_message(self, fmt: str, *args) -> None:  # 既定のノイズを抑える
        pass

    # --- 送信ヘルパ -----------------------------------------------------

    def _send(self, status: int, body: bytes, content_type: str, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise JigoeError("台本が大きすぎます")
        return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

    # --- ルーティング ---------------------------------------------------

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            engines = [(n, c.description) for n, c in sorted(available_engines().items())]
            self._send(200, _page(self.config, engines), "text/html; charset=utf-8")
        elif self.path == "/api/engines":
            self._json(200, {
                "engines": [
                    {"name": n, "description": c.description, "clones_voice": c.clones_voice}
                    for n, c in sorted(available_engines().items())
                ]
            })
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        try:
            body = self._read_json()
            if self.path == "/api/check":
                self._json(200, self._check(body))
            elif self.path == "/api/speak":
                wav, summary = self._speak(body)
                self._send(
                    200, wav, "audio/wav",
                    {"X-Jigoe-Summary": urllib.parse.quote(json.dumps(summary, ensure_ascii=False))},
                )
            else:
                self._json(404, {"error": "not found"})
        except JigoeError as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:  # 予期しないものも UI に返す
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

    # --- 処理本体 -------------------------------------------------------

    def _config_for(self, body: dict) -> Config:
        return self.config.with_overrides(
            engine=body.get("engine") or None,
            speed=float(body["speed"]) if body.get("speed") else None,
        )

    def _check(self, body: dict) -> dict:
        cfg = self._config_for(body)
        script = parse_script(body.get("script", ""), cfg.audio)
        text = script.text()
        risks = find_risky_terms(text, self.lexicon)
        seconds = (
            script.char_count() / CHARS_PER_SECOND / max(0.1, cfg.voice.speed)
            + script.pause_seconds()
            + cfg.audio.lead_silence
            + cfg.audio.tail_silence
        )
        return {
            "chars": script.char_count(),
            "segments": len(script.segments),
            "chapters": len(script.chapters),
            "estimated_minutes": round(seconds / 60, 1),
            "risks": [
                {"term": r.term, "kind": r.kind, "count": r.count, "advice": r.advice}
                for r in risks
            ],
        }

    def _speak(self, body: dict) -> tuple[bytes, dict]:
        cfg = self._config_for(body)
        consent_mod.ensure_consent(cfg.voice.engine)
        script = parse_script(body.get("script", ""), cfg.audio)
        engine = get_engine(cfg.voice.engine, cfg.engine_options(), cfg.voice)
        result = synthesize(
            script, cfg, engine, self.lexicon,
            cache=Cache(cfg.out_dir / CACHE_DIRNAME, enabled=True),
        )
        return result.pcm.to_wav_bytes(), result.summary()


def make_server(
    config: Config,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    lexicon_paths: list[str] | None = None,
) -> ThreadingHTTPServer:
    """UI のサーバーを組み立てる（起動はしない）。

    ``port=0`` を渡すと空きポートが自動で割り当てられ、
    ``server.server_address[1]`` で実際のポートが分かる。
    """
    paths = list(config.lexicon_paths) + [Path(p) for p in (lexicon_paths or [])]
    handler = type("Handler", (_Handler,), {"config": config, "lexicon": Lexicon.load_all(paths)})
    return ThreadingHTTPServer((host, port), handler)


def serve(
    config: Config,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    lexicon_paths: list[str] | None = None,
    open_browser: bool = True,
) -> None:
    """簡易 UI を起動する（Ctrl-C で終了）。"""
    server = make_server(config, host=host, port=port, lexicon_paths=lexicon_paths)
    url = f"http://{host}:{server.server_address[1]}/"
    print(f"jigoe UI: {url}  （Ctrl-C で終了）")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n終了しました")
    finally:
        server.server_close()
