# Sensor-detect

AI 生成图像检测网站的本地 MVP。

## 当前能力

- 本地启动一个后端服务
- React + TypeScript 前端检测页面
- 上传 PNG / JPEG / WebP / GIF 图片
- 展示扫描动画、分析进度、AI 生成概率和异常信号
- 后端默认使用 GitHub 开源 NPR 模型权重进行真实推理
- 模型不可用时会返回明确错误，`auto` 模式可回退到 demo 结果

当前接入的模型是 `chuangchuangtan/NPR-DeepfakeDetection`，权重文件为 `backend/models/NPR.pth`。它是基于 Neighboring Pixel Relationships 的深度伪造图像检测模型，适合作为本地 MVP 的真实检测后端起点。

## 快速启动

当前机器的 IPv4 localhost 异常，服务默认使用 IPv6 回环地址。

```powershell
.\start-local.cmd
```

启动后打开：

```text
http://[::1]:8000
```

## 安装依赖

```powershell
python -m pip install -r backend\requirements.txt
```

## 模型权重

本地已下载：

```text
backend/models/NPR.pth
```

权重来源：

```text
https://github.com/chuangchuangtan/NPR-DeepfakeDetection
```

如果重新克隆仓库后没有权重文件，可以从 GitHub raw 下载：

```powershell
python -c "from urllib.request import urlopen; from pathlib import Path; url='https://raw.githubusercontent.com/chuangchuangtan/NPR-DeepfakeDetection/main/NPR.pth'; out=Path('backend/models/NPR.pth'); out.parent.mkdir(parents=True, exist_ok=True); out.write_bytes(urlopen(url, timeout=120).read())"
```

第三方权重文件不会提交到本仓库。

## 前端开发

前端位于 `frontend/`，技术栈为 React、TypeScript、Vite 和 CSS。

```powershell
cd frontend
npm install
npm run build
```

构建后，后端会优先托管 `frontend/dist`。

## 切换模式

真实模型模式：

```powershell
$env:SENSOR_DETECT_MODE="github"
$env:SENSOR_DETECT_MODEL="chuangchuangtan/NPR-DeepfakeDetection"
$env:SENSOR_DETECT_WEIGHTS="backend/models/NPR.pth"
python backend\app\main.py
```

自动回退模式：

```powershell
$env:SENSOR_DETECT_MODE="auto"
python backend\app\main.py
```

演示模式：

```powershell
$env:SENSOR_DETECT_MODE="demo"
python backend\app\main.py
```

## 目录结构

```text
backend/
  app/
    main.py
    services/
      detector.py
      npr_detector.py
  models/
    NPR.pth
frontend/
  src/
    App.tsx
    main.tsx
    styles.css
  dist/
  package.json
docs/
  technical-analysis.md
```

## 注意

AI 生成图像检测只能提供概率和风险参考，不能作为绝对证明。图片压缩、裁剪、重采样、社交平台二次处理、新模型生成图像都会影响检测可靠性。
