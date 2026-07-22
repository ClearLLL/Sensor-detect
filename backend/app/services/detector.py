from __future__ import annotations

import hashlib
import math
import os
import statistics
import time
from dataclasses import dataclass
from typing import Any


DEFAULT_MODEL = "haywoodsloan/ai-image-detector-deploy"


@dataclass(frozen=True)
class ImageInfo:
    filename: str
    content_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None


class DetectorService:
    def __init__(self) -> None:
        self.mode = os.getenv("SENSOR_DETECT_MODE", "demo").strip().lower()
        self.model_name = os.getenv("SENSOR_DETECT_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        self._pipeline: Any | None = None
        self._model_error: str | None = None

    def detect(self, image_bytes: bytes, image_info: ImageInfo) -> dict[str, Any]:
        started = time.perf_counter()

        if self.mode in {"model", "auto"}:
            result = self._detect_with_model(image_bytes, image_info)
            if result is not None:
                result["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
                return result
            if self.mode == "model":
                return self._error_result(image_info, started)

        result = self._detect_demo(image_bytes, image_info)
        result["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
        return result

    def _detect_with_model(self, image_bytes: bytes, image_info: ImageInfo) -> dict[str, Any] | None:
        try:
            pipe = self._get_pipeline()
            if pipe is None:
                return None

            from PIL import Image
            from io import BytesIO

            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            predictions = pipe(image)
            ai_probability, real_probability, raw = self._normalize_model_predictions(predictions)
            return self._format_result(
                image_info=image_info,
                ai_probability=ai_probability,
                real_probability=real_probability,
                mode="model",
                model=self.model_name,
                warnings=[
                    "检测结果仅供参考，不能作为图片来源的唯一证据。",
                    "压缩、裁剪、重采样和新生成模型都可能影响准确率。",
                ],
                raw_predictions=raw,
            )
        except Exception as exc:
            self._model_error = str(exc)
            return None

    def _get_pipeline(self) -> Any | None:
        if self._pipeline is not None:
            return self._pipeline
        if self._model_error:
            return None

        try:
            from transformers import pipeline

            self._pipeline = pipeline("image-classification", model=self.model_name)
            return self._pipeline
        except Exception as exc:
            self._model_error = str(exc)
            return None

    def _normalize_model_predictions(self, predictions: Any) -> tuple[float, float, list[dict[str, Any]]]:
        raw: list[dict[str, Any]] = []
        ai_score = 0.0
        real_score = 0.0

        if not isinstance(predictions, list):
            predictions = []

        for item in predictions:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label", "")).lower()
            score = float(item.get("score", 0.0))
            raw.append({"label": item.get("label"), "score": score})

            if any(token in label for token in ("ai", "artificial", "fake", "generated", "synthetic")):
                ai_score += score
            elif any(token in label for token in ("real", "human", "natural", "authentic")):
                real_score += score

        if ai_score == 0 and real_score == 0 and raw:
            top_label = str(raw[0].get("label", "")).lower()
            top_score = float(raw[0].get("score", 0.0))
            if "0" in top_label or "fake" in top_label:
                ai_score = top_score
                real_score = max(0.0, 1.0 - top_score)
            else:
                real_score = top_score
                ai_score = max(0.0, 1.0 - top_score)

        total = ai_score + real_score
        if total <= 0:
            return 0.5, 0.5, raw

        return ai_score / total, real_score / total, raw

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
                "安装模型依赖并设置 SENSOR_DETECT_MODE=model 后，会切换到真实图像分类模型推理。",
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
            "message": "模型推理未能启动，请确认已安装 requirements.txt 并且模型可以下载。",
            "detail": self._model_error,
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
