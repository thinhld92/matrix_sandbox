import csv
import os
import time
from datetime import datetime, timezone

import ctypes
import redis
import ujson as json

from utils.terminal import dan_tran_cua_so

os.system("title KETOAN TRUONG TONG HOP - SANDBOX")
try:
    ctypes.windll.kernel32.SetConsoleTitleW("KETOAN SANDBOX")
except:
    pass
dan_tran_cua_so(5)

with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

r = redis.Redis(
    host=config["redis"]["host"],
    port=config["redis"]["port"],
    db=config["redis"]["db"],
    decode_responses=True,
)

vps_name = config.get("vps_name", "UNKNOWN_VPS")
chien_thuat = config.get("super_matrix", {}).get("chien_thuat", {})

# So du mo phong
sim_cfg = config.get("simulation", {})
running_balance = sim_cfg.get("initial_balance", 10000.0)
initial_balance = running_balance

history_dir = "history"
os.makedirs(history_dir, exist_ok=True)

# Khoi phuc balance tu file CSV neu co
ten_file_csv = f"sandbox_history_{vps_name}.csv"
csv_file = os.path.join(history_dir, ten_file_csv)
if os.path.isfile(csv_file):
    try:
        with open(csv_file, "r", encoding="utf-8") as f_csv:
            reader = csv.DictReader(f_csv)
            rows = list(reader)
            if rows:
                last_row = rows[-1]
                running_balance = float(last_row.get("Running_Balance", initial_balance))
                print(
                    f"Khoi phuc Balance tu lich su: {running_balance:.2f}$ ({len(rows)} lenh da ghi)"
                )
    except:
        pass

print(f"Ke Toan Truong [{vps_name}] SANDBOX MODE da vao vi tri.")
print(f"Balance hien tai: {running_balance:.2f}$ (Khoi diem: {initial_balance:.2f}$)")
print("Dang lang nghe bien lai mo phong...")

while True:
    try:
        if r.get("SIGNAL:SHUTDOWN"):
            print("Ke Toan nhan lenh rut quan tu Redis! Tam biet!")
            quit()

        data_raw = r.brpop("QUEUE:ACCOUNTANT", timeout=1)

        if data_raw:
            bien_lai = json.loads(data_raw[1])

            pair_group = bien_lai.get("pair_id", "UNKNOWN")
            # Pair_ID trong CSV can la ID duy nhat cua tung lenh mo phong.
            pair_token = bien_lai.get("pair_token", pair_group)
            action_type = bien_lai.get("action_type", "CLOSE")
            huong = bien_lai.get("huong", "")
            b_base = bien_lai.get("base", "")
            b_diff = bien_lai.get("diff", "")
            volume = bien_lai.get("volume", 0.01)

            chenh_vao = bien_lai.get("chenh_vao", 0)
            chenh_dong = bien_lai.get("chenh_dong", 0)

            open_price_base = bien_lai.get("open_price_base", 0)
            close_price_base = bien_lai.get("close_price_base", 0)
            open_price_diff = bien_lai.get("open_price_diff", 0)
            close_price_diff = bien_lai.get("close_price_diff", 0)

            profit_base = bien_lai.get("profit_base", 0)
            profit_diff = bien_lai.get("profit_diff", 0)
            fee_base = bien_lai.get("fee_base", 0)
            fee_diff = bien_lai.get("fee_diff", 0)

            total_fee = fee_base + fee_diff
            net_profit = profit_base + profit_diff - total_fee

            running_balance += net_profit

            if huong == "TH1":
                entry_live = open_price_base - open_price_diff
                close_live = close_price_diff - close_price_base
            elif huong == "TH2":
                entry_live = open_price_diff - open_price_base
                close_live = close_price_base - close_price_diff
            else:
                entry_live, close_live = 0.0, 0.0

            speed_base_entry = bien_lai.get("speed_base_entry", 0)
            speed_diff_entry = bien_lai.get("speed_diff_entry", 0)
            speed_base_close = bien_lai.get("speed_base_close", 0)
            speed_diff_close = bien_lai.get("speed_diff_close", 0)

            file_exists = os.path.isfile(csv_file)

            try:
                with open(csv_file, mode="a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    if not file_exists:
                        writer.writerow(
                            [
                                "Time_Closed_UTC",
                                "Pair_ID",
                                "Action",
                                "Direction",
                                "Volume",
                                "Base_Broker",
                                "Diff_Broker",
                                "Entry_Dev",
                                "Entry_Live",
                                "Close_Dev",
                                "Close_Live",
                                "Base_Open",
                                "Base_Close",
                                "Diff_Open",
                                "Diff_Close",
                                "Profit_Base",
                                "Profit_Diff",
                                "Fee_Base",
                                "Fee_Diff",
                                "Total_Fee",
                                "Net_Profit",
                                "Running_Balance",
                                "Speed_Base_Entry",
                                "Speed_Diff_Entry",
                                "Speed_Base_Close",
                                "Speed_Diff_Close",
                                "Cfg_Dev_Entry",
                                "Cfg_Dev_Close",
                                "Cfg_Stable_Time",
                            ]
                        )

                    writer.writerow(
                        [
                            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                            pair_token,
                            action_type,
                            huong,
                            volume,
                            b_base,
                            b_diff,
                            f"{chenh_vao:.2f}",
                            f"{entry_live:.2f}",
                            f"{chenh_dong:.2f}",
                            f"{close_live:.2f}",
                            open_price_base,
                            close_price_base,
                            open_price_diff,
                            close_price_diff,
                            f"{profit_base:.2f}",
                            f"{profit_diff:.2f}",
                            f"{fee_base:.2f}",
                            f"{fee_diff:.2f}",
                            f"{total_fee:.2f}",
                            f"{net_profit:.2f}",
                            f"{running_balance:.2f}",
                            speed_base_entry,
                            speed_diff_entry,
                            speed_base_close,
                            speed_diff_close,
                            f"{chien_thuat.get('deviation_entry', 0):.3f}",
                            f"{chien_thuat.get('deviation_close', 0):.3f}",
                            chien_thuat.get("stable_time", 0),
                        ]
                    )

                pnl_icon = "[OK]" if net_profit >= 0 else "[LOSS]"
                print(
                    f"{pnl_icon} Ghi so: {pair_token} | {action_type} | Net: {net_profit:.2f}$ | Balance: {running_balance:.2f}$"
                )

            except PermissionError:
                print(
                    f"LOI: Hay dong file Excel {ten_file_csv} de Ke Toan ghi so! Dang cho..."
                )
                running_balance -= net_profit
                r.rpush("QUEUE:ACCOUNTANT", data_raw[1])
                time.sleep(3)

    except Exception as e:
        print(f"Ke toan gap loi vat: {e}")
        time.sleep(1)
