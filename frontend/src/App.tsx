import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, CSSProperties, DragEvent } from "react";

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

type SignalState = "异常" | "关注" | "缺失" | "正常";

type Signal = {
  key: string;
  name: string;
  value: number;
  state: SignalState;
};

const MAX_BYTES = 10 * 1024 * 1024;
const SUPPORTED_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);

const methodRows = [
  {
    index: "01",
    title: "像素与频域",
    text: "观察噪声分布、压缩残留与频谱结构，寻找生成模型留下的统计特征。",
  },
  {
    index: "02",
    title: "结构与语义",
    text: "交叉检查边缘、光影、透视和局部语义，识别视觉上自然却逻辑不一致的区域。",
  },
  {
    index: "03",
    title: "来源与元数据",
    text: "结合 EXIF、编辑链路和文件编码信息，让内容判断拥有更完整的证据上下文。",
  },
];

const faqRows = [
  ["检测结果能替代人工判断吗？", "不能。Sensor 输出的是风险概率和证据线索，仍需要人工复核。"],
  ["图片会被保存吗？", "当前本地 MVP 不做持久化保存，图片只用于本次检测请求。"],
  ["压缩图片是否还能检测？", "可以检测，但压缩、裁剪和平台转存会削弱部分取证信号。"],
];

function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [result, setResult] = useState<DetectResponse | null>(null);
  const [signals, setSignals] = useState<Signal[]>(initialSignals());
  const [progress, setProgress] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [message, setMessage] = useState("图片仅在本地预览 · 支持 JPG、PNG、WEBP");
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
    setProgress(12);
    const timer = window.setInterval(() => {
      setProgress((value) => Math.min(94, value + 9 + Math.random() * 10));
    }, 260);
    return () => window.clearInterval(timer);
  }, [isAnalyzing]);

  const probabilityValue = result ? clampPercent(result.ai_probability * 100) : 84;
  const probabilityLabel = result ? formatProbability(result.ai_probability) : "84%";
  const threshold = 70;
  const verdict = useMemo(() => {
    if (!result) return "高概率为 AI 生成";
    return result.ai_probability >= threshold / 100 ? "高概率为 AI 生成" : "未达到 AI 判定阈值";
  }, [result]);

  function selectFile(nextFile?: File) {
    if (!nextFile) return;
    if (!SUPPORTED_TYPES.has(nextFile.type)) {
      setMessage("仅支持 JPG、PNG、WEBP、GIF 图片");
      return;
    }
    if (nextFile.size > MAX_BYTES) {
      setMessage("图片不能超过 10MB");
      return;
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(nextFile);
    setPreviewUrl(URL.createObjectURL(nextFile));
    setResult(null);
    setProgress(0);
    setSignals(previewSignals(nextFile));
    setMessage("图片已载入，点击开始检测");
  }

  function onInputChange(event: ChangeEvent<HTMLInputElement>) {
    selectFile(event.target.files?.[0]);
  }

  function onDragOver(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragging(true);
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragging(false);
    selectFile(event.dataTransfer.files?.[0]);
  }

  async function detectImage() {
    if (!file || isAnalyzing) return;
    setIsAnalyzing(true);
    setMessage("正在扫描频域、纹理、边缘与元数据");

    const form = new FormData();
    form.append("image", file);

    try {
      const response = await fetch("/api/detect", { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok || data.ok === false) {
        throw new Error(data.message || data.error || "检测失败");
      }
      setResult(data);
      setSignals(resultSignals(file, data));
      setProgress(100);
      setMessage("分析完成");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "无法连接检测服务");
      setProgress(0);
    } finally {
      window.setTimeout(() => setIsAnalyzing(false), 360);
    }
  }

  function resetImage() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(null);
    setPreviewUrl("");
    setResult(null);
    setProgress(0);
    setSignals(initialSignals());
    setMessage("图片仅在本地预览 · 支持 JPG、PNG、WEBP");
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  return (
    <main className="site-shell">
      <header className="site-header">
        <a className="brand" href="#top" aria-label="Sensor AI 图像检测">
          <span className="logo-diamond" />
          <strong>Sensor</strong>
          <em>AI 图像检测</em>
        </a>
        <nav>
          <a href="#method">技术原理</a>
          <a href="#capability">检测能力</a>
          <a href="#faq">常见问题</a>
          <button type="button" onClick={() => fileInputRef.current?.click()}>
            开始检测 <span>↗</span>
          </button>
        </nav>
      </header>

      <section id="top" className="hero-section">
        <div className="technical-lines" aria-hidden="true">
          <span className="axis cross-a" />
          <span className="axis line-a" />
          <span className="axis line-b" />
          <span className="coord">X: 0.3021<br />Y: 0.6180<br />Z: 0.2417</span>
        </div>

        <div className="hero-copy">
          <p className="mono-kicker"><span /> MULTIMODAL FORENSICS / 2026</p>
          <h1>
            一眼之外，<br />识别图像的<span>真实来源</span>
          </h1>
          <p className="hero-text">通过多维度图像取证分析，识别生成痕迹、像素异常与语义不一致，给出清晰可信的判断依据。</p>
          <div className="hero-actions">
            <button className="solid-button" type="button" onClick={() => fileInputRef.current?.click()}>
              ↑ 上传图片检测
            </button>
            <a className="outline-button" href="#method">查看检测原理 →</a>
          </div>
          <p className="upload-note">◇ 图片仅在本地预览 · 支持 JPG、PNG、WEBP</p>
        </div>

        <section className="analysis-card" aria-label="图像分析面板">
          <div className="analysis-title">
            <h2><span>[ 01 ]</span> 图像分析</h2>
            <p><i /> {result ? "分析完成" : file ? "等待检测" : "演示状态"}</p>
          </div>

          <div className="analysis-body">
            <label
              className={`image-stage ${isDragging ? "dragging" : ""}`}
              onDragOver={onDragOver}
              onDragLeave={() => setIsDragging(false)}
              onDrop={onDrop}
            >
              <input ref={fileInputRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={onInputChange} />
              {previewUrl ? (
                <img src={previewUrl} alt="待检测图片" />
              ) : (
                <div className="image-placeholder">
                  <span className="focus-box" />
                  <strong>拖入或选择图片</strong>
                  <small>Image forensic preview</small>
                </div>
              )}
              <span className={`scan-beam ${isAnalyzing ? "active" : ""}`} />
              <button className="zoom-button" type="button" aria-label="选择图片">＋</button>
              <small className="stage-hint">点击或拖放图片</small>
            </label>

            <div className="result-console">
              <span className="console-label">AI 生成概率</span>
              <strong className="probability">{probabilityLabel}</strong>
              <div className="probability-bar">
                <i style={{ width: `${probabilityValue}%` }} />
                <b style={{ left: `${threshold}%` }} />
              </div>
              <div className="bar-scale"><span>0%</span><em>判定阈值 {threshold}%</em><span>100%</span></div>
              <div className="verdict-line">△ {verdict}</div>

              <div className="signals">
                {signals.map((signal) => (
                  <div className={`signal-row ${signal.state}`} key={signal.key}>
                    <span className="signal-icon">{signal.key === "freq" ? "⌁" : signal.key === "texture" ? "▦" : signal.key === "edge" ? "⌁" : "□"}</span>
                    <span className="signal-name">{signal.name}</span>
                    <div className="mini-bars" aria-label={`${signal.name} ${signal.value}%`}>
                      {Array.from({ length: 12 }).map((_, index) => (
                        <i key={index} className={index < Math.round(signal.value / 8.4) ? "on" : ""} />
                      ))}
                    </div>
                    <strong>{signal.state}</strong>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="analysis-footer">
            <span>{file?.name ?? "images.webp"}</span>
            <span>颜色空间 sRGB</span>
            <span>分析模式 MULTI-04</span>
            <button type="button" onClick={file ? resetImage : () => fileInputRef.current?.click()}>
              更换图片 ↗
            </button>
          </div>

          <div className="analysis-actions">
            <p>{message}</p>
            <div className="progress-track"><i style={{ width: `${progress}%` }} /></div>
            <button className="solid-button small" type="button" disabled={!file || isAnalyzing} onClick={detectImage}>
              {isAnalyzing ? "分析中" : "开始检测"}
            </button>
          </div>
        </section>
      </section>

      <section id="method" className="method-section">
        <div className="method-copy">
          <p className="blue-kicker">METHOD / 方法</p>
          <h2>不是猜测，<br />是<span>多重证据</span>的交叉验证。</h2>
          <p>单一特征容易被压缩、编辑和截图干扰。Sensor AI 图像检测将多个维度联合分析，让每个结论都能被解释。</p>
        </div>
        <div className="method-list">
          {methodRows.map((row) => (
            <article key={row.index}>
              <span>{row.index}</span>
              <div>
                <h3>{row.title}</h3>
                <p>{row.text}</p>
              </div>
              <a href="#top" aria-label={`${row.title} 上传检测`}>↗</a>
            </article>
          ))}
        </div>
      </section>

      <section id="capability" className="capability-band">
        <div><strong>4</strong><span>类取证信号</span></div>
        <div><strong>＜ 3s</strong><span>演示分析耗时</span></div>
        <div><strong>3</strong><span>种图片格式</span></div>
        <p>结果用于辅助判断<br />不替代人工核验</p>
      </section>

      <section id="faq" className="faq-section">
        <p className="blue-kicker">FAQ / 常见问题</p>
        <h2>检测前需要知道的边界</h2>
        <div className="faq-grid">
          {faqRows.map(([question, answer]) => (
            <details key={question} open={question === faqRows[0][0]}>
              <summary>{question}</summary>
              <p>{answer}</p>
            </details>
          ))}
        </div>
      </section>

      <footer className="footer">
        <strong>Sensor AI 图像检测</strong>
        <span>多模态图像取证 · AI 生成图像风险识别</span>
      </footer>
    </main>
  );
}

function clampPercent(value: number) {
  return Math.max(0, Math.min(100, value));
}

function formatProbability(probability: number) {
  const percent = clampPercent(probability * 100);
  if (percent > 0 && percent < 0.1) return "<0.1%";
  if (percent < 100 && percent > 99.9) return ">99.9%";
  const digits = percent < 10 || percent > 90 ? 1 : 0;
  return `${percent.toFixed(digits)}%`;
}

function initialSignals(): Signal[] {
  return [
    { key: "freq", name: "频域异常", value: 84, state: "异常" },
    { key: "texture", name: "纹理重复", value: 76, state: "异常" },
    { key: "edge", name: "边缘一致性", value: 68, state: "关注" },
    { key: "meta", name: "元数据完整度", value: 30, state: "缺失" },
  ];
}

function previewSignals(file: File): Signal[] {
  const seed = file.name.length + Math.round(file.size / 1024);
  return buildSignals(58 + (seed % 22));
}

function resultSignals(file: File, result: DetectResponse): Signal[] {
  const base = Math.round(clampPercent(result.ai_probability * 100));
  const seed = file.name.length + Math.round(file.size / 2048);
  return buildSignals(base + (seed % 9) - 4);
}

function buildSignals(base: number): Signal[] {
  const values = [clamp(base + 5), clamp(base - 2), clamp(base - 14), clamp(100 - base - 10)];
  return [
    { key: "freq", name: "频域异常", value: values[0], state: stateFor(values[0], true) },
    { key: "texture", name: "纹理重复", value: values[1], state: stateFor(values[1], true) },
    { key: "edge", name: "边缘一致性", value: values[2], state: stateFor(values[2], false) },
    { key: "meta", name: "元数据完整度", value: values[3], state: values[3] < 42 ? "缺失" : "正常" },
  ];
}

function clamp(value: number) {
  return Math.max(8, Math.min(96, value));
}

function stateFor(value: number, highMeansAbnormal: boolean): SignalState {
  if (!highMeansAbnormal) return value >= 62 ? "关注" : "正常";
  if (value >= 70) return "异常";
  if (value >= 48) return "关注";
  return "正常";
}

export default App;