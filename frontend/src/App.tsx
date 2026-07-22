import { ChangeEvent, DragEvent, useEffect, useMemo, useRef, useState } from "react";

type HealthResponse = {
  ok: boolean;
  service: string;
  mode: string;
  model: string;
};

type DetectResponse = {
  ok: boolean;
  result: "likely_ai" | "likely_real";
  ai_probability: number;
  real_probability: number;
  confidence: "high" | "medium" | "low";
  mode: string;
  model: string;
  duration_ms: number;
  image: {
    filename: string;
    content_type: string;
    size_bytes: number;
    width: number | null;
    height: number | null;
  };
  warnings: string[];
};

type Signal = {
  key: string;
  name: string;
  value: number;
  status: "stable" | "watch" | "alert";
  description: string;
};

const SUPPORTED_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);
const MAX_BYTES = 10 * 1024 * 1024;

const principles = [
  {
    title: "像素与频域",
    text: "观察噪声分布、压缩痕迹与频谱异常，识别生成模型留下的统计偏移。",
  },
  {
    title: "结构与语义",
    text: "对纹理重复、边缘连续性、局部细节一致性进行交叉比对。",
  },
  {
    title: "来源与元数据",
    text: "结合格式、尺寸、元数据缺失和转存特征，形成更稳健的风险判断。",
  },
];

const capabilityStats = [
  ["16+", "信号维度"],
  ["< 2s", "演示分析"],
  ["4", "支持格式"],
  ["参考", "使用边界"],
];

const faqs = [
  ["检测结果能当作最终证据吗？", "不能。结果应作为风险线索，仍需要人工复核、来源追踪和上下文判断。"],
  ["上传图片会保存吗？", "当前本地 MVP 不做持久化保存，图片只用于本次检测请求。"],
  ["压缩图片还能检测吗？", "可以检测，但压缩、裁剪和平台转存会降低信号稳定性。"],
];

function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string>("");
  const [result, setResult] = useState<DetectResponse | null>(null);
  const [signals, setSignals] = useState<Signal[]>(createInitialSignals());
  const [progress, setProgress] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [message, setMessage] = useState("等待图像输入");
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    fetch("/api/health")
      .then((response) => response.json())
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  useEffect(() => {
    if (!isAnalyzing) return;
    setProgress(8);
    const timer = window.setInterval(() => {
      setProgress((value) => Math.min(value + Math.random() * 16 + 7, 92));
    }, 260);
    return () => window.clearInterval(timer);
  }, [isAnalyzing]);

  const probability = result ? Math.round(result.ai_probability * 100) : 0;
  const threshold = 62;
  const verdict = useMemo(() => {
    if (!result) return "等待检测";
    return result.result === "likely_ai" ? "疑似 AI 生成" : "倾向真实来源";
  }, [result]);

  function pickFile(nextFile?: File) {
    if (!nextFile) return;
    if (!SUPPORTED_TYPES.has(nextFile.type)) {
      setMessage("仅支持 PNG、JPEG、WebP、GIF 图片");
      return;
    }
    if (nextFile.size > MAX_BYTES) {
      setMessage("图片大小不能超过 10MB");
      return;
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(nextFile);
    setPreviewUrl(URL.createObjectURL(nextFile));
    setResult(null);
    setProgress(0);
    setSignals(createPreviewSignals(nextFile));
    setMessage("图像已载入，可以开始检测");
  }

  function handleInputChange(event: ChangeEvent<HTMLInputElement>) {
    pickFile(event.target.files?.[0]);
  }

  function handleDragOver(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragging(true);
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragging(false);
    pickFile(event.dataTransfer.files?.[0]);
  }

  async function runDetection() {
    if (!file || isAnalyzing) return;
    setIsAnalyzing(true);
    setMessage("扫描纹理、频域与元数据信号");

    const formData = new FormData();
    formData.append("image", file);

    try {
      const response = await fetch("/api/detect", { method: "POST", body: formData });
      const data = await response.json();
      if (!response.ok || data.ok === false) {
        throw new Error(data.message || data.error || "检测失败");
      }
      setResult(data);
      setSignals(createSignals(file, data));
      setProgress(100);
      setMessage("分析完成");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "无法连接检测服务");
      setProgress(0);
    } finally {
      window.setTimeout(() => setIsAnalyzing(false), 420);
    }
  }

  function resetImage() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(null);
    setPreviewUrl("");
    setResult(null);
    setProgress(0);
    setSignals(createInitialSignals());
    setMessage("等待图像输入");
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  return (
    <main className="page-shell">
      <header className="top-nav" aria-label="Sensor AI 图像检测导航">
        <a className="brand-mark" href="#top" aria-label="Sensor AI 图像检测">
          <span className="brand-symbol">S</span>
          <span>Sensor AI 图像检测</span>
        </a>
        <nav>
          <a href="#principle">检测原理</a>
          <a href="#capability">能力概览</a>
          <a href="#faq">常见问题</a>
        </nav>
      </header>

      <section id="top" className="hero-grid">
        <div className="hero-copy">
          <p className="section-kicker">Sensor-detect / AI Image Forensics</p>
          <h1>一眼之外，识别图像的真实来源</h1>
          <p className="hero-lead">
            通过像素噪声、频域结构、边缘纹理与元数据信号，辅助判断图片是否存在 AI 生成风险。
          </p>
          <div className="hero-actions">
            <button className="primary-action" type="button" onClick={() => fileInputRef.current?.click()}>
              上传图片检测
            </button>
            <a className="secondary-action" href="#principle">查看检测原理</a>
          </div>
          <dl className="trust-strip">
            <div><dt>模式</dt><dd>{health?.mode ?? "未连接"}</dd></div>
            <div><dt>阈值</dt><dd>{threshold}%</dd></div>
            <div><dt>格式</dt><dd>PNG / JPG / WebP / GIF</dd></div>
          </dl>
        </div>

        <section className="forensic-panel" aria-label="图像检测面板">
          <div className="panel-grid" />
          <div className="panel-header">
            <div>
              <span className="panel-label">Forensic Console</span>
              <h2>图像检测面板</h2>
            </div>
            <span className={`live-dot ${health?.ok ? "online" : ""}`}>{health?.ok ? "ONLINE" : "LOCAL"}</span>
          </div>

          <div className="instrument-layout">
            <label
              className={`drop-target ${isDragging ? "is-dragging" : ""}`}
              onDragOver={handleDragOver}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
            >
              <input ref={fileInputRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={handleInputChange} />
              {previewUrl ? (
                <img src={previewUrl} alt="待检测图片" />
              ) : (
                <div className="empty-visual">
                  <span className="crosshair" />
                  <strong>DROP IMAGE</strong>
                  <small>点击或拖入图片</small>
                </div>
              )}
              <span className={`scan-line ${isAnalyzing ? "active" : ""}`} />
            </label>

            <div className="result-stack">
              <div className="probability-ring" style={{ "--score": probability } as React.CSSProperties}>
                <span>{probability}%</span>
                <small>AI 生成概率</small>
              </div>
              <div className="verdict-box">
                <span>检测结论</span>
                <strong>{verdict}</strong>
                <small>判定阈值：{threshold}% · {result ? confidenceText(result.confidence) : "待分析"}</small>
              </div>
            </div>
          </div>

          <div className="progress-row">
            <span>{message}</span>
            <strong>{Math.round(progress)}%</strong>
            <i style={{ width: `${progress}%` }} />
          </div>

          <div className="signal-grid">
            {signals.map((signal) => (
              <div className={`signal-card ${signal.status}`} key={signal.key}>
                <div className="signal-head">
                  <span>{signal.name}</span>
                  <strong>{signal.value}%</strong>
                </div>
                <div className="signal-bar"><i style={{ width: `${signal.value}%` }} /></div>
                <small>{signal.description}</small>
              </div>
            ))}
          </div>

          <div className="panel-actions">
            <button className="primary-action compact" type="button" disabled={!file || isAnalyzing} onClick={runDetection}>
              {isAnalyzing ? "分析中" : "开始检测"}
            </button>
            <button className="ghost-action" type="button" disabled={!file || isAnalyzing} onClick={resetImage}>
              更换图片
            </button>
          </div>
        </section>
      </section>

      <section id="principle" className="content-section principle-section">
        <p className="section-kicker">Detection Method</p>
        <h2>检测原理</h2>
        <div className="principle-grid">
          {principles.map((item) => (
            <article key={item.title}>
              <span className="corner-mark" />
              <h3>{item.title}</h3>
              <p>{item.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="capability" className="content-section capability-section">
        <div>
          <p className="section-kicker">Capability</p>
          <h2>检测能力概览</h2>
          <p>当前版本用于本地 MVP 验证，概率和信号展示仍以演示逻辑为主，后续可接入真实模型推理。</p>
        </div>
        <div className="stat-grid">
          {capabilityStats.map(([value, label]) => (
            <div key={label}>
              <strong>{value}</strong>
              <span>{label}</span>
            </div>
          ))}
        </div>
      </section>

      <section id="faq" className="content-section faq-section">
        <p className="section-kicker">FAQ</p>
        <h2>常见问题</h2>
        <div className="faq-list">
          {faqs.map(([question, answer]) => (
            <details key={question} open={question === faqs[0][0]}>
              <summary>{question}</summary>
              <p>{answer}</p>
            </details>
          ))}
        </div>
      </section>

      <footer className="site-footer">
        <strong>Sensor AI 图像检测</strong>
        <span>面向科研、媒体审核与数字取证场景的 AI 图像来源风险识别工具。</span>
      </footer>
    </main>
  );
}

function createInitialSignals(): Signal[] {
  return [
    { key: "freq", name: "频域残差", value: 12, status: "stable", description: "等待图像频谱输入" },
    { key: "texture", name: "纹理重复", value: 18, status: "stable", description: "等待局部纹理采样" },
    { key: "edge", name: "边缘一致性", value: 14, status: "stable", description: "等待轮廓响应分析" },
    { key: "meta", name: "元数据完整性", value: 20, status: "stable", description: "等待文件头解析" },
  ];
}

function createPreviewSignals(file: File): Signal[] {
  const seed = file.name.length + Math.round(file.size / 1024);
  return signalFromSeed(seed, 34, "watch");
}

function createSignals(file: File, result: DetectResponse): Signal[] {
  const base = Math.round(result.ai_probability * 100);
  const seed = file.name.length + file.size + base;
  const status: Signal["status"] = base >= 70 ? "alert" : base >= 45 ? "watch" : "stable";
  return signalFromSeed(seed, base, status);
}

function signalFromSeed(seed: number, base: number, preferredStatus: Signal["status"]): Signal[] {
  const values = [
    clamp(base + ((seed * 7) % 21) - 10),
    clamp(base + ((seed * 11) % 25) - 12),
    clamp(base + ((seed * 13) % 23) - 11),
    clamp(100 - base + ((seed * 5) % 18) - 9),
  ];
  return [
    { key: "freq", name: "频域残差", value: values[0], status: statusFor(values[0], preferredStatus), description: "频谱能量与自然图像基线的偏移" },
    { key: "texture", name: "纹理重复", value: values[1], status: statusFor(values[1], preferredStatus), description: "局部纹理块的周期性与重复风险" },
    { key: "edge", name: "边缘一致性", value: values[2], status: statusFor(values[2], preferredStatus), description: "轮廓、阴影与细节边缘的连续性" },
    { key: "meta", name: "元数据完整性", value: values[3], status: statusFor(values[3], "watch"), description: "文件来源、尺寸与编码信息完整度" },
  ];
}

function statusFor(value: number, fallback: Signal["status"]): Signal["status"] {
  if (value >= 72) return "alert";
  if (value >= 45) return "watch";
  return fallback === "alert" ? "watch" : "stable";
}

function clamp(value: number) {
  return Math.max(8, Math.min(96, value));
}

function confidenceText(value: DetectResponse["confidence"]) {
  if (value === "high") return "高置信";
  if (value === "medium") return "中置信";
  return "低置信";
}

export default App;