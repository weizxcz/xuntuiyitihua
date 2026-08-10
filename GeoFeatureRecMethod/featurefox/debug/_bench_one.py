# -*- coding: utf-8 -*-
"""单文件分阶段耗时实测（STEP-parser 版本）。"""
import time, sys, os

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FEATFOX_ROOT = os.path.dirname(os.path.dirname(THIS_DIR))
if FEATFOX_ROOT not in sys.path:
    sys.path.insert(0, FEATFOX_ROOT)
from featurefox.lib._env import get_project_root
PROJECT_ROOT = get_project_root()
if PROJECT_ROOT is None:
    PROJECT_ROOT = os.path.join(os.path.dirname(FEATFOX_ROOT), "YHCADSmartCleaner")
UTILS_DIR = os.path.join(PROJECT_ROOT, "utils")
TS_DIR = os.path.join(UTILS_DIR, "through_step")
for p in (PROJECT_ROOT, UTILS_DIR, TS_DIR, FEATFOX_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from detect_blind_holes_and_export_stp_v15_22 import StepParser
sys.path.insert(0, os.path.join(TS_DIR, "featurefox"))
from edge_features import build_face_graph
from predict import load_models, load_instance_models, predict_through_slots
from featurefox.lib._env import get_steps_dir

DEFAULT_STEP = os.path.join(get_steps_dir(), "20221121_154647_101.step")
STEP = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_STEP
print("文件: %.1f KB / %d 行" % (os.path.getsize(STEP)/1024,
      sum(1 for _ in open(STEP, encoding="utf-8", errors="ignore"))))

def med(xs):
    s = sorted(xs); n = len(s)
    return s[n//2] if n % 2 else (s[n//2-1]+s[n//2])/2

# ① 正则解析（5 次，排除冷启动）
ts = []
for _ in range(5):
    p = StepParser(STEP); t0 = time.perf_counter(); p.parse()
    ts.append((time.perf_counter()-t0)*1000)
print("① StepParser.parse  : 中位 %.1f ms  (%d 实体 / %d 面)  各次=%s"
      % (med(ts), len(p.entities), len(p.advanced_faces), [round(x,1) for x in ts]))

# ② 边特征提取 / AAG 构建（复用同一 parser，5 次）
ts = []
for _ in range(5):
    t0 = time.perf_counter(); edges, fa = build_face_graph(p)
    ts.append((time.perf_counter()-t0)*1000)
print("② build_face_graph  : 中位 %.1f ms  (%d 条边)  各次=%s"
      % (med(ts), len(edges), [round(x,1) for x in ts]))

# ③ 模型加载（一次性）
t0 = time.perf_counter()
booster, calib = load_models(); ib, ic = load_instance_models()
print("③ 模型加载(一次)    : %.0f ms" % ((time.perf_counter()-t0)*1000))

# ④ 预测全流程（含内部 parse+build+两级推理，3 次）
ts = []
for _ in range(3):
    t0 = time.perf_counter()
    insts = predict_through_slots(STEP, booster, calib, inst_booster=ib, inst_calibrator=ic)
    ts.append((time.perf_counter()-t0)*1000)
print("④ predict 全流程    : 中位 %.1f ms  (检出 %d 个通槽)  各次=%s"
      % (med(ts), len(insts), [round(x,1) for x in ts]))
print("   → 其中纯模型推理 ≈ ④ - ① - ②")
