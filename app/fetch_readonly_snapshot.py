#!/usr/bin/env python3
"""Fetch a read-only snapshot from Extract_data for the local demo.

This script only reads the remote /internfs tree through ssh and writes a local
JavaScript snapshot next to the static demo. It never writes to Extract_data.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path


REMOTE_ROOT = "/internfs/wangchenyan/shougang/Extract_data"
SSH_TARGET = "dp_cpu"
OUT_FILE = Path(__file__).with_name("readonly_snapshot.js")

PROJECTS = {
    "non_magnetic": "无磁钢",
    "nuclear_fusion": "核聚变低磁奥氏体钢",
    "cor_res": "耐蚀钢",
    "cuti": "钛铜",
}


def run_remote_python() -> dict:
    code = r'''
import csv
import glob
import json
import os
import re

ROOT = "/internfs/wangchenyan/shougang/Extract_data"
PROJECTS = {
    "non_magnetic": "无磁钢",
    "nuclear_fusion": "核聚变低磁奥氏体钢",
    "cor_res": "耐蚀钢",
    "cuti": "钛铜",
}

def parse_summary(project_dir):
    path = os.path.join(project_dir, "database_tables", "final_database_summary.md")
    result = {"total_papers": None, "total_rows": None, "xlsx_inserted_images": None, "per_paper": []}
    if not os.path.exists(path):
        return result
    text = open(path, encoding="utf-8", errors="ignore").read()
    patterns = {
        "total_papers": r"total papers:\s*(\d+)",
        "total_rows": r"total rows:\s*(\d+)",
        "xlsx_inserted_images": r"xlsx inserted images:\s*(\d+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text, re.I)
        if m:
            result[key] = int(m.group(1))
    for line in text.splitlines():
        if not line.startswith("|") or line.startswith("|---") or "paper_id" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 6:
            try:
                result["per_paper"].append({
                    "paper_id": cells[0],
                    "samples": int(cells[1]),
                    "conditions": int(cells[2]),
                    "figures": int(cells[3]),
                    "microstructure": int(cells[4]),
                    "rows": int(cells[5]),
                })
            except ValueError:
                pass
    return result

def infer_fields(project_dir):
    scripts = glob.glob(os.path.join(project_dir, "scripts", "01_extract.py"))
    fields = {"metadata": [], "sample": [], "condition": [], "property": [], "figure": []}
    if not scripts:
        return fields
    text = open(scripts[0], encoding="utf-8", errors="ignore").read()
    for name in [
        "title", "doi", "journal", "year", "authors", "material_system",
        "abstract", "keywords",
    ]:
        if name in text:
            fields["metadata"].append(name)
    for name in [
        "sample_name", "product_form", "alloy_family", "composition",
        "base_processing_description", "sample_processing_overview",
        "sample_microstructure_overview",
    ]:
        if name in text:
            fields["sample"].append(name)
    for name in [
        "condition_name", "condition_type", "component_type",
        "joint_or_material_type", "welding_process", "filler_material",
        "heat_treatment_condition", "test_temperature",
        "condition_processing_description", "microstructure",
    ]:
        if name in text:
            fields["condition"].append(name)
    for name in [
        "yield_strength", "tensile_strength", "elongation",
        "fracture_toughness", "permeability", "hardness",
        "conductivity", "corrosion_rate", "pitting_potential",
        "passive_current_density", "polarization_resistance",
    ]:
        if name in text:
            fields["property"].append(name)
    for name in [
        "figure_id", "placeholder_index", "figure_type",
        "is_microstructure_image", "is_post_test_image", "sample_id",
        "condition_id", "caption", "scale_bar_info", "image_purpose",
    ]:
        if name in text:
            fields["figure"].append(name)
    return fields

def add_keys(target, keys):
    for key in keys:
        if key and key not in target:
            target.append(key)

def infer_fields_from_outputs(project_dir, fields, limit=12):
    for path in sorted(glob.glob(os.path.join(project_dir, "outputs", "*", "paper.json")))[:limit]:
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        metadata = data.get("paper_metadata")
        if isinstance(metadata, dict):
            add_keys(fields["metadata"], metadata.keys())
        for sample in data.get("samples") or []:
            if isinstance(sample, dict):
                add_keys(fields["sample"], sample.keys())
        for condition in data.get("conditions") or []:
            if isinstance(condition, dict):
                for key, value in condition.items():
                    if key in {
                        "mechanical_properties", "magnetic_properties",
                        "corrosion_properties", "electrical_properties",
                        "thermal_properties", "fatigue_properties",
                    } and isinstance(value, dict):
                        add_keys(fields["property"], value.keys())
                    else:
                        add_keys(fields["condition"], [key])
        for figure in data.get("figures") or []:
            if isinstance(figure, dict):
                add_keys(fields["figure"], figure.keys())
    return fields

FIELD_ALIASES = {
    "title": ["title", "paper_metadata"],
    "material_system": ["material_system", "钢种", "合金体系"],
    "sample_name": ["sample_name", "样品识别", "样品（sample）"],
    "sample_id": ["sample_id"],
    "product_form": ["product_form"],
    "alloy_family": ["alloy_family"],
    "composition": ["composition", "化学成分"],
    "composition_unit": ["composition_unit", "化学成分"],
    "base_processing_description": ["base_processing_description", "样品级公共工艺"],
    "sample_processing_overview": ["sample_processing_overview"],
    "sample_microstructure_overview": ["sample_microstructure_overview"],
    "condition_id": ["condition_id"],
    "condition_name": ["condition_name"],
    "condition_type": ["condition_type"],
    "component_type": ["component_type"],
    "joint_or_material_type": ["joint_or_material_type"],
    "welding_process": ["welding_process", "焊接"],
    "filler_material": ["filler_material", "焊材", "焊丝"],
    "heat_treatment_condition": ["heat_treatment_condition", "热处理"],
    "test_temperature": ["test_temperature", "测试温度"],
    "condition_processing_description": ["condition_processing_description"],
    "microstructure": ["microstructure", "组织描述"],
    "grain_size": ["grain_size", "晶粒尺寸"],
    "magnetic_properties": ["magnetic_properties", "磁性能"],
    "permeability": ["permeability", "磁导率"],
    "mechanical_properties": ["mechanical_properties", "力学性能"],
    "yield_strength": ["yield_strength", "屈服强度", "YS", "Rp0.2"],
    "tensile_strength": ["tensile_strength", "抗拉强度", "UTS", "Rm"],
    "elongation": ["elongation", "伸长率"],
    "fracture_toughness": ["fracture_toughness", "断裂韧性", "KIC", "JIC"],
    "hardness": ["hardness", "硬度"],
    "conductivity": ["conductivity", "导电率", "electrical_properties"],
    "corrosion_rate": ["corrosion_rate", "腐蚀速率"],
    "pitting_potential": ["pitting_potential", "点蚀电位"],
    "passive_current_density": ["passive_current_density", "钝化电流"],
    "polarization_resistance": ["polarization_resistance", "极化电阻"],
    "figure_id": ["figure_id", "Figure → Sample", "图片类型"],
    "placeholder_index": ["placeholder_index"],
    "figure_type": ["figure_type", "图片类型"],
    "is_microstructure_image": ["is_microstructure_image", "图片类型", "microstructure_image"],
    "is_post_test_image": ["is_post_test_image", "post_test_image", "断后"],
    "caption": ["caption", "图片标题"],
    "scale_bar_info": ["scale_bar_info", "比例尺"],
    "image_purpose": ["image_purpose", "图片类型"],
}

SECTION_FIELD_MAP = [
    (r"样品识别", ["sample.sample_id", "sample.sample_name"]),
    (r"condition 筛选", ["condition.condition_id", "condition.condition_name", "condition.condition_type"]),
    (r"product_form", ["sample.product_form"]),
    (r"alloy_family", ["sample.alloy_family"]),
    (r"化学成分", ["sample.composition", "sample.composition_unit"]),
    (r"condition_id\s*/\s*condition_name|condition_name", ["condition.condition_id", "condition.condition_name"]),
    (r"condition_processing_description", ["condition.condition_processing_description"]),
    (r"condition_type", ["condition.condition_type"]),
    (r"rolling_processing", ["condition.rolling_processing"]),
    (r"solution_treatment\s*/\s*aging\s*/\s*cold_rolling", [
        "condition.solution_treatment", "condition.aging",
        "condition.cold_rolling", "condition.condition_processing_description",
    ]),
    (r"焊接/热处理/测试温度", [
        "condition.welding_process", "condition.filler_material",
        "condition.heat_treatment_condition", "condition.test_temperature",
    ]),
    (r"component_type", ["condition.component_type", "condition.joint_or_material_type"]),
    (r"magnetic_properties", [
        "property.magnetic_properties", "property.permeability", "property.saturation_magnetization",
        "property.remanence", "property.coercivity", "property.curie_temperature",
        "property.neel_temperature", "property.austenite_stability",
        "property.martensite_transformation_temperature",
    ]),
    (r"mechanical_properties", [
        "property.mechanical_properties", "property.yield_strength", "property.tensile_strength",
        "property.elongation", "property.fracture_toughness", "property.hardness",
        "property.elastic_modulus", "property.impact_77K", "property.impact_toughness",
        "property.reduction_of_area", "property.microhardness",
    ]),
    (r"electrical_properties", ["property.electrical_properties", "property.conductivity", "property.electrical_conductivity"]),
    (r"bending_performance", ["condition.bending_performance"]),
    (r"Figure\s*→\s*Sample", ["figure.figure_id", "figure.sample_id", "figure.condition_id"]),
    (r"图片类型判定|Figure\s*→\s*Sample.*图片类型", [
        "figure.figure_type", "figure.caption", "figure.is_microstructure_image",
        "figure.is_post_test_image", "figure.image_purpose",
    ]),
    (r"is_microstructure_image", [
        "figure.is_microstructure_image", "figure.is_post_test_image",
        "figure.figure_type", "figure.caption", "figure.image_purpose",
    ]),
    (r"image_purpose", ["figure.image_purpose"]),
    (r"scale_bar_info", ["figure.scale_bar_info"]),
    (r"sample_processing_overview", ["sample.sample_processing_overview", "sample.sample_microstructure_overview", "condition.microstructure"]),
    (r"placeholder_index", ["figure.placeholder_index"]),
]

def extract_prompt_text(script_text):
    m = re.search(r'JSON_SCHEMA_PROMPT\s*=\s*"""([\s\S]*?)"""', script_text)
    return m.group(1) if m else script_text

def parse_rule_sections(prompt_text):
    sections = []
    matches = list(re.finditer(r"^###\s+\d+\.?\s*(.+?)\s*$", prompt_text, re.M))
    h2_matches = list(re.finditer(r"^##\s+(.+?)\s*$", prompt_text, re.M))
    for i, match in enumerate(matches):
        start = match.end()
        next_starts = []
        if i + 1 < len(matches):
            next_starts.append(matches[i + 1].start())
        next_starts.extend(h.start() for h in h2_matches if h.start() > start)
        end = min(next_starts) if next_starts else len(prompt_text)
        title = match.group(1).strip()
        body = prompt_text[start:end].strip()
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        sections.append({"title": title, "body": "\n".join(lines)})
    return sections

def parse_schema_descriptions(prompt_text):
    descriptions = {}
    for match in re.finditer(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:\s*"([^"\n]{1,260})"', prompt_text):
        key, value = match.groups()
        if key not in descriptions:
            descriptions[key] = value
    return descriptions

def section_field_keys(title):
    keys = []
    for pattern, names in SECTION_FIELD_MAP:
        if re.search(pattern, title, re.I):
            add_keys(keys, names)
    return keys

def split_rule_lines(text, max_lines=8):
    rows = []
    deny_mode = False
    for line in text.splitlines():
        cleaned = re.sub(r"^-+\s*", "", line).strip()
        if not cleaned:
            continue
        if re.search(r"以下内容禁止|禁止填入|严禁", cleaned):
            deny_mode = True
        rows.append((cleaned, deny_mode))
        if len(rows) >= max_lines:
            break
    return rows

def build_field_rules(script_text, fields):
    prompt_text = extract_prompt_text(script_text)
    sections = parse_rule_sections(prompt_text)
    descriptions = parse_schema_descriptions(prompt_text)
    section_by_field = {}
    for section in sections:
        for key in section_field_keys(section["title"]):
            section_by_field.setdefault(key, []).append(section)
    field_rules = {}
    all_items = []
    for level, values in fields.items():
        for value in values:
            all_items.append((level, value))
    for level, field in dict.fromkeys(all_items):
        rule_key = f"{level}.{field}"
        matched_sections = section_by_field.get(rule_key, [])
        if not matched_sections:
            aliases = FIELD_ALIASES.get(field, [field])
            # Conservative fallback: only exact field names in section titles.
            matched_sections = [
                section for section in sections
                if any(alias.lower() in section["title"].lower() for alias in aliases)
            ]
        schema = descriptions.get(field, "")
        rule_parts = []
        positive_examples = []
        negative_examples = []
        note_parts = []
        if schema:
            rule_parts.append(f"字段定义：{schema}")
        for section in matched_sections[:3]:
            note_parts.append(f"来自规则：{section['title']}")
            for line, deny_mode in split_rule_lines(section["body"], max_lines=8):
                target = negative_examples if deny_mode or re.search(r"禁止|不要|不能|勿|无法|省略|不作为|不入|不要瞎猜|严禁", line) else rule_parts
                if re.search(r"例如|例：|常见格式|caption 含", line) and target is rule_parts:
                    target = positive_examples
                target.append(line)
        if not rule_parts and negative_examples:
            first = negative_examples[0]
            if not re.match(r"^(\*\*)?(严禁|禁止|不要|不能|勿|无法|省略|不作为|不入)", first):
                rule_parts.append(first)
                negative_examples = negative_examples[1:]
        if rule_parts or positive_examples or negative_examples or note_parts:
            field_rules[rule_key] = {
                "rule": "\n".join(rule_parts[:10]) or "真实脚本中未解析到专门抽取规则。",
                "positive_examples": "\n".join(positive_examples[:8]),
                "negative_examples": "\n".join(negative_examples[:8]),
                "note": "\n".join(note_parts[:6]) or "来自真实 01_extract.py 字段定义。",
                "source": "scripts/01_extract.py",
            }
    return field_rules

def sample_outputs(project_dir, limit=3):
    rows = []
    for path in sorted(glob.glob(os.path.join(project_dir, "outputs", "*", "paper.json")))[:limit]:
        paper_id = os.path.basename(os.path.dirname(path))
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        metadata = data.get("paper_metadata") or {}
        rows.append({
            "paper_id": paper_id,
            "title": metadata.get("title") or "",
            "samples": len(data.get("samples") or []),
            "conditions": len(data.get("conditions") or []),
            "figures": len(data.get("figures") or []),
        })
    return rows

def parsed_papers(project_dir, limit=300):
    rows = []
    pattern = os.path.join(project_dir, "parsed_results", "*", "paper.md")
    for path in sorted(glob.glob(pattern))[:limit]:
        paper_id = os.path.basename(os.path.dirname(path))
        rows.append({
            "paper_id": paper_id,
            "source": "parsed_results",
        })
    return rows

snapshot = {"remote_root": ROOT, "projects": {}, "mode": "read_only_snapshot"}
for project_id, name in PROJECTS.items():
    project_dir = os.path.join(ROOT, project_id)
    summary = parse_summary(project_dir)
    fields = infer_fields(project_dir)
    fields = infer_fields_from_outputs(project_dir, fields)
    script_text = ""
    script_path = os.path.join(project_dir, "scripts", "01_extract.py")
    if os.path.exists(script_path):
        script_text = open(script_path, encoding="utf-8", errors="ignore").read()
    snapshot["projects"][project_id] = {
        "name": name,
        "summary": summary,
        "fields": fields,
        "field_rules": build_field_rules(script_text, fields) if script_text else {},
        "parsed_papers": parsed_papers(project_dir),
        "sample_outputs": sample_outputs(project_dir),
        "paths": {
            "parsed_results": os.path.join(project_dir, "parsed_results"),
            "outputs": os.path.join(project_dir, "outputs"),
            "database_tables": os.path.join(project_dir, "database_tables"),
            "scripts": os.path.join(project_dir, "scripts"),
        },
    }
print(json.dumps(snapshot, ensure_ascii=False))
'''
    completed = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", SSH_TARGET, "python3", "-"],
        input=code,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "remote read-only snapshot command failed\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    return json.loads(completed.stdout)


def main() -> None:
    snapshot = run_remote_python()
    snapshot["generated_at"] = datetime.now().isoformat(timespec="seconds")
    snapshot["snapshot_version"] = "20260810_rules_scoped"
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2)
    OUT_FILE.write_text(f"window.READONLY_SNAPSHOT = {payload};\n", encoding="utf-8")
    print(f"Wrote {OUT_FILE}")
    for project_id, project in snapshot["projects"].items():
        summary = project["summary"]
        print(
            f"- {project_id}: papers={summary.get('total_papers')} "
            f"rows={summary.get('total_rows')} images={summary.get('xlsx_inserted_images')}"
        )


if __name__ == "__main__":
    main()
