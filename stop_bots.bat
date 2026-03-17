@echo off
:: Dòng lệnh ma thuật: Ép Windows quay về thư mục gốc của file .bat này
cd /d "%~dp0"
title 🛑 MATRIX SANDBOX - LENH RUT QUAN

echo.
echo ============================================
echo   🛑 DANG HA LENH RUT QUAN TOAN BO...
echo ============================================
echo.

:: Kích hoạt venv để dùng được Python + redis
call venv\Scripts\activate

:: Gửi tín hiệu tắt máy qua Redis (tất cả process sẽ tự ngắt an toàn)
python -c "import redis, json; r = redis.Redis(**json.load(open('config.json'))['redis'], decode_responses=True); r.setex('SIGNAL:SHUTDOWN', 30, '1'); print('📡 Da gui tin hieu tat may qua Redis!')"

echo ⏳ Cho 10 giay de cac process tu tat an toan...
timeout /t 10 /nobreak >nul

:: Dọn dẹp tín hiệu shutdown
python -c "import redis, json; r = redis.Redis(**json.load(open('config.json'))['redis'], decode_responses=True); r.delete('SIGNAL:SHUTDOWN'); print('🧹 Da don dep tin hieu shutdown.')"

:: Dự phòng: Nếu còn sót process nào chưa tắt thì Force Kill
taskkill /F /FI "WINDOWTITLE eq *MATRIX SANDBOX*" 2>nul
taskkill /F /FI "WINDOWTITLE eq *SANDBOX*" 2>nul
taskkill /F /FI "WINDOWTITLE eq *TELEGRAM*" 2>nul

echo.
echo ✅ Tat ca quan doan da rut lui an toan!
echo.
pause
