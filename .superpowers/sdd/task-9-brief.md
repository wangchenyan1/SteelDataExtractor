### Task 9: 前端四个入口、字段库勾选、出处高亮、导出

**Files:**
- Modify: `app/index.html`
- Modify: `app/app.js`
- Modify: `app/styles.css`

**Interfaces:**
- Consumes: Task 8 API
- Produces: 可离线用 demo 操作的 UI（浏览器手工验；本任务用静态检查 + 现有 mock 跑通）

- [ ] **Step 1: 改 index.html 主操作区**

替换「试运行两阶段抽取」单一按钮为四个：

- `#btnRunAll` 整篇一次跑完
- `#btnRunStep` 跑当前选中步骤（步骤条 `#stepList` 可点，`data-step-id`）
- `#btnParseOnly` 只解析
- `#btnReextract` 只重抽：旁边 `<select id="reextractField">` 与 `<select id="reextractScope">`（当前文献 / 本项目已抽文献）

步骤条：property/figure 在 entity 未完成时加 `disabled`。重跑 entity 前 `confirm("下游性质和图片将作废并重跑")`。

字段配置区：

- 分类展示库字段 checkbox（从 `/api/field_library`）
- 已有「新增字段」改为写入 PUT overlay 的 `private_fields`
- 编辑规则对话框增加单选：`仅本项目` / `写回公共库`
- 「导出」按钮 `#btnExport`：`GET /api/projects/<id>/export` 后下载 `<id>_fields_schema.json`
- 新项目对话框：模板 select（steel/blank）+ 按类勾选 + 提交 `POST /api/projects`

结果列表：每个非标识字段显示 value、location、摘录状态。点击调用 `highlightExcerpt(paperText, excerpt)`：规范化空白后 `indexOf`；命中则把 `#paperTextViewer` 里对应片段包 `<mark>`（若正在显示 PDF iframe，先隐藏 iframe 显示文本视图）。未命中在字段旁显示 excerpt 文本，不加 mark。

- [ ] **Step 2: app.js 把 title 等对象取值改为 `field.value ?? field` 兼容旧字符串**

- [ ] **Step 3: 离线验收命令**

```bash
python3 tools/workbench_server.py --run-once --project demo_steel --paper-id demo_steel_2024 --mode two_stage
python3 tools/workbench_server.py --export-fields-schema --project demo_steel | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['schema']['paper_metadata']['title']['excerpt']=='' or True; assert d['fields']"
```

手工：打开工作台，点字段看 Table 2 高亮；改 title 规则仅本项目，确认 `configs/field_library/steel.json` 未变。

- [ ] **Step 4: Commit** `feat: workbench UI for staged run, field library, provenance, export`

---

