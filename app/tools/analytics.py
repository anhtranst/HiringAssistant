import csv, os

LOG_PATH = os.path.join("logs", "usage.csv")

def log_event(name: str, payload: dict):
    os.makedirs("logs", exist_ok=True)
    header = ["event", "payload"]
    exists = os.path.isfile(LOG_PATH)
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(header)
        w.writerow([name, str(payload)])
