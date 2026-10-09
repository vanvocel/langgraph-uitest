"""Feishu (Lark) app-bot channel: text summary + file upload to a chat."""

from __future__ import annotations

import json
import mimetypes
import os
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from framework.notify.base import NotifyChannel, NotifyResult
from framework.notify.models import ReportPayload

_BASE = "https://open.feishu.cn/open-apis"
# Feishu im/v1/files rejects large stream uploads (HTML allure often exceeds).
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _env_or(config: dict[str, Any], key: str, env_key: str | None = None) -> str:
    direct = str(config.get(key) or "").strip()
    if direct:
        return direct
    env_name = str(env_key or config.get(f"{key}_env") or "").strip()
    if env_name:
        return os.getenv(env_name, "").strip()
    return ""


def _http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 30,
) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(url, data=data, method=method.upper())
    req.add_header("Content-Type", "application/json; charset=utf-8")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"msg": raw}
        raise RuntimeError(
            f"Feishu HTTP {exc.code}: {payload.get('msg') or payload.get('message') or raw[:300]}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"Feishu network error: {exc}") from exc
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Feishu non-JSON response: {raw[:300]}") from exc


def _multipart_upload(
    url: str,
    *,
    token: str,
    fields: dict[str, str],
    file_field: str,
    file_path: Path,
    timeout: float = 60,
) -> dict[str, Any]:
    boundary = f"----uitest{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(f"{value}\r\n".encode())
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    file_bytes = file_path.read_bytes()
    chunks.append(f"--{boundary}\r\n".encode())
    chunks.append(
        (
            f'Content-Disposition: form-data; name="{file_field}"; '
            f'filename="{file_path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode()
    )
    chunks.append(file_bytes)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    body = b"".join(chunks)
    req = Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Feishu upload HTTP {exc.code}: {raw[:400]}") from exc
    data = json.loads(raw) if raw else {}
    if int(data.get("code") or 0) != 0:
        raise RuntimeError(f"Feishu upload failed: {data.get('msg') or data}")
    return data


def _feishu_file_type(path: Path) -> str:
    """Map extension to Feishu im/v1/files file_type."""
    ext = path.suffix.lower()
    if ext in {".xls", ".xlsx"}:
        return "xls"
    if ext in {".doc", ".docx"}:
        return "doc"
    if ext in {".ppt", ".pptx"}:
        return "ppt"
    if ext == ".pdf":
        return "pdf"
    # html / json / zip / others
    return "stream"


def _prepare_upload_path(path: Path, *, max_bytes: int = _MAX_UPLOAD_BYTES) -> tuple[Path, Path | None]:
    """Return (path_to_upload, temp_to_cleanup). Zip oversized / html reports."""
    size = path.stat().st_size
    need_zip = path.suffix.lower() in {".html", ".htm"} or size > max_bytes
    if not need_zip:
        return path, None
    tmp = Path(tempfile.gettempdir()) / f"{path.stem}_{uuid.uuid4().hex[:8]}.zip"
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(path, arcname=path.name)
    zipped = tmp.stat().st_size
    if zipped > max_bytes:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"file too large for Feishu even after zip: {path.name} "
            f"({size} -> {zipped} bytes, limit {max_bytes})"
        )
    return tmp, tmp


class FeishuChannel(NotifyChannel):
    name = "feishu"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.app_id = _env_or(self.config, "app_id", self.config.get("app_id_env") or "FEISHU_APP_ID")
        self.app_secret = _env_or(
            self.config, "app_secret", self.config.get("app_secret_env") or "FEISHU_APP_SECRET"
        )
        self.chat_id = _env_or(self.config, "chat_id", self.config.get("chat_id_env") or "FEISHU_CHAT_ID")

    def _token(self) -> str:
        data = _http_json(
            "POST",
            f"{_BASE}/auth/v3/tenant_access_token/internal",
            body={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        token = str(data.get("tenant_access_token") or "").strip()
        if not token:
            raise RuntimeError(f"Feishu token missing: {data}")
        return token

    def _send_text(self, token: str, text: str) -> dict[str, Any]:
        return _http_json(
            "POST",
            f"{_BASE}/im/v1/messages?receive_id_type=chat_id",
            headers={"Authorization": f"Bearer {token}"},
            body={
                "receive_id": self.chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        )

    def _upload_file(self, token: str, path: Path) -> str:
        data = _multipart_upload(
            f"{_BASE}/im/v1/files",
            token=token,
            fields={
                "file_type": _feishu_file_type(path),
                "file_name": path.name,
            },
            file_field="file",
            file_path=path,
        )
        file_key = str((data.get("data") or {}).get("file_key") or "").strip()
        if not file_key:
            raise RuntimeError(f"Feishu file_key missing: {data}")
        return file_key

    def _send_file(self, token: str, file_key: str) -> dict[str, Any]:
        return _http_json(
            "POST",
            f"{_BASE}/im/v1/messages?receive_id_type=chat_id",
            headers={"Authorization": f"Bearer {token}"},
            body={
                "receive_id": self.chat_id,
                "msg_type": "file",
                "content": json.dumps({"file_key": file_key}, ensure_ascii=False),
            },
        )

    def send(self, payload: ReportPayload) -> NotifyResult:
        if not self.app_id or not self.app_secret:
            return NotifyResult(
                channel=self.name,
                ok=False,
                message="missing FEISHU_APP_ID / FEISHU_APP_SECRET (or config app_id/app_secret)",
            )
        if not self.chat_id:
            return NotifyResult(
                channel=self.name,
                ok=False,
                message="missing FEISHU_CHAT_ID (or config chat_id)",
            )
        details: dict[str, Any] = {"uploaded": [], "errors": []}
        try:
            token = self._token()
            if self.config.get("send_summary", True):
                resp = self._send_text(token, payload.summary_text())
                if int(resp.get("code") or 0) != 0:
                    raise RuntimeError(f"send text failed: {resp.get('msg') or resp}")
                details["text_message_id"] = (resp.get("data") or {}).get("message_id")

            paths = payload.attachment_paths(
                excel=bool(self.config.get("upload_excel", True)),
                html=bool(self.config.get("upload_html", True)),
            )
            for path in paths:
                tmp: Path | None = None
                try:
                    upload_path, tmp = _prepare_upload_path(path)
                    file_key = self._upload_file(token, upload_path)
                    resp = self._send_file(token, file_key)
                    if int(resp.get("code") or 0) != 0:
                        raise RuntimeError(f"send file failed: {resp.get('msg') or resp}")
                    details["uploaded"].append(
                        {
                            "name": upload_path.name,
                            "source": path.name,
                            "file_key": file_key,
                            "message_id": (resp.get("data") or {}).get("message_id"),
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    details["errors"].append({"file": path.name, "error": str(exc)})
                    if "too large" in str(exc).lower() or "234006" in str(exc):
                        try:
                            self._send_text(
                                token,
                                f"【附件过大未上传】{path.name}\n"
                                f"本地路径：{path.resolve()}\n"
                                "请在执行机打开该文件；飞书单文件上限无法承载完整 Allure HTML。",
                            )
                        except Exception:  # noqa: BLE001
                            pass
                finally:
                    if tmp is not None:
                        tmp.unlink(missing_ok=True)

            if details["errors"] and not details["uploaded"] and not details.get("text_message_id"):
                return NotifyResult(
                    channel=self.name,
                    ok=False,
                    message="; ".join(e["error"] for e in details["errors"]),
                    details=details,
                )
            msg = f"sent summary + {len(details['uploaded'])} file(s)"
            if details["errors"]:
                msg += f"; {len(details['errors'])} upload error(s)"
            return NotifyResult(channel=self.name, ok=True, message=msg, details=details)
        except Exception as exc:  # noqa: BLE001
            return NotifyResult(channel=self.name, ok=False, message=str(exc), details=details)
