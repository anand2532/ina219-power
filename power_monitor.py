#!/usr/bin/env python3
"""
INA219 Power Monitor for Raspberry Pi 4B
Monitors power consumption with real-time logging and 10-minute summaries
"""

import time
import logging
from datetime import datetime
from collections import deque
import board
import busio
from adafruit_ina219 import INA219, ADCResolution, BusVoltageRange

# Configuration
SHUNT_OHMS = 0.1  # 100mΩ shunt resistor (R100)
LOG_FILE = "power_consumption.log"
SUMMARY_INTERVAL = 600  # 10 minutes in seconds
READ_INTERVAL = 1  # Read every 1 second

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

class PowerMonitor:
    def __init__(self):
        """Initialize INA219 sensor"""
        try:
            # Initialize I2C bus
            i2c = busio.I2C(board.SCL, board.SDA)
            
            # Initialize INA219
            # Note: Library assumes 0.1Ω shunt resistor by default (which matches R100)
            self.ina = INA219(i2c)
            
            # Configure ADC resolution and voltage range (if supported)
            try:
                self.ina.bus_adc_resolution = ADCResolution.ADCRES_12BIT_32S
                self.ina.shunt_adc_resolution = ADCResolution.ADCRES_12BIT_32S
                self.ina.bus_voltage_range = BusVoltageRange.RANGE_16V
            except AttributeError:
                # Some library versions may not support these attributes
                # Default settings will be used
                logging.info("Using default INA219 configuration")
            
            logging.info("INA219 initialized successfully")
            logging.info(f"Using default 0.1Ω shunt resistor (R100)")
        except Exception as e:
            logging.error(f"Failed to initialize INA219: {e}")
            raise
    
    def read_measurements(self):
        """Read current, voltage, and power from INA219"""
        try:
            # bus_voltage is the voltage across the load (V+ to V-)
            # This is already the load voltage we want
            bus_voltage = self.ina.bus_voltage
            
            # shunt_voltage is the voltage drop across the shunt resistor
            # Used internally by INA219 to calculate current
            shunt_voltage = self.ina.shunt_voltage
            
            # Current is returned in milliamps, convert to Amps
            current = self.ina.current / 1000.0
            
            # Calculate power manually: P = V * I
            # bus_voltage is the load voltage, so use it directly
            power = bus_voltage * current
            
            # Try to get power from library as well (for comparison)
            try:
                library_power = self.ina.power / 1000.0  # Convert mW to W
            except:
                library_power = power  # Fallback to calculated power
            
            return {
                'voltage': bus_voltage,  # bus_voltage IS the load voltage
                'current': current,
                'power': power,  # Use calculated power
                'bus_voltage': bus_voltage,
                'shunt_voltage': shunt_voltage
            }
        except Exception as e:
            logging.error(f"Error reading measurements: {e}")
            return None
    
    def monitor(self):
        """Main monitoring loop"""
        logging.info("Starting power monitoring...")
        logging.info(f"Summary interval: {SUMMARY_INTERVAL} seconds ({SUMMARY_INTERVAL/60:.1f} minutes)")
        logging.info(f"Reading interval: {READ_INTERVAL} second(s)")
        logging.info("-" * 60)
        
        measurements = deque()
        last_summary_time = time.time()
        
        try:
            while True:
                data = self.read_measurements()
                
                if data:
                    timestamp = datetime.now()
                    
                    # Log real-time data
                    log_msg = (
                        f"Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')} | "
                        f"Voltage: {data['voltage']:.3f}V | "
                        f"Current: {data['current']:.3f}A | "
                        f"Power: {data['power']:.3f}W"
                    )
                    logging.info(log_msg)
                    
                    # Store measurement for summary
                    measurements.append({
                        'timestamp': timestamp,
                        'voltage': data['voltage'],
                        'current': data['current'],
                        'power': data['power']
                    })
                    
                    # Generate summary every 10 minutes
                    current_time = time.time()
                    if current_time - last_summary_time >= SUMMARY_INTERVAL:
                        self.print_summary(measurements)
                        measurements.clear()
                        last_summary_time = current_time
                
                time.sleep(READ_INTERVAL)
                
        except KeyboardInterrupt:
            logging.info("\nMonitoring stopped by user")
            if measurements:
                self.print_summary(measurements)
    
    def print_summary(self, measurements):
        """Print 10-minute summary statistics"""
        if not measurements:
            return
        
        voltages = [m['voltage'] for m in measurements]
        currents = [m['current'] for m in measurements]
        powers = [m['power'] for m in measurements]
        
        avg_voltage = sum(voltages) / len(voltages)
        avg_current = sum(currents) / len(currents)
        avg_power = sum(powers) / len(powers)
        min_power = min(powers)
        max_power = max(powers)
        total_energy = sum(powers) * (READ_INTERVAL / 3600)  # Wh
        
        summary = f"""
{'=' * 60}
10-MINUTE SUMMARY ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
{'=' * 60}
Average Voltage:     {avg_voltage:.3f} V
Average Current:     {avg_current:.3f} A
Average Power:       {avg_power:.3f} W
Minimum Power:       {min_power:.3f} W
Maximum Power:       {max_power:.3f} W
Total Energy:        {total_energy:.3f} Wh
Samples Collected:  {len(measurements)}
{'=' * 60}
"""
        logging.info(summary)

def main():
    """Main entry point"""
    try:
        monitor = PowerMonitor()
        monitor.monitor()
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        return 1
    return 0

if __name__ == "__main__":
    exit(main())
