from machine import Pin
import sensor
import os
import time
import machine
import random
import gc
import network
import ubinascii
import json
import requests

URL = "https://api.vyomiq.io/watchman/upload/"

wifi_nic = None
WIFI_SSID = "xx"
WIFI_PASSWORD = "00000000"

def init_wifi():
    # Input: None; Output: bool indicating if WiFi connection was successful
    global wifi_nic
    try:
        print(f"[WIFI] Initializing WiFi connection to SSID: {WIFI_SSID} password: {WIFI_PASSWORD}")
        # Create WLAN interface in station mode
        wifi_nic = network.WLAN(network.WLAN.IF_STA)

        # Activate the interface
        wifi_nic.active(True)

        # Connect to WiFi access point
        print(f"[WIFI] Connecting to WiFi network: {WIFI_SSID}")
        wifi_nic.connect(WIFI_SSID, WIFI_PASSWORD)

        # Wait for connection with timeout
        max_wait = 20  # Maximum wait time in seconds
        wait_count = 0
        while wait_count < max_wait:
            if wifi_nic.isconnected():
                # Connection successful
                ifconfig = wifi_nic.ifconfig()
                print(f"[WIFI] WiFi connected successfully!, IP add: {ifconfig[0]}, Subnet mask: {ifconfig[1]}, Gateway: {ifconfig[2]}, DNS: {ifconfig[3]}")
                return True

            # Check for connection errors (if status() is available)
            try:
                status = wifi_nic.status()
                # Try to detect common error statuses if constants exist
                if hasattr(network.WLAN, 'STAT_WRONG_PASSWORD') and status == network.WLAN.STAT_WRONG_PASSWORD:
                    print(f"[WIFI] Connection failed: Wrong password")
                    wifi_nic.active(False)
                    return False
                elif hasattr(network.WLAN, 'STAT_NO_AP_FOUND') and status == network.WLAN.STAT_NO_AP_FOUND:
                    print(f"[WIFI] Connection failed: Access point not found")
                    wifi_nic.active(False)
                    return False
                elif hasattr(network.WLAN, 'STAT_CONNECT_FAIL') and status == network.WLAN.STAT_CONNECT_FAIL:
                    print(f"[WIFI] Connection failed: Connection failed")
                    wifi_nic.active(False)
                    return False
                print(f"[WIFI] Connecting... (status: {status}, wait: {wait_count}s)")
            except Exception as e:
                # Status checking not available, just log wait time
                print(f"[WIFI] error in Connecting... (wait: {wait_count}s) : {e}")

            time.sleep(1)
            wait_count += 1

        print(f"[WIFI] Wifi connection timeout after {max_wait} seconds")
        wifi_nic.active(False)
        return False

    except Exception as e:
        print(f"[WIFI] error in initialization: {e}")
        if wifi_nic:
            try:
                wifi_nic.active(False)
            except:
                pass
        return False

def wifi_upload_payload(payload, msg_typ, creator): # FINAL
    # Input: payload: dict payload; msg_typ: str, creator: int; Output: bool upload success
    """Send payload via WiFi"""
    global wifi_nic
    if not wifi_nic or not wifi_nic.isconnected():
        print(f"WiFi not connected")
        return False

    try:
        headers = {"Content-Type": "application/json"}
        json_payload = json.dumps(payload)
        response = requests.post(URL, data=json_payload, headers=headers)
        if response.status_code == 200 or response.status_code == 201:
            return True
        else:
            print(f"Image upload failed: status {response.status_code}, response {str(response)}")
            try:
                response_text = response.text
            except:
                response_text = "Unable to read response body"
            try:
                response_json = response.json()
                error_details = f"JSON: {json.dumps(response_json)}"
            except:
                error_details = f"Text: {response_text[:500]}"  # Limit to first 500 chars
            print(f"Image upload failed: status {response.status_code}, {error_details}")
            return False
    except Exception as e:
        print(f"Image upload : error in wifi_upload_payload: {e}")
        return False

def upload_image(img, pid, pir, count):
    imgbytes = img.compress().bytearray()
    print(f"[IMG] ⋙⋙⋙ Uploading encrypted image (size: {len(imgbytes)} bytes), file:{count}_{pir}")
    imgbytes_b64 = ubinascii.b2a_base64(imgbytes).decode("ascii").strip()
    img_payload =  {
                   "pid": pid,
                   "message_type": "img",
                   "image": imgbytes_b64,
                   "pir" : pir,
                   "count" : count
               }
    return wifi_upload_payload(img_payload, "t", 0)
# --- Configuration ---
PIR_PIN = Pin('P8', Pin.IN, Pin.PULL_DOWN)  # Adjust pin as needed

sensor.reset()
sensor.set_pixformat(sensor.RGB565)
sensor.set_framesize(sensor.SVGA)
sensor.skip_frames(time=2000)
sensor.set_auto_whitebal(False)
led = machine.LED("LED_RED")

def get_rand(len=3):
    # Input: None; Output: str random 3-letter uppercase identifier
    rstr = ""
    for i in range(len):
        rstr += chr(65+random.randint(0,25))
    return rstr

PID = get_rand()

def main():
    if not init_wifi():
        return
    count=0
    img = None
    succ_count = 0
    pir_count = 0
    while count < 3:
        gc.collect()
        count+=1
        pir_val = PIR_PIN.value()
        if pir_val:
            pir_count += 1
        img = sensor.snapshot()
        succ = upload_image(img, PID, pir_val, count)
        if succ:
            succ_count += 1
            print(f"Succ uploading image: {count}")
        else:
            print(f"Error uploading image: {count}")
    print(f"Successfully uploaded : {succ_count} images out of {count} out of which {pir_count} had PIR triggered")

if __name__ == "__main__":
    main()
