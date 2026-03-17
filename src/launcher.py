import json
import subprocess
import time
import os

# Đổi tên cửa sổ chính của Launcher cho ngầu
os.system("title 🚀 TRUNG TÂM CHỈ HUY - MATRIX HEDGER")

print("🚀 ĐANG KHỞI ĐỘNG HỆ THỐNG MATRIX HEDGER (MA TRẬN N-SÀN)...")

# ==========================================
# 1. ĐỌC CONFIG
# ==========================================
try:
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
except Exception as e:
    print(f"❌ Lỗi đọc config.json: {e}")
    quit()

matrix_cfg = config.get('super_matrix', {})
active_brokers = matrix_cfg.get('active_brokers', [])
symbol_map = matrix_cfg.get('symbol_mapping', {})

if not active_brokers:
    print("❌ Lỗi: Không có sàn nào được khai báo trong active_brokers!")
    quit()

# ==========================================
# 2. BẬT ĐƯỜNG DÂY NÓNG TELEGRAM
# ==========================================
if config.get('telegram', {}).get('enable', False):
    print("📨 Đang gọi lính liên lạc: Telegram Service...")
    subprocess.Popen(
        ['cmd', '/k', 'python', 'src/services/telegram_bot.py'], 
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )
    time.sleep(2) # Đợi Telegram bot khởi động xong

# ==========================================
# 3. BẬT DÀN TRINH SÁT TIỀN TUYẾN (WORKERS)
# ==========================================
print(f"\n👷‍♂️ ĐANG BỐ TRÍ DÀN TRINH SÁT ({len(active_brokers)} SÀN)...")
for broker in active_brokers:
    # Lấy đúng mã giao dịch của sàn đó từ config
    symbol = symbol_map.get(broker, "")
    if not symbol:
        print(f"⚠️ Thiếu mapping mã giao dịch cho sàn {broker}. Bỏ qua!")
        continue
        
    print(f"   👉 Đang gọi Worker: {broker} - {symbol}")
    subprocess.Popen(
        # Role bây giờ chỉ đơn giản là WORKER, không cần phân biệt BASE/DIFF nữa
        ['cmd', '/k', 'python', 'src/worker.py', '--broker', broker, '--symbol', symbol, '--role', broker], 
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )
    time.sleep(3) # Cực kỳ cần thiết: Chờ 3s cho MT5 load xong để tránh kẹt I/O

# ==========================================
# 4. BẬT TƯỚNG QUÂN ĐÔ ĐỐC (SUPER MASTER)
# ==========================================
print("\n🧠 ĐANG ĐÁNH THỨC ĐÔ ĐỐC TỔNG TƯ LỆNH...")
subprocess.Popen(
    ['cmd', '/k', 'python', 'src/super_master.py'], 
    creationflags=subprocess.CREATE_NEW_CONSOLE
)
time.sleep(2)

# ==========================================
# 5. BẬT KẾ TOÁN TRƯỞNG TỔNG HỢP
# ==========================================
print("\n👓 ĐANG ĐÁNH THỨC KẾ TOÁN TRƯỞNG TỔNG HỢP...")
# Bật ẩn dưới taskbar để đỡ chật màn hình
command = 'start "KETOAN_MATRIX" /min cmd /k python src/accountant.py'
subprocess.Popen(command, shell=True)
time.sleep(2)

print("\n✅ TẤT CẢ QUÂN ĐOÀN ĐÃ VÀO VỊ TRÍ!")
print(f"👀 Dàn trận hiện tại: 1 Đô Đốc, 1 Kế Toán, và {len(active_brokers)} Trinh sát.")