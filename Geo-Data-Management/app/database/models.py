from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base


class PartInfo(Base):
    """零件信息数据模型

    该模型用于存储STP/STEP/IGS等CAD模型文件的基本信息，支持对零件特征（圆角、倒角、孔等）的标注和管理。

    Attributes:
        __tablename__: 数据库表名，固定为 'part_info'
    """
    __tablename__ = "part_info"

    id = Column(Integer, primary_key=True, autoincrement=True)
    """int: 主键，自增，唯一标识每条记录"""

    hash_id = Column(String(64), nullable=False, unique=True)
    """str: 文件内容的哈希值（如SHA256），用于唯一标识文件，避免重复上传"""

    name = Column(String(255), nullable=False)
    """str: 原始文件名，不含路径"""

    created_time = Column(DateTime, nullable=False, server_default=func.now())
    """datetime: 记录创建时间，自动生成"""

    modified_time = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    """datetime: 记录最后修改时间，每次更新自动刷新"""

    created_by = Column(String(100))
    """str: 创建该记录的用户标识"""

    modified_by = Column(String(100))
    """str: 最后修改该记录的用户标识"""

    format = Column(String(10), nullable=False)
    """str: 文件格式，取值范围: stp, step, igs"""

    is_open_source = Column(Boolean, default=False)
    """bool: 是否开源，TRUE表示开源，FALSE表示私有"""

    source_type = Column(String(20), default="private")
    """str: 数据来源类型，取值: public(公开数据集), private(自有数据)"""

    industry = Column(String(50))
    """str: 零件所属行业，如: 家电、汽车、航空航天、机械制造、电子设备等"""

    product_type = Column(String(100))
    """str: 零件所属的具体产品，如: 冰箱、发动机、齿轮等"""

    has_round = Column(Boolean, default=False)
    """bool: 模型是否包含圆角特征"""

    has_chamfer = Column(Boolean, default=False)
    """bool: 模型是否包含倒角特征"""

    has_countersink_hole = Column(Boolean, default=False)
    """bool: 模型是否包含沉头孔特征"""

    has_counterbore_hole = Column(Boolean, default=False)
    """bool: 模型是否包含沉孔特征"""

    has_through_hole = Column(Boolean, default=False)
    """bool: 模型是否包含通孔特征"""

    has_blind_hole = Column(Boolean, default=False)
    """bool: 模型是否包含盲孔特征"""

    label_round_status = Column(String(20), default="pending")
    """str: 圆角标注状态，取值: pending(待标注), in_progress(标注中), completed(已完成), skipped(跳过), error(标注异常)"""

    label_chamfer_status = Column(String(20), default="pending")
    """str: 倒角标注状态"""

    label_countersink_hole_status = Column(String(20), default="pending")
    """str: 沉头孔标注状态"""

    label_counterbore_hole_status = Column(String(20), default="pending")
    """str: 沉孔标注状态"""

    label_through_hole_status = Column(String(20), default="pending")
    """str: 通孔标注状态"""

    label_blind_hole_status = Column(String(20), default="pending")
    """str: 盲孔标注状态"""

    def __repr__(self):
        """返回对象的字符串表示"""
        return f"<PartInfo(id={self.id}, name='{self.name}', format='{self.format}')>"

    def to_dict(self):
        """将模型对象转换为字典

        Returns:
            dict: 包含所有字段的字典，datetime类型转换为ISO格式字符串
        """
        return {
            "id": self.id,
            "hash_id": self.hash_id,
            "name": self.name,
            "created_time": self.created_time.isoformat() if self.created_time else None,
            "modified_time": self.modified_time.isoformat() if self.modified_time else None,
            "created_by": self.created_by,
            "modified_by": self.modified_by,
            "format": self.format,
            "is_open_source": self.is_open_source,
            "source_type": self.source_type,
            "industry": self.industry,
            "product_type": self.product_type,
            "has_round": self.has_round,
            "has_chamfer": self.has_chamfer,
            "has_countersink_hole": self.has_countersink_hole,
            "has_counterbore_hole": self.has_counterbore_hole,
            "has_through_hole": self.has_through_hole,
            "has_blind_hole": self.has_blind_hole,
            "label_round_status": self.label_round_status,
            "label_chamfer_status": self.label_chamfer_status,
            "label_countersink_hole_status": self.label_countersink_hole_status,
            "label_counterbore_hole_status": self.label_counterbore_hole_status,
            "label_through_hole_status": self.label_through_hole_status,
            "label_blind_hole_status": self.label_blind_hole_status,
        }
