"""jigoe 共通の例外。CLI はこれらを捕捉して 1 行のメッセージで返す。"""

from __future__ import annotations


class JigoeError(Exception):
    """ユーザーに見せて意味のあるエラーの基底クラス。"""

    #: CLI の終了コード
    exit_code = 1


class ConfigError(JigoeError):
    """設定ファイルの不備。"""


class ConsentError(JigoeError):
    """自声であることの同意が未登録、または本人以外の声を指している。"""

    exit_code = 3


class ScriptError(JigoeError):
    """台本の書式エラー。"""


class EngineError(JigoeError):
    """音声合成エンジン側のエラー（接続不可・APIエラー・認証失敗など）。"""

    exit_code = 4


class AudioError(JigoeError):
    """音声データの扱いに関するエラー（未対応フォーマットなど）。"""
