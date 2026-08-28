### Task 8: HTTP API 与 CLI

**Files:**
- Modify: `tools/workbench_server.py`
- Create: `tests/test_api_handlers.py`

**Interfaces:**
- Produces: 规格 8.2 全部端点。路由可用 `urlparse` 手工拆，不必上 Flask。
  - `POST /api/projects` body: `{id, name, template_id, selected_field_ids}`
  - `POST /api/parse` body: `{project, paper_id, overwrite}`；测试可不测 multipart。实现上传：若 `Content-Type` 为 `application/json` 则 `{project, pdf_path}` 指向已有文件；若 `multipart` 则保存到 parsed 目录 `source.pdf` 再 parse。第一版 JSON+本地路径足够，界面用 `<input type=file>` 走 multipart。
  - `POST /api/run` 保持；无 md 且请求带 `pdf_path` 或已上传 source.pdf 则先 parse
  - `POST /api/run_step` `{project, paper_id, step_id, run_id, partition, model_id}`
  - `POST /api/reextract` `{project, field_id, paper_id, scope, partition}`
  - `GET /api/field_library?template=steel`
  - `GET/PUT /api/projects/<id>/config` — 若 stdlib 解析路径不便，用 query：`GET /api/project_config?project=` 与 `PUT /api/project_config?project=`
  - 规格写了 `/api/projects/:id/config`。**实现用路径** `/api/projects/<id>/config` 和 `/api/projects/<id>/export`：在 `do_GET`/`do_PUT`/`do_POST` 里 `parts = route.strip("/").split("/")`
  - `POST /api/field_library/writeback` `{template_id, field}`
  - `POST /api/field_library/promote` `{project, field_id}`
  - CLI: `--parse-only --pdf PATH`、`--step entity`、`--reextract-field yield_strength`、`--export-fields-schema`

为避免改 Handler 难以测，把路由函数做成模块级 `handle_get(route, qs) -> tuple[int, dict]`、`handle_post(route, body, files=None)`，Handler 只做 IO。测试直接调 `handle_*`。

- [ ] **Step 1: Write failing tests for handle_get export and handle_post run_step**

```python
# tests/test_api_handlers.py
from tools.workbench_server import handle_get, handle_post


def test_export_demo():
    status, data = handle_get("/api/projects/demo_steel/export", {})
    assert status == 200
    assert data["template_id"] == "steel"
    assert data["fields"]


def test_field_library():
    status, data = handle_get("/api/field_library", {"template": ["steel"]})
    assert status == 200
    assert data["fields"]
```

- [ ] **Step 2: FAIL then implement routing + CLI flags**

`argparse` 增加：

```python
parser.add_argument("--parse-only", action="store_true")
parser.add_argument("--pdf", default=None)
parser.add_argument("--step", default=None)
parser.add_argument("--reextract-field", default=None)
parser.add_argument("--export-fields-schema", action="store_true")
parser.add_argument("--overwrite-parse", action="store_true")
```

互斥优先级：`export` > `parse-only` > `reextract-field` > `step` > `run-once`。

- [ ] **Step 3: pytest `tests/test_api_handlers.py` PASS**

- [ ] **Step 4: `python3 tools/workbench_server.py --export-fields-schema --project demo_steel` 打印 JSON 且含 schema**

- [ ] **Step 5: Commit** `feat: expose parse, staged run, reextract, and export APIs`

---

