"""V4 自动 fallback 抽取脚本。

策略：
1. 尝试标准版 01_extract.py（完整 schema）
2. 标准版失败 → 自动切瘦身版 01_extract_lite.py
3. 瘦身版也失败 → 记录到 failed.txt

全程无需人工介入。
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# 导入标准版和瘦身版的核心函数
# 为避免命名冲突，我们动态调用
import importlib.util


def load_extractor(script_name: str):
    """动态加载抽取脚本模块。"""
    script_path = Path(__file__).parent / script_name
    spec = importlib.util.spec_from_file_location(script_name.replace(".py", ""), script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {script_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract_one_auto(paper_id: str, *, overwrite: bool = False) -> tuple[str, str]:
    """自动 fallback 抽取单篇论文。

    Returns:
        (status, message) where status in {"success_std", "success_lite", "failed"}
    """
    PROJECT_DIR = Path(__file__).resolve().parents[1]
    OUTPUT_DIR = PROJECT_DIR / "outputs"
    out_json = OUTPUT_DIR / paper_id / "paper.json"

    if out_json.exists() and not overwrite:
        return ("success_std", "已存在，跳过")

    # 尝试标准版
    print(f"  → 尝试标准版...")
    try:
        std_module = load_extractor("01_extract.py")
        std_module.extract_one_paper(paper_id, overwrite=overwrite)
        return ("success_std", "标准版成功")
    except Exception as e_std:
        std_err = str(e_std)
        print(f"  ✗ 标准版失败: {std_err[:100]}")

        # 判断是否值得尝试瘦身版
        # JSON 截断、输出过长才有必要
        if "无法解析 LLM 输出为 JSON" in std_err or "截断" in std_err or "max_tokens" in std_err:
            print(f"  → 切换瘦身版重试...")
            try:
                lite_module = load_extractor("01_extract_lite.py")
                lite_module.extract_one(paper_id, overwrite=True)
                return ("success_lite", "瘦身版成功")
            except Exception as e_lite:
                lite_err = str(e_lite)
                print(f"  ✗ 瘦身版失败: {lite_err[:100]}")
                return ("failed", f"标准版: {std_err[:80]} | 瘦身版: {lite_err[:80]}")
        else:
            # 其他错误（400/网络/文件不存在等）瘦身版也救不了
            return ("failed", std_err[:150])


def main() -> int:
    parser = argparse.ArgumentParser(description="V4 自动 fallback 批量抽取")
    parser.add_argument("--paper-id", action="append", dest="paper_ids")
    parser.add_argument("--limit", type=int, help="从 parsed_results 按字母序取前 N 篇")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    PROJECT_DIR = Path(__file__).resolve().parents[1]
    PARSED_DIR = PROJECT_DIR / "parsed_results"

    # 确定待处理论文列表
    if args.paper_ids:
        paper_ids = args.paper_ids
    elif args.limit:
        paper_ids = sorted([d.name for d in PARSED_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")])[:args.limit]
    else:
        paper_ids = sorted([d.name for d in PARSED_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")])

    print(f"[INFO] 共 {len(paper_ids)} 篇论文待处理\n")

    success_std = 0
    success_lite = 0
    failed_list = []

    for i, pid in enumerate(paper_ids, 1):
        print(f"[{i}/{len(paper_ids)}] === {pid} ===")
        try:
            status, msg = extract_one_auto(pid, overwrite=args.overwrite)
            if status == "success_std":
                print(f"[OK] 标准版: {msg}")
                success_std += 1
            elif status == "success_lite":
                print(f"[OK] 瘦身版: {msg}")
                success_lite += 1
            else:
                print(f"[FAIL] {msg}")
                failed_list.append((pid, msg))
        except Exception as e:
            print(f"[FAIL] 未预期异常: {e}")
            traceback.print_exc()
            failed_list.append((pid, str(e)))

    print(f"\n[SUMMARY] 标准版成功: {success_std} | 瘦身版成功: {success_lite} | 失败: {len(failed_list)}")

    if failed_list:
        failed_txt = PROJECT_DIR / "failed_papers.txt"
        with open(failed_txt, "w", encoding="utf-8") as f:
            for pid, err in failed_list:
                f.write(f"{pid}\t{err}\n")
        print(f"[INFO] 失败论文清单已保存: {failed_txt}")
        for pid, err in failed_list:
            print(f"  - {pid}: {err}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
