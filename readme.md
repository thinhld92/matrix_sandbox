# 🧪 Matrix Sandbox (Paper Trading Simulator)

Hệ thống mô phỏng giao dịch chênh lệch giá (Arbitrage) đa sàn trên nền tảng MetaTrader 5 (MT5). **Không vào lệnh thật** — Workers chỉ lấy tick data live từ MT5, mọi lệnh mua/bán đều được **mô phỏng** với fill ngay tại giá tick, tính phí commission, và ghi sổ kế toán đầy đủ như lệnh thật.

Phiên bản kế thừa từ **Matrix Hedger**, chuyển đổi sang hướng **khảo sát & paper trading** để phân tích chiến lược trước khi triển khai tài khoản thật.

## 🌟 Tính Năng

* **Paper Trading** — Mô phỏng fill tại giá tick hiện tại, không ảnh hưởng tài khoản thật.
* **Commission Tracking** — Khai báo `commission_per_lot` cho từng sàn, tính phí chính xác.
* **Running Balance** — Theo dõi số dư mô phỏng liên tục, bắt đầu từ `initial_balance` trong config.
* **Ma Trận N-Sàn** — Giao dịch chênh lệch giá chéo trên nhiều sàn.
* **Freeze Mode** — Ngâm lệnh đóng băng tuyệt đối (tính từ tick cuối cùng).
* **Khóa Hướng Per-Pair** — Mỗi cặp sàn (VD: TICKMILL_EXNESS) có khóa hướng riêng, không ảnh hưởng cặp khác.
* **Sổ Kế Toán CSV** — Ghi chi tiết từng lệnh: giá mở/đóng, profit, commission, balance, speed.
* **Bất Tử Trạng Thái** — Lưu trí nhớ xuống Redis. Tắt bật vẫn nhớ các lệnh đang gồng.
* **Telegram Alert** — Cảnh báo qua Telegram (tùy chọn).

---

## ⚙️ Cấu Hình (`config.json`)

**Mô phỏng:**
```json
"simulation": {
  "initial_balance": 10000.0,
  "lot_size": 0.01
}
```

**Commission cho từng sàn:**
```json
"brokers": {
  "TICKMILL": { "path": "...", "commission_per_lot": 2.0 },
  "EXNESS":  { "path": "...", "commission_per_lot": 0.0 },
  "FXPRO":   { "path": "...", "commission_per_lot": 5.0 }
}
```

**Chiến thuật** (freeze-only, không còn continuous mode):
```json
"chien_thuat": {
  "deviation_entry": 0.1,
  "deviation_close": 0.03,
  "stable_time": 300,
  ...
}
```

---

## 🛠️ Yêu Cầu Hệ Thống

1. **Python 3.9+**
2. **MetaTrader 5** — Cài nhiều bản MT5 cho từng sàn.
3. **Memurai / Redis** — localhost:6379.
4. **Thư viện**: `pip install redis MetaTrader5 requests ujson hiredis`

---

## 🚀 Khởi Chạy

Nháy đúp `start_bots.bat` hoặc chạy `python src/launcher.py`.

Hệ thống tự động bật:
1. **Worker** × N sàn — Chỉ lấy tick live (không vào lệnh).
2. **Super Master** — Phân tích chéo + mô phỏng fill.
3. **Accountant** — Ghi sổ, theo dõi balance.
4. **Telegram** (tùy chọn).

---

## 📊 Output

File CSV: `history/sandbox_history_{VPS_NAME}.csv`

Các cột: Time, Pair, Action, Direction, Volume, Prices, Profits, Fees, Net_Profit, **Running_Balance**, Speed, Config.

---
*Matrix Sandbox — Paper Trading Built to Learn.*