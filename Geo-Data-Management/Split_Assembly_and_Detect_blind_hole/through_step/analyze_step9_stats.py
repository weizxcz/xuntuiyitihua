"""最终统计分析：双侧通槽台阶(2-sided_through_step, seg=9)的完整规则提取"""
import re, os, json, glob, math
from collections import Counter

step_dir = "D:/wyg/data/data/通槽/steps"
label_dir = "D:/wyg/data/data/通槽/label"

def parse_step(content):
    plane_pat = re.compile(r'#(\d+)\s*=\s*PLANE\s*\([^,]*,\s*#(\d+)\)', re.MULTILINE)
    dir_pat = re.compile(r'#(\d+)\s*=\s*DIRECTION\s*\([^,]*,\s*\(([^)]*)\)\)', re.MULTILINE)
    axis2_pat = re.compile(r'#(\d+)\s*=\s*AXIS2_PLACEMENT_3D\s*\([^,]*,\s*#(\d+)\s*,\s*#(\d+)\s*,\s*#(\d+)\)', re.MULTILINE)
    point_pat = re.compile(r'#(\d+)\s*=\s*CARTESIAN_POINT\s*\([^,]*,\s*\(([^)]*)\)\)', re.MULTILINE)
    ec_pat = re.compile(r'#(\d+)\s*=\s*EDGE_CURVE\s*\([^,]*,\s*#(\d+)\s*,\s*#(\d+)\s*,\s*#(\d+)', re.MULTILINE)
    fb_pat = re.compile(r'#(\d+)\s*=\s*FACE_BOUND\s*\([^,]*,\s*#(\d+)', re.MULTILINE)
    el_pat = re.compile(r'#(\d+)\s*=\s*EDGE_LOOP\s*\([^,]*,\s*\(([^)]*)\)', re.MULTILINE)
    oe_pat = re.compile(r'#(\d+)\s*=\s*ORIENTED_EDGE\s*\([^,]*,\s*\*\s*,\s*\*\s*,\s*#(\d+)', re.MULTILINE)
    sc_pat = re.compile(r'#(\d+)\s*=\s*SURFACE_CURVE\s*\([^,]*,\s*#(\d+)', re.MULTILINE)
    line_pat = re.compile(r'#(\d+)\s*=\s*LINE\b', re.MULTILINE)
    circle_pat = re.compile(r'#(\d+)\s*=\s*CIRCLE\b', re.MULTILINE)
    cyl_pat = re.compile(r'#(\d+)\s*=\s*CYLINDRICAL_SURFACE\s*\([^,]*,\s*#(\d+)', re.MULTILINE)

    surface_refs = {}
    for m in plane_pat.finditer(content):
        surface_refs[int(m.group(1))] = ("PLANE", int(m.group(2)))
    for m in cyl_pat.finditer(content):
        surface_refs[int(m.group(1))] = ("CYL", int(m.group(2)))

    dirs = {}
    for m in dir_pat.finditer(content):
        dirs[int(m.group(1))] = [float(x.strip()) for x in m.group(2).split(",")]

    axis2 = {}
    for m in axis2_pat.finditer(content):
        axis2[int(m.group(1))] = int(m.group(3))

    points = {}
    for m in point_pat.finditer(content):
        points[int(m.group(1))] = [float(x.strip()) for x in m.group(2).split(",")]

    edge_curves = {}
    for m in ec_pat.finditer(content):
        edge_curves[int(m.group(1))] = (int(m.group(2)), int(m.group(3)))

    face_bounds = {}
    for m in fb_pat.finditer(content):
        face_bounds[int(m.group(1))] = int(m.group(2))

    edge_loops = {}
    for m in el_pat.finditer(content):
        refs = [int(x.strip().lstrip("#")) for x in m.group(2).split(",") if x.strip()]
        edge_loops[int(m.group(1))] = refs

    oriented_edges = {}
    for m in oe_pat.finditer(content):
        oriented_edges[int(m.group(1))] = int(m.group(2))

    sc_map = {}
    for m in sc_pat.finditer(content):
        sc_map[int(m.group(1))] = int(m.group(2))

    line_set = set()
    for m in line_pat.finditer(content):
        line_set.add(int(m.group(1)))
    circle_set = set()
    for m in circle_pat.finditer(content):
        circle_set.add(int(m.group(1)))

    return surface_refs, dirs, axis2, points, edge_curves, face_bounds, edge_loops, oriented_edges, sc_map, line_set, circle_set


face_pat = re.compile(r'#(\d+)\s*=\s*ADVANCED_FACE\s*\([^)]*,\s*\(([^)]*)\),\s*#(\d+),\s*\.([TF])\.', re.MULTILINE)


def get_face_edges(bounds_str, face_bounds, edge_loops, oriented_edges):
    bound_refs = [int(x.strip().lstrip("#")) for x in bounds_str.split(",") if x.strip()]
    ec_refs = set()
    for bref in bound_refs:
        lref = face_bounds.get(bref)
        if lref is None:
            continue
        for oe_ref in edge_loops.get(lref, []):
            ec_ref = oriented_edges.get(oe_ref)
            if ec_ref is not None:
                ec_refs.add(ec_ref)
    return ec_refs


def get_normal(sref, surface_refs, axis2, dirs):
    info = surface_refs.get(sref)
    if not info or info[0] != "PLANE":
        return None
    dref = axis2.get(info[1])
    return dirs.get(dref) if dref else None


files = sorted(glob.glob(os.path.join(label_dir, "*.json")))[:1000]

# === Final stats ===
total_valid = 0
face_count_dist = Counter()
surface_type_dist = Counter()
edge_count_dist = Counter()
edge_type_dist = Counter()
angle_pattern_dist = Counter()  # triplet type
bottom_vs_role = Counter()  # bottom标记 vs 几何角色
is_connected_subgraph = Counter()  # step9面是否形成连通子图
instance_count_dist = Counter()  # 单个模型中有几个通槽实例

for json_file in files:
    sample_name = os.path.splitext(os.path.basename(json_file))[0]
    step_file = os.path.join(step_dir, sample_name + ".step")
    if not os.path.exists(step_file):
        continue
    with open(json_file, "r") as f:
        data = json.load(f)
    seg = data[0][1]["seg"]
    bottom = data[0][1].get("bottom", {})
    inst = data[0][1]["inst"]
    step9_ids = sorted(int(k) for k, v in seg.items() if v == 9)
    step9_set = set(step9_ids)

    with open(step_file, "r", errors="replace") as f:
        content = f.read()

    surface_refs, dirs, axis2, points, edge_curves, face_bounds, edge_loops, oriented_edges, sc_map, line_set, circle_set = parse_step(content)

    faces_ordered = []
    for m in face_pat.finditer(content):
        sref = int(m.group(3))
        stype = surface_refs.get(sref, ("UNKNOWN",))[0]
        normal = get_normal(sref, surface_refs, axis2, dirs)
        edges = get_face_edges(m.group(2), face_bounds, edge_loops, oriented_edges)
        faces_ordered.append({"stype": stype, "normal": normal, "edges": edges})

    if len(faces_ordered) != len(seg):
        continue
    total_valid += 1

    face_count_dist[len(step9_ids)] += 1

    for idx in step9_ids:
        surface_type_dist[faces_ordered[idx]["stype"]] += 1
        n_e = len(faces_ordered[idx]["edges"])
        edge_count_dist[n_e] += 1

    # Analyze each "instance" of step9 faces (using inst matrix grouping)
    # Find connected components among step9 faces via shared edges
    visited = set()
    n_instances = 0
    instance_face_counts = []

    for start in step9_ids:
        if start in visited:
            continue
        n_instances += 1
        # BFS
        queue = [start]
        component = set()
        while queue:
            cur = queue.pop(0)
            if cur in visited or cur not in step9_set:
                continue
            visited.add(cur)
            component.add(cur)
            # Find step9 neighbors via shared edge
            for other in step9_ids:
                if other not in visited and faces_ordered[cur]["edges"] & faces_ordered[other]["edges"]:
                    queue.append(other)
        instance_face_counts.append(len(component))
        # Analyze each instance
        comp_list = sorted(component)

        # Angle pattern within instance
        normals_list = [(i, faces_ordered[i]["normal"]) for i in comp_list if faces_ordered[i]["normal"]]
        labels = []
        for i in range(len(normals_list)):
            for j in range(i+1, len(normals_list)):
                n1 = normals_list[i][1]
                n2 = normals_list[j][1]
                dot = abs(sum(a*b for a,b in zip(n1, n2)))
                dot = max(-1.0, min(1.0, dot))
                angle = math.degrees(math.acos(dot))
                if angle < 10:
                    labels.append("P")
                elif 80 <= angle <= 100:
                    labels.append("V")
                else:
                    labels.append("O")
        triplet = "".join(sorted(labels)) if labels else "EMPTY"
        angle_pattern_dist[triplet] += 1

        # Bottom vs role for 3-face instances
        if len(comp_list) == 3 and len(normals_list) == 3:
            # Find which pair is most parallel
            best_dot = 0
            best_pair = None
            for i in range(3):
                for j in range(i+1, 3):
                    dot = abs(sum(a*b for a,b in zip(normals_list[i][1], normals_list[j][1])))
                    if dot > best_dot:
                        best_dot = dot
                        best_pair = (i, j)
            if best_pair:
                k_idx = normals_list[3 - best_pair[0] - best_pair[1]][0]
                pa_idx = normals_list[best_pair[0]][0]
                pb_idx = normals_list[best_pair[1]][0]
                np_bottom = bottom.get(str(k_idx), 0)
                is_parallel = best_dot > 0.95
                pa_bottom_val = bottom.get(str(pa_idx), 0)
                pb_bottom_val = bottom.get(str(pb_idx), 0)
                role = "par_pair_({},{})_nonpar_{}".format(pa_bottom_val, pb_bottom_val, np_bottom)
                if is_parallel:
                    bottom_vs_role["parallel_pair_exists"] += 1
                    if np_bottom == 1:
                        bottom_vs_role["nonpar_is_bottom"] += 1
                    else:
                        bottom_vs_role["nonpar_NOT_bottom"] += 1
                else:
                    bottom_vs_role["no_strict_parallel"] += 1
                    if np_bottom == 1:
                        bottom_vs_role["no_par_nonpar_is_bottom"] += 1

    instance_count_dist[n_instances] += 1

    # Check step9 faces form connected subgraph
    if n_instances == 1 and len(step9_ids) == len(visited):
        is_connected_subgraph["fully_connected"] += 1
    else:
        is_connected_subgraph["disconnected_or_partial"] += 1


print("=" * 60)
print("双侧通槽台阶(2-sided_through_step, seg=9) 统计报告")
print("=" * 60)
print("有效样本数: {}".format(total_valid))

print("\n--- 1. 每个样本中通槽面数量 ---")
for k in sorted(face_count_dist.keys()):
    print("  {} 面: {} 样本".format(k, face_count_dist[k]))

print("\n--- 2. 通槽面曲面类型 ---")
for k in sorted(surface_type_dist.keys(), key=lambda x: surface_type_dist[x], reverse=True):
    print("  {}: {}".format(k, surface_type_dist[k]))

print("\n--- 3. 通槽面边数分布 ---")
for k in sorted(edge_count_dist.keys()):
    if edge_count_dist[k] >= 5:
        print("  {} 条边: {} 面".format(k, edge_count_dist[k]))

print("\n--- 4. 每个样本中通槽实例数(连通分量) ---")
for k in sorted(instance_count_dist.keys()):
    print("  {} 个实例: {} 样本".format(k, instance_count_dist[k]))

print("\n--- 5. 实例内法向量角度模式 ---")
print("  P=平行(<10deg), V=垂直(80-100deg), O=其他")
for k in sorted(angle_pattern_dist.keys(), key=lambda x: angle_pattern_dist[x], reverse=True)[:15]:
    print("  {}: {} 实例".format(k, angle_pattern_dist[k]))

print("\n--- 6. 3面实例中底面标记与平行对关系 ---")
for k in sorted(bottom_vs_role.keys(), key=lambda x: bottom_vs_role[x], reverse=True):
    print("  {}: {}".format(k, bottom_vs_role[k]))

print("\n--- 7. 通槽面连通性 ---")
for k in sorted(is_connected_subgraph.keys(), key=lambda x: is_connected_subgraph[x], reverse=True):
    print("  {}: {}".format(k, is_connected_subgraph[k]))
