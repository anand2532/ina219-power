from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class INA219Reading:
    timestamp_unix_s: float
    bus_voltage_v: float
    current_ma: float
    power_w: float


class INA219Sensor:
    """
    Wrapper around Adafruit's INA219 driver that supports:
    - configurable I2C bus/address
    - calibration parameters
    - robust read() with automatic re-init on failures
    """

    def __init__(
        self,
        *,
        i2c_bus: int = 1,
        i2c_address: int = 0x40,
        shunt_ohms: float = 0.1,
        max_expected_amps: float = 3.2,
        debug: bool = False,
    ) -> None:
        self._i2c_bus = int(i2c_bus)
        self._i2c_address = int(i2c_address)
        self._shunt_ohms = float(shunt_ohms)
        self._max_expected_amps = float(max_expected_amps)
        self._debug = bool(debug)

        self._sensor = None
        self._had_error = False
        self._init_sensor()

    def _log(self, msg: str) -> None:
        if self._debug:
            print(f"[sensor] {msg}", flush=True)

    def _init_sensor(self) -> None:
        """
        (Re)initialize I2C + INA219 object.

        Notes:
        - We import hardware-specific modules here to keep import-time failures clearer.
        - We recreate I2C each time to recover from transient kernel/I2C issues.
        """
        try:
            import board  # type: ignore
            import busio  # type: ignore
            from adafruit_ina219 import INA219  # type: ignore
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                "Missing INA219 dependencies. Install requirements.txt on the Raspberry Pi."
            ) from e

        self._log(
            f"initializing INA219 (bus={self._i2c_bus}, addr=0x{self._i2c_address:02X}, "
            f"shunt_ohms={self._shunt_ohms}, max_expected_amps={self._max_expected_amps})"
        )

        i2c = busio.I2C(board.SCL, board.SDA)
        # Some systems need a moment for I2C bus to become ready.
        t0 = time.monotonic()
        locked = i2c.try_lock()
        while not locked:
            if time.monotonic() - t0 > 1.0:
                break
            time.sleep(0.01)
            locked = i2c.try_lock()
        if locked:
            i2c.unlock()

        try:
            # Prefer newer-style drivers (if supported).
            self._sensor = INA219(
                i2c,
                addr=self._i2c_address,
                shunt_ohms=self._shunt_ohms,
                max_expected_amps=self._max_expected_amps,
            )  # type: ignore[call-arg]
            return
        except TypeError:
            # Older/stable Adafruit API: INA219(i2c_bus, addr=0x40) + set_calibration_* methods.
            self._sensor = INA219(i2c, addr=self._i2c_address)  # type: ignore[call-arg]

            # Adafruit's built-in calibration helpers assume a 0.1Ω shunt.
            if abs(self._shunt_ohms - 0.1) > 1e-6:
                self._log(
                    f"warning: Adafruit INA219 calibration helpers assume 0.1Ω shunt; "
                    f"configured shunt_ohms={self._shunt_ohms} may reduce accuracy"
                )

            # Pick the closest built-in calibration.
            if self._max_expected_amps <= 1.0 and hasattr(self._sensor, "set_calibration_32V_1A"):
                self._sensor.set_calibration_32V_1A()
            elif hasattr(self._sensor, "set_calibration_32V_2A"):
                self._sensor.set_calibration_32V_2A()

    def read(self) -> INA219Reading:
        """
        Read a sample. On I2C errors, attempts to reinitialize and retries.
        """
        last_exc: Optional[BaseException] = None
        for attempt in range(1, 4):
            try:
                if self._sensor is None:
                    self._init_sensor()

                # Adafruit INA219:
                # - bus_voltage: volts
                # - current: milliamps
                # - power: milliwatts
                bus_v = float(self._sensor.bus_voltage)
                current_ma = float(self._sensor.current)
                power_w = float(self._sensor.power) / 1000.0

                if self._had_error:
                    self._log("recovered from previous I2C error")
                    self._had_error = False

                return INA219Reading(
                    timestamp_unix_s=time.time(),
                    bus_voltage_v=bus_v,
                    current_ma=current_ma,
                    power_w=power_w,
                )
            except (OSError, ValueError) as e:
                last_exc = e
                self._had_error = True
                self._log(f"I2C read failed (attempt {attempt}/3): {e!r}; reinitializing")
                try:
                    self._sensor = None
                    self._init_sensor()
                except Exception as reinit_exc:  # noqa: BLE001
                    self._log(f"reinit failed: {reinit_exc!r}")
                time.sleep(min(0.25 * attempt, 1.0))

        raise RuntimeError("INA219 read failed after retries") from last_exc

