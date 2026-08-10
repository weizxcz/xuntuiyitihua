#!/usr/bin/env python3
"""生成训练 test 集文件列表，与 train.py 的 train_test_split(random_state=42) 保持一致。"""
import os, json
import sys
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FEATFOX_ROOT = os.path.dirname(THIS_DIR)
if FEATFOX_ROOT not in sys.path:
    sys.path.insert(0, FEATFOX_ROOT)
from sklearn.model_selection import train_test_split
from featurefox.lib._env import get_steps_dir

STEPS_DIR = get_steps_dir()
OUT = os.path.join(THIS_DIR, "test_names.json")

files = sorted(f for f in os.listdir(STEPS_DIR) if f.endswith(".step"))
names = sorted(set(os.path.splitext(f)[0] for f in files))
train_names, test_names = train_test_split(names, test_size=0.2, random_state=42)
print(f"总零件: {len(names)}, Train: {len(train_names)}, Test: {len(test_names)}")
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(sorted(test_names), f, ensure_ascii=False)
print(f"Test 集已保存: {OUT}")
