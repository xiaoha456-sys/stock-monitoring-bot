"""Load portfolio configuration and merge live holdings overlay."""

from __future__ import annotations

import json
from typing import Any

from domain.paths import CONFIG_PATH


def load_config_raw() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_config() -> dict[str, Any]:
    config = load_config_raw()
    from domain.holdings import resolve_holdings

    config = dict(config)
    config["holdings"] = resolve_holdings(config)
    return config
