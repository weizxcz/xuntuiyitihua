import os
import json
import hashlib

from flask import Blueprint, Response, request, jsonify, current_app, send_file
from app.database import get_db
from app.database.crud import (
    create_part,
    get_part_by_id,
    get_part_by_hash_id,
    get_parts,
    get_parts_by_label_status,
    update_part,
    update_label_status,
    delete_part,
    count_parts,
    get_distinct_fields,
)
from utils.logger import get_logger

api_bp = Blueprint("api", __name__)
"""Flask Blueprint对象，用于注册零件数据管理相关API路由"""

logger = get_logger()


@api_bp.route("parts/filter_options", methods=["GET"])
def filter_options():
    """获取所有去重的行业和产品类型列表

    GET /parts/filter_options?industry=xxx

    Returns:
        JSON: {"code": 0, "data": {"industries": [...], "product_types": [...]}}
    """
    industry = request.args.get("industry")
    db = next(get_db())
    try:
        return jsonify({"code": 0, "data": get_distinct_fields(db, industry)})
    finally:
        db.close()


@api_bp.route("parts/list_parts", methods=["POST"])
def list_parts():
    """获取零件列表（支持分页和多条件筛选）

    POST /list_parts

    Request Body:
        {
            "skip": 0,
            "limit": 100,
            "industry": "行业分类",
            "product_type": "产品类型",
            "format": "文件格式",
            "is_open_source": true/false,
            "source_type": "public/private"
        }

    Returns:
        JSON: {"code": 0, "data": [part1, part2, ...]}
    """
    db = next(get_db())
    try:
        data = request.get_json() if request.get_json() else {}
        skip = data.get("skip", 0)
        limit = data.get("limit", 100)
        industry = data.get("industry")
        product_type = data.get("product_type")
        format_type = data.get("format")
        is_open_source = data.get("is_open_source")
        source_type = data.get("source_type")
        def _to_bool(v):
            if v is None:
                return None
            if isinstance(v, bool):
                return v
            return str(v).lower() == "true"

        has_round = _to_bool(data.get("has_round"))
        has_chamfer = _to_bool(data.get("has_chamfer"))
        has_countersink_hole = _to_bool(data.get("has_countersink_hole"))
        has_counterbore_hole = _to_bool(data.get("has_counterbore_hole"))
        has_through_hole = _to_bool(data.get("has_through_hole"))
        has_blind_hole = _to_bool(data.get("has_blind_hole"))

        parts = get_parts(
            db,
            skip=int(skip),
            limit=int(limit),
            industry=industry,
            product_type=product_type,
            format_type=format_type,
            is_open_source=is_open_source,
            source_type=source_type,
            has_round=has_round,
            has_chamfer=has_chamfer,
            has_countersink_hole=has_countersink_hole,
            has_counterbore_hole=has_counterbore_hole,
            has_through_hole=has_through_hole,
            has_blind_hole=has_blind_hole,
        )
        return jsonify({"code": 0, "data": [p.to_dict() for p in parts]})
    finally:
        db.close()


@api_bp.route("/parts/get_part", methods=["POST"])
def get_part():
    """根据ID获取单个零件详情

    POST /parts/get_part

    Request Body:
        {
            "part_id": 零件ID
        }

    Returns:
        JSON: {"code": 0, "data": part} - 成功
        JSON: {"code": 400, "message": "Missing part_id"} - 缺少参数
        JSON: {"code": 404, "message": "Part not found"} - 未找到
    """
    db = next(get_db())
    try:
        data = request.get_json()
        if not data or "part_id" not in data:
            return jsonify({"code": 400, "message": "Missing part_id"}), 400

        part_id = data["part_id"]
        part = get_part_by_id(db, part_id)
        if part is None:
            return jsonify({"code": 404, "message": "Part not found"}), 404
        return jsonify({"code": 0, "data": part.to_dict()})
    finally:
        db.close()


@api_bp.route("/parts/add_part", methods=["POST"])
def add_part():
    """创建新零件记录

    POST /parts/add_part

    Request Body:
        {
            "hash_id": "文件哈希值(必填)",
            "name": "文件名(必填)",
            "format": "文件格式(必填)",
            "industry": "行业分类",
            "product_type": "产品类型",
            "has_round": true/false,
            "has_chamfer": true/false,
            "has_through_hole": true/false,
            "is_open_source": true/false,
            "source_type": "public/private",
            "created_by": "创建人"
        }

    Returns:
        JSON: {"code": 0, "data": part} - 创建成功（HTTP 201）
        JSON: {"code": 400, "message": "Missing required field: xxx"} - 缺少必填字段
        JSON: {"code": 409, "message": "Part with this hash_id already exists"} - hash_id重复
    """
    db = next(get_db())
    try:
        data = request.get_json()
        if not data:
            logger.warning("add_part called with no data provided")
            return jsonify({"code": 400, "message": "No data provided"}), 400

        required_fields = ["hash_id", "name", "format"]
        for field in required_fields:
            if field not in data:
                logger.warning(f"add_part missing required field: {field}")
                return jsonify({"code": 400, "message": f"Missing required field: {field}"}), 400

        existing = get_part_by_hash_id(db, data["hash_id"])
        if existing:
            logger.info(f"add_part hash_id already exists: {data['hash_id']}")
            return jsonify({"code": 409, "message": "Part with this hash_id already exists"}), 409

        part = create_part(db, data)
        logger.info(f"add_part success: {part.name} (id: {part.id})")
        return jsonify({"code": 0, "data": part.to_dict()}), 201
    finally:
        db.close()


@api_bp.route("/parts/modify_part", methods=["POST"])
def modify_part():
    """更新零件信息

    POST /parts/modify_part

    Request Body:
        {
            "part_id": 零件ID,
            "name": "新文件名",
            "industry": "新行业分类",
            "product_type": "新产品类型",
            ... (其他字段)
        }

    Returns:
        JSON: {"code": 0, "data": part} - 更新成功
        JSON: {"code": 400, "message": "Missing part_id"} - 缺少参数
        JSON: {"code": 404, "message": "Part not found"} - 未找到
    """
    db = next(get_db())
    try:
        data = request.get_json()
        if not data:
            return jsonify({"code": 400, "message": "No data provided"}), 400

        if "part_id" not in data:
            return jsonify({"code": 400, "message": "Missing part_id"}), 400

        part_id = data["part_id"]
        update_data = {k: v for k, v in data.items() if k != "part_id"}

        part = update_part(db, part_id, update_data)
        if part is None:
            return jsonify({"code": 404, "message": "Part not found"}), 404
        return jsonify({"code": 0, "data": part.to_dict()})
    finally:
        db.close()


@api_bp.route("/parts/update_feature_label", methods=["POST"])
def update_feature_label():
    """更新零件特征标注状态

    POST /parts/update_feature_label

    Request Body:
        {
            "part_id": 零件ID,
            "feature_type": "特征类型(round/chamfer/countersink_hole/counterbore_hole/through_hole/blind_hole)",
            "status": "标注状态(pending/in_progress/completed/skipped/error)",
            "modified_by": "修改人"
        }

    Returns:
        JSON: {"code": 0, "data": part} - 更新成功
        JSON: {"code": 400, "message": "Missing part_id/feature_type/status"} - 缺少必要参数
        JSON: {"code": 404, "message": "Part or feature not found"} - 零件或特征不存在
    """
    db = next(get_db())
    try:
        data = request.get_json()
        if not data:
            return jsonify({"code": 400, "message": "No data provided"}), 400

        part_id = data.get("part_id")
        feature_type = data.get("feature_type")
        status = data.get("status")
        modified_by = data.get("modified_by")

        if not part_id or not feature_type:
            return jsonify({"code": 400, "message": "Missing part_id or feature_type"}), 400

        if not status:
            return jsonify({"code": 400, "message": "Missing status"}), 400

        part = update_label_status(db, part_id, feature_type, status, modified_by)
        if part is None:
            return jsonify({"code": 404, "message": "Part or feature not found"}), 404
        return jsonify({"code": 0, "data": part.to_dict()})
    finally:
        db.close()



@api_bp.route("/parts/filter_by_label_status", methods=["POST"])
def filter_by_label_status():
    """根据标注状态筛选零件

    POST /parts/filter_by_label_status

    Request Body:
        {
            "label_round_status": "pending",
            "label_chamfer_status": "completed",
            "limit": 100
        }

    Returns:
        JSON: {"code": 0, "data": [part1, part2, ...]}
    """
    db = next(get_db())
    try:
        data = request.get_json() if request.get_json() else {}
        label_statuses = {k: v for k, v in data.items() if k.startswith("label_")}
        limit = data.get("limit", 100)
        parts = get_parts_by_label_status(db, label_statuses, limit)
        return jsonify({"code": 0, "data": [p.to_dict() for p in parts]})
    finally:
        db.close()


@api_bp.route("/stats", methods=["POST"])
def statistics():
    """统计零件数量

    POST /stats

    Request Body:
        {
            "industry": "行业分类"
        }

    Returns:
        JSON: {"code": 0, "data": {"total": 数量, "industry": "筛选条件"}}
    """
    db = next(get_db())
    try:
        data = request.get_json() if request.get_json() else {}
        industry = data.get("industry")
        total = count_parts(db, industry)
        return jsonify({"code": 0, "data": {"total": total, "industry": industry}})
    finally:
        db.close()


@api_bp.route("/label/save_json", methods=["POST"])
def save_json():
    """保存零件标注JSON文件

    POST /label/save_json

    Request Body:
        {
            "name": "零件123",
            "feature_type": "round",
            "industry": "汽车",
            "user": "张三",
            "json_data": {},
        }

    Returns:
        JSON: {"code": 0, "message": "JSON saved successfully"}
        JSON: {"code": 400, "message": "Missing required field: xxx"} - 缺少必填字段
        JSON: {"code": 500, "message": "Failed to save JSON"} - 保存失败
    """
    data = request.get_json()
    if not data:
        logger.warning("save_json called with no data provided")
        return jsonify({"code": 400, "message": "No data provided"}), 400

    required_fields = ["name", "feature_type", "industry", "user", "json_data"]
    for field in required_fields:
        if field not in data:
            logger.warning(f"save_json missing required field: {field}")
            return jsonify({"code": 400, "message": f"Missing required field: {field}"}), 400

    name = data["name"]
    feature_type = data["feature_type"]
    industry = data["industry"]
    user = data["user"]
    json_data = data["json_data"]

    base_path = current_app.config.get("label_json_path", "labels")

    folder_path = os.path.join(base_path, user, industry, feature_type)

    try:
        os.makedirs(folder_path, exist_ok=True)

        file_path = os.path.join(folder_path, f"{name}.json")
        logger.info(f"保存标注文件:{file_path}")

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        logger.info(f"save_json success: {file_path}")
        return jsonify({"code": 0, "message": "JSON saved successfully", "path": file_path})
    except Exception as e:
        logger.error(f"save_json failed: {str(e)}", exc_info=True)
        return jsonify({"code": 500, "message": f"Failed to save JSON: {str(e)}"}), 500


@api_bp.route("/label/send_solid_file", methods=["POST"])
def send_solid_file():
    """发送零件模型文件

    POST /label/send_solid_file

    Request Body:
        {
            "part_id": "零件id"
        }

    Returns:
        文件流 - 返回对应的STP/STEP模型文件
        JSON: {"code": 400, "message": "Missing part_id"} - 缺少参数
        JSON: {"code": 404, "message": "Part not found"} - 零件不存在
        JSON: {"code": 404, "message": "File not found"} - 文件不存在
    """
    data = request.get_json()
    if not data or "part_id" not in data:
        logger.warning("send_solid_file missing part_id parameter")
        return jsonify({"code": 400, "message": "Missing part_id"}), 400

    part_id = data["part_id"]

    db = next(get_db())
    try:
        part = get_part_by_id(db, part_id)
        if not part:
            logger.info(f"send_solid_file part not found: {part_id}")
            return jsonify({"code": 404, "message": "Part not found"}), 404
        file_name = part.name
    finally:
        db.close()

    # 从本地目录读取文件
    base_path = current_app.config.get("SOLID_FILE_PATH", "steps")
    base_path = os.path.abspath(base_path)
    file_path = os.path.join(base_path, file_name)

    if not os.path.exists(file_path):
        logger.info(f"send_solid_file file not found: {file_path}")
        return jsonify({"code": 404, "message": "File not found"}), 404

    logger.info(f"send_solid_file local: {file_path}")
    return send_file(file_path, as_attachment=True)


@api_bp.route("/label/import_json", methods=["POST"])
def import_json():
    """导入零件标注JSON文件

    POST /label/import_json
    Request Body:
        {
            "name": "零件123",
            "feature_type": "round",
            "industry": "汽车",
            "user": "张三",
        }

    Returns:
        文件流 - 返回对应的STP/STEP模型文件，同时在响应头中包含JSON数据
        JSON: {"code": 400, "message": "Missing required field: xxx"} - 缺少必填字段
        JSON: {"code": 404, "message": "JSON file not found"} - JSON文件不存在
        JSON: {"code": 404, "message": "Part not found"} - 零件不存在
        JSON: {"code": 404, "message": "STEP file not found"} - STEP文件不存在
        JSON: {"code": 400, "message": "part_id not found in JSON data"} - JSON中缺少part_id
    """
    data = request.get_json()
    if not data:
        logger.warning("import_json called with no data provided")
        return jsonify({"code": 400, "message": "No data provided"}), 400

    required_fields = ["name", "feature_type", "industry", "user"]
    for field in required_fields:
        if field not in data:
            logger.warning(f"import_json missing required field: {field}")
            return jsonify({"code": 400, "message": f"Missing required field: {field}"}), 400

    name = data["name"]
    feature_type = data["feature_type"]
    industry = data["industry"]
    user = data["user"]

    label_base_path = current_app.config.get("label_json_path", "labels")
    label_base_path = os.path.abspath(label_base_path)
    json_file_path = os.path.join(label_base_path, user, industry, feature_type, f"{name}.json")

    if not os.path.exists(json_file_path):
        logger.info(f"import_json JSON file not found: {json_file_path}")
        return jsonify({"code": 404, "message": "JSON file not found"}), 404

    try:
        with open(json_file_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)
    except Exception as e:
        logger.error(f"import_json failed to read JSON: {str(e)}", exc_info=True)
        return jsonify({"code": 500, "message": f"Failed to read JSON file: {str(e)}"}), 500

    if "part_id" not in json_data:
        logger.warning("import_json part_id not found in JSON data")
        return jsonify({"code": 400, "message": "part_id not found in JSON data"}), 400

    part_id = json_data["part_id"]

    db = next(get_db())
    try:
        part = get_part_by_id(db, part_id)
        if not part:
            logger.info(f"import_json part not found: {part_id}")
            return jsonify({"code": 404, "message": "Part not found"}), 404

        file_name = part.name
        solid_base_path = current_app.config.get("SOLID_FILE_PATH", "steps")
        solid_base_path = os.path.abspath(solid_base_path)
        file_path = os.path.join(solid_base_path, file_name)

        if not os.path.exists(file_path):
            logger.info(f"import_json STEP file not found: {file_path}")
            return jsonify({"code": 404, "message": "STEP file not found"}), 404

        logger.info(f"import_json success: {file_path}")

        boundary = "----SolidInfoBoundary"

        metadata_part = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="metadata"\r\n'
            'Content-Type: application/json; charset=utf-8\r\n'
            "\r\n"
            f"{json.dumps(json_data, ensure_ascii=False)}\r\n"
        ).encode("utf-8")

        with open(file_path, "rb") as f:
            file_content = f.read()

        filename = os.path.basename(file_path)
        file_part = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            'Content-Type: application/octet-stream\r\n'
            "\r\n"
        ).encode("utf-8") + file_content + f"\r\n--{boundary}--\r\n".encode("utf-8")

        return Response(
            metadata_part + file_part,
            content_type=f"multipart/form-data; boundary={boundary}"
        )
    finally:
        db.close()


@api_bp.route("/label/upload_file", methods=["POST"])
def upload_file():
    """上传 CAD 模型文件到服务器

    POST /api/label/upload_file
    Content-Type: multipart/form-data

    Form Fields:
        file (必填): STP/STEP/IGS 文件

    Returns:
        JSON: {"code": 0, "data": {"hash_id": "...", "name": "...", "format": "stp", "file_path": "..."}} - 上传成功
        JSON: {"code": 400, "message": "..."} - 缺少文件或格式不支持
        JSON: {"code": 409, "message": "..."} - 文件已存在
    """
    if "file" not in request.files:
        return jsonify({"code": 400, "message": "Missing file"}), 400

    uploaded = request.files["file"]
    if not uploaded.filename:
        return jsonify({"code": 400, "message": "Empty filename"}), 400

    ext = os.path.splitext(uploaded.filename)[1].lower()
    if ext not in (".stp", ".step", ".igs"):
        return jsonify({"code": 400, "message": f"Unsupported format: {ext}"}), 400

    sha256 = hashlib.sha256()
    chunks = []
    for chunk in iter(lambda: uploaded.read(65536), b""):
        sha256.update(chunk)
        chunks.append(chunk)
    file_bytes = b"".join(chunks)
    hash_id = sha256.hexdigest()

    name = uploaded.filename

    base_path = current_app.config.get("SOLID_FILE_PATH", "steps")
    base_path = os.path.abspath(base_path)
    os.makedirs(base_path, exist_ok=True)

    save_path = os.path.join(base_path, name)
    if os.path.exists(save_path):
        existing_hash = hashlib.sha256(open(save_path, "rb").read()).hexdigest()
        if existing_hash == hash_id:
            return jsonify({"code": 409, "message": "File already exists", "data": {"hash_id": hash_id, "name": name}}), 409
        name = f"{hash_id[:8]}_{name}"
        save_path = os.path.join(base_path, name)

    with open(save_path, "wb") as f:
        f.write(file_bytes)

    logger.info(f"upload_file saved: {save_path}")
    return jsonify({"code": 0, "data": {"hash_id": hash_id, "name": name, "format": ext.lstrip("."), "file_path": save_path}})

@api_bp.route("/label/filter_json", methods=["POST"])
def filter_json():
    """筛选 JSON 标注文件

    POST /api/label/filter_json
    Content-Type: application/json

    Request Body:
        {
            "user": "用户名(默认'all')",
            "industry": "行业类型(默认'all')",
            "feature_type": "特征类型(默认'all')"
        }

    Returns:
        JSON: {"code": 0, "data": [...], "message": "filter successful"} - 筛选成功
        JSON: {"code": 400, "message": "..."} - 参数错误
        JSON: {"code": 500, "message": "..."} - 服务器错误
    """
    data = request.get_json()
    if not data:
        logger.warning("filter_json called with no data provided")
        return jsonify({"code": 400, "message": "No data provided"}), 400
    
    user = data.get("user", "all")
    industry = data.get("industry", "all")
    feature_type = data.get("feature_type", "all")
    
    label_base_path = current_app.config.get("label_json_path", "labels")
    label_base_path = os.path.abspath(label_base_path)
    logger.info(f"base path:{label_base_path}")
    
    try:
        result = []
        
        # 1. 筛选一级文件夹 (user)
        if not os.path.exists(label_base_path):
            return jsonify({"code": 0, "data": [], "message": "filter successful"}), 200
        
        first_level_dirs = [d for d in os.listdir(label_base_path) 
                           if os.path.isdir(os.path.join(label_base_path, d))]
        
        if user != "all":
            first_level_dirs = [d for d in first_level_dirs if d == user]
        
        # 2. 筛选二级文件夹 (industry)
        second_level_dirs = []
        for first_dir in first_level_dirs:
            first_path = os.path.join(label_base_path, first_dir)
            dirs = [os.path.join(first_dir, d) for d in os.listdir(first_path) 
                    if os.path.isdir(os.path.join(first_path, d))]
            second_level_dirs.extend(dirs)
        
        if industry != "all":
            second_level_dirs = [d for d in second_level_dirs if os.path.basename(d) == industry]
        
        # 3. 筛选三级文件夹 (feature_type)
        third_level_dirs = []
        for second_dir in second_level_dirs:
            second_path = os.path.join(label_base_path, second_dir)
            dirs = [os.path.join(second_dir, d) for d in os.listdir(second_path) 
                    if os.path.isdir(os.path.join(second_path, d))]
            third_level_dirs.extend(dirs)
        
        if feature_type != "all":
            third_level_dirs = [d for d in third_level_dirs if os.path.basename(d) == feature_type]
        
        # 4. 遍历三级文件夹，收集 JSON 文件
        for third_dir in third_level_dirs:
            third_path = os.path.join(label_base_path, third_dir)
            for filename in os.listdir(third_path):
                if filename.endswith(".json"):
                    result.append({
                        "path": third_dir,
                        "filename": filename
                    })
        
        logger.info(f"filter_json success: found {len(result)} files")
        return jsonify({"code": 0, "data": result, "message": "filter successful"}), 200
    
    except Exception as e:
        logger.error(f"filter_json failed: {str(e)}", exc_info=True)
        return jsonify({"code": 500, "message": f"Filter failed: {str(e)}"}), 500