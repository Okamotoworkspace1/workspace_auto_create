"""コマンドラインインターフェース。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, consent as consent_mod
from .config import CONFIG_FILENAME, Config, load_config, write_template
from .cost import CHARS_PER_SECOND, DEFAULT_USD_JPY, ENGINE_SERVICE, estimate
from .engines.base import available_engines, get_engine
from .errors import JigoeError
from .lexicon import Entry, Lexicon, find_risky_terms
from .pipeline import Cache, CACHE_DIRNAME, synthesize, write_outputs
from .script import load_script, parse_script


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def _build_config(args: argparse.Namespace) -> Config:
    cfg = load_config(getattr(args, "config", None))
    return cfg.with_overrides(
        engine=getattr(args, "engine", None),
        speed=getattr(args, "speed", None),
        pitch=getattr(args, "pitch", None),
        volume=getattr(args, "volume", None),
        out_dir=Path(args.out) if getattr(args, "out", None) else None,
    )


def _build_lexicon(cfg: Config, extra: list[str] | None) -> Lexicon:
    paths = list(cfg.lexicon_paths)
    paths += [Path(p) for p in (extra or [])]
    return Lexicon.load_all(paths)


def _prepare_engine(cfg: Config, args: argparse.Namespace):
    name = cfg.voice.engine
    consent_mod.ensure_consent(name, assume_yes=getattr(args, "i_own_this_voice", False))
    return get_engine(name, cfg.engine_options(name), cfg.voice)


# --- 各コマンド ---------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.directory)
    config_path = target / CONFIG_FILENAME
    write_template(config_path, name=args.name, engine=args.engine)

    lexicon_path = target / "lexicon" / "names.tsv"
    if not lexicon_path.exists():
        lexicon_path.parent.mkdir(parents=True, exist_ok=True)
        lexicon_path.write_text(
            "# 表記\t読み\tメモ\n"
            "# 固有名詞の読みをここで固定する。誤読チェックの対象からも外れる。\n"
            "レブロン・ジェームズ\tレブロンジェームズ\t\n"
            "NBA\tエヌビーエー\t\n",
            encoding="utf-8",
        )

    script_path = target / "scripts" / "sample.txt"
    if not script_path.exists():
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(SAMPLE_SCRIPT, encoding="utf-8")

    print(f"作成しました: {config_path}")
    print(f"            : {lexicon_path}")
    print(f"            : {script_path}")
    print()
    print("次の手順:")
    print(f"  1. {config_path} の [engines.*] に使うエンジンの設定を書く")
    print("  2. jigoe doctor           # エンジンに繋がるか確認")
    print(f"  3. jigoe check {script_path}   # 誤読チェックと尺の見積り")
    print(f"  4. jigoe speak {script_path}   # 音声・字幕・チャプターを生成")
    return 0


def cmd_engines(args: argparse.Namespace) -> int:
    print(f"{'エンジン':<14} {'クローン':<8} 説明")
    print("-" * 78)
    for name, cls in sorted(available_engines().items()):
        mark = "要同意" if cls.clones_voice else "-"
        print(f"{name:<14} {mark:<8} {cls.description}")
    return 0


def cmd_voices(args: argparse.Namespace) -> int:
    cfg = _build_config(args)
    engine = _prepare_engine(cfg, args)
    voices = engine.voices()
    if not voices:
        print(f"{engine.name}: 話者一覧を取得できるエンジンではありません")
        return 0
    print(f"{engine.name} の話者 ({len(voices)} 件)")
    print("-" * 78)
    for voice in voices:
        print(f"{voice.id:<24} {voice.name}" + (f"   [{voice.note}]" if voice.note else ""))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = _build_config(args)
    print(f"設定ファイル : {cfg.source or '(未使用・既定値で動作)'}")
    print(f"エンジン     : {cfg.voice.engine}")
    print(f"出力先       : {cfg.out_dir}")

    record = consent_mod.load_consent()
    if consent_mod.env_override():
        print(f"自声宣言     : 環境変数 {consent_mod.ENV_OVERRIDE} で同意済み扱い")
    elif record:
        print(f"自声宣言     : 同意済み ({record.accepted_at})")
    elif consent_mod.requires_consent(cfg.voice.engine):
        print("自声宣言     : 未登録 → `jigoe consent` が必要です")
    else:
        print("自声宣言     : このエンジンには不要")

    lexicon = _build_lexicon(cfg, args.lexicon)
    print(f"読み辞書     : {len(lexicon)} 語")

    engine = _prepare_engine(cfg, args)
    print(engine.health())
    return 0


def cmd_consent(args: argparse.Namespace) -> int:
    if args.revoke:
        print("同意記録を削除しました" if consent_mod.revoke_consent() else "同意記録はありません")
        return 0
    record = consent_mod.load_consent()
    if args.status:
        print(f"同意済み: {record.accepted_at}" if record else "未同意")
        return 0 if record else 1
    if record and not args.force:
        print(f"すでに同意済みです ({record.accepted_at})。記録場所: {consent_mod.consent_path()}")
        return 0

    print(consent_mod.DECLARATION)
    if not args.yes:
        if not sys.stdin.isatty():
            _err("対話端末ではありません。--yes を付けて実行してください。")
            return 1
        answer = input("上記に同意しますか？ [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            print("同意しませんでした。クローン系エンジンは使用できません。")
            return 1
    record = consent_mod.record_consent(note=args.note or "")
    print(f"同意を記録しました: {consent_mod.consent_path()}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    cfg = _build_config(args)
    script = load_script(args.script, cfg.audio, speak_headings=args.speak_headings)
    lexicon = _build_lexicon(cfg, args.lexicon)

    chars = script.char_count()
    speech = len(script.speech_segments)
    pause = script.pause_seconds()
    est_seconds = (
        chars / CHARS_PER_SECOND / max(0.1, cfg.voice.speed)
        + pause
        + cfg.audio.lead_silence
        + cfg.audio.tail_silence
    )

    print(f"台本         : {script.source}")
    print(f"読み上げ文字数: {chars:,} 字")
    print(f"セグメント   : 読み上げ {speech} / ポーズ {len(script.segments) - speech}")
    print(f"ポーズ合計   : {pause:.1f} 秒")
    print(f"推定尺       : 約 {est_seconds / 60:.1f} 分（話速 {cfg.voice.speed} で概算）")
    print(f"章           : {len(script.chapters)}")
    for chapter in script.chapters:
        print(f"  - {chapter.title}")

    text = script.text()
    _, hits = lexicon.apply(text)
    print(f"\n読み辞書     : {len(lexicon)} 語（うち今回適用 {len(hits)} 語）")
    for surface, count in hits.most_common(10):
        print(f"  ✓ {surface} × {count}")

    risks = find_risky_terms(text, lexicon)
    print(f"\n誤読チェック : 要確認 {len(risks)} 件")
    if risks:
        print("  （固有名詞とスコアの読みは、AI に任せず人が確認すべき箇所）")
        for risk in risks[: args.limit]:
            print(f"  ! {risk.term:<22} ×{risk.count:<3} {risk.kind:<9} {risk.advice}")
        if len(risks) > args.limit:
            print(f"  … 他 {len(risks) - args.limit} 件（--limit で表示数を変更）")
        print("\n  読み辞書の雛形を作る: jigoe lexicon scan " + str(args.script))

    service = ENGINE_SERVICE.get(cfg.voice.engine, cfg.voice.engine)
    if service != "local":
        print()
        for line in estimate(
            chars, engine=cfg.voice.engine, videos_per_month=args.videos, usd_jpy=args.usd_jpy
        ).lines()[:6]:
            print(line)

    if args.strict and risks:
        _err(f"\n--strict: 未確認の誤読候補が {len(risks)} 件あります")
        return 2
    return 0


def cmd_speak(args: argparse.Namespace) -> int:
    cfg = _build_config(args)
    script = load_script(args.script, cfg.audio, speak_headings=args.speak_headings)
    lexicon = _build_lexicon(cfg, args.lexicon)
    engine = _prepare_engine(cfg, args)

    risks = find_risky_terms(script.text(), lexicon)
    if args.strict and risks:
        _err(f"--strict: 未確認の誤読候補が {len(risks)} 件あります。`jigoe check` で確認してください。")
        return 2

    cache = Cache(cfg.out_dir / CACHE_DIRNAME, enabled=not args.no_cache)

    def progress(i: int, total: int, text: str) -> None:
        if not args.quiet:
            preview = text if len(text) <= 32 else text[:31] + "…"
            print(f"[{i:>4}/{total}] {preview}", file=sys.stderr)

    result = synthesize(
        script,
        cfg,
        engine,
        lexicon,
        cache=cache,
        keep_segment_audio=args.segments,
        on_progress=progress,
    )
    basename = args.basename or Path(args.script).stem
    files = write_outputs(result, cfg.out_dir, basename=basename, write_segments=args.segments)

    summary = result.summary()
    print()
    print(f"エンジン     : {summary['engine']}")
    print(f"尺           : {summary['duration_display']}")
    print(f"文字数       : {summary['char_count']:,} 字")
    print(f"合成 / 再利用: {summary['synthesized']} / {summary['from_cache']} セグメント")
    print(f"ピーク       : {summary['peak_dbfs']} dBFS")
    if risks:
        print(f"誤読要確認   : {len(risks)} 件（jigoe check で一覧）")
    print()
    for label, path in files.items():
        print(f"{label:<9}: {path}")
    return 0


def cmd_say(args: argparse.Namespace) -> int:
    cfg = _build_config(args)
    script = parse_script(args.text, cfg.audio)
    lexicon = _build_lexicon(cfg, args.lexicon)
    engine = _prepare_engine(cfg, args)
    result = synthesize(script, cfg, engine, lexicon, cache=Cache(Path(), enabled=False))
    out = Path(args.output)
    result.pcm.save(out)
    print(f"{out}（{result.duration:.2f} 秒）")
    return 0


def cmd_cost(args: argparse.Namespace) -> int:
    cfg = _build_config(args)
    if args.script:
        chars = load_script(args.script, cfg.audio).char_count()
    else:
        chars = args.chars
    report = estimate(
        chars,
        engine=cfg.voice.engine,
        videos_per_month=args.videos,
        model=args.model,
        require_professional_clone=not args.instant_clone_ok,
        usd_jpy=args.usd_jpy,
    )
    for line in report.lines():
        print(line)
    print()
    print("※ 料金は改定が多い領域です。契約前に必ず公式サイトで最新を確認してください。")
    return 0


def cmd_lexicon(args: argparse.Namespace) -> int:
    cfg = _build_config(args)
    lexicon = _build_lexicon(cfg, args.lexicon)

    if args.action == "list":
        print(f"# {len(lexicon)} 語")
        print(lexicon.to_tsv(), end="")
        return 0

    if args.action == "scan":
        script = load_script(args.script, cfg.audio)
        risks = find_risky_terms(script.text(), lexicon)
        rows = ["# 表記\t読み\tメモ  ← 読みを埋めてから lexicon.paths に追加する"]
        for risk in risks:
            rows.append(f"{risk.term}\t\t{risk.kind}: {risk.advice}")
        output = "\n".join(rows) + "\n"
        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
            print(f"{args.output} に {len(risks)} 件を書き出しました。読みの列を埋めてください。")
        else:
            print(output, end="")
        return 0

    if args.action == "add":
        if not cfg.lexicon_paths:
            _err("追記先がありません。jigoe.toml の [lexicon] paths を設定してください。")
            return 1
        target = cfg.lexicon_paths[0]
        existing = Lexicon.load(target) if target.is_file() else Lexicon()
        existing.add(Entry(surface=args.surface, reading=args.reading, note=args.note or ""))
        target.write_text(existing.to_tsv(), encoding="utf-8")
        print(f"{target} に追加しました: {args.surface} → {args.reading}")
        return 0

    _err(f"未知の操作です: {args.action}")
    return 1


def cmd_cache(args: argparse.Namespace) -> int:
    cfg = _build_config(args)
    cache = Cache(cfg.out_dir / CACHE_DIRNAME)
    if args.action == "clear":
        print(f"{cache.clear()} 件のキャッシュを削除しました: {cache.root}")
    else:
        count = len(list(cache.root.glob("*.wav"))) if cache.root.is_dir() else 0
        print(f"{cache.root}: {count} 件")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .web import serve

    cfg = _build_config(args)
    serve(cfg, host=args.host, port=args.port, lexicon_paths=args.lexicon or [], open_browser=not args.no_browser)
    return 0


SAMPLE_SCRIPT = """\
// jigoe のサンプル台本
// 「#」で始まる行はチャプター、「//」はコメント、「[[0.5]]」は行内の無音（秒）

# オープニング

@speed 1.0
NBAの歴史には、記録よりも語り継がれた選手がいます。[[0.6]]今日はそのひとりの話です。

# 本編

彼のキャリア平均は、25.3得点。[[0.4]]けれど数字よりも、その試合運びが人々の記憶に残りました。

@pause 1.0

# まとめ

記録は塗り替えられます。[[0.5]]語り継がれる理由は、その先にあります。
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jigoe",
        description="自分の声のクローンで台本を読み上げる、動画ナレーション向けツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "他人の声の無断クローンには使えません。初回に `jigoe consent` で\n"
            "「合成に使うのは自分の声である」ことの宣言が必要です。"
        ),
    )
    parser.add_argument("--version", action="version", version=f"jigoe {__version__}")
    parser.add_argument("-c", "--config", help=f"設定ファイル（既定: ./{CONFIG_FILENAME}）")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser, *, engine: bool = True) -> None:
        if engine:
            p.add_argument("-e", "--engine", help="使用するエンジン（設定より優先）")
        p.add_argument("-L", "--lexicon", action="append", help="読み辞書を追加（複数可）")
        p.add_argument(
            "--i-own-this-voice",
            action="store_true",
            help="自声であることの宣言を省略して実行する（非対話環境向け）",
        )

    p = sub.add_parser("init", help="設定ファイルと台本の雛形を作る")
    p.add_argument("directory", nargs="?", default=".", help="作成先（既定: カレント）")
    p.add_argument("--name", default="jigoe project", help="プロジェクト名")
    p.add_argument("--engine", default="mock", help="初期エンジン（既定: mock）")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("engines", help="使えるエンジンの一覧")
    p.set_defaults(func=cmd_engines)

    p = sub.add_parser("voices", help="エンジンが持つ話者の一覧")
    add_common(p)
    p.set_defaults(func=cmd_voices)

    p = sub.add_parser("doctor", help="設定とエンジン接続の確認")
    add_common(p)
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("consent", help="自声であることの宣言を記録する")
    p.add_argument("--yes", action="store_true", help="対話せずに同意する")
    p.add_argument("--status", action="store_true", help="同意状態だけ表示する")
    p.add_argument("--revoke", action="store_true", help="同意記録を削除する")
    p.add_argument("--force", action="store_true", help="同意済みでも記録し直す")
    p.add_argument("--note", help="記録に残すメモ")
    p.set_defaults(func=cmd_consent)

    p = sub.add_parser("check", help="合成せずに台本を検査する（誤読・尺・コスト）")
    p.add_argument("script", help="台本ファイル")
    add_common(p)
    p.add_argument("--speak-headings", action="store_true", help="見出しも読み上げる前提で計算する")
    p.add_argument("--strict", action="store_true", help="誤読候補が残っていたら終了コード 2")
    p.add_argument("--limit", type=int, default=20, help="誤読候補の表示件数")
    p.add_argument("--videos", type=int, default=8, help="月の本数（コスト試算用）")
    p.add_argument("--usd-jpy", type=float, default=DEFAULT_USD_JPY, help="為替レート")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("speak", help="台本から音声・字幕・チャプターを生成する")
    p.add_argument("script", help="台本ファイル")
    add_common(p)
    p.add_argument("-o", "--out", help="出力先ディレクトリ")
    p.add_argument("--basename", help="出力ファイル名の基準（既定: 台本のファイル名）")
    p.add_argument("--speed", type=float, help="話速")
    p.add_argument("--pitch", type=float, help="ピッチ")
    p.add_argument("--volume", type=float, help="音量")
    p.add_argument("--speak-headings", action="store_true", help="見出しも読み上げる")
    p.add_argument("--segments", action="store_true", help="1 文ずつの WAV も書き出す")
    p.add_argument("--no-cache", action="store_true", help="キャッシュを使わず毎回合成する")
    p.add_argument("--strict", action="store_true", help="誤読候補が残っていたら合成しない")
    p.add_argument("-q", "--quiet", action="store_true", help="進捗を出さない")
    p.set_defaults(func=cmd_speak)

    p = sub.add_parser("say", help="短いテキストをその場で読み上げて WAV にする")
    p.add_argument("text", help="読み上げる文字列")
    add_common(p)
    p.add_argument("-o", "--output", default="say.wav", help="出力ファイル")
    p.add_argument("--speed", type=float, help="話速")
    p.add_argument("--pitch", type=float, help="ピッチ")
    p.add_argument("--volume", type=float, help="音量")
    p.set_defaults(func=cmd_say)

    p = sub.add_parser("cost", help="クラウド TTS の月額を試算する")
    p.add_argument("script", nargs="?", help="台本ファイル（省略時は --chars）")
    p.add_argument("-e", "--engine", help="対象エンジン")
    p.add_argument("--chars", type=int, default=3300, help="1 本あたりの文字数（既定: 3,300 ≒ 10 分）")
    p.add_argument("--videos", type=int, default=8, help="月の本数")
    p.add_argument("--model", default="multilingual", help="multilingual | flash | turbo")
    p.add_argument("--instant-clone-ok", action="store_true", help="Instant クローンで良い場合")
    p.add_argument("--usd-jpy", type=float, default=DEFAULT_USD_JPY, help="為替レート")
    p.set_defaults(func=cmd_cost)

    p = sub.add_parser("lexicon", help="読み辞書の操作")
    p.add_argument("action", choices=["list", "scan", "add"], help="list / scan / add")
    p.add_argument("script", nargs="?", help="scan の対象台本")
    add_common(p, engine=False)
    p.add_argument("-o", "--output", help="scan の書き出し先")
    p.add_argument("--surface", help="add: 表記")
    p.add_argument("--reading", help="add: 読み")
    p.add_argument("--note", help="add: メモ")
    p.set_defaults(func=cmd_lexicon)

    p = sub.add_parser("cache", help="合成キャッシュの確認と削除")
    p.add_argument("action", choices=["status", "clear"], default="status", nargs="?")
    p.add_argument("-o", "--out", help="出力先ディレクトリ")
    p.set_defaults(func=cmd_cache)

    p = sub.add_parser("serve", help="ブラウザから使う簡易 UI を起動する")
    add_common(p)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true", help="ブラウザを自動で開かない")
    p.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "lexicon":
        if args.action == "scan" and not args.script:
            parser.error("lexicon scan には台本ファイルが必要です")
        if args.action == "add" and not (args.surface and args.reading):
            parser.error("lexicon add には --surface と --reading が必要です")

    try:
        return args.func(args)
    except JigoeError as exc:
        _err(f"エラー: {exc}")
        return exc.exit_code
    except KeyboardInterrupt:
        _err("中断しました")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
