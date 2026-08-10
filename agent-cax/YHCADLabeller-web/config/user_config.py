import os
import json

_USER_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_config.json")


def load_user_config():
    try:
        if os.path.exists(_USER_CONFIG_PATH):
            with open(_USER_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_user_config(config):
    try:
        os.makedirs(os.path.dirname(_USER_CONFIG_PATH), exist_ok=True)
        with open(_USER_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
