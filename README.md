# INA219 Power Monitor (Raspberry Pi)

Production-ready Python project for Raspberry Pi 4B+ using an INA219 (CJMCU-219) I2C sensor to measure real-time voltage/current/power, and log to CSV files per service restart.

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
- `csv_rotation.max_bytes`: optional size-based rollover (in addition to daily files)

## Run manually
```bash
python3 -m ina219_power.main --config ./config.json
```

Enable debug logging:
```bash
python3 -m ina219_power.main --config ./config.json --debug
```

## Real-time logs on your phone (hotspot + web page)
This project can serve a tiny web page that streams (“tails”) today’s CSV in real time.

### 1) Run the web tail server
Run the monitor with `--serve`:
```bash
python3 -m ina219_power.main --config ./config.json --serve --http-host 0.0.0.0 --http-port 8080
```

### 2) Create an always-on hotspot (NetworkManager)
This creates a Wi‑Fi AP **SSID** `INA219-LOGS` on `wlan0` with gateway IP **192.168.4.1**.

Pick a password and run:
```bash
sudo nmcli con add type wifi ifname wlan0 con-name ina219-hotspot autoconnect yes ssid "INA219-LOGS"
sudo nmcli con modify ina219-hotspot 802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared ipv4.addresses 192.168.4.1/24
sudo nmcli con modify ina219-hotspot wifi-sec.key-mgmt wpa-psk wifi-sec.psk "CHANGE_ME_PASSWORD"
sudo nmcli con up ina219-hotspot
```

Now connect your phone to Wi‑Fi `INA219-LOGS` and open:
- `http://192.168.4.1:8080/`

### 3) Optional: systemd service to bring up hotspot on boot
After the `ina219-hotspot` connection exists, install the helper unit:
```bash
sudo cp ./systemd/ina219-hotspot.service /etc/systemd/system/ina219-hotspot.service
sudo systemctl daemon-reload
sudo systemctl enable --now ina219-hotspot.service
```

## Logs
- Logs are written to `log_dir` (default `./logs`)
- A new CSV is created per service restart/boot session: `YYYY-MM-DD_<session_id>.csv`
- Optional size-based rollover creates `YYYY-MM-DD_001.csv`, etc.

## Install as a systemd service (auto-start on boot)

### Simple service (keep files where they are)
This setup keeps the repo in place (for example `~/ina219-power`) and the service just points to your paths.

1) Make sure your venv exists in the project directory:
```bash
cd ~/ina219-power
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

2) Edit the unit template and set the correct paths:
- In [`systemd/ina219-power.service`](systemd/ina219-power.service), update:
  - `WorkingDirectory=/home/<user>/ina219-power`
  - `ExecStart=/home/<user>/ina219-power/.venv/bin/python -m ina219_power.main --config /home/<user>/ina219-power/config.json`

### Install the unit
```bash
sudo cp ./systemd/ina219-power.service /etc/systemd/system/ina219-power.service
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
- **Service is running but no CSV appears**: check `log_dir` and make sure it’s writable for the service user. With the provided unit, relative paths are resolved under `WorkingDirectory=` from the unit file.
- **Hotspot web page not opening**: confirm you can `ping 192.168.4.1` from the phone and that the monitor is started with `--serve` (or that `ExecStart` includes it in the service file).
- **Viewing logs**: `sudo journalctl -u ina219-power.service -f`.

### Run as non-root (optional)
If you prefer not to run as root, create/use a user in the `i2c` group:
```bash
sudo usermod -aG i2c pi
```
Then edit the unit file `User=` accordingly.

