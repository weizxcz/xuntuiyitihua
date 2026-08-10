"""
BrepMFR CADSynth 数据集，来源：BrepMFR-main/data/dataset.py
"""
import os
import pathlib
import random
import torch
from torch import FloatTensor
from torch.utils.data import Dataset
from torch_geometric.data import Data as PYGGraph
from dgl.data.utils import load_graphs
from tqdm import tqdm

from src.data_utils.dataloader.brepmfr_collator import collator, collator_st
from src.data_utils.dataloader.brepmfr_utils import get_random_rotation, rotate_uvgrid


class CADSynth(Dataset):
    """CAD 合成数据集 - B-rep 模型的主要输入数据"""

    def __init__(
        self,
        root_dir,
        split="train",
        random_rotate=False,
        num_class=25,
        splits_dir=None,
    ):
        """
        参数:
            root_dir: 数据集根目录（含 bin/ 子目录）
            split: 'train', 'val', 'test'
            random_rotate: 是否启用随机旋转数据增强
            num_class: 特征类别数量
            splits_dir: 可选，train.txt/val.txt/test.txt 所在目录，默认用 root_dir
        """
        assert split in ("train", "val", "test")
        path = pathlib.Path(root_dir)
        self.split = split
        self.num_class = num_class
        self.random_rotate = random_rotate
        self.file_paths = []
        splits_path = pathlib.Path(splits_dir) if splits_dir else path
        filelist_path = splits_path / f"{split}.txt"
        self._get_filenames(path, filelist_path)

    def _get_filenames(self, root_dir, filelist_path):
        with open(str(filelist_path), "r", encoding="utf-8") as f:
            file_list = [x.strip() for x in f.readlines()]

        bin_dir = root_dir / "bin"
        if not bin_dir.exists():
            bin_dir = root_dir
        for x in tqdm(list(bin_dir.rglob("*.bin")), desc=f"加载 {self.split} 数据"):
            if x.stem in file_list:
                self.file_paths.append(x)

    def load_one_graph(self, file_path):
        graphfile = load_graphs(str(file_path))
        graph = graphfile[0][0]

        pyg_graph = PYGGraph()
        pyg_graph.graph = graph

        if self.random_rotate:
            rotation = get_random_rotation()
            graph.ndata["x"] = rotate_uvgrid(graph.ndata["x"], rotation)
            graph.edata["x"] = rotate_uvgrid(graph.edata["x"], rotation)

        pyg_graph.node_data = graph.ndata["x"].type(FloatTensor)
        pyg_graph.edge_data = graph.edata["x"].type(FloatTensor)
        pyg_graph.face_type = graph.ndata["z"].type(torch.int)
        pyg_graph.face_area = graph.ndata["y"].type(torch.float)
        pyg_graph.face_loop = graph.ndata["l"].type(torch.int)
        pyg_graph.face_adj = graph.ndata["a"].type(torch.int)
        pyg_graph.label_feature = graph.ndata["f"].type(torch.int)
        pyg_graph.edge_type = graph.edata["t"].type(torch.int)
        pyg_graph.edge_len = graph.edata["l"].type(torch.float)
        pyg_graph.edge_ang = graph.edata["a"].type(torch.float)
        pyg_graph.edge_conv = graph.edata["c"].type(torch.int)

        dense_adj = graph.adj().to_dense().type(torch.int)
        n_nodes = graph.num_nodes()
        pyg_graph.node_degree = dense_adj.long().sum(dim=1).view(-1)
        pyg_graph.attn_bias = torch.zeros([n_nodes + 1, n_nodes + 1], dtype=torch.float)

        pyg_graph.edge_path = graphfile[1]["edges_path"]
        pyg_graph.spatial_pos = graphfile[1]["spatial_pos"]
        pyg_graph.d2_distance = graphfile[1]["d2_distance"]
        pyg_graph.angle_distance = graphfile[1]["angle_distance"]

        basename = os.path.splitext(os.path.basename(file_path))[0]
        try:
            pyg_graph.data_id = int(basename.split("_")[-1])
        except ValueError:
            pyg_graph.data_id = hash(basename) % (2**31)

        return pyg_graph

    def __len__(self):
        return len(self.file_paths)

    def __getitem__(self, idx):
        return self.load_one_graph(self.file_paths[idx])

    def _collate(self, batch):
        return collator(
            batch,
            multi_hop_max_dist=16,
            spatial_pos_max=32,
        )

    def get_dataloader(self, batch_size, shuffle=True, num_workers=0):
        try:
            from prefetch_generator import BackgroundGenerator

            class _DataLoaderX(torch.utils.data.DataLoader):
                def __iter__(self):
                    return BackgroundGenerator(super().__iter__())

            return _DataLoaderX(
                dataset=self,
                batch_size=batch_size,
                shuffle=shuffle,
                collate_fn=self._collate,
                num_workers=num_workers,
                drop_last=True,
                pin_memory=True,
                prefetch_factor=2 if num_workers > 0 else None,
            )
        except ImportError:
            return torch.utils.data.DataLoader(
                dataset=self,
                batch_size=batch_size,
                shuffle=shuffle,
                collate_fn=self._collate,
                num_workers=num_workers,
                drop_last=True,
                pin_memory=True,
            )


class TransferDataset(Dataset):
    """域适应数据集：source(有标签) + target(无标签/弱标签)"""

    def __init__(
        self,
        root_dir_source,
        root_dir_target,
        split="train",
        random_rotate=False,
        num_class=25,
        open_set=0,
        source_splits_dir=None,
        target_splits_dir=None,
    ):
        assert split in ("train", "val", "test")
        self.split = split
        self.random_rotate = random_rotate
        self.num_class = num_class
        self.open_set = bool(open_set)
        self.source_root = pathlib.Path(root_dir_source)
        self.target_root = pathlib.Path(root_dir_target)
        self.source_splits_dir = pathlib.Path(source_splits_dir) if source_splits_dir else self.source_root
        self.target_splits_dir = pathlib.Path(target_splits_dir) if target_splits_dir else self.target_root

        self.source_file_paths = []
        self.target_file_paths = []
        self._get_filenames()

    def _resolve_split_files(self):
        prefix = {"train": "train", "val": "val", "test": "test"}[self.split]
        source_file = self.source_splits_dir / f"s_{prefix}.txt"
        target_file = self.target_splits_dir / f"t_{prefix}.txt"
        return source_file, target_file

    def _collect_bin_files(self, root_dir):
        bin_dir = root_dir / "bin"
        if bin_dir.exists():
            return list(bin_dir.rglob("*.bin"))
        return list(root_dir.rglob("*.bin"))

    def _get_filenames(self):
        source_list_file, target_list_file = self._resolve_split_files()
        with open(str(source_list_file), "r", encoding="utf-8") as f:
            source_ids = {x.strip() for x in f.readlines() if x.strip()}
        with open(str(target_list_file), "r", encoding="utf-8") as f:
            target_ids = {x.strip() for x in f.readlines() if x.strip()}

        for x in tqdm(self._collect_bin_files(self.source_root), desc=f"加载 source-{self.split}"):
            if x.stem in source_ids:
                if self.open_set:
                    graphfile = load_graphs(str(x))
                    face_labels = graphfile[0][0].ndata["f"].type(torch.int)
                    if torch.max(face_labels) > self.num_class:
                        continue
                self.source_file_paths.append(x)

        for x in tqdm(self._collect_bin_files(self.target_root), desc=f"加载 target-{self.split}"):
            if x.stem in target_ids:
                if self.open_set:
                    graphfile = load_graphs(str(x))
                    face_labels = graphfile[0][0].ndata["f"].type(torch.int)
                    if torch.max(face_labels) > self.num_class:
                        continue
                self.target_file_paths.append(x)

        if self.split != "test":
            random.shuffle(self.source_file_paths)
            random.shuffle(self.target_file_paths)

    def load_one_graph(self, file_path):
        graphfile = load_graphs(str(file_path))
        graph = graphfile[0][0]
        pyg_graph = PYGGraph()
        pyg_graph.graph = graph

        if self.random_rotate:
            rotation = get_random_rotation()
            graph.ndata["x"] = rotate_uvgrid(graph.ndata["x"], rotation)
            graph.edata["x"] = rotate_uvgrid(graph.edata["x"], rotation)

        pyg_graph.node_data = graph.ndata["x"].type(FloatTensor)
        pyg_graph.edge_data = graph.edata["x"].type(FloatTensor)
        pyg_graph.face_type = graph.ndata["z"].type(torch.int)
        pyg_graph.face_area = graph.ndata["y"].type(torch.float)
        pyg_graph.face_loop = graph.ndata["l"].type(torch.int)
        pyg_graph.face_adj = graph.ndata["a"].type(torch.int)
        pyg_graph.label_feature = graph.ndata["f"].type(torch.int)
        pyg_graph.edge_type = graph.edata["t"].type(torch.int)
        pyg_graph.edge_len = graph.edata["l"].type(torch.float)
        pyg_graph.edge_ang = graph.edata["a"].type(torch.float)
        pyg_graph.edge_conv = graph.edata["c"].type(torch.int)

        dense_adj = graph.adj().to_dense().type(torch.int)
        n_nodes = graph.num_nodes()
        pyg_graph.in_degree = dense_adj.long().sum(dim=1).view(-1)
        pyg_graph.attn_bias = torch.zeros([n_nodes + 1, n_nodes + 1], dtype=torch.float)
        pyg_graph.edge_path = graphfile[1]["edges_path"]
        pyg_graph.spatial_pos = graphfile[1]["spatial_pos"]
        pyg_graph.d2_distance = graphfile[1]["d2_distance"]
        pyg_graph.angle_distance = graphfile[1]["angle_distance"]

        basename = os.path.splitext(os.path.basename(file_path))[0]
        try:
            pyg_graph.data_id = int(basename.split("_")[-1])
        except ValueError:
            pyg_graph.data_id = hash(basename) % (2**31)
        return pyg_graph

    def __len__(self):
        # 对于域适应训练，每个epoch只迭代target数据集的长度次数
        # 这样可以确保每个target样本都被使用，同时避免过多的迭代
        # return max(len(self.source_file_paths), len(self.target_file_paths))
        return len(self.target_file_paths)*2

    def __getitem__(self, idx):
        idx_s = idx if idx < len(self.source_file_paths) else random.randint(0, len(self.source_file_paths) - 1)
        idx_t = idx if idx < len(self.target_file_paths) else random.randint(0, len(self.target_file_paths) - 1)
        sample_s = self.load_one_graph(self.source_file_paths[idx_s])
        sample_t = self.load_one_graph(self.target_file_paths[idx_t])
        return {"source_data": sample_s, "target_data": sample_t}

    def _collate(self, batch):
        return collator_st(
            batch,
            multi_hop_max_dist=16,
            spatial_pos_max=32,
        )

    def get_dataloader(self, batch_size, shuffle=True, num_workers=0):
        return torch.utils.data.DataLoader(
            dataset=self,
            batch_size=batch_size,
            shuffle=shuffle,
            collate_fn=self._collate,
            num_workers=num_workers,
            drop_last=True,
            pin_memory=True,
            prefetch_factor=2 if num_workers > 0 else None,
            persistent_workers=False,
        )
