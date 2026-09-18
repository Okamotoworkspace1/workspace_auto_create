"""クラウド TTS のコスト試算。

料金表はリサーチ文書（2026 年時点）の数値をそのまま持っている。
サービス側の改定が早い領域なので、**必ず公式で最新を確認すること**。
``--usd-jpy`` で為替は上書きできる（既定 150 円／ドル）。
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_USD_JPY = 150.0

#: 10 分のナレーションに必要な日本語の文字数（リサーチの試算 3,000〜3,600 字）
CHARS_PER_10MIN = 3300

#: 日本語ナレーションのおおよその発話速度（話速 1.0 のとき）
CHARS_PER_SECOND = CHARS_PER_10MIN / 600


@dataclass(frozen=True)
class Plan:
    """料金プラン 1 つ。"""

    service: str
    name: str
    usd_per_month: float
    credits_per_month: int
    commercial: bool
    instant_clone: bool
    professional_clone: bool
    note: str = ""

    def jpy(self, usd_jpy: float = DEFAULT_USD_JPY) -> int:
        return int(round(self.usd_per_month * usd_jpy))


#: ElevenLabs（Multilingual v2 は 1 文字 = 1 クレジット、Flash/Turbo は 0.5）
ELEVENLABS_PLANS = [
    Plan("elevenlabs", "Free", 0, 10_000, False, False, False, "商用不可・クローン不可"),
    Plan("elevenlabs", "Starter", 5, 30_000, True, True, False, "Instant クローンのみ"),
    Plan("elevenlabs", "Creator", 22, 100_000, True, True, True, "自声ナレーションの本命"),
    Plan("elevenlabs", "Pro", 99, 500_000, True, True, True, ""),
    Plan("elevenlabs", "Scale", 330, 2_000_000, True, True, True, ""),
    Plan("elevenlabs", "Business", 1320, 11_000_000, True, True, True, ""),
]

#: Fish Audio（クレジットは文字数基準ではないため、目安の生成分数から換算する）
FISH_PLANS = [
    Plan("fishaudio", "Free", 0, 8_000, False, True, False, "商用不可・1 生成 500 字まで"),
    Plan("fishaudio", "Plus", 11, 250_000, True, True, False, "約 200 分/月・15 秒でクローン"),
    Plan("fishaudio", "Pro", 75, 2_000_000, True, True, False, "約 1,620 分/月"),
    Plan("fishaudio", "Max", 749, 25_000_000, True, True, False, "約 6,250 分/月"),
]

#: ローカル OSS（AivisSpeech / Style-Bert-VITS2 / GPT-SoVITS / VOICEVOX）
LOCAL_PLANS = [
    Plan("local", "AivisSpeech / OSS", 0, 0, True, True, True, "無料・自声モデルは自分が権利者"),
]

SERVICES = {
    "elevenlabs": ELEVENLABS_PLANS,
    "fishaudio": FISH_PLANS,
    "local": LOCAL_PLANS,
}

#: エンジン名 → 料金表を持つサービス名
ENGINE_SERVICE = {
    "elevenlabs": "elevenlabs",
    "fishaudio": "fishaudio",
    "aivisspeech": "local",
    "voicevox": "local",
    "sbv2": "local",
    "gptsovits": "local",
    "mock": "local",
}

#: Fish Audio のクレジット消費（1 分あたり）。Plus 250,000 credit ≒ 200 分 から逆算。
FISH_CREDITS_PER_MINUTE = 1250


@dataclass
class Estimate:
    """1 本あたり・月あたりの試算結果。"""

    service: str
    chars_per_video: int
    videos_per_month: int
    credits_per_video: int
    credits_per_month: int
    recommended: Plan | None
    usd_jpy: float
    #: 全プランについて「足りるか」を並べたもの
    breakdown: list[tuple[Plan, bool]]

    @property
    def monthly_jpy(self) -> int:
        return self.recommended.jpy(self.usd_jpy) if self.recommended else 0

    def lines(self) -> list[str]:
        out = [
            f"サービス       : {self.service}",
            f"1 本の文字数   : {self.chars_per_video:,} 字"
            f"（約 {self.chars_per_video / CHARS_PER_10MIN * 10:.1f} 分相当）",
            f"月の本数       : {self.videos_per_month} 本",
        ]
        if self.service == "local":
            out.append("月コスト       : 0 円（ローカル OSS。電気代のみ）")
            return out
        out += [
            f"1 本のクレジット: {self.credits_per_video:,}",
            f"月のクレジット  : {self.credits_per_month:,}",
        ]
        if self.recommended:
            plan = self.recommended
            out.append(
                f"推奨プラン      : {plan.name} — 月 ${plan.usd_per_month:g}"
                f"（約 {plan.jpy(self.usd_jpy):,} 円）"
                + (f" / {plan.note}" if plan.note else "")
            )
        else:
            out.append("推奨プラン      : 既定の料金表では足りません。上位プランや従量課金を確認してください")
        out.append("")
        out.append("プラン別の可否:")
        for plan, ok in self.breakdown:
            mark = "○" if ok else "×"
            out.append(
                f"  {mark} {plan.name:<10} ${plan.usd_per_month:>6g}"
                f" / {plan.credits_per_month:>10,} credit"
                + (f"  ({plan.note})" if plan.note else "")
            )
        return out


def credits_for(service: str, chars: int, *, model: str = "multilingual") -> int:
    """文字数から必要クレジットを求める。"""
    if service == "elevenlabs":
        per_char = 0.5 if model.lower() in {"flash", "turbo"} else 1.0
        return int(round(chars * per_char))
    if service == "fishaudio":
        minutes = chars / CHARS_PER_10MIN * 10
        return int(round(minutes * FISH_CREDITS_PER_MINUTE))
    return 0


def estimate(
    chars_per_video: int,
    *,
    engine: str = "elevenlabs",
    videos_per_month: int = 8,
    model: str = "multilingual",
    require_professional_clone: bool = True,
    require_commercial: bool = True,
    usd_jpy: float = DEFAULT_USD_JPY,
) -> Estimate:
    """必要クレジットと推奨プランを返す。"""
    service = ENGINE_SERVICE.get(engine, engine)
    plans = SERVICES.get(service)
    if plans is None:
        raise ValueError(f"料金表を持っていないサービスです: {service}")

    per_video = credits_for(service, chars_per_video, model=model)
    per_month = per_video * max(1, videos_per_month)

    breakdown: list[tuple[Plan, bool]] = []
    recommended: Plan | None = None
    for plan in plans:
        ok = plan.credits_per_month >= per_month
        if require_commercial and not plan.commercial:
            ok = False
        if require_professional_clone and service == "elevenlabs" and not plan.professional_clone:
            ok = False
        breakdown.append((plan, ok))
        if ok and recommended is None:
            recommended = plan

    if service == "local":
        recommended = plans[0]

    return Estimate(
        service=service,
        chars_per_video=chars_per_video,
        videos_per_month=videos_per_month,
        credits_per_video=per_video,
        credits_per_month=per_month,
        recommended=recommended,
        usd_jpy=usd_jpy,
        breakdown=breakdown,
    )
