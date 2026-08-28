# SDD progress ledger

Task 1: complete (no git commits; review clean after spec 5.7 fix)
Task 2: complete (no git; review clean). Minors: promote/step_overrides untested; silent skip unknown field ids; writeback can create blank.json; unused tempfile import.
Task 3: complete (no git; review clean). Minors: composition/boolean/origin untested; excerpt whitespace mapping; spec figures [] vs brief example object.
Task 4: complete (no git; review clean). Minors: deny_phrase not scanning excerpt; system role still 钢铁材料.
Task 5: complete (no git; review clean). Minors: empty run dirs on skeleton-gate; dead entity_only branch in run_step; figures not in invalidate test; invalidated_steps linger after rerun.
Task 6: complete (no git; review clean). Minors: empty LLM still ok=True; group fallback properties; mkdir on success path.
Task 7: complete (no git; review clean). Minors: uniparser constants imported on fake-client path; .env not loaded in pdf_parser; no missing-key unit test.
Task 8: complete (no git; review clean). Minors: POST routes untested; parse_only paper_id sentinel; unused handle_post import in tests; POST export branch extra.
Task 9: complete (no git; review clean after UI Important fixes). Minor: afterRun may show 仅摘录 until paper text loaded.
Task 10: complete (no git; README/docs updated; pytest 28; two_stage/single_pass verified).

Whole-branch review: Ready with nits (no Critical). Important: blank promote silently dropped fields.
Final-fix wave: complete (no git; review Approved). blank promote raises ValueError; batch reextract UI counts list items; system role → 材料文献结构化抽取专家. pytest 30 passed.
Remaining minors (not blocking): writeback(blank) still FileNotFound; UI may still show promote on blank (API 500); deny_phrase not on excerpt; empty LLM ok=True; skeleton-gate empty run dirs; run_step entity_only dead; afterRun 仅摘录 until paper loaded; pipeline.py size.
