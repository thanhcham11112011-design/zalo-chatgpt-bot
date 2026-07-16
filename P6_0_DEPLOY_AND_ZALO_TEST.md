# P6.0 – VÁ WEBHOOK LẶP P6-WH-001

## 1. Trạng thái bản vá

- Phạm vi: chỉ tầng kỹ thuật webhook, không thay đổi dữ liệu nghiệp vụ hoặc router.
- Kiểm thử tự động: `40 passed` gồm 21 core, 9 Gemini và 10 webhook P6.0.
- Trạng thái: sẵn sàng deploy thử; chưa được ghi `STABLE` cho đến khi kiểm tra trực tiếp trên Zalo đạt.

## 2. Biến môi trường phải cấu hình trên Render trước khi deploy

```env
ZALO_OA_SECRET_KEY=<OA Secret Key dùng ký webhook>
ZALO_WEBHOOK_VERIFY_SIGNATURE=TRUE
SHEET_WEBHOOK_EVENT=BOT_WEBHOOK_EVENT
WEBHOOK_EVENT_MAX_ROWS=10000
WEBHOOK_DEDUP_FAIL_CLOSED=TRUE
```

Lưu ý:

- `ZALO_OA_SECRET_KEY` có thể khác `ZALO_APP_SECRET`.
- Không đưa giá trị thật của khóa vào GitHub, ảnh chụp hoặc báo cáo.
- Nếu chưa xác định đúng OA Secret Key thì chưa deploy, vì BOT sẽ bỏ qua webhook sai chữ ký.

## 3. Tệp cần cập nhật lên GitHub

- `app.py`
- `config.py`
- `env.example`
- `services/sheet_api.py`
- `services/webhook_service.py`
- `tests/test_webhook_idempotency.py`
- `README.md`
- `VERSION.txt`
- `DEPLOY_CHECKLIST_BOT_CAP_V3_1.md`
- `P6_0_DEPLOY_AND_ZALO_TEST.md`

Có thể cập nhật toàn bộ thư mục trong gói ZIP P6.0 để tránh bỏ sót tệp mới.

## 4. Kiểm tra sau deploy

1. Mở `/` và xác nhận HTTP `200`.
2. Mở `/health` và xác nhận `status=healthy`.
3. Mở `/webhook` bằng GET và xác nhận `Webhook OK`.
4. Kiểm tra Render log không có `Traceback`.
5. Sau webhook hợp lệ đầu tiên, xác nhận Google Sheets tự có sheet `BOT_WEBHOOK_EVENT` với các cột chuẩn.

## 5. Ba câu kiểm tra trực tiếp trên Zalo

Gửi mỗi câu đúng một lần, chờ BOT trả lời xong rồi mới gửi câu tiếp theo:

1. `menu`
2. `Xin BOT cho biết tổ BV ANTT tổ Ngọc Sơn - phường Phù Liễn - HP có ai?`
3. `Cho tôi xin số điện thoại Trưởng Công an phường Phù Liễn.`

Sau câu thứ ba:

1. Không gửi thêm bất kỳ tin nhắn nào trong 10 phút.
2. Zalo chỉ được có đúng ba lượt trả lời mới, không tự gửi lại câu trước.
3. `LICH_SU_CHAT` chỉ được có đúng ba dòng mới tương ứng; cột `NOTE` có `MESSAGE_ID=`.
4. `BOT_WEBHOOK_EVENT` chỉ được có đúng ba khóa sự kiện mới.

Nếu BOT tự gửi thêm hoặc lịch sử tăng khi không có tin mới, chưa chốt P6.0 và gửi thời điểm phát sinh cùng ảnh hai sheet để tiếp tục truy vết.

## 6. Điều kiện chốt P6.0

- `40 passed` trước deploy.
- Render deploy thành công và `/health=healthy`.
- Ba câu Zalo trả lời đúng.
- Chờ 10 phút không có câu trả lời tự phát.
- `LICH_SU_CHAT` và `BOT_WEBHOOK_EVENT` khớp đúng ba lượt.

Khi đủ năm điều kiện trên mới chốt P6-WH-001 và chuyển sang vá 20 mã còn lại của Phiên 6.
