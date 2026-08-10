import os

_AI_MODEL_CACHE = {}


def _normalize_model_path(path):
    return os.path.normcase(os.path.abspath(str(path)))


def _model_cache_key(weight_path, stat_path, use_onnx):
    return "onnx", _normalize_model_path(weight_path), _normalize_model_path(stat_path)


def clear_ai_model_cache():
    _AI_MODEL_CACHE.clear()


def _create_aag_net(weight_path, stat_path, backend):
    from .base_utils_onnx import AGGNetInferenceONNX

    return AGGNetInferenceONNX(weight_path=weight_path, stat_path=stat_path)


def get_cached_aag_net(weight_path, stat_path, use_onnx=False):
    key = _model_cache_key(weight_path, stat_path, use_onnx)
    if key not in _AI_MODEL_CACHE:
        _AI_MODEL_CACHE[key] = _create_aag_net(weight_path, stat_path, key[0])
    return _AI_MODEL_CACHE[key]
