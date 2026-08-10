"""训练页中间层。

UI（train_tab.py）只调用本模块的函数；生成graph/训练神经网络的重活交给独立子进程
（装了 dgl/torch/torch_ema/torchmetrics 的 conda 环境，路径见 config/system_config.json
的 trainEnvPython/aiEnvPython 字段）完成，参见 ai/train_client.py、ai/train_worker.py。
训练管线代码已整体移植进本项目的 ai/AAGNet_train/ 包，本模块不重复实现数据划分/
图生成/训练逻辑。

label_index 说明：数据集里每个 json 的 feature_mapping 是"某次标注会话里 特征名->编号"
的映射，编号本身不是全局约定值（不同文件、不同标注会话可能给同一个特征名分配不同编号，
批量预标注写出的 json 更是统一固定用编号 1，参见 on_pre_label._build_export_data）。
Geo-Rec 的标签过滤只认一个全局 label_index（configs.yaml 的 recognize_task_infos.index_num），
所以这里在生成graph前会校验所选特征在数据集内所有文件里的编号是否一致，不一致就报错
而不是悄悄选一个凑合用。
"""

import json
import os
import time

import wx

from ai import train_client

_STP_EXTENSIONS = (".stp", ".step")


def _find_dataset_pairs(folder):
    """返回 folder 下与同名 .stp/.step 文件配对的 .json 文件路径列表。"""
    if not folder or not os.path.isdir(folder):
        return []
    entries = os.listdir(folder)
    stems_with_stp = {
        os.path.splitext(name)[0] for name in entries if name.lower().endswith(_STP_EXTENSIONS)
    }
    return [
        os.path.join(folder, name) for name in entries
        if name.lower().endswith(".json") and os.path.splitext(name)[0] in stems_with_stp
    ]


def _normalize_label_data(data):
    """把标注 json 解析结果统一成"标签数据 dict"。

    兼容两种格式：
      - 新格式：dict {source_file, feature_mapping, seg, inst, bottom}
      - 旧格式：list [model_name, {数据}] 或 list [[model_name, {数据}]]
    无法解析时返回空 dict。
    """
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, list) and len(first) == 2 and isinstance(first[1], dict):
            return first[1]
        if isinstance(first, dict):
            return first
        if isinstance(first, str) and len(data) > 1 and isinstance(data[1], dict):
            return data[1]
    return {}


def _scan_feature_names(json_paths):
    """汇总所有 json 的 feature_mapping 里出现过的特征名（并集，按字母排序）。"""
    names = set()
    for json_path in json_paths:
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        label_data = _normalize_label_data(data)
        names.update((label_data.get("feature_mapping") or {}).keys())
    return sorted(names)


def _parse_manual_category(value):
    """把用户填写的类别解析为整数；拒绝空值、小数和科学计数法。"""
    text = str(value).strip()
    if not text or (text[0] in "+-" and not text[1:].isdigit()) or (
        text[0] not in "+-" and not text.isdigit()
    ):
        raise ValueError("类别必须填写整数")
    return int(text)


class ManualFeatureMappingDialog(wx.Dialog):
    """数据集没有 feature_mapping 时，补录本次训练使用的特征映射。"""

    def __init__(self, parent):
        super().__init__(parent, title="填写训练特征映射", style=wx.DEFAULT_DIALOG_STYLE)
        sizer = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(2, 2, 8, 10)
        grid.Add(wx.StaticText(self, label="训练几何特征："), 0, wx.ALIGN_CENTER_VERTICAL)
        self.feature_ctrl = wx.TextCtrl(self)
        grid.Add(self.feature_ctrl, 1, wx.EXPAND)
        grid.Add(wx.StaticText(self, label="类别（整数）："), 0, wx.ALIGN_CENTER_VERTICAL)
        self.category_ctrl = wx.TextCtrl(self)
        grid.Add(self.category_ctrl, 1, wx.EXPAND)
        grid.AddGrowableCol(1, 1)
        sizer.Add(grid, 1, wx.EXPAND | wx.ALL, 12)

        buttons = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(buttons, 0, wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        self.SetSizerAndFit(sizer)
        self.SetMinSize((360, -1))
        self.CentreOnParent()

    def GetMapping(self):
        feature = self.feature_ctrl.GetValue().strip()
        if not feature:
            raise ValueError("训练几何特征不能为空")
        return feature, _parse_manual_category(self.category_ctrl.GetValue())


def _prompt_manual_feature_mapping(parent):
    """循环提示直至输入有效、用户取消；成功返回 (特征名, 整数类别)。"""
    dlg = ManualFeatureMappingDialog(parent)
    try:
        while dlg.ShowModal() == wx.ID_OK:
            try:
                return dlg.GetMapping()
            except ValueError as exc:
                wx.MessageBox(str(exc), "输入错误", wx.OK | wx.ICON_WARNING, parent=dlg)
        return None
    finally:
        dlg.Destroy()


def _select_manual_feature_mapping(main_window):
    result = _prompt_manual_feature_mapping(main_window)
    if result is None:
        main_window.status_bar.SetStatusText("未填写训练特征映射，已取消")
        return ""
    feature, category = result
    main_window.train_selected_feature = feature
    main_window.train_available_features = [feature]
    main_window.train_manual_feature_mapping = {feature: category}
    main_window.status_bar.SetStatusText(f"已设置训练特征映射: {feature} -> {category}")
    return feature


def _resolve_from_features(main_window, features):
    """给定特征名列表，单个自动选中；多个弹窗选择。返回选中的特征名，取消返回空字符串。"""
    if len(features) == 1:
        main_window.train_selected_feature = features[0]
        return features[0]

    dlg = wx.SingleChoiceDialog(
        None, "数据集中发现多个特征，请选择本次训练使用的特征：", "选择训练特征", features
    )
    try:
        if dlg.ShowModal() == wx.ID_OK:
            main_window.train_selected_feature = dlg.GetStringSelection()
            return main_window.train_selected_feature
        main_window.train_selected_feature = ""
        return ""
    finally:
        dlg.Destroy()


def _ensure_feature_resolved(main_window, json_paths):
    """generate_graph 前的兜底：如果用户没点过"选择训练特征"，这里补上同一套
    自动选择/弹窗提醒逻辑，避免特征未确定就往下跑。已解析过的直接复用缓存。"""
    feature = getattr(main_window, "train_selected_feature", "")
    if feature:
        return feature

    features = getattr(main_window, "train_available_features", None) or _scan_feature_names(json_paths)
    main_window.train_available_features = features
    if not features:
        return _select_manual_feature_mapping(main_window)

    feature = _resolve_from_features(main_window, features)
    if not feature:
        main_window.status_bar.SetStatusText("未选择训练特征，已取消生成graph")
    return feature


def _resolve_label_index(json_paths, feature_name, manual_mapping=None):
    """返回 (label_index, error_msg)。error_msg 非空时 label_index 为 None。

    要求所选特征在数据集所有文件里的编号一致，否则视为数据集标注不规范，直接报错。
    """
    ids = set()
    for json_path in json_paths:
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        mapping = _normalize_label_data(data).get("feature_mapping") or {}
        if feature_name in mapping:
            ids.add(mapping[feature_name])

    if not ids and feature_name in (manual_mapping or {}):
        return manual_mapping[feature_name], None
    if not ids:
        return None, f"没有任何文件的 feature_mapping 中包含特征 '{feature_name}'"
    if len(ids) > 1:
        return None, (
            f"特征 '{feature_name}' 在不同文件里的 feature_mapping 编号不一致"
            f"（发现编号: {sorted(ids)}），无法确定唯一的训练标签，"
            f"请检查数据集是否混用了不同标注会话/批量预标注的结果"
        )
    return ids.pop(), None


def select_dataset_folder(main_window):
    """选择数据集文件夹：文件夹下需含同名 STP/step + JSON 配对文件。"""
    if getattr(main_window, "train_job", None) is not None:
        main_window.status_bar.SetStatusText("训练任务进行中，请等待完成后再切换数据集")
        return

    dlg = wx.DirDialog(None, message="选择数据集文件夹（含同名STP/JSON配对文件）")
    result = dlg.ShowModal()
    folder = dlg.GetPath()
    dlg.Destroy()
    if result != wx.ID_OK or not folder:
        return

    json_paths = _find_dataset_pairs(folder)
    if not json_paths:
        main_window.status_bar.SetStatusText("所选文件夹下没有找到STP/JSON同名配对文件")
        return

    main_window.train_dataset_folder = folder
    main_window.train_available_features = []
    main_window.train_selected_feature = ""
    main_window.train_manual_feature_mapping = {}
    main_window.status_bar.SetStatusText(f"已选择数据集文件夹: {folder}（共{len(json_paths)}对文件）")


def _warn_graph_stale_if_needed(main_window):
    """若已生成过 graph 且其记录的特征与当前选中特征不一致，提醒用户重生成 graph。

    仅当用户当前会话显式选过特征、且 work_dir 下已有 train_job.json（说明之前
    基于别的特征生成过 graph）时才提醒；没生成过 graph 则静默放过。
    """
    feature = getattr(main_window, "train_selected_feature", "")
    if not feature:
        return
    folder = getattr(main_window, "train_dataset_folder", "")
    if not folder:
        return
    job_path = os.path.join(folder, "_train_work", "train_job.json")
    if not os.path.exists(job_path):
        return
    try:
        with open(job_path, "r", encoding="utf-8") as f:
            old_feature = json.load(f).get("feature_name", "")
    except (OSError, ValueError):
        return
    if old_feature and old_feature != feature:
        main_window.status_bar.SetStatusText(
            f"已切换训练特征为「{feature}」，但已生成的graph基于「{old_feature}」已过期，请重新点击\"生成graph\""
        )


def select_train_feature(main_window):
    """列出数据集中出现过的特征供用户选择；只有一种时自动选中。"""
    if getattr(main_window, "train_job", None) is not None:
        main_window.status_bar.SetStatusText("训练任务进行中，请等待完成后再切换特征")
        return

    folder = getattr(main_window, "train_dataset_folder", "")
    if not folder:
        main_window.status_bar.SetStatusText("请先选择数据集文件夹")
        return

    json_paths = _find_dataset_pairs(folder)
    if not json_paths:
        main_window.status_bar.SetStatusText("数据集文件夹下没有找到匹配的STP/JSON文件")
        return

    features = _scan_feature_names(json_paths)
    if not features:
        if _select_manual_feature_mapping(main_window):
            _warn_graph_stale_if_needed(main_window)
        return
    main_window.train_available_features = features

    if len(features) == 1:
        main_window.train_selected_feature = features[0]
        main_window.status_bar.SetStatusText(f"已自动选择训练特征: {features[0]}（数据集中仅此一种特征）")
        _warn_graph_stale_if_needed(main_window)
        return

    feature = _resolve_from_features(main_window, features)
    if feature:
        main_window.status_bar.SetStatusText(f"已选择训练特征: {feature}")
        _warn_graph_stale_if_needed(main_window)
    else:
        main_window.status_bar.SetStatusText(f"发现{len(features)}个特征，尚未选择，生成graph时会再次提醒选择")


def _launch_job(main_window, mode, work_dir, start_status):
    try:
        proc, stdout_log_path = train_client.launch_subprocess(mode, work_dir)
    except Exception as e:
        action = "生成graph" if mode == "graph" else "训练神经网络"
        main_window.status_bar.SetStatusText(f"启动{action}子进程失败: {e}")
        return

    main_window.train_job = {
        "mode": mode,
        "work_dir": work_dir,
        "proc": proc,
        "stdout_log_path": stdout_log_path,
        "real_log_path": None,
        "last_log_size": 0,
        "start_time": time.time(),
    }
    main_window.status_bar.SetStatusText(f"{start_status}，日志: {stdout_log_path}")
    # 训练页内嵌仪表盘：一点击训练/生成graph 就开始实时刷新曲线与日志
    if hasattr(main_window, "train_dashboard"):
        main_window.train_dashboard.set_work_dir(work_dir, mode)
    wx.CallLater(1000, _poll_train_job, main_window)


def generate_graph(main_window):
    """按8:1:1划分数据集并生成graph，保存在数据集文件夹下的 _train_work 子目录。"""
    if getattr(main_window, "train_job", None) is not None:
        main_window.status_bar.SetStatusText("训练任务进行中，请等待完成")
        return

    folder = getattr(main_window, "train_dataset_folder", "")
    if not folder:
        main_window.status_bar.SetStatusText("请先选择数据集文件夹")
        return

    json_paths = _find_dataset_pairs(folder)
    if not json_paths:
        main_window.status_bar.SetStatusText("数据集文件夹下没有找到匹配的STP/JSON文件")
        return

    feature = _ensure_feature_resolved(main_window, json_paths)
    if not feature:
        return

    label_index, err = _resolve_label_index(
        json_paths, feature, getattr(main_window, "train_manual_feature_mapping", None)
    )
    if err:
        main_window.status_bar.SetStatusText(f"生成graph失败: {err}")
        return

    work_dir = os.path.join(folder, "_train_work")
    os.makedirs(work_dir, exist_ok=True)
    job_data = {
        "feature_name": feature,
        "label_index": label_index,
        "raw_folder": folder,
        "train_ratio": 0.8,
        "val_ratio": 0.1,
        "test_ratio": 0.1,
        "num_workers": 4,
        "timeout": 120,
    }
    with open(os.path.join(work_dir, "train_job.json"), "w", encoding="utf-8") as f:
        json.dump(job_data, f, ensure_ascii=False, indent=2)

    _launch_job(main_window, "graph", work_dir, f"生成graph已开始（特征: {feature}）")


class TrainEpochDialog(wx.Dialog):
    """点击"训练神经网络"后弹出，让用户输入训练轮数(epochs)。"""

    def __init__(self, parent):
        super().__init__(parent, title="设置训练参数", style=wx.DEFAULT_DIALOG_STYLE)
        sizer = wx.BoxSizer(wx.VERTICAL)

        hint = wx.StaticText(self, label="训练轮数 (epochs)：")
        sizer.Add(hint, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
        self.epoch_ctrl = wx.SpinCtrl(self, value="200", min=1, max=100000, size=(120, -1))
        sizer.Add(self.epoch_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        btn_sizer = wx.StdDialogButtonSizer()
        btn_sizer.AddButton(wx.Button(self, wx.ID_OK, "开始训练"))
        btn_sizer.AddButton(wx.Button(self, wx.ID_CANCEL, "取消"))
        btn_sizer.Realize()
        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 12)

        self.SetSizer(sizer)
        self.Fit()
        self.CentreOnParent()

    def GetEpochs(self):
        return self.epoch_ctrl.GetValue()


def _update_train_job_epochs(work_dir, epochs):
    """把用户指定的 epochs 写回 work_dir/train_job.json，供训练子进程读取。"""
    job_path = os.path.join(work_dir, "train_job.json")
    if not os.path.exists(job_path):
        return
    try:
        with open(job_path, "r", encoding="utf-8") as f:
            job = json.load(f)
    except (OSError, ValueError):
        return
    job["epochs"] = epochs
    with open(job_path, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)


def train_model(main_window):
    """用已选的AAGNet模型架构和已生成的graph训练神经网络。

    点击后会弹出小窗口让用户填写 epochs，确认后再启动训练子进程。
    """
    if getattr(main_window, "train_job", None) is not None:
        main_window.status_bar.SetStatusText("训练任务进行中，请等待完成")
        return

    folder = getattr(main_window, "train_dataset_folder", "")
    if not folder:
        main_window.status_bar.SetStatusText("请先选择数据集文件夹")
        return

    work_dir = os.path.join(folder, "_train_work")
    job_path = os.path.join(work_dir, "train_job.json")

    # P1 防御：防止用「改了特征却没重生成 graph」的过期配置静默训错特征。
    # 仅当用户在当前会话显式选过特征（train_selected_feature 非空）且与已生成
    # graph 记录的特征不一致时拦截；若用户从未在 GUI 选特征（直接用现成 work_dir
    # 训练），则信任 train_job.json 里的 feature_name，不拦截。
    if os.path.exists(job_path):
        try:
            with open(job_path, "r", encoding="utf-8") as f:
                job = json.load(f)
            graph_feature = job.get("feature_name", "")
            current_feature = getattr(main_window, "train_selected_feature", "")
            if current_feature and graph_feature and current_feature != graph_feature:
                main_window.status_bar.SetStatusText(
                    f"训练特征「{current_feature}」与已生成graph的特征「{graph_feature}」不一致，"
                    f"请先重新点击\"生成graph\""
                )
                return
        except (OSError, ValueError):
            pass

    graph_dir = os.path.join(work_dir, "0000-00-00_processed_data", "graph")
    if not os.path.isdir(graph_dir) or not os.listdir(graph_dir):
        main_window.status_bar.SetStatusText("尚未生成graph，请先点击\"生成graph\"")
        return

    dlg = TrainEpochDialog(main_window)
    if dlg.ShowModal() != wx.ID_OK:
        dlg.Destroy()
        return
    epochs = dlg.GetEpochs()
    dlg.Destroy()

    _update_train_job_epochs(work_dir, epochs)

    # 清理上一次训练的曲线缓存（metrics.jsonl），确保本次从空白开始，
    # 不再显示上一次的训练曲线。在启动子进程前删除，避免与子进程文件句柄冲突。
    metrics_path = os.path.join(work_dir, "metrics.jsonl")
    if os.path.exists(metrics_path):
        try:
            os.remove(metrics_path)
        except OSError:
            pass

    _launch_job(main_window, "train", work_dir, f"训练神经网络已开始（epochs={epochs}）")


def _read_last_metric(work_dir):
    """读取 work_dir/metrics.jsonl 的最后一条训练指标记录（JSON 行），无则返回 None。"""
    path = os.path.join(work_dir, "metrics.jsonl")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
    except OSError:
        return None
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except ValueError:
        return None


def _read_total_epochs(work_dir):
    """从 train_job.json 读取用户设定的总 epoch 数，读取失败返回 None。"""
    job_path = os.path.join(work_dir, "train_job.json")
    try:
        with open(job_path, "r", encoding="utf-8") as f:
            return json.load(f).get("epochs")
    except (OSError, ValueError):
        return None


def _format_duration(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}秒"
    if seconds < 3600:
        return f"{seconds // 60}分{seconds % 60}秒"
    return f"{seconds // 3600}时{(seconds % 3600) // 60}分"


def _estimate_eta(job, epoch, total):
    """根据已用时间和当前 epoch 估算剩余训练时间，无法估算返回 None。"""
    if not epoch or not total or epoch <= 0:
        return None
    elapsed = time.time() - job.get("start_time", time.time())
    remaining = elapsed / epoch * (total - epoch)
    if remaining <= 0:
        return None
    return _format_duration(remaining)


def _build_train_status(job):
    """训练模式下构造状态栏结构化进度文本（epoch X/Y · loss=... · 剩余≈...）。无指标时返回 None。"""
    metric = _read_last_metric(job["work_dir"])
    if metric is None:
        return None
    epoch = metric.get("epoch")
    total = _read_total_epochs(job["work_dir"])
    loss = metric.get("val_loss") if metric.get("val_loss") is not None else metric.get("train_loss")
    parts = []
    if epoch is not None:
        parts.append(f"epoch {epoch}/{total}" if total else f"epoch {epoch}")
    if loss is not None:
        try:
            parts.append(f"loss={loss:.4f}")
        except (TypeError, ValueError):
            parts.append(f"loss={loss}")
    eta = _estimate_eta(job, epoch, total)
    if eta:
        parts.append(f"剩余≈{eta}")
    return "训练中 " + " · ".join(parts) if parts else None


def _find_latest_model(work_dir):
    """定位 model_weights 下最新生成的模型（兼容旧名及带特征前缀的新名）。"""
    base = os.path.join(work_dir, "model_weights")
    if not os.path.isdir(base):
        return ""
    candidates = []
    for root, _dirs, files in os.walk(base):
        for name in files:
            if name == "best_model.pth" or name.endswith("_best_model.pth"):
                candidates.append(os.path.join(root, name))
    if not candidates:
        return ""
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]


def _poll_train_job(main_window):
    """每秒轮询一次子进程状态和日志文件内容，更新状态栏；子进程结束后自动清理。"""
    job = getattr(main_window, "train_job", None)
    if job is None:
        return

    if job["real_log_path"] is None:
        hint_path = os.path.join(job["work_dir"], "current_log_path.txt")
        if os.path.exists(hint_path):
            try:
                with open(hint_path, "r", encoding="utf-8") as f:
                    real_path = f.read().strip()
            except OSError:
                real_path = ""
            if real_path:
                job["real_log_path"] = real_path
                job["last_log_size"] = 0

    if job["mode"] == "train":
        # 有 metrics 后用结构化进度（epoch/loss/ETA），尚未产出指标时回退到日志末行
        status = _build_train_status(job)
        if status:
            main_window.status_bar.SetStatusText(status)
        else:
            tail = _read_log_tail(job)
            if tail:
                main_window.status_bar.SetStatusText(tail)
    else:
        tail = _read_log_tail(job)
        if tail:
            main_window.status_bar.SetStatusText(tail)

    retcode = job["proc"].poll()
    if retcode is None:
        wx.CallLater(1000, _poll_train_job, main_window)
        return

    _finish_train_job(main_window, job, retcode)


def _read_log_tail(job):
    log_path = job["real_log_path"] or job["stdout_log_path"]
    if not log_path or not os.path.exists(log_path):
        return ""
    try:
        # 用二进制模式做增量定位：字节偏移绝对合法，避免文本模式在多字节 UTF-8
        # 字符中间 seek 抛 ValueError（原文本模式 seek/tell 的隐患）。
        with open(log_path, "rb") as f:
            f.seek(job["last_log_size"])
            chunk = f.read().decode("utf-8", errors="ignore")
            job["last_log_size"] = f.tell()
    except OSError:
        return ""
    lines = [line.strip() for line in chunk.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _describe_retcode(retcode):
    """把子进程退出码翻译成可读含义，便于排查（尤其 Windows 段错误/被杀）。"""
    if retcode is None:
        return "未知"
    if retcode == -1:
        return "被外部终止(-1，可能被系统 OOM 杀死/手动取消/子进程崩溃)" if sys.platform == "win32" \
            else "被信号终止"
    if retcode < 0:
        return f"被信号终止(-{-retcode})"
    known = {
        3221225477: "Windows 访问冲突(0xC0000005 段错误/C崩溃)",
        3221225786: "Windows 栈溢出(0xC00000FD)",
        3221225620: "Windows 非法指令(0xC000001D)",
        3221226505: "Windows 栈缓冲区溢出(0xC0000409)",
    }
    return known.get(retcode, f"0x{retcode & 0xFFFFFFFF:08X}")


def _tail_lines(path, n=50):
    """读取日志文件最后 n 行，失败时回显子进程输出用。"""
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.read().splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-n:])


def _finish_train_job(main_window, job, retcode):
    main_window.train_job = None
    # 子进程结束：隐藏进度条（曲线保留最终状态/或保持隐藏）
    if hasattr(main_window, "train_dashboard"):
        main_window.train_dashboard.finish_job()

    action = "生成graph" if job["mode"] == "graph" else "训练神经网络"
    if retcode == 0:
        if job["mode"] == "train":
            model_path = _find_latest_model(job["work_dir"])
            msg = f"{action}完成。"
            if model_path:
                msg += (
                    f"\n\n模型权重已保存：\n{model_path}\n"
                    f"（同目录含与模型同名的 JSON 归一化统计量，可直接用于推理端「选择预训练模型」）"
                )
            else:
                msg += f"\n\n未在 {os.path.join(job['work_dir'], 'model_weights')} 定位到模型权重，请检查训练日志"
            wx.MessageBox(msg, "训练完成", wx.OK | wx.ICON_INFORMATION)
        else:
            graph_dir = os.path.join(job["work_dir"], "0000-00-00_processed_data", "graph")
            msg = f"{action}完成。"
            if os.path.isdir(graph_dir):
                msg += f"\n\ngraph 已生成：\n{graph_dir}"
            wx.MessageBox(msg, "graph 生成完成", wx.OK | wx.ICON_INFORMATION)
        main_window.status_bar.SetStatusText(f"{action}完成")
    else:
        log_path = job["real_log_path"] or job["stdout_log_path"]
        stdout_log = job.get("stdout_log_path", "")
        reason = _describe_retcode(retcode)
        # 子进程 stderr 重定向到 stdout_log（含 faulthandler 崩溃堆栈），读尾部作为线索
        stderr_tail = _tail_lines(stdout_log, 80)
        # 把失败摘要写到至少一处日志，保证"看日志就能看到报错"：
        # 1) 业务日志 run_xxx.log（若存在）
        # 2) 否则兜底写进子进程日志 stdout_log（崩溃发生在 setup_logging 之前时 real_log_path 还为空）
        summary = (
            f"\n[ERROR] {action}失败（退出码 {retcode}，{reason}）\n"
            f"子进程输出日志(含崩溃堆栈): {stdout_log}\n"
        )
        if stderr_tail:
            summary += "---- 子进程输出尾部 ----\n" + stderr_tail + "\n"

        wrote_to = None
        if job.get("real_log_path") and os.path.isfile(job["real_log_path"]):
            try:
                with open(job["real_log_path"], "a", encoding="utf-8") as f:
                    f.write(summary)
                wrote_to = job["real_log_path"]
            except OSError:
                pass
        if wrote_to is None and stdout_log and os.path.isfile(stdout_log):
            try:
                with open(stdout_log, "a", encoding="utf-8") as f:
                    f.write(summary)
                wrote_to = stdout_log
            except OSError:
                pass
        tail_hint = f"（错误摘要已写入: {wrote_to}）" if wrote_to else ""
        main_window.status_bar.SetStatusText(
            f"{action}失败（退出码 {retcode} {reason}），日志: {log_path}{tail_hint}"
        )
