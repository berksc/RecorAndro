"""Explicit local configuration; loading never creates directories."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Mapping


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    data_root: Path
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"


def load_config(path: str | None = None, env: Mapping[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    selected = path if path is not None else env.get("RECORANDRO_CONFIG")
    values = {}
    base = Path.cwd()
    if selected is not None:
        if not selected.strip():
            raise ConfigError("Config path must not be empty")
        config_path = Path(selected).expanduser().resolve()
        base = config_path.parent
        try:
            if config_path.stat().st_size > 65536:
                raise ConfigError("Config file exceeds 64 KiB")
            values = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConfigError(f"Cannot read config: {exc}") from exc
        if not isinstance(values, dict) or set(values) - {"data_root", "ffmpeg", "ffprobe"}:
            raise ConfigError("Config must be an object with only data_root, ffmpeg, ffprobe")
    for key in ("data_root", "ffmpeg", "ffprobe"):
        override = env.get(f"RECORANDRO_{key.upper()}")
        if override is not None:
            values[key] = override
    root = values.get("data_root")
    if not isinstance(root, str) or not root.strip() or "\x00" in root:
        raise ConfigError("Set data_root in a config file or RECORANDRO_DATA_ROOT")
    root_path = Path(root).expanduser()
    # File-relative paths resolve relative to the config; env paths must be absolute.
    if "RECORANDRO_DATA_ROOT" in env and not root_path.is_absolute():
        raise ConfigError("RECORANDRO_DATA_ROOT must be absolute (or start with ~/)")
    root_path = (base / root_path).resolve()
    if root_path == Path(root_path.anchor):
        raise ConfigError("Data root must be an owned subdirectory, not a filesystem root")
    tools = []
    for key in ("ffmpeg", "ffprobe"):
        value = values.get(key, key)
        if not isinstance(value, str) or not value.strip() or "\x00" in value:
            raise ConfigError(f"{key} must be an executable name or path, not arguments")
        tools.append(value)
    return Config(root_path, *tools)
