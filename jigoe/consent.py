"""自声であることの同意ゲート。

ボイスクローンは技術的には誰の声にも使えてしまうが、他人の声を無断で
クローンする行為は主要サービスの規約違反（ElevenLabs は全プランで禁止）であり、
日本ではパブリシティ権・人格権の侵害にもなり得る。YouTube 側でも「なりすまし」
として削除・収益化剥奪の対象になる。

そこで本ツールは、**クローン系エンジンを初めて使う前に一度だけ**、
「合成に使う声は自分自身の声であり、録音・利用の権利を自分が持っている」ことの
宣言を記録する。記録は :func:`consent_path` に JSON で残る。

これは法的な免責ではなく、事故を防ぐための運用上のブレーキ。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import user_config_dir
from .errors import ConsentError

#: 同意を必要とするエンジン（＝任意の声を複製し得るもの）。
#: VOICEVOX のように配布キャラクター音声のみを鳴らすエンジンは対象外。
CLONING_ENGINES = frozenset({"elevenlabs", "fishaudio", "sbv2", "gptsovits", "aivisspeech"})

#: 同意を省略するための環境変数（CI / バッチ用）。
ENV_OVERRIDE = "JIGOE_VOICE_IS_MINE"

DECLARATION = """\
この宣言に同意すると、jigoe はボイスクローン系エンジンでの合成を許可します。

  1. 合成に使う声は自分自身の声であるか、本人から明示的な許諾を得た声である。
  2. 有名人・実況者・配信者など第三者の声を、本人の許諾なくクローンしない。
  3. 生成音声を、実在の人物が実際に発言したかのように見せる用途で使わない。

他人の声の無断クローンは主要サービスの規約違反であり、パブリシティ権・
人格権の侵害、および YouTube のなりすましポリシー違反になり得ます。
"""


@dataclass(frozen=True)
class Consent:
    """記録済みの同意。"""

    accepted_at: str
    note: str = ""

    def to_json(self) -> dict[str, str]:
        return {"accepted_at": self.accepted_at, "note": self.note, "declaration": DECLARATION}


def consent_path() -> Path:
    """同意記録の保存先。"""
    return user_config_dir() / "consent.json"


def load_consent() -> Consent | None:
    """記録済みの同意を読む。無ければ None。"""
    path = consent_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    accepted_at = data.get("accepted_at")
    if not accepted_at:
        return None
    return Consent(accepted_at=accepted_at, note=data.get("note", ""))


def record_consent(note: str = "") -> Consent:
    """同意を記録して返す。"""
    consent = Consent(
        accepted_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        note=note,
    )
    path = consent_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(consent.to_json(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return consent


def revoke_consent() -> bool:
    """同意記録を削除する。削除したら True。"""
    path = consent_path()
    if path.is_file():
        path.unlink()
        return True
    return False


def env_override() -> bool:
    """環境変数による同意済み扱いが有効か。"""
    return os.environ.get(ENV_OVERRIDE, "").strip().lower() in {"1", "true", "yes"}


def requires_consent(engine: str) -> bool:
    """そのエンジンが同意ゲートの対象か。"""
    return engine in CLONING_ENGINES


def ensure_consent(engine: str, *, assume_yes: bool = False) -> None:
    """同意が無ければ :class:`ConsentError` を送出する。

    Parameters
    ----------
    engine:
        これから使うエンジン名。
    assume_yes:
        True なら（``--i-own-this-voice`` 相当）その場で同意を記録する。
    """
    if not requires_consent(engine):
        return
    if env_override():
        return
    if load_consent() is not None:
        return
    if assume_yes:
        record_consent(note=f"--i-own-this-voice ({engine})")
        return
    raise ConsentError(
        "自声であることの宣言が未登録です。`jigoe consent` を実行して同意するか、"
        "`--i-own-this-voice` を付けて実行してください。\n\n" + DECLARATION
    )
