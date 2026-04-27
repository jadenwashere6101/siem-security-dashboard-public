import argparse
import os
import random
import time

import requests
from dotenv import load_dotenv


def env_first(*names, default=None):
    for name in names:
        value = os.getenv(name)
        if value not in (None, ""):
            return value
    return default


load_dotenv()

# DEFAULT CONFIG
SIEM_URL = env_first("SIEM_INGEST_URL", "SIEM_API_URL", "SIEM_URL", default="http://127.0.0.1:5051/ingest")
SIEM_INGEST_API_KEY = env_first("SIEM_INGEST_API_KEY", "INGEST_API_KEY", default="")


def send_event(event_type, severity, source_ip, message):
    payload = {
        "event_type": event_type,
        "severity": severity,
        "source_ip": source_ip,
        "message": message,
        "app_name": "simulator",
        "environment": "dev"
    }

    headers = {}
    if SIEM_INGEST_API_KEY:
        headers["X-API-Key"] = SIEM_INGEST_API_KEY

    try:
        response = requests.post(SIEM_URL, json=payload, headers=headers, timeout=2)
        print(f"POST {SIEM_URL} -> {response.status_code}")
        print(response.text)
    except Exception as e:
        print(f"Error sending event: {e}")


def simulate_failed_logins(count, ip):
    print(f"Sending {count} failed login attempts from {ip}")

    for i in range(count):
        send_event(
            event_type="failed_login",
            severity="medium",
            source_ip=ip,
            message=f"Simulated failed login #{i+1}"
        )
        time.sleep(0.2)  # small delay so logs look realistic


def simulate_noise():
    print("Sending random background noise...")

    for _ in range(20):
        ip = f"192.168.1.{random.randint(1, 255)}"
        send_event(
            event_type="normal_activity",
            severity="low",
            source_ip=ip,
            message="Normal system activity"
        )
        time.sleep(0.1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--failed-logins", type=int, default=0, help="Number of failed login attempts")
    parser.add_argument("--ip", type=str, default="1.2.3.4", help="Source IP")

    args = parser.parse_args()

    if args.failed_logins > 0:
        simulate_failed_logins(args.failed_logins, args.ip)
    else:
        simulate_noise()
