#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Standalone NCTI STEP assembly splitter.

用途：
1. 单独验证 Linux 服务器上的 NCTI 是否能导入 STEP/STP。
2. 单独验证装配体拆分是否能导出每个叶子 solid。
3. 给主盲孔流程提供一份清晰的 NCTI 拆分参考实现。

服务器运行前通常需要：

    export NCTI_CONFIG=$PWD/config/ncti_config.server.json
    export NCTI_SDK=/mnt/data/workspace/wuhongqing/tools/YanHe_GMDE_SDK_2026.1.1.2_Beta_Linux_x86-64
    export LD_LIBRARY_PATH=$NCTI_SDK
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class LeafSolid:
    """NCTI 装配树中的叶子 solid。"""

    ncti_name: Any
    path_names: list[str]


@dataclass
class SplitTarget:
    """拆分后的目标 STP。"""

    key: str
    path: Path
    source_path: Path
    was_split: bool
    solid_path_names: list[str]


def sanitize_filename_part(value: Any) -> str:
    """把 NCTI display name 转成可安全用于文件名的字符串。"""
    text = str(value).strip()
    text = re.sub(r"[<>:\"/\\|?*\x00-\x1f]+", "_", text)
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text).strip("._ ")
    return text or "unnamed"


def unique_stem(stem: str, used: set[str]) -> str:
    """避免同一个 source 下多个 solid 导出为同名文件。"""
    candidate = stem
    index = 2
    while candidate.lower() in used:
        candidate = f"{stem}_{index:03d}"
        index += 1
    used.add(candidate.lower())
    return candidate


def safe_list(value: Any) -> list[Any]:
    """NCTI 有些接口可能返回 None、单个对象或 list，这里统一成 list。"""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def init_ncti() -> Any:
    """
    初始化 NCTI。

    这里直接复用项目里的 config/config_load.py。它已经处理了：
    1. Windows DLL 和 Linux SO 的差异。
    2. Linux 下 libncti_python311.so 的真实 PyInit 模块名。
    3. NCTI.Init(init_path)。
    """
    from config.config_load import global_scope, init_ncti_config

    ncti = global_scope.get("NCTI")
    if ncti is not None:
        return ncti

    ncti = init_ncti_config()
    if ncti is None:
        raise RuntimeError("NCTI 初始化失败，请检查 NCTI_CONFIG、LD_LIBRARY_PATH 和 SDK 路径。")
    global_scope["NCTI"] = ncti
    return ncti


class NctiAssemblySplitter:
    """只负责调用 NCTI 完成 STEP/STP 装配体拆分。"""

    def __init__(self, ncti: Any):
        self.NCTI = ncti

    def load_doc(self) -> Any:
        """
        创建 NCTI Document。

        SetImportAssemelFile(1) 是装配体拆分的关键：
        它要求 NCTI 按装配结构导入文件，否则后续可能只得到一个整体对象。
        """
        doc = self.NCTI.Document()
        doc.New("OCC", "DCM", "GMSH")
        doc.SetImportAssemelFile(1)
        return doc

    def import_stp(self, doc: Any, stp_path: Path) -> None:
        """调用 NCTI 导入 STEP/STP 文件。"""
        doc.RunCommand("cmd_ncti_import_file", str(stp_path), 2)

    def display_name(self, object_api: Any, node: Any) -> str:
        """读取 NCTI 节点显示名，用于生成拆分文件名。"""
        try:
            names = object_api.GetDisplayName(node)
            if isinstance(names, (list, tuple)) and names:
                return sanitize_filename_part(names[0])
            if names:
                return sanitize_filename_part(names)
        except Exception:
            pass
        return sanitize_filename_part(node)

    def child_groups(self, group_api: Any, node: Any | None = None) -> list[Any]:
        """获取当前 group 下的子 group。node=None 时获取根 group。"""
        try:
            if node is None:
                return safe_list(group_api.GetCurSubGroup())
            return safe_list(group_api.GetCurSubGroup(node))
        except Exception:
            return []

    def child_solids(self, group_api: Any, node: Any) -> list[Any]:
        """获取当前 group 下直接挂载的 solid object。"""
        try:
            return safe_list(group_api.GetCurSubObject(node))
        except Exception:
            return []

    def collect_leaf_solids(
        self,
        group_api: Any,
        object_api: Any,
        root_nodes: list[Any],
    ) -> tuple[list[LeafSolid], bool]:
        """
        递归遍历装配树，收集叶子 solid。

        返回：
        - leaves: 每个可导出的 leaf solid。
        - saw_branch: 是否看到过装配分支。用于判断单 solid 是否需要拆分。
        """
        leaves: list[LeafSolid] = []
        saw_branch = len(root_nodes) > 1
        include_root_name = len(root_nodes) > 1

        def walk(node: Any, path_names: list[str]) -> None:
            nonlocal saw_branch

            sub_groups = self.child_groups(group_api, node)
            solids = self.child_solids(group_api, node)

            # 如果一个节点下面有多个子 group 或 solid，说明这是装配分支。
            if len(sub_groups) + len(solids) > 1:
                saw_branch = True

            # 当前 group 下的 solid 视为叶子 solid，可以单独导出。
            for solid in solids:
                solid_name = self.display_name(object_api, solid)
                leaves.append(LeafSolid(solid, path_names + [solid_name]))

            # 继续向下遍历子 group。
            for child_group in sub_groups:
                child_name = self.display_name(object_api, child_group)
                walk(child_group, path_names + [child_name])

        for root in root_nodes:
            root_path = [self.display_name(object_api, root)] if include_root_name else []
            walk(root, root_path)

        return leaves, saw_branch

    def export_solid(self, doc: Any, output_path: Path, solid_name: Any) -> None:
        """
        导出单个 leaf solid 为 STP 文件。

        不同版本 NCTI 对 solid_name 参数接受形式可能略有差异，
        所以这里先传单个对象，失败后再尝试 list 包裹。
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            doc.RunCommand("cmd_ncti_export_file", str(output_path), solid_name)
        except Exception:
            doc.RunCommand("cmd_ncti_export_file", str(output_path), [solid_name])

        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise RuntimeError(f"NCTI 导出失败或文件为空: {output_path}")

    def split_one_stp(self, stp_path: Path, output_dir: Path) -> list[SplitTarget]:
        """
        拆分单个 STEP/STP。

        如果导入后只有一个 leaf solid 且没有装配分支，则不额外导出，
        直接返回原始 STP 作为 target。
        """
        used_stems: set[str] = set()
        doc = self.load_doc()
        try:
            self.import_stp(doc, stp_path)

            group_api = self.NCTI.RootGroup(doc)
            object_api = self.NCTI.Object(doc)
            root_nodes = self.child_groups(group_api)
            if not root_nodes:
                raise RuntimeError("NCTI 导入后没有得到 root group")

            leaves, saw_branch = self.collect_leaf_solids(group_api, object_api, root_nodes)
            if not leaves:
                raise RuntimeError("NCTI 导入后没有得到 leaf solid")

            source_stem = sanitize_filename_part(stp_path.stem)

            # 单 solid 非装配体：不制造额外 STP 文件，直接使用原始文件。
            if len(leaves) == 1 and not saw_branch:
                key = unique_stem(source_stem, used_stems)
                return [
                    SplitTarget(
                        key=key,
                        path=stp_path,
                        source_path=stp_path,
                        was_split=False,
                        solid_path_names=leaves[0].path_names,
                    )
                ]

            targets: list[SplitTarget] = []
            for leaf in leaves:
                raw_stem = f"{source_stem}__{'_'.join(leaf.path_names)}"
                output_stem = unique_stem(sanitize_filename_part(raw_stem), used_stems)
                output_path = output_dir / f"{output_stem}.stp"
                self.export_solid(doc, output_path, leaf.ncti_name)
                targets.append(
                    SplitTarget(
                        key=output_stem,
                        path=output_path,
                        source_path=stp_path,
                        was_split=True,
                        solid_path_names=leaf.path_names,
                    )
                )
            return targets
        finally:
            # 主动释放 NCTI Document，避免批量处理时内存持续增长。
            try:
                doc.Delete()
            except Exception:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standalone NCTI STEP/STP assembly splitter.")
    parser.add_argument("stp_path", type=Path, help="需要拆分的 STEP/STP 文件。")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="拆分 STP 输出目录。默认与输入文件同目录。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stp_path = args.stp_path.resolve()
    output_dir = (args.output_dir or stp_path.parent).resolve()
    if not stp_path.is_file():
        raise SystemExit(f"输入 STP 不存在: {stp_path}")

    ncti = init_ncti()
    splitter = NctiAssemblySplitter(ncti)
    targets = splitter.split_one_stp(stp_path, output_dir)

    print(f"[done] source={stp_path} targets={len(targets)} output_dir={output_dir}")
    for index, target in enumerate(targets, 1):
        print(
            f"[target] {index}/{len(targets)} "
            f"was_split={target.was_split} path={target.path} "
            f"solid_path={'/'.join(target.solid_path_names)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
