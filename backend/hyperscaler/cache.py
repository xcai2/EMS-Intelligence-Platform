import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR = Path("data/hyperscaler")
_VIEW_MODEL_PATH = _DATA_DIR / "big5_capex_view_model.json"
_RAW_PATH = _DATA_DIR / "big5_capex_api_raw.json"


def _ensure_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def read_view_model() -> dict | None:
    try:
        return json.loads(_VIEW_MODEL_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as exc:
        logger.error("Failed to read view model cache: %s", exc)
        return None


def write_view_model(payload: dict) -> bool:
    try:
        _ensure_dir()
        tmp = _VIEW_MODEL_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_VIEW_MODEL_PATH)
        return True
    except Exception as exc:
        logger.error("Failed to write view model cache: %s", exc)
        return False


def write_raw(payload: dict) -> bool:
    try:
        _ensure_dir()
        tmp = _RAW_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_RAW_PATH)
        return True
    except Exception as exc:
        logger.error("Failed to write raw cache: %s", exc)
        return False
