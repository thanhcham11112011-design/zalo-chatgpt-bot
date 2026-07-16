\# BƯỚC 25 – CHUẨN HÓA DEPLOY VÀ CHECKLIST BÀN GIAO



\## 1. Trạng thái đầu vào



\- Phiên bản: BOT CAP V3.1.

\- Nhánh triển khai: `main`.

\- Kiểm thử hồi quy gần nhất: `40 passed`.

\- Google Sheets là nguồn dữ liệu nghiệp vụ duy nhất.

\- Gemini hoạt động ở chế độ `OPTIONAL`; `STRICT\_SHEET\_ONLY=TRUE`.

\- Không áp dụng timeout tự thoát ngữ cảnh hội thoại.



\## 2. Tệp triển khai chuẩn



\- `app.py`

\- `config.py`

\- `requirements.txt`

\- `Procfile`

\- `README.md`

\- `services/`

\- `tests/conftest.py`

\- `tests/test\_core.py`

\- `tests/test\_gemini\_service.py`

\- `tests/test\_webhook\_idempotency.py`

\- `services/webhook\_service.py`

\- `pytest.ini`

\- `requirements-dev.txt`



Không đưa `.env`, `credentials.json`, token, API key hoặc khóa Service Account vào GitHub.



\## 3. Kiểm tra trước deploy



\- \[ ] Tên tệp trong repository là `app.py`, `config.py`, `requirements.txt`, `Procfile`, `README.md`; không giữ hậu tố tải xuống như `(11)`, `(6)`, `(3)`.

\- \[ ] Tệp `services/router\_utils.py` có trong repository.

\- \[ ] `router\_service.py` đang import 5 hàm tiện ích từ `router\_utils.py`.

\- \[ ] Chạy `python -m pytest -v` và nhận `40 passed`.

\- \[ ] Không có test thất bại; `DeprecationWarning` từ thư viện Google được phép xuất hiện.

\- \[ ] Không có token, credentials hoặc API key trong mã nguồn và lịch sử commit mới.

\- \[ ] Đã sao lưu commit ổn định gần nhất để có thể rollback.



\## 4. Cấu hình Render



Build command:



```text

pip install -r requirements.txt

```



Start command/Procfile:



```text

gunicorn app:app --workers 1 --threads 8 --timeout 120 --keep-alive 5

```



Health check path:



```text

/health

```



Biến môi trường bắt buộc:



\- `GOOGLE\_SHEET\_ID`

\- `GOOGLE\_CREDENTIALS\_JSON`

\- `ZALO\_ACCESS\_TOKEN`

\- `ZALO\_APP\_ID`

\- `ZALO\_OA\_SECRET\_KEY`

\- `INTERNAL\_API\_KEY`



Biến phục vụ làm mới token Zalo theo cơ chế hiện tại:



\- `ZALO\_APP\_ID`

\- `ZALO\_APP\_SECRET`

\- `ZALO\_REFRESH\_TOKEN`



Biến AI Optional:



\- `GEMINI\_API\_KEY`

\- `GEMINI\_MODEL` để trống nếu model vận hành được lấy từ `SETTING\_AI.MODEL`.



Giá trị vận hành:



```env

DEBUG\_MODE=FALSE

SHEET\_CACHE\_TTL\_SECONDS=300

SHEET\_CACHE\_MAX\_STALE\_SECONDS=1800

HEALTH\_CHECK\_TTL\_SECONDS=300

MESSAGE\_DEDUP\_TTL\_SECONDS=600

MAX\_PROCESSED\_MESSAGES=5000

ZALO\_WEBHOOK\_VERIFY\_SIGNATURE=TRUE

SHEET\_WEBHOOK\_EVENT=BOT\_WEBHOOK\_EVENT

WEBHOOK\_EVENT\_MAX\_ROWS=10000

WEBHOOK\_DEDUP\_FAIL\_CLOSED=TRUE

MAX\_ZALO\_TEXT\_LENGTH=1900

```



\## 5. Quy trình deploy



1\. Commit toàn bộ tệp đã đạt test trực tiếp vào nhánh `main`.

2\. Chờ Render tự động build từ commit mới.

3\. Xác nhận log có `Starting gunicorn`, `Listening at` và `Booting worker`.

4\. Xác nhận không có `Traceback`, lỗi import hoặc lỗi worker khởi động.

5\. Mở endpoint `/` và xác nhận HTTP `200`.

6\. Mở endpoint `/health` và xác nhận `status=healthy`, HTTP `200`.

7\. Mở endpoint `/webhook` bằng GET và xác nhận `Webhook OK`, HTTP `200`.

8\. Gọi `/test-ai` không có khóa và xác nhận HTTP `401`.

9\. Gọi `/test-ai` với header `X-Internal-API-Key` hợp lệ và xác nhận trả kết quả.



`degraded` chỉ được chấp nhận tạm thời khi Google Sheets lỗi nhưng cache còn hợp lệ; không dùng trạng thái này để chốt bàn giao.



\## 6. Kiểm thử duy nhất trên Zalo sau deploy



Chỉ gửi đúng câu:



```text

Xin BOT cho biết tổ BV ANTT tổ Ngọc Sơn - phường Phù Liễn - HP có ai?

```



Kết quả bắt buộc:



\- Route tra cứu liên hệ.

\- Bộ phận `ANCS`.

\- Địa bàn `Ngọc Sơn`.

\- Trả đúng 7 thành viên ANCS Ngọc Sơn.

\- Không trả `CSKV`.

\- Không trả `BO\_MAY\_TDP`.

\- Không phát sinh `ROUTER\_ERROR`.



\## 7. Rollback khi deploy lỗi



1\. Dừng kiểm thử Zalo, không tiếp tục phát sinh hội thoại trên bản lỗi.

2\. Mở lịch sử deploy của Render.

3\. Chọn commit ổn định gần nhất và thực hiện rollback/redeploy.

4\. Kiểm tra lại `/`, `/health` và `/webhook`.

5\. Khoanh đúng file/hàm gây lỗi, bổ sung test hồi quy rồi mới deploy lại.



Không sửa trực tiếp dữ liệu nghiệp vụ để che lỗi Python và không thay đổi ngoài phạm vi lỗi.



\## 8. Checklist bàn giao



\- \[ ] Repository chính và nhánh `main` đã xác định.

\- \[ ] Commit đang chạy trên Render đã ghi lại.

\- \[ ] URL dịch vụ Render đã ghi lại.

\- \[ ] URL webhook Zalo OA đã ghi lại.

\- \[ ] Google Sheet trung tâm và quyền Service Account đã kiểm tra.

\- \[ ] Người quản trị biết vị trí quản lý biến môi trường Render.

\- \[ ] Người quản trị biết quy trình làm mới token Zalo hiện tại.

\- \[ ] README kỹ thuật đã bàn giao.

\- \[ ] Bộ test và lệnh chạy test đã bàn giao.

\- \[ ] Checklist rollback đã bàn giao.

\- \[ ] Kết quả `40 passed` đã lưu.

\- \[ ] Kết quả `/health=healthy` sau deploy đã lưu.

\- \[ ] Kết quả câu test Zalo cuối cùng đã lưu.



\## 9. Tiêu chí hoàn thành Bước 25



Bước 25 hoàn thành khi đồng thời đạt đủ:



1\. `40 passed` trước deploy.

2\. Render build và khởi động Gunicorn thành công.

3\. `/`, `/health`, `/webhook` đạt yêu cầu.

4\. API nội bộ được bảo vệ bằng `INTERNAL\_API\_KEY`.

5\. Câu test Zalo duy nhất trả đúng ANCS Ngọc Sơn.

6\. Checklist bàn giao và rollback đã hoàn tất.



Khi đủ sáu điều kiện trên, dự án đạt `25/25 bước hoàn thành`.
