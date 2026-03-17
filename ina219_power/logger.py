from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional, TextIO


DEFAULT_FIELDS = [
    "timestamp",
    "voltage_v",
    "current_ma",
    "power_w",
    "cumulative_energy_wh",
]


@dataclass(frozen=True)
class LogRow:
    timestamp: datetime
    voltage_v: float
    current_ma: float
    power_w: float
    cumulative_energy_wh: float


class CSVLogger:
    def __init__(
        self,
        *,
        log_dir: str,
        rotation_enabled: bool = True,
        max_bytes: int = 5 * 1024 * 1024,
        debug: bool = False,
    ) -> None:
        self._log_dir = Path(log_dir)
        self._rotation_enabled = bool(rotation_enabled)
        self._max_bytes = int(max_bytes)
        self._debug = bool(debug)

        self._current_day: Optional[date] = None
        self._fh: Optional[TextIO] = None
        self._writer: Optional[csv.DictWriter] = None
        self._current_path: Optional[Path] = None

    def _log(self, msg: str) -> None:
        if self._debug:
            print(f"[logger] {msg}", flush=True)

    def _ensure_dir(self) -> None:
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def _base_name_for_day(self, d: date) -> str:
        return d.isoformat()

    def _pick_path_for_day(self, d: date) -> Path:
        """
        Pick a CSV file path for the given day.

        - Default: YYYY-MM-DD.csv
        - If rotation enabled and file exists+too large: YYYY-MM-DD_001.csv, etc.
        """
        base = self._base_name_for_day(d)
        primary = self._log_dir / f"{base}.csv"
        if not self._rotation_enabled:
            return primary

        if not primary.exists():
            return primary

        try:
            if primary.stat().st_size <= self._max_bytes:
                return primary
        except OSError:
            return primary

        idx = 1
        while True:
            candidate = self._log_dir / f"{base}_{idx:03d}.csv"
            if not candidate.exists():
                return candidate
            try:
                if candidate.stat().st_size <= self._max_bytes:
                    return candidate
            except OSError:
                return candidate
            idx += 1

    def _open_for_day(self, d: date) -> None:
        self._ensure_dir()
        path = self._pick_path_for_day(d)

        if self._fh is not None and self._current_path == path:
            return

        self.close()

        is_new_file = True
        if path.exists():
            try:
                is_new_file = path.stat().st_size == 0
            except OSError:
                is_new_file = False

        self._log(f"opening CSV {path}")
        fh = path.open("a", newline="", encoding="utf-8")

        writer = csv.DictWriter(fh, fieldnames=DEFAULT_FIELDS)
        if is_new_file:
            writer.writeheader()
            fh.flush()
            os.fsync(fh.fileno())

        self._fh = fh
        self._writer = writer
        self._current_day = d
        self._current_path = path

    def _maybe_rotate(self, d: date) -> None:
        if not self._rotation_enabled:
            return
        if self._fh is None or self._current_path is None:
            return
        try:
            if self._current_path.stat().st_size <= self._max_bytes:
                return
        except OSError:
            return

        next_path = self._pick_path_for_day(d)
        if next_path != self._current_path:
            self._log(f"rotating CSV to {next_path}")
            self._open_for_day(d)

    def write_row(self, row: LogRow) -> None:
        d = row.timestamp.date()
        if self._current_day != d:
            self._open_for_day(d)

        self._maybe_rotate(d)

        assert self._fh is not None
        assert self._writer is not None

        self._writer.writerow(
            {
                "timestamp": row.timestamp.isoformat(timespec="seconds"),
                "voltage_v": f"{row.voltage_v:.6f}",
                "current_ma": f"{row.current_ma:.6f}",
                "power_w": f"{row.power_w:.6f}",
                "cumulative_energy_wh": f"{row.cumulative_energy_wh:.9f}",
            }
        )

        self._fh.flush()
        try:
            os.fsync(self._fh.fileno())
        except OSError:
            # Some filesystems may not support fsync; flush is still helpful.
            pass

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            finally:
                self._fh = None
                self._writer = None
                self._current_day = None
                self._current_path = None

