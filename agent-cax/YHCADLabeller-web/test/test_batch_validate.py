#!/usr/bin/env python3
"""批量验证标注JSON文件格式"""
import json
import os
import glob

def validate_json(json_path):
    """验证单个JSON文件"""
    errors = []
    warnings = []

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return [f"文件读取失败: {e}"], []

    # 新格式：对象 {source_file, feature_mapping, seg, inst, bottom}
    if isinstance(data, dict):
        # 检查必要字段
        required_fields = ['source_file', 'feature_mapping', 'seg', 'inst', 'bottom']
        for field in required_fields:
            if field not in data:
                errors.append(f"缺少字段: {field}")

        # 检查 source_file
        source_file = data.get('source_file', '')
        if not source_file:
            warnings.append("source_file 为空")
        elif not os.path.exists(source_file):
            warnings.append(f"source_file 路径不存在: {source_file}")

        # 检查 seg
        seg = data.get('seg', {})
        if seg:
            seg_keys = set(int(k) for k in seg.keys())
            max_face_id = max(seg_keys) if seg_keys else 0

            # 检查 inst 矩阵
            inst = data.get('inst', [])
            if inst:
                if len(inst) != max_face_id + 1:
                    errors.append(f"inst矩阵大小({len(inst)})与最大面ID({max_face_id})不匹配")

                # 检查对称性
                for i in range(len(inst)):
                    for j in range(i, len(inst)):
                        if inst[i][j] != inst[j][i]:
                            errors.append(f"inst矩阵不对称: inst[{i}][{j}]={inst[i][j]} != inst[{j}][{i}]={inst[j][i]}")
                            break
                    if errors and 'inst矩阵不对称' in errors[-1]:
                        break

            # 检查 bottom
            bottom = data.get('bottom', {})
            bottom_keys = set(int(k) for k in bottom.keys())
            if not bottom_keys.issubset(seg_keys):
                warnings.append(f"bottom中存在不属于seg的面ID")

    # 旧格式：数组 [filename, {data}]
    elif isinstance(data, list) and len(data) >= 2:
        warnings.append("旧格式数组，建议转换")
        if isinstance(data[1], dict):
            if 'source_file' not in data[1]:
                warnings.append("旧格式缺少source_file")
    else:
        errors.append("未知的JSON格式")

    return errors, warnings

def main():
    labels_dir = r"D:\wyg\data\data\labels"
    json_files = glob.glob(os.path.join(labels_dir, "*.json"))

    print(f"开始验证 {len(json_files)} 个JSON文件...")
    print("=" * 60)

    error_stats = {"total": 0, "errors": 0, "warnings": 0, "ok": 0}
    error_samples = []

    for i, json_path in enumerate(json_files):
        errors, warnings = validate_json(json_path)

        error_stats["total"] += 1
        if errors:
            error_stats["errors"] += 1
            error_samples.append((json_path, errors))
        elif warnings:
            error_stats["warnings"] += 1
        else:
            error_stats["ok"] += 1

        if (i + 1) % 1000 == 0:
            print(f"已验证 {i + 1} / {len(json_files)}")

    print("=" * 60)
    print(f"验证完成！总计: {error_stats['total']}")
    print(f"  ✅ 正常: {error_stats['ok']}")
    print(f"  ⚠️ 警告: {error_stats['warnings']}")
    print(f"  ❌ 错误: {error_stats['errors']}")

    if error_samples:
        print("\n错误样例（前10个）:")
        for path, errs in error_samples[:10]:
            print(f"\n文件: {os.path.basename(path)}")
            for e in errs:
                print(f"  - {e}")

if __name__ == "__main__":
    main()