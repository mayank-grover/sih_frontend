# ingest/push_predictions.py
import requests
import pandas as pd
import sys
import time

BACKEND = "http://localhost:8000"  # change if needed

def push_csv(csv_path):
    files = {"file": open(csv_path, "rb")}
    r = requests.post(f"{BACKEND}/upload_csv", files=files)
    print("status", r.status_code, r.text)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python push_predictions.py path/to/predictions.csv")
        sys.exit(1)
    push_csv(sys.argv[1])

