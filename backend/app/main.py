from __future__ import annotations

import json
import mimetypes
import re
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.detector import DetectorService, ImageInfo


ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT_DIR / "frontend"
HOST = "127.0.0.1"
PORT = 8000
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

DETECTOR = DetectorService()


class SensorDetectHandler(BaseHTTPRequestHandler):
    server_version = "sensor-detect/0.1"

    def do_OPTIONS(self) -> None:
        self._send_empty(HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            self._send_json(
                {
                    "ok": True,
                    "service": "sensor-detect",
                    "mode": DETECTOR.mode,
                    "model": DETECTOR.model_name,
                }
            )
            return

        if path == "/api/models/current":
            self._send_json(
                {
                    "mode": DETECTOR.mode,
                    "model": DETECTOR.model_name,
                    "default_model": "haywoodsloan/ai-image-detector-deploy",
                }
            )
            return

        self._serve_static(path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/detect":
            self._send_json({"ok": False, "error": "not_found"}, HTTPStatus.NOT_FOUND)
            return

        content_length = self.headers.get("Content-Length")
        if not content_length or not content_length.isdigit():
            self._send_json({"ok": False, "error": "missing_content_length"}, HTTPStatus.BAD_REQUEST)
            return

        length = int(content_length)
        if length > MAX_UPLOAD_BYTES:
            self._send_json(
                {"ok": False, "error": "file_too_large", "max_bytes": MAX_UPLOAD_BYTES},
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
            return

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send_json({"ok": False, "error": "expected_multipart_form"}, HTTPStatus.BAD_REQUEST)
            return

        body = self.rfile.read(length)
        try:
            upload = _extract_image_upload(content_type, body)
        except ValueError as exc:
            self._send_json({"ok": False, "error": "invalid_upload", "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        image_bytes = upload["data"]
        detected_type = _detect_image_type(image_bytes)
        if detected_type is None:
            self._send_json(
                {"ok": False, "error": "unsupported_image", "message": "Only PNG, JPEG, WebP and GIF images are supported."},
                HTTPStatus.BAD_REQUEST,
            )
            return

        width, height = _detect_dimensions(image_bytes, detected_type)
        image_info = ImageInfo(
            filename=upload["filename"],
            content_type=detected_type,
            size_bytes=len(image_bytes),
            width=width,
            height=height,
        )
        self._send_json(DETECTOR.detect(image_bytes, image_info))

    def _serve_static(self, request_path: str) -> None:
        if request_path in {"", "/"}:
            file_path = FRONTEND_DIR / "index.html"
        else:
            clean_path = unquote(request_path).lstrip("/")
            file_path = (FRONTEND_DIR / clean_path).resolve()
            if FRONTEND_DIR.resolve() not in file_path.parents and file_path != FRONTEND_DIR.resolve():
                self._send_json({"ok": False, "error": "forbidden"}, HTTPStatus.FORBIDDEN)
                return

        if not file_path.exists() or not file_path.is_file():
            self._send_json({"ok": False, "error": "not_found"}, HTTPStatus.NOT_FOUND)
            return

        content_type, _ = mimetypes.guess_type(str(file_path))
        content_type = content_type or "application/octet-stream"
        data = file_path.read_bytes()

        self.send_response(HTTPStatus.OK)
        self._send_common_headers(content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_common_headers("application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_empty(self, status: HTTPStatus) -> None:
        self.send_response(status)
        self._send_common_headers("text/plain; charset=utf-8")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_common_headers(self, content_type: str) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format: str, *args: object) -> None:
        sys.stdout.write("%s - %s\n" % (self.log_date_time_string(), format % args))


def _extract_image_upload(content_type: str, body: bytes) -> dict[str, object]:
    boundary_match = re.search(r"boundary=(?P<boundary>[^;]+)", content_type)
    if not boundary_match:
        raise ValueError("Missing multipart boundary.")

    boundary = boundary_match.group("boundary").strip().strip('"').encode("utf-8")
    delimiter = b"--" + boundary

    for part in body.split(delimiter):
        part = part.strip()
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2].strip()
        if b"\r\n\r\n" not in part:
            continue

        header_blob, data = part.split(b"\r\n\r\n", 1)
        headers = header_blob.decode("utf-8", errors="replace")
        if 'name="image"' not in headers:
            continue

        filename_match = re.search(r'filename="(?P<filename>[^"]*)"', headers)
        filename = filename_match.group("filename") if filename_match else "upload"
        data = data.rstrip(b"\r\n")
        if not data:
            raise ValueError("Uploaded image is empty.")
        return {"filename": filename, "data": data}

    raise ValueError("No uploaded file named image was found.")


def _detect_image_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    return None


def _detect_dimensions(data: bytes, content_type: str) -> tuple[int | None, int | None]:
    if content_type == "image/png" and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")

    if content_type == "image/gif" and len(data) >= 10:
        return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")

    if content_type == "image/webp" and len(data) >= 30:
        if data[12:16] == b"VP8X":
            width = int.from_bytes(data[24:27], "little") + 1
            height = int.from_bytes(data[27:30], "little") + 1
            return width, height

    if content_type == "image/jpeg":
        return _detect_jpeg_dimensions(data)

    return None, None


def _detect_jpeg_dimensions(data: bytes) -> tuple[int | None, int | None]:
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(data):
            break
        segment_length = int.from_bytes(data[index:index + 2], "big")
        if segment_length < 2 or index + segment_length > len(data):
            break
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            height = int.from_bytes(data[index + 3:index + 5], "big")
            width = int.from_bytes(data[index + 5:index + 7], "big")
            return width, height
        index += segment_length
    return None, None


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), SensorDetectHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()




