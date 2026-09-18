"""VOICEVOX 互換 API のエンジン（AivisSpeech / VOICEVOX）。

どちらも ``/audio_query`` → ``/synthesis`` の 2 段構えで、パラメータ名も共通。
AivisSpeech はリサーチで「日本語 × 無料 × 自分の声」の本命とされたもので、
中身は Style-Bert-VITS2。自作の ``.aivmx`` モデルを読み込ませれば、
ここに自分の声の話者 ID が出てくる。
"""

from __future__ import annotations

from ..audio import Pcm
from ..errors import EngineError
from ..http import get_json, post_json, request
from .base import Engine, Voice, register


class VoicevoxLikeEngine(Engine):
    """VOICEVOX 互換エンジンの共通実装。"""

    default_url = "http://127.0.0.1:50021"
    default_speaker = 1
    #: 起動していないときの案内
    launch_hint = "エンジンを起動してから再実行してください"

    def _url(self, path: str) -> str:
        return f"{self.base_url(self.default_url)}{path}"

    def _speaker(self) -> int:
        return int(self.option("speaker", self.default_speaker))

    def voices(self) -> list[Voice]:
        try:
            data = get_json(self._url("/speakers"), label="話者一覧の取得", retries=1)
        except EngineError as exc:
            raise EngineError(f"{self.name} に接続できません（{exc}）。{self.launch_hint}") from exc
        voices: list[Voice] = []
        for speaker in data:
            for style in speaker.get("styles", []):
                voices.append(
                    Voice(
                        id=str(style.get("id")),
                        name=f"{speaker.get('name', '?')} / {style.get('name', '?')}",
                        note=speaker.get("speaker_uuid", ""),
                    )
                )
        return voices

    def synthesize(
        self,
        text: str,
        *,
        speed: float | None = None,
        pitch: float | None = None,
        volume: float | None = None,
        style: str | None = None,
    ) -> Pcm:
        speaker = self._speaker()
        query = post_json(
            self._url("/audio_query"),
            params={"text": text, "speaker": speaker},
            label="audio_query",
        )
        query["speedScale"] = self.resolve("speed", speed, 1.0)
        query["pitchScale"] = self.resolve("pitch", pitch, 0.0)
        query["volumeScale"] = self.resolve("volume", volume, 1.0)
        # 前後の余白はこちら側でポーズとして厳密に管理するので 0 にする
        query["prePhonemeLength"] = 0.0
        query["postPhonemeLength"] = 0.0
        if "outputSamplingRate" in query:
            query["outputSamplingRate"] = int(self.option("sample_rate", query["outputSamplingRate"]))

        raw = request(
            "POST",
            self._url("/synthesis"),
            params={"speaker": speaker},
            json=query,
            headers={"Accept": "audio/wav"},
            label="音声合成",
        )
        return Pcm.from_wav_bytes(raw)


@register
class AivisSpeechEngine(VoicevoxLikeEngine):
    """AivisSpeech Engine（既定ポート 10101）。"""

    name = "aivisspeech"
    clones_voice = True
    description = "AivisSpeech（無料・商用可・自作の .aivmx で自声モデルを読み込める）"
    default_url = "http://127.0.0.1:10101"
    default_speaker = 888753760
    launch_hint = "AivisSpeech を起動し、エンジンが http://127.0.0.1:10101 で待ち受けているか確認してください"


@register
class VoicevoxEngine(VoicevoxLikeEngine):
    """VOICEVOX Engine（既定ポート 50021）。配布キャラクターの音声のみ。"""

    name = "voicevox"
    clones_voice = False
    description = "VOICEVOX（無料・配布キャラクター音声。自声クローンは不可）"
    default_url = "http://127.0.0.1:50021"
    default_speaker = 3
    launch_hint = "VOICEVOX を起動し、エンジンが http://127.0.0.1:50021 で待ち受けているか確認してください"
