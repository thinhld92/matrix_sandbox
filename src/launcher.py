import json
import os
import subprocess
import time

os.system("title MATRIX SANDBOX - LAUNCHER")

print("DANG KHOI DONG HE THONG MATRIX SANDBOX (CHE DO MO PHONG)...")

try:
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)
except Exception as e:
    print(f"[ERROR] Loi doc config.json: {e}")
    quit()

matrix_cfg = config.get("super_matrix", {})
active_brokers = matrix_cfg.get("active_brokers", [])
symbol_map = matrix_cfg.get("symbol_mapping", {})
sim_cfg = config.get("simulation", {})
telegram_enabled = config.get("telegram", {}).get("enable", False)

if not active_brokers:
    print("[ERROR] Khong co san nao duoc khai bao trong active_brokers!")
    quit()

print("Che do: SANDBOX (Mo phong)")
print(f"Balance: {sim_cfg.get('initial_balance', 10000.0)}$ | Lot: {sim_cfg.get('lot_size', 0.01)}")

next_window_slot = 1

if telegram_enabled:
    print("Dang goi lien lac: Telegram Service...")
    telegram_env = os.environ.copy()
    telegram_env["MATRIX_WINDOW_SLOT"] = str(next_window_slot)
    subprocess.Popen(
        ["cmd", "/k", "python", "src/services/telegram_bot.py"],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        env=telegram_env,
    )
    next_window_slot += 1
    time.sleep(2)

worker_specs = []
for broker in active_brokers:
    symbol = symbol_map.get(broker, "")
    if not symbol:
        print(f"[WARN] Thieu mapping ma giao dich cho san {broker}. Bo qua!")
        continue
    worker_specs.append((broker, symbol))

print(f"\nDANG BO TRI DAN TRINH SAT ({len(worker_specs)} SAN)...")
for worker_index, (broker, symbol) in enumerate(worker_specs):

    print(f"   -> Dang goi Worker: {broker} - {symbol} [TICK-ONLY]")
    worker_env = os.environ.copy()
    worker_env["MATRIX_WINDOW_SLOT"] = str(next_window_slot)
    worker_env["MATRIX_WINDOW_LAYOUT"] = "three_panel"
    worker_env["MATRIX_WINDOW_ROLE"] = "worker"
    worker_env["MATRIX_WORKER_INDEX"] = str(worker_index)
    worker_env["MATRIX_WORKER_COUNT"] = str(len(worker_specs))
    subprocess.Popen(
        ["cmd", "/k", "python", "src/worker.py", "--broker", broker, "--symbol", symbol, "--role", broker],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        env=worker_env,
    )
    next_window_slot += 1
    time.sleep(3)

print("\nDANG DANH THUC SUPER MASTER SANDBOX...")
master_env = os.environ.copy()
master_env["MATRIX_WINDOW_SLOT"] = str(next_window_slot)
master_env["MATRIX_WINDOW_LAYOUT"] = "three_panel"
master_env["MATRIX_WINDOW_ROLE"] = "master"
subprocess.Popen(
    ["cmd", "/k", "python", "src/super_master.py"],
    creationflags=subprocess.CREATE_NEW_CONSOLE,
    env=master_env,
)
next_window_slot += 1
time.sleep(2)

print("\nDANG DANH THUC KETOAN SANDBOX...")
accountant_env = os.environ.copy()
accountant_env["MATRIX_WINDOW_SLOT"] = str(next_window_slot)
accountant_env["MATRIX_WINDOW_LAYOUT"] = "three_panel"
accountant_env["MATRIX_WINDOW_ROLE"] = "accountant"
command = 'start "KETOAN_SANDBOX" cmd /k python src/accountant.py'
subprocess.Popen(command, shell=True, env=accountant_env)
time.sleep(2)

print("\nTAT CA QUAN DOAN SANDBOX DA VAO VI TRI!")
print(f"Dan tran: 1 Super Master, 1 Ke Toan, va {len(active_brokers)} Worker tick-only.")
print("Moi lenh deu la mo phong, khong anh huong tien that.")
