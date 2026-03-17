# INA219 Power Monitor (Raspberry Pi)

Production-ready Python project for Raspberry Pi 4B+ using an INA219 (CJMCU-219) I2C sensor to measure real-time voltage/current/power, accumulate energy (Wh), and log to daily CSV files.

## Hardware wiring (typical)
- **VCC** → 3.3V
- **GND** → GND
- **SDA** → GPIO2 (SDA)
- **SCL** → GPIO3 (SCL)

## Raspberry Pi setup

### Enable I2C
- `sudo raspi-config` → **Interface Options** → **I2C** → Enable
- Reboot if prompted

### Install OS packages
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv i2c-tools
```

### Verify the sensor is visible
```bash
sudo i2cdetect -y 1
```
You should see `40` (default INA219 address) unless you changed it.

## Install Python dependencies
From the project directory (recommended: use a virtual environment):
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If you *intentionally* want to install into the system Python (not recommended), you can use:
```bash
python3 -m pip install --break-system-packages -r requirements.txt
```

## Configure
Edit [`config.json`](config.json). Key options:
- `sampling_interval_s`: print/log interval (default `1.0`)
- `i2c_bus`: typically `1` on Raspberry Pi
- `i2c_address`: hex string like `"0x40"`
- `shunt_ohms`: typically `0.1` on CJMCU-219 boards
- `max_expected_amps`: calibration target (default `3.2`)
- `log_dir`: default `./logs`
- `max_dt_s`: clamps large time gaps for energy integration
- `csv_rotation.max_bytes`: optional size-based rollover (in addition to daily files)

## Run manually
```bash
python3 -m ina219_power.main --config ./config.json
```

Enable debug logging:
```bash
python3 -m ina219_power.main --config ./config.json --debug
```

## Logs
- Logs are written to `log_dir` (default `./logs`)
- A new CSV is created per day: `YYYY-MM-DD.csv`
- Optional size-based rollover creates `YYYY-MM-DD_001.csv`, etc.

## Install as a systemd service (auto-start on boot)

### Suggested install paths
- Project: `/opt/ina219-power`
- Config: `/etc/ina219-power/config.json`

### Copy files
```bash
sudo mkdir -p /opt/ina219-power
sudo rsync -a --delete ./ /opt/ina219-power/

sudo mkdir -p /etc/ina219-power
sudo cp /opt/ina219-power/config.json /etc/ina219-power/config.json
```

### Install the unit
```bash
sudo cp /opt/ina219-power/systemd/ina219-power.service /etc/systemd/system/ina219-power.service
sudo systemctl daemon-reload
sudo systemctl enable --now ina219-power.service
```

### View service logs
```bash
sudo journalctl -u ina219-power.service -f
```

### Troubleshooting
- **No device at `0x40`**: run `sudo i2cdetect -y 1` and confirm the detected address; update `i2c_address` in config (supports `"0x40"` style).
- **Permission errors (non-root service)**: ensure the service user is in the `i2c` group (then log out/in) and update `User=` in the unit file.
- **Service is running but no CSV appears**: check `log_dir` and make sure it’s writable for the service user. With the provided unit, relative paths are resolved under `WorkingDirectory=/opt/ina219-power`.
- **Viewing logs**: `sudo journalctl -u ina219-power.service -f`.

### Run as non-root (optional)
If you prefer not to run as root, create/use a user in the `i2c` group:
```bash
sudo usermod -aG i2c pi
```
Then edit the unit file `User=` accordingly.

