import redis
import ujson as json
import time

r = redis.Redis(host='localhost', port=6379, db=1)

print("💉 BẮT ĐẦU CHIẾN DỊCH BƠM GIÁ GIẢ CHO 3 SÀN...")
print("🎯 Mục tiêu: Bơm EXNESS cao hơn TICKMILL & FXPRO 0.4 giá (Vượt mốc dev 0.1)")

start_time = time.time()

# Bơm liên tục trong 3 giây để đảm bảo Đô Đốc đếm đủ 300ms đóng băng
while time.time() - start_time < 3.0:
    now_msc = int(time.time() * 1000)
    
    # 1. TICKMILL (Ký hiệu: XAUUSD) - Giá thấp
    r.set("TICK:TICKMILL:XAUUSD", json.dumps({
        "bid": 2000.00, "ask": 2000.10, "time_msc": now_msc
    }))
    
    # 2. EXNESS (Ký hiệu: XAUUSD) - Giá vọt lên cao tạo chênh lệch
    r.set("TICK:EXNESS:XAUUSD", json.dumps({
        "bid": 2000.50, "ask": 2000.60, "time_msc": now_msc
    }))

    # 3. FXPRO (Ký hiệu: GOLD) - Giá thấp (Đi chung mâm với TICKMILL)
    r.set("TICK:FXPRO:GOLD", json.dumps({
        "bid": 2000.00, "ask": 2000.10, "time_msc": now_msc
    }))
    
    # Cho vòng lặp nghỉ 0.05s (Tương đương 20 lần bơm/giây)
    time.sleep(0.05)

print("✅ Đã bơm xong 3 giây! Đại ca liếc ngay sang màn hình Đô Đốc nhé!")