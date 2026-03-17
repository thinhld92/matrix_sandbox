import os
import redis
import ujson as json
import time
import itertools
from datetime import datetime, timezone
import ctypes

from utils.trading_logic import check_tin_hieu_arbitrage 
from utils.terminal import dan_tran_cua_so

os.system("title 🧠 ĐÔ ĐỐC TỔNG TƯ LỆNH - MATRIX HEDGER")
try:
    ctypes.windll.kernel32.SetConsoleTitleW("🧠 ĐÔ ĐỐC MATRIX HEDGER")
except:
    pass
dan_tran_cua_so(4)

print("🚀 ĐANG KHỞI ĐỘNG HỆ THỐNG MATRIX HEDGER...")

with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

redis_conf = config['redis']
r = redis.Redis(host=redis_conf['host'], port=redis_conf['port'], db=redis_conf['db'], decode_responses=True)

matrix_cfg = config['super_matrix']
active_brokers = matrix_cfg['active_brokers']
symbol_map = matrix_cfg['symbol_mapping']
vol_map = matrix_cfg['volume_mapping']
chien_thuat = matrix_cfg['chien_thuat']
quan_tri = matrix_cfg['quan_tri_rui_ro']

print("=" * 60)
print("🎯 THÔNG SỐ CHIẾN LƯỢC ĐÃ NẠP:")
print(f" ┣ 📈 Chế độ bắn: [{chien_thuat.get('stable_mode').upper()}] | Đóng băng in/out: {chien_thuat.get('stable_time')}ms")
print(f" ┣ 🎯 Lệch VÀO: {chien_thuat.get('deviation_entry')} | Lệch CHỐT: {chien_thuat.get('deviation_close')}")
print(f" ┣ ⏳ Hold Time tối thiểu: {chien_thuat.get('hold_time')}s")
print(f" ┣ ⏱️ Cooldown Mở: {chien_thuat.get('cooldown_second')}s | Cooldown Đóng (Van xả): {chien_thuat.get('cooldown_close_second')}s")
print(f" ┣ 🛡️ Equity Báo động: < {chien_thuat.get('alert_equity')}$")
print(f" ┣ 👻 Diệt Tick Ma (Feed Timeout): Quá {quan_tri.get('max_tick_delay_second', 15.0)}s")
print(f" ┗ ⚔️ Tối đa {quan_tri.get('max_concurrent_pairs')} Cặp song song | {quan_tri.get('max_orders_per_broker')} Lệnh/Sàn")
print("=" * 60)

danh_sach_cap_cheo = list(itertools.combinations(active_brokers, 2))

# ==========================================
# HÀM KIỂM TRA GIỜ (GMT+0)
# ==========================================
def kiem_tra_gio(khung_gio_list, thoi_gian_hien_tai):
    if not khung_gio_list: return True 
    for khung in khung_gio_list:
        start, end = khung.split('-')
        if start <= end:
            if start <= thoi_gian_hien_tai <= end: return True
        else:
            if thoi_gian_hien_tai >= start or thoi_gian_hien_tai <= end: return True
    return False

# ==========================================
# TRÍ NHỚ VÀ KHÔI PHỤC TRẠNG THÁI 
# ==========================================
KEY_STATE = "STATE:SUPER_MASTER"

# ĐÃ FIX RÒ RỈ BỘ NHỚ: TẤT CẢ DICT NÀY CHỈ ĐƯỢC DÙNG KEY LÀ `pair_group`
dong_ho_vao = {}        
dong_ho_dong = {}       
thoi_diem_nhan_tick_cuoi = {} 

# 👉 THÊM DÒNG NÀY VÀO: Đồng hồ theo dõi tuổi thọ của lệnh lẻ
thoi_diem_phat_hien_ve_le = {}

chuyen_xe_dang_cho = [] 
lich_su_vao_lenh = []       
huong_dang_danh_map = {}        
thoi_diem_vao_lenh_cuoi_map = {} 
thoi_diem_dong_lenh_cuoi_map = {}
orphan_count = {b: 0 for b in active_brokers}        
broker_cooldown_until = {b: 0 for b in active_brokers}

# Đồng hồ ghi nhớ sự sống của Tick Giá để diệt Tick Ma (Fix Múi Giờ)
last_seen_msc = {b: 0 for b in active_brokers}
last_active_local_time = {b: time.time() for b in active_brokers}

saved_state_raw = r.get(KEY_STATE)
if saved_state_raw:
    try:
        saved_state = json.loads(saved_state_raw)
        lich_su_vao_lenh = saved_state.get("lich_su_vao_lenh", [])
        huong_dang_danh_map = saved_state.get("huong_dang_danh_map", {})
        thoi_diem_vao_lenh_cuoi_map = saved_state.get("thoi_diem_vao_lenh_cuoi_map", {})
        thoi_diem_dong_lenh_cuoi_map = saved_state.get("thoi_diem_dong_lenh_cuoi_map", {})
        orphan_count = saved_state.get("orphan_count", {b: 0 for b in active_brokers})
        broker_cooldown_until = saved_state.get("broker_cooldown_until", {b: 0 for b in active_brokers})
        print(f"🧠 Đã khôi phục Sổ Cái: Gồng {len(lich_su_vao_lenh)} cặp lệnh!")
    except:
        pass

def luu_tri_nho():
    state = {
        "lich_su_vao_lenh": lich_su_vao_lenh,
        "huong_dang_danh_map": huong_dang_danh_map,
        "thoi_diem_vao_lenh_cuoi_map": thoi_diem_vao_lenh_cuoi_map,
        "thoi_diem_dong_lenh_cuoi_map": thoi_diem_dong_lenh_cuoi_map,
        "orphan_count": orphan_count,
        "broker_cooldown_until": broker_cooldown_until
    }
    r.set(KEY_STATE, json.dumps(state))

last_time_update = 0
current_utc_time_str = "00:00"
# dem_so_vong_test = 0

# ==========================================
# VÒNG LẶP QUÉT RADAR SIÊU TỐC
# ==========================================
try:
    while True:
        time.sleep(0.001) 
        now_sec = time.time()
        
        if now_sec - last_time_update >= 1.0:
            current_utc_time_str = datetime.now(timezone.utc).strftime("%H:%M")
            last_time_update = now_sec

            # 👉 Kiểm tra tín hiệu tắt máy từ Redis (1s/lần, 0 tốn hiệu năng)
            if r.get("SIGNAL:SHUTDOWN"):
                print("\n🛑 Đô Đốc nhận lệnh rút quân từ Redis! Đang tắt máy an toàn...")
                luu_tri_nho()
                print("✅ Đã lưu trí nhớ. Tạm biệt!")
                quit()

        cho_phep_vao_lenh = kiem_tra_gio(chien_thuat.get("trading_hours", []), current_utc_time_str)
        gio_cam_bat_buoc_dong = kiem_tra_gio(chien_thuat.get("force_close_hours", []), current_utc_time_str)
        if not chien_thuat.get("force_close_hours", []): gio_cam_bat_buoc_dong = False

        # ----------------------------------------------------
        # 1. THƯỢNG PHƯƠNG BẢO KIẾM (GIỜ GIỚI NGHIÊM)
        # ----------------------------------------------------
        if gio_cam_bat_buoc_dong:
            if len(lich_su_vao_lenh) > 0:
                print(f"\n🛑 [GIỜ GIỚI NGHIÊM] Đã điểm {current_utc_time_str}! XẢ TOÀN BỘ CẶP!")
                pipe = r.pipeline()
                for cap in lich_su_vao_lenh[:]:
                    b_base, b_diff, pair_key = cap['base'], cap['diff'], cap['id_cap']
                    ctx_data = {
                        "pair_token": pair_key, "pair_id": cap['pair_group'],
                        "chenh_vao": cap.get('chenh_lech_vao', 0), "mode_vao": cap.get('tinh_chat_vao', 'UNKNOWN'),
                        "chenh_dong": 0, "mode_dong": "[BLACKOUT_CUT]", "action_type": "BLACKOUT_CLOSE",
                        "huong": cap['huong'], "base": b_base, "diff": b_diff
                    }
                    pipe.lpush(f"QUEUE:ORDER:{b_base.upper()}", json.dumps({"action": "CLOSE_BY_TICKET", "ticket": cap['ticket_b'], "comment": "BLACKOUT", "role": b_base, "context": ctx_data}))
                    pipe.lpush(f"QUEUE:ORDER:{b_diff.upper()}", json.dumps({"action": "CLOSE_BY_TICKET", "ticket": cap['ticket_d'], "comment": "BLACKOUT", "role": b_diff, "context": ctx_data}))
                pipe.execute()
                lich_su_vao_lenh.clear() 
                luu_tri_nho()
            continue

        # ----------------------------------------------------
        # 2. GOM DATA (MGET) & LỌC TICK MA / HEALTH CHECK
        # ----------------------------------------------------
        tick_timeout_sec = quan_tri.get("max_tick_delay_second", 15.0)
        keys_to_get = []
        for broker in active_brokers:
            symbol = symbol_map.get(broker, "").upper()
            keys_to_get.extend([
                f"TICK:{broker}:{symbol}", 
                f"POSITION:{broker}:{symbol}", 
                f"ACCOUNT:{broker}:EQUITY",
                f"HEALTH:{broker}" 
            ])
        raw_data = r.mget(keys_to_get)
        san_data = {}
        
        for i, broker in enumerate(active_brokers):
            idx = i * 4 
            tick_raw, pos_raw, eq_raw, health_raw = raw_data[idx:idx+4]
            
            # Kiểm định Worker
            health_ok = False
            if health_raw:
                try:
                    h_obj = json.loads(health_raw)
                    if h_obj.get("connected") and h_obj.get("trade_allowed") and (time.time() - h_obj.get("update_time", 0) < 5.0):
                        health_ok = True
                except: pass

            # Bóp cổ Tick Ma
            tick_obj = json.loads(tick_raw) if tick_raw else None
            if tick_obj:
                if tick_obj['time_msc'] != last_seen_msc[broker]:
                    last_seen_msc[broker] = tick_obj['time_msc']
                    last_active_local_time[broker] = time.time()
                
                if not health_ok or (time.time() - last_active_local_time[broker] > tick_timeout_sec):
                    tick_obj = None

            so_lenh_dang_mo = 0
            danh_sach_ticket = []
            if pos_raw:
                try:
                    pos_list = json.loads(pos_raw)
                    if isinstance(pos_list, list):
                        so_lenh_dang_mo = len(pos_list)
                        danh_sach_ticket = pos_list
                except: pass
                
            san_data[broker] = {
                "tick": tick_obj, 
                "so_lenh_dang_mo": so_lenh_dang_mo, 
                "danh_sach_ticket": danh_sach_ticket, 
                "equity": float(eq_raw) if eq_raw else 999999.0,
                "speed_60s": tick_obj.get("speed_60s", 0) if tick_obj else 0
            }

        # ----------------------------------------------------
        # 3. ÔNG TƠ BÀ NGUYỆT (GHÉP CẶP TICKET - BỐC VÉ MỚI NHẤT) 
        # ----------------------------------------------------
        paired_tickets = {broker: set() for broker in active_brokers}
        for cap in lich_su_vao_lenh:
            paired_tickets[cap['base']].add(cap['ticket_b'])
            paired_tickets[cap['diff']].add(cap['ticket_d'])

        chuyen_xe_con_lai = []
        for chuyen in chuyen_xe_dang_cho:
            b_base, b_diff = chuyen["base"], chuyen["diff"]
            unpaired_base = [p for p in san_data[b_base]["danh_sach_ticket"] if p['ticket'] not in paired_tickets[b_base]]
            unpaired_diff = [p for p in san_data[b_diff]["danh_sach_ticket"] if p['ticket'] not in paired_tickets[b_diff]]
            
            if len(unpaired_base) > 0 and len(unpaired_diff) > 0:
                # 👉 VŨ KHÍ TỐI THƯỢNG: Sắp xếp Ticket giảm dần. Vé mới nhất luôn nằm ở Index 0!
                unpaired_base.sort(key=lambda x: x['ticket'], reverse=True)
                unpaired_diff.sort(key=lambda x: x['ticket'], reverse=True)
                
                # Bốc ngay 2 vé mới nhất để ghép cặp cho Chuyến xe này
                t_base, t_diff = unpaired_base[0], unpaired_diff[0]
                
                lich_su_vao_lenh.append({
                    "id_cap": f"PAIR_{t_base['ticket']}_{t_diff['ticket']}", "pair_group": chuyen["pair_group"],
                    "base": b_base, "ticket_b": t_base['ticket'], "diff": b_diff, "ticket_d": t_diff['ticket'],
                    "huong": chuyen["huong"], "time_match": time.time(), # Dùng giờ Local để tính Hold Time
                    "chenh_lech_vao": chuyen["chenh_vao"], "tinh_chat_vao": chuyen["mode_vao"]
                })
                paired_tickets[b_base].add(t_base['ticket'])
                paired_tickets[b_diff].add(t_diff['ticket'])
                orphan_count[b_base] = 0
                orphan_count[b_diff] = 0
                luu_tri_nho()
            else:
                if time.time() - chuyen["time_fired"] < 10.0:
                    chuyen_xe_con_lai.append(chuyen)
        chuyen_xe_dang_cho = chuyen_xe_con_lai

        # ----------------------------------------------------
        # 4. BAO THANH THIÊN (XỬ TRẢM STOPOUT)
        # ----------------------------------------------------
        cac_cap_con_song = []
        pipe_tram = r.pipeline()
        has_tram = False
        
        for cap in lich_su_vao_lenh:
            b_base, b_diff = cap['base'], cap['diff']
            live_tickets_base = [p['ticket'] for p in san_data[b_base]["danh_sach_ticket"]]
            live_tickets_diff = [p['ticket'] for p in san_data[b_diff]["danh_sach_ticket"]]
            
            base_alive = cap['ticket_b'] in live_tickets_base
            diff_alive = cap['ticket_d'] in live_tickets_diff
            
            ctx_data = {
                "pair_token": cap['id_cap'], "pair_id": cap['pair_group'],
                "chenh_vao": cap.get('chenh_lech_vao', 0), "mode_vao": cap.get('tinh_chat_vao', 'UNKNOWN'),
                "chenh_dong": 0, "mode_dong": "[STOPOUT]", "action_type": "FORCE_CLOSE",
                "huong": cap['huong'], "base": b_base, "diff": b_diff
            }

            if base_alive and diff_alive:
                cac_cap_con_song.append(cap)
            elif base_alive and not diff_alive:
                pipe_tram.lpush(f"QUEUE:ORDER:{b_base.upper()}", json.dumps({"action": "CLOSE_BY_TICKET", "ticket": cap['ticket_b'], "role": b_base, "context": ctx_data}))
                pipe_tram.lpush(f"QUEUE:ORDER:{b_diff.upper()}", json.dumps({"action": "FETCH_HISTORY_ONLY", "ticket": cap['ticket_d'], "role": b_diff, "context": ctx_data}))
                has_tram = True
            elif not base_alive and diff_alive:
                pipe_tram.lpush(f"QUEUE:ORDER:{b_diff.upper()}", json.dumps({"action": "CLOSE_BY_TICKET", "ticket": cap['ticket_d'], "role": b_diff, "context": ctx_data}))
                pipe_tram.lpush(f"QUEUE:ORDER:{b_base.upper()}", json.dumps({"action": "FETCH_HISTORY_ONLY", "ticket": cap['ticket_b'], "role": b_base, "context": ctx_data}))
                has_tram = True
                
        if has_tram:
            pipe_tram.execute()
                
        if len(lich_su_vao_lenh) != len(cac_cap_con_song):
            lich_su_vao_lenh = cac_cap_con_song
            luu_tri_nho()

        # ----------------------------------------------------
        # 5. ĐỘI VỆ SINH MỒ CÔI (MISS IN/OUT VÀ CẦU DAO)
        # ----------------------------------------------------
        for broker in active_brokers:
            for ticket_info in san_data[broker]["danh_sach_ticket"]:
                t_id = ticket_info["ticket"]
                
                # Nếu phát hiện Ticket chưa được ghép cặp (Lệch chân)
                if t_id not in paired_tickets[broker]:
                    # Ghi nhận thời điểm Đô Đốc lần đầu nhìn thấy cái vé này bằng giờ Local
                    if t_id not in thoi_diem_phat_hien_ve_le:
                        thoi_diem_phat_hien_ve_le[t_id] = time.time()
                    
                    # Tính thời gian lệnh này bị bơ vơ
                    tuoi_ve_le = time.time() - thoi_diem_phat_hien_ve_le[t_id]
                    
                    # Nếu bơ vơ quá 5 giây -> VÁC ĐAO RA CHÉM!
                    if tuoi_ve_le > 5.0:
                        ctx_data = {
                            "pair_token": f"ORPHAN_{t_id}", "pair_id": f"ERR_{broker}",
                            "mode_dong": "[ORPHAN]", "action_type": "FORCE_CLOSE", "is_single_cut": True
                        }
                        r.lpush(f"QUEUE:ORDER:{broker.upper()}", json.dumps({"action": "CLOSE_BY_TICKET", "ticket": t_id, "role": broker, "context": ctx_data}))
                        print(f"\n☠️ [TRẢM] Lệnh mồ côi {t_id} của {broker} đã bị kẹt {tuoi_ve_le:.1f}s! Ép đóng ngay lập tức!")
                        
                        # Tạm đưa vào danh sách có cặp để không bị lặp lệnh spam gửi đi
                        paired_tickets[broker].add(t_id) 
                        
                        orphan_count[broker] += 1
                        if orphan_count[broker] >= chien_thuat.get("max_orphan_count", 3):
                            broker_cooldown_until[broker] = time.time() + chien_thuat.get("orphan_cooldown_second", 1800)
                            orphan_count[broker] = 0 
                            luu_tri_nho()
                else:
                    # Nếu ticket đã có cặp, xóa khỏi sổ theo dõi cho nhẹ não
                    if t_id in thoi_diem_phat_hien_ve_le:
                        del thoi_diem_phat_hien_ve_le[t_id]

        for pair_group in list(huong_dang_danh_map.keys()):
            if sum(1 for cap in lich_su_vao_lenh if cap['pair_group'] == pair_group) == 0:
                huong_dang_danh_map[pair_group] = None

        # ----------------------------------------------------
        # 6. QUÉT TÍN HIỆU ĐÓNG LỆNH (CHỐT LỜI / CẮT LỖ) 
        # ----------------------------------------------------
        danh_sach_chua_chot = []
        for cap in lich_su_vao_lenh:
            b_base, b_diff, pair_key, pair_group = cap['base'], cap['diff'], cap['id_cap'], cap['pair_group']
            
            # Throttle Van tiết lưu: Chống nhồi lệnh đóng liên tục
            if (time.time() - thoi_diem_dong_lenh_cuoi_map.get(pair_group, 0)) < chien_thuat.get("cooldown_close_second", 3):
                danh_sach_chua_chot.append(cap); continue

            # Hold time tối thiểu
            if (time.time() - cap['time_match']) < chien_thuat.get('hold_time', 180):
                danh_sach_chua_chot.append(cap); continue

            tick_base, tick_diff = san_data[b_base]["tick"], san_data[b_diff]["tick"]
            if not tick_base or not tick_diff: 
                danh_sach_chua_chot.append(cap); continue
            
            # Đồng bộ Local Time
            thoi_diem_nhan_tick_cuoi[pair_group] = max(last_active_local_time[b_base], last_active_local_time[b_diff])
            tin_hieu = check_tin_hieu_arbitrage(tick_base, tick_diff, chien_thuat, huong_dang_danh=cap['huong'])
            
            if tin_hieu["hanh_dong"] == "DONG_LENH":
                if dong_ho_dong.get(pair_group, 0) == 0: 
                    dong_ho_dong[pair_group] = time.time()
                    # print(f"\n🎯 [CHUẨN BỊ CHỐT LỜI] {pair_group} | Độ lệch co về: {tin_hieu['chenh_lech']:.2f}. Bắt đầu ngâm...")
                
                dong_ho_vao[pair_group] = 0 
                
                # PHÂN LUỒNG LOGIC FREEZE VÀ CONTINUOUS (FIXED)
                stable_sec = chien_thuat['stable_time'] / 1000.0
                is_continuous = (chien_thuat.get('stable_mode', 'freeze').lower() == 'continuous')
                
                if is_continuous:
                    # Logic Ngâm liên tục: Trừ đi đồng hồ ĐÓNG
                    tg_ngam_dong = time.time() - dong_ho_dong[pair_group]
                else:
                    # Logic Đóng băng tuyệt đối: Trừ đi Tick CUỐI CÙNG
                    tg_ngam_dong = time.time() - thoi_diem_nhan_tick_cuoi[pair_group]
                
                
                if tg_ngam_dong >= stable_sec:
                    print(f"\n⚡ [BÓP CÒ ĐÓNG LỆNH] {pair_group} | Đã ngâm đủ {tg_ngam_dong:.3f}s / {stable_sec}s! Ném lệnh vào lò!")
                    ctx_data = {
                        "pair_token": pair_key, "pair_id": pair_group,
                        "chenh_vao": cap.get('chenh_lech_vao', 0), "mode_vao": cap.get('tinh_chat_vao', 'UNKNOWN'),
                        "chenh_dong": tin_hieu['chenh_lech'], "mode_dong": f"[{chien_thuat.get('stable_mode', 'freeze')[0].upper()}]", "action_type": "CLOSE",
                        "huong": cap['huong'], "base": b_base, "diff": b_diff,
                        "speed_base_close": san_data[b_base]["speed_60s"],
                        "speed_diff_close": san_data[b_diff]["speed_60s"]
                    }
                    pipe_close = r.pipeline()
                    pipe_close.lpush(f"QUEUE:ORDER:{b_base.upper()}", json.dumps({"action": "CLOSE_BY_TICKET", "ticket": cap['ticket_b'], "role": b_base, "context": ctx_data}))
                    pipe_close.lpush(f"QUEUE:ORDER:{b_diff.upper()}", json.dumps({"action": "CLOSE_BY_TICKET", "ticket": cap['ticket_d'], "role": b_diff, "context": ctx_data}))
                    pipe_close.execute()
                    
                    dong_ho_dong[pair_group] = 0
                    thoi_diem_dong_lenh_cuoi_map[pair_group] = time.time() 
                else: 
                    danh_sach_chua_chot.append(cap)
                    # print(f"\r⏳ [ĐANG NGÂM ĐÓNG] {pair_group} | Tg chờ: {tg_ngam_dong:.3f}s / {stable_sec}s   ", end="", flush=True)
            else:
                if dong_ho_dong.get(pair_group, 0) != 0:
                    # print(f"\n❌ [HỦY CHỐT LỜI] {pair_group} | Quay xe < {chien_thuat['deviation_close']}, tiếp tục gồng!")
                    dong_ho_dong[pair_group] = 0
                danh_sach_chua_chot.append(cap)
        
        if len(lich_su_vao_lenh) != len(danh_sach_chua_chot):
            lich_su_vao_lenh = danh_sach_chua_chot
            luu_tri_nho()

        # ----------------------------------------------------
        # 7. QUÉT TÍN HIỆU VÀO LỆNH (MA TRẬN)
        # ----------------------------------------------------
        # 👉 XÂY DỰNG KHÓA HƯỚNG TOÀN CỤC (GLOBAL DIRECTION LOCK)
        broker_direction_lock = {}
        for cap in lich_su_vao_lenh:
            b, d = cap['base'], cap['diff']
            if cap['huong'] == "TH1":
                # TH1: Sell Base, Buy Diff
                broker_direction_lock[b] = "SELL"
                broker_direction_lock[d] = "BUY"
            elif cap['huong'] == "TH2":
                # TH2: Buy Base, Sell Diff
                broker_direction_lock[b] = "BUY"
                broker_direction_lock[d] = "SELL"

        tin_hieu_kha_thi = []
        if cho_phep_vao_lenh:
            for b_base, b_diff in danh_sach_cap_cheo:
                pair_group = f"{b_base}_{b_diff}"
                
                if time.time() < broker_cooldown_until[b_base] or time.time() < broker_cooldown_until[b_diff]: continue
                if (time.time() - thoi_diem_vao_lenh_cuoi_map.get(pair_group, 0)) < chien_thuat.get("cooldown_second", 60): continue

                tick_base, tick_diff = san_data[b_base]["tick"], san_data[b_diff]["tick"]
                if not tick_base or not tick_diff: continue
                
                thoi_diem_nhan_tick_cuoi[pair_group] = max(last_active_local_time[b_base], last_active_local_time[b_diff])
                huong_hien_tai = huong_dang_danh_map.get(pair_group)
                tin_hieu = check_tin_hieu_arbitrage(tick_base, tick_diff, chien_thuat, huong_dang_danh=huong_hien_tai)
                
                if tin_hieu["hanh_dong"] == "VAO_LENH":
                    # 👉 KIỂM TRA XUNG ĐỘT HƯỚNG TOÀN CỤC CHÉO SÀN
                    lenh_b_du_kien, lenh_d_du_kien = tin_hieu["lenh_base"], tin_hieu["lenh_diff"]
                    xung_dot = False
                    
                    if broker_direction_lock.get(b_base) and broker_direction_lock.get(b_base) != lenh_b_du_kien:
                        # Tắt print để đỡ rác log, nếu đại ca muốn xem thì bỏ dấu thăng (#) ra
                        # print(f"\n🚫 [CẤM CHÉO] {b_base} đang gồng {broker_direction_lock[b_base]}, cấm đánh {lenh_b_du_kien} ({pair_group})")
                        xung_dot = True
                    if broker_direction_lock.get(b_diff) and broker_direction_lock.get(b_diff) != lenh_d_du_kien:
                        # print(f"\n🚫 [CẤM CHÉO] {b_diff} đang gồng {broker_direction_lock[b_diff]}, cấm đánh {lenh_d_du_kien} ({pair_group})")
                        xung_dot = True
                        
                    if xung_dot:
                        dong_ho_vao[pair_group] = 0
                        continue

                    if huong_hien_tai is not None and huong_hien_tai != tin_hieu["loai_lenh"]: continue 

                    if dong_ho_vao.get(pair_group, 0) == 0: 
                        dong_ho_vao[pair_group] = time.time()
                        # print(f"\n🎯 [PHÁT HIỆN] {pair_group} lệch {tin_hieu['chenh_lech']:.2f}. Bắt đầu ngâm VÀO LỆNH...")

                    dong_ho_dong[pair_group] = 0
                    # PHÂN LUỒNG LOGIC FREEZE VÀ CONTINUOUS
                    stable_sec = chien_thuat['stable_time'] / 1000.0
                    is_continuous = (chien_thuat.get('stable_mode', 'freeze').lower() == 'continuous')
                    
                    if is_continuous:
                        # Logic Ngâm liên tục (Bao dung)
                        tg_ngam = time.time() - dong_ho_vao[pair_group]
                    else:
                        # Logic Đóng băng tuyệt đối (Khắc nghiệt)
                        # Tính từ lúc nhận được cái Tick CUỐI CÙNG làm thay đổi giá
                        tg_ngam = time.time() - thoi_diem_nhan_tick_cuoi[pair_group]
                    
                    if tg_ngam >= stable_sec:
                        tin_hieu_kha_thi.append({
                            "pair_group": pair_group, "broker_base": b_base, "broker_diff": b_diff,
                            "chi_tiet": tin_hieu, "chenh_lech": tin_hieu["chenh_lech"], "mode_vao": f"[{chien_thuat.get('stable_mode', 'freeze')[0].upper()}]"
                        })
                    else:
                        # print(f"\r⏳ [ĐANG NGÂM VÀO] {pair_group} | Tg ngâm: {tg_ngam:.3f}s / {stable_sec}s   ", end="", flush=True)
                        pass
                else:
                    dong_ho_vao[pair_group] = 0; dong_ho_dong[pair_group] = 0

        # ----------------------------------------------------
        # 8. RANK & SPRAY (XẾP HẠNG & SẤY ĐẠN)
        # ----------------------------------------------------
        if tin_hieu_kha_thi:
            tin_hieu_kha_thi.sort(key=lambda x: x["chenh_lech"], reverse=True)
            so_cap_da_ban = 0
            for th in tin_hieu_kha_thi:
                b_base, b_diff, pair_group = th["broker_base"], th["broker_diff"], th["pair_group"]
                
                alert_eq = chien_thuat.get("alert_equity", 0)
                if san_data[b_base]["equity"] < alert_eq or san_data[b_diff]["equity"] < alert_eq: continue 
                if san_data[b_base]["so_lenh_dang_mo"] >= quan_tri["max_orders_per_broker"]: continue 
                if san_data[b_diff]["so_lenh_dang_mo"] >= quan_tri["max_orders_per_broker"]: continue 
                
                lenh_base, lenh_diff = th["chi_tiet"]["lenh_base"], th["chi_tiet"]["lenh_diff"]
                vol_base, vol_diff = vol_map[b_base], vol_map[b_diff]
                
               # Phải bơm đủ thông tin để Kế Toán còn biết đường ghép cặp OPEN
                ctx_vao = {
                    "pair_token": f"OPEN_{pair_group}_{time.time()}", # Cấp cho nó 1 cái ID độc nhất
                    "pair_id": pair_group,
                    "action_type": "OPEN",
                    "chenh_vao": th["chenh_lech"],
                    "mode_vao": th["mode_vao"],
                    "huong": th["chi_tiet"]["loai_lenh"],
                    "base": b_base,
                    "diff": b_diff,
                    "speed_base_entry": san_data[b_base]["speed_60s"],
                    "speed_diff_entry": san_data[b_diff]["speed_60s"]
                }
                
                pipe_open = r.pipeline()
                pipe_open.lpush(f"QUEUE:ORDER:{b_base.upper()}", json.dumps({"action": lenh_base, "volume": vol_base, "context": ctx_vao}))
                pipe_open.lpush(f"QUEUE:ORDER:{b_diff.upper()}", json.dumps({"action": lenh_diff, "volume": vol_diff, "context": ctx_vao}))
                pipe_open.execute()
                print(f"\n⚡ BÓP CÒ: {b_base} ({lenh_base}) <-> {b_diff} ({lenh_diff}) {th['mode_vao']} | Lệch: {th['chenh_lech']:.2f}")
                
                san_data[b_base]["so_lenh_dang_mo"] += 1
                san_data[b_diff]["so_lenh_dang_mo"] += 1
                
                chuyen_xe_dang_cho.append({
                    "pair_group": pair_group, "base": b_base, "diff": b_diff,
                    "huong": th["chi_tiet"]["loai_lenh"], "time_fired": time.time(),
                    "chenh_vao": th["chenh_lech"], "mode_vao": th["mode_vao"]
                })
                
                huong_dang_danh_map[pair_group] = th["chi_tiet"]["loai_lenh"]
                thoi_diem_vao_lenh_cuoi_map[pair_group] = time.time()
                
                # Trả lại đồng hồ ngâm vào lệnh
                dong_ho_vao[pair_group] = 0
                luu_tri_nho()
                
                so_cap_da_ban += 1
                if so_cap_da_ban >= quan_tri["max_concurrent_pairs"]: break


        # Dọn rác dict theo dõi vé lẻ
        all_live_tickets = set()
        for broker in active_brokers:
            for t in san_data[broker]["danh_sach_ticket"]:
                all_live_tickets.add(t["ticket"])
        thoi_diem_phat_hien_ve_le = {k: v for k, v in thoi_diem_phat_hien_ve_le.items() if k in all_live_tickets}
except KeyboardInterrupt:
    print("\n🛑 Đô Đốc đã hạ lệnh rút quân!")
    luu_tri_nho()
    print("✅ Đã lưu trí nhớ. Tạm biệt!")