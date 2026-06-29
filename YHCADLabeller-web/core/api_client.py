"""Flask API HTTP 客户端。"""

import logging
import os
import json
from email.parser import BytesParser
from email.policy import default as default_policy

import requests

from config.config_load import get_system_config_json

_logger = logging.getLogger(__name__)


def _get_api_url():
    config = get_system_config_json()
    return config.get("apiServerUrl", "http://localhost:5000/api")


class APIClient:
    _cached_base_url = None

    def __init__(self):
        if APIClient._cached_base_url is None:
            APIClient._cached_base_url = _get_api_url()
        self.base_url = APIClient._cached_base_url

    @staticmethod
    def _check_resp(resp, error_prefix="请求失败"):
        if resp.ok:
            return
        try:
            msg = resp.json().get("message", resp.text)
        except Exception:
            msg = resp.text
        _logger.warning("%s(%d): %s", error_prefix, resp.status_code, msg)
        raise Exception(f"{error_prefix}({resp.status_code}): {msg}")

    @staticmethod
    def _extract_filename(resp):
        filename = "part.step"
        cd = resp.headers.get("Content-Disposition", "")
        for part in cd.split(";"):
            part = part.strip()
            if part.startswith("filename=") and not part.startswith("filename*="):
                filename = part[len("filename="):].strip('" ')
                break
        return filename

    def _stream_to_file(self, resp, save_dir, progress_callback=None, cancel_event=None):
        self._check_resp(resp, "下载失败")

        filename = self._extract_filename(resp)
        save_path = os.path.join(save_dir, filename)
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0

        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if cancel_event and cancel_event.is_set():
                    f.close()
                    try:
                        os.remove(save_path)
                    except OSError:
                        pass
                    raise Exception("下载已取消")
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback and total:
                    progress_callback(downloaded, total)

        return save_path

    def get_filter_options(self, industry=None):
        params = {}
        if industry:
            params["industry"] = industry
        resp = requests.get(f"{self.base_url}/parts/filter_options", params=params, timeout=10)
        self._check_resp(resp, "获取筛选选项失败")
        return resp.json()["data"]

    def get_parts(self, skip=0, limit=100, **filters):
        body = {"skip": skip, "limit": limit}
        for k, v in filters.items():
            if v is not None:
                body[k] = v
        resp = requests.post(f"{self.base_url}/parts/list_parts", json=body, timeout=10)
        self._check_resp(resp, "加载零件列表失败")
        return resp.json()["data"]

    def get_stats(self, industry=None, user=None):
        body = {}
        if industry:
            body["industry"] = industry
        if user:
            body["user"] = user
        resp = requests.post(f"{self.base_url}/stats", json=body, timeout=10)
        self._check_resp(resp, "获取统计失败")
        return resp.json()["data"]

    def save_label_json(self, name, feature_type, industry, user, json_data):
        resp = requests.post(
            f"{self.base_url}/label/save_json",
            json={"name": name, "feature_type": feature_type,
                  "industry": industry, "user": user, "json_data": json_data},
            timeout=30,
        )
        self._check_resp(resp, "上传标注失败")
        return resp.json()

    def update_feature_label(self, part_id, feature_type, status, modified_by=None):
        resp = requests.post(
            f"{self.base_url}/parts/update_feature_label",
            json={"part_id": part_id, "feature_type": feature_type,
                  "status": status, "modified_by": modified_by},
            timeout=10,
        )
        self._check_resp(resp, "更新标注状态失败")
        return resp.json()["data"]

    def send_solid_file(self, part_id, save_dir, progress_callback=None, cancel_event=None):
        resp = requests.post(
            f"{self.base_url}/label/send_solid_file",
            json={"part_id": part_id},
            stream=True,
            timeout=120,
        )
        return self._stream_to_file(resp, save_dir, progress_callback, cancel_event)

    def list_saved_json(self, user, industry=None, feature_type=None):
        """查询已保存标注列表，对接后端 filter_json 接口。"""
        body = {
            "user": user or "all",
            "industry": industry or "all",
            "feature_type": feature_type or "all",
        }
        resp = requests.post(f"{self.base_url}/label/filter_json", json=body, timeout=10)
        self._check_resp(resp, "查询已保存标注列表失败")
        raw_items = resp.json()["data"]
        # 将后端的 path+filename 转换为前端需要的扁平字段
        items = []
        for r in raw_items:
            parts = r["path"].replace("\\", "/").split("/")
            name = os.path.splitext(r["filename"])[0]
            items.append({
                "name": name,
                "user": parts[0] if len(parts) > 0 else "",
                "industry": parts[1] if len(parts) > 1 else "",
                "feature_type": parts[2] if len(parts) > 2 else "",
            })
        return items

    def import_label_json(self, name, feature_type, industry, user):
        resp = requests.post(
            f"{self.base_url}/label/import_json",
            json={"name": name, "feature_type": feature_type,
                  "industry": industry, "user": user},
            timeout=60,
        )
        self._check_resp(resp, "导入失败")

        content_type = resp.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise Exception(f"Unexpected response Content-Type: {content_type}")

        boundary = None
        for part in content_type.split(";"):
            part = part.strip()
            if part.startswith("boundary="):
                boundary = part[len("boundary="):]
                break
        if not boundary:
            raise Exception("No boundary found in multipart response")

        return self._parse_multipart(resp.content, boundary)

    @staticmethod
    def _parse_multipart(raw_bytes, boundary):
        header = f'Content-Type: multipart/form-data; boundary="{boundary}"\r\nMIME-Version: 1.0\r\n\r\n'
        msg = BytesParser(policy=default_policy).parsebytes(header.encode() + raw_bytes)

        result = {"metadata": None, "file": None, "filename": None}
        for part in msg.iter_parts():
            name = part.get_param("name", header="Content-Disposition")
            if name == "metadata":
                result["metadata"] = json.loads(part.get_content())
            elif name == "file":
                result["file"] = part.get_content()
                filename = part.get_filename()
                if filename:
                    result["filename"] = filename

        if result["metadata"] is None:
            raise Exception("Multipart response missing metadata part")
        return result
