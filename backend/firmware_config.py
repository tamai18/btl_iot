"""Read the configuration defaults declared by the ESP32 firmware."""

import re
from pathlib import Path


_NUMBER = r"([-+]?(?:\d+(?:\.\d*)?|\.\d+))"


def _read_constant(source: str, name: str) -> float | None:
    match = re.search(rf"\b{name}\s*=\s*{_NUMBER}", source)
    return float(match.group(1)) if match else None


def load_firmware_defaults() -> dict[str, str]:
    """Return dashboard config keys from the firmware's compile-time defaults."""
    firmware_path = Path(__file__).parent.parent / "ao_nuoc" / "ao_nuoc.ino"
    try:
        source = firmware_path.read_text(encoding="utf-8")
    except OSError:
        return {}

    # Ignore old examples and disabled declarations, preserving string literals.
    source = re.sub(
        r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/',
        lambda match: match.group(0) if match.group(0).startswith('"') else " ",
        source,
    )

    values = {
        "d_empty": _read_constant(source, "DEF_D_EMPTY"),
        "d_full": _read_constant(source, "DEF_D_FULL"),
        "in_on_pct": _read_constant(source, "DEF_IN_ON"),
        "in_off_pct": _read_constant(source, "DEF_IN_OFF"),
        "out_on_pct": _read_constant(source, "DEF_OUT_ON"),
        "out_off_pct": _read_constant(source, "DEF_OUT_OFF"),
        "limit_high": _read_constant(source, "LIMIT_HIGH"),
        "limit_low": _read_constant(source, "LIMIT_LOW"),
    }

    max_run = re.search(r"\bMAX_RUN_MS\s*=\s*(\d+)\s*UL\s*\*\s*60\s*UL\s*\*\s*1000\s*UL", source)
    if max_run:
        values["max_run_min"] = float(max_run.group(1))

    publish = _read_constant(source, "PUBLISH_MS")
    if publish is not None:
        values["publish_sec"] = publish / 1000

    result = {
        key: str(int(value) if value.is_integer() else value)
        for key, value in values.items()
        if value is not None
    }
    for key, name in (("mqtt_broker", "MQTT_HOST"), ("topic_prefix", "P")):
        match = re.search(rf'\b{name}\s*=\s*"([^"\\]*)"', source)
        if match:
            result[key] = match.group(1)
    port = _read_constant(source, "MQTT_PORT")
    if port is not None:
        result["mqtt_port"] = str(int(port))
    return result
