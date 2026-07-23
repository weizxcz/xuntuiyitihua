"""预标注中间层。

UI（label_tab.py）只调用本模块的函数；后续接入识别算法时，
只需修改本模块内部实现，UI 侧无需改动，从而与底层算法解耦。

模型前向计算通过 ai.ai_recognizer.infer_via_subprocess 交给独立子进程
（yhcad_env）完成，参见 ai/infer_client.py、ai/infer_worker.py。
"""

import json
import os

import wx

from dialog.select_file_base import select_file_base_dialog
from ai.ai_recognizer import infer_via_subprocess

_STP_EXTENSIONS = (".stp", ".step")
# "选择预标注模型"首次使用时的默认目录，避免 defaultDir="" 时 wx.FileDialog
# 在 Windows 上回退到系统级的"上次访问目录"缓存——那个缓存是整个进程共享的，
# 会和"文件"页面"导入"按钮（同样传 defaultDir=""）互相串到一起。
_DEFAULT_MODEL_DIR = os.path.join("ai", "AAGNet_infer", "weights")
_ONNX_FACE_LIMITS = {
    "blind_hole_scatter.onnx": (2, 5),
    "countersunk_hole_scatter.onnx": (2, 8),
    "chamfer_scatter.onnx": (0, 9),
    "round_scatter.onnx": (0, 9),
}


def select_pretrain_model(main_window):
    """选择预标注模型：选取 .onnx 权重文件，再弹窗选取配套的统计归一化文件。

    不做已知模型自动匹配——不依赖"识别"选项卡那 4 套权重路径字段，
    阈值统一使用 main_window.pretrain_min_faces_num/max_faces_num 的默认值 (0, 9)。
    """
    default_dir = getattr(main_window, "last_pretrain_model_dir", "") or _DEFAULT_MODEL_DIR
    weight_path = select_file_base_dialog(
        parent=None,
        wildcard="ONNX 模型文件 (*.onnx)|*.onnx",
        message="选择预标注模型",
        default_dir=default_dir,
        default_file="",
    )
    if not weight_path:
        main_window.status_bar.SetStatusText("选择预标注模型：未选择文件")
        return

    stat_path = select_file_base_dialog(
        parent=None,
        wildcard="统计文件 (*.json)|*.json",
        message="请选择配套的统计归一化文件",
        default_dir=os.path.dirname(weight_path),
        default_file="",
    )
    if not stat_path:
        main_window.status_bar.SetStatusText("选择预标注模型失败：未指定统计文件")
        return

    default_feature_name = os.path.splitext(os.path.basename(weight_path))[0]
    name_dlg = wx.TextEntryDialog(
        None, "该模型识别的特征名称（如：盲孔、圆角）：", "预标注特征名称", default_feature_name
    )
    feature_name = default_feature_name
    if name_dlg.ShowModal() == wx.ID_OK:
        feature_name = name_dlg.GetValue().strip() or default_feature_name
    name_dlg.Destroy()

    main_window.pretrain_model_path = weight_path
    main_window.pretrain_stat_path = stat_path
    main_window.pretrain_feature_name = feature_name
    main_window.pretrain_min_faces_num, main_window.pretrain_max_faces_num = _ONNX_FACE_LIMITS.get(
        os.path.basename(weight_path).lower(), (0, 9)
    )
    main_window.last_pretrain_model_dir = os.path.dirname(weight_path)
    main_window.status_bar.SetStatusText(f"已选择预标注模型: {weight_path}（特征名称: {feature_name}）")


def _run_inference(main_window, doc=None, obj_name=None):
    """在给定文档（默认当前文档）上跑一次整机推理。

    Args:
        obj_name: 传给 infer_via_subprocess，指定要推理的对象名。批量模式的后台
            文档没有视图/选中状态，必须显式传入；交互模式（默认 None）走
            SelectionManager 取当前选中对象。

    Returns:
        (face_list, obj_names, groups, all_face_id) 或 None（出错时已写状态栏）。
    """
    if not getattr(main_window, "pretrain_model_path", ""):
        main_window.status_bar.SetStatusText("请先选择预标注模型")
        return None

    target_doc = doc if doc is not None else main_window.doc
    try:
        return infer_via_subprocess(
            target_doc, main_window.NCTI,
            weight_path=main_window.pretrain_model_path,
            stat_path=main_window.pretrain_stat_path,
            feature_name=getattr(main_window, "pretrain_feature_name", "ai_feature"),
            min_faces_num=getattr(main_window, "pretrain_min_faces_num", 0),
            max_faces_num=getattr(main_window, "pretrain_max_faces_num", 9),
            obj_name=obj_name,
        )
    except Exception as e:
        main_window.status_bar.SetStatusText(f"预标注推理失败: {e}")
        return None


def pre_label(main_window):
    """对当前文档执行预标注：整机推理后高亮检测到的面，并按检测到的连通分组
    （每组视为一个独立特征实例）加载到"已标注特征"表格（不区分底面，底面
    数据不处理）。"""
    if not hasattr(main_window, 'doc'):
        main_window.status_bar.SetStatusText("没有doc对象")
        return

    result = _run_inference(main_window)
    if result is None:
        return

    face_list, obj_names, groups, _all_face_id = result
    if not face_list:
        wx.MessageBox("未检测到特征", "预标注", wx.OK | wx.ICON_INFORMATION)
        main_window.status_bar.SetStatusText("预标注：未检测到特征")
        return

    main_window.show_selection(obj_names, face_list)

    label_name = main_window.pretrain_feature_name
    label_name_panel = main_window.label_name_panel
    if label_name not in label_name_panel.feature_to_id:
        label_name_panel.get_feature_id(label_name)
        label_name_panel.name_list.Append(label_name)

    obj_name = obj_names[0] if obj_names else ""
    panel = main_window.labeled_features_panel
    panel._save_snapshot()
    panel.update_label_result(label_name, face_list, "add")
    # 按连通分组逐组写入：每组是整机推理识别出的一个独立特征实例（比如两个
    # 互不相邻的盲孔），必须各自分配独立的 inst_id，否则会被合并成同一个实例，
    # 污染导出的 inst 矩阵和底面关联（与 batch_pre_label 的 _build_export_data
    # 按组处理保持一致）。
    for group in groups:
        panel._assign_feature_instance(label_name, group)
        panel._add_row(label_name, [obj_name], group)
    panel._mark_label_dirty()

    main_window.status_bar.SetStatusText(f"预标注完成，共检测到{len(face_list)}个面，已加入已标注特征列表")


def _build_export_data(source_file, face_list, groups, all_face_id, category_name):
    """构建与手动标注一致的 seg/inst/bottom/feature_mapping 结构。

    bottom 字段本次不做 AI 底面检测，统一填 0（详见实现计划说明）。
    """
    num_faces = (max(all_face_id) + 1) if all_face_id else 0
    category_id = 1

    seg = {str(i): 0 for i in range(num_faces)}
    for fa in face_list:
        seg[str(fa)] = category_id

    inst = [[0] * num_faces for _ in range(num_faces)]
    for group in groups:
        for i, fa in enumerate(group):
            for fb in group[i:]:
                inst[fa][fb] = 1
                inst[fb][fa] = 1

    bottom = {str(i): 0 for i in range(num_faces)}

    return {
        "source_file": source_file,
        "feature_mapping": {category_name: category_id},
        "seg": seg,
        "inst": inst,
        "bottom": bottom,
    }


def batch_pre_label(main_window):
    """批量预标注：对所选文件夹顶层的每个 stp/step 文件整机推理，
    输出同名 json（已存在则直接覆盖）到该文件夹下。"""
    if not getattr(main_window, "pretrain_model_path", ""):
        main_window.status_bar.SetStatusText("请先选择预标注模型")
        return

    dlg = wx.DirDialog(None, message="选择包含STP文件的文件夹")
    result = dlg.ShowModal()
    folder = dlg.GetPath()
    dlg.Destroy()
    if result != wx.ID_OK or not folder:
        return

    stp_files = sorted(
        os.path.join(folder, name) for name in os.listdir(folder)
        if name.lower().endswith(_STP_EXTENSIONS)
    )
    if not stp_files:
        main_window.status_bar.SetStatusText("所选文件夹下没有找到stp/step文件")
        return

    category_name = main_window.pretrain_feature_name

    # 全程在一个后台文档上跑，不导入到软件可见的主文档/视图，也不接触
    # main_window.doc/cad_view——用户在整个批量过程中不应看到任何界面变化。
    # 必须复用同一个 Document（doc.New 逐个重置），每件新建 Document 会在
    # ~60 件后因 C++ 对象累积 segfault（参见 ncti_backend.load_part 的说明）。
    doc = main_window.NCTI.Document()
    success_count = 0
    fail_count = 0
    failures = []
    try:
        for stp_path in stp_files:
            try:
                doc.New("OCC", "DCM", "GMSH")
                doc.SetImportAssemelFile(1)
                ok = doc.RunCommand("cmd_ncti_import_file", str(stp_path), "testbox")
                if not ok:
                    raise RuntimeError("NCTI 导入失败")
                obj_names = list(doc.AllNames() or [])
                if not obj_names:
                    raise RuntimeError("导入后未找到对象")

                result = _run_inference(main_window, doc=doc, obj_name=obj_names[0])
                if result is None:
                    failures.append((stp_path, "推理失败，详见当时的状态栏提示"))
                    fail_count += 1
                    continue
                face_list, _obj_names, groups, all_face_id = result

                export_data = _build_export_data(stp_path, face_list, groups, all_face_id, category_name)
                json_path = os.path.splitext(stp_path)[0] + ".json"
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=2)
                success_count += 1
            except Exception as e:
                main_window.status_bar.SetStatusText(f"处理 {stp_path} 失败: {e}")
                failures.append((stp_path, str(e)))
                fail_count += 1
    finally:
        doc.Delete()

    summary = f"批量预标注完成：成功{success_count}个，失败{fail_count}个"
    if failures:
        # 逐个文件失败的原因只会在状态栏短暂出现、被下一次循环覆盖掉，
        # 批量跑几十个文件时根本没法知道具体是哪个文件出了什么问题，
        # 所以额外落一份日志到所选文件夹里。
        log_path = os.path.join(folder, "_batch_pre_label_errors.log")
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                for path, err in failures:
                    f.write(f"{path}: {err}\n")
            summary += f"，失败详情见 {log_path}"
        except OSError:
            pass
    main_window.status_bar.SetStatusText(summary)
