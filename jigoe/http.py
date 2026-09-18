"""HTTP クライアントの薄いラッパ。

必須依存を増やさないため標準の :mod:`urllib.request` を使う。``requests`` が
入っていればそちらを使う（プロキシやリトライの挙動が安定するため）。
"""

from __future__ import annotations

import json as _json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .errors import EngineError

try:
    import requests  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - 任意依存
    requests = None  # type: ignore[assignment]

DEFAULT_TIMEOUT = 120.0
#: リトライ対象の HTTP ステータス（レート制限・一時的な上流エラー）
RETRY_STATUS = {429, 500, 502, 503, 504}


def request(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json: Any = None,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = 3,
    label: str = "リクエスト",
) -> bytes:
    """レスポンスボディをバイト列で返す。失敗時は :class:`EngineError`。

    429 / 5xx は指数バックオフで ``retries`` 回まで再試行する。
    """
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    headers = dict(headers or {})
    body = data
    if json is not None:
        body = _json.dumps(json, ensure_ascii=False).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return _once(method, url, body, headers, timeout)
        except _RetryableStatus as exc:
            last_error = exc
            if attempt == retries:
                break
            time.sleep(2**attempt)
        except EngineError:
            raise
        except Exception as exc:  # 接続エラーなど
            last_error = exc
            if attempt == retries:
                break
            time.sleep(2**attempt)
    raise EngineError(f"{label}に失敗しました: {last_error}")


class _RetryableStatus(Exception):
    pass


def _once(
    method: str, url: str, body: bytes | None, headers: dict[str, str], timeout: float
) -> bytes:
    if requests is not None:
        response = requests.request(
            method, url, data=body, headers=headers, timeout=timeout
        )
        if response.status_code in RETRY_STATUS:
            raise _RetryableStatus(f"HTTP {response.status_code}")
        if response.status_code >= 400:
            raise EngineError(
                f"HTTP {response.status_code}: {_short(response.content)}"
            )
        return response.content

    req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        if exc.code in RETRY_STATUS:
            raise _RetryableStatus(f"HTTP {exc.code}") from exc
        raise EngineError(f"HTTP {exc.code}: {_short(payload)}") from exc


def get_json(url: str, **kwargs: Any) -> Any:
    raw = request("GET", url, **kwargs)
    return _decode_json(raw)


def post_json(url: str, **kwargs: Any) -> Any:
    raw = request("POST", url, **kwargs)
    return _decode_json(raw)


def _decode_json(raw: bytes) -> Any:
    try:
        return _json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, _json.JSONDecodeError) as exc:
        raise EngineError(f"JSON として解釈できない応答が返りました: {_short(raw)}") from exc


def _short(payload: bytes, limit: int = 300) -> str:
    text = payload.decode("utf-8", errors="replace").strip().replace("\n", " ")
    return text[:limit] + ("…" if len(text) > limit else "")
