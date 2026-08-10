#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""sigs_agree 新阈值的轻量单测。
不依赖 NCTI/STEP，只测函数本身在边界条件下的行为。
"""
import os, sys, math
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PROJ = os.path.dirname(os.path.dirname(HERE))
for _d in (REPO, PROJ, os.path.join(PROJ,"utils"), HERE):
    if _d not in sys.path: sys.path.insert(0, _d)
from check_order_assumption import sigs_agree

# 全部调用约定：ft_s, n_s, a_s, ft_n, n_n, a_n, n_verts_s=, truth_area_s=
N = (0, 0, 1)  # 单位法向

def case(name, **kw):
    expected = kw.pop("expect")
    got = sigs_agree(**kw)
    mark = "[OK]" if got == expected else "[FAIL]"
    print(f"  {mark}  {name:60}  →  {got}  (期望 {expected})")
    return got == expected

print("=== PLANE 真面积判据（n_verts ≤ 6 用 0.7 阈值）===")
all_ok = True
# 1) 矩形 PLANE 4 顶点，a_s=100, truth=100 → r=1.0 应通过
all_ok &= case("PLANE 4v a_s=100 truth=100 a_n=0.001",
               ft_s="PLANE", n_s=N, a_s=100, ft_n="PLANE", n_n=N, a_n=0.001,
               n_verts_s=4, truth_area_s=100, expect=True)
# 2) 矩形 PLANE 4 顶点，a_s=50, truth=100 → r=0.5 拒绝
all_ok &= case("PLANE 4v a_s=50 truth=100 (r=0.5 拒)",
               ft_s="PLANE", n_s=N, a_s=50, ft_n="PLANE", n_n=N, a_n=0.001,
               n_verts_s=4, truth_area_s=100, expect=False)
# 3) 矩形 PLANE 4 顶点，a_s=70, truth=100 → r=0.7 通过（边界）
all_ok &= case("PLANE 4v a_s=70 truth=100 (r=0.7 过)",
               ft_s="PLANE", n_s=N, a_s=70, ft_n="PLANE", n_n=N, a_n=0.001,
               n_verts_s=4, truth_area_s=100, expect=True)

print("\n=== PLANE 真面积判据（n_verts > 6 用 0.55 阈值）===")
# 4) 8 顶点含弧 PLANE，a_s=80, truth=100 → r=0.8 通过
all_ok &= case("PLANE 8v a_s=80 truth=100 (r=0.8 过)",
               ft_s="PLANE", n_s=N, a_s=80, ft_n="PLANE", n_n=N, a_n=0.001,
               n_verts_s=8, truth_area_s=100, expect=True)
# 5) 8 顶点含弧 PLANE，a_s=55, truth=100 → r=0.55 边界通过
all_ok &= case("PLANE 8v a_s=55 truth=100 (r=0.55 过)",
               ft_s="PLANE", n_s=N, a_s=55, ft_n="PLANE", n_n=N, a_n=0.001,
               n_verts_s=8, truth_area_s=100, expect=True)
# 6) 8 顶点含弧 PLANE，a_s=50, truth=100 → r=0.5 拒
all_ok &= case("PLANE 8v a_s=50 truth=100 (r=0.5 拒)",
               ft_s="PLANE", n_s=N, a_s=50, ft_n="PLANE", n_n=N, a_n=0.001,
               n_verts_s=8, truth_area_s=100, expect=False)
# 7) 8 顶点含弧 PLANE，a_s=30, truth=100 → r=0.3 拒
all_ok &= case("PLANE 8v a_s=30 truth=100 (r=0.3 拒)",
               ft_s="PLANE", n_s=N, a_s=30, ft_n="PLANE", n_n=N, a_n=0.001,
               n_verts_s=8, truth_area_s=100, expect=False)

print("\n=== PLANE 无 truth（fallback 旧判据）===")
# 8) 旧 fallback：a_s=1, a_n=0.8 → r=0.8 通过
all_ok &= case("PLANE fallback a_s=1 a_n=0.8 (min/max=0.8 过)",
               ft_s="PLANE", n_s=N, a_s=1, ft_n="PLANE", n_n=N, a_n=0.8,
               expect=True)
# 9) 旧 fallback：a_s=0.4, a_n=1.0 → r=0.4 拒
all_ok &= case("PLANE fallback a_s=0.4 a_n=1.0 (min/max=0.4 拒)",
               ft_s="PLANE", n_s=N, a_s=0.4, ft_n="PLANE", n_n=N, a_n=1.0,
               expect=False)

print("\n=== CYL/OTHER 反向判据 (a_n/a_s ≥ 0.2)===")
# 10) CYL 真面积 a_n=100, a_s=10 → r = 100/10 = 10 通过
all_ok &= case("CYL a_n=100 a_s=10 (r=10 过)",
               ft_s="CYL", n_s=N, a_s=10, ft_n="CYL", n_n=N, a_n=100,
               expect=True)
# 11) CYL a_n=2, a_s=100 → r = 0.02 拒（量级悬殊）
all_ok &= case("CYL a_n=2 a_s=100 (r=0.02 拒)",
               ft_s="CYL", n_s=N, a_s=100, ft_n="CYL", n_n=N, a_n=2,
               expect=False)
# 12) CYL a_n=20, a_s=100 → r = 0.2 边界通过
all_ok &= case("CYL a_n=20 a_s=100 (r=0.2 过)",
               ft_s="CYL", n_s=N, a_s=100, ft_n="CYL", n_n=N, a_n=20,
               expect=True)
# 13) CYL a_n=15, a_s=100 → r = 0.15 拒
all_ok &= case("CYL a_n=15 a_s=100 (r=0.15 拒)",
               ft_s="CYL", n_s=N, a_s=100, ft_n="CYL", n_n=N, a_n=15,
               expect=False)

print("\n=== 类型不匹配/法向不一致（应拒）===")
# 14) 类型不一致
all_ok &= case("PLANE vs CYL 类型不一致",
               ft_s="PLANE", n_s=N, a_s=100, ft_n="CYL", n_n=N, a_n=100,
               n_verts_s=4, truth_area_s=100, expect=False)
# 15) 法向夹角 30°
all_ok &= case("PLANE 法向 30° 不一致",
               ft_s="PLANE", n_s=N, a_s=100,
               ft_n="PLANE", n_n=(math.cos(math.radians(30)), math.sin(math.radians(30)), 0),
               a_n=0.001, n_verts_s=4, truth_area_s=100, expect=False)

print(f"\n{'='*60}")
print(f"  {'全部通过' if all_ok else '有失败'}")
print(f"{'='*60}")
sys.exit(0 if all_ok else 1)
