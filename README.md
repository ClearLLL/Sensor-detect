# Sensor-detect

AI 生成图像检测网站的本地 MVP。

## 当前能力

- 本地启动一个后端服务
- React + TypeScript 前端检测页面
- 上传 PNG / JPEG / WebP / GIF 图片
- 展示扫描动画、分析进度、AI 生成概率和异常信号
- 返回统一的检测结果结构
- 支持后续切换到 Hugging Face 图像分类模型推理

当前默认使用 `demo` 检测模式，保证没有安装深度学习依赖时也能先跑通前后端链路。真实模型模式需要额外安装 `transformers`、`torch`、`Pillow`。

## 快速启动

当前机器的 IPv4 localhost 异常，服务默认使用 IPv6 回环地址。

```powershell
.\start-local.cmd
```

启动后打开：

```text
http://[::1]:8000
```

## 前端开发

前端位于 `frontend/`，技术栈为 React、TypeScript、Vite 和 CSS。

```powershell
cd frontend
npm install
npm run build
```

构建后，后端会优先托管 `frontend/dist`。

## 启用真实模型推理

先安装后端依赖：

```powershell
python -m pip install -r backend\requirements.txt
```

然后启动时设置：

```powershell
$env:SENSOR_DETECT_MODE="model"
$env:SENSOR_DETECT_MODEL="haywoodsloan/ai-image-detector-deploy"
python backend\app\main.py
```

也可以保持 `auto`，服务会尝试加载模型，失败时回退到 demo 模式：

```powershell
$env:SENSOR_DETECT_MODE="auto"
python backend\app\main.py
```

## 目录结构

```text
backend/
  app/
    main.py
    services/
      detector.py
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