from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, distinct
from app.database.models import PartInfo


def create_part(db: Session, part_data: dict) -> PartInfo:
    """创建新零件记录

    Args:
        db: 数据库会话对象
        part_data: 零件数据字典，包含所有字段信息

    Returns:
        PartInfo: 创建成功的零件对象
    """
    db_part = PartInfo(**part_data)
    db.add(db_part)
    db.commit()
    db.refresh(db_part)
    return db_part


def get_part_by_id(db: Session, part_id: int) -> Optional[PartInfo]:
    """根据ID获取零件记录

    Args:
        db: 数据库会话对象
        part_id: 零件ID

    Returns:
        Optional[PartInfo]: 找到的零件对象，未找到返回None
    """
    return db.query(PartInfo).filter(PartInfo.id == part_id).first()


def get_part_by_hash_id(db: Session, hash_id: str) -> Optional[PartInfo]:
    """根据哈希ID获取零件记录

    Args:
        db: 数据库会话对象
        hash_id: 文件哈希值

    Returns:
        Optional[PartInfo]: 找到的零件对象，未找到返回None
    """
    return db.query(PartInfo).filter(PartInfo.hash_id == hash_id).first()


def get_parts(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    industry: Optional[str] = None,
    product_type: Optional[str] = None,
    format_type: Optional[str] = None,
    is_open_source: Optional[bool] = None,
    source_type: Optional[str] = None,
    has_round: Optional[bool] = None,
    has_chamfer: Optional[bool] = None,
    has_countersink_hole: Optional[bool] = None,
    has_counterbore_hole: Optional[bool] = None,
    has_through_hole: Optional[bool] = None,
    has_blind_hole: Optional[bool] = None,
) -> List[PartInfo]:
    query = db.query(PartInfo)

    if industry:
        query = query.filter(PartInfo.industry == industry)
    if product_type:
        query = query.filter(PartInfo.product_type == product_type)
    if format_type:
        query = query.filter(PartInfo.format == format_type)
    if is_open_source is not None:
        query = query.filter(PartInfo.is_open_source == is_open_source)
    if source_type:
        query = query.filter(PartInfo.source_type == source_type)
    if has_round is not None:
        query = query.filter(PartInfo.has_round == has_round)
    if has_chamfer is not None:
        query = query.filter(PartInfo.has_chamfer == has_chamfer)
    if has_countersink_hole is not None:
        query = query.filter(PartInfo.has_countersink_hole == has_countersink_hole)
    if has_counterbore_hole is not None:
        query = query.filter(PartInfo.has_counterbore_hole == has_counterbore_hole)
    if has_through_hole is not None:
        query = query.filter(PartInfo.has_through_hole == has_through_hole)
    if has_blind_hole is not None:
        query = query.filter(PartInfo.has_blind_hole == has_blind_hole)

    return query.offset(skip).limit(limit).all()


def get_parts_by_label_status(
    db: Session,
    label_statuses: dict = None,
    limit: int = 100,
) -> List[PartInfo]:
    """根据标注状态筛选零件

    Args:
        db: 数据库会话对象
        label_statuses: 标注状态字典，例如 {"label_round_status": "pending", "label_chamfer_status": "completed"}
        limit: 返回的最大记录数，默认100

    Returns:
        List[PartInfo]: 满足所有标注状态条件的零件列表
    """
    query = db.query(PartInfo)

    if label_statuses:
        for field_name, status in label_statuses.items():
            if hasattr(PartInfo, field_name):
                query = query.filter(getattr(PartInfo, field_name) == status)

    return query.limit(limit).all()


def update_part(db: Session, part_id: int, update_data: dict) -> Optional[PartInfo]:
    """更新零件信息

    Args:
        db: 数据库会话对象
        part_id: 零件ID
        update_data: 更新的数据字典

    Returns:
        Optional[PartInfo]: 更新后的零件对象，未找到返回None
    """
    db_part = db.query(PartInfo).filter(PartInfo.id == part_id).first()
    if db_part:
        for key, value in update_data.items():
            if hasattr(db_part, key):
                setattr(db_part, key, value)
        db.commit()
        db.refresh(db_part)
    return db_part


def update_label_status(
    db: Session,
    part_id: int,
    feature_type: str,
    status: str,
    modified_by: Optional[str] = None,
) -> Optional[PartInfo]:
    """更新指定特征的标注状态

    Args:
        db: 数据库会话对象
        part_id: 零件ID
        feature_type: 特征类型，取值: round, chamfer, countersink_hole, counterbore_hole, through_hole, blind_hole
        status: 标注状态，取值: pending, in_progress, completed, skipped, error
        modified_by: 修改人标识

    Returns:
        Optional[PartInfo]: 更新后的零件对象，无效特征类型返回None
    """
    feature_status_map = {
        "round": "label_round_status",
        "chamfer": "label_chamfer_status",
        "countersink_hole": "label_countersink_hole_status",
        "counterbore_hole": "label_counterbore_hole_status",
        "through_hole": "label_through_hole_status",
        "blind_hole": "label_blind_hole_status",
    }

    if feature_type not in feature_status_map:
        return None

    update_data = {feature_status_map[feature_type]: status}
    if modified_by:
        update_data["modified_by"] = modified_by

    return update_part(db, part_id, update_data)


def delete_part(db: Session, part_id: int) -> bool:
    """删除零件记录

    Args:
        db: 数据库会话对象
        part_id: 零件ID

    Returns:
        bool: 删除成功返回True，未找到返回False
    """
    db_part = db.query(PartInfo).filter(PartInfo.id == part_id).first()
    if db_part:
        db.delete(db_part)
        db.commit()
        return True
    return False


def count_parts(db: Session, industry: Optional[str] = None) -> int:
    """统计零件数量

    Args:
        db: 数据库会话对象
        industry: 行业分类筛选（可选）

    Returns:
        int: 零件数量
    """
    query = db.query(PartInfo)
    if industry:
        query = query.filter(PartInfo.industry == industry)
    return query.count()


def get_distinct_fields(db: Session, industry: Optional[str] = None) -> dict:
    """获取所有去重的行业和产品类型列表

    Args:
        industry: 指定行业时只返回该行业下的产品类型

    Returns:
        dict: {"industries": [...], "product_types": [...]}
    """
    industries = [r[0] for r in db.query(distinct(PartInfo.industry)).filter(PartInfo.industry.isnot(None)).all()]
    pt_query = db.query(distinct(PartInfo.product_type)).filter(PartInfo.product_type.isnot(None))
    if industry:
        pt_query = pt_query.filter(PartInfo.industry == industry)
    product_types = [r[0] for r in pt_query.all()]
    return {"industries": sorted(industries), "product_types": sorted(product_types)}
