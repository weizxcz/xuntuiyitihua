"""
BrepMFR 数据批处理 collator，来源：BrepMFR-main/data/collator.py
"""
import torch
import dgl


def pad_mask_unsqueeze(x, padlen):
    """向量 padding 并添加 batch 维度，用于 node/edge padding mask."""
    xlen = x.size(0)
    if xlen < padlen:
        new_x = x.new_ones([padlen], dtype=x.dtype)
        new_x[:xlen] = x
        x = new_x
    return x.unsqueeze(0)


def pad_attn_bias_unsqueeze(x, padlen):
    """扩展 attention bias 并加 batch 维度，用于不同图节点数对齐。"""
    xlen = x.size(0)
    if xlen < padlen:
        new_x = x.new_zeros([padlen, padlen], dtype=x.dtype).fill_(float("-inf"))
        new_x[:xlen, :xlen] = x
        new_x[xlen:, :xlen] = 0
        x = new_x
    return x.unsqueeze(0)


def pad_spatial_pos_unsqueeze(x, padlen):
    """扩展空间位置编码并添加 batch 维度。"""
    x = x + 1
    xlen = x.size(0)
    if xlen < padlen:
        new_x = x.new_zeros([padlen, padlen], dtype=x.dtype)
        new_x[:xlen, :xlen] = x
        x = new_x
    return x.unsqueeze(0)


def pad_d2_pos_unsqueeze(x, padlen):
    """扩展二阶距离编码并添加 batch 维度。"""
    xlen = x.size(0)
    if xlen < padlen:
        new_x = x.new_zeros([padlen, padlen, 64], dtype=x.dtype)
        new_x[:xlen, :xlen, :] = x
        x = new_x
    return x.unsqueeze(0)


def pad_ang_pos_unsqueeze(x, padlen):
    """扩展角度位置编码并添加 batch 维度。"""
    xlen = x.size(0)
    if xlen < padlen:
        new_x = x.new_zeros([padlen, padlen, 64], dtype=x.dtype)
        new_x[:xlen, :xlen, :] = x
        x = new_x
    return x.unsqueeze(0)


def pad_3d_unsqueeze(x, padlen1, padlen2, padlen3):
    """扩展 3D 张量并添加 batch 维度（用于 edge_path）。"""
    xlen1, xlen2, xlen3 = x.size()
    if xlen1 < padlen1 or xlen2 < padlen2 or xlen3 < padlen3:
        new_x = -1 * x.new_ones([padlen1, padlen2, padlen3], dtype=x.dtype)
        new_x[:xlen1, :xlen2, :xlen3] = x
        x = new_x
    return x.unsqueeze(0)


def collator(items, multi_hop_max_dist, spatial_pos_max):
    items = [
        (
            item.graph,
            item.node_data,
            item.face_area,
            item.face_type,
            item.face_loop,
            item.face_adj,
            item.edge_data,
            item.edge_type,
            item.edge_len,
            item.edge_ang,
            item.edge_conv,
            item.node_degree,
            item.attn_bias,
            item.spatial_pos,
            item.d2_distance,
            item.angle_distance,
            item.edge_path[:, :, :multi_hop_max_dist],
            item.label_feature,
            item.data_id
        )
        for item in items
    ]

    (
        graphs,
        node_datas,
        face_areas,
        face_types,
        face_loops,
        face_adjs,
        edge_datas,
        edge_types,
        edge_lens,
        edge_angs,
        edge_convs,
        node_degrees,
        attn_biases,
        spatial_poses,
        d2_distances,
        angle_distances,
        edge_paths,
        label_features,
        data_ids
    ) = zip(*items)

    for idx, _ in enumerate(attn_biases):
        attn_biases[idx][1:, 1:][spatial_poses[idx] >= spatial_pos_max] = float("-inf")

    max_node_num = max(i.size(0) for i in node_datas)
    max_edge_num = max(i.size(0) for i in edge_datas)
    max_dist = max(i.size(-1) for i in edge_paths)
    max_dist = max(max_dist, multi_hop_max_dist)

    padding_mask_list = [torch.zeros([i.size(0)], dtype=torch.bool) for i in node_datas]
    padding_mask = torch.cat([pad_mask_unsqueeze(i, max_node_num) for i in padding_mask_list])

    edge_padding_mask_list = [torch.zeros([i.size(0)], dtype=torch.bool) for i in edge_datas]
    edge_padding_mask = torch.cat([pad_mask_unsqueeze(i, max_edge_num) for i in edge_padding_mask_list])

    node_data = torch.cat([i for i in node_datas])
    face_area = torch.cat([i for i in face_areas])
    face_type = torch.cat([i for i in face_types])
    face_loop = torch.cat([i for i in face_loops])
    face_adj = torch.cat([i for i in face_adjs])

    edge_data = torch.cat([i for i in edge_datas])
    edge_type = torch.cat([i for i in edge_types])
    edge_len = torch.cat([i for i in edge_lens])
    edge_ang = torch.cat([i for i in edge_angs])
    edge_conv = torch.cat([i for i in edge_convs])

    edge_path = torch.cat(
        [pad_3d_unsqueeze(i, max_node_num, max_node_num, max_dist) for i in edge_paths]
    ).long()

    attn_bias = torch.cat(
        [pad_attn_bias_unsqueeze(i, max_node_num + 1) for i in attn_biases]
    )

    spatial_pos = torch.cat(
        [pad_spatial_pos_unsqueeze(i, max_node_num) for i in spatial_poses]
    )
    d2_distance = torch.cat(
        [pad_d2_pos_unsqueeze(i, max_node_num) for i in d2_distances]
    )
    angle_distance = torch.cat(
        [pad_ang_pos_unsqueeze(i, max_node_num) for i in angle_distances]
    )

    in_degree = torch.cat([i for i in node_degrees])
    batched_graph = dgl.batch([i for i in graphs])
    batched_label_feature = torch.cat([i for i in label_features])
    data_ids = torch.tensor([i for i in data_ids])

    batch_data = dict(
        padding_mask=padding_mask,
        edge_padding_mask=edge_padding_mask,
        graph=batched_graph,
        node_data=node_data,
        face_area=face_area,
        face_type=face_type,
        face_loop=face_loop,
        face_adj=face_adj,
        edge_data=edge_data,
        edge_type=edge_type,
        edge_len=edge_len,
        edge_ang=edge_ang,
        edge_conv=edge_conv,
        in_degree=in_degree,
        out_degree=in_degree,
        attn_bias=attn_bias,
        spatial_pos=spatial_pos,
        d2_distance=d2_distance,
        angle_distance=angle_distance,
        edge_path=edge_path,
        label_feature=batched_label_feature,
        id=data_ids
    )
    return batch_data


def collator_st(items, multi_hop_max_dist, spatial_pos_max):
    """Source-Target 联合批处理（用于域适应训练）

    将源域和目标域数据联合批处理，用于域适应训练。
    每个 item 包含 source_data 和 target_data，函数将它们合并为一个批次。

    参数:
        items: 列表，每个元素为 dict，包含 'source_data' 和 'target_data'
        multi_hop_max_dist: 多跳最大距离
        spatial_pos_max: 空间位置最大值

    返回值:
        dict: 批次数据字典，包含填充掩码、图数据、节点/边特征等
    """
    # 提取源域数据项
    items_source = [
        (
            item["source_data"].graph,
            item["source_data"].node_data,
            item["source_data"].face_area,
            item["source_data"].face_type,
            item["source_data"].face_loop,
            item["source_data"].face_adj,
            item["source_data"].edge_data,
            item["source_data"].edge_type,
            item["source_data"].edge_len,
            item["source_data"].edge_ang,
            item["source_data"].edge_conv,
            item["source_data"].in_degree,
            item["source_data"].attn_bias,
            item["source_data"].spatial_pos,
            item["source_data"].d2_distance,
            item["source_data"].angle_distance,
            item["source_data"].edge_path[:, :, :multi_hop_max_dist],
            item["source_data"].label_feature,
            item["source_data"].data_id,
        )
        for item in items
    ]

    # 提取目标域数据项
    items_target = [
        (
            item["target_data"].graph,
            item["target_data"].node_data,
            item["target_data"].face_area,
            item["target_data"].face_type,
            item["target_data"].face_loop,
            item["target_data"].face_adj,
            item["target_data"].edge_data,
            item["target_data"].edge_type,
            item["target_data"].edge_len,
            item["target_data"].edge_ang,
            item["target_data"].edge_conv,
            item["target_data"].in_degree,
            item["target_data"].attn_bias,
            item["target_data"].spatial_pos,
            item["target_data"].d2_distance,
            item["target_data"].angle_distance,
            item["target_data"].edge_path[:, :, :multi_hop_max_dist],
            item["target_data"].label_feature,
            item["target_data"].data_id,
        )
        for item in items
    ]

    # 合并源域和目标域数据
    merged_items = items_source + items_target
    (
        graphs,
        node_datas,
        face_areas,
        face_types,
        face_loops,
        face_adjs,
        edge_datas,
        edge_types,
        edge_lens,
        edge_angs,
        edge_convs,
        node_degrees,
        attn_biases,
        spatial_poses,
        d2_distances,
        angle_distances,
        edge_paths,
        label_features,
        data_ids,
    ) = zip(*merged_items)

    # 处理注意力偏置：超出空间位置最大值的设为 -inf
    for idx, _ in enumerate(attn_biases):
        attn_biases[idx][1:, 1:][spatial_poses[idx] >= spatial_pos_max] = float("-inf")

    # 计算批次中最大节点数、边数、距离
    max_node_num = max(i.size(0) for i in node_datas)
    max_edge_num = max(i.size(0) for i in edge_datas)
    max_dist = max(i.size(-1) for i in edge_paths)
    max_dist = max(max_dist, multi_hop_max_dist)

    # 创建节点填充掩码
    padding_mask_list = [torch.zeros([i.size(0)], dtype=torch.bool) for i in node_datas]
    padding_mask = torch.cat([pad_mask_unsqueeze(i, max_node_num) for i in padding_mask_list])

    # 创建边填充掩码
    edge_padding_mask_list = [torch.zeros([i.size(0)], dtype=torch.bool) for i in edge_datas]
    edge_padding_mask = torch.cat([pad_mask_unsqueeze(i, max_edge_num) for i in edge_padding_mask_list])

    # 拼接节点相关数据
    node_data = torch.cat([i for i in node_datas])
    face_area = torch.cat([i for i in face_areas])
    face_type = torch.cat([i for i in face_types])
    face_loop = torch.cat([i for i in face_loops])
    face_adj = torch.cat([i for i in face_adjs])

    # 拼接边相关数据
    edge_data = torch.cat([i for i in edge_datas])
    edge_type = torch.cat([i for i in edge_types])
    edge_len = torch.cat([i for i in edge_lens])
    edge_ang = torch.cat([i for i in edge_angs])
    edge_conv = torch.cat([i for i in edge_convs])

    # 拼接并填充边路径
    edge_path = torch.cat(
        [pad_3d_unsqueeze(i, max_node_num, max_node_num, max_dist) for i in edge_paths]
    ).long()
    # 拼接并填充注意力偏置
    attn_bias = torch.cat([pad_attn_bias_unsqueeze(i, max_node_num + 1) for i in attn_biases])
    # 拼接并填充空间位置
    spatial_pos = torch.cat([pad_spatial_pos_unsqueeze(i, max_node_num) for i in spatial_poses])
    # 拼接并填充二阶距离
    d2_distance = torch.cat([pad_d2_pos_unsqueeze(i, max_node_num) for i in d2_distances])
    # 拼接并填充角度距离
    angle_distance = torch.cat([pad_ang_pos_unsqueeze(i, max_node_num) for i in angle_distances])

    # 拼接节点度数
    in_degree = torch.cat([i for i in node_degrees])
    # 批次化图
    batched_graph = dgl.batch([i for i in graphs])
    # 拼接标签特征
    batched_label_feature = torch.cat([i for i in label_features])
    # 数据ID
    data_ids = torch.tensor([i for i in data_ids])

    # 返回批次字典
    return dict(
        padding_mask=padding_mask,
        edge_padding_mask=edge_padding_mask,
        graph=batched_graph,
        node_data=node_data,
        face_area=face_area,
        face_type=face_type,
        face_loop=face_loop,
        face_adj=face_adj,
        edge_data=edge_data,
        edge_type=edge_type,
        edge_len=edge_len,
        edge_ang=edge_ang,
        edge_conv=edge_conv,
        in_degree=in_degree,
        out_degree=in_degree,
        attn_bias=attn_bias,
        spatial_pos=spatial_pos,
        d2_distance=d2_distance,
        angle_distance=angle_distance,
        edge_path=edge_path,
        label_feature=batched_label_feature,
        id=data_ids,
    )
