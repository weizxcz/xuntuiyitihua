# workers/ — 子进程 Worker

多进程 chunk 隔离 worker，解决 NCTI C++ SDK 批量累积 segfault 问题。每个 worker 在独立 Python 进程中运行，处理完毕后彻底释放 NCTI 资源。

## 文件

### `_chunk_worker.py` — 边训练数据收集
```bash
python -m featurefox.workers._chunk_worker <start> <end> <output_pkl>
```
被 `instance_data.collect_dataset()` 通过 subprocess 调用。每个 chunk 处理一批 STEP 文件，提取边特征训练数据，增量 pickle 落盘。

### `_inst_chunk_worker.py` — 实例训练数据收集
```bash
python -m featurefox.workers._inst_chunk_worker <start> <end> <output_pkl>
```
同源组件：先跑边分类器得到连通分量候选，再提取实例特征 + 标签，增量 pickle。

### `_sweep_worker.py` — 阈值扫描子进程
```bash
python -m featurefox.workers._sweep_worker <start> <end> <pkl_path> <offset>
```
每文件建一次图，内部扫 9 个阈值 (0.05~0.50)，产出 Mode A / Mode B 的 tp/fp/fn 累计值。

## 设计原则

- **子进程隔离**：每个 worker 独立进程，崩溃不影响主进程
- **增量落盘**：每处理完一件就原子写 pickle（先写 `.tmp` 再 `os.replace`），崩件前数据不丢失
- **独立导入**：worker 内部重新设置 sys.path 和 NCTI 初始化，不依赖父进程状态
- **`os._exit(0)`**：worker 完成任务后用硬退出，确保 NCTI 资源彻底释放
