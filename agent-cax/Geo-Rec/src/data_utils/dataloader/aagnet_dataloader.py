import pathlib
import json
import logging
import os
from flask import config
import torch
import dgl
import numpy as np
from src.data_utils.dataloader.aagnet_dataloader_base import BaseDataset,BaseDataset_single_graph
from src.utils.base_functions import load_one_graph,load_split_filelist,load_config_basic


class MFInstSegDataset(BaseDataset):
    def __init__(self,
                 root_dir,
                 graphs=None,
                 split="train",
                 normalize=True,
                 center_and_scale=True,
                 random_rotate=False,
                 transform=None,
                 num_threads=0,
                 labels_dir="labels"):
        """
        加载 MFInstSeg 数据集

        参数:
            root_dir (str): 数据集的根目录
            graphs (list, optional): 图数据列表
            split (str, optional): 要加载的数据分割。默认为 "train"
            normalize (bool, optional): 是否归一化数据。默认为 True
            center_and_scale (bool, optional): 是否对实体进行中心和缩放。默认为 True
            random_rotate (bool, optional): 是否对实体应用随机旋转（90度增量）。默认为 False
            num_train_data (int, optional): 要使用的训练示例数。默认为 -1（使用所有训练示例）
            transform (callable, optional): 要应用于数据的转换
            dataset_type (str, optional): 要加载的数据集类型。默认为 "full"（已忽略，保留参数是为了兼容性）
            num_threads (int, optional): 用于数据加载的线程数。默认为 0
        """
        path = pathlib.Path(root_dir)
        self.path = path
        self.transform = transform
        self.random_rotate = random_rotate
        self.labels_dir = labels_dir  # 存储标签文件夹名称
        # dataset_type 参数被保留但不使用，只是为了兼容性
        assert split in ("train", "val", "test", "all")
        # 从 train.txt valid.txt test.txt 文件加载数据分区
        split_filelist = load_split_filelist(split)
        # 加载图
        print(f"Loading {split} data...")
        split_filelist = set(split_filelist)
        graph_path = path.joinpath("graphs")
        self.load_graphs(graph_path, graphs, split_filelist, center_and_scale, normalize, num_threads)
        print("Done loading {} files".format(len(self.data)))

    def _get_filenames(self, root_dir):
        """
        获取指定数据分割的文件名列表

        参数:
            root_dir (str): 数据集的根路径

        返回:
            List[str]: 文件名列表
        """
        step_dir = os.path.join(root_dir, 'steps')
        step_dir = pathlib.Path(step_dir)
        files = list(
            x.stem for x in step_dir.rglob(f"*.st*p")
        )
        return files

    def _collate(self, batch):
        """
        将一批数据样本合并成一个批次

        参数:
            batch (List[dict]): 数据样本列表

        返回:
            dict: 批处理数据
        """
        batched_graph = dgl.batch([sample["graph"] for sample in batch])
        inst_labels = self.pack_pad_2D_adj(batch)
        batched_filenames = [sample["filename"] for sample in batch]
        return {"graph": batched_graph,
                "inst_labels": inst_labels,
                "filename": batched_filenames}

    def pack_pad_2D_adj(self, batch):
        """
        打包和填充批次中每个图的2D邻接矩阵
        """
        max_num_nodes = max([sample["inst_y"].shape[0] for sample in batch])
        batched_adj = torch.zeros(len(batch), max_num_nodes, max_num_nodes, dtype=torch.float)
        for i, sample in enumerate(batch):
            adj = sample["inst_y"]
            num_nodes = sample["inst_y"].shape[0]
            batched_adj[i, :num_nodes, :num_nodes] = adj
        return batched_adj

    def load_one_graph(self, fn, data):
        """
        加载单个文件的数据

        参数:
            fn (str): 文件名
            data (dict): 文件的数据

        返回:
            dict: 文件的数据
        """
        # 使用基类方法加载图
        sample = load_one_graph(fn, data)
        num_faces = sample['graph'].num_nodes()
        # 额外加载标签并存储为节点数据
        label_file = self.path.joinpath(self.labels_dir).joinpath(fn + ".json")
        with open(str(label_file), "r") as read_file:
            labels_data = json.load(read_file)
        _, labels = labels_data[0]
        seg_label, inst_label, bottom_label = labels['seg'], labels['inst'], labels['bottom']
        assert len(seg_label) == len(inst_label) and len(seg_label) == len(bottom_label), \
            'have wrong label: ' + fn
        if num_faces != len(seg_label):
            logging.warning(f'跳过 {fn}：标注面数({len(seg_label)})与graph面数({num_faces})不匹配')
            return None

        # 二分类标签处理：将所有非零标签转换为1
        face_segmentaion_labels = np.zeros(num_faces)
        for idx, face_id in enumerate(range(num_faces)):
            index = seg_label[str(face_id)]
            # 将所有非零标签转换为1，零标签保持为0
            face_segmentaion_labels[idx] = 1 if index != 0 else 0

        # 读取实例分割标签 - 只是一个面邻接矩阵
        instance_label = np.array(inst_label, dtype=np.int32)

        # 读取底面分割标签 - 已经是二分类（0或1）
        bottom_segmentaion_labels = np.zeros(num_faces)
        for idx, face_id in enumerate(range(num_faces)):
            index = bottom_label[str(face_id)]
            bottom_segmentaion_labels[idx] = index

        # 转换为torch数组
        sample["graph"].ndata["seg_y"] = torch.tensor(face_segmentaion_labels).long()
        sample["inst_y"] = torch.tensor(instance_label).float()
        sample["graph"].ndata["bottom_y"] = torch.tensor(bottom_segmentaion_labels).float().reshape(-1, 1)
        return sample


class MFInstSegDataset_single_graph(BaseDataset_single_graph):
    def __init__(self,
                 root_dir,
                 graphs=None,
                 split="train",
                 normalize=True,
                 center_and_scale=True,
                 random_rotate=False,
                 transform=None,
                 num_threads=0,
                 labels_dir="labels"):
        super().__init__(transform, random_rotate)
        path = pathlib.Path(root_dir)
        self.path = path
        self.transform = transform
        self.random_rotate = random_rotate
        self.labels_dir = labels_dir  # 存储标签文件夹名称
        # dataset_type 参数被保留但不使用，只是为了兼容性
        assert split in ("train", "val", "test", "all")
        # 从 train.txt valid.txt test.txt 文件加载数据分区
        split_filelist = load_split_filelist(split)
        # 加载图
        print(f"Loading {split} data...")
        split_filelist = set(split_filelist)
        self.load_graphs(path, graphs, split_filelist, center_and_scale, normalize, num_threads)
        print("Done loading {} files".format(len(self.data)))

    def _get_filenames(self, root_dir):
        """
        获取指定数据分割的文件名列表

        参数:
            root_dir (str): 数据集的根路径

        返回:
            List[str]: 文件名列表
        """
        step_dir = os.path.join(root_dir, 'steps')
        step_dir = pathlib.Path(step_dir)
        files = list(
            x.stem for x in step_dir.rglob(f"*.st*p")
        )
        return files

    def _collate(self, batch):
        """
        将一批数据样本合并成一个批次

        参数:
            batch (List[dict]): 数据样本列表

        返回:
            dict: 批处理数据
        """
        batched_graph = dgl.batch([sample["graph"] for sample in batch])
        inst_labels = self.pack_pad_2D_adj(batch)
        batched_filenames = [sample["filename"] for sample in batch]
        return {"graph": batched_graph,
                "inst_labels": inst_labels,
                "filename": batched_filenames}

    def pack_pad_2D_adj(self, batch):
        """
        打包和填充批次中每个图的2D邻接矩阵
        """
        max_num_nodes = max([sample["inst_y"].shape[0] for sample in batch])
        batched_adj = torch.zeros(len(batch), max_num_nodes, max_num_nodes, dtype=torch.float)
        for i, sample in enumerate(batch):
            adj = sample["inst_y"]
            num_nodes = sample["inst_y"].shape[0]
            batched_adj[i, :num_nodes, :num_nodes] = adj
        return batched_adj

    def load_one_graph(self, fn, data):
        """
        加载单个文件的数据

        参数:
            fn (str): 文件名
            data (dict): 文件的数据

        返回:
            dict: 文件的数据
        """
        # 使用基类方法加载图
        sample = load_one_graph(fn, data)
        num_faces = sample['graph'].num_nodes()
        # 额外加载标签并存储为节点数据
        label_file = self.path.joinpath(self.labels_dir).joinpath(fn + ".json")
        with open(str(label_file), "r") as read_file:
            labels_data = json.load(read_file)
        _, labels = labels_data[0]
        seg_label, inst_label, bottom_label = labels['seg'], labels['inst'], labels['bottom']
        assert len(seg_label) == len(inst_label) and len(seg_label) == len(bottom_label), \
            'have wrong label: ' + fn
        if num_faces != len(seg_label):
            logging.warning(f'跳过 {fn}：标注面数({len(seg_label)})与graph面数({num_faces})不匹配')
            return None

        # 二分类标签处理：将所有非零标签转换为1
        face_segmentaion_labels = np.zeros(num_faces)
        for idx, face_id in enumerate(range(num_faces)):
            index = seg_label[str(face_id)]
            # 将所有非零标签转换为1，零标签保持为0
            face_segmentaion_labels[idx] = 1 if index != 0 else 0

        # 读取实例分割标签 - 只是一个面邻接矩阵
        instance_label = np.array(inst_label, dtype=np.int32)

        # 读取底面分割标签 - 已经是二分类（0或1）
        bottom_segmentaion_labels = np.zeros(num_faces)
        for idx, face_id in enumerate(range(num_faces)):
            index = bottom_label[str(face_id)]
            bottom_segmentaion_labels[idx] = index

        # 转换为torch数组
        sample["graph"].ndata["seg_y"] = torch.tensor(face_segmentaion_labels).long()
        sample["inst_y"] = torch.tensor(instance_label).float()
        sample["graph"].ndata["bottom_y"] = torch.tensor(bottom_segmentaion_labels).float().reshape(-1, 1)
        return sample

if __name__ == '__main__':
    dataset = MFInstSegDataset(root_dir='E:\几何特征提取\AAGNet_v2\data3', split='test', center_and_scale=True,
                               normalize=False,labels_dir="long_solt_hole_labels")
    print(dataset[0])
    