import MetaTrader5 as mt5
import redis
import ujson as json
import time
import argparse
import os
import threading 
import collections
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from utils.terminal import dan_tran_cua_so

# ==========================================
# KHỞI TẠO VÀ NẠP THÔNG SỐ
# ==========================================
parser = argparse.ArgumentParser()
parser.add_argument("--broker", required=True)
parser.add_argument("--symbol", required=True)
parser.add_argument("--role", default="WORKER")
args = parser.parse_args()

os.system(f"title 👷‍♂️ {args.role} - {args.broker} - {args.symbol}")
dan_tran_cua_so(2)

try:
    with open('config.json', 'r', encoding='utf-8') as f: 
        config = json.load(f)
    mt5_path = config['brokers'][args.broker]['path']
    redis_conf = config['redis']
    
    terminal_ui_conf = config.get('terminal_ui', {})
    enable_realtime_log = terminal_ui_conf.get('enable_realtime_log', True)
except Exception as e:
    print(f"❌ Lỗi nạp config: {e}")
    quit()

# Kết nối Redis
r = redis.Redis(host=redis_conf['host'], port=redis_conf['port'], db=redis_conf['db'], decode_responses=True)

# Khai báo các kênh liên lạc
REDIS_TICK_KEY = f"TICK:{args.broker.upper()}:{args.symbol.upper()}"
REDIS_POS_KEY = f"POSITION:{args.broker.upper()}:{args.symbol.upper()}"
REDIS_EQUITY_KEY = f"ACCOUNT:{args.broker.upper()}:EQUITY"
REDIS_HEALTH_KEY = f"HEALTH:{args.broker.upper()}"
QUEUE_ORDER_KEY = f"QUEUE:ORDER:{args.broker.upper()}"

mt5_lock = threading.Lock() # Khóa an toàn đa luồng cho MT5

if not mt5.initialize(path=mt5_path, portable=True, timeout=60000): 
    print(f"❌ Không thể khởi động MT5 cho {args.broker}")
    quit()

symbol_info = mt5.symbol_info(args.symbol)
if not symbol_info: 
    print(f"❌ Không tìm thấy mã {args.symbol} trên {args.broker}")
    quit()

# Tự động dò tìm chế độ khớp lệnh (IOC hoặc FOK) của Sàn
CACHED_FILLING_MODE = mt5.ORDER_FILLING_IOC 
if symbol_info.filling_mode & 1: 
    CACHED_FILLING_MODE = mt5.ORDER_FILLING_FOK
elif symbol_info.filling_mode & 2: 
    CACHED_FILLING_MODE = mt5.ORDER_FILLING_IOC

print(f"✅ {args.role} đã sẵn sàng tác chiến tại {args.broker} ({args.symbol})")

# ==========================================
# CÁC HÀM THỰC THI CHIẾN THUẬT
# ==========================================
def thuc_thi_dong_1_lenh(pos, current_tick, comment, chi_thi):
    close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = current_tick.bid if close_type == mt5.ORDER_TYPE_SELL else current_tick.ask
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": args.symbol, "volume": pos.volume,
        "type": close_type, "position": pos.ticket, "price": price, "deviation": 20,
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": CACHED_FILLING_MODE,
    }
    with mt5_lock: 
        result = mt5.order_send(request)
        
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        da_chot_so = False
        deals = []
        # Chờ tối đa 5 giây để MT5 cập nhật lịch sử Lãi/Lỗ
        for _ in range(25):
            time.sleep(0.2)
            deals = mt5.history_deals_get(position=pos.ticket)
            if deals and any(d.entry in [mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_OUT_BY] for d in deals):
                da_chot_so = True
                break
                    
        if da_chot_so and deals:
            bien_lai = {
                "role": chi_thi.get("role", args.broker), "ticket": pos.ticket,
                "volume": pos.volume, "profit": sum(d.profit for d in deals), 
                "fee": sum(d.commission + d.swap for d in deals),
                "open_price": next((d.price for d in deals if d.entry == mt5.DEAL_ENTRY_IN), 0),
                "close_price": next((d.price for d in deals if d.entry in [mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_OUT_BY]), 0),
                "context": chi_thi.get("context", {}) 
            }
            r.lpush("QUEUE:ACCOUNTANT", json.dumps(bien_lai))
    else: print(f"❌ Lỗi đóng lệnh {pos.ticket}: {result.retcode}") 

def thuc_thi_dong_bo_lich_su(chi_thi):
    ticket = chi_thi.get("ticket")
    deals = mt5.history_deals_get(position=ticket)
    if deals:
        bien_lai = {
            "role": chi_thi.get("role", args.broker), "ticket": ticket,
            "volume": deals[0].volume if deals else 0, "profit": sum(d.profit for d in deals), 
            "fee": sum(d.commission + d.swap for d in deals),
            "open_price": next((d.price for d in deals if d.entry == mt5.DEAL_ENTRY_IN), 0),
            "close_price": next((d.price for d in deals if d.entry in [mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_OUT_BY]), 0),
            "context": chi_thi.get("context", {}) 
        }
        r.lpush("QUEUE:ACCOUNTANT", json.dumps(bien_lai))

def thuc_thi_chi_thi(chi_thi, current_tick):
    action = chi_thi.get("action")
    if action in ["BUY", "SELL"]:
        is_buy = (action == "BUY")
        request = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": args.symbol, "volume": float(chi_thi.get("volume", 0.01)),
            "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL, 
            "price": current_tick.ask if is_buy else current_tick.bid,
            "deviation": 20, "type_time": mt5.ORDER_TIME_GTC, "type_filling": CACHED_FILLING_MODE,
        }
        with mt5_lock: 
            mt5.order_send(request)
            
    elif action == "CLOSE_BY_TICKET":
        positions = mt5.positions_get(ticket=chi_thi.get("ticket")) 
        if positions: 
            executor.submit(thuc_thi_dong_1_lenh, positions[0], current_tick, "", chi_thi)

    elif action == "FETCH_HISTORY_ONLY":
        executor.submit(thuc_thi_dong_bo_lich_su, chi_thi)

# ==========================================
# VÒNG LẶP CHÍNH (TRÁI TIM WORKER TỐI THƯỢNG)
# ==========================================
last_health_check = 0
last_pos_update = 0  
last_tick_time = 0

is_connected = False
is_trade_allowed = False

executor = ThreadPoolExecutor(max_workers=3)

tick_history = collections.deque()

# Khai báo bộ nhớ đệm cho Tiền và Lệnh để lúc in Tick không bị lỗi
so_lenh_hien_tai = 0
equity_hien_tai = 0.0

def tat_may_an_toan():
    print(f"\n🛑 [{args.broker}] Đang tắt máy an toàn...")
    executor.shutdown(wait=False)
    mt5.shutdown()
    print(f"✅ [{args.broker}] MT5 đã ngắt kết nối sạch sẽ. Tạm biệt!")

try:
    while True:
        try:
            now_sec = time.time()
            pipe = r.pipeline()
            co_du_lieu_moi = False 
            
            # ----------------------------------------------------
            # 0. BỘ PHẬN KHÁM SỨC KHỎE (Hỏi MT5 2s/lần)
            # ----------------------------------------------------
            if now_sec - last_health_check >= 2.0:
                # 👉 Kiểm tra tín hiệu tắt máy từ Redis (Nhờ bám theo Health Check nên 0 tốn hiệu năng)
                if r.get("SIGNAL:SHUTDOWN"):
                    tat_may_an_toan()
                    quit()

                term_info = mt5.terminal_info()
                if term_info:
                    is_connected = term_info.connected
                    is_trade_allowed = term_info.trade_allowed
                else:
                    is_connected = False
                    is_trade_allowed = False
                last_health_check = now_sec 

                # Cấp cứu nội bộ
                if term_info is None:
                    print(f"\n🚨 [{args.broker}] MT5 Crash! Đang khởi động lại...")
                    mt5.initialize(path=mt5_path, portable=True, timeout=60000)
                elif not is_connected:
                    print(f"\n🔌 [{args.broker}] MẤT MẠNG TỚI SERVER SÀN!")
                elif not is_trade_allowed:
                    print(f"\n🛑 [{args.broker}] NÚT ALGO TRADING ĐANG TẮT!")

            # Bắn nhịp tim lên Redis liên tục
            pipe.set(REDIS_HEALTH_KEY, json.dumps({
                "connected": is_connected,
                "trade_allowed": is_trade_allowed,
                "update_time": now_sec
            }))
            co_du_lieu_moi = True

            # ----------------------------------------------------
            # 1. ĐÔI TAI: LUÔN LẮNG NGHE ĐỂ DỌN RÁC HOẶC BÓP CÒ
            # ----------------------------------------------------
            thu_tu_master = r.rpop(QUEUE_ORDER_KEY)
            if thu_tu_master:
                if is_connected and is_trade_allowed:
                    current_tick = mt5.symbol_info_tick(args.symbol)
                    if current_tick:
                        executor.submit(thuc_thi_chi_thi, json.loads(thu_tu_master), current_tick)
                else:
                    print(f"\n🗑️ [{args.broker}] Đang mất mạng, ném sọt rác lệnh cũ!")

            # ----------------------------------------------------
            # 2. ĐÔI MẮT VÀ CHỤP ẢNH (CHỈ LÀM KHI KHỎE MẠNH)
            # ----------------------------------------------------
            if is_connected and is_trade_allowed:
                # 👉 A. Báo cáo Lệnh & Tiền (vẫn giữ Giảm xóc 0.1s/lần cho nhẹ MT5)
                if now_sec - last_pos_update >= 0.1:
                    positions = mt5.positions_get(symbol=args.symbol)
                    so_lenh_hien_tai = len(positions) if positions else 0
                    pipe.set(REDIS_POS_KEY, json.dumps([{"ticket": p.ticket, "time_msc": p.time_msc} for p in positions] if positions else []))
                    
                    acc_info = mt5.account_info()
                    if acc_info: 
                        equity_hien_tai = acc_info.equity
                        pipe.set(REDIS_EQUITY_KEY, equity_hien_tai)
                    
                    last_pos_update = now_sec
                    co_du_lieu_moi = True

                # 👉 B. Báo cáo Tick & In Màn Hình (Chạy tốc độ tột đỉnh)
                tick = mt5.symbol_info_tick(args.symbol)
                
                # 1. Cắt chuỗi deque những tick cũ hơn 60 giây (dùng now_sec để không bị treo nếu mất tick)
                cutoff_time = now_sec - 60.0
                speed_changed = False
                while len(tick_history) > 0:
                     if tick_history[0] < cutoff_time:
                         tick_history.popleft()
                         speed_changed = True
                     else:
                         break
                
                speed_60s = len(tick_history)
                has_new_tick = False
                
                if tick and tick.time_msc != last_tick_time:
                    # 2. Nạp Tick mới vào Deque (dùng now_sec làm mốc thời gian)
                    tick_history.append(now_sec)
                    speed_60s = len(tick_history)
                    last_tick_time = tick.time_msc
                    has_new_tick = True
                
                # 3. Cập nhật lên Redis nếu có Tick mới HOẶC do Tick cũ bị Pop làm tụt speed
                if has_new_tick or speed_changed:
                    if tick:
                        pipe.set(REDIS_TICK_KEY, json.dumps({
                            "bid": tick.bid, 
                            "ask": tick.ask, 
                            "time_msc": tick.time_msc,
                            "speed_60s": speed_60s
                        }))
                        co_du_lieu_moi = True
                    
                    if has_new_tick:
                        if enable_realtime_log:
                            # IN RA MÀN HÌNH MƯỢT MÀ NẾU ĐƯỢC PHÉP
                            print(f"\r {args.symbol} | B: {tick.bid:.3f} - A: {tick.ask:.3f} | E: {equity_hien_tai:.2f}$ | Open: {so_lenh_hien_tai} | {speed_60s} Ti/m   ", end="", flush=True)
                        elif now_sec - last_pos_update >= 0.5:
                            # CHẾ ĐỘ ẨN GIÚP BƠM HẾT TÀI NGUYÊN CHO REDIS (Chỉ in nhích tí cho đỡ chết màn hình)
                            print(f"\r {args.symbol} | [HFT_MODE] | E: {equity_hien_tai:.2f}$ | Open: {so_lenh_hien_tai} | {speed_60s} Ti/m   ", end="", flush=True)

            # --- GỬI ĐỒNG LOẠT BƯU PHẨM LÊN REDIS ---
            if co_du_lieu_moi:
                pipe.execute()

            # Điều tốc vòng lặp
            if is_connected and is_trade_allowed:
                time.sleep(0.001) 
            else:
                time.sleep(0.1)

        except redis.ConnectionError:
            print(f"\n⚠️ [{args.broker}] Rớt kết nối Redis cục bộ, đang kết nối lại...")
            time.sleep(1)
        except Exception as e:
            print(f"\n⚠️ [{args.broker}] Lỗi vặt trong vòng lặp Worker: {e}")
            time.sleep(0.01)

except KeyboardInterrupt:
    tat_may_an_toan()