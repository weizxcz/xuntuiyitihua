"""CAD 脚本执行参数定义"""
from pydantic import BaseModel
from typing import List, Optional, Any


class NewNctiParams(BaseModel):
    """新建 NCTI 文档参数"""
    md_type: str = "OCC"
    cs_type: str = "DCM"
    new_ncti_path: str
    is_assembly: int = 0


class ExecScriptParams(BaseModel):
    """执行脚本参数"""
    obj_names: Optional[List[str]] = []
    cell_ids: Optional[List[str]] = []
    script: str
    ncti_path: str
    new_ncti_path: str
    task_id: Optional[str] = None
    need_yh: bool = True  # 是否需要 YH 模块和 yh_doc 对象（草图脚本需要，建模脚本不需要）


class ExecScriptResp(BaseModel):
    """执行脚本响应"""
    is_update: bool = False
    has_selected: bool = False
    selected_object_Names: Optional[List[str]] = []
    selected_cell_ids: Optional[List[str]] = []
    export_files: Optional[List[str]] = []


class RunScriptContentParams(BaseModel):
    """运行脚本内容参数"""
    md_type: str = "OCC"
    cs_type: str = "DCM"
    mesh_type: Optional[str] = None
    script_content: str
