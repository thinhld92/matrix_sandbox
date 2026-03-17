import redis
import ujson as json
import time
import csv
import os
from datetime import datetime
import ctypes

os.system("title 👓 KẾ TOÁN TRƯỞNG TỔNG HỢP")
try: ctypes.windll.kernel32.SetConsoleTitleW("👓 KẾ TOÁN TRƯỞNG")
except: pass

with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

r = redis.Redis(host=config['redis']['host'], port=config['redis']['port'], db=config['redis']['db'], decode_responses=True)

vps_name = config.get("vps_name", "UNKNOWN_VPS")
chien_thuat = config.get('super_matrix', {}).get('chien_thuat', {})

history_dir = "history"
os.makedirs(history_dir, exist_ok=True)
pending_receipts = {}
receipt_timestamps = {}

print(f"👓 Kế Toán Trưởng [{vps_name}] đã vào vị trí. Đang lắng nghe biên lai...")

while True:
    try:
        now_sec = time.time()

        # 👉 Kiểm tra tín hiệu tắt máy từ Redis
        if r.get("SIGNAL:SHUTDOWN"):
            print("🛑 Kế Toán nhận lệnh rút quân từ Redis! Tạm biệt!")
            quit()

        data_raw = r.brpop("QUEUE:ACCOUNTANT", timeout=1)

        if data_raw:
            bien_lai = json.loads(data_raw[1])
            ctx = bien_lai.get("context", {})
            pair_token = ctx.get("pair_token")
            broker_name = bien_lai.get("role") 
            
            if not pair_token or not broker_name: continue
            
            if pair_token not in pending_receipts: 
                pending_receipts[pair_token] = {}
                receipt_timestamps[pair_token] = now_sec 
                
            pending_receipts[pair_token][broker_name] = bien_lai
            
            is_single = ctx.get("is_single_cut", False)
            danh_sach_san_trong_pair = list(pending_receipts[pair_token].keys())

            if is_single or len(danh_sach_san_trong_pair) == 2:
                ten_file_csv = f"trade_history_{vps_name}.csv"
                csv_file = os.path.join(history_dir, ten_file_csv)
                file_exists = os.path.isfile(csv_file)
                
                try:
                    with open(csv_file, mode='a', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        if not file_exists:
                            writer.writerow([
                                'Time_Closed', 'Pair_ID', 'Action', 'Volume', 
                                'Leg1_Broker', 'Leg1_Ticket', 'Leg2_Broker', 'Leg2_Ticket',
                                'Entry_Mode', 'Entry_Dev', 'Entry_Live',
                                'Close_Mode', 'Close_Dev', 'Close_Live',
                                'Leg1_Open', 'Leg1_Close', 'Leg2_Open', 'Leg2_Close', 
                                'Leg1_Profit', 'Leg2_Profit', 'Total_Fee', 'Net_Profit',
                                'Leg1_Speed_Entry', 'Leg2_Speed_Entry', 'Leg1_Speed_Close', 'Leg2_Speed_Close',
                                'Cfg_Dev_Entry', 'Cfg_Dev_Close', 'Cfg_Stable_Time'
                            ])
                        
                        if is_single or len(danh_sach_san_trong_pair) == 1:
                            single_data = pending_receipts[pair_token][broker_name]
                            b1_name, b1_ticket = broker_name, single_data['ticket']
                            b2_name, b2_ticket = "N/A", "N/A"
                            b1_prof, b2_prof = single_data['profit'], 0.0
                            b1_op, b1_cp = single_data['open_price'], single_data['close_price']
                            b2_op, b2_cp = 0.0, 0.0
                            total_fee = single_data['fee']
                            vol = single_data['volume']
                            net_profit = b1_prof + total_fee
                            
                            entry_live, close_live = 0.0, 0.0
                            if not is_single: ctx['mode_dong'] = "[INCOMPLETE]"
                        else:
                            broker_1, broker_2 = danh_sach_san_trong_pair[0], danh_sach_san_trong_pair[1]
                            leg1, leg2 = pending_receipts[pair_token][broker_1], pending_receipts[pair_token][broker_2]
                            
                            b1_name, b1_ticket = broker_1, leg1['ticket']
                            b2_name, b2_ticket = broker_2, leg2['ticket']
                            b1_prof, b2_prof = leg1['profit'], leg2['profit']
                            b1_op, b1_cp = leg1['open_price'], leg1['close_price']
                            b2_op, b2_cp = leg2['open_price'], leg2['close_price']
                            total_fee = leg1['fee'] + leg2['fee']
                            vol = leg1['volume'] 
                            net_profit = b1_prof + b2_prof + total_fee
                            
                            # 👉 THUẬT TOÁN ĐO TRƯỢT GIÁ CHÍNH XÁC CÓ DẤU ÂM
                            huong = ctx.get("huong", "")
                            c_base = ctx.get("base", "")
                            c_diff = ctx.get("diff", "")
                            
                            if huong and c_base and c_diff and c_base in pending_receipts[pair_token] and c_diff in pending_receipts[pair_token]:
                                base_op = pending_receipts[pair_token][c_base]['open_price']
                                base_cp = pending_receipts[pair_token][c_base]['close_price']
                                diff_op = pending_receipts[pair_token][c_diff]['open_price']
                                diff_cp = pending_receipts[pair_token][c_diff]['close_price']
                                
                                if huong == "TH1":
                                    entry_live = base_op - diff_op
                                    close_live = diff_cp - base_cp
                                elif huong == "TH2":
                                    entry_live = diff_op - base_op
                                    close_live = base_cp - diff_cp
                                else:
                                    entry_live, close_live = 0.0, 0.0
                            else:
                                entry_live, close_live = 0.0, 0.0
                                
                        # Map base và diff với Leg1 và Leg2 để cột Speed khớp tên sàn
                        b1_speed_entry = ctx.get("speed_base_entry", 0) if b1_name == ctx.get("base") else ctx.get("speed_diff_entry", 0)
                        b1_speed_close = ctx.get("speed_base_close", 0) if b1_name == ctx.get("base") else ctx.get("speed_diff_close", 0)
                        b2_speed_entry = ctx.get("speed_diff_entry", 0) if b1_name == ctx.get("base") else ctx.get("speed_base_entry", 0)
                        b2_speed_close = ctx.get("speed_diff_close", 0) if b1_name == ctx.get("base") else ctx.get("speed_base_close", 0)
                        
                        writer.writerow([
                            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            ctx.get('pair_id', 'UNKNOWN'), ctx.get('action_type', 'CLOSE'), vol,
                            b1_name, b1_ticket, b2_name, b2_ticket,
                            ctx.get('mode_vao', ''), f"{ctx.get('chenh_vao', 0):.2f}", f"{entry_live:.2f}",
                            ctx.get('mode_dong', ''), f"{ctx.get('chenh_dong', 0):.2f}", f"{close_live:.2f}",
                            b1_op, b1_cp, b2_op, b2_cp,
                            f"{b1_prof:.2f}", f"{b2_prof:.2f}", f"{total_fee:.2f}", f"{net_profit:.2f}",
                            b1_speed_entry, b2_speed_entry, b1_speed_close, b2_speed_close,
                            f"{chien_thuat.get('deviation_entry', 0):.3f}", f"{chien_thuat.get('deviation_close', 0):.3f}", chien_thuat.get('stable_time', 0)
                        ])
                    
                    print(f"✅ Đã ghi sổ: {pair_token} | Lời/Lỗ: {net_profit:.2f}$")
                    del pending_receipts[pair_token] 
                    if pair_token in receipt_timestamps: del receipt_timestamps[pair_token]

                except PermissionError:
                    print(f"⚠️ LỖI: Hãy đóng file Excel {ten_file_csv} để Kế Toán ghi sổ! Đang chờ...")
                    time.sleep(3)
                    
        # Quét dọn rác RAM (Biên lai mồ côi)
        tokens_to_delete = []
        for p_token, t_stamp in receipt_timestamps.items():
            if now_sec - t_stamp > 3600: 
                print(f"🧹 Dọn rác: Cặp {p_token} bị thiếu 1 chân quá lâu. Ép ghi sổ mồ côi!")
                b_name = list(pending_receipts[p_token].keys())[0]
                pending_receipts[p_token][b_name]["context"]["is_single_cut"] = True
                r.lpush("QUEUE:ACCOUNTANT", json.dumps(pending_receipts[p_token][b_name]))
                tokens_to_delete.append(p_token)

        for tk in tokens_to_delete:
            del pending_receipts[tk]
            del receipt_timestamps[tk]

    except Exception as e:
        print(f"⚠️ Kế toán gặp lỗi vặt: {e}")
        time.sleep(1)