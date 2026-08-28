/* 材料文献抽取工作台前端逻辑。
 * 数据来源：
 *   - 后端 API（/api/projects, /api/run, /api/run_step, /api/parse, /api/reextract ...）
 *   - window.READONLY_SNAPSHOT：远端只读快照（真实批量产出样例，仅展示）。
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

  const CATEGORY_LABELS = {
    metadata: "文章信息",
    sample: "样品信息",
    condition: "状态信息",
    property: "性能",
    figure: "图片信息",
  };

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
    lastRunId: null,
    currentResult: null,
    editingRule: null,
    view: "papers",
    stageDraft: [],
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
      el.hidden = el.getAttribute("data-view-panel") !== name;
    });
    document.querySelectorAll("#viewNav [data-view]").forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-view") === name);
    });
    if (name === "config") loadConfigEditor();
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
          description: "远端只读快照项目（本地无原文，不能试跑）",
          runnable: false,
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
  }

  function normalizeSnapshotRules(fieldRules) {
    return fieldRules || {};
  }

  async function checkHealth() {
    try {
      await api("/api/health");
      state.backendOnline = true;
      $("apiStatus").textContent = "后端已连接";
      $("runStatus").textContent = "后端已连接，可整篇跑、分步跑、只解析或只重抽。";
    } catch (e) {
      state.backendOnline = false;
      $("apiStatus").textContent = "后端未连接（先启动 workbench_server.py）";
      $("runStatus").textContent =
        "未检测到后端。请运行：python3 tools/workbench_server.py，然后刷新页面。";
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
          description: "远端只读快照项目（本地无原文，不能试跑）",
          runnable: false,
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
      el.innerHTML =
        `<span class="project-name">${esc(p.name)}</span>` +
        `<span class="project-tag">${p.runnable ? "可试跑" : "只读快照"}</span>`;
      el.addEventListener("click", () => selectProject(p.id));
      box.appendChild(el);
    });
  }

  async function selectProject(pid) {
    state.currentId = pid;
    state.project = state.projects[pid];
    state.selectedStepId = null;
    state.entityDone = false;
    state.lastRunId = null;
    state.currentResult = null;
    state.paperText = "";
    const p = state.project;
    $("projectTitle").textContent = p.name;
    $("projectDesc").textContent = p.description || "";
    renderProjectList();
    renderModelConfig();
    await loadOverlayAndLibrary();
    renderStepList();
    renderFieldLibraryChecks();
    renderFields();
    renderReextractFields();
    renderSchema();
    renderPapers();
    renderSnapshotTable();
    buildPromptPreview();
    loadConfigEditor();
    updateRunButtons();
    clearRunOutputs();
    await restoreEntityDoneFromLatestRun();
  }

  /** 从最新 run 的 completed_steps（或结果 samples）恢复 entityDone，并刷新步骤条 */
  function applyEntityDoneFromRunInfo(info, result) {
    const completed = (info && info.completed_steps) || [];
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
    if (!state.backendOnline || !state.project || !state.project.runnable || !pid) {
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
    if (!state.backendOnline || !p || !p.runnable) {
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
  function stepTypeLabel(t) {
    return t === "entity" ? "实体·1 次调用"
      : t === "property" ? "性能·1 次调用"
      : t === "figure" ? "图片·规则过滤"
      : t || "";
  }

  function renderStepList() {
    const ol = $("stepList");
    const steps = state.project.steps || [];
    if (!steps.length) {
      ol.innerHTML = "<li>（未配置 steps，使用默认：实体 → 性能 → 图片）</li>";
      return;
    }
    if (!state.selectedStepId) {
      state.selectedStepId = steps[0].id;
    }
    ol.innerHTML = "";
    steps.forEach((s) => {
      const li = document.createElement("li");
      const needsEntity = s.type === "property" || s.type === "figure";
      const disabled = needsEntity && !state.entityDone;
      li.className =
        (s.id === state.selectedStepId ? "active " : "") +
        (disabled ? "disabled" : "");
      li.setAttribute("data-step-id", s.id);
      li.innerHTML =
        `${esc(s.name || s.id)}` +
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
      if (!p || !p.runnable) {
        el.disabled = true;
      } else {
        el.disabled = false;
      }
    });
    if (!p || !p.runnable) {
      $("btnRunAll").textContent = "只读快照·不可试跑";
    } else {
      $("btnRunAll").textContent = "整篇一次跑完";
    }
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
    const p = state.project;
    if (p.backend === "mock") {
      $("modelInfo").textContent =
        "当前示例项目用离线 mock 后端跑通全流程；此处下拉演示真实项目可切换的模型种类（真实项目在 project_config.json 里设 backend=claude 即生效）。";
    } else if (m.backend === "mock") {
      $("modelInfo").textContent = "该项目为真实后端项目，选 mock 仅作占位。";
    } else {
      $("modelInfo").textContent =
        "真实多模态后端：需在工作区 .env 配置 LLM_API_KEY；base_url / model 取自所选模型。";
    }
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

  function renderFieldLibraryChecks() {
    const box = $("fieldLibraryChecks");
    if (!box) return;
    const fields = (state.fieldLibrary && state.fieldLibrary.fields) || [];
    if (!fields.length) {
      box.innerHTML =
        '<div class="mode-hint">（无字段库或后端未连接；当前项目仍可用已有 fields 配置）</div>';
      return;
    }
    const selected = selectedFieldIds();
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
      const wrap = document.createElement("div");
      wrap.className = "lib-checks";
      list.forEach((f) => {
        const lab = document.createElement("label");
        lab.className = "check-item";
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = selected.has(f.id);
        cb.dataset.fieldId = f.id;
        cb.addEventListener("change", () => onLibraryCheckChange(f.id, cb.checked));
        lab.appendChild(cb);
        lab.appendChild(document.createTextNode(` ${f.label || f.id}`));
        if (selected.has(f.id)) {
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
      });
      group.appendChild(wrap);
      box.appendChild(group);
    });
  }

  async function onLibraryCheckChange(fieldId, checked) {
    if (!state.overlay) {
      $("runStatus").textContent = "无覆盖层，无法勾选保存。";
      return;
    }
    // 与 UI 勾选同源（selectedFieldIds 可能回退到 project.fields），避免空数组覆盖层把项目字段清空
    const ids = new Set(selectedFieldIds());
    if (checked) ids.add(fieldId);
    else ids.delete(fieldId);
    state.overlay.selected_field_ids = Array.from(ids);

    const libFields = (state.fieldLibrary && state.fieldLibrary.fields) || [];
    const meta = libFields.find((f) => f.id === fieldId);
    const isProperty = meta && meta.category === "property";

    if (!checked) {
      syncStageDraftFromDom();
      state.stageDraft.forEach((s) => {
        s.fields = (s.fields || []).filter((id) => id !== fieldId);
      });
      if (Array.isArray(state.overlay.steps) && state.overlay.steps.length) {
        state.overlay.steps = state.overlay.steps
          .map((s) => {
            if (s.type !== "property") return s;
            return {
              ...s,
              fields: (s.fields || []).filter((id) => id !== fieldId),
            };
          })
          .filter((s) => s.type !== "property" || (s.fields || []).length);
      }
    }

    // 新勾选的性能字段尚未挂阶段：只更新本地，等「保存配置」一并落盘
    if (checked && isProperty && state.overlay.steps && state.overlay.steps.length) {
      renderFieldLibraryChecks();
      renderStageEditor();
      $("runStatus").textContent =
        "已勾选性能字段，请挂到阶段后点击「保存配置」。";
      return;
    }

    try {
      await saveOverlay(state.overlay);
      logChange(`${checked ? "勾选" : "取消"}字段 ${fieldId}`);
      await refreshProjectConfig();
    } catch (e) {
      $("runStatus").textContent = "保存字段勾选失败：" + e.message;
    }
  }

  async function saveOverlay(overlay) {
    await api(`/api/projects/${encodeURIComponent(state.currentId)}/config`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(overlay),
    });
  }

  async function refreshProjectConfig() {
    await reloadProjects();
    state.project = state.projects[state.currentId];
    await loadOverlayAndLibrary();
    renderStepList();
    renderFieldLibraryChecks();
    renderFields();
    renderReextractFields();
    renderSchema();
    buildPromptPreview();
    loadConfigEditor();
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
    const fields = (state.fieldLibrary && state.fieldLibrary.fields) || [];
    if (fields.length) {
      return fields
        .filter((f) => f.category === "property" && selected.has(f.id))
        .map((f) => f.id);
    }
    const fromProject = ((state.project && state.project.fields) || {}).property || [];
    return fromProject.filter((id) => selected.has(id));
  }

  function fieldLabel(id) {
    const fields = (state.fieldLibrary && state.fieldLibrary.fields) || [];
    const f = fields.find((x) => x.id === id);
    return (f && f.label) || id;
  }

  function fieldGroup(id) {
    const fields = (state.fieldLibrary && state.fieldLibrary.fields) || [];
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
      const checked = Array.from(row.querySelectorAll('input[type="checkbox"]:checked')).map(
        (cb) => cb.value
      );
      draft.fields = checked;
      draft.group = inferGroup(draft.fields, draft.id);
    });
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
      if (!propIds.length) {
        fieldsWrap.innerHTML = '<span class="mode-hint">（请先勾选性能字段）</span>';
      } else {
        propIds.forEach((fid) => {
          const takenElsewhere =
            assigned.has(fid) && !(stage.fields || []).includes(fid);
          const lab = document.createElement("label");
          lab.className = "check-item";
          const cb = document.createElement("input");
          cb.type = "checkbox";
          cb.value = fid;
          cb.checked = (stage.fields || []).includes(fid);
          cb.disabled = takenElsewhere;
          cb.addEventListener("change", () => {
            syncStageDraftFromDom();
            renderStageEditor();
          });
          lab.appendChild(cb);
          lab.appendChild(document.createTextNode(` ${fieldLabel(fid)}`));
          if (takenElsewhere) {
            lab.title = "已挂到其他阶段";
          }
          fieldsWrap.appendChild(lab);
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
        "未挂阶段：" + unassigned.map((id) => fieldLabel(id) + " (" + id + ")").join(", ");
      box.appendChild(hint);
    }
  }

  function loadConfigEditor() {
    loadStageDraftFromOverlay();
    fillStrategyForms();
    renderStageEditor();
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
        group: inferGroup(fields, s.id),
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
      $("runStatus").textContent = "无覆盖层，无法保存配置。";
      return;
    }
    const steps = buildStepsFromEditor();
    const empty = steps.filter((s) => s.type === "property" && !(s.fields || []).length);
    if (empty.length) {
      $("runStatus").textContent =
        "性能阶段不能为空：" + empty.map((s) => s.name || s.id).join(", ");
      return;
    }
    const unassigned = propertyIdsSelected().filter(
      (id) =>
        !steps.some((s) => s.type === "property" && (s.fields || []).includes(id))
    );
    if (unassigned.length) {
      $("runStatus").textContent = "未挂阶段的性能字段：" + unassigned.join(", ");
      return;
    }
    state.overlay.steps = steps;
    state.overlay.selected_field_ids = Array.from(selectedFieldIds());
    state.overlay.property_source = readStrategyPropertySource();
    state.overlay.figure_filter = readStrategyFigureFilter();
    try {
      await saveOverlay(state.overlay);
      logChange("保存配置（字段 / 阶段 / 策略）");
      $("runStatus").textContent = "配置已保存。需重新抽取后结果才按新配置。";
      await refreshProjectConfig();
    } catch (e) {
      $("runStatus").textContent = "保存配置失败：" + e.message;
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
    state.schemaText = JSON.stringify(buildSchema(), null, 2);
    $("schemaPreview").textContent = state.schemaText;
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

    if (!state.backendOnline || !state.project.runnable) {
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
        const overrides = state.overlay.field_overrides || (state.overlay.field_overrides = {});
        overrides[fid] = { ...(overrides[fid] || {}), ...patch };
        await saveOverlay(state.overlay);
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
    if (state.overlay && state.overlay.field_overrides) {
      delete state.overlay.field_overrides[fid];
      saveOverlay(state.overlay)
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
    const name = $("fieldName").value.trim();
    const level = $("fieldLevel").value;
    if (!name) return;
    const fieldObj = {
      id: name,
      label: name,
      category: level,
      group: level === "property" ? "mechanical_properties" : null,
      value_type: "string",
      rule: $("fieldRule").value,
      positive_examples: $("positiveExamples").value,
      negative_examples: $("negativeExamples").value,
      note: "私有字段",
    };

    if (!state.backendOnline || !state.project.runnable || !state.overlay) {
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

    try {
      const priv = state.overlay.private_fields || (state.overlay.private_fields = []);
      if (!priv.some((f) => f.id === name)) priv.push(fieldObj);
      await saveOverlay(state.overlay);
      logChange(`新增私有字段 ${name}`);
      await refreshProjectConfig();
    } catch (e) {
      $("runStatus").textContent = "新增字段失败：" + e.message;
    }
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
  async function exportProject() {
    if (!state.currentId) return;
    try {
      const data = await api(`/api/projects/${encodeURIComponent(state.currentId)}/export`);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${state.currentId}_fields_schema.json`;
      a.click();
      URL.revokeObjectURL(a.href);
      logChange(`导出 ${state.currentId}_fields_schema.json`);
      $("runStatus").textContent = "已下载导出文件。";
    } catch (e) {
      $("runStatus").textContent = "导出失败：" + e.message;
    }
  }

  // ---------------------------------------------------------------- new project
  async function openNewProjectDialog() {
    $("newProjectId").value = "";
    $("newProjectName").value = "";
    $("newProjectTemplate").value = "steel";
    await fillNewProjectChecks("steel");
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
    if (!id) {
      $("runStatus").textContent = "请填写项目 ID。";
      return;
    }
    const selected = [];
    $("newProjectFieldChecks")
      .querySelectorAll("input[data-new-field-id]:checked")
      .forEach((cb) => selected.push(cb.getAttribute("data-new-field-id")));
    try {
      await api("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, name, template_id, selected_field_ids: selected }),
      });
      logChange(`新建项目 ${id}`);
      await reloadProjects();
      renderProjectList();
      await selectProject(id);
    } catch (e) {
      $("runStatus").textContent = "新建项目失败：" + e.message;
    }
  }

  // ---------------------------------------------------------------- papers
  function renderPapers() {
    const sel = $("paperSelect");
    sel.innerHTML = "";
    const papers = state.project.papers || [];
    if (!papers.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "（该项目本地无 parsed_results）";
      sel.appendChild(opt);
    }
    papers.forEach((pid) => {
      const opt = document.createElement("option");
      opt.value = pid;
      opt.textContent = pid;
      sel.appendChild(opt);
    });
    state.paperId = papers[0] || "";
    updateRunPreview();
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

  function setBusy(busy) {
    ["btnRunAll", "btnRunStep", "btnParseOnly", "btnReextract"].forEach((id) => {
      const el = $(id);
      if (!el) return;
      if (busy) el.disabled = true;
      else updateRunButtons();
    });
  }

  // ---------------------------------------------------------------- four entry points
  async function runAll() {
    const p = state.project;
    if (!p.runnable) {
      $("runStatus").textContent = "该项目为只读快照，无法试跑。请选择 demo_steel。";
      return;
    }
    const pid = currentPaperId();
    if (!pid) {
      $("runStatus").textContent = "请先选择或输入 paper_id。";
      return;
    }
    setBusy(true);
    $("runStatus").textContent = `正在整篇运行（${$("extractMode").value}）...`;
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
      $("runStatus").textContent =
        `完成：${out.run_id}（样品 ${out.result.samples ? out.result.samples.length : 0} · ` +
        `状态 ${out.result.conditions ? out.result.conditions.length : 0} · ` +
        `图片保留 ${(out.figures || []).length} · 规则命中 ${(out.warnings || []).length}）`;
      await refreshRuns();
    } catch (e) {
      $("runStatus").textContent = "运行失败：" + e.message;
    } finally {
      setBusy(false);
    }
  }

  async function runStep() {
    const p = state.project;
    if (!p.runnable) return;
    const pid = currentPaperId();
    if (!pid) {
      $("runStatus").textContent = "请先选择或输入 paper_id。";
      return;
    }
    const stepId = state.selectedStepId;
    if (!stepId) {
      $("runStatus").textContent = "请先在左侧步骤条选择一步。";
      return;
    }
    const step = (p.steps || []).find((s) => s.id === stepId);
    if (step && (step.type === "property" || step.type === "figure") && !state.entityDone) {
      $("runStatus").textContent = "骨架未完成，无法跑性能/图片步骤。";
      return;
    }
    if (step && step.type === "entity" && state.entityDone) {
      if (!confirm("下游性质和图片将作废并重跑")) return;
    }
    setBusy(true);
    $("runStatus").textContent = `正在跑步骤 ${stepId}...`;
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
      $("runStatus").textContent =
        `步骤完成：${stepId}（run ${out.run_id}，作废下游：${inv}）`;
      await refreshRuns();
    } catch (e) {
      $("runStatus").textContent = "分步运行失败：" + e.message;
    } finally {
      setBusy(false);
    }
  }

  async function parseOnly() {
    const p = state.project;
    if (!p.runnable) return;
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
    if (!p.runnable) return;
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
    if (!warnings || !warnings.length) {
      box.innerHTML = '<div class="review-empty">规则校验：无剔除项。</div>';
      return;
    }
    box.innerHTML = warnings
      .map((w) => {
        const tag = w.type === "figure_dropped" ? "图片过滤" : "性能来源剔除";
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

  /** 与 highlightExcerpt 相同的空白规范化匹配（不改 DOM） */
  function excerptMatchesInText(paperText, excerpt) {
    const nEx = normalizeWs(excerpt);
    if (!nEx) return false;
    const text = paperText || "";
    return normalizeWs(text).indexOf(nEx) >= 0;
  }

  /** 规范化空白后 indexOf；命中则用可伸缩空白的正则在原文定位并包 &lt;mark&gt; */
  function highlightExcerpt(paperText, excerpt) {
    const viewer = $("paperTextViewer");
    const pdf = $("pdfViewer");
    if (pdf && !pdf.hidden) {
      pdf.hidden = true;
      viewer.hidden = false;
    }
    const text = paperText || state.paperText || viewer.textContent || "";
    state.paperText = text;
    if (!excerptMatchesInText(text, excerpt)) {
      viewer.textContent = text;
      return false;
    }
    const nEx = normalizeWs(excerpt);
    // 将规范化摘录转成允许空白伸缩的正则，在原文中找首个匹配
    const parts = nEx.split(" ").map((p) => p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    const re = new RegExp(parts.join("\\s+"));
    const m = text.match(re);
    if (!m || m.index == null) {
      viewer.textContent = text;
      return false;
    }
    const start = m.index;
    const end = start + m[0].length;
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

  function isWrappedFact(v) {
    return v && typeof v === "object" && !Array.isArray(v) && ("value" in v || "excerpt" in v);
  }

  function isIdentityKey(key) {
    return IDENTITY_IDS.has(key) || key === "sample_id" || key === "condition_id";
  }

  function collectResultFields(result) {
    const items = [];
    const meta = result.paper_metadata || {};
    Object.keys(meta).forEach((k) => {
      if (isIdentityKey(k)) return;
      items.push({ path: `paper_metadata.${k}`, key: k, raw: meta[k] });
    });
    (result.samples || []).forEach((s, i) => {
      Object.keys(s || {}).forEach((k) => {
        if (isIdentityKey(k)) return;
        items.push({
          path: `samples[${i}].${k}`,
          key: k,
          raw: s[k],
          ctx: s.sample_id || `S${i + 1}`,
        });
      });
    });
    (result.conditions || []).forEach((c, i) => {
      Object.keys(c || {}).forEach((k) => {
        if (isIdentityKey(k) || k === "sample_id") return;
        const v = c[k];
        if (v && typeof v === "object" && !Array.isArray(v) && !isWrappedFact(v) && !("unit" in v)) {
          // property group
          Object.keys(v).forEach((pk) => {
            items.push({
              path: `conditions[${i}].${k}.${pk}`,
              key: pk,
              raw: v[pk],
              ctx: c.condition_id || `C${i + 1}`,
            });
          });
        } else {
          items.push({
            path: `conditions[${i}].${k}`,
            key: k,
            raw: v,
            ctx: c.condition_id || `C${i + 1}`,
          });
        }
      });
    });
    (result.figures || []).forEach((f, i) => {
      Object.keys(f || {}).forEach((k) => {
        if (isIdentityKey(k) || k === "sample_id" || k === "condition_id") return;
        items.push({
          path: `figures[${i}].${k}`,
          key: k,
          raw: f[k],
          ctx: f.figure_id || `F${i + 1}`,
        });
      });
    });
    return items;
  }

  function renderResultFieldList(result) {
    const box = $("resultFieldList");
    const items = collectResultFields(result || {});
    if (!items.length) {
      box.innerHTML = '<div class="review-empty">暂无带出处的字段结果。</div>';
      return;
    }
    const paperText =
      state.paperText || ($("paperTextViewer") && $("paperTextViewer").textContent) || "";
    box.innerHTML = "";
    items.forEach((it) => {
      const raw = it.raw;
      const wrapped = isWrappedFact(raw);
      const value = formatDisplay(raw);
      const location = wrapped ? raw.location || "" : "";
      const excerpt = wrapped ? raw.excerpt || "" : "";
      const hasExcerpt = !!excerpt;
      // 渲染时即用与 highlightExcerpt 相同的规范化匹配判定「已定位」/「仅摘录」
      let status = "无摘录";
      if (hasExcerpt) {
        status = excerptMatchesInText(paperText, excerpt) ? "已定位" : "仅摘录";
      }
      const el = document.createElement("button");
      el.type = "button";
      el.className = "field-result-item";
      el.innerHTML =
        `<span class="fr-path">${esc(it.path)}</span>` +
        `<span class="fr-value">${esc(value)}${wrapped && raw.unit ? " " + esc(raw.unit) : ""}</span>` +
        `<span class="fr-loc">${esc(location || "—")}</span>` +
        `<span class="fr-status">${esc(status)}</span>` +
        `<span class="fr-miss" hidden></span>`;
      el.addEventListener("click", () => {
        const miss = el.querySelector(".fr-miss");
        const statusEl = el.querySelector(".fr-status");
        if (!excerpt) {
          miss.hidden = false;
          miss.textContent = "无摘录可高亮";
          return;
        }
        const text = state.paperText || $("paperTextViewer").textContent || "";
        const ok = highlightExcerpt(text, excerpt);
        if (statusEl) statusEl.textContent = ok ? "已定位" : "仅摘录";
        if (!ok) {
          miss.hidden = false;
          miss.textContent = `仅摘录：${excerpt}`;
        } else {
          miss.hidden = true;
          miss.textContent = "";
        }
      });
      box.appendChild(el);
    });
  }

  // ---------------------------------------------------------------- review panes
  async function loadReview() {
    const pid = currentPaperId();
    if (!pid) {
      $("runStatus").textContent = "请先选择 paper_id。";
      return;
    }
    try {
      const txt = await api(
        `/api/paper_text?project=${encodeURIComponent(state.currentId)}&paper_id=${encodeURIComponent(pid)}`
      );
      state.paperText = txt.text || "";
      $("paperTextViewer").textContent = state.paperText;
      $("pdfViewer").hidden = true;
      $("paperTextViewer").hidden = false;
      $("sourceMeta").textContent = `${pid} · ${state.paperText.length} 字符`;
    } catch (e) {
      $("paperTextViewer").textContent = "载入原文失败：" + e.message;
      $("sourceMeta").textContent = "载入失败";
    }
    try {
      const runId = $("runSelect").value || "";
      const q =
        `/api/result?project=${encodeURIComponent(state.currentId)}&paper_id=${encodeURIComponent(pid)}` +
        (runId ? `&run_id=${encodeURIComponent(runId)}` : "");
      const res = await api(q);
      applyEntityDoneFromRunInfo(res.run_info || {}, res.result || {});
      renderStepList();
      fillResultPanes(res);
    } catch (e) {
      $("resultMeta").textContent = "暂无结果";
      $("resultFieldList").innerHTML = "";
    }
  }

  function fillResultPanes(res) {
    const r = res.result || {};
    state.currentResult = r;
    const info = res.run_info || {};
    $("resultMeta").textContent = info.run_id
      ? `${info.run_id} · ${info.mode || ""} · ${info.backend || ""}`
      : "";
    const trim = (r._pipeline && r._pipeline.input_trim) || {};
    $("resultSummary").innerHTML =
      `<span>样品 <b>${(r.samples || []).length}</b></span>` +
      `<span>状态 <b>${(r.conditions || []).length}</b></span>` +
      `<span>图片 <b>${(r.figures || []).length}</b></span>` +
      `<span>性能值 <b>${countProps(r)}</b></span>` +
      (trim.kept_ratio != null
        ? `<span>输入保留 <b>${(trim.kept_ratio * 100).toFixed(1)}%</b></span>`
        : "");
    renderResultFieldList(r);
    renderWarnings("resultReviewList", res.warnings);
  }

  async function refreshRuns() {
    const pid = currentPaperId();
    try {
      const data = await api(
        `/api/runs?project=${encodeURIComponent(state.currentId)}&paper_id=${encodeURIComponent(pid)}`
      );
      const sel = $("runSelect");
      const cur = sel.value;
      sel.innerHTML = '<option value="">自动选择最新结果</option>';
      (data.runs || []).forEach((run) => {
        const opt = document.createElement("option");
        opt.value = run.run_id;
        opt.textContent = `${run.run_id} (${run.mode}, 命中${run.warnings != null ? run.warnings : "?"})`;
        sel.appendChild(opt);
      });
      sel.value = cur;
    } catch (e) {
      /* ignore */
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
          conditions: [obj(f.condition)],
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
                  { condition_id: "C1" },
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
        state.prompts[s.id] = "（图片分类为确定性规则步骤：按 figure_filter 白名单过滤，非 LLM prompt）";
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
      box.innerHTML = '<div class="snap-empty">该项目无远端快照数据（离线示例项目）。</div>';
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
    $("btnExport").addEventListener("click", exportProject);
    $("btnSaveConfig").addEventListener("click", saveConfigView);
    $("btnAddStage").addEventListener("click", addPropertyStage);
    $("btnNewProject").addEventListener("click", openNewProjectDialog);
    $("newProjectTemplate").addEventListener("change", (e) =>
      fillNewProjectChecks(e.target.value)
    );
    $("saveNewProject").addEventListener("click", saveNewProject);
    $("usePaperBtn").addEventListener("click", async () => {
      state.paperId = currentPaperId();
      updateRunPreview();
      await restoreEntityDoneFromLatestRun();
    });
    $("paperSelect").addEventListener("change", async () => {
      updateRunPreview();
      await restoreEntityDoneFromLatestRun();
    });
    $("extractMode").addEventListener("change", updateRunPreview);
    $("outputPartition").addEventListener("change", updateRunPreview);
    $("paperIdInput").addEventListener("input", updateRunPreview);
    $("pdfPathInput").addEventListener("input", updateRunPreview);
    $("loadReviewBtn").addEventListener("click", loadReview);
    $("refreshRunBtn").addEventListener("click", refreshRuns);
    $("addFieldBtn").addEventListener("click", () => $("fieldDialog").showModal());
    $("copyPromptBtn").addEventListener("click", () => {
      navigator.clipboard && navigator.clipboard.writeText(state.prompts[state.promptTab] || "");
    });
    $("copySchemaBtn").addEventListener("click", () => {
      navigator.clipboard && navigator.clipboard.writeText(state.schemaText || "");
    });
    $("saveField").addEventListener("click", saveNewField);
    $("saveRuleOverride").addEventListener("click", saveRuleOverride);
    $("resetRuleOverride").addEventListener("click", resetRuleOverride);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
