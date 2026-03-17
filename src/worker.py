import MetaTrader5 as mt5
import redis
import ujson as json
import time
import argparse
import os
import collections
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

# Khai báo các kênh liên lạc (Sandbox: Chỉ còn TICK và HEALTH)
REDIS_TICK_KEY = f"TICK:{args.broker.upper()}:{args.symbol.upper()}"
REDIS_HEALTH_KEY = f"HEALTH:{args.broker.upper()}"

if not mt5.initialize(path=mt5_path, portable=True, timeout=60000): 
    print(f"❌ Không thể khởi động MT5 cho {args.broker}")
    quit()

symbol_info = mt5.symbol_info(args.symbol)
if not symbol_info: 
    print(f"❌ Không tìm thấy mã {args.symbol} trên {args.broker}")
    quit()

print(f"✅ {args.role} đã sẵn sàng thu thập tín hiệu tại {args.broker} ({args.symbol}) [SANDBOX MODE]")

# ==========================================
# VÒNG LẶP CHÍNH (CHỈ LẤY TICK + HEALTH CHECK)
# ==========================================
last_health_check = 0
last_tick_time = 0

is_connected = False
is_trade_allowed = False

tick_history = collections.deque()

def tat_may_an_toan():
    print(f"\n🛑 [{args.broker}] Đang tắt máy an toàn...")
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
                # Kiểm tra tín hiệu tắt máy từ Redis
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

            # Bắn nhịp tim lên Redis liên tục
            pipe.set(REDIS_HEALTH_KEY, json.dumps({
                "connected": is_connected,
                "trade_allowed": is_trade_allowed,
                "update_time": now_sec
            }))
            co_du_lieu_moi = True

            # ----------------------------------------------------
            # 1. ĐÔI MẮT: LẤY TICK VÀ ĐẨY LÊN REDIS
            # ----------------------------------------------------
            if is_connected:
                tick = mt5.symbol_info_tick(args.symbol)
                
                # Cắt chuỗi deque những tick cũ hơn 60 giây
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
                    # Nạp Tick mới vào Deque
                    tick_history.append(now_sec)
                    speed_60s = len(tick_history)
                    last_tick_time = tick.time_msc
                    has_new_tick = True
                
                # Cập nhật lên Redis nếu có Tick mới HOẶC do Tick cũ bị Pop làm tụt speed
                if has_new_tick or speed_changed:
                    if tick:
                        pipe.set(REDIS_TICK_KEY, json.dumps({
                            "bid": tick.bid, 
                            "ask": tick.ask, 
                            "time_msc": tick.time_msc,
                            "speed_60s": speed_60s
                        }))
                        co_du_lieu_moi = True
                    
                    if has_new_tick and enable_realtime_log:
                        print(f"\r {args.symbol} | B: {tick.bid:.3f} - A: {tick.ask:.3f} | {speed_60s} Ti/m [SANDBOX]   ", end="", flush=True)

            # --- GỬI ĐỒNG LOẠT LÊN REDIS ---
            if co_du_lieu_moi:
                pipe.execute()

            # Điều tốc vòng lặp
            if is_connected:
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