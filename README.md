# INA219 Power Monitor for Raspberry Pi 4B

This project monitors power consumption using an INA219 current/power monitor with a 100mΩ (R100) shunt resistor connected to a Raspberry Pi 4B via I2C.

## Features

- Real-time power, current, and voltage monitoring
- Continuous logging to file
- 10-minute summary statistics
- Simple and easy to use

## Hardware Requirements

- Raspberry Pi 4B
- INA219 Current/Power Monitor Breakout Board
- 100mΩ (0.1Ω) shunt resistor (R100)
- Jumper wires for I2C connection

## Hardware Connections

Connect the INA219 to your Raspberry Pi 4B as follows:

### INA219 Pin Connections

| INA219 Pin | Raspberry Pi 4B Pin | Description |
|------------|---------------------|-------------|
| VCC        | Pin 1 (3.3V)        | Power supply |
| GND        | Pin 6 (GND)         | Ground |
| SDA        | Pin 3 (GPIO 2, SDA) | I2C Data line |
| SCL        | Pin 5 (GPIO 3, SCL) | I2C Clock line |

### Power Measurement Setup

1. **Shunt Resistor**: The INA219 uses a 100mΩ (0.1Ω) shunt resistor (R100) that is typically built into the breakout board.

2. **Load Connection**:
   - Connect your **load's positive terminal** to **VIN+** on the INA219
   - Connect your **load's negative terminal** to **VIN-** on the INA219
   - The INA219 measures the voltage drop across the shunt resistor to calculate current

3. **Power Supply**:
   - The INA219 itself needs 3.3V power (from Pi pin 1)
   - Your load can be powered separately (up to 26V for INA219)

### Pin Layout Reference (Raspberry Pi 4B)

```
    3.3V  [1]  [2]  5V
    SDA   [3]  [4]  5V
    SCL   [5]  [6]  GND
    ...
```

## Software Setup

### 1. Enable I2C on Raspberry Pi

```bash
sudo raspi-config
```

Navigate to:
- **Interface Options** → **I2C** → **Yes** to enable

Alternatively, enable via command line:
```bash
sudo apt-get update
sudo apt-get install -y i2c-tools
sudo raspi-config nonint do_i2c 0
```

### 2. Verify I2C Connection

Check if INA219 is detected (default address is 0x40):
```bash
sudo i2cdetect -y 1
```

You should see `40` in the output if the connection is correct.

### 3. Install Python Dependencies

```bash
pip3 install -r requirements.txt
```

Or install manually:
```bash
pip3 install adafruit-circuitpython-ina219 adafruit-blinka
```

### 4. Run the Power Monitor

```bash
python3 power_monitor.py
```

Or make it executable and run directly:
```bash
chmod +x power_monitor.py
./power_monitor.py
```

## Usage

The script will:
- Read power, current, and voltage every second
- Log all measurements to `power_consumption.log`
- Display real-time readings in the console
- Generate a 10-minute summary with:
  - Average voltage, current, and power
  - Minimum and maximum power
  - Total energy consumed (Wh)
  - Number of samples collected

### Example Output

**Real-time logging:**
```
2026-01-23 10:15:30 - INFO - Time: 2026-01-23 10:15:30 | Voltage: 5.123V | Current: 0.456A | Power: 2.336W
```

**10-minute summary:**
```
============================================================
10-MINUTE SUMMARY (2026-01-23 10:25:30)
============================================================
Average Voltage:     5.120 V
Average Current:     0.455 A
Average Power:       2.330 W
Minimum Power:       2.100 W
Maximum Power:       2.500 W
Total Energy:        0.388 Wh
Samples Collected:  600
============================================================
```

## Stopping the Monitor

Press `Ctrl+C` to stop monitoring. The script will generate a final summary before exiting.

## Log Files

All measurements are logged to `power_consumption.log` in the same directory. The log file includes timestamps and can be analyzed later.

## Troubleshooting

### INA219 not detected
- Check I2C connections (SDA, SCL)
- Verify I2C is enabled: `sudo raspi-config`
- Check wiring with `sudo i2cdetect -y 1`
- Ensure 3.3V power is connected

### Permission errors
- Run with `sudo` if needed: `sudo python3 power_monitor.py`
- Add user to i2c group: `sudo usermod -aG i2c $USER` (then logout/login)

### Incorrect readings
- Verify shunt resistor value (should be 0.1Ω)
- Check load connections (VIN+ and VIN-)
- Ensure load voltage is within INA219 range (0-26V)

## Configuration

You can modify these constants in `power_monitor.py`:
- `SHUNT_OHMS`: Shunt resistor value (default: 0.1Ω)
- `SUMMARY_INTERVAL`: Time between summaries in seconds (default: 600 = 10 minutes)
- `READ_INTERVAL`: Time between readings in seconds (default: 1)
- `LOG_FILE`: Log file name (default: "power_consumption.log")

## License

This project is provided as-is for educational and personal use.
