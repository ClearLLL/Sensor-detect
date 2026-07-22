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
DEFAULT_SELECTED_MODELS = ["npr", "frequency", "compression", "metadata"]


@dataclass(frozen=True)
class ImageInfo:
    filename: str
    content_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class ModelSpec:
    id: str
    name: str
    kind: str
    source: str
    description: str
    weight: float
    requires_weights: bool = False


MODEL_SPECS = [
    ModelSpec(
        id="npr",
        name="NPR 深度模型",
        kind="deep-learning",
        source="chuangchuangtan/NPR-DeepfakeDetection",
        description="基于邻域像素关系的 GitHub 开源深度伪造检测模型。",
        weight=0.55,
        requires_weights=True,
    ),
    ModelSpec(
        id="frequency",
        name="频域残差模型",
        kind="forensic-signal",
        source="local-frequency-residual",
        description="分析高频残差、局部噪声和边缘变化，用作生成痕迹辅助判断。",
        weight=0.2,
    ),
    ModelSpec(
        id="compression",
        name="压缩痕迹模型",
        kind="forensic-signal",
        source="local-compression-artifact",
        description="比较重压缩前后的误差与文件编码特征，识别异常压缩链路。",
        weight=0.15,
    ),
    ModelSpec(
        id="metadata",
        name="元数据来源模型",
        kind="forensic-signal",
        source="local-metadata-provenance",
        description="检查 EXIF、软件标记和文件头信息，提供来源侧证据。",
        weight=0.1,
    ),
]


class DetectorService:
    def __init__(self) -> None:
        self.mode = os.getenv("SENSOR_DETECT_MODE", "ensemble").strip().lower()
        self.model_name = os.getenv("SENSOR_DETECT_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        self.weights_path = Path(os.getenv("SENSOR_DETECT_WEIGHTS", str(DEFAULT_WEIGHTS))).expanduser()
        self._npr_model: Any | None = None
        self._model_error: str | None = None

    def list_models(self) -> list[dict[str, Any]]:
        return [self._model_metadata(spec) for spec in MODEL_SPECS]

    def detect(self, image_bytes: bytes, image_info: ImageInfo, selected_model_ids: list[str] | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        if self.mode == "demo":
            result = self._detect_demo(image_bytes, image_info)
            result["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
            return result

        selected = self._normalize_selected_models(selected_model_ids)

        if selected:
            result = self._detect_with_selected_models(image_bytes, image_info, selected, started)
            if result is not None:
                return result
            if self.mode in {"ensemble", "github", "model"}:
                return self._error_result(image_info, started, selected)

        result = self._detect_demo(image_bytes, image_info)
        result["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
        return result

    def _detect_with_selected_models(
        self,
        image_bytes: bytes,
        image_info: ImageInfo,
        selected: list[str],
        started: float,
    ) -> dict[str, Any] | None:
        try:
            from PIL import Image

            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            predictions: list[dict[str, Any]] = []
            errors: list[dict[str, Any]] = []

            for model_id in selected:
                spec = self._get_spec(model_id)
                if spec is None:
                    continue
                try:
                    predictions.append(self._run_model(spec, image, image_bytes, image_info))
                except Exception as exc:
                    errors.append({"id": spec.id, "name": spec.name, "error": str(exc)})

            if not predictions:
                if errors:
                    self._model_error = "; ".join(f"{item['name']}: {item['error']}" for item in errors)
                return None

            total_weight = sum(float(item["weight"]) for item in predictions)
            if total_weight <= 0:
                ai_probability = statistics.fmean(float(item["ai_probability"]) for item in predictions)
            else:
                ai_probability = sum(float(item["ai_probability"]) * float(item["weight"]) for item in predictions) / total_weight

            warnings = [
                "综合检测由多个模型/取证信号加权得到，结果只能作为风险参考。",
                "不同模型可能对压缩、裁剪、重采样和新生成模型有不同敏感性。",
            ]
            if errors:
                warnings.append("部分模型本次未能执行，综合结果只基于可用模型。")

            model_label = " + ".join(item["name"] for item in predictions)
            response = self._format_result(
                image_info=image_info,
                ai_probability=ai_probability,
                real_probability=1.0 - ai_probability,
                mode="ensemble" if len(predictions) > 1 else predictions[0]["id"],
                model=model_label,
                warnings=warnings,
                raw_predictions=[
                    {"label": item["id"], "score": item["ai_probability"]}
                    for item in predictions
                ],
            )
            response["selected_models"] = selected
            response["model_results"] = predictions
            response["model_errors"] = errors
            response["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
            return response
        except Exception as exc:
            self._model_error = str(exc)
            return None

    def _run_model(self, spec: ModelSpec, image: Any, image_bytes: bytes, image_info: ImageInfo) -> dict[str, Any]:
        if spec.id == "npr":
            ai_probability = self._predict_npr(image)
            details = "NPR logit 经 sigmoid 转换为 AI 生成概率。"
        elif spec.id == "frequency":
            ai_probability, details = _predict_frequency(image)
        elif spec.id == "compression":
            ai_probability, details = _predict_compression(image, image_bytes, image_info)
        elif spec.id == "metadata":
            ai_probability, details = _predict_metadata(image, image_bytes, image_info)
        else:
            raise ValueError(f"未知模型：{spec.id}")

        ai_probability = _clamp01(ai_probability)
        return {
            "id": spec.id,
            "name": spec.name,
            "kind": spec.kind,
            "source": spec.source,
            "weight": spec.weight,
            "ai_probability": round(ai_probability, 6),
            "real_probability": round(1.0 - ai_probability, 6),
            "result": "likely_ai" if ai_probability >= 0.5 else "likely_real",
            "detail": details,
        }

    def _predict_npr(self, image: Any) -> float:
        model = self._get_npr_model()
        if model is None:
            raise RuntimeError(self._model_error or "NPR 模型不可用")
        return float(model.predict_probability(image))

    def _get_npr_model(self) -> Any | None:
        if self._npr_model is not None:
            return self._npr_model
        if self._model_error:
            return None
        if not self.weights_path.exists():
            self._model_error = f"权重文件不存在：{self.weights_path}"
            return None

        try:
            from .npr_detector import NPRDetector

            self._npr_model = NPRDetector(self.weights_path)
            return self._npr_model
        except Exception as exc:
            self._model_error = str(exc)
            return None

    def _normalize_selected_models(self, selected_model_ids: list[str] | None) -> list[str]:
        available_ids = {spec.id for spec in MODEL_SPECS}
        if not selected_model_ids:
            selected_model_ids = DEFAULT_SELECTED_MODELS

        normalized: list[str] = []
        for model_id in selected_model_ids:
            model_id = model_id.strip().lower()
            if model_id in available_ids and model_id not in normalized:
                normalized.append(model_id)
        return normalized

    def _get_spec(self, model_id: str) -> ModelSpec | None:
        for spec in MODEL_SPECS:
            if spec.id == model_id:
                return spec
        return None

    def _model_metadata(self, spec: ModelSpec) -> dict[str, Any]:
        available = True
        unavailable_reason = None
        if spec.id == "npr" and not self.weights_path.exists():
            available = False
            unavailable_reason = f"缺少权重文件：{self.weights_path}"
        return {
            "id": spec.id,
            "name": spec.name,
            "kind": spec.kind,
            "source": spec.source,
            "description": spec.description,
            "weight": spec.weight,
            "available": available,
            "unavailable_reason": unavailable_reason,
        }

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
                "选择 NPR 或综合模型后，会切换到真实模型/取证信号推理。",
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
        ai_probability = round(float(ai_probability), 6)
        real_probability = round(float(real_probability), 6)
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

    def _error_result(self, image_info: ImageInfo, started: float, selected: list[str]) -> dict[str, Any]:
        return {
            "ok": False,
            "error": "model_unavailable",
            "message": "所选模型均未能启动，请确认依赖和权重文件已准备完整。",
            "detail": self._model_error,
            "mode": self.mode,
            "model": self.model_name,
            "selected_models": selected,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "image": {
                "filename": image_info.filename,
                "content_type": image_info.content_type,
                "size_bytes": image_info.size_bytes,
                "width": image_info.width,
                "height": image_info.height,
            },
        }


def _predict_frequency(image: Any) -> tuple[float, str]:
    gray = image.convert("L").resize((256, 256))
    pixels = list(gray.getdata())
    rows = [pixels[index:index + 256] for index in range(0, len(pixels), 256)]

    horizontal = []
    vertical = []
    for y in range(256):
        row = rows[y]
        horizontal.extend(abs(row[x + 1] - row[x]) / 255 for x in range(255))
    for y in range(255):
        row = rows[y]
        next_row = rows[y + 1]
        vertical.extend(abs(next_row[x] - row[x]) / 255 for x in range(256))

    diffs = horizontal + vertical
    mean_diff = statistics.fmean(diffs) if diffs else 0.0
    stdev_diff = statistics.pstdev(diffs) if len(diffs) > 1 else 0.0
    high_ratio = sum(1 for item in diffs if item > 0.18) / len(diffs) if diffs else 0.0
    score = _sigmoid((mean_diff - 0.045) * 13.0 + (stdev_diff - 0.08) * 6.0 + (high_ratio - 0.18) * 2.4)
    details = f"平均高频差分 {mean_diff:.4f}，差分离散度 {stdev_diff:.4f}，强边缘占比 {high_ratio:.4f}。"
    return score, details


def _predict_compression(image: Any, image_bytes: bytes, image_info: ImageInfo) -> tuple[float, str]:
    from PIL import Image, ImageChops

    rgb = image.convert("RGB").resize((256, 256))
    buffer = BytesIO()
    rgb.save(buffer, format="JPEG", quality=90)
    recompressed = Image.open(BytesIO(buffer.getvalue())).convert("RGB")
    diff = ImageChops.difference(rgb, recompressed)
    values = list(diff.convert("L").getdata())
    mean_error = (statistics.fmean(values) / 255) if values else 0.0
    entropy = _byte_entropy(image_bytes[: min(len(image_bytes), 400_000)]) / 8.0
    jpeg_bonus = -0.08 if image_info.content_type == "image/jpeg" and b"Exif" in image_bytes[:4096] else 0.06
    score = _sigmoid((0.035 - mean_error) * 18.0 + (entropy - 0.72) * 1.4 + jpeg_bonus)
    details = f"JPEG 90 重压缩误差 {mean_error:.4f}，文件字节熵 {entropy:.4f}。"
    return score, details


def _predict_metadata(image: Any, image_bytes: bytes, image_info: ImageInfo) -> tuple[float, str]:
    info = getattr(image, "info", {}) or {}
    exif = image.getexif() if hasattr(image, "getexif") else None
    exif_count = len(exif) if exif else 0
    software = str(info.get("Software") or info.get("software") or "").lower()
    has_exif_marker = b"Exif" in image_bytes[:8192]
    suspicious_software = any(token in software for token in ("stable diffusion", "midjourney", "comfyui", "automatic1111", "dall"))

    score = 0.44
    if exif_count == 0 and not has_exif_marker:
        score += 0.18
    if suspicious_software:
        score += 0.34
    if image_info.content_type in {"image/png", "image/webp"}:
        score += 0.04
    if image_info.width and image_info.height and image_info.width == image_info.height:
        score += 0.03

    details = f"EXIF 项 {exif_count} 个，文件头 EXIF 标记 {'存在' if has_exif_marker else '不存在'}。"
    return _clamp01(score), details


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


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1 / (1 + z)
    z = math.exp(value)
    return z / (1 + z)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
