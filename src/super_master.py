import os
import redis
import ujson as json
import time
import itertools
from datetime import datetime, timezone
import ctypes

from utils.trading_logic import check_tin_hieu_arbitrage 
from utils.terminal import dan_tran_cua_so

os.system("title 🧠 ĐÔ ĐỐC TỔNG TƯ LỆNH - MATRIX SANDBOX")
try:
    ctypes.windll.kernel32.SetConsoleTitleW("🧠 ĐÔ ĐỐC MATRIX SANDBOX")
except:
    pass
dan_tran_cua_so(4)

print("🚀 ĐANG KHỞI ĐỘNG MATRIX SANDBOX (CHẾ ĐỘ MÔ PHỎNG)...")

with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

redis_conf = config['redis']
r = redis.Redis(host=redis_conf['host'], port=redis_conf['port'], db=redis_conf['db'], decode_responses=True)

matrix_cfg = config['super_matrix']
active_brokers = matrix_cfg['active_brokers']
symbol_map = matrix_cfg['symbol_mapping']
chien_thuat = matrix_cfg['chien_thuat']
quan_tri = matrix_cfg['quan_tri_rui_ro']

# Thông số mô phỏng
sim_cfg = config.get('simulation', {})
sim_lot = sim_cfg.get('lot_size', 0.01)

# Commission per lot cho từng sàn (USD/lot, 1 chiều)
commission_map = {}
for broker_name, broker_cfg in config.get('brokers', {}).items():
    commission_map[broker_name] = broker_cfg.get('commission_per_lot', 0.0)

print("=" * 60)
print("🎯 THÔNG SỐ CHIẾN LƯỢC SANDBOX ĐÃ NẠP:")
print(f"  ┣ 📈 Chế độ ngâm: FREEZE | Đóng băng: {chien_thuat.get('stable_time')}ms")
print(f"  ┣ 🎯 Lệch VÀO: {chien_thuat.get('deviation_entry')} | Lệch CHỐT: {chien_thuat.get('deviation_close')}")
print(f"  ┣ ⏳ Hold Time tối thiểu: {chien_thuat.get('hold_time')}s")
print(f"  ┣ ⏱️ Cooldown Mở: {chien_thuat.get('cooldown_second')}s | Cooldown Đóng: {chien_thuat.get('cooldown_close_second')}s")
print(f"  ┣ 👻 Diệt Tick Ma (Feed Timeout): Quá {quan_tri.get('max_tick_delay_second', 15.0)}s")
print(f"  ┣ 💰 Lot mô phỏng: {sim_lot} | Balance: {sim_cfg.get('initial_balance', 10000.0)}$")
print(f"  ┣ 💸 Commission: {commission_map}")
print(f"  ┗ ⚔️ Tối đa {quan_tri.get('max_concurrent_pairs')} Cặp song song | {quan_tri.get('max_orders_per_pair')} Lệnh/Cặp")
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
# TÍNH PROFIT MÔ PHỎNG
# ==========================================
def tinh_profit_mo_phong(open_price, close_price, volume, huong_lenh):
    """
    Tính profit dựa trên giá mở/đóng.
    huong_lenh: "BUY" hoặc "SELL"
    Gold: 1 lot = 100 oz, profit = (close - open) * 100 * volume
    """
    contract_size = 100  # Gold standard contract
    if huong_lenh == "BUY":
        profit = (close_price - open_price) * contract_size * volume
    else:  # SELL
        profit = (open_price - close_price) * contract_size * volume
    return round(profit, 2)

# ==========================================
# TRÍ NHỚ VÀ KHÔI PHỤC TRẠNG THÁI 
# ==========================================
KEY_STATE = "STATE:SUPER_MASTER"

thoi_diem_nhan_tick_cuoi = {} 

lich_su_vao_lenh = []       
huong_dang_danh_map = {}        
thoi_diem_vao_lenh_cuoi_map = {} 
thoi_diem_dong_lenh_cuoi_map = {}

# Đồng hồ ghi nhớ sự sống của Tick Giá để diệt Tick Ma
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
        print(f"🧠 Đã khôi phục Sổ Cái: Gồng {len(lich_su_vao_lenh)} cặp lệnh mô phỏng!")
    except:
        pass

def luu_tri_nho():
    state = {
        "lich_su_vao_lenh": lich_su_vao_lenh,
        "huong_dang_danh_map": huong_dang_danh_map,
        "thoi_diem_vao_lenh_cuoi_map": thoi_diem_vao_lenh_cuoi_map,
        "thoi_diem_dong_lenh_cuoi_map": thoi_diem_dong_lenh_cuoi_map,
    }
    r.set(KEY_STATE, json.dumps(state))

# Bộ đếm mô phỏng tạo Pair ID
sim_pair_counter = int(time.time() * 1000) % 1000000

last_time_update = 0
current_utc_time_str = "00:00"

# ==========================================
# HÀM ĐẾM LỆNH MÔ PHỎNG ĐANG MỞ THEO CẶP
# ==========================================
def dem_lenh_theo_cap(pair_group):
    count = 0
    for cap in lich_su_vao_lenh:
        if cap['pair_group'] == pair_group:
            count += 1
    return count

# ==========================================
# VÒNG LẶP QUÉT RADAR SANDBOX
# ==========================================
try:
    while True:
        time.sleep(0.001) 
        now_sec = time.time()
        
        if now_sec - last_time_update >= 1.0:
            current_utc_time_str = datetime.now(timezone.utc).strftime("%H:%M")
            last_time_update = now_sec

            # Kiểm tra tín hiệu tắt máy từ Redis
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
                print(f"\n🛑 [GIỜ GIỚI NGHIÊM] Đã điểm {current_utc_time_str}! XẢ TOÀN BỘ CẶP MÔ PHỎNG!")
                
                # Gom tất cả tick 1 lần duy nhất
                brokers_can_tick = list({b for cap in lich_su_vao_lenh for b in (cap['base'], cap['diff'])})
                tick_keys = [f"TICK:{b}:{symbol_map.get(b, '').upper()}" for b in brokers_can_tick]
                tick_raws = r.mget(tick_keys)
                tick_cache = {}
                for i, b in enumerate(brokers_can_tick):
                    tick_cache[b] = json.loads(tick_raws[i]) if tick_raws[i] else None
                
                for cap in lich_su_vao_lenh:
                    b_base, b_diff = cap['base'], cap['diff']
                    pair_group = cap['pair_group']
                    
                    tick_base = tick_cache.get(b_base)
                    tick_diff = tick_cache.get(b_diff)
                    
                    if not tick_base or not tick_diff:
                        continue
                    
                    # Tính giá đóng theo hướng
                    if cap['huong'] == "TH1":
                        # TH1: Đang SELL Base, BUY Diff → Đóng: MUA Base (ask), BÁN Diff (bid)
                        close_price_base = tick_base['ask']
                        close_price_diff = tick_diff['bid']
                    else:
                        # TH2: Đang BUY Base, SELL Diff → Đóng: BÁN Base (bid), MUA Diff (ask)
                        close_price_base = tick_base['bid']
                        close_price_diff = tick_diff['ask']
                    
                    lenh_base = "SELL" if cap['huong'] == "TH1" else "BUY"
                    lenh_diff = "BUY" if cap['huong'] == "TH1" else "SELL"
                    
                    profit_base = tinh_profit_mo_phong(cap['open_price_base'], close_price_base, sim_lot, lenh_base)
                    profit_diff = tinh_profit_mo_phong(cap['open_price_diff'], close_price_diff, sim_lot, lenh_diff)
                    
                    fee_base = sim_lot * commission_map.get(b_base, 0)
                    fee_diff = sim_lot * commission_map.get(b_diff, 0)
                    
                    bien_lai = {
                        "pair_token": cap['id_cap'],
                        "pair_id": pair_group,
                        "action_type": "BLACKOUT_CLOSE",
                        "huong": cap['huong'],
                        "base": b_base,
                        "diff": b_diff,
                        "volume": sim_lot,
                        "chenh_vao": cap.get('chenh_lech_vao', 0),
                        "chenh_dong": 0,
                        "open_price_base": cap['open_price_base'],
                        "close_price_base": close_price_base,
                        "open_price_diff": cap['open_price_diff'],
                        "close_price_diff": close_price_diff,
                        "profit_base": profit_base,
                        "profit_diff": profit_diff,
                        "fee_base": round(fee_base, 2),
                        "fee_diff": round(fee_diff, 2),
                        "speed_base_entry": cap.get('speed_base_entry', 0),
                        "speed_diff_entry": cap.get('speed_diff_entry', 0),
                        "speed_base_close": 0,
                        "speed_diff_close": 0,
                    }
                    r.lpush("QUEUE:ACCOUNTANT", json.dumps(bien_lai))
                
                lich_su_vao_lenh.clear()
                huong_dang_danh_map.clear()
                luu_tri_nho()
            continue

        # ----------------------------------------------------
        # 2. GOM DATA TICK & HEALTH CHECK
        # ----------------------------------------------------
        tick_timeout_sec = quan_tri.get("max_tick_delay_second", 15.0)
        keys_to_get = []
        for broker in active_brokers:
            symbol = symbol_map.get(broker, "").upper()
            keys_to_get.extend([
                f"TICK:{broker}:{symbol}", 
                f"HEALTH:{broker}" 
            ])
        raw_data = r.mget(keys_to_get)
        san_data = {}
        
        for i, broker in enumerate(active_brokers):
            idx = i * 2 
            tick_raw, health_raw = raw_data[idx:idx+2]
            
            # Kiểm định Worker
            health_ok = False
            if health_raw:
                try:
                    h_obj = json.loads(health_raw)
                    if h_obj.get("connected") and (time.time() - h_obj.get("update_time", 0) < 5.0):
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
                
            san_data[broker] = {
                "tick": tick_obj, 
                "speed_60s": tick_obj.get("speed_60s", 0) if tick_obj else 0
            }

        # ----------------------------------------------------
        # 3. QUÉT TÍN HIỆU ĐÓNG LỆNH MÔ PHỎNG
        # ----------------------------------------------------
        danh_sach_chua_chot = []
        for cap in lich_su_vao_lenh:
            b_base, b_diff, pair_key, pair_group = cap['base'], cap['diff'], cap['id_cap'], cap['pair_group']
            
            # Throttle Van tiết lưu
            if (time.time() - thoi_diem_dong_lenh_cuoi_map.get(pair_group, 0)) < chien_thuat.get("cooldown_close_second", 3):
                danh_sach_chua_chot.append(cap); continue

            # Hold time tối thiểu
            if (time.time() - cap['time_match']) < chien_thuat.get('hold_time', 180):
                danh_sach_chua_chot.append(cap); continue

            tick_base, tick_diff = san_data[b_base]["tick"], san_data[b_diff]["tick"]
            if not tick_base or not tick_diff: 
                danh_sach_chua_chot.append(cap); continue
            
            # Đồng bộ Local Time (FREEZE mode: tính từ tick cuối cùng)
            thoi_diem_nhan_tick_cuoi[pair_group] = max(last_active_local_time[b_base], last_active_local_time[b_diff])
            tin_hieu = check_tin_hieu_arbitrage(tick_base, tick_diff, chien_thuat, huong_dang_danh=cap['huong'])
            
            if tin_hieu["hanh_dong"] == "DONG_LENH":
                # FREEZE mode ONLY: Tính từ tick cuối cùng
                stable_sec = chien_thuat['stable_time'] / 1000.0
                tg_ngam_dong = time.time() - thoi_diem_nhan_tick_cuoi[pair_group]
                
                if tg_ngam_dong >= stable_sec:
                    # Tính giá đóng theo hướng
                    if cap['huong'] == "TH1":
                        close_price_base = tick_base['ask']
                        close_price_diff = tick_diff['bid']
                    else:
                        close_price_base = tick_base['bid']
                        close_price_diff = tick_diff['ask']
                    
                    lenh_base = "SELL" if cap['huong'] == "TH1" else "BUY"
                    lenh_diff = "BUY" if cap['huong'] == "TH1" else "SELL"
                    
                    profit_base = tinh_profit_mo_phong(cap['open_price_base'], close_price_base, sim_lot, lenh_base)
                    profit_diff = tinh_profit_mo_phong(cap['open_price_diff'], close_price_diff, sim_lot, lenh_diff)
                    
                    fee_base = round(sim_lot * commission_map.get(b_base, 0), 2)
                    fee_diff = round(sim_lot * commission_map.get(b_diff, 0), 2)
                    
                    net_profit = profit_base + profit_diff - fee_base - fee_diff
                    
                    print(f"\n⚡ [ĐÓNG LỆNH MÔ PHỎNG] {pair_group} | Ngâm {tg_ngam_dong:.3f}s | Net: {net_profit:.2f}$")
                    
                    bien_lai = {
                        "pair_token": pair_key,
                        "pair_id": pair_group,
                        "action_type": "CLOSE",
                        "huong": cap['huong'],
                        "base": b_base,
                        "diff": b_diff,
                        "volume": sim_lot,
                        "chenh_vao": cap.get('chenh_lech_vao', 0),
                        "chenh_dong": tin_hieu['chenh_lech'],
                        "open_price_base": cap['open_price_base'],
                        "close_price_base": close_price_base,
                        "open_price_diff": cap['open_price_diff'],
                        "close_price_diff": close_price_diff,
                        "profit_base": profit_base,
                        "profit_diff": profit_diff,
                        "fee_base": fee_base,
                        "fee_diff": fee_diff,
                        "speed_base_entry": cap.get('speed_base_entry', 0),
                        "speed_diff_entry": cap.get('speed_diff_entry', 0),
                        "speed_base_close": san_data[b_base]["speed_60s"],
                        "speed_diff_close": san_data[b_diff]["speed_60s"],
                    }
                    r.lpush("QUEUE:ACCOUNTANT", json.dumps(bien_lai))
                    
                    thoi_diem_dong_lenh_cuoi_map[pair_group] = time.time() 
                else: 
                    danh_sach_chua_chot.append(cap)
            else:
                danh_sach_chua_chot.append(cap)
        
        if len(lich_su_vao_lenh) != len(danh_sach_chua_chot):
            lich_su_vao_lenh = danh_sach_chua_chot
            # Dọn hướng đã trống
            for pg in list(huong_dang_danh_map.keys()):
                if sum(1 for c in lich_su_vao_lenh if c['pair_group'] == pg) == 0:
                    huong_dang_danh_map[pg] = None
            luu_tri_nho()

        # ----------------------------------------------------
        # 4. QUÉT TÍN HIỆU VÀO LỆNH MÔ PHỎNG
        # ----------------------------------------------------
        tin_hieu_kha_thi = []
        if cho_phep_vao_lenh:
            for b_base, b_diff in danh_sach_cap_cheo:
                pair_group = f"{b_base}_{b_diff}"
                
                if (time.time() - thoi_diem_vao_lenh_cuoi_map.get(pair_group, 0)) < chien_thuat.get("cooldown_second", 60): continue

                tick_base, tick_diff = san_data[b_base]["tick"], san_data[b_diff]["tick"]
                if not tick_base or not tick_diff: continue
                
                thoi_diem_nhan_tick_cuoi[pair_group] = max(last_active_local_time[b_base], last_active_local_time[b_diff])
                
                # KHÓA HƯỚNG PER-PAIR: Chỉ check hướng của pair_group này
                huong_hien_tai = huong_dang_danh_map.get(pair_group)
                tin_hieu = check_tin_hieu_arbitrage(tick_base, tick_diff, chien_thuat, huong_dang_danh=huong_hien_tai)
                
                if tin_hieu["hanh_dong"] == "VAO_LENH":
                    if huong_hien_tai is not None and huong_hien_tai != tin_hieu["loai_lenh"]: continue 
                    
                    # FREEZE mode ONLY
                    stable_sec = chien_thuat['stable_time'] / 1000.0
                    tg_ngam = time.time() - thoi_diem_nhan_tick_cuoi[pair_group]
                    
                    if tg_ngam >= stable_sec:
                        tin_hieu_kha_thi.append({
                            "pair_group": pair_group, "broker_base": b_base, "broker_diff": b_diff,
                            "chi_tiet": tin_hieu, "chenh_lech": tin_hieu["chenh_lech"]
                        })

        # ----------------------------------------------------
        # 5. RANK & CHỌN TOP SPREAD ĐỂ FILL
        # ----------------------------------------------------
        if tin_hieu_kha_thi:
            tin_hieu_kha_thi.sort(key=lambda x: x["chenh_lech"], reverse=True)
            so_cap_da_ban = 0
            for th in tin_hieu_kha_thi:
                b_base, b_diff, pair_group = th["broker_base"], th["broker_diff"], th["pair_group"]
                
                # Kiểm tra max lệnh mô phỏng per-pair
                if dem_lenh_theo_cap(pair_group) >= quan_tri["max_orders_per_pair"]: continue 
                
                tick_base, tick_diff = san_data[b_base]["tick"], san_data[b_diff]["tick"]
                lenh_base, lenh_diff = th["chi_tiet"]["lenh_base"], th["chi_tiet"]["lenh_diff"]
                
                # Fill mô phỏng tại giá tick hiện tại
                if lenh_base == "SELL":
                    fill_price_base = tick_base['bid']
                else:
                    fill_price_base = tick_base['ask']
                    
                if lenh_diff == "SELL":
                    fill_price_diff = tick_diff['bid']
                else:
                    fill_price_diff = tick_diff['ask']
                
                # Tạo Pair ID
                sim_pair_counter += 1
                pair_id = f"SIM_{pair_group}_{sim_pair_counter}"
                
                # Ghi nhận mô phỏng ngay vào Sổ Cái
                lich_su_vao_lenh.append({
                    "id_cap": pair_id,
                    "pair_group": pair_group,
                    "base": b_base,
                    "diff": b_diff,
                    "huong": th["chi_tiet"]["loai_lenh"],
                    "time_match": time.time(),
                    "open_price_base": fill_price_base,
                    "open_price_diff": fill_price_diff,
                    "chenh_lech_vao": th["chenh_lech"],
                    "speed_base_entry": san_data[b_base]["speed_60s"],
                    "speed_diff_entry": san_data[b_diff]["speed_60s"],
                })
                
                print(f"\n⚡ BÓP CÒ MÔ PHỎNG: {b_base} ({lenh_base} @ {fill_price_base:.3f}) <-> {b_diff} ({lenh_diff} @ {fill_price_diff:.3f}) | Lệch: {th['chenh_lech']:.2f}")
                
                huong_dang_danh_map[pair_group] = th["chi_tiet"]["loai_lenh"]
                thoi_diem_vao_lenh_cuoi_map[pair_group] = time.time()
                luu_tri_nho()
                
                so_cap_da_ban += 1
                if so_cap_da_ban >= quan_tri["max_concurrent_pairs"]: break

except KeyboardInterrupt:
    print("\n🛑 Đô Đốc đã hạ lệnh rút quân!")
    luu_tri_nho()
    print("✅ Đã lưu trí nhớ. Tạm biệt!")