"""训练页内嵌仪表盘：曲线（loss/指标）+ 进度条 + 滚动日志，直接嵌在训练选项卡中央区域。

替代原先独立的"训练实时监测 / 训练日志"弹窗：切到训练 tab 时，主窗口中央的 STP
查看器被本面板替换，曲线与日志实时显示；离开训练 tab 时还原 STP 查看器。

行为约定（2026-07-20 调整）：
- 曲线图默认隐藏，仅在点击「训练神经网络」启动训练后才显示；「生成graph」阶段不显示曲线。
- 每次启动训练前会清理上一次训练的 metrics.jsonl 缓存（见 function/on_train.py），
  因此曲线总是从空白开始，不会再显示上一次的训练曲线。
- 进度条：以「阶梯式逐行进度条」渲染在日志末尾——训练阶段以约 10% 为一级逐级列出
  已完成台阶（epoch X/total [████░░] pct%），末尾追加当前 epoch 实时行（标 ◀当前），
  随训练推进逐行增长、右缘呈阶梯/三角轮廓；生成graph阶段无 epoch 概念，同样以约 10% 为一级渲染成阶梯（total 视作 10 级），进度单调爬升封顶 0.9 表示"进行中"。
  不再使用独立的 wx.Gauge 控件，进度直接合并进日志文本，用户看日志即知进度。
- 用 wx.Timer 轮询 ai/train_worker.py 写在 work_dir 下的文件
  （current_log_path.txt 指向的日志文件 / metrics.jsonl）。
"""

import json
import os
import time

import wx

try:
    import matplotlib
    matplotlib.use("WXAgg")
    # 与 function/on_visualize.py 的 graphviz 拓扑图保持同一套中文字体约定
    matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
    from matplotlib.figure import Figure
    _HAS_MATPLOTLIB = True
except ImportError:
    _HAS_MATPLOTLIB = False


# 折线图展示的指标：(metrics.jsonl 里的字段名, 图例文字, 颜色)
_LOSS_LINES = [
    ("train_loss", "训练loss", "#1f77b4"),
    ("val_loss", "验证loss", "#d62728"),
]
_METRIC_LINES = [
    ("val_seg_iou", "验证-分割IoU", "#2ca02c"),
    ("val_inst_f1", "验证-实例F1", "#ff7f0e"),
    ("val_bottom_iou", "验证-底面IoU", "#9467bd"),
]


def _format_duration(seconds):
    """把秒数格式化为中文时长，如 45秒 / 3分25秒 / 1时2分。"""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}秒"
    if seconds < 3600:
        return f"{seconds // 60}分{seconds % 60}秒"
    return f"{seconds // 3600}时{(seconds % 3600) // 60}分"


class TrainDashboardPanel(wx.Panel):
    """训练页中央区的内嵌仪表盘：上方曲线、中部进度条、下方日志。"""

    _POLL_MS = 2000
    _LOG_POLL_MS = 800
    _LOG_MAX_LINES = 200

    def __init__(self, parent):
        super().__init__(parent)
        self.work_dir = ""
        self._mode = None          # "train" / "graph" / None
        self._last_record_count = -1
        self._metrics_timer = None
        self._log_timer = None
        # 进度条（文本，渲染在日志末尾）
        self._progress_active = False
        self._progress_fraction = 0.0
        self._start_time = None      # 本轮任务启动时刻，用于算已用/剩余时间
        self._progress_label = ""

        self.main_sizer = wx.BoxSizer(wx.VERTICAL)

        if _HAS_MATPLOTLIB:
            self.figure = Figure(figsize=(6, 5))
            self.loss_axes = self.figure.add_subplot(211)
            self.metric_axes = self.figure.add_subplot(212)
            self.canvas = FigureCanvas(self, -1, self.figure)
            self.main_sizer.Add(self.canvas, 1, wx.EXPAND | wx.ALL, 5)
        else:
            self.canvas = None
            hint = wx.StaticText(self, label="未安装 matplotlib，无法显示训练曲线（日志仍可查看）")
            self.main_sizer.Add(hint, 0, wx.ALL, 10)

        self.log_text = wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP
        )
        self.log_text.SetFont(wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self.log_text.SetMinSize((-1, 160))
        self.main_sizer.Add(self.log_text, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

        self.SetSizer(self.main_sizer)

        # 初始：曲线隐藏、进度未激活，仅日志可见（日志占满区域）
        self.show_curve(False)
        if _HAS_MATPLOTLIB:
            self._show_placeholder("尚未开始训练，点击「训练神经网络」后曲线将在此实时显示")

    # ---- 对外接口 ----

    def set_work_dir(self, work_dir, mode=None):
        """设置训练工作目录并开始轮询（重复调用同一目录不重复起定时器）。

        mode: "train" 显示曲线并开始确定进度；"graph" 隐藏曲线并用脉冲表示进行中。
        """
        self.work_dir = work_dir
        self._mode = mode
        self._last_record_count = -1

        self._progress_active = True
        self._progress_fraction = 0.0
        self._start_time = time.time()
        if mode == "train":
            self.show_curve(True)
            self._progress_label = "训练进度"
        else:
            self.show_curve(False)
            self._progress_label = "生成graph进度"

        if self._metrics_timer is None and _HAS_MATPLOTLIB:
            self._metrics_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self._on_metrics_timer, self._metrics_timer)
            self._metrics_timer.Start(self._POLL_MS)
        if self._log_timer is None:
            self._log_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self._on_log_timer, self._log_timer)
            self._log_timer.Start(self._LOG_POLL_MS)

        self._refresh()
        self._refresh_log()

    def on_show(self):
        """训练 tab 被切到前台时刷新一次（定时器已跑，这里补一次即时刷新）。"""
        if not self.work_dir:
            return
        self._refresh()
        self._refresh_log()

    def finish_job(self):
        """子进程结束后停止在日志里显示进度条；曲线保留最终状态（训练成功时）或保持隐藏（graph）。"""
        self._progress_active = False
        self._refresh_log()

    def stop(self):
        if self._metrics_timer is not None:
            self._metrics_timer.Stop()
        if self._log_timer is not None:
            self._log_timer.Stop()

    # ---- 布局切换 ----

    def show_curve(self, show):
        """显示/隐藏曲线图。隐藏时让日志占满剩余空间，避免留空。"""
        if not _HAS_MATPLOTLIB:
            return
        self.canvas.Show(show)
        self.main_sizer.GetItem(self.log_text).SetProportion(1 if not show else 0)
        self.Layout()

    # ---- 进度条（文本，渲染在日志内） ----

    def set_progress(self, fraction):
        """设置确定进度（0~1），由日志里的文本进度条渲染。"""
        try:
            self._progress_fraction = max(0.0, min(1.0, float(fraction)))
        except (TypeError, ValueError):
            return

    def _render_progress_lines(self):
        """在日志内渲染「阶梯式逐行进度条」。

        训练模式：以约 10% 为一级，逐级列出已完成的台阶（epoch X/total [bar] pct%），
        最后追加当前 epoch 的实时行（标 ◀当前）。随训练推进，行数逐行增长，右侧填充
        边缘呈阶梯/三角轮廓。最多约 10 行，不会撑长日志。
        生成graph模式：无 epoch 概念，退化为单行脉冲进度条。
        """
        width = 24
        if self._mode == "graph":
            # 生成graph 无 epoch 概念，同样以约 10% 为一级渲染成阶梯（total 视作 10 级），
            # 进度由 _on_log_timer 单调爬升，末尾标 ◀进行中。
            total_steps = 10
            cur_step = int(round(self._progress_fraction * total_steps))
            cur_step = max(0, min(total_steps, cur_step))
            lines = []
            for s in range(1, cur_step + 1):
                frac = s / total_steps
                filled = int(round(frac * width))
                filled = max(0, min(width, filled))
                bar = "█" * filled + "░" * (width - filled)
                pct = int(round(frac * 100))
                lines.append(f"{self._progress_label} {s:>2}/{total_steps}  [{bar}] {pct}%")
            if lines:
                lines[-1] = lines[-1] + "  ◀进行中"
            if not lines:
                lines.append(f"{self._progress_label} 0/{total_steps}  [{'░' * width}] 0%")
            if self._start_time:
                lines.append("⏱ 已用 " + _format_duration(time.time() - self._start_time) + " · 进行中（无明确进度）")
            return lines

        total = self._read_total_epochs() or 0
        if not total:
            return [f"{self._progress_label}: 等待首个 epoch 输出…"]
        cur_epoch = int(round(self._progress_fraction * total))
        cur_epoch = max(0, min(total, cur_epoch))
        pad = len(str(total))
        lines = []

        def _bar_line(epoch):
            frac = epoch / total
            filled = int(round(frac * width))
            filled = max(0, min(width, filled))
            bar = "█" * filled + "░" * (width - filled)
            pct = int(round(frac * 100))
            return f"epoch {epoch:>{pad}}/{total}  [{bar}] {pct}%"

        # 以约 10% 为一级，列出已完成的台阶
        step = max(1, total // 10)
        e = step
        while e <= cur_epoch:
            lines.append(_bar_line(e))
            e += step
        # 当前 epoch 实时行（不在台阶整数上时单独补一行，标 ◀当前）
        if cur_epoch > 0 and cur_epoch % step != 0:
            lines.append(_bar_line(cur_epoch) + "  ◀当前")
        if not lines:
            lines.append(f"{self._progress_label}: epoch 0/{total}  [{'░' * width}] 0%")
        # 时间摘要（已用 / 每epoch速度 / 剩余），置于末尾始终可见
        if self._start_time and cur_epoch > 0:
            elapsed = time.time() - self._start_time
            per_epoch = elapsed / cur_epoch
            remaining = elapsed / cur_epoch * (total - cur_epoch)
            lines.append(
                f"⏱ 已用 {_format_duration(elapsed)} · 约 {per_epoch:.1f}s/epoch · 剩余≈{_format_duration(remaining)}"
            )
        return lines

    # ---- 日志区 ----

    def _resolve_log_path(self):
        if not self.work_dir:
            return ""
        hint_path = os.path.join(self.work_dir, "current_log_path.txt")
        if not os.path.exists(hint_path):
            return ""
        try:
            with open(hint_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""

    def _refresh_log(self):
        log_path = self._resolve_log_path()
        if not log_path or not os.path.exists(log_path):
            if not self.log_text.GetValue():
                self.log_text.SetValue("暂无训练日志")
            return
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [line.rstrip("\n") for line in f if line.strip()]
        except OSError:
            return
        tail_lines = lines[-self._LOG_MAX_LINES:]
        # 进度条（阶梯式多行）以文本形式追加在日志末尾，随日志一起滚动、刷新
        if self._progress_active:
            tail_lines = tail_lines + self._render_progress_lines()
        tail = "\n".join(tail_lines)
        if tail != self.log_text.GetValue():
            self.log_text.SetValue(tail)
            self.log_text.ShowPosition(self.log_text.GetLastPosition())

    def _on_log_timer(self, evt):
        self._refresh_log()
        # 生成graph阶段无明确进度信号：进度单调爬升并封顶在 0.9，
        # 阶梯随之逐行增长、停在接近满级，表示"进行中、接近完成"（不会缩回）。
        if self._mode == "graph" and self._progress_active:
            self._progress_fraction = min(0.9, self._progress_fraction + 0.01)

    # ---- 曲线刷新 ----

    def _show_placeholder(self, text):
        self.loss_axes.clear()
        self.metric_axes.clear()
        self.loss_axes.set_title(text)
        self.canvas.draw_idle()

    def _load_metrics(self):
        if not self.work_dir:
            return []
        path = os.path.join(self.work_dir, "metrics.jsonl")
        if not os.path.exists(path):
            return []
        records = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except ValueError:
                        continue
        except OSError:
            return []
        return records

    def _read_total_epochs(self):
        """从 train_job.json 读取用户设定的总 epoch 数，读取失败返回 None。"""
        if not self.work_dir:
            return None
        job_path = os.path.join(self.work_dir, "train_job.json")
        try:
            with open(job_path, "r", encoding="utf-8") as f:
                return json.load(f).get("epochs")
        except (OSError, ValueError):
            return None

    def _refresh(self):
        if not _HAS_MATPLOTLIB:
            return
        records = self._load_metrics()
        if len(records) == self._last_record_count:
            return
        self._last_record_count = len(records)

        self.loss_axes.clear()
        self.metric_axes.clear()

        if not records:
            if self._mode == "train":
                self._show_placeholder("训练已开始，等待首个 epoch 输出指标…")
            else:
                self._show_placeholder("尚未开始训练，点击「训练神经网络」后曲线将在此实时显示")
            return

        epochs = [r.get("epoch", i) for i, r in enumerate(records)]

        for key, label, color in _LOSS_LINES:
            values = [r.get(key) for r in records]
            if any(v is not None for v in values):
                self.loss_axes.plot(epochs, values, label=label, color=color, marker="o", markersize=3)
        self.loss_axes.set_ylabel("loss")
        self.loss_axes.set_title("训练/验证 loss")
        self.loss_axes.legend(loc="best", fontsize=8)
        self.loss_axes.grid(True, linestyle="--", alpha=0.4)

        for key, label, color in _METRIC_LINES:
            values = [r.get(key) for r in records]
            if any(v is not None for v in values):
                self.metric_axes.plot(epochs, values, label=label, color=color, marker="o", markersize=3)
        self.metric_axes.set_xlabel("epoch")
        self.metric_axes.set_ylabel("score")
        self.metric_axes.set_title("验证集指标")
        self.metric_axes.legend(loc="best", fontsize=8)
        self.metric_axes.grid(True, linestyle="--", alpha=0.4)

        self.figure.tight_layout()
        self.canvas.draw_idle()

        # 训练阶段：按 epoch/总epoch 更新确定进度
        if self._mode == "train":
            last = records[-1]
            epoch = last.get("epoch")
            total = self._read_total_epochs()
            if epoch and total:
                self.set_progress(epoch / total)

    def _on_metrics_timer(self, evt):
        self._refresh()
