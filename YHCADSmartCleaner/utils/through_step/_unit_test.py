#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""构造一个已知面积的 STEP 文件，看 NCTI attr[5] 给什么。"""
import os, sys, math
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PROJ = os.path.dirname(os.path.dirname(HERE))
for _d in (REPO, PROJ, os.path.join(PROJ,"utils"), HERE):
    if _d not in sys.path: sys.path.insert(0, _d)

def init_ncti():
    sdk = os.path.join(PROJ, "SDK")
    if sdk not in sys.path: sys.path.insert(0, sdk)
    try: os.add_dll_directory(sdk); os.add_dll_directory(os.path.join(sdk,"OCC"))
    except: pass
    import ctypes
    for dll in ["ncti_command.dll","ncti_occ_plugin.dll","ncti_doc_occ.dll","ncti_render_vulkan.dll","ncti_window.dll"]:
        p=os.path.join(sdk,dll);
        if os.path.exists(p): ctypes.CDLL(p)
    import ncti_python; ncti_python.Init(sdk); return ncti_python

def make_box(L, W, H, name="testbox"):
    """构造一个 L×W×H 长方体（以原点为中心），导成临时 STEP。"""
    import tempfile
    # 手工 STEP：8 个顶点 + 6 个 PLANE 面
    # 用 OpenCascade python (OCC) 不一定有，但 NCTI 自带 OCC
    # 改用更简单：写一个 STEP 含一个 PLANE，L×W 方形
    step = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('test'),'2;1');
FILE_NAME('test.step','2024-01-01',('test'),('test'),'test','test','');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));
ENDSEC;
DATA;
#1 = CARTESIAN_POINT('',(0.,0.,0.));
#2 = CARTESIAN_POINT('',(LL,0.,0.));
#3 = CARTESIAN_POINT('',(LL,WW,0.));
#4 = CARTESIAN_POINT('',(0.,WW,0.));
#5 = DIRECTION('',(0.,0.,1.));
#6 = AXIS2_PLACEMENT_3D('',#1,#5,#2);
#7 = PLANE('',#6);
#8 = ORIENTED_EDGE('',*,*,#9,.T.);
#9 = EDGE_CURVE('',#10,#11,#12,.T.);
#10 = VERTEX_POINT('',#1);
#11 = VERTEX_POINT('',#2);
#12 = LINE('',#1,#2);
#13 = ORIENTED_EDGE('',*,*,#14,.T.);
#14 = EDGE_CURVE('',#11,#15,#16,.T.);
#15 = VERTEX_POINT('',#3);
#16 = LINE('',#2,#3);
#17 = ORIENTED_EDGE('',*,*,#18,.T.);
#18 = EDGE_CURVE('',#15,#19,#20,.T.);
#19 = VERTEX_POINT('',#4);
#20 = LINE('',#3,#4);
#21 = ORIENTED_EDGE('',*,*,#22,.T.);
#22 = EDGE_CURVE('',#19,#10,#23,.T.);
#23 = LINE('',#4,#1);
#24 = EDGE_LOOP('',(#8,#13,#17,#21));
#25 = FACE_OUTER_BOUND('',#24,.T.);
#26 = ADVANCED_FACE('',(#25),#7,.T.);
ENDSEC;
END-ISO-10303-21;
""".replace("LL", str(L)).replace("WW", str(W))
    p = os.path.join(tempfile.gettempdir(), name+".step")
    open(p, "w").write(step)
    return p

def main():
    ncti = init_ncti()
    for L, W in [(1000., 1000.), (100., 100.), (10., 10.), (1., 1.)]:
        name = f"_unit_{int(L)}x{int(W)}"
        p = make_box(L, W, 0.0, name)
        doc = ncti.Document(); doc.New("OCC","DCM",0)
        ok = doc.RunCommand("cmd_ncti_import_file", str(p), name)
        if not ok: print(f"  {L}×{W}: import failed"); continue
        ai = ncti.AiModel(doc, name)
        for i in range(len(ai.FaceID)):
            attr = ai.FaceAttr[i]
            ftype = "PLANE" if attr[0]==1.0 else ("CYL" if attr[1]==1.0 else "OTHER")
            area = float(attr[5])
            true_mm2 = L * W
            print(f"  {L}×{W}  true_area={true_mm2:>10.1f} mm²  attr[5]={area:>12.6f}  ratio mm²/attr={true_mm2/area if area>0 else 'inf':>10.3f}  ftype={ftype}")
        try: doc.Clear()
        except: pass
    os._exit(0)

if __name__=="__main__": main()
