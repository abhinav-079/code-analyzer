// Code Quality Analyzer — Multi-Language Frontend Application

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// Global state
let currentAnalysisData = null;
let currentProjectData = null;
let isProjectMode = false;
let currentFileIndex = 0;
let currentDiagFilter = "all";

let projectFiles = [
  { name: "main.c", code: window.SAMPLES ? window.SAMPLES["sample_metrics"] : "", language: "c" },
  { name: "process.py", code: window.SAMPLES ? window.SAMPLES["python_sample"] : "", language: "python" },
  { name: "service.java", code: window.SAMPLES ? window.SAMPLES["java_sample"] : "", language: "java" }
];

// SVG ViewBox and Pan/Zoom state for CFG
let cfgViewBox = { x: 0, y: 0, w: 800, h: 600 };
let cfgInitialViewBox = { x: 0, y: 0, w: 800, h: 600 };
let isDraggingSvg = false;
let dragStart = { x: 0, y: 0 };

// -------------------------------------------------------------
// Pipeline Animation (9 stages)
// -------------------------------------------------------------
function setStage(activeIndex) {
  document.querySelectorAll(".stage").forEach((s, i) => s.classList.toggle("active", i <= activeIndex));
  document.querySelectorAll(".stage-link").forEach((l, i) => l.classList.toggle("active", i < activeIndex));
}

function runPipelineAnimation() {
  setStage(-1);
  for (let i = 0; i < 9; i++) {
    setTimeout(() => setStage(i), i * 60);
  }
}

// -------------------------------------------------------------
// Tab Switching Helper
// -------------------------------------------------------------
function switchTab(tabName) {
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
  const btn = document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
  const panel = document.getElementById(`tab-${tabName}`);
  if (btn) btn.classList.add("active");
  if (panel) panel.classList.add("active");

  if (tabName === "ast" && currentAstMode === "graph" && currentAnalysisData && currentAnalysisData.ast) {
    renderAstGraph(currentAnalysisData.ast);
  }
}

document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

// -------------------------------------------------------------
// Gutter / Line Numbers
// -------------------------------------------------------------
const srcEditor = document.getElementById("src");
function updateGutter() {
  const gutter = document.getElementById("editorGutter");
  const lineCount = srcEditor.value.split("\n").length;
  let linesHtml = "";
  for (let i = 1; i <= lineCount; i++) {
    linesHtml += `<div>${i}</div>`;
  }
  gutter.innerHTML = linesHtml;
  gutter.scrollTop = srcEditor.scrollTop;
}

srcEditor.addEventListener("input", updateGutter);
srcEditor.addEventListener("scroll", () => {
  document.getElementById("editorGutter").scrollTop = srcEditor.scrollTop;
});

// Highlight / Jump to specific line in editor
function jumpToLine(lineNumber) {
  const lines = srcEditor.value.split("\n");
  if (lineNumber < 1 || lineNumber > lines.length) return;
  let charIndex = 0;
  for (let i = 0; i < lineNumber - 1; i++) {
    charIndex += lines[i].length + 1;
  }
  const endChar = charIndex + lines[lineNumber - 1].length;
  srcEditor.focus();
  srcEditor.setSelectionRange(charIndex, endChar);

  // Scroll to roughly that line
  const approxLineHeight = 22;
  srcEditor.scrollTop = Math.max(0, (lineNumber - 4) * approxLineHeight);
}

// -------------------------------------------------------------
// Language Selection & Detection
// -------------------------------------------------------------
const langSelect = document.getElementById("langSelect");
const currentLangTag = document.getElementById("currentLangTag");

function updateLangTag(lang) {
  const display = lang ? lang.toUpperCase() : "AUTO";
  currentLangTag.textContent = `Language: ${display}`;
}

langSelect.addEventListener("change", () => {
  updateLangTag(langSelect.value);
  analyzeCode();
});

// -------------------------------------------------------------
// Single vs Multi-File Project Mode
// -------------------------------------------------------------
const singleModeBtn = document.getElementById("singleFileModeBtn");
const multiModeBtn = document.getElementById("multiFileModeBtn");
const fileTabsBar = document.getElementById("fileTabsBar");
const analyzeProjectBtn = document.getElementById("analyzeProjectBtn");
const analyzeBtn = document.getElementById("analyzeBtn");
const projectTabBtn = document.getElementById("projectTabBtn");

singleModeBtn.addEventListener("click", () => {
  isProjectMode = false;
  singleModeBtn.classList.add("active");
  multiModeBtn.classList.remove("active");
  fileTabsBar.style.display = "none";
  analyzeProjectBtn.style.display = "none";
  analyzeBtn.style.display = "inline-block";
  projectTabBtn.style.display = "none";
});

multiModeBtn.addEventListener("click", () => {
  isProjectMode = true;
  multiModeBtn.classList.add("active");
  singleModeBtn.classList.remove("active");
  fileTabsBar.style.display = "flex";
  analyzeProjectBtn.style.display = "inline-block";
  projectTabBtn.style.display = "inline-block";
  renderFileTabs();
});

function renderFileTabs() {
  const list = document.getElementById("fileTabList");
  list.innerHTML = "";
  projectFiles.forEach((file, idx) => {
    const tab = document.createElement("div");
    tab.className = "file-tab" + (idx === currentFileIndex ? " active" : "");
    tab.innerHTML = `<span>${escapeHtml(file.name)}</span>`;
    if (projectFiles.length > 1) {
      const close = document.createElement("span");
      close.className = "close-file-btn";
      close.innerHTML = "&times;";
      close.onclick = (e) => {
        e.stopPropagation();
        removeFile(idx);
      };
      tab.appendChild(close);
    }
    tab.onclick = () => switchFile(idx);
    list.appendChild(tab);
  });
}

function switchFile(idx) {
  if (projectFiles[currentFileIndex]) {
    projectFiles[currentFileIndex].code = srcEditor.value;
  }
  currentFileIndex = idx;
  srcEditor.value = projectFiles[idx].code;
  if (projectFiles[idx].language) {
    langSelect.value = projectFiles[idx].language;
    updateLangTag(projectFiles[idx].language);
  }
  updateGutter();
  renderFileTabs();
  analyzeCode();
}

function removeFile(idx) {
  if (projectFiles.length <= 1) return;
  projectFiles.splice(idx, 1);
  if (currentFileIndex >= projectFiles.length) {
    currentFileIndex = projectFiles.length - 1;
  }
  srcEditor.value = projectFiles[currentFileIndex].code;
  updateGutter();
  renderFileTabs();
}

document.getElementById("addFileBtn").addEventListener("click", () => {
  const name = prompt("Enter new filename (e.g. util.py, Math.java, helper.js, app.cpp):", `script_${projectFiles.length + 1}.c`);
  if (!name) return;
  const ext = name.split(".").pop().toLowerCase();
  let defaultLang = "c";
  if (ext === "py") defaultLang = "python";
  else if (ext === "java") defaultLang = "java";
  else if (ext === "js") defaultLang = "javascript";
  else if (["cpp", "hpp", "cc"].includes(ext)) defaultLang = "cpp";

  projectFiles.push({
    name: name.trim(),
    code: `// ${name}\nint run() {\n    return 0;\n}\n`,
    language: defaultLang
  });
  switchFile(projectFiles.length - 1);
});

// -------------------------------------------------------------
// Demos Drawer & Sample Selectors
// -------------------------------------------------------------
const toggleDemosBtn = document.getElementById("toggleDemosBtn");
const closeDemosBtn = document.getElementById("closeDemosBtn");
const demosPanel = document.getElementById("demosPanel");

function toggleDemos() {
  if (!demosPanel) return;
  const isHidden = demosPanel.style.display === "none" || !demosPanel.style.display;
  demosPanel.style.display = isHidden ? "block" : "none";
  if (toggleDemosBtn) {
    toggleDemosBtn.classList.toggle("active", isHidden);
    toggleDemosBtn.textContent = isHidden ? "⚡ Demos & Presets ▴" : "⚡ Demos & Presets ▾";
  }
}

function closeDemos() {
  if (!demosPanel) return;
  demosPanel.style.display = "none";
  if (toggleDemosBtn) {
    toggleDemosBtn.classList.remove("active");
    toggleDemosBtn.textContent = "⚡ Demos & Presets ▾";
  }
}

if (toggleDemosBtn) {
  toggleDemosBtn.addEventListener("click", toggleDemos);
}
if (closeDemosBtn) {
  closeDemosBtn.addEventListener("click", closeDemos);
}

document.querySelectorAll(".showcase-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    const sampleKey = btn.dataset.sample;
    const targetTab = btn.dataset.tab;
    const lang = btn.dataset.lang;

    closeDemos();

    if (window.SAMPLES && window.SAMPLES[sampleKey]) {
      srcEditor.value = window.SAMPLES[sampleKey];
      document.getElementById("sampleSelect").value = sampleKey;
      if (lang) {
        langSelect.value = lang;
        updateLangTag(lang);
      }
      updateGutter();
      analyzeCode().then(() => {
        if (targetTab) switchTab(targetTab);
      });
    }
  });
});

document.getElementById("sampleSelect").addEventListener("change", (e) => {
  const key = e.target.value;
  if (window.SAMPLES && window.SAMPLES[key]) {
    srcEditor.value = window.SAMPLES[key];
    if (key.includes("python")) langSelect.value = "python";
    else if (key.includes("java")) langSelect.value = "java";
    else if (key.includes("js")) langSelect.value = "javascript";
    else if (key.includes("cpp")) langSelect.value = "cpp";
    else langSelect.value = "c";
    updateLangTag(langSelect.value);
    updateGutter();
    analyzeCode();
  }
});

// -------------------------------------------------------------
// Error Handling
// -------------------------------------------------------------
function showError(msg, stage) {
  const box = document.getElementById("errorBox");
  box.textContent = `Analysis Notice [${stage || "compiler"}]: ${msg}`;
  box.classList.add("show");
}

function clearError() {
  const box = document.getElementById("errorBox");
  box.textContent = "";
  box.classList.remove("show");
}

// -------------------------------------------------------------
// Metrics & Functions Rendering
// -------------------------------------------------------------
function renderMetrics(m, quality) {
  const grid = document.getElementById("metricGrid");
  const prog = m.program || m;

  const cards = [
    ["Lines of Code", prog.loc, prog.loc > 80 ? "critical" : ""],
    ["Functions", prog.functions, ""],
    ["Variables", prog.variables, ""],
    ["If Statements", prog.ifs, ""],
    ["Loops", (prog.fors || 0) + (prog.whiles || 0), ""],
    ["Return Stmts", prog.returns, ""],
    ["Max Nesting", prog.maxNesting, prog.maxNesting >= 3 ? "flag" : "good"],
    ["Total Cyclomatic CC", prog.cyclomatic, prog.cyclomatic > 10 ? "critical" : "good"],
    ["Avg Function CC", prog.avgCyclomatic || prog.cyclomatic, (prog.avgCyclomatic || prog.cyclomatic) > 5 ? "flag" : "good"],
    ["Quality Score", (quality ? quality.score : 100) + "/100", quality && quality.score < 70 ? "flag" : "good"],
  ];

  grid.innerHTML = cards.map(([label, val, flagClass]) => `
    <div class="metric-card ${flagClass}">
      <div class="num">${val}</div>
      <div class="label">${label}</div>
    </div>
  `).join("");

  // Most complex function card
  const mostComplexCard = document.getElementById("mostComplexCard");
  const mostComplexBody = document.getElementById("mostComplexBody");
  if (prog.mostComplexFunction && prog.maxFunctionComplexity > 1) {
    mostComplexBody.textContent = `Function '${prog.mostComplexFunction}' has the highest cyclomatic complexity of ${prog.maxFunctionComplexity} (${prog.maxFunctionComplexity > 10 ? 'High' : prog.maxFunctionComplexity > 4 ? 'Moderate' : 'Low'}).`;
    mostComplexCard.style.display = "block";
  } else {
    mostComplexCard.style.display = "none";
  }

  // Per-function table
  const tbody = document.getElementById("functionsTableBody");
  tbody.innerHTML = "";
  const fList = m.perFunction || m.functionList || [];
  fList.forEach(fn => {
    const tr = document.createElement("tr");
    if (fn.isMostComplex) tr.className = "highlight-row";
    const badgeClass = fn.complexityLevel ? fn.complexityLevel.toLowerCase() : "low";
    tr.innerHTML = `
      <td>
        <strong>${escapeHtml(fn.name)}</strong>
        ${fn.isMostComplex ? '<span class="tag-badge most-complex">MOST COMPLEX</span>' : ''}
      </td>
      <td><code>${escapeHtml(fn.returnType || "def")}</code></td>
      <td>${fn.loc}</td>
      <td>${fn.paramCount}</td>
      <td>${fn.variables}</td>
      <td>${fn.maxNesting}</td>
      <td><strong>${fn.cyclomatic}</strong></td>
      <td><span class="tag-badge ${badgeClass}">${fn.complexityLevel}</span></td>
    `;
    tbody.appendChild(tr);
  });

  document.getElementById("metricsEmpty").style.display = "none";
  document.getElementById("metricsWrap").style.display = "block";
}

function renderQuickSummary(prog, quality, smellsCount) {
  const quick = document.getElementById("quickSummary");
  const q = quality || { score: 100, grade: "A", description: "Clean code" };
  const circle = document.getElementById("quickGrade");
  circle.textContent = q.grade;
  circle.className = `score-circle grade-${q.grade.toLowerCase()}`;
  document.getElementById("quickScore").textContent = q.score;
  document.getElementById("quickGradeDesc").textContent = q.description;
  document.getElementById("quickLoc").textContent = prog.loc;
  document.getElementById("quickCc").textContent = prog.cyclomatic;
  document.getElementById("quickSmells").textContent = smellsCount;
  quick.style.display = "flex";
}

// -------------------------------------------------------------
// CONTROL FLOW GRAPH (CFG) — Full Branching & Auto-Centering Layout
// -------------------------------------------------------------
function renderCfg(cfgs) {
  const select = document.getElementById("cfgFunctionSelect");
  select.innerHTML = "";
  const fnNames = Object.keys(cfgs || {});
  if (fnNames.length === 0) {
    document.getElementById("cfgEmpty").textContent = "No function definitions found to generate Control Flow Graph.";
    document.getElementById("cfgEmpty").style.display = "block";
    document.getElementById("cfgWrap").style.display = "none";
    return;
  }

  fnNames.forEach(name => {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    select.appendChild(opt);
  });

  select.onchange = () => drawCfgForFunction(cfgs[select.value]);
  drawCfgForFunction(cfgs[fnNames[0]]);

  document.getElementById("cfgEmpty").style.display = "none";
  document.getElementById("cfgWrap").style.display = "block";
}

function drawCfgForFunction(cfg) {
  if (!cfg) return;

  // Formula badge
  const e = cfg.edgeCount;
  const n = cfg.nodeCount;
  const cc = cfg.cyclomaticComplexity;
  document.getElementById("cfgFormulaBadge").innerHTML =
    `McCabe: <strong>M = E - N + 2P</strong> &rarr; ${e} - ${n} + 2(1) = <strong>${cc}</strong>`;

  const svg = document.getElementById("cfgSvg");
  svg.innerHTML = "";

  // Define Arrowhead Markers
  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  const markers = [
    ["arrow-default", "#9b1d3d"],
    ["arrow-true", "#48bb78"],
    ["arrow-false", "#f56565"],
    ["arrow-loop", "#ed8936"],
    ["arrow-return", "#9f7aea"]
  ];
  markers.forEach(([id, color]) => {
    const marker = document.createElementNS("http://www.w3.org/2000/svg", "marker");
    marker.setAttribute("id", id);
    marker.setAttribute("viewBox", "0 0 10 10");
    marker.setAttribute("refX", "8");
    marker.setAttribute("refY", "5");
    marker.setAttribute("markerWidth", "6");
    marker.setAttribute("markerHeight", "6");
    marker.setAttribute("orient", "auto-start-reverse");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", "M 0 1 L 9 5 L 0 9 z");
    path.setAttribute("fill", color);
    marker.appendChild(path);
    defs.appendChild(marker);
  });
  svg.appendChild(defs);

  // Group container for Pan & Zoom
  const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
  g.id = "cfgViewportGroup";
  svg.appendChild(g);

  // Layout Engine: Level and Column Calculation
  const nodes = cfg.nodes || [];
  const edges = cfg.edges || [];
  const blockW = 220;
  const lineH = 17;
  const horizSpacing = 280;
  const vertSpacing = 85;

  // Assign columns and levels based on structure
  const nodeLevels = {};
  const nodeCols = {};

  nodes.forEach((node, i) => {
    nodeLevels[node.id] = i;
    nodeCols[node.id] = 0;
  });

  // Assign branching columns
  edges.forEach(edge => {
    if (edge.type === "true" || edge.label === "True") {
      nodeCols[edge.target] = -1; // Left lane
    } else if (edge.type === "false" || edge.label === "False") {
      nodeCols[edge.target] = 1;  // Right lane
    }
  });

  // Position nodes
  const nodePositions = {};
  const centerX = 360;
  let currY = 40;

  nodes.forEach(node => {
    const instCount = (node.instructions || []).length;
    const blockH = Math.max(52, 36 + instCount * lineH);
    const colOffset = (nodeCols[node.id] || 0) * (blockW + 40);
    const posX = centerX + colOffset;

    nodePositions[node.id] = {
      x: posX,
      y: currY,
      w: blockW,
      h: blockH,
      node: node
    };
    currY += blockH + vertSpacing;
  });

  // Calculate overall bounding box for viewBox
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  Object.values(nodePositions).forEach(pos => {
    minX = Math.min(minX, pos.x - 40);
    maxX = Math.max(maxX, pos.x + pos.w + 40);
    minY = Math.min(minY, pos.y);
    maxY = Math.max(maxY, pos.y + pos.h);
  });

  const totalGraphW = Math.max(700, maxX - minX + 80);
  const totalGraphH = Math.max(500, maxY - minY + 100);

  // Auto-fit entire graph into SVG viewBox
  cfgInitialViewBox = {
    x: minX - 40,
    y: Math.max(0, minY - 30),
    w: totalGraphW,
    h: totalGraphH
  };
  cfgViewBox = { ...cfgInitialViewBox };
  updateSvgViewBox();

  // Draw Edges
  edges.forEach(edge => {
    const src = nodePositions[edge.source];
    const tgt = nodePositions[edge.target];
    if (!src || !tgt) return;

    let markerId = "arrow-default";
    let strokeColor = "#9b1d3d";
    if (edge.type === "true" || edge.label === "True") { markerId = "arrow-true"; strokeColor = "#48bb78"; }
    else if (edge.type === "false" || edge.label === "False") { markerId = "arrow-false"; strokeColor = "#f56565"; }
    else if (edge.type === "loop_back" || edge.label === "Loop") { markerId = "arrow-loop"; strokeColor = "#ed8936"; }
    else if (edge.type === "return" || edge.label === "Return") { markerId = "arrow-return"; strokeColor = "#9f7aea"; }

    const x1 = src.x + src.w / 2;
    const y1 = src.y + src.h;
    const x2 = tgt.x + tgt.w / 2;
    const y2 = tgt.y;

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");

    if (edge.type === "loop_back" || y2 < y1) {
      // Wide curved back-edge around the side
      const loopOffset = Math.min(src.x, tgt.x) - 70;
      path.setAttribute("d", `M ${src.x} ${src.y + 24} C ${loopOffset} ${src.y + 24}, ${loopOffset} ${tgt.y + 24}, ${tgt.x} ${tgt.y + 24}`);
    } else {
      // Smooth cubic bezier connector
      const midY = (y1 + y2) / 2;
      path.setAttribute("d", `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`);
    }

    path.setAttribute("fill", "none");
    path.setAttribute("stroke", strokeColor);
    path.setAttribute("stroke-width", "2");
    path.setAttribute("marker-end", `url(#${markerId})`);
    g.appendChild(path);

    // Label on edge
    if (edge.label && edge.label !== "fallthrough") {
      const lx = (x1 + x2) / 2 + (x2 < x1 ? -25 : 10);
      const ly = (y1 + y2) / 2;

      // Label background pill
      const labelBg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      labelBg.setAttribute("x", lx - 4);
      labelBg.setAttribute("y", ly - 11);
      labelBg.setAttribute("width", edge.label.length * 7 + 10);
      labelBg.setAttribute("height", 16);
      labelBg.setAttribute("rx", 4);
      labelBg.setAttribute("fill", "#101016");
      labelBg.setAttribute("stroke", strokeColor);
      labelBg.setAttribute("stroke-width", 1);
      g.appendChild(labelBg);

      const lbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
      lbl.setAttribute("x", lx + 1);
      lbl.setAttribute("y", ly + 1);
      lbl.setAttribute("fill", strokeColor);
      lbl.setAttribute("font-size", "10px");
      lbl.setAttribute("font-family", "'SF Pro Display', 'SF Pro Text', 'SF Pro', -apple-system, BlinkMacSystemFont, sans-serif");
      lbl.setAttribute("font-weight", "700");
      lbl.textContent = edge.label;
      g.appendChild(lbl);
    }
  });

  // Draw Block Nodes
  nodes.forEach(node => {
    const pos = nodePositions[node.id];
    let fill = "#14141c";
    let stroke = "#272733";
    let tagColor = "#9aa1bc";

    if (node.type === "entry") { fill = "#1a1016"; stroke = "#9b1d3d"; tagColor = "#9b1d3d"; }
    else if (node.type === "condition") { fill = "#2d2417"; stroke = "#ed8936"; tagColor = "#f6ad55"; }
    else if (node.type === "exit") { fill = "#271b33"; stroke = "#9f7aea"; tagColor = "#b794f4"; }
    else if (node.type === "join") { fill = "#182233"; stroke = "#4299e1"; tagColor = "#63b3ed"; }

    const nodeG = document.createElementNS("http://www.w3.org/2000/svg", "g");

    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", pos.x);
    rect.setAttribute("y", pos.y);
    rect.setAttribute("width", pos.w);
    rect.setAttribute("height", pos.h);
    rect.setAttribute("rx", "8");
    rect.setAttribute("fill", fill);
    rect.setAttribute("stroke", stroke);
    rect.setAttribute("stroke-width", "1.5");
    rect.setAttribute("filter", "drop-shadow(0px 3px 6px rgba(0,0,0,0.3))");
    nodeG.appendChild(rect);

    // Node Header
    const header = document.createElementNS("http://www.w3.org/2000/svg", "text");
    header.setAttribute("x", pos.x + 10);
    header.setAttribute("y", pos.y + 19);
    header.setAttribute("fill", tagColor);
    header.setAttribute("font-size", "11px");
    header.setAttribute("font-weight", "700");
    header.setAttribute("font-family", "'SF Pro Display', 'SF Pro Text', 'SF Pro', -apple-system, BlinkMacSystemFont, sans-serif");
    header.textContent = node.label || node.id;
    nodeG.appendChild(header);

    // Node Instructions
    (node.instructions || []).forEach((inst, iIdx) => {
      const lineTxt = document.createElementNS("http://www.w3.org/2000/svg", "text");
      lineTxt.setAttribute("x", pos.x + 12);
      lineTxt.setAttribute("y", pos.y + 38 + iIdx * lineH);
      lineTxt.setAttribute("fill", "#e2e8f0");
      lineTxt.setAttribute("font-size", "11px");
      lineTxt.setAttribute("font-family", "'SF Pro Display', 'SF Pro Text', 'SF Pro', -apple-system, BlinkMacSystemFont, sans-serif");
      lineTxt.textContent = inst.length > 27 ? inst.substring(0, 26) + "..." : inst;
      nodeG.appendChild(lineTxt);
    });

    g.appendChild(nodeG);
  });
}

function updateSvgViewBox() {
  const svg = document.getElementById("cfgSvg");
  if (svg) {
    svg.setAttribute("viewBox", `${cfgViewBox.x} ${cfgViewBox.y} ${cfgViewBox.w} ${cfgViewBox.h}`);
  }
}

// CFG Interactive Pan & Zoom Handlers
const cfgSvg = document.getElementById("cfgSvg");

cfgSvg.addEventListener("mousedown", (e) => {
  isDraggingSvg = true;
  dragStart = { x: e.clientX, y: e.clientY };
});

window.addEventListener("mousemove", (e) => {
  if (!isDraggingSvg) return;
  const dx = (e.clientX - dragStart.x) * (cfgViewBox.w / cfgSvg.clientWidth);
  const dy = (e.clientY - dragStart.y) * (cfgViewBox.h / cfgSvg.clientHeight);
  cfgViewBox.x -= dx;
  cfgViewBox.y -= dy;
  dragStart = { x: e.clientX, y: e.clientY };
  updateSvgViewBox();
});

window.addEventListener("mouseup", () => {
  isDraggingSvg = false;
});

cfgSvg.addEventListener("wheel", (e) => {
  e.preventDefault();
  const zoomFactor = e.deltaY > 0 ? 1.15 : 0.85;
  const mouseX = e.offsetX / cfgSvg.clientWidth;
  const mouseY = e.offsetY / cfgSvg.clientHeight;

  const newW = cfgViewBox.w * zoomFactor;
  const newH = cfgViewBox.h * zoomFactor;

  cfgViewBox.x += (cfgViewBox.w - newW) * mouseX;
  cfgViewBox.y += (cfgViewBox.h - newH) * mouseY;
  cfgViewBox.w = newW;
  cfgViewBox.h = newH;
  updateSvgViewBox();
});

document.getElementById("cfgZoomInBtn").addEventListener("click", () => {
  cfgViewBox.x += cfgViewBox.w * 0.1;
  cfgViewBox.y += cfgViewBox.h * 0.1;
  cfgViewBox.w *= 0.8;
  cfgViewBox.h *= 0.8;
  updateSvgViewBox();
});

document.getElementById("cfgZoomOutBtn").addEventListener("click", () => {
  cfgViewBox.x -= cfgViewBox.w * 0.125;
  cfgViewBox.y -= cfgViewBox.h * 0.125;
  cfgViewBox.w *= 1.25;
  cfgViewBox.h *= 1.25;
  updateSvgViewBox();
});

document.getElementById("cfgFitBtn").addEventListener("click", () => {
  cfgViewBox = { ...cfgInitialViewBox };
  updateSvgViewBox();
});

document.getElementById("cfgResetBtn").addEventListener("click", () => {
  cfgViewBox = { ...cfgInitialViewBox };
  updateSvgViewBox();
});

// -------------------------------------------------------------
// DIAGNOSTICS RENDERING (Interactive Line Jump & Filtering)
// -------------------------------------------------------------
function renderDiagnostics(diagnostics) {
  const allDiags = diagnostics || [];
  const badge = document.getElementById("diagBadge");
  badge.textContent = allDiags.length;

  const errCount = allDiags.filter(d => d.severity === "error").length;
  const warnCount = allDiags.filter(d => d.severity === "warning").length;

  document.getElementById("diagCountAll").textContent = allDiags.length;
  document.getElementById("diagCountError").textContent = errCount;
  document.getElementById("diagCountWarning").textContent = warnCount;

  const container = document.getElementById("diagnosticsList");
  container.innerHTML = "";

  const filtered = allDiags.filter(d => {
    if (currentDiagFilter === "error") return d.severity === "error";
    if (currentDiagFilter === "warning") return d.severity === "warning";
    return true;
  });

  if (filtered.length === 0) {
    if (allDiags.length === 0) {
      container.innerHTML = `<div class="empty-state">No semantic errors or warnings detected. All types and identifiers verified!</div>`;
    } else {
      container.innerHTML = `<div class="empty-state">No diagnostics matching filter '${currentDiagFilter}'.</div>`;
    }
  } else {
    filtered.forEach(d => {
      const card = document.createElement("div");
      card.className = `diag-card ${d.severity}`;
      card.title = `Click to jump to Line ${d.line}`;
      card.innerHTML = `
        <span class="diag-loc">Line ${d.line}${d.col ? ":" + d.col : ""}</span>
        <div class="diag-msg">
          <strong>[${d.severity.toUpperCase()}]</strong> ${escapeHtml(d.message)}
        </div>
        ${d.rule ? `<span class="diag-rule">${escapeHtml(d.rule)}</span>` : ""}
      `;
      card.onclick = () => jumpToLine(d.line);
      container.appendChild(card);
    });
  }

  document.getElementById("semanticEmpty").style.display = "none";
  document.getElementById("semanticWrap").style.display = "block";
}

// Wire Diagnostic Filter Buttons
document.getElementById("diagFilterAll").addEventListener("click", () => {
  currentDiagFilter = "all";
  document.getElementById("diagFilterAll").classList.add("active");
  document.getElementById("diagFilterError").classList.remove("active");
  document.getElementById("diagFilterWarning").classList.remove("active");
  if (currentAnalysisData) renderDiagnostics(currentAnalysisData.diagnostics);
});

document.getElementById("diagFilterError").addEventListener("click", () => {
  currentDiagFilter = "error";
  document.getElementById("diagFilterError").classList.add("active");
  document.getElementById("diagFilterAll").classList.remove("active");
  document.getElementById("diagFilterWarning").classList.remove("active");
  if (currentAnalysisData) renderDiagnostics(currentAnalysisData.diagnostics);
});

document.getElementById("diagFilterWarning").addEventListener("click", () => {
  currentDiagFilter = "warning";
  document.getElementById("diagFilterWarning").classList.add("active");
  document.getElementById("diagFilterAll").classList.remove("active");
  document.getElementById("diagFilterError").classList.remove("active");
  if (currentAnalysisData) renderDiagnostics(currentAnalysisData.diagnostics);
});

// -------------------------------------------------------------
// Code Smells & Refactoring Recommendations
// -------------------------------------------------------------
function renderCodeSmells(smells) {
  const allSmells = smells || [];
  const badge = document.getElementById("smellsBadge");
  badge.textContent = allSmells.length;
  document.getElementById("smellsTotalPill").textContent = `${allSmells.length} Smells Detected`;

  const container = document.getElementById("smellsList");
  container.innerHTML = "";

  if (allSmells.length === 0) {
    container.innerHTML = `<div class="empty-state">No code smells detected! Code meets all nesting, length, and modularity thresholds.</div>`;
  } else {
    allSmells.forEach(smell => {
      const card = document.createElement("div");
      card.className = "smell-card";
      card.innerHTML = `
        <div class="smell-card-header">
          <div class="smell-title-row">
            <span class="severity-pill ${smell.severity.toLowerCase()}">${smell.severity}</span>
            <span class="smell-name">${escapeHtml(smell.category)}</span>
          </div>
          <span class="smell-location">${escapeHtml(smell.function)} &middot; Line ${smell.line}</span>
        </div>
        <div class="smell-desc">${escapeHtml(smell.description)}</div>
        <div class="smell-suggestion">
          <strong>Recommendation:</strong> ${escapeHtml(smell.suggestion)}
        </div>
        ${smell.examplePattern ? `<div class="smell-code-hint">${escapeHtml(smell.examplePattern)}</div>` : ''}
      `;
      container.appendChild(card);
    });
  }

  document.getElementById("smellsEmpty").style.display = "none";
  document.getElementById("smellsWrap").style.display = "block";
}

// -------------------------------------------------------------
// Symbol Table Rendering
// -------------------------------------------------------------
function renderSymbolTable(st) {
  const summary = document.getElementById("symbolSummary");
  summary.innerHTML = `<p>Active Scopes: <strong>${st.totalScopes || 0}</strong> &middot; Tracked Identifiers: <strong>${st.totalSymbols || 0}</strong></p>`;

  const tbody = document.getElementById("symbolTableBody");
  tbody.innerHTML = "";
  (st.flatSymbols || []).forEach(sym => {
    const tr = document.createElement("tr");
    let statusBadge;
    if (sym.name === "main" && sym.kind === "function") {
      statusBadge = '<span class="tag-badge low">Entry Point</span>';
    } else if (sym.isUsed) {
      statusBadge = '<span class="tag-badge low">Referenced</span>';
    } else {
      statusBadge = '<span class="tag-badge high">Unused</span>';
    }

    const refText = (sym.name === "main" && sym.kind === "function" && (!sym.references || sym.references.length === 0))
      ? 'Entry Point'
      : (sym.references && sym.references.length > 0 ? `${sym.usageCount} times` : '0');

    tr.innerHTML = `
      <td><strong>${escapeHtml(sym.name)}</strong></td>
      <td><code>${escapeHtml(sym.type || "Any")}</code></td>
      <td>${escapeHtml(sym.kind)}</td>
      <td><code>${escapeHtml(sym.scopeName)}</code></td>
      <td>L${sym.line}:C${sym.col}</td>
      <td>${refText}</td>
      <td>${statusBadge}</td>
    `;
    tbody.appendChild(tr);
  });

  document.getElementById("symbolEmpty").style.display = "none";
  document.getElementById("symbolWrap").style.display = "block";
}

// -------------------------------------------------------------
// AST & Tokens Rendering
// -------------------------------------------------------------
function exprToStr(e) {
  if (!e) return "";
  if (typeof e === "string") return e;
  switch (e.type) {
    case "Number": return e.value;
    case "String": return `"${e.value}"`;
    case "Identifier": return e.name;
    case "BinaryExpr": return `${exprToStr(e.left)} ${e.op} ${exprToStr(e.right)}`;
    case "Assign": return `${e.name || exprToStr(e.target)} = ${exprToStr(e.value)}`;
    case "Unary": return `${e.op}${exprToStr(e.argument)}`;
    case "Call": return `${e.callee}(${(e.args || []).map(exprToStr).join(", ")})`;
    case "Expr": return e.value || "";
    default: return e.value || e.type || "";
  }
}

let currentAstMode = "tree";
let astViewBox = { x: 0, y: 0, w: 1000, h: 600 };
let astInitialViewBox = { x: 0, y: 0, w: 1000, h: 600 };
let isDraggingAstSvg = false;
let astDragStart = { x: 0, y: 0 };

const astViewTreeBtn = document.getElementById("astViewTreeBtn");
const astViewGraphBtn = document.getElementById("astViewGraphBtn");
const astTree = document.getElementById("astTree");
const astGraphContainer = document.getElementById("astGraphContainer");
const astSvg = document.getElementById("astSvg");

function setAstView(mode) {
  currentAstMode = mode;
  if (mode === "tree") {
    if (astViewTreeBtn) astViewTreeBtn.classList.add("active");
    if (astViewGraphBtn) astViewGraphBtn.classList.remove("active");
    if (astTree) astTree.style.display = "block";
    if (astGraphContainer) astGraphContainer.style.display = "none";
  } else {
    if (astViewGraphBtn) astViewGraphBtn.classList.add("active");
    if (astViewTreeBtn) astViewTreeBtn.classList.remove("active");
    if (astTree) astTree.style.display = "none";
    if (astGraphContainer) astGraphContainer.style.display = "block";
    if (currentAnalysisData && currentAnalysisData.ast) {
      renderAstGraph(currentAnalysisData.ast);
    }
  }
}

if (astViewTreeBtn) astViewTreeBtn.addEventListener("click", () => setAstView("tree"));
if (astViewGraphBtn) astViewGraphBtn.addEventListener("click", () => setAstView("graph"));

function updateAstSvgViewBox() {
  if (astSvg) {
    astSvg.setAttribute("viewBox", `${astViewBox.x} ${astViewBox.y} ${astViewBox.w} ${astViewBox.h}`);
  }
}

if (astSvg) {
  astSvg.addEventListener("mousedown", (e) => {
    isDraggingAstSvg = true;
    astDragStart = { x: e.clientX, y: e.clientY };
  });

  window.addEventListener("mousemove", (e) => {
    if (!isDraggingAstSvg || !astSvg) return;
    const clientW = astSvg.clientWidth || 800;
    const clientH = astSvg.clientHeight || 500;
    const dx = (e.clientX - astDragStart.x) * (astViewBox.w / clientW);
    const dy = (e.clientY - astDragStart.y) * (astViewBox.h / clientH);
    astViewBox.x -= dx;
    astViewBox.y -= dy;
    astDragStart = { x: e.clientX, y: e.clientY };
    updateAstSvgViewBox();
  });

  window.addEventListener("mouseup", () => {
    isDraggingAstSvg = false;
  });

  astSvg.addEventListener("wheel", (e) => {
    e.preventDefault();
    const zoomFactor = e.deltaY > 0 ? 1.15 : 0.85;
    const clientW = astSvg.clientWidth || 800;
    const clientH = astSvg.clientHeight || 500;
    const mouseX = e.offsetX / clientW;
    const mouseY = e.offsetY / clientH;

    const newW = astViewBox.w * zoomFactor;
    const newH = astViewBox.h * zoomFactor;

    astViewBox.x += (astViewBox.w - newW) * mouseX;
    astViewBox.y += (astViewBox.h - newH) * mouseY;
    astViewBox.w = newW;
    astViewBox.h = newH;
    updateAstSvgViewBox();
  });
}

const astZoomInBtn = document.getElementById("astZoomInBtn");
if (astZoomInBtn) {
  astZoomInBtn.addEventListener("click", () => {
    astViewBox.x += astViewBox.w * 0.1;
    astViewBox.y += astViewBox.h * 0.1;
    astViewBox.w *= 0.8;
    astViewBox.h *= 0.8;
    updateAstSvgViewBox();
  });
}

const astZoomOutBtn = document.getElementById("astZoomOutBtn");
if (astZoomOutBtn) {
  astZoomOutBtn.addEventListener("click", () => {
    astViewBox.x -= astViewBox.w * 0.125;
    astViewBox.y -= astViewBox.h * 0.125;
    astViewBox.w *= 1.25;
    astViewBox.h *= 1.25;
    updateAstSvgViewBox();
  });
}

const astFitBtn = document.getElementById("astFitBtn");
if (astFitBtn) {
  astFitBtn.addEventListener("click", () => {
    astViewBox = { ...astInitialViewBox };
    updateAstSvgViewBox();
  });
}

const astResetBtn = document.getElementById("astResetBtn");
if (astResetBtn) {
  astResetBtn.addEventListener("click", () => {
    astViewBox = { ...astInitialViewBox };
    updateAstSvgViewBox();
  });
}

function renderAstTree(ast) {
  const root = document.getElementById("astTree");
  root.innerHTML = "";

  function label(tag, detail) {
    const div = document.createElement("div");
    div.className = "node-label";
    div.innerHTML = `<span class="node-tag">${tag}</span>${detail ? ' <span class="node-detail">' + escapeHtml(detail) + "</span>" : ""}`;
    return div;
  }

  function buildStmt(node, container) {
    if (!node) return;
    const box = document.createElement("div");
    box.className = "node";
    switch (node.type) {
      case "Block":
        (node.statements || []).forEach(s => buildStmt(s, container));
        return;
      case "Declaration":
        box.appendChild(label("DECLARATION", `${node.varType || "var"} ${node.name}${node.init ? " = " + exprToStr(node.init) : ""}`));
        break;
      case "If":
        box.appendChild(label("IF", exprToStr(node.condition)));
        buildStmt(node.consequent, box);
        if (node.alternate) {
          box.appendChild(label("ELSE"));
          buildStmt(node.alternate, box);
        }
        break;
      case "For":
        box.appendChild(label("FOR", node.init || "loop"));
        buildStmt(node.body, box);
        break;
      case "While":
        box.appendChild(label("WHILE", exprToStr(node.condition)));
        buildStmt(node.body, box);
        break;
      case "Return":
        box.appendChild(label("RETURN", node.value ? exprToStr(node.value) : ""));
        break;
      case "ExprStmt":
        box.appendChild(label("EXPR", exprToStr(node.expr)));
        break;
      default:
        box.appendChild(label(node.type));
        break;
    }
    container.appendChild(box);
  }

  (ast.functions || []).forEach(fn => {
    const fnBox = document.createElement("div");
    fnBox.className = "node";
    fnBox.appendChild(label("FUNCTION", `${fn.returnType || "def"} ${fn.name}(${(fn.params || []).map(p => (p.varType || "") + " " + p.name).join(", ")})`));
    buildStmt(fn.body, fnBox);
    root.appendChild(fnBox);
  });

  document.getElementById("astEmpty").style.display = "none";
  document.getElementById("astWrap").style.display = "block";

  if (currentAstMode === "graph") {
    renderAstGraph(ast);
  }
}

// Hierarchical AST Diagram Data Builder
function buildAstTreeHierarchy(ast) {
  let counter = 0;
  const genId = () => `ast_node_${++counter}`;

  const root = {
    id: "root_prog",
    tag: "PROG",
    title: "Program (AST Root)",
    sub: `${(ast.functions || []).length} Function(s)`,
    type: "root",
    children: []
  };

  function parseExpr(e) {
    if (!e) return null;
    const id = genId();
    if (typeof e === "string") {
      return { id, tag: "EXPR", title: e, sub: "", type: "expr", children: [] };
    }
    if (e.type === "BinaryExpr") {
      const children = [];
      const left = parseExpr(e.left);
      const right = parseExpr(e.right);
      if (left) children.push(left);
      if (right) children.push(right);
      return {
        id,
        tag: "OP",
        title: `Binary: ${e.op}`,
        sub: exprToStr(e),
        type: "op",
        children
      };
    }
    if (e.type === "Unary") {
      const arg = parseExpr(e.argument);
      return {
        id,
        tag: "UNARY",
        title: `Unary: ${e.op}`,
        sub: exprToStr(e),
        type: "op",
        children: arg ? [arg] : []
      };
    }
    if (e.type === "Call") {
      const args = (e.args || []).map(parseExpr).filter(Boolean);
      return {
        id,
        tag: "CALL",
        title: `${e.callee}()`,
        sub: `${args.length} argument(s)`,
        type: "call",
        children: args
      };
    }
    if (e.type === "Assign") {
      const val = parseExpr(e.value);
      return {
        id,
        tag: "ASSIGN",
        title: `${e.name || exprToStr(e.target)} =`,
        sub: exprToStr(e.value),
        type: "assign",
        children: val ? [val] : []
      };
    }
    if (e.type === "Identifier") {
      return { id, tag: "ID", title: e.name, sub: "identifier", type: "id", children: [] };
    }
    if (e.type === "Number" || e.type === "String") {
      return { id, tag: "LIT", title: String(e.value), sub: e.type.toLowerCase(), type: "literal", children: [] };
    }
    return { id, tag: "EXPR", title: exprToStr(e) || e.type || "expr", sub: "", type: "expr", children: [] };
  }

  function parseStmt(s) {
    if (!s) return [];
    const id = genId();
    switch (s.type) {
      case "Block": {
        const out = [];
        (s.statements || []).forEach(st => {
          out.push(...parseStmt(st));
        });
        return out;
      }
      case "Declaration": {
        const children = [];
        if (s.init) {
          const initNode = parseExpr(s.init);
          if (initNode) children.push(initNode);
        }
        return [{
          id,
          tag: "DECL",
          title: `${s.name}`,
          sub: `${s.varType || "var"}${s.init ? " = " + exprToStr(s.init) : ""}`,
          type: "decl",
          children
        }];
      }
      case "If": {
        const children = [];
        const condNode = parseExpr(s.condition);
        if (condNode) children.push(condNode);

        const thenChildren = parseStmt(s.consequent);
        children.push({
          id: genId(),
          tag: "THEN",
          title: "Then Branch",
          sub: `${thenChildren.length} statement(s)`,
          type: "branch",
          children: thenChildren
        });

        if (s.alternate) {
          const elseChildren = parseStmt(s.alternate);
          children.push({
            id: genId(),
            tag: "ELSE",
            title: "Else Branch",
            sub: `${elseChildren.length} statement(s)`,
            type: "branch",
            children: elseChildren
          });
        }

        return [{
          id,
          tag: "IF",
          title: `if (${exprToStr(s.condition)})`,
          sub: "Conditional branch",
          type: "control",
          children
        }];
      }
      case "While": {
        const bodyChildren = parseStmt(s.body);
        return [{
          id,
          tag: "WHILE",
          title: `while (${exprToStr(s.condition)})`,
          sub: `Loop body (${bodyChildren.length} stmts)`,
          type: "control",
          children: bodyChildren
        }];
      }
      case "For": {
        const bodyChildren = parseStmt(s.body);
        return [{
          id,
          tag: "FOR",
          title: `for (${s.init || "loop"})`,
          sub: `Loop body (${bodyChildren.length} stmts)`,
          type: "control",
          children: bodyChildren
        }];
      }
      case "Return": {
        const children = [];
        if (s.value) {
          const valNode = parseExpr(s.value);
          if (valNode) children.push(valNode);
        }
        return [{
          id,
          tag: "RETURN",
          title: "return",
          sub: s.value ? exprToStr(s.value) : "void",
          type: "return",
          children
        }];
      }
      case "ExprStmt": {
        const exprNode = parseExpr(s.expr);
        return [{
          id,
          tag: exprNode ? exprNode.tag : "EXPR",
          title: exprToStr(s.expr) || "Expression",
          sub: "Expr Statement",
          type: "expr",
          children: exprNode && exprNode.children ? exprNode.children : []
        }];
      }
      default:
        return [{
          id,
          tag: (s.type || "STMT").toUpperCase().substring(0, 6),
          title: s.type || "Statement",
          sub: "",
          type: "stmt",
          children: []
        }];
    }
  }

  (ast.functions || []).forEach(fn => {
    const fnId = genId();
    const stmts = parseStmt(fn.body);
    const paramNames = (fn.params || []).map(p => (p.varType ? p.varType + " " : "") + p.name).join(", ");

    root.children.push({
      id: fnId,
      tag: "FN",
      title: `${fn.name}(${paramNames})`,
      sub: `returns ${fn.returnType || "void"} | ${stmts.length} stmts`,
      type: "function",
      children: stmts
    });
  });

  return root;
}

// Interactive SVG AST Diagram Renderer
function renderAstGraph(ast) {
  const svg = document.getElementById("astSvg");
  if (!svg) return;
  svg.innerHTML = "";

  if (!ast || (!ast.functions || ast.functions.length === 0)) {
    svg.innerHTML = `
      <text x="50%" y="50%" fill="#71717a" font-size="14" font-family="'SF Pro Display', 'SF Pro Text', 'SF Pro', -apple-system, BlinkMacSystemFont, sans-serif" text-anchor="middle">
        No AST nodes found. Run analysis with valid code.
      </text>`;
    return;
  }

  const treeRoot = buildAstTreeHierarchy(ast);

  // Compute Layout (Compact Editorial Grid)
  const nodeW = 180;
  const nodeH = 48;
  const gapX = 26;
  const gapY = 60;

  function computeLayout(node, depth = 0) {
    node.depth = depth;
    node.y = depth * (nodeH + gapY) + 36;

    if (!node.children || node.children.length === 0) {
      node.subtreeWidth = nodeW;
      return;
    }

    node.children.forEach(c => computeLayout(c, depth + 1));
    const childrenWidth = node.children.reduce((sum, c) => sum + c.subtreeWidth, 0)
      + (node.children.length - 1) * gapX;
    node.subtreeWidth = Math.max(nodeW, childrenWidth);
  }

  function assignCoordinates(node, leftX) {
    const childrenWidth = (node.children && node.children.length > 0)
      ? node.children.reduce((sum, c) => sum + c.subtreeWidth, 0) + (node.children.length - 1) * gapX
      : 0;

    let currentX = leftX + (node.subtreeWidth - childrenWidth) / 2;

    if (node.children && node.children.length > 0) {
      node.children.forEach(c => {
        assignCoordinates(c, currentX);
        currentX += c.subtreeWidth + gapX;
      });
      const firstX = node.children[0].x;
      const lastX = node.children[node.children.length - 1].x;
      node.x = (firstX + lastX) / 2;
    } else {
      node.x = leftX + (node.subtreeWidth - nodeW) / 2;
    }
  }

  computeLayout(treeRoot, 0);
  assignCoordinates(treeRoot, 36);

  // Collect all nodes and edges for bounds
  const allNodes = [];
  const allEdges = [];

  function collect(node) {
    allNodes.push(node);
    (node.children || []).forEach(c => {
      allEdges.push({ from: node, to: c });
      collect(c);
    });
  }
  collect(treeRoot);

  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  allNodes.forEach(n => {
    minX = Math.min(minX, n.x);
    maxX = Math.max(maxX, n.x + nodeW);
    minY = Math.min(minY, n.y);
    maxY = Math.max(maxY, n.y + nodeH);
  });

  const pad = 44;
  const totalW = Math.max(760, maxX - minX + pad * 2);
  const totalH = Math.max(480, maxY - minY + pad * 2);

  astInitialViewBox = {
    x: minX - pad,
    y: minY - pad,
    w: totalW,
    h: totalH
  };
  astViewBox = { ...astInitialViewBox };
  updateAstSvgViewBox();

  // Create SVG Defs (Arrows & Filters)
  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  defs.innerHTML = `
    <marker id="astArrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#9b1d3d" />
    </marker>
    <filter id="astShadow" x="-10%" y="-10%" width="130%" height="130%">
      <feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#000000" flood-opacity="0.6"/>
    </filter>
  `;
  svg.appendChild(defs);

  const mainG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  svg.appendChild(mainG);

  // Draw Edges (Curved Bézier paths)
  allEdges.forEach(edge => {
    const px = edge.from.x + nodeW / 2;
    const py = edge.from.y + nodeH;
    const cx = edge.to.x + nodeW / 2;
    const cy = edge.to.y;
    const midY = (py + cy) / 2;

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", `M ${px} ${py} C ${px} ${midY}, ${cx} ${midY}, ${cx} ${cy}`);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "#9b1d3d");
    path.setAttribute("stroke-opacity", "0.75");
    path.setAttribute("stroke-width", "1.75");
    path.setAttribute("marker-end", "url(#astArrow)");
    mainG.appendChild(path);

    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx", px);
    dot.setAttribute("cy", py);
    dot.setAttribute("r", "2.5");
    dot.setAttribute("fill", "#f43f5e");
    mainG.appendChild(dot);
  });

  // Draw Nodes
  allNodes.forEach(node => {
    const nodeG = document.createElementNS("http://www.w3.org/2000/svg", "g");
    nodeG.setAttribute("class", "ast-node-card");
    nodeG.setAttribute("transform", `translate(${node.x}, ${node.y})`);

    let strokeColor = "rgba(255, 255, 255, 0.12)";
    let tagBg = "#1f1f2e";
    let tagText = "#a1a1aa";

    if (node.type === "root") {
      strokeColor = "#9b1d3d";
      tagBg = "#9b1d3d";
      tagText = "#ffffff";
    } else if (node.type === "function") {
      strokeColor = "#9b1d3d";
      tagBg = "#800020";
      tagText = "#f4f4f6";
    } else if (node.type === "control") {
      strokeColor = "rgba(155, 29, 61, 0.7)";
      tagBg = "rgba(155, 29, 61, 0.3)";
      tagText = "#f43f5e";
    } else if (node.type === "branch") {
      strokeColor = "rgba(255, 255, 255, 0.18)";
      tagBg = "#222230";
      tagText = "#f43f5e";
    } else if (node.type === "call" || node.type === "return") {
      strokeColor = "rgba(155, 29, 61, 0.5)";
      tagBg = "rgba(155, 29, 61, 0.25)";
      tagText = "#ffffff";
    }

    // Node Card Rect
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", "0");
    rect.setAttribute("y", "0");
    rect.setAttribute("width", nodeW);
    rect.setAttribute("height", nodeH);
    rect.setAttribute("rx", "8");
    rect.setAttribute("fill", "#111116");
    rect.setAttribute("stroke", strokeColor);
    rect.setAttribute("stroke-width", "1.5");
    rect.setAttribute("filter", "url(#astShadow)");
    nodeG.appendChild(rect);

    // Tag Pill
    const tagW = Math.min(58, node.tag.length * 7 + 10);
    const tagRect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    tagRect.setAttribute("x", "8");
    tagRect.setAttribute("y", "7");
    tagRect.setAttribute("width", tagW);
    tagRect.setAttribute("height", "15");
    tagRect.setAttribute("rx", "3.5");
    tagRect.setAttribute("fill", tagBg);
    nodeG.appendChild(tagRect);

    const tagLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
    tagLabel.setAttribute("x", 8 + tagW / 2);
    tagLabel.setAttribute("y", "18");
    tagLabel.setAttribute("fill", tagText);
    tagLabel.setAttribute("font-size", "9px");
    tagLabel.setAttribute("font-family", "'SF Pro Display', 'SF Pro Text', 'SF Pro', -apple-system, BlinkMacSystemFont, sans-serif");
    tagLabel.setAttribute("font-weight", "700");
    tagLabel.setAttribute("text-anchor", "middle");
    tagLabel.textContent = node.tag;
    nodeG.appendChild(tagLabel);

    // Title Text
    const titleText = document.createElementNS("http://www.w3.org/2000/svg", "text");
    titleText.setAttribute("class", "node-title");
    titleText.setAttribute("x", 8 + tagW + 6);
    titleText.setAttribute("y", "18.5");
    titleText.setAttribute("fill", "#f4f4f6");
    titleText.setAttribute("font-size", "11px");
    titleText.setAttribute("font-family", "'SF Pro Display', 'SF Pro Text', 'SF Pro', -apple-system, BlinkMacSystemFont, sans-serif");
    titleText.setAttribute("font-weight", "600");
    const rawTitle = node.title || "";
    titleText.textContent = rawTitle.length > 15 ? rawTitle.substring(0, 14) + "…" : rawTitle;
    nodeG.appendChild(titleText);

    // Subtitle Text
    const subText = document.createElementNS("http://www.w3.org/2000/svg", "text");
    subText.setAttribute("x", "10");
    subText.setAttribute("y", "35");
    subText.setAttribute("fill", "#a1a1aa");
    subText.setAttribute("font-size", "9.5px");
    subText.setAttribute("font-family", "'SF Pro Display', 'SF Pro Text', 'SF Pro', -apple-system, BlinkMacSystemFont, sans-serif");
    const rawSub = node.sub || "";
    subText.textContent = rawSub.length > 25 ? rawSub.substring(0, 24) + "…" : rawSub;
    nodeG.appendChild(subText);

    // Tooltip for full text
    const titleEl = document.createElementNS("http://www.w3.org/2000/svg", "title");
    titleEl.textContent = `[${node.tag}] ${rawTitle}\n${rawSub}`;
    nodeG.appendChild(titleEl);

    mainG.appendChild(nodeG);
  });
}

function renderTokens(tokens) {
  const body = document.getElementById("tokensBody");
  body.innerHTML = "";
  tokens.forEach(t => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>L${t.line}:C${t.col}</td>
      <td><code>${escapeHtml(t.value)}</code></td>
      <td class="tok-type">${t.type}</td>
    `;
    body.appendChild(tr);
  });
  document.getElementById("tokensEmpty").style.display = "none";
  document.getElementById("tokensWrap").style.display = "block";
}

// -------------------------------------------------------------
// Quality Report Rendering
// -------------------------------------------------------------
function renderReport(m, quality, smells) {
  const prog = m.program || m;
  const q = quality || { score: 100, grade: "A", description: "Clean code" };

  const text =
`
         COMPREHENSIVE CODE QUALITY & COMPILER REPORT


1. EXECUTIVE QUALITY SUMMARY
   Overall Maintainability Score : ${q.score} / 100
   Quality Classification Grade  : ${q.grade} (${q.description})
   Lines of Code (LOC)           : ${prog.loc}
   Total Defined Functions       : ${prog.functions}
   Total Tracked Variables       : ${prog.variables}

2. CONTROL FLOW & COMPLEXITY METRICS
   Total Cyclomatic Complexity   : ${prog.cyclomatic}
   Average Complexity per Func   : ${prog.avgCyclomatic || prog.cyclomatic}
   Maximum Nesting Depth         : ${prog.maxNesting} (Threshold: 3)
   Most Complex Function         : ${prog.mostComplexFunction || 'N/A'} (CC: ${prog.maxFunctionComplexity || 0})
   Complexity Classification     : ${prog.complexityLevel}

3. CONTROL STRUCTURES BREAKDOWN
   If Statements                 : ${prog.ifs}
   For Loops                     : ${prog.fors}
   While Loops                   : ${prog.whiles}
   Switch-Case Blocks            : ${prog.switches || 0}
   Return Statements             : ${prog.returns}

4. CODE SMELLS & REFACTORING RECOMMENDATIONS
   Total Smells Identified       : ${smells.length}
${smells.map((s, i) => `   [${i+1}] ${s.category} (${s.severity}) in ${s.function} @ L${s.line}: ${s.description}\n       Advice: ${s.suggestion}`).join("\n\n")}


Generated by Code Quality Analyzer (Multi-Language Pipeline)
`;

  document.getElementById("reportText").textContent = text;
  document.getElementById("sayText").textContent =
    "Our project is an end-to-end multi-language compiler-based code quality analyzer supporting C, C++, Python, Java, and JavaScript. The pipeline accepts source code, performs lexical analysis, builds an Abstract Syntax Tree, manages scope hierarchies in a symbol table, performs semantic diagnostics, generates basic blocks and control-flow graphs computing McCabe's complexity (M = E - N + 2P), and detects code smells with actionable refactoring recommendations.";

  document.getElementById("reportEmpty").style.display = "none";
  document.getElementById("reportWrap").style.display = "block";
}

function downloadBlob(content, filename, contentType) {
  const blob = new Blob([content], { type: contentType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 100);
}

const downloadReportBtn = document.getElementById("downloadReportBtn");
if (downloadReportBtn) {
  downloadReportBtn.addEventListener("click", () => {
    const text = document.getElementById("reportText").textContent;
    if (!text || text.trim() === "") return;
    const dateStr = new Date().toISOString().slice(0, 10);
    const lang = (currentAnalysisData && currentAnalysisData.language) ? currentAnalysisData.language : "code";
    downloadBlob(text, `code_quality_report_${lang}_${dateStr}.txt`, "text/plain;charset=utf-8");

    downloadReportBtn.textContent = "✓ Downloaded!";
    setTimeout(() => { downloadReportBtn.textContent = "↓ Download Report (.txt)"; }, 2000);
  });
}

const downloadJsonReportBtn = document.getElementById("downloadJsonReportBtn");
if (downloadJsonReportBtn) {
  downloadJsonReportBtn.addEventListener("click", () => {
    if (!currentAnalysisData) return;
    const jsonStr = JSON.stringify(currentAnalysisData, null, 2);
    const dateStr = new Date().toISOString().slice(0, 10);
    const lang = currentAnalysisData.language || "code";
    downloadBlob(jsonStr, `analysis_data_${lang}_${dateStr}.json`, "application/json;charset=utf-8");

    downloadJsonReportBtn.textContent = "✓ Downloaded!";
    setTimeout(() => { downloadJsonReportBtn.textContent = "↓ Download JSON"; }, 2000);
  });
}

document.getElementById("copyReportBtn").addEventListener("click", () => {
  const text = document.getElementById("reportText").textContent;
  navigator.clipboard.writeText(text).then(() => {
    const btn = document.getElementById("copyReportBtn");
    btn.textContent = "Copied!";
    setTimeout(() => { btn.textContent = "Copy Report"; }, 2000);
  });
});

// -------------------------------------------------------------
// History Management
// -------------------------------------------------------------
function saveToHistory(data) {
  try {
    const history = JSON.parse(localStorage.getItem("cqa_history") || "[]");
    const item = {
      timestamp: new Date().toLocaleTimeString(),
      lang: data.language || "c",
      loc: data.metrics.program.loc,
      cc: data.metrics.program.cyclomatic,
      grade: data.quality.grade,
      score: data.quality.score,
      smells: data.codeSmells.length,
      codeSnippet: srcEditor.value.slice(0, 100) + "..."
    };
    history.unshift(item);
    if (history.length > 15) history.pop();
    localStorage.setItem("cqa_history", JSON.stringify(history));
    renderHistory();
  } catch (e) {
    console.error("Failed to save history", e);
  }
}

function renderHistory() {
  const container = document.getElementById("historyList");
  const history = JSON.parse(localStorage.getItem("cqa_history") || "[]");
  container.innerHTML = "";

  if (history.length === 0) {
    container.innerHTML = `<div class="empty-state">No previous runs saved yet.</div>`;
    return;
  }

  history.forEach(item => {
    const div = document.createElement("div");
    div.className = "history-item";
    div.innerHTML = `
      <div class="history-meta">
        <span class="score-circle grade-${item.grade.toLowerCase()}" style="width:32px;height:32px;font-size:0.9rem;">${item.grade}</span>
        <div>
          <div class="history-stats">Score: <strong>${item.score}/100</strong> &middot; CC: <strong>${item.cc}</strong> &middot; Smells: <strong>${item.smells}</strong></div>
          <div class="history-time">${item.timestamp} &middot; ${item.loc} LOC &middot; [${(item.lang || 'c').toUpperCase()}]</div>
        </div>
      </div>
    `;
    container.appendChild(div);
  });
}

document.getElementById("clearHistoryBtn").addEventListener("click", () => {
  localStorage.removeItem("cqa_history");
  renderHistory();
});

// -------------------------------------------------------------
// Project (Multi-File) Analysis
// -------------------------------------------------------------
function renderProjectOverview(data) {
  const s = data.summary;
  const grid = document.getElementById("projectMetricGrid");
  grid.innerHTML = `
    <div class="metric-card"><div class="num">${s.fileCount}</div><div class="label">Files</div></div>
    <div class="metric-card"><div class="num">${s.totalLoc}</div><div class="label">Project LOC</div></div>
    <div class="metric-card"><div class="num">${s.totalFunctions}</div><div class="label">Total Functions</div></div>
    <div class="metric-card"><div class="num">${s.totalCyclomatic}</div><div class="label">Project CC</div></div>
    <div class="metric-card"><div class="num">${s.averageCyclomatic}</div><div class="label">Avg CC</div></div>
    <div class="metric-card"><div class="num">${s.totalCodeSmells}</div><div class="label">Total Smells</div></div>
    <div class="metric-card good"><div class="num">${s.overallQualityScore}/100</div><div class="label">Project Grade</div></div>
  `;

  const tbody = document.getElementById("projectTableBody");
  tbody.innerHTML = "";
  data.files.forEach(f => {
    const tr = document.createElement("tr");
    if (f.error) {
      tr.innerHTML = `<td>${escapeHtml(f.filename)}</td><td colspan="6" style="color:var(--danger)">${escapeHtml(f.error)}</td>`;
    } else {
      const q = f.quality;
      tr.innerHTML = `
        <td><strong>${escapeHtml(f.filename)}</strong></td>
        <td>${f.metrics.program.loc}</td>
        <td>${f.metrics.program.functions}</td>
        <td><strong>${f.metrics.program.cyclomatic}</strong></td>
        <td>${f.metrics.program.avgCyclomatic}</td>
        <td>${f.codeSmells.length}</td>
        <td><span class="tag-badge ${q.grade === 'A' ? 'low' : q.grade === 'B' ? 'moderate' : 'high'}">${q.grade} (${q.score})</span></td>
      `;
    }
    tbody.appendChild(tr);
  });

  document.getElementById("projectEmpty").style.display = "none";
  document.getElementById("projectWrap").style.display = "block";
}

// -------------------------------------------------------------
// Core Analysis Pipeline Execution
// -------------------------------------------------------------
async function analyzeCode() {
  clearError();
  const code = srcEditor.value;
  const lang = langSelect.value;
  runPipelineAnimation();

  let res;
  try {
    res = await fetch("/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, language: lang === "auto" ? null : lang }),
    });
  } catch (err) {
    showError("Could not reach the analysis server.", "network");
    return;
  }

  const data = await res.json();
  if (!res.ok) {
    showError(data.error, data.stage);
    return;
  }

  currentAnalysisData = data;
  if (data.language) updateLangTag(data.language);

  renderTokens(data.tokens);
  renderAstTree(data.ast);
  renderMetrics(data.metrics, data.quality);
  renderQuickSummary(data.metrics.program, data.quality, data.codeSmells.length);
  renderCfg(data.cfgs);
  renderSymbolTable(data.symbolTable);
  renderDiagnostics(data.diagnostics);
  renderCodeSmells(data.codeSmells);
  renderReport(data.metrics, data.quality, data.codeSmells);
  saveToHistory(data);
}

async function analyzeProject() {
  clearError();
  if (projectFiles[currentFileIndex]) {
    projectFiles[currentFileIndex].code = srcEditor.value;
    projectFiles[currentFileIndex].language = langSelect.value;
  }
  runPipelineAnimation();

  let res;
  try {
    res = await fetch("/analyze_project", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files: projectFiles }),
    });
  } catch (err) {
    showError("Could not reach the analysis server.", "network");
    return;
  }

  const data = await res.json();
  if (!res.ok) {
    showError(data.error, "project");
    return;
  }

  currentProjectData = data;
  renderProjectOverview(data);

  // Switch to Project tab
  switchTab("project");
}

// -------------------------------------------------------------
// File Upload & Drag-and-Drop
// -------------------------------------------------------------
const uploadFileBtn = document.getElementById("uploadFileBtn");
const fileUploadInput = document.getElementById("fileUploadInput");

function loadFileContent(file) {
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    srcEditor.value = e.target.result;
    updateGutter();

    const ext = file.name.split(".").pop().toLowerCase();
    let detected = "c";
    if (ext === "py") detected = "python";
    else if (ext === "java") detected = "java";
    else if (ext === "js") detected = "javascript";
    else if (["cpp", "cc", "hpp", "cxx"].includes(ext)) detected = "cpp";

    if (langSelect) {
      langSelect.value = detected;
      updateLangTag(detected);
    }

    if (isProjectMode && projectFiles[currentFileIndex]) {
      projectFiles[currentFileIndex].name = file.name;
      projectFiles[currentFileIndex].language = detected;
      renderFileTabs();
    }

    analyzeCode();
  };
  reader.readAsText(file);
}

if (uploadFileBtn && fileUploadInput) {
  uploadFileBtn.addEventListener("click", () => fileUploadInput.click());
  fileUploadInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      loadFileContent(e.target.files[0]);
      fileUploadInput.value = "";
    }
  });
}

const editorWrapperEl = document.querySelector(".editor-wrapper");
if (editorWrapperEl) {
  editorWrapperEl.addEventListener("dragover", (e) => {
    e.preventDefault();
    editorWrapperEl.style.borderColor = "var(--accent)";
  });
  editorWrapperEl.addEventListener("dragleave", () => {
    editorWrapperEl.style.borderColor = "var(--border)";
  });
  editorWrapperEl.addEventListener("drop", (e) => {
    e.preventDefault();
    editorWrapperEl.style.borderColor = "var(--border)";
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
      loadFileContent(e.dataTransfer.files[0]);
    }
  });
}

document.getElementById("analyzeBtn").addEventListener("click", analyzeCode);
document.getElementById("analyzeProjectBtn").addEventListener("click", analyzeProject);

// Initial bootstrap
window.addEventListener("DOMContentLoaded", () => {
  updateGutter();
  renderHistory();
  analyzeCode();
});

