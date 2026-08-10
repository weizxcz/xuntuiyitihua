#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""纯法向位置一致性检查（单位无关、不过 oracle）。

判据：同位置 k，STEP 面法向 与 NCTI 位置 k 法向 是否同向 (abs dot > cos20°)。
法向是单位无关、两侧采样一致的强不变量 —— 直接证/伪「声明顺序==位置顺序」，
不经过重心最近邻 oracle（避免面积单位差异/重心定义差异干扰）。

main 用子进程分 chunk 调本脚本 --worker。
"""
import os, sys, math, glob, pickle, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
UTILS_DIR = os.path.join(PROJECT_ROOT, "utils")
for _d in (PROJECT_ROOT, UTILS_DIR, HERE):
    if _d not in sys.path: sys.path.insert(0, _d)

def init_ncti(project_root=PROJECT_ROOT):
    sdk = os.path.join(project_root, "SDK")
    if sdk not in sys.path: sys.path.insert(0, sdk)
    try: os.add_dll_directory(sdk); os.add_dll_directory(os.path.join(sdk,"OCC"))
    except Exception: pass
    import ctypes
    for dll in ["ncti_command.dll","ncti_occ_plugin.dll","ncti_doc_occ.dll","ncti_render_vulkan.dll","ncti_window.dll"]:
        p=os.path.join(sdk,dll)
        if os.path.exists(p): ctypes.CDLL(p)
    import ncti_python; ncti_python.Init(sdk); return ncti_python

def _pt(p):
    try: return (float(p.X),float(p.Y),float(p.Z))
    except: return (float(p[0]),float(p[1]),float(p[2]))

def worker(chunk_pkl, out_pkl, conv):
    from detect_blind_holes_and_export_stp_v15_22 import StepParser
    from featurefox.edge_features import FaceAttrs
    from geom_helpers import _dot
    paths=pickle.load(open(chunk_pkl,"rb"))
    ncti=init_ncti()
    TH=math.cos(math.radians(20.0))
    out=[]
    for p in paths:
        try:
            parser=StepParser(p); parser.parse(); order=list(parser.advanced_faces.keys()); fa=FaceAttrs(parser)
            doc=ncti.Document()
            doc.New("OCC","DCM",0) if conv=="A" else doc.New("OCC","DCM","GMSH")
            if not doc.RunCommand("cmd_ncti_import_file",str(p),"testbox"): out.append({"path":p,"error":"import"}); continue
            ai=ncti.AiModel(doc,"testbox"); n=len(ai.FaceID)
            if n!=len(order): out.append({"path":p,"error":"count",**{"n_step":len(order),"n_ncti":n}});
            else:
                pres=viol=0; bad=[]
                for k,fid in enumerate(order):
                    ns=fa.normal(fid); nn=None
                    try:
                        v=doc.GetNormalByUV("testbox",k,0.5,0.5); nn=_pt(v) if v is not None else None
                    except: pass
                    if ns and nn:
                        if abs(_dot(ns,nn))<TH: viol+=1; bad.append(k)
                        else: pres+=1
                out.append({"path":p,"pres":pres,"viol":viol,"bad":bad})
            try: doc.Clear()
            except: pass
        except Exception as e:
            out.append({"path":p,"error":repr(e)[:80]})
        tmp=out_pkl+".tmp"; pickle.dump(out,open(tmp,"wb")); os.replace(tmp,out_pkl)
    os._exit(0)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--worker",nargs=2,metavar=("CHUNK","OUT"))
    ap.add_argument("--n",type=int,default=200)
    ap.add_argument("--chunk",type=int,default=15)
    ap.add_argument("--conv",default="A")
    args=ap.parse_args()
    if args.worker: worker(args.worker[0],args.worker[1],args.conv); return
    import subprocess,tempfile
    files=sorted(glob.glob(r"D:/wyg/data/data/steps/*.step"))[:args.n]
    chunks=[files[i:i+args.chunk] for i in range(0,len(files),args.chunk)]
    PY=r"D:/Anaconda3/envs/yhcad_py312/python.exe"
    R=[]
    for ci,ch in enumerate(chunks):
        cf=os.path.join(tempfile.gettempdir(),"_npc_chunk_%d.pkl"%ci)
        of=os.path.join(tempfile.gettempdir(),"_npc_out_%d.pkl"%ci)
        pickle.dump(ch,open(cf,"wb"))
        if os.path.exists(of): os.remove(of)
        subprocess.run([PY,os.path.abspath(__file__),"--worker",cf,of,"--conv",args.conv],check=False,timeout=900)
        if os.path.exists(of):
            try: R.extend(pickle.load(open(of,"rb")))
            except: pass
        print("chunk %d/%d done, total=%d"%(ci+1,len(chunks),len(R)))
    ok=[r for r in R if "error" not in r]
    cnt=[r for r in R if r.get("error")=="count"]
    pres=sum(r["pres"] for r in ok); viol=sum(r["viol"] for r in ok)
    bf=[r for r in ok if r["viol"]>0]
    print("="*60)
    print("纯法向位置一致性（声明位k == 位置k 的法向同向率，不过oracle）")
    print("="*60)
    print("文件: 成功{}  count不匹配{}  违反率(位置对): {:.3%}  (pres={} viol={})".format(
        len(ok),len(cnt),viol/(pres+viol) if pres+viol else 0,pres,viol))
    print("含法向违反文件: {}/{} = {:.1%}".format(len(bf),len(ok),len(bf)/len(ok) if ok else 0))
    print("count不匹配示例:",[(os.path.basename(r["path"]),r["n_step"],r["n_ncti"]) for r in cnt[:5]])

if __name__=="__main__": main()
