from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
from PIL import Image
from torch import nn
from torch.nn import functional as F


class Bottleneck(nn.Module):
    expansion = 4

    def __init__(self, inplanes: int, planes: int, stride: int = 1, downsample: nn.Module | None = None) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(inplanes, planes, kernel_size=1, bias=False)
        self.bn1 = nn.BatchNorm2d(planes)
        self.conv2 = nn.Conv2d(planes, planes, kernel_size=3, stride=stride, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(planes)
        self.conv3 = nn.Conv2d(planes, planes * self.expansion, kernel_size=1, bias=False)
        self.bn3 = nn.BatchNorm2d(planes * self.expansion)
        self.relu = nn.ReLU(inplace=True)
        self.downsample = downsample

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        identity = x

        out = self.relu(self.bn1(self.conv1(x)))
        out = self.relu(self.bn2(self.conv2(out)))
        out = self.bn3(self.conv3(out))

        if self.downsample is not None:
            identity = self.downsample(x)

        return self.relu(out + identity)


class NPRResNet(nn.Module):
    """ResNet variant used by chuangchuangtan/NPR-DeepfakeDetection."""

    def __init__(self) -> None:
        super().__init__()
        self.inplanes = 64
        self.conv1 = nn.Conv2d(3, 64, kernel_size=3, stride=2, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(64)
        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)
        self.layer1 = self._make_layer(64, 3)
        self.layer2 = self._make_layer(128, 4, stride=2)
        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
        self.fc1 = nn.Linear(512, 1)

    def _make_layer(self, planes: int, blocks: int, stride: int = 1) -> nn.Sequential:
        downsample = None
        if stride != 1 or self.inplanes != planes * Bottleneck.expansion:
            downsample = nn.Sequential(
                nn.Conv2d(self.inplanes, planes * Bottleneck.expansion, kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm2d(planes * Bottleneck.expansion),
            )

        layers: list[nn.Module] = [Bottleneck(self.inplanes, planes, stride, downsample)]
        self.inplanes = planes * Bottleneck.expansion
        for _ in range(1, blocks):
            layers.append(Bottleneck(self.inplanes, planes))

        return nn.Sequential(*layers)

    @staticmethod
    def _nearest_roundtrip(x: torch.Tensor) -> torch.Tensor:
        down = F.interpolate(x, scale_factor=0.5, mode="nearest", recompute_scale_factor=True)
        return F.interpolate(down, scale_factor=2.0, mode="nearest", recompute_scale_factor=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        npr = x - self._nearest_roundtrip(x)
        x = self.relu(self.bn1(self.conv1(npr * 2.0 / 3.0)))
        x = self.maxpool(x)
        x = self.layer1(x)
        x = self.layer2(x)
        x = self.avgpool(x)
        x = x.view(x.size(0), -1)
        return self.fc1(x)


class NPRDetector:
    def __init__(self, weights_path: str | Path) -> None:
        self.weights_path = Path(weights_path)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = NPRResNet().to(self.device)

        checkpoint: Any = torch.load(self.weights_path, map_location=self.device)
        state_dict = checkpoint.get("model", checkpoint) if isinstance(checkpoint, dict) else checkpoint
        state_dict = {
            key.removeprefix("module."): value
            for key, value in state_dict.items()
        }
        self.model.load_state_dict(state_dict, strict=True)
        self.model.eval()

    def predict_probability(self, image: Image.Image) -> float:
        tensor = self._preprocess(image).to(self.device)
        with torch.no_grad():
            return float(self.model(tensor).sigmoid().item())

    @staticmethod
    def _preprocess(image: Image.Image) -> torch.Tensor:
        resampling = getattr(Image, "Resampling", Image).BILINEAR
        rgb = image.convert("RGB").resize((256, 256), resampling)
        data = torch.frombuffer(bytearray(rgb.tobytes()), dtype=torch.uint8)
        tensor = data.view(256, 256, 3).permute(2, 0, 1).float().div(255.0)

        mean = torch.tensor([0.485, 0.456, 0.406], dtype=tensor.dtype).view(3, 1, 1)
        std = torch.tensor([0.229, 0.224, 0.225], dtype=tensor.dtype).view(3, 1, 1)
        tensor = (tensor - mean) / std
        return tensor.unsqueeze(0)


