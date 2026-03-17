# 🤖 Matrix Hedger (HFT Multi-Broker Arbitrage)

Hệ thống Bot giao dịch chênh lệch giá (Arbitrage) siêu tốc đa sàn trên nền tảng MetaTrader 5 (MT5). Được thiết kế theo chuẩn kiến trúc **Microservices (SaaS Architecture)** với Redis làm trung tâm xử lý dữ liệu Real-time. Phiên bản Matrix Hedger hỗ trợ giao dịch song song trên cấu trúc N-Sàn (Vd: Tickmill, Exness, FxPro,...), được tối ưu hóa cực hạn bằng lõi C (`ujson` & `hiredis`), đảm bảo tốc độ phản hồi và khớp lệnh tính bằng micro-giây.

## 🌟 Tính Năng Nổi Bật (Core Features)

* **Ma Trận N-Sàn (Multi-Broker Matrix):** Hỗ trợ khai báo và giao dịch chênh lệch giá trên nhiều sàn cùng lúc. Master tự động tổ hợp các cặp sàn (VD: Tickmill-Exness, Exness-FxPro) để tìm cơ hội chênh lệch giá tốt nhất.
* **Kiến trúc Tách Não (Microservices):** Tách biệt hoàn toàn `Worker` (Trinh sát mặt trận: Kéo data/Vào lệnh MT5 từng sàn), `Super Master` (Đô đốc tổng tư lệnh: Tính toán logic ma trận) và `Accountant` (Kế toán tổng hợp). Chống nghẽn cổ chai tuyệt đối.
* **Động cơ Siêu Tốc (HFT Engine):** Tích hợp `ujson` và `hiredis` giúp tăng tốc độ đọc/ghi JSON. Worker đẩy Tick data liên tục lên Redis qua cơ chế Pipeline.
* **Tự Phục Hồi Đa Tầng & Bao Thanh Thiên:** Hệ thống "Bao Thanh Thiên" liên tục quét Sổ Cái. Tự động săn lùng và cắt bỏ các "lệnh góa phụ", "lệnh mồ côi", trảm ngay lập tức các lệnh kẹt do sàn trượt giá (Miss in/out).
* **Đóng Băng & Bám Đuổi (Freeze/Continuous Mode):** Hệ thống có 2 chế độ ngâm lệnh: Freeze (đóng băng tuyệt đối tính từ tick cuối cùng) hoặc Continuous (ngâm liên tục) để tối ưu lợi nhuận.
* **Máy Chém Giờ Cấm & Giới Nghiêm:** Tự động xả toàn bộ lệnh (cắt lỗ/chốt lời) tại các khung giờ cấm (VD: qua đêm, cuối tuần). Hoạt động độc lập và chuẩn xác theo múi giờ quốc tế **GMT+0**.
* **Khóa An Toàn (Low Equity Lock):** Hệ thống giám sát vốn (Equity) độc lập trên từng sàn. Tự động đóng băng cấm mở lệnh nếu vốn tụt dưới mức báo động.
* **Bất Tử Trạng Thái (State Persistence):** Lưu "Trí nhớ" liên tục xuống Redis. Tắt Bot bật lại vẫn nhớ Sổ Cái đang gồng những cặp lệnh nào, độ đồng bộ hoàn hảo.
* **Lính Liên Lạc (Telegram Service):** Tích hợp bot cảnh báo qua Telegram để theo dõi sát sao tình hình chiến sự 24/7.

---

## 🛠️ Yêu Cầu Hệ Thống (Prerequisites)

1. **Python 3.9+** (Đảm bảo đã tick chọn *"Add Python to PATH"* khi cài đặt).
2. **Thư viện C++ cho Windows:** Chạy cài đặt `vc_redist.x64.exe` để kích hoạt engine C cho Python.
3. **MetaTrader 5 (MT5):** Cài đặt nhiều bản MT5 khác nhau cho từng sàn khai báo trong cấu hình (VD: Exness, Tickmill, FxPro).
4. **Memurai / Redis:** Bản port của Redis dành cho Windows, đảm bảo cấu hình chạy ở localhost:6379, db: 1.

---

## ⚙️ Hướng Dẫn Cài Đặt & Sử Dụng

**Bước 1: Cài đặt thư viện cốt lõi**
Mở Terminal (CMD) tại bản đồ dự án và chạy:
```bash
pip install redis MetaTrader5 requests ujson hiredis
```
*(Lưu ý: Đảm bảo đã cài `vc_redist.x64.exe` trước khi cài `ujson` và `hiredis`).*

**Bước 2: Setup MT5**
1. Mở các trạm MT5 và đăng nhập tài khoản. Phải đúng đường dẫn `path` đã khai báo trong cấu hình.
2. Bật "Allow algorithmic trading" (Ctrl+O -> Expert Advisors).
3. Mở sẵn Chart của các mã giao dịch muốn đánh. Cấu hình đúng hậu tố mã (VD: `XAUUSD` hay `GOLD`) theo từng sàn.

**Bước 3: Cấu hình hệ thống**
1. Mở file `config.json`.
2. Khai báo danh sách các `active_brokers` và cài đặt đường dẫn executable cho từng sàn.
3. Thiết lập thông số ma trận `super_matrix` (Độ lệch vào, ra, Lot size, Giờ giao dịch GMT+0, Max Orders).
4. (Tùy chọn) Bật tính năng Telegram.

**Bước 4: Khởi Chạy Tướng Quân & Quân Đoàn**
Chỉ cần nháy đúp vào file `start_bots.bat` (Hoặc mở Terminal gõ lệnh `python src/launcher.py`).

Trạm biến áp trung tâm (Launcher) sẽ tự động kích hoạt:
1. **Lính liên lạc (Telegram)** - Tùy cấu hình.
2. Dàn **Worker (Trinh sát)** ứng với số lượng tài khoản (Broker) đã khai.
3. **Super Master (Đô Đốc)** - Đầu não phân tích chéo.
4. **Accountant (Kế Toán)** chạy thu nhỏ ở Taskbar lo hậu cần.

Mọi thứ chạy hoàn toàn tự động!

---

## 📚 Mẹo Quản Trị Hệ Thống (Pro-Tips)

1. ⚠️ **CẢNH BÁO CHẾ ĐỘ QUICKEDIT CỦA WINDOWS**
Đây là "bẫy chuột" chí mạng. Nếu bạn vô tình click chuột vào màn hình dòng lệnh, hệ thống sẽ bị ĐÓNG BĂNG.
👉 **Thuốc giải:** Click chuột phải vào thanh tiêu đề của cửa sổ Terminal -> Properties -> Bỏ tick ô "QuickEdit Mode" -> OK.

2. **Tẩy Não Sổ Cái (Clear Cache)**
Nếu muốn xóa sạch "trí nhớ" (ép quên các lệnh mồ côi ảo, ghép cặp lỗi khi test), mở CMD lên và gõ lệnh:
```bash
memurai-cli FLUSHALL
```
*(Lưu ý: Chắc chắn bạn hiểu mình đang làm gì vì hệ thống sẽ quên toàn bộ)*.

3. **Hot Reloading Khẩn Cấp**
Khi đang gặp "bão" thị trường, bạn có thể vào `config.json`, xóa danh sách `trading_hours` thành `[]` rồi lưu lại. Các Trinh sát lập tức cấm mở lệnh mới nhưng vẫn tiếp tục rình rập để gồng và chốt lời các lệnh cũ.

---
*Phát triển và Thiết kế bởi Hehehe ☕💻 - Multi-Broker & High-Frequency Arbitrage Built to Win.*