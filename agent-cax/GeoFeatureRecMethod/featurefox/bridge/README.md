# bridge/ — GUI 桥接层

wxPython GUI → FeatureFox 识别 → NCTI 高亮的桥接代码。

## 文件

### `on_find_through_step_featurefox.py`
与 `on_find_through_step_stp.py` 功能等价，但识别器替换为 FeatureFox（XGBoost 边分类 + 等渗校准 + 图剪枝 + 连通分量）。

**流程：**
1. `StepParser` 解析 STEP 文本拓扑（一次解析，预测与映射共用）
2. `FeatureFox predict_through_slots()` 预测通槽实例（face_id 空间）
3. 通过 `ncti.AiModel(doc, obj_name)` 获取 ai.FaceID，几何最近邻建立 STEP face → ai.FaceID 映射
4. 返回 `(obj_names, cell_ids)` 供 `show_selection()` 高亮

**依赖：**
- STEP 版 FeatureFox：`utils/through_step/featurefox/`
- NCTI SDK（用于面 ID 映射）
- `function/on_find_blind_hole_stp.py` 的 `unique_keep_order` 工具
- `utils/detect_blind_holes_and_export_stp_v15_22.py` 的 `StepParser`
