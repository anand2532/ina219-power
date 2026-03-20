from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional, TextIO


DEFAULT_FIELDS = [
    "timestamp",
    "voltage_v",
    "current_ma",
    "power_w",
    "total_power_w",
]


@dataclass(frozen=True)
class LogRow:
    timestamp: datetime
    voltage_v: float
    current_ma: float
    power_w: float
    # NOTE: Despite the name, this value is an energy-like cumulative quantity
    # computed as sum(power_w * dt / 3600). It's reported as "W" only to match
    # the user's requested numeric convention.
    total_power_w: float


class CSVLogger:
    def __init__(
        self,
        *,
        log_dir: str,
        session_id: str,
        session_start_utc: datetime,
        rotation_enabled: bool = True,
        max_bytes: int = 5 * 1024 * 1024,
        debug: bool = False,
    ) -> None:
        self._log_dir = Path(log_dir)
        self._session_id = str(session_id)
        self._rotation_enabled = bool(rotation_enabled)
        self._max_bytes = int(max_bytes)
        self._debug = bool(debug)

        self._fh: Optional[TextIO] = None
        self._writer: Optional[csv.DictWriter] = None
        self._current_path: Optional[Path] = None
        # Use local date so the web tail (which keys off `date.today()`) finds the file.
        self._session_start_date_local: date = session_start_utc.astimezone().date()
        self._base_session_path = (
            self._log_dir / f"{self._session_start_date_local.isoformat()}_{self._session_id}.csv"
        )

    def _log(self, msg: str) -> None:
        if self._debug:
            print(f"[logger] {msg}", flush=True)

    def _ensure_dir(self) -> None:
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def _pick_path_for_session(self) -> Path:
        """
        Pick a CSV file path for this boot/session.

        - Default: YYYY-MM-DD_<session_id>.csv
        - If rotation enabled and file exists+too large: append _001, etc.
        """
        primary = self._base_session_path
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
            candidate = self._base_session_path.with_name(
                f"{self._base_session_path.stem}_{idx:03d}{self._base_session_path.suffix}"
            )
            if not candidate.exists():
                return candidate
            try:
                if candidate.stat().st_size <= self._max_bytes:
                    return candidate
            except OSError:
                return candidate
            idx += 1

    def _open_for_session(self) -> None:
        self._ensure_dir()
        path = self._pick_path_for_session()

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
        self._current_path = path

    def _maybe_rotate(self) -> None:
        if not self._rotation_enabled:
            return
        if self._fh is None or self._current_path is None:
            return
        try:
            if self._current_path.stat().st_size <= self._max_bytes:
                return
        except OSError:
            return

        next_path = self._pick_path_for_session()
        if next_path != self._current_path:
            self._log(f"rotating CSV to {next_path}")
            self._open_for_session()

    def write_row(self, row: LogRow) -> None:
        if self._fh is None or self._writer is None or self._current_path is None:
            self._open_for_session()

        self._maybe_rotate()

        assert self._fh is not None
        assert self._writer is not None

        self._writer.writerow(
            {
                "timestamp": row.timestamp.isoformat(timespec="seconds"),
                "voltage_v": f"{row.voltage_v:.6f}",
                "current_ma": f"{row.current_ma:.6f}",
                "power_w": f"{row.power_w:.6f}",
                "total_power_w": f"{row.total_power_w:.9f}",
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
                self._current_path = None

