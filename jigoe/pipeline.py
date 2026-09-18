"""台本 → ナレーション音声・字幕・チャプターの生成。

エンジンには「テキスト 1 片 → PCM」しか任せず、ポーズ・音量・連結・
タイムライン作成はすべてここで行う。エンジンを差し替えても、ポーズの尺や
字幕のタイミングが変わらないのはこのため。

同じ文の再合成を避けるキャッシュを持つ。台本の一部を直して作り直すときに、
クラウド API のクレジットを無駄に消費しないための仕組み。
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import __version__
from .audio import Pcm, concat
from .config import Config
from .engines.base import Engine
from .lexicon import Lexicon, Risk, find_risky_terms
from .script import Script, Segment
from .subtitle import Cue, to_srt, to_vtt, to_youtube_chapters

ProgressFn = Callable[[int, int, str], None]

CACHE_DIRNAME = ".jigoe-cache"


@dataclass
class RenderedSegment:
    """1 セグメントの合成結果とタイムライン上の位置。"""

    segment: Segment
    start: float
    end: float
    #: 読み辞書適用後の、実際にエンジンへ渡したテキスト
    spoken_text: str = ""
    cached: bool = False
    pcm: Pcm | None = None


@dataclass
class Result:
    """1 本分の生成結果。"""

    pcm: Pcm
    rendered: list[RenderedSegment]
    chapters: list[tuple[str, float]]
    lexicon_hits: Counter
    risks: list[Risk]
    engine_name: str
    char_count: int
    cached_count: int = 0
    synthesized_count: int = 0
    files: dict[str, Path] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.pcm.duration

    def cues(self) -> list[Cue]:
        """読み上げ部分だけを字幕キューにする。"""
        cues: list[Cue] = []
        for item in self.rendered:
            if not item.segment.is_speech:
                continue
            cues.append(
                Cue(
                    index=len(cues) + 1,
                    start=item.start,
                    end=item.end,
                    text=item.segment.text,
                )
            )
        return cues

    def summary(self) -> dict:
        minutes, seconds = divmod(self.duration, 60)
        return {
            "engine": self.engine_name,
            "duration_seconds": round(self.duration, 3),
            "duration_display": f"{int(minutes)}分{seconds:04.1f}秒",
            "char_count": self.char_count,
            "segments": len(self.rendered),
            "speech_segments": self.synthesized_count + self.cached_count,
            "synthesized": self.synthesized_count,
            "from_cache": self.cached_count,
            "chapters": len(self.chapters),
            "peak_dbfs": round(self.pcm.peak_dbfs(), 2),
            "lexicon_applied": dict(self.lexicon_hits),
            "risky_terms": [
                {"term": r.term, "kind": r.kind, "count": r.count, "advice": r.advice}
                for r in self.risks
            ],
        }


class Cache:
    """合成済み音声のディスクキャッシュ。"""

    def __init__(self, root: Path, enabled: bool = True) -> None:
        self.root = root
        self.enabled = enabled

    @staticmethod
    def key(engine: Engine, text: str, params: dict) -> str:
        payload = json.dumps(
            {
                "engine": engine.name,
                "options": {k: str(v) for k, v in sorted(engine.options.items())},
                "text": text,
                "params": {k: str(v) for k, v in sorted(params.items())},
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]

    def get(self, key: str) -> Pcm | None:
        if not self.enabled:
            return None
        path = self.root / f"{key}.wav"
        if not path.is_file():
            return None
        try:
            return Pcm.load(path)
        except Exception:  # 壊れたキャッシュは無視して作り直す
            return None

    def put(self, key: str, pcm: Pcm) -> None:
        if not self.enabled:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        pcm.save(self.root / f"{key}.wav")

    def clear(self) -> int:
        if not self.root.is_dir():
            return 0
        count = len(list(self.root.glob("*.wav")))
        shutil.rmtree(self.root)
        return count


def synthesize(
    script: Script,
    config: Config,
    engine: Engine,
    lexicon: Lexicon | None = None,
    *,
    cache: Cache | None = None,
    keep_segment_audio: bool = False,
    on_progress: ProgressFn | None = None,
) -> Result:
    """台本を音声化する。"""
    lexicon = lexicon or Lexicon()
    audio_cfg = config.audio
    rate = audio_cfg.sample_rate
    cache = cache if cache is not None else Cache(config.out_dir / CACHE_DIRNAME, enabled=True)

    parts: list[Pcm] = []
    rendered: list[RenderedSegment] = []
    lexicon_hits: Counter = Counter()
    cursor = 0.0
    cached_count = 0
    synthesized_count = 0

    def append(pcm: Pcm) -> tuple[float, float]:
        nonlocal cursor
        pcm = pcm.conform(rate, 1)
        start = cursor
        parts.append(pcm)
        cursor += pcm.duration
        return start, cursor

    if audio_cfg.lead_silence > 0:
        append(Pcm.silence(audio_cfg.lead_silence, rate))

    total = len(script.segments)
    for i, segment in enumerate(script.segments, start=1):
        if not segment.is_speech:
            start, end = append(Pcm.silence(segment.seconds, rate))
            rendered.append(RenderedSegment(segment=segment, start=start, end=end))
            continue

        spoken, hits = lexicon.apply(segment.text)
        lexicon_hits.update(hits)

        # キャッシュキーには「解決後」の値を入れる。設定ファイルの [voice] を
        # 変えたのに古い音声が再利用される、という事故を防ぐため。
        params = {
            "speed": engine.resolve("speed", segment.speed, 1.0),
            "pitch": engine.resolve("pitch", segment.pitch, 0.0),
            "volume": engine.resolve("volume", segment.volume, 1.0),
            "style": segment.style or engine.voice.style or config.voice.style,
        }
        key = Cache.key(engine, spoken, params)
        pcm = cache.get(key)
        from_cache = pcm is not None
        if pcm is None:
            if on_progress:
                on_progress(i, total, segment.text)
            # 行単位の指定だけを渡す。None の場合の解決はエンジン側
            # （Engine.resolve）が設定ファイルの [voice] を見て行う。
            pcm = engine.synthesize(
                spoken,
                speed=segment.speed,
                pitch=segment.pitch,
                volume=segment.volume,
                style=params["style"],
            )
            pcm = pcm.conform(rate, 1)
            cache.put(key, pcm)
            synthesized_count += 1
        else:
            cached_count += 1
            if on_progress:
                on_progress(i, total, f"(キャッシュ) {segment.text}")

        start, end = append(pcm)
        rendered.append(
            RenderedSegment(
                segment=segment,
                start=start,
                end=end,
                spoken_text=spoken,
                cached=from_cache,
                pcm=pcm if keep_segment_audio else None,
            )
        )

    if audio_cfg.tail_silence > 0:
        append(Pcm.silence(audio_cfg.tail_silence, rate))

    full = concat(parts, rate, 1).normalize(audio_cfg.peak_dbfs)

    chapters: list[tuple[str, float]] = []
    for chapter in script.chapters:
        # その章以降で最初に音が出る位置を章の開始とする
        start = next(
            (r.start for r in rendered[chapter.segment_index :] if r.segment.is_speech),
            0.0,
        )
        chapters.append((chapter.title, start))

    return Result(
        pcm=full,
        rendered=rendered,
        chapters=chapters,
        lexicon_hits=lexicon_hits,
        risks=find_risky_terms(script.text(), lexicon),
        engine_name=engine.name,
        char_count=script.char_count(),
        cached_count=cached_count,
        synthesized_count=synthesized_count,
    )


def write_outputs(
    result: Result,
    out_dir: Path,
    *,
    basename: str = "narration",
    write_segments: bool = False,
) -> dict[str, Path]:
    """音声・字幕・チャプター・レポートを書き出す。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}

    files["wav"] = result.pcm.save(out_dir / f"{basename}.wav")

    cues = result.cues()
    files["srt"] = out_dir / f"{basename}.srt"
    files["srt"].write_text(to_srt(cues), encoding="utf-8")
    files["vtt"] = out_dir / f"{basename}.vtt"
    files["vtt"].write_text(to_vtt(cues), encoding="utf-8")

    if result.chapters:
        files["chapters"] = out_dir / f"{basename}.chapters.txt"
        files["chapters"].write_text(to_youtube_chapters(result.chapters), encoding="utf-8")

    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "jigoe_version": __version__,
        **result.summary(),
        "timeline": [
            {
                "kind": r.segment.kind,
                "start": round(r.start, 3),
                "end": round(r.end, 3),
                "line": r.segment.line_no,
                "chapter": r.segment.chapter,
                "text": r.segment.text,
                "spoken": r.spoken_text if r.spoken_text != r.segment.text else None,
                "cached": r.cached,
            }
            for r in result.rendered
        ],
    }
    files["report"] = out_dir / f"{basename}.report.json"
    files["report"].write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if write_segments:
        seg_dir = out_dir / f"{basename}_lines"
        seg_dir.mkdir(parents=True, exist_ok=True)
        n = 0
        for item in result.rendered:
            if item.pcm is None:
                continue
            n += 1
            item.pcm.save(seg_dir / f"{n:04d}.wav")
        files["segments"] = seg_dir

    result.files = files
    return files
