const state = {
  file: null,
  previewUrl: null,
};

const els = {
  imageInput: document.getElementById("imageInput"),
  dropZone: document.getElementById("dropZone"),
  previewWrap: document.getElementById("previewWrap"),
  previewImage: document.getElementById("previewImage"),
  fileName: document.getElementById("fileName"),
  fileSize: document.getElementById("fileSize"),
  detectButton: document.getElementById("detectButton"),
  clearButton: document.getElementById("clearButton"),
  serviceMode: document.getElementById("serviceMode"),
  emptyState: document.getElementById("emptyState"),
  resultContent: document.getElementById("resultContent"),
  duration: document.getElementById("duration"),
  verdict: document.getElementById("verdict"),
  confidence: document.getElementById("confidence"),
  aiScoreText: document.getElementById("aiScoreText"),
  realScoreText: document.getElementById("realScoreText"),
  aiMeter: document.getElementById("aiMeter"),
  realMeter: document.getElementById("realMeter"),
  modeText: document.getElementById("modeText"),
  modelText: document.getElementById("modelText"),
  dimensionText: document.getElementById("dimensionText"),
  typeText: document.getElementById("typeText"),
  warnings: document.getElementById("warnings"),
};

const MAX_BYTES = 10 * 1024 * 1024;
const SUPPORTED_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function formatPercent(value) {
  return `${Math.round(value * 100)}%`;
}

function setSelectedFile(file) {
  if (!file) return;

  if (!SUPPORTED_TYPES.has(file.type)) {
    showError("仅支持 PNG、JPEG、WebP、GIF 图片。");
    return;
  }

  if (file.size > MAX_BYTES) {
    showError("图片不能超过 10MB。");
    return;
  }

  if (state.previewUrl) {
    URL.revokeObjectURL(state.previewUrl);
  }

  state.file = file;
  state.previewUrl = URL.createObjectURL(file);
  els.previewImage.src = state.previewUrl;
  els.fileName.textContent = file.name;
  els.fileSize.textContent = formatBytes(file.size);
  els.previewWrap.classList.remove("hidden");
  els.detectButton.disabled = false;
  els.clearButton.disabled = false;
}

function clearAll() {
  if (state.previewUrl) {
    URL.revokeObjectURL(state.previewUrl);
  }
  state.file = null;
  state.previewUrl = null;
  els.imageInput.value = "";
  els.previewImage.removeAttribute("src");
  els.previewWrap.classList.add("hidden");
  els.detectButton.disabled = true;
  els.clearButton.disabled = true;
  els.emptyState.classList.remove("hidden");
  els.resultContent.classList.add("hidden");
  els.duration.textContent = "等待上传";
}

function showError(message) {
  els.emptyState.textContent = message;
  els.emptyState.classList.remove("hidden");
  els.resultContent.classList.add("hidden");
  els.duration.textContent = "检测失败";
}

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    els.serviceMode.textContent = `${data.mode} 模式`;
    els.serviceMode.classList.add("ready");
  } catch {
    els.serviceMode.textContent = "检测服务未连接";
    els.serviceMode.classList.remove("ready");
  }
}

async function detectImage() {
  if (!state.file) return;

  els.detectButton.disabled = true;
  els.detectButton.textContent = "检测中";
  els.duration.textContent = "检测中";

  const form = new FormData();
  form.append("image", state.file);

  try {
    const response = await fetch("/api/detect", {
      method: "POST",
      body: form,
    });
    const data = await response.json();

    if (!response.ok || data.ok === false) {
      showError(data.message || data.error || "检测失败。");
      return;
    }

    renderResult(data);
  } catch {
    showError("无法连接后端检测服务。");
  } finally {
    els.detectButton.disabled = false;
    els.detectButton.textContent = "开始检测";
  }
}

function renderResult(data) {
  const aiPercent = formatPercent(data.ai_probability);
  const realPercent = formatPercent(data.real_probability);
  const dimension = data.image.width && data.image.height
    ? `${data.image.width} × ${data.image.height}`
    : "未识别";

  els.emptyState.classList.add("hidden");
  els.resultContent.classList.remove("hidden");
  els.duration.textContent = `${data.duration_ms} ms`;
  els.verdict.textContent = data.result === "likely_ai" ? "更像 AI 生成" : "更像真实图片";
  els.confidence.textContent = confidenceText(data.confidence);
  els.aiScoreText.textContent = aiPercent;
  els.realScoreText.textContent = realPercent;
  els.aiMeter.style.width = aiPercent;
  els.realMeter.style.width = realPercent;
  els.modeText.textContent = data.mode;
  els.modelText.textContent = data.model;
  els.dimensionText.textContent = dimension;
  els.typeText.textContent = data.image.content_type;
  els.warnings.innerHTML = "";

  for (const warning of data.warnings || []) {
    const item = document.createElement("li");
    item.textContent = warning;
    els.warnings.appendChild(item);
  }
}

function confidenceText(confidence) {
  if (confidence === "high") return "高置信度";
  if (confidence === "medium") return "中置信度";
  return "低置信度";
}

els.imageInput.addEventListener("change", (event) => {
  setSelectedFile(event.target.files[0]);
});

els.clearButton.addEventListener("click", clearAll);
els.detectButton.addEventListener("click", detectImage);

els.dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  els.dropZone.classList.add("dragging");
});

els.dropZone.addEventListener("dragleave", () => {
  els.dropZone.classList.remove("dragging");
});

els.dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  els.dropZone.classList.remove("dragging");
  setSelectedFile(event.dataTransfer.files[0]);
});

checkHealth();
