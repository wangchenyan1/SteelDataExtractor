/* 材料文献抽取工作台前端逻辑。
 * 数据来源：
 *   - 后端 API（/api/projects, /api/run, /api/run_step, /api/parse, /api/reextract ...）
 *   - window.READONLY_SNAPSHOT：离线时的项目名兜底（后端连上后以 API 为准）。
 */
(function () {
  "use strict";

  const SNAPSHOT = window.READONLY_SNAPSHOT || { projects: {} };
  const $ = (id) => document.getElementById(id);
  const esc = (s) =>
    String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
    );

  /** 兼容旧字符串与 {value, unit, excerpt, location} 包装对象 */
  function displayValue(field) {
    if (field == null) return "";
    if (typeof field === "object" && !Array.isArray(field)) {
      return field.value ?? field;
    }
    return field;
  }

  function formatDisplay(val) {
    const v = displayValue(val);
    if (v == null) return "";
    if (typeof v === "object") return JSON.stringify(v);
    return String(v);
  }

  /** 文章信息窗格只展示取值；unit / excerpt / location 已在左侧 Review 列表对照。 */
  function metadataValuesOnly(meta) {
    const out = {};
    Object.entries(meta || {}).forEach(([k, v]) => {
      if (v && typeof v === "object" && !Array.isArray(v) && "value" in v) {
        out[k] = v.value;
      } else {
        out[k] = v;
      }
    });
    return out;
  }

  const IDENTITY_IDS = new Set([
    "sample_id", "condition_id", "figure_id", "placeholder_index",
  ]);
  const LOCKED_FIELD_IDS = new Set([
    "sample_id", "condition_id", "figure_id", "placeholder_index",
  ]);

  const CATEGORY_LABELS = {
    metadata: "文章信息",
    sample: "样品信息",
    condition: "状态信息",
    property: "性能",
    figure: "图片信息",
  };

  /** 与 configs/templates/steel.json 六类一致；前端无模板大类 API，硬编码后与自建合并。 */
  const TEMPLATE_PROPERTY_GROUPS = [
    { id: "mechanical_properties", name: "力学性能" },
    { id: "magnetic_properties", name: "磁性能" },
    { id: "electrical_properties", name: "电性能" },
    { id: "impact_properties", name: "冲击性能" },
    { id: "corrosion_properties", name: "腐蚀性能" },
    { id: "phase_stability", name: "相稳定性" },
  ];
  const TEMPLATE_PROPERTY_GROUP_IDS = new Set(TEMPLATE_PROPERTY_GROUPS.map((g) => g.id));

  const state = {
    projects: {},
    models: [],
    selectedModel: null,
    defaultProject: null,
    currentId: null,
    project: null,
    overlay: null,
    fieldLibrary: { fields: [] },
    paperId: null,
    paperText: "",
    prompts: {},
    promptLabels: {},
    promptTab: "",
    changeLog: [],
    backendOnline: false,
    selectedStepId: null,
    entityDone: false,
    completedSteps: [],
    lastRunId: null,
    currentResult: null,
    editingRule: null,
    view: "papers",
    stageDraft: [],
    configHydratedFor: null,
    persistedOverlay: null,
    sourceMode: "text",
    hasPdf: false,
    hasMd: false,
    reviewFilter: "all",
    paperImageNames: [],
    selectedPaperIds: {},
    analyzing: false,
    currentAnalysisId: "",
    currentRunId: null,
  };

  const FIELD_LEVELS = [
    ["metadata", "metadataFields", "metadataFieldCount"],
    ["sample", "sampleFields", "sampleFieldCount"],
    ["condition", "conditionFields", "conditionFieldCount"],
    ["property", "propertyFields", "propertyFieldCount"],
    ["figure", "figureFields", "figureFieldCount"],
  ];

  async function api(path, opts) {
    const res = await fetch(path, opts);
    const ct = res.headers.get("content-type") || "";
    const data = ct.includes("application/json")
      ? await res.json().catch(() => ({}))
      : await res.text().then((t) => {
          try { return JSON.parse(t); } catch (_) { return { raw: t }; }
        });
    if (!res.ok) throw new Error((data && data.error) || `HTTP ${res.status}`);
    return data;
  }

  function setView(name) {
    state.view = name;
    document.querySelectorAll("[data-view-panel]").forEach((el) => {
      const views = (el.getAttribute("data-view-panel") || "").trim().split(/\s+/);
      el.hidden = !views.includes(name);
    });
    document.querySelectorAll("#viewNav [data-view]").forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-view") === name);
    });
    if (name === "config") {
      if (state.configHydratedFor !== state.currentId) loadConfigEditor();
      else {
        renderFieldLibraryChecks();
        renderPropertyGroupList();
        renderStageEditor();
      }
    }
    if (name === "review" || name === "export") {
      renderExtractedPaperList();
    }
    if (name === "export") {
      renderSchema();
      renderExportPaperChecks();
    }
    if (name === "review" && isCurrentPaperExtracted()) {
      loadReview();
    }
  }

  // ---------------------------------------------------------------- init
  async function init() {
    bindEvents();
    setView(state.view);
    await checkHealth();
    try {
      const payload = await api("/api/projects");
      state.projects = payload.projects || {};
      state.models = payload.models || [];
      state.defaultProject = payload.default_project;
    } catch (e) {
      state.projects = {};
    }
    Object.keys(SNAPSHOT.projects || {}).forEach((pid) => {
      if (!state.projects[pid]) {
        const sp = SNAPSHOT.projects[pid];
        state.projects[pid] = {
          id: pid,
          name: sp.name || pid,
          description: sp.description || "",
          runnable: true,
          backend: "claude",
          fields: sp.fields || {},
          rules: normalizeSnapshotRules(sp.field_rules || {}),
          property_source: {},
          figure_filter: {},
          papers: (sp.parsed_papers || []).map((p) => p.paper_id),
        };
      }
    });
    renderProjectList();
    const first = state.defaultProject || Object.keys(state.projects)[0];
    if (first) await selectProject(first);
    startJobPolling();
  }

  function normalizeSnapshotRules(fieldRules) {
    return fieldRules || {};
  }

  async function checkHealth() {
    try {
      await api("/api/health");
      state.backendOnline = true;
      $("apiStatus").textContent = "后端已连接";
      setRunStatus("后端已连接，可整篇跑、分阶段跑、只解析或只重抽。");
    } catch (e) {
      state.backendOnline = false;
      $("apiStatus").textContent = "后端未连接（先启动 workbench_server.py）";
      setRunStatus(
        "未检测到后端。请运行：python3 tools/workbench_server.py，然后刷新页面。",
        "failed"
      );
    }
  }

  async function reloadProjects() {
    const payload = await api("/api/projects");
    state.projects = payload.projects || {};
    state.models = payload.models || [];
    state.defaultProject = payload.default_project;
    Object.keys(SNAPSHOT.projects || {}).forEach((pid) => {
      if (!state.projects[pid]) {
        const sp = SNAPSHOT.projects[pid];
        state.projects[pid] = {
          id: pid,
          name: sp.name || pid,
          description: sp.description || "",
          runnable: true,
          backend: "claude",
          fields: sp.fields || {},
          rules: normalizeSnapshotRules(sp.field_rules || {}),
          property_source: {},
          figure_filter: {},
          papers: (sp.parsed_papers || []).map((p) => p.paper_id),
        };
      }
    });
  }

  // ---------------------------------------------------------------- project list
  function renderProjectList() {
    const box = $("projectList");
    box.innerHTML = "";
    Object.values(state.projects).forEach((p) => {
      const el = document.createElement("button");
      el.className = "project-item" + (p.id === state.currentId ? " active" : "");
      const kind = p.document_kind === "patent" ? "专利" : "文献";
      el.innerHTML =
        `<span class="project-name">${esc(p.name)}</span><span class="kind-badge">${kind}</span>`;
      el.addEventListener("click", () => selectProject(p.id));
      box.appendChild(el);
    });
    updateDeleteProjectButton();
  }

  function updateDeleteProjectButton() {
    const btn = $("btnDeleteProject");
    if (!btn) return;
    const protectedId = state.currentId === "demo_steel";
    btn.disabled = !state.currentId || protectedId;
    btn.title = protectedId
      ? "示例项目不可删除"
      : "删除当前项目（配置、文献解析与抽取记录）";
  }

  async function deleteCurrentProject() {
    const pid = state.currentId;
    if (!pid) return;
    if (pid === "demo_steel") {
      setRunStatus("示例项目不可删除", "failed");
      return;
    }
    const p = state.projects[pid] || {};
    const name = p.name || pid;
    if (
      !window.confirm(
        "确定删除项目「" +
          name +
          "」（" +
          pid +
          "）？\n\n将删除该项目配置、全部文献解析与抽取记录，不可恢复。"
      )
    ) {
      return;
    }
    setRunStatus("正在删除项目…", "running");
    try {
      await api("/api/project_delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project: pid }),
      });
      await reloadProjects();
      const next =
        state.projects[state.defaultProject]
          ? state.defaultProject
          : Object.keys(state.projects)[0] || "";
      if (next) await selectProject(next);
      else {
        state.currentId = "";
        state.project = null;
        renderProjectList();
        renderPapers();
      }
      setRunStatus("已删除项目 " + pid, "success");
    } catch (e) {
      setRunStatus("删除项目失败：" + e.message, "failed");
    }
  }

  async function deletePaper(paperId) {
    const pid = (paperId || "").trim();
    if (!pid || !state.currentId) return;
    const rec = paperRecords().find((r) => r.paper_id === pid);
    const label = (rec && (rec.title || rec.paper_id)) || pid;
    if (
      !window.confirm(
        "确定删除文献「" +
          label +
          "」？\n\n将删除解析文件与该篇全部抽取记录，不可恢复。"
      )
    ) {
      return;
    }
    setRunStatus("正在删除文献…", "running");
    try {
      await api("/api/paper_delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project: state.currentId, paper_id: pid }),
      });
      delete state.selectedPaperIds[pid];
      await reloadProjects();
      state.project = state.projects[state.currentId];
      if (state.paperId === pid) {
        state.paperId = "";
        state.currentResult = null;
        state.paperText = "";
      }
      renderPapers();
      setRunStatus("已删除文献 " + pid, "success");
    } catch (e) {
      setRunStatus("删除文献失败：" + e.message, "failed");
    }
  }

  async function selectProject(pid) {
    state.currentId = pid;
    state.project = state.projects[pid];
    state.configHydratedFor = null;
    state.selectedStepId = null;
    state.entityDone = false;
    state.completedSteps = [];
    state.lastRunId = null;
    state.currentResult = null;
    state.paperText = "";
    state.selectedPaperIds = {};
    state.paperId = "";
    const p = state.project;
    $("projectTitle").textContent = p.name;
    $("projectDesc").textContent = p.description || "";
    renderProjectList();
    updateDeleteProjectButton();
    renderModelConfig();
    await loadOverlayAndLibrary();
    renderDocumentKindBadges();
    renderStepList();
    renderFieldLibraryChecks();
    renderPropertyGroupList();
    renderFields();
    renderReextractFields();
    renderSchema();
    renderPapers();
    renderSnapshotTable();
    buildPromptPreview();
    loadConfigEditor();
    updateRunButtons();
    clearRunOutputs();
    updateGoReviewButton(false);
    await restoreEntityDoneFromLatestRun();
    if (state.view === "review" && isCurrentPaperExtracted()) {
      loadReview();
    }
  }

  /** 从最新 run 的 completed_steps（或结果 samples）恢复 entityDone，并刷新步骤条 */
  function applyEntityDoneFromRunInfo(info, result) {
    const completed = (info && info.completed_steps) || [];
    state.completedSteps = completed;
    const entityIds = (state.project.steps || [])
      .filter((s) => s.type === "entity")
      .map((s) => s.id);
    state.entityDone =
      entityIds.some((id) => completed.includes(id)) ||
      !!((result || {}).samples || []).length;
    if (info && info.run_id) state.lastRunId = info.run_id;
  }

  async function restoreEntityDoneFromLatestRun() {
    const pid = currentPaperId();
    if (!state.backendOnline || !state.project || !pid) {
      state.entityDone = false;
      renderStepList();
      return;
    }
    try {
      const res = await api(
        `/api/result?project=${encodeURIComponent(state.currentId)}&paper_id=${encodeURIComponent(pid)}`
      );
      applyEntityDoneFromRunInfo(res.run_info || {}, res.result || {});
    } catch (_) {
      state.entityDone = false;
    }
    renderStepList();
  }

  async function loadOverlayAndLibrary() {
    const p = state.project;
    const templateId =
      (state.overlay && state.overlay.template_id) ||
      (p && p.template_id) ||
      "steel";
    if (!state.backendOnline || !p) {
      state.overlay = null;
      state.fieldLibrary = { fields: [] };
      return;
    }
    try {
      state.overlay = await api(`/api/projects/${encodeURIComponent(state.currentId)}/config`);
    } catch (e) {
      try {
        state.overlay = await api(
          `/api/project_config?project=${encodeURIComponent(state.currentId)}`
        );
      } catch (_) {
        state.overlay = null;
      }
    }
    const tid = (state.overlay && state.overlay.template_id) || templateId;
    try {
      state.fieldLibrary = await api(
        `/api/field_library?template=${encodeURIComponent(tid)}`
      );
    } catch (e) {
      state.fieldLibrary = { fields: [] };
    }
  }

  // ---------------------------------------------------------------- step list
  function visibleRunSteps(steps) {
    return (steps || []).filter((s) => s.type !== "figure");
  }

  function stepTypeLabel(t) {
    return t === "entity" ? "骨架"
      : t === "property" ? "性能"
      : t || "";
  }

  function updateGoReviewButton(show) {
    const btn = $("btnGoReview");
    if (!btn) return;
    btn.hidden = !show;
    btn.disabled = !show;
  }

  function setRunStatus(text, kind) {
    const el = $("runStatus");
    if (!el) return;
    el.textContent = text;
    el.classList.remove("running", "failed", "done");
    if (kind) el.classList.add(kind);
  }

  function setConfigStatus(text, kind) {
    const el = $("configStatus");
    if (!el) return;
    el.textContent = text;
    el.hidden = !text;
    el.classList.remove("running", "failed", "done");
    if (kind) el.classList.add(kind);
  }

  function renderStepList() {
    const ol = $("stepList");
    const steps = visibleRunSteps(state.project.steps || []);
    if (!steps.length) {
      ol.innerHTML = "<li>（未配置阶段，使用默认：骨架 → 性能）</li>";
      return;
    }
    if (!state.selectedStepId || !steps.some((s) => s.id === state.selectedStepId)) {
      state.selectedStepId = steps[0].id;
    }
    ol.innerHTML = "";
    steps.forEach((s) => {
      const li = document.createElement("li");
      const needsEntity = s.type === "property";
      const disabled = needsEntity && !state.entityDone;
      const done = (state.completedSteps || []).includes(s.id);
      li.className =
        (s.id === state.selectedStepId ? "active " : "") +
        (disabled ? "disabled " : "") +
        (done ? "done" : "");
      li.setAttribute("data-step-id", s.id);
      li.innerHTML =
        `${esc(s.name || s.id)}${done ? " ✓" : ""}` +
        `<span class="step-type">${esc(stepTypeLabel(s.type))}</span>`;
      if (!disabled) {
        li.addEventListener("click", () => {
          state.selectedStepId = s.id;
          renderStepList();
          updateRunPreview();
        });
      }
      ol.appendChild(li);
    });
  }

  function updateRunButtons() {
    const p = state.project;
    const btns = ["btnRunAll", "btnRunStep", "btnParseOnly", "btnReextract"];
    btns.forEach((id) => {
      const el = $(id);
      if (!el) return;
      el.disabled = !p || !state.backendOnline;
    });
    const imp = $("btnImportPdfs");
    if (imp) imp.disabled = !p || !state.backendOnline;
    $("btnRunAll").textContent = "整篇跑当前";
    updateUploadVisibility();
    updateSelectedRunButton();
  }

  function updateUploadVisibility() {
    const bar = $("paperUploadBar");
    if (!bar) return;
    bar.hidden = !(state.backendOnline && state.project);
  }

  function selectedParsedIds() {
    return Object.keys(state.selectedPaperIds || {}).filter((id) => state.selectedPaperIds[id]);
  }

  function updateSelectedRunButton() {
    const btn = $("btnRunSelected");
    if (!btn) return;
    btn.disabled = !(state.backendOnline && state.project) || selectedParsedIds().length === 0;
  }

  // ---------------------------------------------------------------- model config
  function renderModelConfig() {
    const p = state.project;
    const sel = $("modelSelect");
    sel.innerHTML = "";
    const models = state.models.length
      ? state.models
      : [{ id: p.backend, label: p.backend, backend: p.backend, base_url: "", model: p.backend }];
    models.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.label;
      sel.appendChild(opt);
    });
    const def = models.find((m) => m.backend === p.backend) || models[0];
    sel.value = def.id;
    applyModel(def);
    sel.onchange = () => {
      const m = models.find((x) => x.id === sel.value);
      if (m) applyModel(m);
    };
  }

  function applyModel(m) {
    state.selectedModel = m;
    $("modelBaseUrl").value = m.base_url || "";
    $("modelName").value = m.model || "";
    $("modelInfo").textContent =
      "真实多模态后端：需在工作区 .env 配置 LLM_API_KEY 或 GPUGEEK_API_KEY；base_url / model 取自所选模型。";
  }

  // ---------------------------------------------------------------- field library checkboxes
  function selectedFieldIds() {
    if (state.overlay && Array.isArray(state.overlay.selected_field_ids)) {
      return new Set(state.overlay.selected_field_ids);
    }
    const f = (state.project && state.project.fields) || {};
    const ids = [];
    Object.values(f).forEach((arr) => (arr || []).forEach((id) => ids.push(id)));
    return new Set(ids);
  }

  function allLibraryFields() {
    const lib = (state.fieldLibrary && state.fieldLibrary.fields) || [];
    const priv = (state.overlay && state.overlay.private_fields) || [];
    const seen = new Set();
    const out = [];
    lib.forEach((f) => {
      if (!f || !f.id || seen.has(f.id)) return;
      seen.add(f.id);
      out.push(f);
    });
    priv.forEach((f) => {
      if (!f || !f.id || seen.has(f.id)) return;
      seen.add(f.id);
      out.push(f);
    });
    return out;
  }

  function customPropertyGroups() {
    return ((state.overlay && state.overlay.property_groups) || []).filter(
      (g) => g && g.id && !TEMPLATE_PROPERTY_GROUP_IDS.has(g.id)
    );
  }

  function mergedPropertyGroups() {
    const seen = new Set();
    const out = [];
    TEMPLATE_PROPERTY_GROUPS.forEach((g) => {
      if (seen.has(g.id)) return;
      seen.add(g.id);
      out.push({ id: g.id, name: g.name, template: true });
    });
    customPropertyGroups().forEach((g) => {
      if (seen.has(g.id)) return;
      seen.add(g.id);
      out.push({ id: g.id, name: g.name || g.id, template: false });
    });
    return out;
  }

  function slugifyGroupId(name) {
    const ascii = String(name || "")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
    if (ascii && /^[a-z][a-z0-9_]*$/.test(ascii)) {
      const base = ascii.endsWith("_properties") ? ascii : ascii + "_properties";
      return base;
    }
    const stamp = Date.now().toString(36).slice(-6);
    return "custom_" + stamp + "_properties";
  }

  function autoFieldIdFromLabel(label) {
    const raw = String(label || "").trim();
    if (!raw) return "";
    if (/[^\x00-\x7F]/.test(raw)) {
      return "field_" + Date.now().toString(36);
    }
    const slug = raw
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
    return slug || "field_" + Date.now().toString(36);
  }

  function renderFieldLibraryChecks() {
    const box = $("fieldLibraryChecks");
    if (!box) return;
    const fields = allLibraryFields();
    if (!fields.length) {
      box.innerHTML =
        '<div class="mode-hint">（无字段库或后端未连接；当前项目仍可用已有 fields 配置）</div>';
      return;
    }
    const selected = selectedFieldIds();
    LOCKED_FIELD_IDS.forEach((id) => {
      if (fields.some((f) => f.id === id)) selected.add(id);
    });
    const byCat = {};
    fields.forEach((f) => {
      const cat = f.category || "property";
      (byCat[cat] = byCat[cat] || []).push(f);
    });
    box.innerHTML = "";
    Object.keys(CATEGORY_LABELS).forEach((cat) => {
      const list = byCat[cat];
      if (!list || !list.length) return;
      const group = document.createElement("div");
      group.className = "lib-cat";
      group.innerHTML = `<h4>${esc(CATEGORY_LABELS[cat])}</h4>`;
      if (cat === "property") {
        const groups = mergedPropertyGroups();
        const used = new Set();
        groups.forEach((ginfo) => {
          const glist = list.filter((f) => (f.group || "") === ginfo.id);
          if (!glist.length) return;
          glist.forEach((f) => used.add(f.id));
          const sub = document.createElement("div");
          sub.className = "lib-prop-group";
          sub.innerHTML = `<h5>${esc(ginfo.name || ginfo.id)}</h5>`;
          const wrap = document.createElement("div");
          wrap.className = "lib-checks";
          glist.forEach((f) => appendLibraryCheck(wrap, f, cat, selected));
          sub.appendChild(wrap);
          group.appendChild(sub);
        });
        const orphan = list.filter((f) => !used.has(f.id));
        if (orphan.length) {
          const sub = document.createElement("div");
          sub.className = "lib-prop-group";
          sub.innerHTML = "<h5>其他</h5>";
          const wrap = document.createElement("div");
          wrap.className = "lib-checks";
          orphan.forEach((f) => appendLibraryCheck(wrap, f, cat, selected));
          sub.appendChild(wrap);
          group.appendChild(sub);
        }
      } else {
        const wrap = document.createElement("div");
        wrap.className = "lib-checks";
        list.forEach((f) => appendLibraryCheck(wrap, f, cat, selected));
        group.appendChild(wrap);
      }
      box.appendChild(group);
    });
  }

  function appendLibraryCheck(wrap, f, cat, selected) {
    const locked = LOCKED_FIELD_IDS.has(f.id);
    const lab = document.createElement("label");
    lab.className = "check-item" + (locked ? " locked-field" : "");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = locked || selected.has(f.id);
    cb.disabled = locked;
    cb.dataset.fieldId = f.id;
    if (!locked) {
      cb.addEventListener("change", () => onLibraryCheckChange(f.id, cb.checked));
    }
    lab.appendChild(cb);
    lab.appendChild(document.createTextNode(` ${f.label || f.id}`));
    if (locked) {
      lab.title = "锁定字段，不可取消";
    }
    if (cb.checked && !locked) {
      const ruleBtn = document.createElement("button");
      ruleBtn.type = "button";
      ruleBtn.className = "ghost rule-mini";
      ruleBtn.textContent = "规则";
      ruleBtn.addEventListener("click", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        openRuleDialog(f.category || cat, f.id);
      });
      lab.appendChild(ruleBtn);
    }
    wrap.appendChild(lab);
  }

  function groupDisplayName(groupId) {
    const gid = groupId || "";
    const fromOverlay = customPropertyGroups().find((g) => g.id === gid);
    if (fromOverlay && fromOverlay.name) return fromOverlay.name;
    const fromTemplate = TEMPLATE_PROPERTY_GROUPS.find((g) => g.id === gid);
    if (fromTemplate) return fromTemplate.name;
    if (gid.endsWith("_properties")) return gid.slice(0, -"_properties".length) || "其他性能";
    return gid || "其他性能";
  }

  function renderPropertyGroupList() {
    const box = $("propertyGroupList");
    if (!box) return;
    const groups = mergedPropertyGroups();
    if (!groups.length) {
      box.innerHTML = '<div class="mode-hint">（暂无性能大类）</div>';
      return;
    }
    box.innerHTML = "";
    groups.forEach((g) => {
      const row = document.createElement("div");
      row.className = "property-group-row";
      const name = document.createElement("span");
      name.className = "property-group-name";
      name.textContent = g.name || g.id;
      const meta = document.createElement("span");
      meta.className = "property-group-meta";
      meta.textContent = g.template ? "模板" : "自建 · " + g.id;
      row.appendChild(name);
      row.appendChild(meta);
      if (!g.template) {
        const del = document.createElement("button");
        del.type = "button";
        del.className = "ghost tiny";
        del.textContent = "删除";
        del.addEventListener("click", () => removeCustomPropertyGroup(g.id));
        row.appendChild(del);
      }
      box.appendChild(row);
    });
  }

  function addCustomPropertyGroup() {
    if (!state.overlay) {
      setConfigStatus("无覆盖层，无法添加大类。", "failed");
      return;
    }
    const name = window.prompt("请输入性能大类中文名（如：疲劳性能）", "");
    if (name == null) return;
    const trimmed = String(name).trim();
    if (!trimmed) {
      setConfigStatus("大类中文名不能为空。", "failed");
      return;
    }
    let gid = slugifyGroupId(trimmed);
    const existing = new Set(mergedPropertyGroups().map((g) => g.id));
    if (existing.has(gid)) {
      let n = 2;
      const base = gid.replace(/_properties$/, "");
      while (existing.has(base + "_" + n + "_properties")) n += 1;
      gid = base + "_" + n + "_properties";
    }
    if (!/^[a-z][a-z0-9_]*$/.test(gid)) {
      setConfigStatus("大类 id 非法。", "failed");
      return;
    }
    state.overlay.property_groups = customPropertyGroups();
    state.overlay.property_groups.push({ id: gid, name: trimmed });
    renderPropertyGroupList();
    fillFieldGroupSelect();
    setConfigStatus("已添加自建大类「" + trimmed + "」，保存配置后落盘。", "running");
  }

  function removeCustomPropertyGroup(groupId) {
    if (!state.overlay || TEMPLATE_PROPERTY_GROUP_IDS.has(groupId)) return;
    const usedInStage = (state.stageDraft || []).some((s) => s.group === groupId);
    const selected = selectedFieldIds();
    const usedInField = allLibraryFields().some(
      (f) =>
        f.category === "property" &&
        f.group === groupId &&
        selected.has(f.id)
    );
    if (usedInStage || usedInField) {
      setConfigStatus("该类仍有已选性能字段或阶段占用，请先改挂或取消勾选后再删。", "failed");
      return;
    }
    state.overlay.property_groups = customPropertyGroups().filter((g) => g.id !== groupId);
    renderPropertyGroupList();
    fillFieldGroupSelect();
    renderFieldLibraryChecks();
    setConfigStatus("已从草稿移除自建大类，保存配置后生效。", "running");
  }

  function fillFieldGroupSelect() {
    const sel = $("fieldGroup");
    if (!sel) return;
    const cur = sel.value;
    sel.innerHTML = '<option value="">请选择大类</option>';
    mergedPropertyGroups().forEach((g) => {
      const opt = document.createElement("option");
      opt.value = g.id;
      opt.textContent = g.name || g.id;
      sel.appendChild(opt);
    });
    if (cur && [...sel.options].some((o) => o.value === cur)) sel.value = cur;
  }

  function syncFieldGroupVisibility() {
    const wrap = $("fieldGroupWrap");
    const level = $("fieldLevel");
    if (!wrap || !level) return;
    const isProp = level.value === "property";
    wrap.hidden = !isProp;
    if (isProp) fillFieldGroupSelect();
  }

  function openFieldDialog() {
    fillFieldGroupSelect();
    syncFieldGroupVisibility();
    if ($("fieldLabel")) $("fieldLabel").value = "";
    if ($("fieldName")) $("fieldName").value = "";
    if ($("fieldRule")) $("fieldRule").value = "";
    if ($("positiveExamples")) $("positiveExamples").value = "";
    if ($("negativeExamples")) $("negativeExamples").value = "";
    if ($("fieldLevel")) $("fieldLevel").value = "property";
    syncFieldGroupVisibility();
    $("fieldDialog").showModal();
  }

  function assignPropertyToDraft(field) {
    if (!field || !field.id) return;
    const fid = field.id;
    if (state.stageDraft.some((s) => (s.fields || []).includes(fid))) return;
    const group = field.group || "";
    let target = null;
    if (group) {
      target = state.stageDraft.find((s) => s.group === group) || null;
    } else {
      target = state.stageDraft.find((s) => s.id === "other") || null;
      if (!target) {
        target = {
          id: "other",
          name: "其他性能",
          group: "other_properties",
          fields: [],
        };
        state.stageDraft.push(target);
      }
    }
    if (!target) {
      const baseId = group.endsWith("_properties")
        ? group.slice(0, -"_properties".length) || "other"
        : group || "other";
      let stepId = baseId;
      const existing = new Set(state.stageDraft.map((s) => s.id));
      let n = 2;
      while (existing.has(stepId)) {
        stepId = baseId + "_" + n;
        n += 1;
      }
      target = {
        id: stepId,
        name: groupDisplayName(group),
        group: group || "other_properties",
        fields: [],
      };
      state.stageDraft.push(target);
    }
    if (!target.fields) target.fields = [];
    if (!target.fields.includes(fid)) target.fields.push(fid);
  }

  async function onLibraryCheckChange(fieldId, checked) {
    if (!state.overlay) {
      setConfigStatus("无覆盖层，无法勾选。", "failed");
      return;
    }
    if (LOCKED_FIELD_IDS.has(fieldId) && !checked) {
      renderFieldLibraryChecks();
      return;
    }
    const ids = new Set(selectedFieldIds());
    if (checked) ids.add(fieldId);
    else ids.delete(fieldId);
    LOCKED_FIELD_IDS.forEach((id) => {
      const fields = allLibraryFields();
      if (fields.some((f) => f.id === id)) ids.add(id);
    });
    state.overlay.selected_field_ids = Array.from(ids);

    const libFields = allLibraryFields();
    const meta = libFields.find((f) => f.id === fieldId);
    const isProperty = meta && meta.category === "property";

    if (checked && isProperty) {
      assignPropertyToDraft(meta);
    } else if (!checked && isProperty) {
      syncStageDraftFromDom();
      state.stageDraft = state.stageDraft.filter((s) => {
        const fields = s.fields || [];
        const had = fields.includes(fieldId);
        s.fields = fields.filter((id) => id !== fieldId);
        if (had && s.fields.length === 0) return false;
        return true;
      });
    }

    renderFieldLibraryChecks();
    renderStageEditor();
    setConfigStatus(checked ? "已更新草稿，保存配置后生效。" : "已从草稿移除，保存配置后生效。", "running");
  }

  async function saveOverlay(overlay) {
    await api(`/api/projects/${encodeURIComponent(state.currentId)}/config`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(overlay),
    });
  }

  async function refreshProjectConfig() {
    const keepDraft = state.configHydratedFor === state.currentId;
    let savedSelected = null;
    let savedStageDraft = null;
    let savedPropertyGroups = null;
    let savedPrivateFields = null;
    let savedDocumentKind = null;
    if (keepDraft) {
      savedSelected = JSON.parse(
        JSON.stringify((state.overlay && state.overlay.selected_field_ids) || [])
      );
      savedStageDraft = JSON.parse(JSON.stringify(state.stageDraft || []));
      savedPropertyGroups = JSON.parse(
        JSON.stringify((state.overlay && state.overlay.property_groups) || [])
      );
      savedPrivateFields = JSON.parse(
        JSON.stringify((state.overlay && state.overlay.private_fields) || [])
      );
      savedDocumentKind = (state.overlay && state.overlay.document_kind) || "paper";
    }
    await reloadProjects();
    state.project = state.projects[state.currentId];
    await loadOverlayAndLibrary();
    // Server-aligned snapshot before restoring draft checks / stageDraft
    state.persistedOverlay = state.overlay
      ? JSON.parse(JSON.stringify(state.overlay))
      : null;
    if (keepDraft && state.overlay) {
      state.overlay.selected_field_ids = savedSelected;
      state.overlay.property_groups = savedPropertyGroups;
      state.overlay.private_fields = savedPrivateFields;
      state.overlay.document_kind = savedDocumentKind;
      state.stageDraft = savedStageDraft;
    }
    renderStepList();
    renderFieldLibraryChecks();
    renderPropertyGroupList();
    renderFields();
    renderReextractFields();
    renderSchema();
    buildPromptPreview();
    loadConfigEditor();
    renderDocumentKindBadges();
    renderProjectList();
  }

  // ---------------------------------------------------------------- config view: stages + strategy
  function splitCsv(text) {
    return String(text || "")
      .split(/[,，\n]/)
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function joinCsv(arr) {
    return (arr || []).join(", ");
  }

  function propertyIdsSelected() {
    const selected = selectedFieldIds();
    const fields = allLibraryFields();
    if (fields.length) {
      return fields
        .filter((f) => f.category === "property" && selected.has(f.id))
        .map((f) => f.id);
    }
    const fromProject = ((state.project && state.project.fields) || {}).property || [];
    return fromProject.filter((id) => selected.has(id));
  }

  function fieldLabel(id) {
    const fields = allLibraryFields();
    const f = fields.find((x) => x.id === id);
    return (f && f.label) || id;
  }

  function fieldGroup(id) {
    const fields = allLibraryFields();
    const f = fields.find((x) => x.id === id);
    return (f && f.group) || null;
  }

  function inferGroup(fields, fallbackId) {
    const groups = fields.map(fieldGroup).filter(Boolean);
    if (groups.length && groups.every((g) => g === groups[0])) return groups[0];
    return (fallbackId || "custom") + "_properties";
  }

  function loadStageDraftFromOverlay() {
    const src =
      (state.overlay && state.overlay.steps) ||
      (state.project && state.project.steps) ||
      [];
    state.stageDraft = src
      .filter((s) => s && s.type === "property")
      .map((s) => ({
        id: s.id,
        name: s.name || s.id,
        group: s.group || inferGroup(s.fields || [], s.id),
        fields: Array.isArray(s.fields) ? s.fields.slice() : [],
      }));
  }

  function fillStrategyForms() {
    const src =
      (state.overlay && state.overlay.property_source) ||
      (state.project && state.project.property_source) ||
      {};
    const ff =
      (state.overlay && state.overlay.figure_filter) ||
      (state.project && state.project.figure_filter) ||
      {};
    if ($("strategyAllow")) $("strategyAllow").value = joinCsv(src.allow);
    if ($("strategyDeny")) $("strategyDeny").value = joinCsv(src.deny);
    if ($("strategyDenyPhrases"))
      $("strategyDenyPhrases").value = joinCsv(src.deny_phrase_patterns);
    if ($("strategyKeepTypes")) $("strategyKeepTypes").value = joinCsv(ff.keep_types);
    if ($("strategyDropTypes")) $("strategyDropTypes").value = joinCsv(ff.drop_types);
    if ($("strategyRequireMicro"))
      $("strategyRequireMicro").checked = !!ff.require_microstructure;
    if ($("strategyDropPostTest"))
      $("strategyDropPostTest").checked = !!ff.drop_if_post_test;
  }

  function readStrategyPropertySource() {
    return {
      allow: splitCsv($("strategyAllow") && $("strategyAllow").value),
      deny: splitCsv($("strategyDeny") && $("strategyDeny").value),
      deny_phrase_patterns: splitCsv(
        $("strategyDenyPhrases") && $("strategyDenyPhrases").value
      ),
    };
  }

  function readStrategyFigureFilter() {
    return {
      keep_types: splitCsv($("strategyKeepTypes") && $("strategyKeepTypes").value),
      drop_types: splitCsv($("strategyDropTypes") && $("strategyDropTypes").value),
      require_microstructure: !!(
        $("strategyRequireMicro") && $("strategyRequireMicro").checked
      ),
      drop_if_post_test: !!(
        $("strategyDropPostTest") && $("strategyDropPostTest").checked
      ),
    };
  }

  function syncStageDraftFromDom() {
    const box = $("stageEditor");
    if (!box) return;
    box.querySelectorAll(".stage-row[data-stage-id]").forEach((row) => {
      const id = row.getAttribute("data-stage-id");
      const draft = state.stageDraft.find((s) => s.id === id);
      if (!draft) return;
      const nameInput = row.querySelector(".stage-name");
      if (nameInput) draft.name = nameInput.value.trim() || draft.id;
    });
  }

  function moveFieldBetweenStages(fieldId, fromStageId, toStageId) {
    if (!toStageId || fromStageId === toStageId) return;
    const from = state.stageDraft.find((s) => s.id === fromStageId);
    const to = state.stageDraft.find((s) => s.id === toStageId);
    if (!from || !to) return;
    from.fields = (from.fields || []).filter((id) => id !== fieldId);
    if (!(to.fields || []).includes(fieldId)) {
      to.fields = (to.fields || []).concat([fieldId]);
    }
    renderStageEditor();
  }

  function renderStageEditor() {
    const box = $("stageEditor");
    if (!box) return;
    const propIds = propertyIdsSelected();
    const assigned = new Set();
    state.stageDraft.forEach((s) => (s.fields || []).forEach((id) => assigned.add(id)));

    box.innerHTML = "";
    const entity = document.createElement("div");
    entity.className = "stage-row entity-row";
    entity.innerHTML =
      '<div class="stage-row-head"><strong>骨架</strong>' +
      '<span class="mode-hint">文章 / 样品 / 状态（固定第一阶段，不可删改）</span></div>';
    box.appendChild(entity);

    state.stageDraft.forEach((stage, idx) => {
      const row = document.createElement("div");
      row.className = "stage-row";
      row.dataset.stageId = stage.id;

      const head = document.createElement("div");
      head.className = "stage-row-head";
      const nameInput = document.createElement("input");
      nameInput.className = "stage-name";
      nameInput.type = "text";
      nameInput.value = stage.name || stage.id;
      nameInput.addEventListener("change", () => {
        stage.name = nameInput.value.trim() || stage.id;
      });
      head.appendChild(nameInput);

      const actions = document.createElement("div");
      actions.className = "stage-row-actions";
      const mkBtn = (label, fn, disabled) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "ghost";
        b.textContent = label;
        b.disabled = !!disabled;
        b.addEventListener("click", fn);
        return b;
      };
      actions.appendChild(
        mkBtn("上移", () => {
          syncStageDraftFromDom();
          if (idx <= 0) return;
          const t = state.stageDraft[idx - 1];
          state.stageDraft[idx - 1] = state.stageDraft[idx];
          state.stageDraft[idx] = t;
          renderStageEditor();
        }, idx === 0)
      );
      actions.appendChild(
        mkBtn("下移", () => {
          syncStageDraftFromDom();
          if (idx >= state.stageDraft.length - 1) return;
          const t = state.stageDraft[idx + 1];
          state.stageDraft[idx + 1] = state.stageDraft[idx];
          state.stageDraft[idx] = t;
          renderStageEditor();
        }, idx === state.stageDraft.length - 1)
      );
      actions.appendChild(
        mkBtn("删除", () => {
          syncStageDraftFromDom();
          state.stageDraft.splice(idx, 1);
          renderStageEditor();
        })
      );
      head.appendChild(actions);
      row.appendChild(head);

      const fieldsWrap = document.createElement("div");
      fieldsWrap.className = "stage-fields";
      const stageFields = (stage.fields || []).filter((fid) => propIds.includes(fid));
      if (!stageFields.length) {
        fieldsWrap.innerHTML = '<span class="mode-hint">（本段暂无性能字段）</span>';
      } else {
        stageFields.forEach((fid) => {
          const chip = document.createElement("span");
          chip.className = "stage-chip";
          chip.dataset.fieldId = fid;
          chip.appendChild(document.createTextNode(fieldLabel(fid)));
          const otherStages = state.stageDraft.filter((s) => s.id !== stage.id);
          if (otherStages.length) {
            const sel = document.createElement("select");
            sel.className = "stage-chip-move";
            sel.title = "移至其他阶段";
            const placeholder = document.createElement("option");
            placeholder.value = "";
            placeholder.textContent = "移至…";
            sel.appendChild(placeholder);
            otherStages.forEach((s) => {
              const opt = document.createElement("option");
              opt.value = s.id;
              opt.textContent = s.name || s.id;
              sel.appendChild(opt);
            });
            sel.addEventListener("change", () => {
              const toId = sel.value;
              if (!toId) return;
              syncStageDraftFromDom();
              moveFieldBetweenStages(fid, stage.id, toId);
            });
            chip.appendChild(sel);
          }
          fieldsWrap.appendChild(chip);
        });
      }
      row.appendChild(fieldsWrap);
      box.appendChild(row);
    });

    const unassigned = propIds.filter((id) => !assigned.has(id));
    if (unassigned.length) {
      const hint = document.createElement("div");
      hint.className = "mode-hint";
      hint.textContent =
        "未挂阶段：" + unassigned.map((id) => fieldLabel(id)).join("、");
      box.appendChild(hint);
    }
  }

  function loadConfigEditor() {
    if (state.configHydratedFor !== state.currentId) {
      loadStageDraftFromOverlay();
      if (state.overlay) {
        state.overlay.property_groups = customPropertyGroups();
      }
      // 已选性能字段但无性能段时，按挂段规则生成初稿（有 steps 则保留）
      if (!state.stageDraft.length) {
        propertyIdsSelected().forEach((id) => {
          const fields = allLibraryFields();
          const meta = fields.find((f) => f.id === id);
          if (meta) assignPropertyToDraft(meta);
        });
      }
      const ids = new Set(selectedFieldIds());
      const libFields = allLibraryFields();
      LOCKED_FIELD_IDS.forEach((id) => {
        if (libFields.some((f) => f.id === id)) ids.add(id);
      });
      if (state.overlay) state.overlay.selected_field_ids = Array.from(ids);
      fillStrategyForms();
      state.configHydratedFor = state.currentId;
      if (state.overlay) {
        state.persistedOverlay = JSON.parse(JSON.stringify(state.overlay));
      }
    }
    renderFieldLibraryChecks();
    renderPropertyGroupList();
    renderStageEditor();
    fillDocumentKindSelect();
  }

  function fillDocumentKindSelect() {
    const sel = $("documentKind");
    if (!sel) return;
    const kind = state.overlay && state.overlay.document_kind === "patent" ? "patent" : "paper";
    sel.value = kind;
  }

  function documentKindLabel(kind) {
    return kind === "patent" ? "专利" : "文献";
  }

  function renderDocumentKindBadges() {
    const kind = (state.overlay && state.overlay.document_kind)
      || (state.project && state.project.document_kind)
      || "paper";
    const label = documentKindLabel(kind);
    if ($("projectKindBadge")) $("projectKindBadge").textContent = label;
    if ($("papersKindBadge")) $("papersKindBadge").textContent = label;
  }

  function buildStepsFromEditor() {
    syncStageDraftFromDom();
    const steps = [{ id: "entity", type: "entity", name: "骨架" }];
    state.stageDraft.forEach((s) => {
      const fields = (s.fields || []).slice();
      steps.push({
        id: s.id,
        type: "property",
        name: s.name || s.id,
        group: s.group || inferGroup(fields, s.id),
        fields,
      });
    });
    return steps;
  }

  function addPropertyStage() {
    syncStageDraftFromDom();
    const id = "prop_" + Date.now().toString(36);
    state.stageDraft.push({
      id,
      name: "新性能阶段",
      group: id + "_properties",
      fields: [],
    });
    renderStageEditor();
  }

  async function saveConfigView() {
    if (!state.overlay) {
      setConfigStatus("无覆盖层，无法保存配置。", "failed");
      return;
    }
    let steps = buildStepsFromEditor();
    steps = steps.filter((s) => s.type !== "property" || (s.fields || []).length);
    const unassigned = propertyIdsSelected().filter(
      (id) =>
        !steps.some((s) => s.type === "property" && (s.fields || []).includes(id))
    );
    if (unassigned.length) {
      setConfigStatus(
        "未挂阶段的性能字段：" + unassigned.map((id) => fieldLabel(id)).join("、"),
        "failed"
      );
      return;
    }
    const selected = new Set(selectedFieldIds());
    const libFields = allLibraryFields();
    LOCKED_FIELD_IDS.forEach((id) => {
      if (libFields.some((f) => f.id === id)) selected.add(id);
    });
    state.overlay.steps = steps;
    state.overlay.selected_field_ids = Array.from(selected);
    state.overlay.property_groups = state.overlay.property_groups || [];
    state.overlay.property_groups = customPropertyGroups();
    state.overlay.property_source = readStrategyPropertySource();
    state.overlay.figure_filter = readStrategyFigureFilter();
    state.overlay.document_kind = ($("documentKind") && $("documentKind").value) || "paper";
    try {
      await saveOverlay(state.overlay);
      logChange("保存配置（字段 / 阶段 / 策略 / 文档类型）");
      setConfigStatus("配置已保存。需重新抽取后结果才按新配置。", "done");
      state.configHydratedFor = null;
      await refreshProjectConfig();
    } catch (e) {
      setConfigStatus("保存配置失败：" + e.message, "failed");
    }
  }

  // ---------------------------------------------------------------- fields chips
  function renderFields() {
    const p = state.project;
    const fields = p.fields || {};
    FIELD_LEVELS.forEach(([level, boxId, countId]) => {
      const box = $(boxId);
      box.innerHTML = "";
      const list = fields[level] || [];
      $(countId).textContent = list.length;
      list.forEach((name) => {
        const chip = document.createElement("button");
        chip.className = "chip";
        chip.textContent = name;
        chip.title = "点击查看/编辑抽取规则";
        chip.addEventListener("click", () => openRuleDialog(level, name));
        box.appendChild(chip);
      });
      if (!list.length) {
        const empty = document.createElement("span");
        empty.className = "chip empty";
        empty.textContent = "（无）";
        box.appendChild(empty);
      }
    });
    $("paperCount").textContent = (p.papers || []).length;
    $("metadataOutput").textContent =
      "选择「" + p.name + "」后用四个入口跑抽取，查看真实输出。";
  }

  function renderReextractFields() {
    const sel = $("reextractField");
    sel.innerHTML = "";
    const fields = pFieldsFlat();
    const candidates = fields.filter((id) => !IDENTITY_IDS.has(id));
    if (!candidates.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "（无可重抽字段）";
      sel.appendChild(opt);
      return;
    }
    candidates.forEach((id) => {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = id;
      sel.appendChild(opt);
    });
  }

  function pFieldsFlat() {
    const f = (state.project && state.project.fields) || {};
    const out = [];
    ["metadata", "sample", "condition", "property", "figure"].forEach((cat) => {
      (f[cat] || []).forEach((id) => out.push(id));
    });
    return out;
  }

  // ---------------------------------------------------------------- schema preview
  function schemaLeaf(name) {
    if (/^is_/.test(name)) return true;
    if (/_index$/.test(name)) return 0;
    if (name === "composition") return { C: "...", Cr: "...", "…": "..." };
    if (name === "test_temperature" || name === "scale_bar_info") return { value: "...", unit: "..." };
    return "...";
  }

  function objFromFields(keys) {
    const o = {};
    (keys || []).forEach((k) => (o[k] = schemaLeaf(k)));
    return o;
  }

  function buildSchema() {
    const p = state.project;
    const f = p.fields || {};
    const condObj = objFromFields(f.condition);
    const propSteps = (p.steps || []).filter((s) => s.type === "property");
    if (propSteps.length) {
      propSteps.forEach((s) => {
        const group = s.group || "properties";
        condObj[group] = {};
        (s.fields || []).forEach((k) => (condObj[group][k] = { value: "...", unit: "..." }));
      });
    } else if ((f.property || []).length) {
      condObj.properties = {};
      f.property.forEach((k) => (condObj.properties[k] = { value: "...", unit: "..." }));
    }
    return {
      paper_metadata: objFromFields(f.metadata),
      samples: [objFromFields(f.sample)],
      conditions: [condObj],
      figures: [objFromFields(f.figure)],
    };
  }

  function renderSchema() {
    if (!state.project) {
      state.schemaText = "";
      if ($("schemaPreview")) $("schemaPreview").textContent = "";
      if ($("schemaPreviewMain")) $("schemaPreviewMain").textContent = "请先选择项目。";
      return;
    }
    state.schemaText = JSON.stringify(buildSchema(), null, 2);
    if ($("schemaPreview")) $("schemaPreview").textContent = state.schemaText;
    if ($("schemaPreviewMain")) $("schemaPreviewMain").textContent = state.schemaText;
  }

  function copySchemaText() {
    const text = state.schemaText || "";
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text);
    }
    if ($("runStatus")) $("runStatus").textContent = text ? "已复制 Schema。" : "暂无 Schema 可复制。";
  }

  function selectedExportPaperIds() {
    return Array.from(document.querySelectorAll("#exportPaperChecks input[data-export-paper]:checked"))
      .map((el) => el.getAttribute("data-export-paper"))
      .filter(Boolean);
  }

  function renderExportPaperChecks() {
    const box = $("exportPaperChecks");
    if (!box) return;
    const prev = new Set(selectedExportPaperIds());
    if (!prev.size && state.paperId) prev.add(state.paperId);
    const items = extractedPaperRecords();
    box.innerHTML = "";
    if (!items.length) {
      box.innerHTML = '<div class="mode-hint">本项目还没有已抽取文献，请先在「抽取」页完成抽取。</div>';
      if ($("exportSelectAll")) $("exportSelectAll").checked = false;
      return;
    }
    items.forEach((rec) => {
      const label = document.createElement("label");
      label.className = "check-item";
      const inp = document.createElement("input");
      inp.type = "checkbox";
      inp.setAttribute("data-export-paper", rec.paper_id);
      inp.checked = prev.has(rec.paper_id);
      const span = document.createElement("span");
      span.textContent = (rec.title || rec.paper_id) + "（" + rec.paper_id + "）";
      label.appendChild(inp);
      label.appendChild(span);
      box.appendChild(label);
    });
    syncExportSelectAll();
  }

  function syncExportSelectAll() {
    const all = document.querySelectorAll("#exportPaperChecks input[data-export-paper]");
    const checked = document.querySelectorAll("#exportPaperChecks input[data-export-paper]:checked");
    if ($("exportSelectAll")) {
      $("exportSelectAll").checked = all.length > 0 && checked.length === all.length;
    }
    if ($("exportResultsStatus")) {
      $("exportResultsStatus").textContent = all.length
        ? `已选 ${checked.length} / ${all.length} 篇`
        : "";
    }
  }

  // ---------------------------------------------------------------- rule dialog
  let editingRuleKey = null;
  function openRuleDialog(level, field) {
    const key = `${level}.${field}`;
    editingRuleKey = key;
    state.editingRule = { level, field, id: field };
    const rules = state.project.rules || {};
    const r = rules[key] || {};
    $("ruleDialogTitle").textContent = `字段规则 · ${key}`;
    $("editRuleText").value = r.rule || "";
    $("editPositiveExamples").value = r.positive_examples || "";
    $("editNegativeExamples").value = r.negative_examples || "";
    $("ruleScopeProject").checked = true;
    $("ruleDialogNote").textContent = rules[key]
      ? (r.note || "默认仅写本项目覆盖层；勾选「写回公共库」才会改库文件。")
      : "该字段暂无规则，可在此填写。";
    $("ruleDialog").showModal();
  }

  async function saveRuleOverride() {
    if (!editingRuleKey || !state.editingRule) return;
    const fid = state.editingRule.id;
    const patch = {
      rule: $("editRuleText").value,
      positive_examples: $("editPositiveExamples").value,
      negative_examples: $("editNegativeExamples").value,
    };
    const scope = ($("ruleScopeLibrary").checked && "library") || "project";

    if (!state.backendOnline || !state.project) {
      const rules = state.project.rules || (state.project.rules = {});
      rules[editingRuleKey] = { ...patch, note: "本地修改（预览）" };
      logChange(`修改规则 ${editingRuleKey}（本地）`);
      buildPromptPreview();
      return;
    }

    try {
      if (scope === "library") {
        const tid =
          (state.overlay && state.overlay.template_id) || "steel";
        const libFields = (state.fieldLibrary && state.fieldLibrary.fields) || [];
        const base = libFields.find((f) => f.id === fid) || {
          id: fid,
          category: state.editingRule.level,
          label: fid,
        };
        await api("/api/field_library/writeback", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            template_id: tid,
            field: { ...base, ...patch, id: fid },
          }),
        });
        logChange(`写回公共库规则 ${fid}`);
      } else {
        if (!state.overlay) throw new Error("无覆盖层");
        const target = state.persistedOverlay || state.overlay;
        const overrides = target.field_overrides || (target.field_overrides = {});
        overrides[fid] = { ...(overrides[fid] || {}), ...patch };
        if (state.overlay && state.overlay !== target) {
          state.overlay.field_overrides = state.overlay.field_overrides || {};
          state.overlay.field_overrides[fid] = { ...(overrides[fid] || {}) };
        }
        await saveOverlay(target);
        logChange(`仅本项目修改规则 ${fid}`);
      }
      await refreshProjectConfig();
    } catch (e) {
      $("runStatus").textContent = "保存规则失败：" + e.message;
    }
  }

  function resetRuleOverride() {
    if (!editingRuleKey || !state.editingRule) return;
    const fid = state.editingRule.id;
    const target = state.persistedOverlay || state.overlay;
    if (target && target.field_overrides) {
      delete target.field_overrides[fid];
      if (state.overlay && state.overlay !== target && state.overlay.field_overrides) {
        delete state.overlay.field_overrides[fid];
      }
      saveOverlay(target)
        .then(() => {
          logChange(`清除覆盖 ${fid}`);
          return refreshProjectConfig();
        })
        .catch((e) => {
          $("runStatus").textContent = "重置失败：" + e.message;
        });
    } else {
      logChange(`重置规则 ${editingRuleKey}（本地）`);
    }
  }

  // ---------------------------------------------------------------- add field → private_fields
  async function saveNewField() {
    const labelEl = $("fieldLabel");
    const label = (labelEl && labelEl.value.trim()) || "";
    const level = $("fieldLevel").value;
    let name = ($("fieldName") && $("fieldName").value.trim()) || "";
    if (!label) {
      setConfigStatus("中文名不能为空。", "failed");
      return;
    }
    if (!name) name = autoFieldIdFromLabel(label);
    if (!name) {
      setConfigStatus("无法生成字段 id。", "failed");
      return;
    }
    const groupSel = $("fieldGroup");
    const groupVal = groupSel ? groupSel.value : "";
    if (level === "property" && !groupVal) {
      setConfigStatus("性能字段必须选择大类。", "failed");
      return;
    }
    if (allLibraryFields().some((f) => f.id === name)) {
      setConfigStatus("字段 id 已存在：" + name, "failed");
      return;
    }
    const fieldObj = {
      id: name,
      label: label,
      category: level,
      group: level === "property" ? groupVal : null,
      value_type: level === "property" ? "number_with_unit" : "string",
      rule: $("fieldRule").value,
      positive_examples: $("positiveExamples").value,
      negative_examples: $("negativeExamples").value,
      note: "私有字段",
    };

    if (!state.backendOnline || !state.project || !state.overlay) {
      const fields = state.project.fields || (state.project.fields = {});
      fields[level] = fields[level] || [];
      if (!fields[level].includes(name)) fields[level].push(name);
      const rules = state.project.rules || (state.project.rules = {});
      rules[`${level}.${name}`] = {
        rule: fieldObj.rule,
        positive_examples: fieldObj.positive_examples,
        negative_examples: fieldObj.negative_examples,
        note: "本地新增字段（预览）",
      };
      logChange(`新增字段 ${level}.${name}（本地）`);
      renderFields();
      renderSchema();
      buildPromptPreview();
      return;
    }

    const priv = state.overlay.private_fields || (state.overlay.private_fields = []);
    if (!priv.some((f) => f.id === name)) priv.push(fieldObj);
    const selected = new Set(selectedFieldIds());
    selected.add(name);
    state.overlay.selected_field_ids = Array.from(selected);
    if (level === "property") assignPropertyToDraft(fieldObj);
    logChange(`新增私有字段 ${label}（${name}），保存配置后落盘`);
    setConfigStatus("已加入草稿私有字段，保存配置后生效。", "running");
    renderFieldLibraryChecks();
    renderPropertyGroupList();
    renderStageEditor();
    if ($("fieldDialog") && $("fieldDialog").open) $("fieldDialog").close();
  }

  function logChange(text) {
    state.changeLog.unshift({ time: new Date().toLocaleTimeString(), text });
    const box = $("changeLog");
    box.innerHTML = state.changeLog
      .slice(0, 20)
      .map((c) => `<div class="log-item"><span class="log-time">${esc(c.time)}</span> ${esc(c.text)}</div>`)
      .join("");
  }

  // ---------------------------------------------------------------- export
  function downloadJsonBlob(data, filename) {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function exportProject() {
    if (!state.currentId) return;
    try {
      const data = await api(`/api/projects/${encodeURIComponent(state.currentId)}/export`);
      const filename = `${state.currentId}_fields_schema.json`;
      downloadJsonBlob(data, filename);
      logChange(`导出 ${filename}`);
      $("runStatus").textContent = "已下载项目配置。";
    } catch (e) {
      $("runStatus").textContent = "导出失败：" + e.message;
    }
  }

  async function exportResults() {
    if (!state.currentId) return;
    const includeRejected = $("includeRejected").checked;
    const paperIds = selectedExportPaperIds();
    if (!paperIds.length) {
      $("runStatus").textContent = "请先勾选要导出的文献。";
      if ($("exportResultsStatus")) $("exportResultsStatus").textContent = "请先勾选文献。";
      return;
    }
    const qs = new URLSearchParams({ include_rejected: includeRejected ? "true" : "false" });
    qs.set("paper_ids", paperIds.join(","));
    try {
      const data = await api(
        `/api/projects/${encodeURIComponent(state.currentId)}/export_results?${qs}`
      );
      const filename =
        paperIds.length === 1
          ? `${state.currentId}_${paperIds[0]}_results.json`
          : `${state.currentId}_${paperIds.length}papers_results.json`;
      downloadJsonBlob(data, filename);
      logChange(`导出 ${filename}`);
      $("runStatus").textContent = `已下载 ${paperIds.length} 篇抽取结果。`;
      if ($("exportResultsStatus")) $("exportResultsStatus").textContent = `已导出 ${paperIds.length} 篇。`;
    } catch (e) {
      $("runStatus").textContent = "导出结果失败：" + e.message;
    }
  }

  function setLegacyDevPanelsVisible(visible) {
    const box = $("legacyDevPanels");
    if (box) box.hidden = !visible;
  }

  // ---------------------------------------------------------------- new project
  function fillNewProjectCopyFrom() {
    const sel = $("newProjectCopyFrom");
    if (!sel) return;
    const keep = sel.value || "";
    sel.innerHTML = "";
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = "不复制（按模板勾选）";
    sel.appendChild(empty);
    Object.keys(state.projects || {})
      .sort()
      .forEach((pid) => {
        const p = state.projects[pid] || {};
        const opt = document.createElement("option");
        opt.value = pid;
        opt.textContent = (p.name || pid) + "（" + pid + "）";
        sel.appendChild(opt);
      });
    if (keep && Array.from(sel.options).some((o) => o.value === keep)) sel.value = keep;
  }

  function syncNewProjectCopyUI() {
    const copyFrom = ($("newProjectCopyFrom") && $("newProjectCopyFrom").value) || "";
    const copying = !!copyFrom;
    const tpl = $("newProjectTemplate");
    const fields = $("newProjectFieldsBlock");
    const hint = $("newProjectCopyHint");
    if (tpl) tpl.disabled = copying;
    if (fields) fields.style.opacity = copying ? "0.5" : "";
    if (fields) {
      fields.querySelectorAll("input, select, button").forEach((el) => {
        el.disabled = copying;
      });
    }
    if (hint) {
      hint.hidden = !copying;
      if (copying) {
        const p = state.projects[copyFrom] || {};
        hint.textContent =
          "字段与阶段将从 " + (p.name || copyFrom) + " 复制，创建后可在配置页修改。";
      }
    }
  }

  async function openNewProjectDialog() {
    $("newProjectId").value = "";
    $("newProjectName").value = "";
    $("newProjectTemplate").value = "steel";
    if ($("newProjectDocumentKind")) $("newProjectDocumentKind").value = "paper";
    fillNewProjectCopyFrom();
    if ($("newProjectCopyFrom")) $("newProjectCopyFrom").value = "";
    await fillNewProjectChecks("steel");
    syncNewProjectCopyUI();
    $("newProjectDialog").showModal();
  }

  async function fillNewProjectChecks(templateId) {
    const box = $("newProjectFieldChecks");
    box.innerHTML = "";
    if (!state.backendOnline) {
      box.innerHTML = '<div class="mode-hint">后端未连接，无法加载字段库。</div>';
      return;
    }
    let lib = { fields: [] };
    try {
      lib = await api(`/api/field_library?template=${encodeURIComponent(templateId)}`);
    } catch (e) {
      box.innerHTML = `<div class="mode-hint">加载失败：${esc(e.message)}</div>`;
      return;
    }
    const byCat = {};
    (lib.fields || []).forEach((f) => {
      const cat = f.category || "property";
      (byCat[cat] = byCat[cat] || []).push(f);
    });
    if (!Object.keys(byCat).length) {
      box.innerHTML = '<div class="mode-hint">（blank 模板无公共库字段，创建后可新增私有字段）</div>';
      return;
    }
    Object.keys(CATEGORY_LABELS).forEach((cat) => {
      const list = byCat[cat];
      if (!list) return;
      const group = document.createElement("div");
      group.className = "lib-cat";
      group.innerHTML = `<h4>${esc(CATEGORY_LABELS[cat])}</h4>`;
      const wrap = document.createElement("div");
      wrap.className = "lib-checks";
      list.forEach((f) => {
        const lab = document.createElement("label");
        lab.className = "check-item";
        lab.innerHTML =
          `<input type="checkbox" data-new-field-id="${esc(f.id)}" checked /> ${esc(f.label || f.id)}`;
        wrap.appendChild(lab);
      });
      group.appendChild(wrap);
      box.appendChild(group);
    });
  }

  async function saveNewProject() {
    const id = $("newProjectId").value.trim();
    const name = $("newProjectName").value.trim() || id;
    const template_id = $("newProjectTemplate").value;
    const document_kind =
      ($("newProjectDocumentKind") && $("newProjectDocumentKind").value) || "paper";
    const copy_from = ($("newProjectCopyFrom") && $("newProjectCopyFrom").value) || "";
    if (!id) {
      $("runStatus").textContent = "请填写项目 ID。";
      return;
    }
    const selected = [];
    $("newProjectFieldChecks")
      .querySelectorAll("input[data-new-field-id]:checked")
      .forEach((cb) => selected.push(cb.getAttribute("data-new-field-id")));
    const body = {
      id,
      name,
      template_id,
      selected_field_ids: selected,
      document_kind,
    };
    if (copy_from) body.copy_from = copy_from;
    try {
      await api("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      logChange(`新建项目 ${id}（${document_kind === "patent" ? "专利" : "文献"}）`);
      $("newProjectDialog").close();
      await reloadProjects();
      renderProjectList();
      await selectProject(id);
    } catch (e) {
      $("runStatus").textContent = "新建项目失败：" + e.message;
    }
  }

  // ---------------------------------------------------------------- papers
  function normalizePaperRec(p) {
    if (typeof p === "string") return { paper_id: p, parsed: true };
    return p || { paper_id: "", parsed: false };
  }

  function paperRecords() {
    return (state.project.papers || []).map(normalizePaperRec);
  }

  function renderPapers() {
    const sel = $("paperSelect");
    sel.innerHTML = "";
    const papers = paperRecords();
    if (!papers.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "（该项目本地无 parsed_results）";
      sel.appendChild(opt);
    }
    papers.forEach((rec) => {
      const opt = document.createElement("option");
      opt.value = rec.paper_id;
      opt.textContent = rec.title || rec.paper_id;
      sel.appendChild(opt);
    });
    const ids = papers.map((r) => r.paper_id);
    if (!state.paperId || !ids.includes(state.paperId)) {
      state.paperId = ids[0] || "";
    }
    if (state.paperId) {
      sel.value = state.paperId;
      if ($("paperIdInput") && !$("paperIdInput").value.trim()) {
        $("paperIdInput").value = state.paperId;
      }
    }
    renderPaperTable(papers);
    updateUploadVisibility();
    updateSelectedRunButton();
    updateRunPreview();
    renderExtractedPaperList();
  }

  function extractedPaperRecords() {
    return paperRecords().filter((r) => r.extracted === true);
  }

  function isCurrentPaperExtracted() {
    const pid = state.paperId;
    if (!pid) return false;
    return extractedPaperRecords().some((r) => r.paper_id === pid);
  }

  function renderExtractedPaperList() {
    const box = $("extractedPaperList");
    if (!box) return;
    box.innerHTML = "";
    const items = extractedPaperRecords();
    if (!items.length) {
      box.innerHTML = '<div class="mode-hint">本项目还没有已抽取文献</div>';
      if (state.view === "export") renderExportPaperChecks();
      return;
    }
    items.forEach((rec) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "extracted-paper-item" + (rec.paper_id === state.paperId ? " active" : "");
      const label = rec.title || rec.paper_id;
      btn.title = rec.paper_id;
      btn.textContent = label;
      btn.addEventListener("click", () => selectExtractedPaper(rec.paper_id));
      box.appendChild(btn);
    });
    if (state.view === "export") renderExportPaperChecks();
  }

  async function selectExtractedPaper(paperId) {
    selectPaperRow(paperId);
    renderExtractedPaperList();
    if (state.view === "review") {
      await loadReview();
    }
  }

  function renderPaperTable(papers) {
    const table = $("paperTable");
    if (!table) return;
    const tbody = table.querySelector("tbody");
    tbody.innerHTML = "";
    const known = new Set(papers.map((r) => r.paper_id));
    Object.keys(state.selectedPaperIds || {}).forEach((id) => {
      if (!known.has(id)) delete state.selectedPaperIds[id];
    });
    papers.forEach((rec) => {
      const tr = document.createElement("tr");
      tr.dataset.paperId = rec.paper_id;
      if (rec.paper_id === state.paperId) tr.classList.add("active");
      const label = rec.title || rec.paper_id;
      const parsedText = rec.parsed ? "已解析" : "未解析";
      const st = rec.extract_status || (rec.extracted ? "success" : "none");
      let extractedText = "未抽取";
      let extractedClass = "";
      if (st === "success") extractedText = "已抽取";
      else if (st === "failed") {
        extractedText = rec.extract_skeleton_done
          ? "失败·骨架已完成"
          : "失败·骨架未完成";
        extractedClass = "extract-failed";
      }
      const errTip = rec.extract_error ? String(rec.extract_error) : "";
      const canCheck = !!rec.parsed;
      const checked = canCheck && !!state.selectedPaperIds[rec.paper_id];
      tr.innerHTML =
        `<td><input type="checkbox" class="paper-row-check" data-paper-id="${esc(rec.paper_id)}" ` +
        `${canCheck ? "" : "disabled "}${checked ? "checked " : ""}/></td>` +
        `<td class="paper-title-cell">${esc(label)}</td>` +
        `<td>${esc(parsedText)}</td>` +
        `<td class="${extractedClass}" title="${esc(errTip)}">${esc(extractedText)}</td>` +
        `<td class="paper-actions">` +
        `<button type="button" class="ghost tiny paper-rerun-btn" data-paper-id="${esc(rec.paper_id)}">重新抽取</button> ` +
        `<button type="button" class="ghost tiny paper-delete-btn" data-paper-id="${esc(rec.paper_id)}">删除</button>` +
        `</td>`;
      tr.addEventListener("click", (ev) => {
        if (ev.target && ev.target.closest && ev.target.closest("input,button")) return;
        selectPaperRow(rec.paper_id);
      });
      const cb = tr.querySelector(".paper-row-check");
      if (cb) {
        cb.addEventListener("change", () => {
          if (cb.checked) state.selectedPaperIds[rec.paper_id] = true;
          else delete state.selectedPaperIds[rec.paper_id];
          syncPaperSelectAll();
          updateSelectedRunButton();
        });
      }
      const rerun = tr.querySelector(".paper-rerun-btn");
      if (rerun) {
        rerun.addEventListener("click", (ev) => {
          ev.stopPropagation();
          rerunPaper(rec.paper_id);
        });
      }
      const delBtn = tr.querySelector(".paper-delete-btn");
      if (delBtn) {
        delBtn.addEventListener("click", (ev) => {
          ev.stopPropagation();
          deletePaper(rec.paper_id);
        });
      }
      tbody.appendChild(tr);
    });
    syncPaperSelectAll();
  }

  function selectPaperRow(paperId) {
    state.paperId = paperId;
    if ($("paperSelect")) $("paperSelect").value = paperId;
    if ($("paperIdInput")) $("paperIdInput").value = paperId;
    document.querySelectorAll("#paperTable tbody tr").forEach((tr) => {
      tr.classList.toggle("active", tr.dataset.paperId === paperId);
    });
    updateRunPreview();
    restoreEntityDoneFromLatestRun();
  }

  function syncPaperSelectAll() {
    const all = $("paperSelectAll");
    if (!all) return;
    const checks = Array.from(document.querySelectorAll("#paperTable .paper-row-check:not(:disabled)"));
    all.checked = checks.length > 0 && checks.every((c) => c.checked);
    all.indeterminate = checks.some((c) => c.checked) && !all.checked;
  }

  function onPaperSelectAllChange() {
    const all = $("paperSelectAll");
    const on = !!(all && all.checked);
    paperRecords().forEach((rec) => {
      if (!rec.parsed) return;
      if (on) state.selectedPaperIds[rec.paper_id] = true;
      else delete state.selectedPaperIds[rec.paper_id];
    });
    renderPaperTable(paperRecords());
    updateSelectedRunButton();
  }

  function renderImportProgress(rows) {
    const box = $("importProgress");
    if (!box) return;
    if (!rows || !rows.length) {
      box.innerHTML = "";
      return;
    }
    box.innerHTML =
      "<ul>" +
      rows
        .map((r) => `<li><code>${esc(r.name)}</code> — ${esc(r.status)}</li>`)
        .join("") +
      "</ul>";
  }

  async function importPdfs() {
    const p = state.project;
    if (!p || !state.backendOnline) return;
    const input = $("pdfFileInput");
    const files = input && input.files ? Array.from(input.files) : [];
    if (!files.length) {
      $("runStatus").textContent = "请先选择要导入的 PDF 文件。";
      return;
    }
    const rows = files.map((f) => ({ name: f.name, status: "等待" }));
    renderImportProgress(rows);
    setBusy(true);
    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        rows[i].status = "解析中";
        renderImportProgress(rows);
        try {
          const fd = new FormData();
          fd.append("project", state.currentId);
          fd.append("pdf", file, file.name);
          const out = await fetch("/api/parse", { method: "POST", body: fd }).then(async (res) => {
            const ct = res.headers.get("content-type") || "";
            const data = ct.includes("application/json")
              ? await res.json().catch(() => ({}))
              : await res.text().then((t) => {
                  try {
                    return JSON.parse(t);
                  } catch (_) {
                    return { raw: t };
                  }
                });
            if (!res.ok) throw new Error((data && data.error) || `HTTP ${res.status}`);
            return data;
          });
          if (out.skipped || out.status === "skipped") rows[i].status = "已跳过";
          else rows[i].status = "已解析";
        } catch (e) {
          rows[i].status = "失败：" + (e.message || e);
        }
        renderImportProgress(rows);
      }
      await reloadProjects();
      state.project = state.projects[state.currentId];
      renderPapers();
      $("runStatus").textContent = `导入完成：共 ${files.length} 个文件`;
    } finally {
      setBusy(false);
      if (input) input.value = "";
    }
  }

  async function runOnePaperExtract(paperId) {
    const body = {
      project: state.currentId,
      paper_id: paperId,
      mode: ($("extractMode") && $("extractMode").value) || "two_stage",
      partition: $("outputPartition").value,
      model_id: state.selectedModel && state.selectedModel.id,
    };
    const out = await api("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    afterRun(out);
    return out;
  }

  async function rerunPaper(paperId) {
    const p = state.project;
    if (!p || !state.backendOnline) {
      setRunStatus("请先启动后端并选择一个项目。", "failed");
      return;
    }
    if (!paperId) return;
    selectPaperRow(paperId);
    setBusy(true);
    const mode = ($("extractMode") && $("extractMode").value) || "two_stage";
    setRunStatus(`正在重新抽取 ${paperId}（${modeLabel(mode)}）...`, "running");
    try {
      const out = await runOnePaperExtract(paperId);
      const r = out.result || {};
      const resumeNote = out.resumed ? "（从已完成骨架续跑）" : "";
      setRunStatus(
        `重新抽取完成${resumeNote}：${out.run_id || ""}（样品 ${(r.samples || []).length} · 状态 ${(r.conditions || []).length}）`,
        "done"
      );
      await reloadProjects();
      state.project = state.projects[state.currentId];
      renderPapers();
      await refreshRuns();
    } catch (e) {
      setRunStatus(`重新抽取失败 ${paperId}：${e.message}`, "failed");
      await reloadProjects();
      state.project = state.projects[state.currentId];
      renderPapers();
    } finally {
      setBusy(false);
    }
  }

  async function runSelectedPapers() {
    const p = state.project;
    if (!p || !state.backendOnline) return;
    const ids = selectedParsedIds();
    if (!ids.length) {
      $("runStatus").textContent = "请先勾选已解析的文献。";
      return;
    }
    const btn = $("btnRunSelected");
    if (btn) btn.disabled = true;
    try {
      const out = await api("/api/run_batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project: state.currentId,
          paper_ids: ids,
          mode: ($("extractMode") && $("extractMode").value) || "two_stage",
          partition: $("outputPartition").value,
          model_id: state.selectedModel && state.selectedModel.id,
          concurrency: 2,
        }),
      });
      setRunStatus(
        `已提交批量抽取 ${out.count} 篇（并发 ${out.concurrency}），进度见上方任务表`,
        "running"
      );
      await refreshJobProgress();
    } catch (e) {
      setRunStatus("提交批量抽取失败：" + e.message, "failed");
      updateSelectedRunButton();
    }
  }

  function currentPaperId() {
    return $("paperIdInput").value.trim() || $("paperSelect").value || state.paperId || "";
  }

  function updateRunPreview() {
    const pid = currentPaperId();
    const mode = $("extractMode").value;
    const partition = $("outputPartition").value;
    const step = state.selectedStepId || "";
    $("paperRunPreview").textContent =
      `POST /api/run | /api/run_step | /api/parse | /api/reextract\n` +
      JSON.stringify(
        {
          project: state.currentId,
          paper_id: pid,
          mode,
          partition,
          step_id: step,
          pdf_path: $("pdfPathInput").value.trim() || undefined,
        },
        null,
        2
      ) +
      `\n\n结果将写入: test_runs/${state.currentId}/${partition}/<run_id>/`;
  }

  function commonRunBody() {
    return {
      project: state.currentId,
      paper_id: currentPaperId(),
      partition: $("outputPartition").value,
      model_id: state.selectedModel && state.selectedModel.id,
    };
  }

  function projectName(pid) {
    const p = (state.projects || {})[pid];
    return (p && p.name) || pid || "";
  }

  function formatJobClock(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso).replace("T", " ").slice(0, 19);
    const pad = (n) => String(n).padStart(2, "0");
    return (
      pad(d.getMonth() + 1) +
      "-" +
      pad(d.getDate()) +
      " " +
      pad(d.getHours()) +
      ":" +
      pad(d.getMinutes()) +
      ":" +
      pad(d.getSeconds())
    );
  }

  function jobElapsed(job) {
    const start = job.started_at ? new Date(job.started_at).getTime() : NaN;
    if (Number.isNaN(start)) return "—";
    const end = job.finished_at ? new Date(job.finished_at).getTime() : Date.now();
    const sec = Math.max(0, Math.round((end - start) / 1000));
    if (sec < 60) return sec + "s";
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return m + "m" + String(s).padStart(2, "0") + "s";
  }

  function jobStatusLabel(st, job) {
    if (st === "cancelled") return "已取消";
    if (st === "failed") {
      if (job && job.skeleton_done === true) return "失败·骨架已完成";
      if (job && job.skeleton_done === false) return "失败·骨架未完成";
      return "失败";
    }
    return { running: "进行中", success: "已完成" }[st] || st || "?";
  }

  function renderJobProgress(jobs) {
    const body = $("jobProgressBody");
    const sum = $("jobProgressSummary");
    if (!body) return;
    const list = jobs || [];
    const running = list.filter((j) => j.status === "running").length;
    const failed = list.filter((j) => j.status === "failed").length;
    const cancelBtn = $("btnCancelJobs");
    if (cancelBtn) cancelBtn.hidden = running === 0;
    if (sum) {
      if (!list.length) sum.textContent = "无进行中任务";
      else sum.textContent = "进行中 " + running + " · 最近 " + list.length + (failed ? "（失败 " + failed + "）" : "");
    }
    if (!list.length) {
      body.innerHTML = '<tr><td colspan="7" class="mode-hint">还没有抽取任务。</td></tr>';
      return;
    }
    body.innerHTML = list
      .map((j) => {
        const st = j.status || "";
        const endCol =
          st === "running"
            ? "已用 " + jobElapsed(j)
            : formatJobClock(j.finished_at) + "（" + jobElapsed(j) + "）";
        const err = j.error ? '<div class="job-st-failed">' + esc(j.error) + "</div>" : "";
        const kind = j.kind === "batch" ? "批量" : j.kind === "run_step" && j.step_id ? "阶段 " + j.step_id : "";
        const cancelCell =
          st === "running"
            ? '<div><button type="button" class="ghost tiny job-cancel-one" data-job-id="' +
              esc(j.job_id) +
              '">取消</button></div>'
            : "";
        return (
          "<tr>" +
          '<td class="job-st-' +
          esc(st) +
          '">' +
          esc(jobStatusLabel(st, j)) +
          cancelCell +
          "</td>" +
          "<td>" +
          esc(projectName(j.project_id)) +
          "</td>" +
          "<td>" +
          esc(j.paper_id || "") +
          (kind ? "<div class='mode-hint'>" + esc(kind) + "</div>" : "") +
          "</td>" +
          "<td>" +
          esc(j.model_id || "") +
          "</td>" +
          "<td>" +
          esc(formatJobClock(j.started_at)) +
          "</td>" +
          "<td>" +
          esc(endCol) +
          err +
          "</td>" +
          "<td>" +
          esc(j.run_id || "—") +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
    body.querySelectorAll(".job-cancel-one").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.preventDefault();
        cancelJobs(btn.getAttribute("data-job-id"));
      });
    });
  }

  async function cancelJobs(jobId) {
    try {
      await api("/api/job_cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId || "" }),
      });
      await refreshJobProgress();
      setRunStatus(jobId ? "已请求取消该任务" : "已请求取消进行中的任务", "done");
    } catch (e) {
      setRunStatus("取消失败：" + e.message, "failed");
    }
  }

  async function refreshJobProgress() {
    try {
      const data = await api("/api/jobs");
      const jobs = data.jobs || [];
      renderJobProgress(jobs);
      const running = jobs.some((j) => j.status === "running");
      if (state._jobsWereRunning && !running) {
        reloadProjects().then(() => {
          state.project = state.projects[state.currentId];
          renderPapers();
          refreshRuns();
        }).catch(() => {});
      }
      state._jobsWereRunning = running;
      return running;
    } catch (e) {
      return false;
    }
  }

  function startJobPolling() {
    const tick = async () => {
      const running = await refreshJobProgress();
      setTimeout(tick, running ? 2000 : 8000);
    };
    tick();
  }

  function setBusy(busy) {
    ["btnRunAll", "btnRunStep", "btnParseOnly", "btnReextract", "btnImportPdfs", "btnRunSelected"].forEach((id) => {
      const el = $(id);
      if (!el) return;
      if (busy) el.disabled = true;
      else updateRunButtons();
    });
  }

  // ---------------------------------------------------------------- four entry points
  async function runAll() {
    const p = state.project;
    if (!p || !state.backendOnline) {
      $("runStatus").textContent = "请先启动后端并选择一个项目。";
      return;
    }
    const pid = currentPaperId();
    if (!pid) {
      $("runStatus").textContent = "请先选择或输入 paper_id。";
      return;
    }
    setBusy(true);
    const stagePlan = visibleRunSteps(p.steps)
      .map((s) => s.name || s.id)
      .join(" → ");
    setRunStatus(
      `正在整篇运行（${$("extractMode").value}）${stagePlan ? "：" + stagePlan : ""}...`,
      "running"
    );
    try {
      const body = {
        ...commonRunBody(),
        mode: $("extractMode").value,
      };
      const pdf = $("pdfPathInput").value.trim();
      if (pdf) body.pdf_path = pdf;
      const out = await api("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      afterRun(out);
      const r = out.result || {};
      const resumeNote = out.resumed ? "（从已完成骨架续跑）" : "";
      setRunStatus(
        `完成${resumeNote}：${out.run_id}（样品 ${(r.samples || []).length} · ` +
          `状态 ${(r.conditions || []).length} · 性能值 ${countProps(r)}）`,
        "done"
      );
      await refreshRuns();
    } catch (e) {
      setRunStatus("运行失败：" + e.message, "failed");
    } finally {
      setBusy(false);
    }
  }

  async function runStep() {
    const p = state.project;
    if (!p || !state.backendOnline) return;
    const pid = currentPaperId();
    if (!pid) {
      $("runStatus").textContent = "请先选择或输入 paper_id。";
      return;
    }
    const stepId = state.selectedStepId;
    if (!stepId) {
      setRunStatus("请先在左侧进度条选择一个阶段。");
      return;
    }
    const step = (p.steps || []).find((s) => s.id === stepId);
    if (step && step.type === "property" && !state.entityDone) {
      setRunStatus("骨架未完成，无法跑性能阶段。");
      return;
    }
    if (step && step.type === "entity" && state.entityDone) {
      if (!confirm("下游性能阶段将作废并重跑")) return;
    }
    const stepName = step ? step.name || step.id : stepId;
    setBusy(true);
    setRunStatus(`正在跑阶段「${stepName}」...`, "running");
    try {
      const out = await api("/api/run_step", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...commonRunBody(),
          step_id: stepId,
          run_id: state.lastRunId || undefined,
        }),
      });
      afterRun(out);
      const inv = (out.invalidated || []).join(", ") || "无";
      setRunStatus(
        `阶段「${stepName}」完成（run ${out.run_id}，作废下游：${inv}）`,
        "done"
      );
      await refreshRuns();
    } catch (e) {
      setRunStatus("分阶段运行失败：" + e.message, "failed");
    } finally {
      setBusy(false);
    }
  }

  async function parseOnly() {
    const p = state.project;
    if (!p || !state.backendOnline) return;
    const pid = currentPaperId();
    const pdf = $("pdfPathInput").value.trim();
    if (!pid && !pdf) {
      $("runStatus").textContent = "只解析需要 paper_id（已有 source.pdf）或 pdf_path。";
      return;
    }
    setBusy(true);
    $("runStatus").textContent = "正在解析 PDF...";
    try {
      const body = { project: state.currentId, paper_id: pid || undefined };
      if (pdf) body.pdf_path = pdf;
      const out = await api("/api/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      $("runStatus").textContent =
        `解析完成：${out.paper_id || pid}` +
        (out.skipped ? "（已跳过，paper.md 已存在）" : "");
      await reloadProjects();
      state.project = state.projects[state.currentId];
      renderPapers();
    } catch (e) {
      $("runStatus").textContent = "解析失败：" + e.message;
    } finally {
      setBusy(false);
    }
  }

  async function reextract() {
    const p = state.project;
    if (!p || !state.backendOnline) return;
    const fieldId = $("reextractField").value;
    if (!fieldId) {
      $("runStatus").textContent = "请选择要重抽的字段。";
      return;
    }
    const scope = $("reextractScope").value;
    const body = {
      ...commonRunBody(),
      field_id: fieldId,
    };
    if (scope === "project_extracted") {
      body.scope = "project_extracted";
      body.paper_id = undefined;
    } else {
      if (!currentPaperId()) {
        $("runStatus").textContent = "请先选择 paper_id。";
        return;
      }
      body.paper_id = currentPaperId();
    }
    setBusy(true);
    $("runStatus").textContent = `正在重抽 ${fieldId}...`;
    try {
      const out = await api("/api/reextract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (out.result) afterRun(out);
      else if (out.report) {
        const okCount = out.report.filter((r) => r.ok).length;
        const failCount = out.report.filter((r) => !r.ok).length;
        $("runStatus").textContent =
          `批量重抽完成：成功 ${okCount} · 失败 ${failCount}`;
      } else {
        $("runStatus").textContent = `重抽完成：${fieldId}`;
        if (out.run_id) state.lastRunId = out.run_id;
      }
      await refreshRuns();
      await loadReview();
    } catch (e) {
      $("runStatus").textContent = "重抽失败：" + e.message;
    } finally {
      setBusy(false);
    }
  }

  function afterRun(out) {
    state.lastRunId = out.run_id || (out.run_info && out.run_info.run_id) || state.lastRunId;
    applyEntityDoneFromRunInfo(out.run_info || {}, out.result || {});
    if (out.entity && (out.entity.samples || []).length) {
      state.entityDone = true;
    }
    renderStepList();
    renderRun(out);
    updateGoReviewButton(true);
  }

  function renderRun(out) {
    const r = out.result || {};
    const steps = out.steps || [];
    $("metadataOutput").textContent = JSON.stringify(
      metadataValuesOnly(r.paper_metadata || {}),
      null,
      2
    );
    $("entityOutput").textContent = JSON.stringify(
      {
        samples: (out.entity && out.entity.samples) || r.samples || [],
        conditions: (out.entity && out.entity.conditions) || r.conditions || [],
      },
      null,
      2
    );
    const propSteps = steps.filter((s) => s.type === "property");
    $("propertyOutput").textContent = propSteps.length
      ? propSteps
          .map(
            (s) =>
              `# ${s.name}  →  ${s.group}\n` +
              JSON.stringify(s.output, null, 2) +
              (s.warnings && s.warnings.length ? `\n（本步规则剔除 ${s.warnings.length} 项）` : "")
          )
          .join("\n\n")
      : "（无性能步骤）";
    const figStep = steps.find((s) => s.type === "figure");
    $("figureOutput").textContent = JSON.stringify(
      figStep ? figStep.output : out.figures || r.figures || [],
      null,
      2
    );
    renderWarnings("reviewList", out.warnings);
    fillResultPanes({ run_info: out.run_info, result: r, warnings: out.warnings });
    $("sampleFieldCount").textContent = (r.samples || []).length;
    $("conditionFieldCount").textContent = (r.conditions || []).length;
    $("figureFieldCount").textContent = (r.figures || []).length;
    $("propertyFieldCount").textContent = countProps(r);
    if (out.prompts) {
      state.prompts = out.prompts;
      state.promptLabels = {};
      (state.project.steps || []).forEach((s) => (state.promptLabels[s.id] = s.name || s.id));
      steps.forEach((s) => (state.promptLabels[s.id] = s.name || s.id));
      if (!Object.keys(state.prompts).includes(state.promptTab)) {
        state.promptTab = Object.keys(state.prompts)[0] || "";
      }
      renderPromptTab();
    }
  }

  function countProps(result) {
    let n = 0;
    (result.conditions || []).forEach((c) => {
      Object.values(c).forEach((v) => {
        if (v && typeof v === "object" && !Array.isArray(v)) {
          const vals = Object.values(v);
          if (vals.length && vals.every((x) => x && typeof x === "object" && "value" in x)) {
            n += vals.length;
          }
        }
      });
    });
    return n;
  }

  function renderWarnings(boxId, warnings) {
    const box = $(boxId);
    if (!box) return;
    // 复核主路径：未通过原因挂在结果树节点上，不另开告警条列表。
    // 本函数仅供高级开发面板 #reviewList 使用。
    if (!warnings || !warnings.length) {
      box.innerHTML = '<div class="review-empty">规则校验：无剔除项。</div>';
      return;
    }
    box.innerHTML = warnings
      .map((w) => {
        const tag = w.type === "figure_dropped" ? "图片策略" : "性能来源剔除";
        return `<div class="review-item warn"><span class="review-tag">${esc(tag)}</span> ${esc(w.detail || w.message || JSON.stringify(w))}</div>`;
      })
      .join("");
  }

  function clearRunOutputs() {
    ["entityOutput", "propertyOutput", "figureOutput"].forEach((id) => ($(id).textContent = ""));
    $("reviewList").innerHTML = '<div class="review-empty">尚未运行。</div>';
    $("resultFieldList").innerHTML = "";
  }

  // ---------------------------------------------------------------- provenance highlight
  function normalizeWs(s) {
    return String(s || "").replace(/\s+/g, " ").trim();
  }

  function escapeRe(s) {
    return String(s || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  /** 定位用：value 优先，再 excerpt（成分等常被改写成斜杠分隔，摘录又对不上表格） */
  function factLocateNeedles(raw) {
    const out = [];
    if (isWrappedFact(raw)) {
      const v = displayValue(raw);
      if (v != null && String(v).trim() !== "") out.push(String(v).trim());
      const ex = raw.excerpt || "";
      if (ex && String(ex).trim()) out.push(String(ex).trim());
    } else if (raw != null && String(raw).trim() !== "") {
      out.push(String(raw).trim());
    }
    return out;
  }

  /** 多数字段（成分）用数字序列对 markdown 表；否则按词/标点切分 */
  function locateTokenSets(needle) {
    const s = String(needle || "").trim();
    if (!s) return [];
    const sets = [];
    const nums = s.match(/\d+(?:\.\d+)?/g) || [];
    if (nums.length >= 3) sets.push(nums);
    const words = normalizeWs(s)
      .split(/[\s/,;|·•]+/)
      .filter(Boolean);
    if (words.length) sets.push(words);
    return sets;
  }

  /** 在原文中找 needle；命中返回 {start,end}，否则 null */
  function findNeedleInText(paperText, needle) {
    const text = paperText || "";
    if (!needle || !text) return null;
    for (const tokens of locateTokenSets(needle)) {
      if (!tokens.length) continue;
      const re = new RegExp(
        tokens.map(escapeRe).join("(?:[\\s|/,;·•:()\\[\\]]|[^0-9\\s]){0,32}?")
      );
      const m = text.match(re);
      if (m && m.index != null) {
        return { start: m.index, end: m.index + m[0].length, match: m[0] };
      }
    }
    return null;
  }

  function needleMatchesInText(paperText, needle) {
    return !!findNeedleInText(paperText, needle);
  }

  /** 兼容旧名 */
  function excerptMatchesInText(paperText, excerpt) {
    return needleMatchesInText(paperText, excerpt);
  }

  function factCanLocate(paperText, raw) {
    return factLocateNeedles(raw).some((n) => needleMatchesInText(paperText, n));
  }

  function setSourceMode(mode) {
    state.sourceMode = mode;
    const pdf = $("pdfViewer");
    const html = $("paperHtmlViewer");
    const text = $("paperTextViewer");
    if (pdf) pdf.hidden = mode !== "pdf";
    if (html) html.hidden = mode !== "html";
    if (text) text.hidden = mode !== "text";
    document.querySelectorAll("#sourceModeTabs [data-source-mode]").forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-source-mode") === mode);
    });
  }

  function applyTextHighlight(text, start, end) {
    const viewer = $("paperTextViewer");
    setSourceMode("text");
    state.paperText = text;
    viewer.innerHTML =
      esc(text.slice(0, start)) +
      "<mark>" +
      esc(text.slice(start, end)) +
      "</mark>" +
      esc(text.slice(end));
    const mark = viewer.querySelector("mark");
    if (mark) mark.scrollIntoView({ block: "center", behavior: "smooth" });
    return true;
  }

  /** 命中则切到文本视图并包 &lt;mark&gt; */
  function highlightExcerpt(paperText, excerpt) {
    const text = paperText || state.paperText || "";
    state.paperText = text;
    const hit = findNeedleInText(text, excerpt);
    if (!hit) {
      const viewer = $("paperTextViewer");
      setSourceMode("text");
      if (viewer) viewer.textContent = text;
      return false;
    }
    return applyTextHighlight(text, hit.start, hit.end);
  }

  /** value 优先，再 excerpt */
  function highlightFact(paperText, raw) {
    const text = paperText || state.paperText || "";
    state.paperText = text;
    for (const needle of factLocateNeedles(raw)) {
      const hit = findNeedleInText(text, needle);
      if (hit) return applyTextHighlight(text, hit.start, hit.end);
    }
    const viewer = $("paperTextViewer");
    setSourceMode("text");
    if (viewer) viewer.textContent = text;
    return false;
  }

  function isWrappedFact(v) {
    return v && typeof v === "object" && !Array.isArray(v) && ("value" in v || "excerpt" in v);
  }

  function isIdentityKey(key) {
    return IDENTITY_IDS.has(key) || key === "sample_id" || key === "condition_id";
  }

  function isPropertyGroup(v) {
    if (!v || typeof v !== "object" || Array.isArray(v) || isWrappedFact(v)) return false;
    const vals = Object.values(v);
    return vals.length > 0 && vals.every((x) => isWrappedFact(x));
  }

  function isRejectedStatus(raw) {
    return !!(raw && typeof raw === "object" && raw.status === "rejected_by_rule");
  }

  function extractImageNamesFromMd(md) {
    const names = [];
    const re = /(?:images_from_md\/)([^)\s"']+)/g;
    let m;
    while ((m = re.exec(md || ""))) {
      const name = PathBasename(m[1]);
      if (name && !names.includes(name)) names.push(name);
    }
    return names;
  }

  function PathBasename(p) {
    const s = String(p || "").replace(/\\/g, "/");
    const i = s.lastIndexOf("/");
    return i >= 0 ? s.slice(i + 1) : s;
  }

  function rewriteMdImages(md, project, paperId) {
    return String(md || "").replace(
      /(!\[[^\]]*\]\()(?:\.\/)?images_from_md\/([^)\s]+)(\))/g,
      (_, a, name, c) =>
        a +
        paperImageUrl(project, paperId, PathBasename(name)) +
        c
    );
  }

  function paperImageUrl(project, paperId, name) {
    return (
      `/api/paper_image?project=${encodeURIComponent(project || "")}` +
      `&paper_id=${encodeURIComponent(paperId || "")}` +
      `&name=${encodeURIComponent(name || "")}`
    );
  }

  function figureImageName(fig) {
    if (!fig) return null;
    const direct = fig.image_file || fig.file_name || fig.filename || fig.path;
    if (direct) {
      const base = PathBasename(direct);
      if (base) return base;
    }
    const names = state.paperImageNames || [];
    const idx = fig.placeholder_index != null ? Number(fig.placeholder_index) : NaN;
    if (!Number.isNaN(idx) && names.length) {
      // UniParser: figure_001.png / chart_003.png
      const padded = String(idx).padStart(3, "0");
      const reReal = new RegExp(
        "^(?:figure|chart|fig)[_-]?(?:0*" + idx + "|" + padded + ")\\.",
        "i"
      );
      const hitReal = names.find((n) => reReal.test(n));
      if (hitReal) return hitReal;
      // fallback: n-th image in paper.md order
      if (idx >= 1 && names[idx - 1]) return names[idx - 1];
    }
    // Figure 1 / Fig. 2a → try figure_001
    const fid = String(fig.figure_id || "");
    const m = fid.match(/(\d+)/);
    if (m && names.length) {
      const n = m[1];
      const padded = n.padStart(3, "0");
      const hit = names.find((x) =>
        new RegExp("^(?:figure|fig)[_-]?(?:0*" + n + "|" + padded + ")\\.", "i").test(x)
      );
      if (hit) return hit;
    }
    return null;
  }

  function renderMdToHtml(md, project, paperId) {
    const rewritten = rewriteMdImages(md, project, paperId);
    if (typeof marked !== "undefined" && marked && typeof marked.parse === "function") {
      return marked.parse(rewritten);
    }
    // CDN 不可用时的降级：转义 + 换行 + 图片链接
    return (
      "<pre class=\"md-fallback\">" +
      esc(rewritten).replace(
        /!\[([^\]]*)\]\(([^)]+)\)/g,
        (_, alt, src) => `</pre><p><img alt="${esc(alt)}" src="${esc(src)}" /></p><pre class="md-fallback">`
      ) +
      "</pre>"
    );
  }

  async function loadSourcePane(project, paperId) {
    const pdf = $("pdfViewer");
    const html = $("paperHtmlViewer");
    const text = $("paperTextViewer");
    const btnPdf = $("btnSourcePdf");
    const btnHtml = $("btnSourceHtml");
    state.hasPdf = false;
    state.hasMd = false;
    state.paperImageNames = [];
    try {
      const meta = await api(
        `/api/paper_meta?project=${encodeURIComponent(project)}&paper_id=${encodeURIComponent(paperId)}`
      );
      state.hasPdf = !!meta.has_pdf;
      state.hasMd = !!meta.has_md;
      if (Array.isArray(meta.images) && meta.images.length) {
        state.paperImageNames = meta.images.slice();
      }
      if (btnPdf) btnPdf.hidden = !state.hasPdf;
      if (btnHtml) btnHtml.hidden = !state.hasMd;
    } catch (e) {
      if (btnPdf) btnPdf.hidden = true;
      if (btnHtml) btnHtml.hidden = true;
    }
    try {
      const txt = await api(
        `/api/paper_text?project=${encodeURIComponent(project)}&paper_id=${encodeURIComponent(paperId)}`
      );
      state.paperText = txt.text || "";
      state.paperImageNames = extractImageNamesFromMd(state.paperText);
      text.textContent = state.paperText;
      if (state.hasMd || state.paperText) {
        html.innerHTML = renderMdToHtml(state.paperText, project, paperId);
        if (btnHtml) btnHtml.hidden = false;
        state.hasMd = true;
      }
      $("sourceMeta").textContent =
        `${paperId} · ${state.paperText.length} 字符` +
        (state.hasPdf ? " · PDF" : "") +
        (state.paperImageNames.length ? ` · ${state.paperImageNames.length} 图` : "");
    } catch (e) {
      state.paperText = "";
      text.textContent = "载入原文失败：" + e.message;
      html.innerHTML = "";
      $("sourceMeta").textContent = "载入失败";
    }
    if (state.hasPdf) {
      pdf.src =
        `/api/paper_pdf?project=${encodeURIComponent(project)}&paper_id=${encodeURIComponent(paperId)}`;
      setSourceMode("pdf");
    } else if (state.hasMd) {
      pdf.removeAttribute("src");
      setSourceMode("html");
    } else {
      pdf.removeAttribute("src");
      setSourceMode("text");
    }
  }

  function attachFieldClick(el, raw) {
    const excerpt = isWrappedFact(raw) ? raw.excerpt || "" : "";
    const location = isWrappedFact(raw) ? raw.location || "" : "";
    el.addEventListener("click", () => {
      const miss = el.querySelector(".fr-miss");
      const statusEl = el.querySelector(".fr-status");
      const needles = factLocateNeedles(raw);
      if (!needles.length) {
        if (miss) {
          miss.hidden = false;
          miss.textContent = location ? `无值可定位 · ${location}` : "无值可定位";
        }
        return;
      }
      const ok = highlightFact(state.paperText, raw);
      if (statusEl) {
        statusEl.textContent = ok ? "已定位" : excerpt ? "仅摘录" : "未定位";
      }
      if (miss) {
        if (!ok) {
          miss.hidden = false;
          const shown = excerpt || needles[0];
          miss.textContent =
            (excerpt ? `仅摘录：${shown}` : `未定位：${shown}`) +
            (location ? ` · ${location}` : "");
        } else {
          miss.hidden = true;
          miss.textContent = "";
        }
      }
    });
  }

  function buildFieldBlock(key, raw, opts) {
    opts = opts || {};
    const wrapped = isWrappedFact(raw);
    const rejected = isRejectedStatus(raw);
    if (state.reviewFilter === "rejected" && !rejected && !opts.forceShow) {
      return null;
    }
    const value = formatDisplay(raw);
    const location = wrapped ? raw.location || "" : "";
    const excerpt = wrapped ? raw.excerpt || "" : "";
    let excerptStatus = "无摘录";
    if (factCanLocate(state.paperText, raw)) {
      excerptStatus = "已定位";
    } else if (excerpt) {
      excerptStatus = "仅摘录";
    } else if (value) {
      excerptStatus = "未定位";
    }
    const label = fieldLabel(key);
    const el = document.createElement("button");
    el.type = "button";
    el.className =
      "field-result-item " + (rejected ? "field-rejected" : "field-accepted");
    if (opts.path) el.dataset.resultPath = opts.path;
    el.innerHTML =
      `<span class="fr-label">${esc(label)}</span>` +
      `<span class="fr-value">${esc(value)}${wrapped && raw.unit ? " " + esc(raw.unit) : ""}</span>` +
      `<span class="fr-loc">${esc(location || "—")}</span>` +
      `<span class="fr-status">${esc(excerptStatus)}</span>` +
      (rejected && raw.reject_reason
        ? `<span class="fr-reason">${esc(raw.reject_reason)}</span>`
        : "") +
      `<span class="fr-miss" hidden></span>`;
    attachFieldClick(el, raw);
    return el;
  }

  function buildThumb(fig, project, paperId) {
    const name = figureImageName(fig);
    const rejected = isRejectedStatus(fig);
    const wrap = document.createElement("button");
    wrap.type = "button";
    wrap.className =
      "fig-thumb " + (rejected ? "field-rejected" : "field-accepted");
    const typeLabel = formatDisplay(fig.figure_type);
    wrap.title =
      (fig.figure_id || "图") +
      (typeLabel ? " · " + typeLabel : "") +
      (rejected && fig.reject_reason ? " · " + fig.reject_reason : "");
    if (name) {
      const url = paperImageUrl(project, paperId, name);
      wrap.innerHTML =
        `<img src="${esc(url)}" alt="${esc(fig.figure_id || name)}" loading="lazy" />` +
        `<span class="fig-thumb-cap">${esc(fig.figure_id || name)} · ${esc(name)}</span>`;
      const imgEl = wrap.querySelector("img");
      if (imgEl) {
        imgEl.addEventListener("error", () => {
          imgEl.replaceWith(
            Object.assign(document.createElement("span"), {
              className: "fig-thumb-missing",
              textContent: "加载失败 " + name,
            })
          );
        });
      }
      wrap.addEventListener("click", (e) => {
        e.stopPropagation();
        const dlg = $("thumbDialog");
        const img = $("thumbDialogImg");
        if (img) img.src = url;
        if (dlg && dlg.showModal) dlg.showModal();
      });
    } else {
      wrap.innerHTML =
        `<span class="fig-thumb-missing">无图</span>` +
        `<span class="fig-thumb-cap">${esc(fig.figure_id || "?")}</span>`;
    }
    if (rejected && fig.reject_reason) {
      const reason = document.createElement("span");
      reason.className = "fr-reason";
      reason.textContent = fig.reject_reason;
      wrap.appendChild(reason);
    }
    return wrap;
  }

  function figuresForNode(figures, sampleId, conditionId) {
    return (figures || []).filter((f) => {
      const sid = f.sample_id || null;
      const cid = f.condition_id || null;
      if (conditionId) {
        return cid === conditionId;
      }
      return sid === sampleId && !cid;
    });
  }

  function renderResultTree(result) {
    const box = $("resultFieldList");
    const project = state.currentId;
    const paperId = currentPaperId();
    const r = result || {};
    box.innerHTML = "";
    box.className = "result-tree";

    let shown = 0;

    // 文章信息
    const metaSec = document.createElement("section");
    metaSec.className = "tree-section";
    metaSec.innerHTML = "<h5>文章信息</h5>";
    const metaBody = document.createElement("div");
    metaBody.className = "tree-fields";
    const meta = r.paper_metadata || {};
    Object.keys(meta).forEach((k) => {
      if (isIdentityKey(k)) return;
      const block = buildFieldBlock(k, meta[k], { path: "paper_metadata." + k });
      if (block) {
        metaBody.appendChild(block);
        shown++;
      }
    });
    if (metaBody.children.length) {
      metaSec.appendChild(metaBody);
      box.appendChild(metaSec);
    }

    const figures = r.figures || [];
    const conditions = r.conditions || [];
    const samples = r.samples || [];

    function conditionSampleId(c) {
      const raw = c && c.sample_id;
      if (raw && typeof raw === "object") return raw.value || "";
      return raw || "";
    }

    const knownSids = new Set();
    samples.forEach((s, si) => knownSids.add(s.sample_id || `S${si + 1}`));

    function appendConditionBlock(parent, c, ci) {
      const cid = c.condition_id || `C${ci + 1}`;
      const condBlock = document.createElement("div");
      condBlock.className = "tree-condition";
      condBlock.innerHTML = `<h6>状态 ${esc(cid)}</h6>`;

      const condFields = document.createElement("div");
      condFields.className = "tree-fields";
      Object.keys(c || {}).forEach((k) => {
        if (isIdentityKey(k) || k === "sample_id") return;
        const v = c[k];
        if (isPropertyGroup(v)) {
          Object.keys(v).forEach((pk) => {
            const block = buildFieldBlock(pk, v[pk], {
              path: "conditions[" + cid + "]." + k + "." + pk,
            });
            if (block) {
              condFields.appendChild(block);
              shown++;
            }
          });
        } else {
          const block = buildFieldBlock(k, v, { path: "conditions[" + cid + "]." + k });
          if (block) {
            condFields.appendChild(block);
            shown++;
          }
        }
      });
      if (condFields.children.length) condBlock.appendChild(condFields);

      const condFigs = figures.filter((f) => f.condition_id === cid);
      if (condFigs.length) {
        const row = document.createElement("div");
        row.className = "fig-thumb-row";
        condFigs.forEach((f) => {
          if (state.reviewFilter === "rejected" && !isRejectedStatus(f)) return;
          row.appendChild(buildThumb(f, project, paperId));
          shown++;
        });
        if (row.children.length) condBlock.appendChild(row);
      }

      if (condBlock.querySelector(".field-result-item, .fig-thumb")) {
        parent.appendChild(condBlock);
      }
    }

    samples.forEach((s, si) => {
      const sid = s.sample_id || `S${si + 1}`;
      const sampleSec = document.createElement("section");
      sampleSec.className = "tree-section tree-sample";
      sampleSec.innerHTML = `<h5>样品 ${esc(sid)}</h5>`;

      const sampleFields = document.createElement("div");
      sampleFields.className = "tree-fields";
      Object.keys(s || {}).forEach((k) => {
        if (isIdentityKey(k)) return;
        const block = buildFieldBlock(k, s[k], { path: "samples[" + sid + "]." + k });
        if (block) {
          sampleFields.appendChild(block);
          shown++;
        }
      });
      if (sampleFields.children.length) sampleSec.appendChild(sampleFields);

      const sampleFigs = figuresForNode(figures, sid, null);
      if (sampleFigs.length) {
        const row = document.createElement("div");
        row.className = "fig-thumb-row";
        sampleFigs.forEach((f) => {
          if (state.reviewFilter === "rejected" && !isRejectedStatus(f)) return;
          row.appendChild(buildThumb(f, project, paperId));
          shown++;
        });
        if (row.children.length) sampleSec.appendChild(row);
      }

      conditions
        .filter((c) => {
          const csid = conditionSampleId(c);
          return csid === sid || (!csid && samples.length === 1);
        })
        .forEach((c, ci) => appendConditionBlock(sampleSec, c, ci));

      if (sampleSec.querySelector(".field-result-item, .fig-thumb, .tree-condition")) {
        box.appendChild(sampleSec);
      }
    });

    const unlinked = conditions.filter((c) => {
      const csid = conditionSampleId(c);
      if (!csid) return samples.length !== 1;
      return !knownSids.has(csid);
    });
    if (unlinked.length) {
      const orphanSec = document.createElement("section");
      orphanSec.className = "tree-section tree-unlinked";
      orphanSec.innerHTML = "<h5>未挂样品的状态</h5>";
      unlinked.forEach((c, ci) => appendConditionBlock(orphanSec, c, ci));
      if (orphanSec.querySelector(".tree-condition, .field-result-item")) {
        box.appendChild(orphanSec);
      }
    }

    // 图片总览
    const figSec = document.createElement("section");
    figSec.className = "tree-section tree-figures";
    figSec.innerHTML = "<h5>图片总览</h5>";
    const figRow = document.createElement("div");
    figRow.className = "fig-thumb-row fig-overview";
    figures.forEach((f) => {
      if (state.reviewFilter === "rejected" && !isRejectedStatus(f)) return;
      const card = document.createElement("div");
      const figId =
        f.figure_id && typeof f.figure_id === "object" ? f.figure_id.value : f.figure_id;
      const figPath = "figures[" + (figId || "") + "]";
      card.className =
        "fig-card " + (isRejectedStatus(f) ? "field-rejected" : "field-accepted");
      card.dataset.resultPath = figPath;
      const thumb = buildThumb(f, project, paperId);
      thumb.dataset.resultPath = figPath;
      card.appendChild(thumb);
      const metaLine = document.createElement("div");
      metaLine.className = "fig-card-meta";
      const typeLabel = formatDisplay(f.figure_type);
      const sidLabel = formatDisplay(f.sample_id);
      const cidLabel = formatDisplay(f.condition_id);
      metaLine.textContent =
        typeLabel +
        (sidLabel ? ` · ${sidLabel}` : "") +
        (cidLabel ? ` / ${cidLabel}` : "");
      card.appendChild(metaLine);
      // figure field facts (non-id)
      const extra = document.createElement("div");
      extra.className = "tree-fields";
      Object.keys(f || {}).forEach((k) => {
        if (
          isIdentityKey(k) ||
          k === "sample_id" ||
          k === "condition_id" ||
          k === "figure_type" ||
          k === "status" ||
          k === "reject_reason" ||
          k === "is_microstructure_image" ||
          k === "is_post_test_image" ||
          k === "scale_bar_info" ||
          k === "image_file" ||
          k === "file_name"
        )
          return;
        if (!isWrappedFact(f[k])) return;
        const block = buildFieldBlock(k, f[k], { path: figPath + "." + k });
        if (block) extra.appendChild(block);
      });
      if (extra.children.length) card.appendChild(extra);
      figRow.appendChild(card);
      shown++;
    });
    if (figRow.children.length) {
      figSec.appendChild(figRow);
      box.appendChild(figSec);
    }

    if (!shown) {
      box.innerHTML =
        state.reviewFilter === "rejected"
          ? '<div class="review-empty">当前无规则未通过项。</div>'
          : '<div class="review-empty">暂无带出处的字段结果。</div>';
    }
  }

  // ---------------------------------------------------------------- review panes
  async function loadReview() {
    const pid = currentPaperId();
    if (!pid) {
      $("runStatus").textContent = "请先选择 paper_id。";
      return;
    }
    await refreshRuns();
    await loadSourcePane(state.currentId, pid);
    try {
      const runId = $("runSelect").value || "";
      const q =
        `/api/result?project=${encodeURIComponent(state.currentId)}&paper_id=${encodeURIComponent(pid)}` +
        (runId ? `&run_id=${encodeURIComponent(runId)}` : "");
      const res = await api(q);
      applyEntityDoneFromRunInfo(res.run_info || {}, res.result || {});
      renderStepList();
      fillResultPanes(res);
      hideRunArtifacts();
    } catch (e) {
      $("resultMeta").textContent = "暂无结果";
      $("resultSummary").innerHTML = "";
      $("resultFieldList").innerHTML = "";
      state.currentResult = null;
      const selRun = ($("runSelect") && $("runSelect").value) || "";
      state.currentRunId = selRun || null;
      if (selRun) {
        await showRunArtifacts(selRun);
      } else {
        hideRunArtifacts();
      }
    }
    await refreshAnalyzeHistory();
    syncAnalyzeButton();
  }

  async function deleteSelectedRun() {
    const pid = currentPaperId();
    const status = $("deleteRunStatus");
    if (!pid) {
      if (status) status.textContent = "请先选择文献";
      return;
    }
    let runId = ($("runSelect") && $("runSelect").value) || "";
    if (!runId) runId = state.currentRunId || "";
    if (!runId) {
      if (status) status.textContent = "请先在「结果来源」选择一条 run，或先载入结果";
      return;
    }
    if (!window.confirm("确认删除这条抽取结果？\n\n" + runId + "\n\n删除后不可恢复（原文解析不会动）。")) {
      return;
    }
    if (status) status.textContent = "删除中…";
    try {
      await api("/api/run_delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project: state.currentId,
          paper_id: pid,
          run_id: runId,
        }),
      });
      if (status) status.textContent = "已删除 " + runId;
      state.currentResult = null;
      state.currentRunId = null;
      if ($("runSelect")) $("runSelect").value = "";
      if ($("runArtifactsPanel")) {
        $("runArtifactsPanel").hidden = true;
        $("runArtifactsPanel").innerHTML = "";
      }
      if ($("runComparePanel")) {
        $("runComparePanel").hidden = true;
        $("runComparePanel").innerHTML = "";
      }
      if ($("analyzePanel")) {
        $("analyzePanel").hidden = true;
        $("analyzePanel").innerHTML = "";
      }
      await refreshRuns();
      await loadReview();
      try {
        await reloadProjects();
        renderExtractedPaperList();
      } catch (e) {
        /* ignore */
      }
    } catch (e) {
      if (status) status.textContent = "删除失败：" + (e.message || e);
    }
  }

  function fillResultPanes(res) {
    const r = res.result || {};
    state.currentResult = r;
    const info = res.run_info || {};
    state.currentRunId = info.run_id || null;
    $("resultMeta").textContent = info.run_id
      ? `${info.run_id} · ${info.mode || ""} · ${info.model_id || info.backend || ""}`
      : "";
    const trim = (r._pipeline && r._pipeline.input_trim) || {};
    const rejectedCount = countRejected(r);
    $("resultSummary").innerHTML =
      `<span>样品 <b>${(r.samples || []).length}</b></span>` +
      `<span>状态 <b>${(r.conditions || []).length}</b></span>` +
      `<span>图片 <b>${(r.figures || []).length}</b></span>` +
      `<span>性能值 <b>${countProps(r)}</b></span>` +
      `<span>未通过 <b>${rejectedCount}</b></span>` +
      (trim.kept_ratio != null
        ? `<span>输入保留 <b>${(trim.kept_ratio * 100).toFixed(1)}%</b></span>`
        : "");
    renderResultTree(r);
  }

  function countRejected(result) {
    let n = 0;
    const meta = result.paper_metadata || {};
    Object.values(meta).forEach((v) => {
      if (isRejectedStatus(v)) n++;
    });
    (result.samples || []).forEach((s) => {
      Object.values(s || {}).forEach((v) => {
        if (isRejectedStatus(v)) n++;
      });
    });
    (result.conditions || []).forEach((c) => {
      Object.keys(c || {}).forEach((k) => {
        if (isIdentityKey(k) || k === "sample_id") return;
        const v = c[k];
        if (isPropertyGroup(v)) {
          Object.values(v).forEach((pv) => {
            if (isRejectedStatus(pv)) n++;
          });
        } else if (isRejectedStatus(v)) n++;
      });
    });
    (result.figures || []).forEach((f) => {
      if (isRejectedStatus(f)) n++;
    });
    return n;
  }

  function modeLabel(mode) {
    return (
      {
        two_stage: "完整流程",
        entity_only: "只抽骨架",
        single_pass: "对照",
      }[mode] || mode || "?"
    );
  }

  function runStamp(run) {
    const m = String((run && run.run_id) || "").match(/^(\d{8}_\d{6})/);
    return m ? m[1] : (run && run.run_id) || "";
  }

  function runModelLabel(run) {
    if (run && run.model_id) return String(run.model_id);
    const id = String((run && run.run_id) || "");
    // 新格式：{stamp}_{mode}_{model}[_{n}]；stamp 为 YYYYMMDD_HHMMSS
    const m = id.match(/^\d{8}_\d{6}_[^_]+_(.+)$/);
    if (m) return m[1].replace(/_\d+$/, "") || m[1];
    return "";
  }

  function runOptionLabel(run) {
    const mode = modeLabel(run.mode);
    const warn = run.warnings != null ? run.warnings : "?";
    const paper = (run && run.paper_id) || currentPaperId() || "";
    const stamp = runStamp(run);
    const model = runModelLabel(run);
    const modelPart = model ? `_${model}` : "";
    const failed = (run && run.status) === "failed";
    const tail = failed
      ? (run.skeleton_done ? "失败·骨架已完成" : "失败·骨架未完成")
      : `警告${warn}`;
    // 主文案：文献ID_抽取方式_模型；时间戳区分同模式多次跑
    if (paper) {
      return `${paper}_${mode}${modelPart}（${stamp}，${tail}）`;
    }
    return `${run.run_id}（${mode}${model ? " · " + model : ""}，${tail}）`;
  }

  function selectedRunId() {
    return ($("runSelect") && $("runSelect").value) || state.currentRunId || "";
  }

  function hideRunArtifacts() {
    const box = $("runArtifactsPanel");
    if (!box) return;
    box.hidden = true;
    box.innerHTML = "";
  }

  function renderRunArtifacts(data) {
    const box = $("runArtifactsPanel");
    if (!box) return;
    const info = data.run_info || {};
    const err = info.error || "";
    const files = data.files || [];
    const steps = (info.completed_steps || []).join("、") || "无";
    const skel = (info.completed_steps || []).some(
      (s) => s === "entity" || String(s).endsWith("entity")
    );
    const skelText =
      info.status === "failed"
        ? skel
          ? "骨架已完成，后面失败"
          : "骨架抽取失败"
        : skel
          ? "骨架已完成"
          : "骨架未写盘";
    let html =
      '<div class="art-head"><span>run <b>' +
      esc(data.run_id || "") +
      "</b></span><span>状态 <b>" +
      esc(info.status || "?") +
      "</b></span><span>骨架 <b>" +
      esc(skelText) +
      "</b></span><span>已完成步骤 <b>" +
      esc(steps) +
      "</b></span><span>模型 <b>" +
      esc(info.model_id || "") +
      "</b></span></div>";
    if (err) {
      html += '<div class="art-error">错误：' + esc(err) + "</div>";
    }
    if (!files.length) {
      html += '<div class="mode-hint">该 run 没有可展示的源输出文件。</div>';
    }
    const kindLabel = { output: "抽取结果", note: "校验", log: "失败日志", meta: "元信息", prompt: "prompt" };
    files.forEach((f) => {
      const kind = f.kind || "";
      const open = kind === "output" || kind === "log" ? " open" : "";
      const trunc = f.truncated ? "（已截断）" : "";
      const tag = kindLabel[kind] ? "[" + kindLabel[kind] + "] " : "";
      html +=
        "<details" +
        open +
        "><summary>" +
        esc(tag + f.name) +
        " · " +
        esc(String(f.bytes || 0)) +
        " B" +
        trunc +
        "</summary><pre>" +
        esc(f.text || "") +
        "</pre></details>";
    });
    box.hidden = false;
    box.innerHTML = html;
  }

  async function showRunArtifacts(runId) {
    const pid = currentPaperId();
    const status = $("deleteRunStatus");
    const rid = runId || selectedRunId();
    if (!pid) {
      if (status) status.textContent = "请先选择文献";
      return;
    }
    if (!rid) {
      if (status) status.textContent = "请先在「结果来源」选择一条 run";
      return;
    }
    if (status) status.textContent = "载入源输出…";
    try {
      const q =
        `/api/run_artifacts?project=${encodeURIComponent(state.currentId)}` +
        `&paper_id=${encodeURIComponent(pid)}&run_id=${encodeURIComponent(rid)}`;
      const data = await api(q);
      renderRunArtifacts(data);
      if (status) status.textContent = "已载入源输出 " + rid;
    } catch (e) {
      if (status) status.textContent = "载入源输出失败：" + (e.message || e);
      const box = $("runArtifactsPanel");
      if (box) {
        box.hidden = false;
        box.innerHTML =
          '<div class="art-error">载入失败：' + esc(e.message || e) + "</div>";
      }
    }
  }

  function fillRunSelect(sel, runs, emptyLabel, keepValue) {
    if (!sel) return;
    const cur = keepValue != null ? keepValue : sel.value;
    sel.innerHTML = "";
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = emptyLabel;
    sel.appendChild(empty);
    (runs || []).forEach((run) => {
      const opt = document.createElement("option");
      opt.value = run.run_id;
      opt.textContent = runOptionLabel(run);
      sel.appendChild(opt);
    });
    if (cur && Array.from(sel.options).some((o) => o.value === cur)) sel.value = cur;
  }

  function factCompareDisplay(raw) {
    if (raw == null) return "";
    if (isWrappedFact(raw)) {
      const text = formatDisplay(raw);
      const st = raw.status || "";
      return st ? text + " [" + st + "]" : text;
    }
    if (typeof raw === "object") return "";
    return String(raw);
  }

  /** 与 tools/run_compare.py::_put 对齐 */
  function putFlat(out, path, raw) {
    if (raw && typeof raw === "object" && !Array.isArray(raw)) {
      if ("value" in raw || "excerpt" in raw) {
        out[path] = factCompareDisplay(raw);
        return;
      }
      Object.keys(raw).forEach((k) => {
        if (String(k).startsWith("_")) return;
        putFlat(out, path ? path + "." + k : k, raw[k]);
      });
      return;
    }
    if (Array.isArray(raw)) return;
    out[path] = raw == null ? "" : String(raw);
  }

  function flattenResult(result) {
    const out = {};
    const r = result || {};
    const meta = r.paper_metadata || {};
    Object.keys(meta).forEach((k) => putFlat(out, "paper_metadata." + k, meta[k]));
    (r.samples || []).forEach((sample, i) => {
      if (!sample || typeof sample !== "object") return;
      const sid = displayValue(sample.sample_id) || sample.sample_id || "#" + i;
      const base = "samples[" + sid + "]";
      Object.keys(sample).forEach((k) => {
        if (k === "sample_id") {
          out[base + ".sample_id"] = String(sid);
          return;
        }
        putFlat(out, base + "." + k, sample[k]);
      });
    });
    (r.conditions || []).forEach((cond, i) => {
      if (!cond || typeof cond !== "object") return;
      const cid = displayValue(cond.condition_id) || cond.condition_id || "#" + i;
      const base = "conditions[" + cid + "]";
      Object.keys(cond).forEach((k) => {
        if (k === "condition_id" || k === "sample_id") {
          out[base + "." + k] = String(displayValue(cond[k]) || cond[k] || "");
          return;
        }
        const v = cond[k];
        if (isPropertyGroup(v)) {
          Object.keys(v).forEach((pk) => putFlat(out, base + "." + k + "." + pk, v[pk]));
        } else {
          putFlat(out, base + "." + k, v);
        }
      });
    });
    (r.figures || []).forEach((fig, i) => {
      if (!fig || typeof fig !== "object") return;
      const fid = displayValue(fig.figure_id) || fig.figure_id || "#" + i;
      const base = "figures[" + fid + "]";
      Object.keys(fig).forEach((k) => {
        if (String(k).startsWith("_")) return;
        putFlat(out, base + "." + k, fig[k]);
      });
    });
    return out;
  }

  function diffFlattened(a, b, includeSame) {
    const keys = Object.keys(Object.assign({}, a, b)).sort();
    const rows = [];
    keys.forEach((path) => {
      const va = a[path] != null ? a[path] : "";
      const vb = b[path] != null ? b[path] : "";
      const changed = va !== vb;
      if (changed || includeSame) rows.push({ path: path, a: va, b: vb, changed: changed });
    });
    return rows;
  }

  function renderRunCompare(rows, labelA, labelB) {
    const box = $("runComparePanel");
    const status = $("compareStatus");
    if (!box) return;
    if (!rows.length) {
      box.hidden = false;
      box.innerHTML = '<div class="mode-hint" style="padding:10px">两侧结果在对比范围内完全一致。</div>';
      if (status) status.textContent = "0 处差异";
      return;
    }
    const changedN = rows.filter((r) => r.changed).length;
    if (status) status.textContent = changedN + " 处差异 / 共 " + rows.length + " 行";
    let html =
      '<table class="run-compare-table"><thead><tr>' +
      "<th>路径</th><th>" +
      esc(labelA || "Run A") +
      "</th><th>" +
      esc(labelB || "Run B") +
      "</th></tr></thead><tbody>";
    rows.forEach((r) => {
      html +=
        '<tr class="' +
        (r.changed ? "diff-changed" : "") +
        '"><td class="diff-path">' +
        esc(r.path) +
        "</td><td>" +
        esc(r.a) +
        "</td><td>" +
        esc(r.b) +
        "</td></tr>";
    });
    html += "</tbody></table>";
    box.hidden = false;
    box.innerHTML = html;
  }

  async function compareSelectedRuns() {
    const pid = currentPaperId();
    const aId = $("compareRunA") && $("compareRunA").value;
    const bId = $("compareRunB") && $("compareRunB").value;
    const status = $("compareStatus");
    if (!pid) {
      if (status) status.textContent = "请先选择文献";
      return;
    }
    if (!aId || !bId) {
      if (status) status.textContent = "请选择 Run A 和 Run B";
      return;
    }
    if (aId === bId) {
      if (status) status.textContent = "请选择两个不同的 run";
      return;
    }
    if (status) status.textContent = "对比中…";
    try {
      const qa =
        `/api/result?project=${encodeURIComponent(state.currentId)}&paper_id=${encodeURIComponent(pid)}` +
        `&run_id=${encodeURIComponent(aId)}`;
      const qb =
        `/api/result?project=${encodeURIComponent(state.currentId)}&paper_id=${encodeURIComponent(pid)}` +
        `&run_id=${encodeURIComponent(bId)}`;
      const [ra, rb] = await Promise.all([api(qa), api(qb)]);
      const includeSame = !!($("compareShowSame") && $("compareShowSame").checked);
      const rows = diffFlattened(
        flattenResult(ra.result || {}),
        flattenResult(rb.result || {}),
        includeSame
      );
      const modeA = modeLabel((ra.run_info || {}).mode);
      const modeB = modeLabel((rb.run_info || {}).mode);
      renderRunCompare(rows, aId + " · " + modeA, bId + " · " + modeB);
    } catch (e) {
      if (status) status.textContent = "对比失败：" + (e.message || e);
      if ($("runComparePanel")) {
        $("runComparePanel").hidden = false;
        $("runComparePanel").innerHTML =
          '<div class="mode-hint" style="padding:10px">对比失败：' + esc(e.message || e) + "</div>";
      }
    }
  }

  async function refreshRuns() {
    const pid = currentPaperId();
    try {
      const data = await api(
        `/api/runs?project=${encodeURIComponent(state.currentId)}&paper_id=${encodeURIComponent(pid)}`
      );
      const runs = data.runs || [];
      fillRunSelect($("runSelect"), runs, "自动选择最新结果");
      fillRunSelect($("compareRunA"), runs, "选择 run");
      fillRunSelect($("compareRunB"), runs, "选择 run");
      // 默认：最新为 A，若有第二份则 B 取下一份
      if ($("compareRunA") && !$("compareRunA").value && runs[0]) {
        $("compareRunA").value = runs[0].run_id;
      }
      if ($("compareRunB") && !$("compareRunB").value && runs[1]) {
        $("compareRunB").value = runs[1].run_id;
      }
      syncAnalyzeButton();
    } catch (e) {
      /* ignore */
    }
  }

  const FOCUS_LABEL = {
    value_binding: "数值绑定",
    process_binding: "工艺对应",
    figure_judgment: "图片判断",
    custom: "自定义",
  };

  function collectAnalyzeScope() {
    const focuses = Array.from(document.querySelectorAll(".analyze-focus:checked")).map(
      (el) => el.value
    );
    const custom = (($("analyzeCustomFocus") && $("analyzeCustomFocus").value) || "").trim();
    return { focuses: focuses, custom_focus: custom };
  }

  function syncAnalyzeButton() {
    const btn = $("btnStartAnalyze");
    if (!btn) return;
    const type = ($("analyzeType") && $("analyzeType").value) || "vs_source";
    let ok = !!currentPaperId();
    if (type === "vs_runs") {
      const a = $("compareRunA") && $("compareRunA").value;
      const b = $("compareRunB") && $("compareRunB").value;
      ok = ok && !!a && !!b && a !== b;
    } else {
      ok = ok && !!state.currentResult;
    }
    btn.disabled = !ok || !!state.analyzing;
  }

  function locateResultPath(path) {
    if (!path) return;
    const box = $("resultFieldList");
    if (!box) return;
    const nodes = box.querySelectorAll("[data-result-path]");
    let best = null;
    let bestLen = -1;
    nodes.forEach((el) => {
      const p = el.getAttribute("data-result-path") || "";
      if (path === p || path.startsWith(p + ".") || path.startsWith(p + "[")) {
        if (p.length > bestLen) {
          best = el;
          bestLen = p.length;
        }
      }
    });
    if (!best) return;
    best.scrollIntoView({ block: "center", behavior: "smooth" });
    best.classList.add("path-flash");
    window.setTimeout(() => best.classList.remove("path-flash"), 1600);
    if (best.classList.contains("field-result-item")) best.click();
  }

  function renderAnalyzePanel(analysis) {
    const box = $("analyzePanel");
    if (!box) return;
    box.hidden = false;
    if (!analysis) {
      box.innerHTML = '<div class="mode-hint" style="padding:10px">尚无分析。</div>';
      return;
    }
    if (analysis.status === "failed") {
      box.innerHTML =
        '<div class="analyze-error">分析失败：' +
        esc(analysis.raw_error || analysis.error || "未知错误") +
        "</div>";
      return;
    }
    const issues = analysis.issues || [];
    let html = '<div class="analyze-summary">' + esc(analysis.summary || "") + "</div>";
    html +=
      '<table class="run-compare-table analyze-table"><thead><tr>' +
      "<th>严重度</th><th>焦点</th><th>路径</th><th>标题</th><th>说明</th><th>建议</th>" +
      "</tr></thead><tbody>";
    if (!issues.length) {
      html += '<tr><td colspan="6" class="mode-hint">未发现所选范围内的硬问题</td></tr>';
    }
    issues.forEach((it) => {
      const sev = it.severity || "medium";
      html +=
        '<tr><td class="sev-' +
        esc(sev) +
        '">' +
        esc(sev) +
        "</td><td>" +
        esc(FOCUS_LABEL[it.focus] || it.focus || "") +
        '</td><td class="analyze-path" data-locate-path="' +
        esc(it.path || "") +
        '">' +
        esc(it.path || "—") +
        "</td><td>" +
        esc(it.title || "") +
        "</td><td>" +
        esc(it.detail || "") +
        "</td><td>" +
        esc(it.suggestion || "") +
        "</td></tr>";
    });
    html += "</tbody></table>";
    box.innerHTML = html;
    box.querySelectorAll("[data-locate-path]").forEach((td) => {
      td.addEventListener("click", () => locateResultPath(td.getAttribute("data-locate-path")));
    });
  }

  async function refreshAnalyzeHistory() {
    const sel = $("analyzeHistory");
    const pid = currentPaperId();
    if (!sel || !pid) return;
    try {
      const data = await api(
        `/api/analyze_list?project=${encodeURIComponent(state.currentId)}&paper_id=${encodeURIComponent(pid)}`
      );
      const items = data.analyses || [];
      const keep = state.currentAnalysisId || sel.value;
      sel.innerHTML = "";
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = items.length ? "选择历史记录" : "暂无记录";
      sel.appendChild(empty);
      items.forEach((it) => {
        const opt = document.createElement("option");
        opt.value = it.analysis_id;
        const typ = it.analysis_type === "vs_runs" ? "Run对比" : "vs原文";
        const st = it.status === "failed" ? "失败" : "成功";
        opt.textContent = `${it.created_at || it.analysis_id} · ${typ} · ${st}`;
        sel.appendChild(opt);
      });
      if (keep && Array.from(sel.options).some((o) => o.value === keep)) sel.value = keep;
    } catch (e) {
      /* ignore */
    }
  }

  async function loadSavedAnalysis(analysisId) {
    const pid = currentPaperId();
    if (!analysisId || !pid) return;
    const status = $("analyzeStatus");
    try {
      const data = await api(
        `/api/analyze?project=${encodeURIComponent(state.currentId)}` +
          `&paper_id=${encodeURIComponent(pid)}&analysis_id=${encodeURIComponent(analysisId)}`
      );
      state.currentAnalysisId = analysisId;
      renderAnalyzePanel(data);
      if (status) status.textContent = data.status === "failed" ? "历史：失败" : "已载入历史";
    } catch (e) {
      if (status) status.textContent = "载入失败：" + (e.message || e);
    }
  }

  async function startAnalyze() {
    const pid = currentPaperId();
    const status = $("analyzeStatus");
    const type = ($("analyzeType") && $("analyzeType").value) || "vs_source";
    if (!pid) {
      if (status) status.textContent = "请先选择文献";
      return;
    }
    if (type === "vs_runs") {
      const a = $("compareRunA") && $("compareRunA").value;
      const b = $("compareRunB") && $("compareRunB").value;
      if (!a || !b || a === b) {
        if (status) status.textContent = "请选择两个不同的 Run A / Run B";
        return;
      }
    } else if (!state.currentResult) {
      if (status) status.textContent = "请先载入抽取结果";
      return;
    }
    state.analyzing = true;
    syncAnalyzeButton();
    if (status) status.textContent = "分析中…";
    try {
      const body = {
        project: state.currentId,
        paper_id: pid,
        analysis_type: type,
        model_id: state.selectedModel && state.selectedModel.id,
      };
      const scope = collectAnalyzeScope();
      if (!scope.focuses.length && !scope.custom_focus) {
        if (status) status.textContent = "请至少勾选一类检查，或填写自定义检查重点";
        state.analyzing = false;
        syncAnalyzeButton();
        return;
      }
      body.focuses = scope.focuses;
      if (scope.custom_focus) body.custom_focus = scope.custom_focus;
      if (type === "vs_source") {
        const runId = $("runSelect") && $("runSelect").value;
        if (runId) body.run_id = runId;
      } else {
        body.run_id_a = $("compareRunA").value;
        body.run_id_b = $("compareRunB").value;
      }
      const out = await api("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const analysis = out.analysis || out;
      state.currentAnalysisId = out.analysis_id || analysis.analysis_id || "";
      renderAnalyzePanel(analysis);
      await refreshAnalyzeHistory();
      if ($("analyzeHistory") && state.currentAnalysisId) {
        $("analyzeHistory").value = state.currentAnalysisId;
      }
      if (status) {
        status.textContent = out.ok === false ? "分析失败" : `完成 · ${(analysis.issues || []).length} 条`;
      }
    } catch (e) {
      if (status) status.textContent = "分析失败：" + (e.message || e);
      if ($("analyzePanel")) {
        $("analyzePanel").hidden = false;
        $("analyzePanel").innerHTML =
          '<div class="analyze-error">分析失败：' + esc(e.message || e) + "</div>";
      }
    } finally {
      state.analyzing = false;
      syncAnalyzeButton();
    }
  }

  // ---------------------------------------------------------------- prompt preview
  function defaultSteps(f) {
    const s = [{ id: "entity", type: "entity", name: "Stage1 · 样品-状态骨架" }];
    if ((f.property || []).length)
      s.push({ id: "property", type: "property", name: "Stage2 · 性能", group: "properties", fields: f.property });
    if ((f.figure || []).length) s.push({ id: "figures", type: "figure", name: "Stage3 · 图片分类" });
    return s;
  }

  function buildPromptPreview() {
    const p = state.project;
    const f = p.fields || {};
    const rules = p.rules || {};
    const src = p.property_source || {};
    const steps = p.steps && p.steps.length ? p.steps : defaultSteps(f);
    const fmtRules = (keys) =>
      keys
        .map(
          (k) =>
            rules[k] &&
            `- [${k}] ${rules[k].rule || ""}` +
              (rules[k].positive_examples ? `\n    正例: ${rules[k].positive_examples}` : "") +
              (rules[k].negative_examples ? `\n    反例: ${rules[k].negative_examples}` : "")
        )
        .filter(Boolean)
        .join("\n");
    state.prompts = {};
    state.promptLabels = {};
    steps.forEach((s) => {
      state.promptLabels[s.id] = s.name || s.id;
      if (s.type === "entity") {
        const schema = {
          paper_metadata: obj(f.metadata),
          samples: [obj(f.sample)],
          conditions: [Object.assign({ sample_id: "S1" }, obj(f.condition))],
          figures: [obj(f.figure)],
        };
        state.prompts[s.id] =
          `[${s.name}] 只建立样品/状态索引，不抽性能值。\n\n` +
          JSON.stringify(schema, null, 2) +
          `\n\n## 抽取规则\n` +
          fmtRules(
            [].concat(
              (f.sample || []).map((x) => `sample.${x}`),
              (f.condition || []).map((x) => `condition.${x}`)
            )
          );
      } else if (s.type === "property") {
        const flds = s.fields || [];
        state.prompts[s.id] =
          `[${s.name}] 只给已有 condition 补【${s.group}】：${flds.join(", ")}\n` +
          `禁止新增样品/状态，也不要抽本组以外的字段。\n\n` +
          JSON.stringify(
            {
              properties: [
                Object.assign(
                  { condition_id: "C1", sample_id: "S1" },
                  obj(flds, { value: "...", unit: "...", source: "measured_table" })
                ),
              ],
            },
            null,
            2
          ) +
          `\n\n## 本组字段规则\n` +
          fmtRules(flds.map((x) => `property.${x}`)) +
          `\n\n## 来源要求\n允许: ${(src.allow || []).join(", ") || "(未配置)"}\n禁止: ${(src.deny || []).join(", ") || "(未配置)"}`;
      } else if (s.type === "figure") {
        state.prompts[s.id] = "（图片分类为确定性规则步骤：按 is_microstructure_image / is_post_test_image 过滤，非 LLM prompt）";
      }
    });
    const ids = Object.keys(state.prompts);
    if (!ids.includes(state.promptTab)) state.promptTab = ids[0] || "";
    renderPromptTab();
  }

  function obj(keys, val) {
    const o = {};
    (keys || []).forEach((k) => (o[k] = val || "..."));
    return o;
  }

  function renderPromptTab() {
    const tabs = $("promptTabs");
    const ids = Object.keys(state.prompts);
    tabs.innerHTML = ids
      .map(
        (id) =>
          `<button class="tab${id === state.promptTab ? " active" : ""}" data-prompt-tab="${esc(id)}">` +
          `${esc((state.promptLabels && state.promptLabels[id]) || id)}</button>`
      )
      .join("");
    tabs.querySelectorAll("[data-prompt-tab]").forEach((t) => {
      t.addEventListener("click", () => {
        state.promptTab = t.getAttribute("data-prompt-tab");
        renderPromptTab();
      });
    });
    $("promptPreview").textContent = state.prompts[state.promptTab] || "";
  }

  // ---------------------------------------------------------------- snapshot table
  function renderSnapshotTable() {
    const box = $("snapshotPapers");
    const sp = (SNAPSHOT.projects || {})[state.currentId];
    if (!sp) {
      box.innerHTML = '<div class="snap-empty">该项目无远端快照数据。</div>';
      return;
    }
    const summary = sp.summary || {};
    const rows = sp.sample_outputs || [];
    let html =
      `<div class="snap-summary">远端批量产出：篇数 <b>${summary.total_papers ?? "?"}</b> · ` +
      `行数 <b>${summary.total_rows ?? "?"}</b> · 嵌图 <b>${summary.xlsx_inserted_images ?? "?"}</b></div>`;
    if (rows.length) {
      html +=
        '<table class="snap-table"><thead><tr><th>paper_id</th><th>样品</th><th>状态</th><th>图片</th></tr></thead><tbody>' +
        rows
          .map(
            (r) =>
              `<tr><td>${esc(r.paper_id)}</td><td>${r.samples}</td><td>${r.conditions}</td><td>${r.figures}</td></tr>`
          )
          .join("") +
        "</tbody></table>";
    }
    box.innerHTML = html;
  }

  // ---------------------------------------------------------------- events
  function bindEvents() {
    document.querySelectorAll("#viewNav [data-view]").forEach((btn) => {
      btn.addEventListener("click", () => setView(btn.getAttribute("data-view")));
    });
    $("btnRunAll").addEventListener("click", runAll);
    $("btnRunStep").addEventListener("click", runStep);
    $("btnParseOnly").addEventListener("click", parseOnly);
    $("btnReextract").addEventListener("click", reextract);
    $("btnImportPdfs").addEventListener("click", importPdfs);
    $("btnRunSelected").addEventListener("click", runSelectedPapers);
    if ($("btnCancelJobs")) $("btnCancelJobs").addEventListener("click", () => cancelJobs(""));
    $("paperSelectAll").addEventListener("change", onPaperSelectAllChange);
    $("btnGoReview").onclick = () => {
      setView("review");
      loadReview();
    };
    $("btnExport").addEventListener("click", exportProject);
    $("btnExportResults").addEventListener("click", exportResults);
    if ($("copySchemaBtnMain")) $("copySchemaBtnMain").addEventListener("click", copySchemaText);
    if ($("exportSelectAll")) {
      $("exportSelectAll").addEventListener("change", (e) => {
        document.querySelectorAll("#exportPaperChecks input[data-export-paper]").forEach((el) => {
          el.checked = e.target.checked;
        });
        syncExportSelectAll();
      });
    }
    if ($("exportPaperChecks")) {
      $("exportPaperChecks").addEventListener("change", syncExportSelectAll);
    }
    $("toggleLegacyDev").addEventListener("change", (e) => {
      setLegacyDevPanelsVisible(e.target.checked);
    });
    $("btnSaveConfig").addEventListener("click", saveConfigView);
    if ($("documentKind")) {
      $("documentKind").addEventListener("change", () => {
        if (!state.overlay) return;
        state.overlay.document_kind = $("documentKind").value;
        setConfigStatus("已更新草稿，保存配置后生效。", "running");
      });
    }
    $("btnAddStage").addEventListener("click", addPropertyStage);
    $("btnAddPropertyGroup").addEventListener("click", addCustomPropertyGroup);
    $("btnNewProject").addEventListener("click", openNewProjectDialog);
    if ($("btnDeleteProject")) {
      $("btnDeleteProject").addEventListener("click", deleteCurrentProject);
    }
    $("newProjectTemplate").addEventListener("change", (e) =>
      fillNewProjectChecks(e.target.value)
    );
    if ($("newProjectCopyFrom")) {
      $("newProjectCopyFrom").addEventListener("change", syncNewProjectCopyUI);
    }
    $("saveNewProject").addEventListener("click", saveNewProject);
    $("usePaperBtn").addEventListener("click", async () => {
      state.paperId = currentPaperId();
      renderPaperTable(paperRecords());
      updateRunPreview();
      await restoreEntityDoneFromLatestRun();
    });
    $("paperSelect").addEventListener("change", async () => {
      state.paperId = $("paperSelect").value || "";
      if ($("paperIdInput")) $("paperIdInput").value = state.paperId;
      renderPaperTable(paperRecords());
      updateRunPreview();
      await restoreEntityDoneFromLatestRun();
    });
    $("extractMode").addEventListener("change", updateRunPreview);
    $("outputPartition").addEventListener("change", updateRunPreview);
    $("paperIdInput").addEventListener("input", updateRunPreview);
    $("pdfPathInput").addEventListener("input", updateRunPreview);
    $("loadReviewBtn").addEventListener("click", loadReview);
    if ($("btnShowRunArtifacts")) {
      $("btnShowRunArtifacts").addEventListener("click", () => showRunArtifacts());
    }
    if ($("btnDeleteRun")) $("btnDeleteRun").addEventListener("click", deleteSelectedRun);
    if ($("btnCompareRuns")) $("btnCompareRuns").addEventListener("click", compareSelectedRuns);
    if ($("compareShowSame")) {
      $("compareShowSame").addEventListener("change", () => {
        if ($("compareRunA") && $("compareRunA").value && $("compareRunB") && $("compareRunB").value) {
          compareSelectedRuns();
        }
      });
    }
    if ($("btnStartAnalyze")) $("btnStartAnalyze").addEventListener("click", startAnalyze);
    if ($("analyzeType")) $("analyzeType").addEventListener("change", syncAnalyzeButton);
    if ($("analyzeHistory")) {
      $("analyzeHistory").addEventListener("change", () => {
        const id = $("analyzeHistory").value;
        if (id) loadSavedAnalysis(id);
      });
    }
    ["compareRunA", "compareRunB", "runSelect"].forEach((id) => {
      if ($(id)) $(id).addEventListener("change", syncAnalyzeButton);
    });
    $("refreshRunBtn").addEventListener("click", refreshRuns);
    document.querySelectorAll("#sourceModeTabs [data-source-mode]").forEach((btn) => {
      btn.addEventListener("click", () => setSourceMode(btn.getAttribute("data-source-mode")));
    });
    document.querySelectorAll('input[name="reviewFilter"]').forEach((inp) => {
      inp.addEventListener("change", () => {
        if (!inp.checked) return;
        state.reviewFilter = inp.value;
        if (state.currentResult) renderResultTree(state.currentResult);
      });
    });
    $("addFieldBtn").addEventListener("click", openFieldDialog);
    $("fieldLevel").addEventListener("change", syncFieldGroupVisibility);
    $("copyPromptBtn").addEventListener("click", () => {
      navigator.clipboard && navigator.clipboard.writeText(state.prompts[state.promptTab] || "");
    });
    $("copySchemaBtn").addEventListener("click", copySchemaText);
    $("saveField").addEventListener("click", (ev) => {
      ev.preventDefault();
      saveNewField();
    });
    $("saveRuleOverride").addEventListener("click", saveRuleOverride);
    $("resetRuleOverride").addEventListener("click", resetRuleOverride);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
