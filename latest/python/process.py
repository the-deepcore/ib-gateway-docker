import subprocess
import os

def process_status(process_name):
    try:
        output = subprocess.check_output(["pgrep", process_name])
        return len([int(s) for s in output.split() if s.isdigit()]) > 1
    except subprocess.CalledProcessError:
        return False

process_name = "python3"
if process_status(process_name):
    print(f"Process {process_name} is running.")
else:
    os.system("sh /etc/init.d/ib-gateway start > /app/main.log")
