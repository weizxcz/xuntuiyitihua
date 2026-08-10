# -*- coding: utf-8 -*-
"""
调试 NCTI 解析面数 vs label 面数不一致的工具脚本
==================================================
目的：单步追查 NCTI 到底在哪一步把面"拆多"了。
样例：00026.stp —— NCTI 解析 38 面，label 标注 37 面，差 1。

【运行前置——必须先设新版 SDK 环境变量，否则 NCTI 报 undefined symbol】
   export LD_LIBRARY_PATH=/softwares/YanHe_GMDE_SDK_2026.2.0_Linux_x86-64_Community:$LD_LIBRARY_PATH
   如果用 IDE 的 Debug，把上面这行加进 IDE 的 Run Configuration / 环境变量里。
   并在项目根目录 /workspace/Geo-Rec 下运行（脚本依赖 src 包）。

【断点打法】
   ★ 最关键的断点打在下面 [BREAKPOINT-B] 那一行：
       ai_data_info = NCTI.AiModel(doc, "testbox")
     —— 面数就是在这行产生的。执行前 doc 里只有刚导入的 STEP，
        执行后 ai_data_info.FaceID 就是 NCTI 识别出的全部面（本例 38 个）。
        在断点处展开 ai_data_info，逐面看 FaceID / FaceAttr / FacePoints。
"""
import json
import numpy as np

from src.utils.base_functions import init_ncti

# ===================== 配置区（改这里换样本）=====================
STEP_FILE  = "/mnt/data/geometry_data/steps/step_files/00026.stp"
LABEL_FILE = "/data/data2/processed_data/2026-06-15_true_blind_hole/labels/00026.json"
# ================================================================


def debug_one_step():
    # ---------- 1) 初始化 NCTI ----------
    NCTI = init_ncti()
    assert NCTI is not None, "NCTI 初始化失败，检查 LD_LIBRARY_PATH 是否指向新版 SDK"

    # ---------- 2) 复刻 AAGGraphExtraToolNcti.import_step_get_info ----------
    #    对应 src/utils/step2graph_tools_ncti.py 第 19~24 行
    doc = NCTI.Document()
    doc.New("OCC", "DCM", 0)
    doc.RunCommand("cmd_ncti_import_file", str(STEP_FILE), "testbox")  # [BREAKPOINT-A] STEP 导入完成，可看 doc
    ai_data_info = NCTI.AiModel(doc, "testbox")                        # 面数在这行产生！

    # ---------- 3) 取面相关属性（都按面组织，长度 = 面数）----------
    FaceID     = ai_data_info.FaceID      # 面ID列表
    FaceAttr   = ai_data_info.FaceAttr    # [N, 12] 面属性
    FacePoints = ai_data_info.FacePoints  # [N, 75] 每面 25 点 × 3
    print(f"\nNCTI 面数 = {len(FaceID)}")
    print(f"FaceID = {FaceID}")

    # ---------- 4) 与 label 对比 ----------
    seg = json.load(open(LABEL_FILE))[0][1]['seg']
    print(f"label 面数 = {len(seg)}")
    print(f"差 = NCTI({len(FaceID)}) - label({len(seg)}) = {len(FaceID) - len(seg)}")

    # ---------- 5) 逐面打印属性 ----------
    attr = np.array(FaceAttr)
    for i, fid in enumerate(FaceID):
        print(f"  面idx={i:2d} FaceID={fid:3d}: {np.round(attr[i], 3)}")

    # ---------- 6) 几何共面检测：找疑似被 NCTI 拆开的面对 ----------
    #    思路：同一张面被拆成两块 → 两块法向平行且落在同一平面
    geom = []
    for p in FacePoints:
        P = np.array(p).reshape(-1, 3)
        c = P.mean(0)
        _, _, Vt = np.linalg.svd(P - c)   # 最小奇异值方向 = 平面法向
        n = Vt[2]
        d = -(n @ c)
        geom.append((n, d, c))
    print("\n=== 共面对（法向平行且同平面 → 疑似 NCTI 把 1 个面拆成 2 个）===")
    for i in range(len(geom)):
        for j in range(i + 1, len(geom)):
            ni, di, ci = geom[i]
            nj, dj, _ = geom[j]
            if abs(abs(ni @ nj) - 1) < 0.02 and abs(nj @ ci + dj) < 0.08:
                print(f"  FaceID {FaceID[i]}  ≈  FaceID {FaceID[j]}")

    doc.Delete()


if __name__ == "__main__":
    debug_one_step()
