from __future__ import annotations

import hashlib
import math
import os
import statistics
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "chuangchuangtan/NPR-DeepfakeDetection"
DEFAULT_WEIGHTS = Path(__file__).resolve().parents[2] / "models" / "NPR.pth"


@dataclass(frozen=True)
class ImageInfo:
    filename: str
    content_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None


class DetectorService:
    def __init__(self) -> None:
        self.mode = os.getenv("SENSOR_DETECT_MODE", "github").strip().lower()
        self.model_name = os.getenv("SENSOR_DETECT_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        self.weights_path = Path(os.getenv("SENSOR_DETECT_WEIGHTS", str(DEFAULT_WEIGHTS))).expanduser()
        self._model: Any | None = None
        self._model_error: str | None = None

    def detect(self, image_bytes: bytes, image_info: ImageInfo) -> dict[str, Any]:
        started = time.perf_counter()

        if self.mode in {"github", "model", "auto"}:
            result = self._detect_with_model(image_bytes, image_info)
            if result is not None:
                result["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
                return result
            if self.mode in {"github", "model"}:
                return self._error_result(image_info, started)

        result = self._detect_demo(image_bytes, image_info)
        result["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
        return result

    def _detect_with_model(self, image_bytes: bytes, image_info: ImageInfo) -> dict[str, Any] | None:
        try:
            model = self._get_model()
            if model is None:
                return None

            from PIL import Image

            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            ai_probability = model.predict_probability(image)
            real_probability = 1.0 - ai_probability
            return self._format_result(
                image_info=image_info,
                ai_probability=ai_probability,
                real_probability=real_probability,
                mode="github",
                model=self.model_name,
                warnings=[
                    "当前使用 GitHub 开源 NPR 模型推理，检测结果只能作为风险参考。",
                    "压缩、裁剪、重采样和新一代生成模型可能影响准确率。",
                ],
                raw_predictions=[
                    {"label": "ai_generated", "score": ai_probability},
                    {"label": "real_image", "score": real_probability},
                ],
            )
        except Exception as exc:
            self._model_error = str(exc)
            return None

    def _get_model(self) -> Any | None:
        if self._model is not None:
            return self._model
        if self._model_error:
            return None
        if not self.weights_path.exists():
            self._model_error = f"权重文件不存在：{self.weights_path}"
            return None

        try:
            from .npr_detector import NPRDetector

            self._model = NPRDetector(self.weights_path)
            return self._model
        except Exception as exc:
            self._model_error = str(exc)
            return None

    def _detect_demo(self, image_bytes: bytes, image_info: ImageInfo) -> dict[str, Any]:
        digest = hashlib.sha256(image_bytes).digest()
        sample = image_bytes[: min(len(image_bytes), 200_000)]

        entropy = _byte_entropy(sample)
        mean = statistics.fmean(sample) if sample else 128
        variance = statistics.pvariance(sample) if len(sample) > 1 else 0

        hash_component = int.from_bytes(digest[:2], "big") / 65535
        entropy_component = min(1.0, entropy / 8.0)
        variance_component = min(1.0, math.sqrt(variance) / 96.0)

        ai_probability = (
            0.42 * hash_component
            + 0.32 * entropy_component
            + 0.16 * variance_component
            + 0.10 * (mean / 255)
        )
        ai_probability = max(0.05, min(0.95, ai_probability))

        return self._format_result(
            image_info=image_info,
            ai_probability=ai_probability,
            real_probability=1.0 - ai_probability,
            mode="demo",
            model="demo-local-image-signal",
            warnings=[
                "当前是 demo 检测模式，只用于验证前后端链路，不代表真实 AI 图像检测结论。",
                "下载 NPR.pth 并设置 SENSOR_DETECT_MODE=github 后，会切换到真实 GitHub 权重推理。",
            ],
            raw_predictions=[
                {"label": "ai", "score": ai_probability},
                {"label": "real", "score": 1.0 - ai_probability},
            ],
        )

    def _format_result(
        self,
        image_info: ImageInfo,
        ai_probability: float,
        real_probability: float,
        mode: str,
        model: str,
        warnings: list[str],
        raw_predictions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ai_probability = round(float(ai_probability), 4)
        real_probability = round(float(real_probability), 4)
        result = "likely_ai" if ai_probability >= real_probability else "likely_real"
        confidence_delta = abs(ai_probability - real_probability)

        if confidence_delta >= 0.55:
            confidence = "high"
        elif confidence_delta >= 0.25:
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "ok": True,
            "result": result,
            "ai_probability": ai_probability,
            "real_probability": real_probability,
            "confidence": confidence,
            "mode": mode,
            "model": model,
            "image": {
                "filename": image_info.filename,
                "content_type": image_info.content_type,
                "size_bytes": image_info.size_bytes,
                "width": image_info.width,
                "height": image_info.height,
            },
            "warnings": warnings,
            "raw_predictions": raw_predictions,
        }

    def _error_result(self, image_info: ImageInfo, started: float) -> dict[str, Any]:
        return {
            "ok": False,
            "error": "model_unavailable",
            "message": "GitHub NPR 模型推理未能启动，请确认已安装 backend/requirements.txt，且 backend/models/NPR.pth 已下载完整。",
            "detail": self._model_error,
            "mode": self.mode,
            "model": self.model_name,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "image": {
                "filename": image_info.filename,
                "content_type": image_info.content_type,
                "size_bytes": image_info.size_bytes,
                "width": image_info.width,
                "height": image_info.height,
            },
        }


def _byte_entropy(data: bytes) -> float:
    if not data:
        return 0.0

    counts = [0] * 256
    for byte in data:
        counts[byte] += 1

    entropy = 0.0
    length = len(data)
    for count in counts:
        if count:
            probability = count / length
            entropy -= probability * math.log2(probability)
    return entropy
