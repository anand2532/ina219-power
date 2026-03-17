from __future__ import annotations

import argparse
import json
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .logger import CSVLogger, LogRow
from .sensor import INA219Reading, INA219Sensor


def _parse_i2c_address(value: str) -> int:
    s = value.strip().lower()
    if s.startswith("0x"):
        return int(s, 16)
    return int(s, 10)


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("config must be a JSON object")
    return data


@dataclass(frozen=True)
class AppConfig:
    sampling_interval_s: float
    i2c_bus: int
    i2c_address: int
    shunt_ohms: float
    max_expected_amps: float
    log_dir: str
    max_dt_s: float
    rotation_enabled: bool
    rotation_max_bytes: int


def _config_from_dict(d: dict[str, Any]) -> AppConfig:
    interval = float(d.get("sampling_interval_s", 1.0))
    i2c_bus = int(d.get("i2c_bus", 1))
    i2c_addr_raw = d.get("i2c_address", "0x40")
    i2c_addr = (
        _parse_i2c_address(i2c_addr_raw)
        if isinstance(i2c_addr_raw, str)
        else int(i2c_addr_raw)
    )

    shunt_ohms = float(d.get("shunt_ohms", 0.1))
    max_expected_amps = float(d.get("max_expected_amps", 3.2))
    log_dir = str(d.get("log_dir", "./logs"))
    max_dt_s = float(d.get("max_dt_s", 5.0))

    rotation = d.get("csv_rotation", {}) if isinstance(d.get("csv_rotation", {}), dict) else {}
    rotation_enabled = bool(rotation.get("enabled", True))
    rotation_max_bytes = int(rotation.get("max_bytes", 5 * 1024 * 1024))

    if interval <= 0:
        raise ValueError("sampling_interval_s must be > 0")
    if shunt_ohms <= 0:
        raise ValueError("shunt_ohms must be > 0")
    if max_expected_amps <= 0:
        raise ValueError("max_expected_amps must be > 0")
    if max_dt_s <= 0:
        raise ValueError("max_dt_s must be > 0")

    return AppConfig(
        sampling_interval_s=interval,
        i2c_bus=i2c_bus,
        i2c_address=i2c_addr,
        shunt_ohms=shunt_ohms,
        max_expected_amps=max_expected_amps,
        log_dir=log_dir,
        max_dt_s=max_dt_s,
        rotation_enabled=rotation_enabled,
        rotation_max_bytes=rotation_max_bytes,
    )


class _StopFlag:
    def __init__(self) -> None:
        self.stop = False


def _fmt_ts_local(ts_unix_s: float) -> str:
    return datetime.fromtimestamp(ts_unix_s).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _print_reading(reading: INA219Reading, energy_wh: float) -> None:
    ts = _fmt_ts_local(reading.timestamp_unix_s)
    print(
        f"{ts} | "
        f"V={reading.bus_voltage_v:6.3f} V | "
        f"I={reading.current_ma:8.3f} mA | "
        f"P={reading.power_w:7.3f} W | "
        f"E={energy_wh:10.6f} Wh",
        flush=True,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="INA219 power monitor (voltage/current/power + energy + CSV logs)")
    parser.add_argument("--config", default="./config.json", help="Path to config.json")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--interval", type=float, default=None, help="Override sampling interval in seconds")
    parser.add_argument("--i2c-address", type=str, default=None, help='Override I2C address (e.g. "0x40")')
    parser.add_argument("--log-dir", type=str, default=None, help="Override log directory")
    args = parser.parse_args(argv)

    cfg_path = Path(args.config)
    cfg_dict = _load_json(cfg_path)
    cfg = _config_from_dict(cfg_dict)

    if args.interval is not None:
        cfg = AppConfig(**{**cfg.__dict__, "sampling_interval_s": float(args.interval)})
    if args.i2c_address is not None:
        cfg = AppConfig(**{**cfg.__dict__, "i2c_address": _parse_i2c_address(args.i2c_address)})
    if args.log_dir is not None:
        cfg = AppConfig(**{**cfg.__dict__, "log_dir": str(args.log_dir)})

    debug = bool(args.debug)
    if debug:
        print(f"[main] loaded config from {cfg_path.resolve()}", flush=True)
        print(f"[main] i2c_address=0x{cfg.i2c_address:02X}, interval={cfg.sampling_interval_s}s, log_dir={cfg.log_dir}", flush=True)

    sensor = INA219Sensor(
        i2c_bus=cfg.i2c_bus,
        i2c_address=cfg.i2c_address,
        shunt_ohms=cfg.shunt_ohms,
        max_expected_amps=cfg.max_expected_amps,
        debug=debug,
    )
    logger = CSVLogger(
        log_dir=cfg.log_dir,
        rotation_enabled=cfg.rotation_enabled,
        max_bytes=cfg.rotation_max_bytes,
        debug=debug,
    )

    stop_flag = _StopFlag()

    def _handle_stop(_signum: int, _frame: Any) -> None:  # noqa: ANN401
        stop_flag.stop = True

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    energy_wh = 0.0
    last_mono = time.monotonic()

    try:
        while not stop_flag.stop:
            loop_start = time.monotonic()
            dt = loop_start - last_mono
            last_mono = loop_start

            if dt < 0:
                dt = 0
            if dt > cfg.max_dt_s:
                if debug:
                    print(f"[main] large dt={dt:.3f}s clamped to {cfg.max_dt_s:.3f}s", flush=True)
                dt = cfg.max_dt_s

            try:
                reading = sensor.read()
                energy_wh += reading.power_w * dt / 3600.0

                _print_reading(reading, energy_wh)

                logger.write_row(
                    LogRow(
                        timestamp=datetime.now(timezone.utc).astimezone(),
                        voltage_v=reading.bus_voltage_v,
                        current_ma=reading.current_ma,
                        power_w=reading.power_w,
                        cumulative_energy_wh=energy_wh,
                    )
                )
            except Exception as e:  # noqa: BLE001
                # Keep the process alive: retry on next loop iteration.
                msg = f"[main] error: {e!r}"
                if debug:
                    print(msg, flush=True)
                else:
                    print(msg + " (enable --debug for details)", flush=True)

            elapsed = time.monotonic() - loop_start
            sleep_s = cfg.sampling_interval_s - elapsed
            if sleep_s > 0:
                time.sleep(sleep_s)

    finally:
        logger.close()

    if debug:
        print("[main] stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

