# \# BOT CAP V3.1 – Nhân viên AI Zalo OA

# 

# Hệ thống hỗ trợ người dân tra cứu thủ tục hành chính, thông tin liên hệ, câu hỏi thường gặp và hướng dẫn nghiệp vụ qua Zalo Official Account.

# 

# \## 1. Kiến trúc

# 

# ```text

# Người dân

# &#x20;  ↓

# Zalo Official Account

# &#x20;  ↓

# Flask/Python trên Render

# &#x20;  ↓

# Router dữ liệu + AI Optional

# &#x20;  ↓

# Google Sheets

# &#x20;  ↓

# Zalo Official Account

# ```

# 

# Google Sheets là nguồn dữ liệu nghiệp vụ duy nhất. Python chỉ thực hiện đọc dữ liệu, chuẩn hóa, định tuyến, chấm điểm, quản lý phiên, ghi log và gửi câu trả lời.

# 

# \## 2. Nguyên tắc phát triển

# 

# 1\. Không suy luận khi chưa có căn cứ dữ liệu.

# 2\. Không hardcode nội dung nghiệp vụ trong Python.

# 3\. Google Sheets là trung tâm cấu hình và dữ liệu.

# 4\. AI chỉ là lớp phụ trợ tùy chọn.

# 5\. Khi thiếu dữ liệu thủ tục, AI không được tự tạo câu trả lời.

# 6\. Mở rộng chức năng chủ yếu bằng dữ liệu Google Sheets.

# 7\. Mỗi hàm chỉ dùng hai dòng chú thích: `Chức năng` và `Vai trò`.

# 8\. Mọi thay đổi định tuyến phải chạy kiểm thử hồi quy.

# 9\. Chỉ vá đúng vùng code cần thay đổi.

# 

# \## 3. Chức năng chính

# 

# \- Tra cứu thủ tục căn cước.

# \- Tra cứu cư trú.

# \- Hướng dẫn VNeID.

# \- Tra cứu phương tiện giao thông.

# \- Tra cứu lý lịch tư pháp.

# \- Trả lời FAQ.

# \- Tra cứu số điện thoại, cán bộ, bộ phận và địa bàn phụ trách.

# \- Duy trì ngữ cảnh câu hỏi nối tiếp.

# \- Cho phép đổi sang thủ tục mới khi người dân nêu rõ yêu cầu.

# \- Lọc ngôn từ không phù hợp.

# \- Ghi lịch sử hội thoại.

# \- Ghi câu hỏi chưa có dữ liệu.

# \- Chống xử lý webhook trùng.

# \- Chia tin nhắn dài trước khi gửi Zalo.

# \- Health check Google Sheets, cache, hiệu lực dữ liệu và AI.

# \- Gemini hoạt động ở chế độ `OPTIONAL`.

# 

# \## 4. Cấu trúc dự án

# 

# ```text

# BOT\_CAP\_3.1/

# ├── app.py

# ├── config.py

# ├── Procfile

# ├── requirements.txt

# ├── README.md

# ├── tests/

# │   ├── conftest.py

# │   └── test\_core.py

# └── services/

# &#x20;   ├── console\_logger.py

# &#x20;   ├── gemini\_service.py

# &#x20;   ├── logger.py

# &#x20;   ├── router\_service.py

# &#x20;   ├── router\_utils.py

# &#x20;   ├── search\_engine.py

# &#x20;   ├── session\_manager.py

# &#x20;   ├── sheet\_api.py

# &#x20;   ├── text\_utils.py

# &#x20;   └── zalo\_service.py

# ```

# 

# `router\\\_service.py` giữ luồng định tuyến chính. Các hàm tiện ích dùng chung đã được tách sang `router\\\_utils.py`.

# 

# \## 5. Google Sheets

# 

# \### 5.1. Sheet lõi

# 

# Hệ thống kiểm tra các sheet lõi sau:

# 

# ```text

# MENU

# SETTING\_SYSTEM

# SETTING\_AI

# SETTING\_CHAT

# PROMPT

# THONGTIN

# TRA\_CUU\_LIEN\_HE

# FAQ

# LICH\_SU\_CHAT

# BOT\_SESSION

# DATA\_DICTIONARY

# BOT\_31\_SCHEMA

# ```

# 

# Sheet `FILTER\\\_BAD\\\_WORD` được dùng cho bộ lọc ngôn từ.

# 

# Các sheet thủ tục có tiền tố `THU\\\_TUC\\\_` được lấy động từ cột `SHEET\\\_DU\\\_LIEU` trong sheet `MENU`, không khai báo cố định từng nhóm trong router.

# 

# \### 5.2. Vai trò một số sheet

# 

# | Sheet | Vai trò |

# |---|---|

# | `MENU` | Định tuyến nhóm chức năng và sheet dữ liệu |

# | `THU\\\_TUC\\\_\\\*` | Dữ liệu thủ tục hành chính |

# | `FAQ` | Câu hỏi thường gặp và lớp hiểu ngữ cảnh |

# | `TRA\\\_CUU\\\_LIEN\\\_HE` | Cán bộ, bộ phận, địa bàn và số điện thoại |

# | `SETTING\\\_SYSTEM` | Tên BOT, phiên bản, đơn vị và thông tin hệ thống |

# | `SETTING\\\_AI` | Cấu hình AI Optional, model, timeout và giới hạn |

# | `SETTING\\\_CHAT` | Nội dung chào, kết thúc, chưa có dữ liệu và hướng dẫn |

# | `PROMPT` | Prompt AI theo nhóm dữ liệu |

# | `THONGTIN` | Địa chỉ, giờ làm việc và thông tin đơn vị |

# | `LICH\\\_SU\\\_CHAT` | Lịch sử hội thoại và thống kê |

# | `BOT\\\_SESSION` | Khôi phục ngữ cảnh khi bộ nhớ tiến trình bị mất |

# | `DATA\\\_DICTIONARY` | Từ điển dữ liệu |

# | `BOT\\\_31\\\_SCHEMA` | Mô tả cấu trúc dữ liệu cần kiểm tra |

# | `FILTER\\\_BAD\\\_WORD` | Quy tắc lọc ngôn từ |

# 

# \## 6. Cài đặt môi trường phát triển

# 

# \### 6.1. Tạo môi trường ảo

# 

# Windows PowerShell:

# 

# ```powershell

# python -m venv .venv

# .venv\\Scripts\\Activate.ps1

# ```

# 

# \### 6.2. Cài thư viện

# 

# ```powershell

# python -m pip install --upgrade pip

# python -m pip install -r requirements.txt

# ```

# 

# Các thư viện chính:

# 

# ```text

# Flask==3.0.3

# flask-cors==4.0.1

# requests==2.32.3

# gspread==6.1.4

# google-auth==2.49.0

# gunicorn==22.0.0

# python-dotenv==1.0.1

# google-genai==2.11.0

# ```

# 

# \## 7. Biến môi trường

# 

# Không đưa token, khóa API hoặc thông tin tài khoản thật vào Git.

# 

# \### 7.1. Biến bắt buộc

# 

# | Biến | Nội dung |

# |---|---|

# | `GOOGLE\\\_SHEET\\\_ID` | ID file Google Sheets trung tâm |

# | `GOOGLE\\\_CREDENTIALS\\\_JSON` | JSON Service Account dưới dạng chuỗi |

# | `ZALO\\\_ACCESS\\\_TOKEN` | Access Token Zalo OA |

# | `INTERNAL\\\_API\\\_KEY` | Khóa bảo vệ `/test-ai` và `/api/chat` |

# 

# Có thể dùng `GOOGLE\\\_CREDENTIALS\\\_FILE` khi chạy cục bộ, nhưng khi deploy Render nên dùng `GOOGLE\\\_CREDENTIALS\\\_JSON`.

# 

# \### 7.2. Biến Zalo

# 

# | Biến | Nội dung |

# |---|---|

# | `ZALO\\\_APP\\\_ID` | App ID Zalo |

# | `ZALO\\\_APP\\\_SECRET` | App Secret Zalo |

# | `ZALO\\\_REFRESH\\\_TOKEN` | Refresh Token Zalo |

# | `ZALO\\\_ACCESS\\\_TOKEN` | Access Token đang sử dụng |

# 

# \### 7.3. Biến AI

# 

# | Biến | Nội dung |

# |---|---|

# | `GEMINI\\\_API\\\_KEY` | Khóa API Gemini |

# | `GEMINI\\\_MODEL` | Biến tương thích kỹ thuật; model vận hành ưu tiên đọc từ `SETTING\\\_AI.MODEL` |

# 

# AI không phải thành phần bắt buộc để router Google Sheets hoạt động.

# 

# \### 7.4. Biến vận hành khuyến nghị

# 

# ```env

# DEBUG\_MODE=FALSE

# SHEET\_CACHE\_TTL\_SECONDS=300

# SHEET\_CACHE\_MAX\_STALE\_SECONDS=1800

# HEALTH\_CHECK\_TTL\_SECONDS=300

# MESSAGE\_DEDUP\_TTL\_SECONDS=600

# MAX\_PROCESSED\_MESSAGES=5000

# MAX\_ZALO\_TEXT\_LENGTH=1900

# ```

# 

# \## 8. Chạy cục bộ

# 

# ```powershell

# python app.py

# ```

# 

# Mặc định ứng dụng chạy tại:

# 

# ```text

# http://127.0.0.1:5000

# ```

# 

# Kiểm tra dịch vụ:

# 

# ```powershell

# curl http://127.0.0.1:5000/

# ```

# 

# Kiểm tra health:

# 

# ```powershell

# curl http://127.0.0.1:5000/health

# ```

# 

# \## 9. API và webhook

# 

# \### 9.1. `GET /`

# 

# Kiểm tra Flask đang hoạt động. Endpoint này không đọc Google Sheets.

# 

# \### 9.2. `GET /health`

# 

# Kiểm tra:

# 

# \- Cấu hình bắt buộc.

# \- Kết nối Google Sheets.

# \- Sheet thiếu hoặc sai cấu trúc.

# \- Trạng thái cache.

# \- Hiệu lực dữ liệu.

# \- Trạng thái AI Optional.

# \- Tuổi của kết quả health check đang cache.

# 

# Trạng thái có thể là:

# 

# | Trạng thái | Ý nghĩa |

# |---|---|

# | `healthy` | Hệ thống và Google Sheets hoạt động |

# | `degraded` | Google Sheets lỗi tạm thời nhưng còn cache hợp lệ |

# | `unhealthy` | Thiếu cấu hình, thiếu sheet hoặc không còn dữ liệu dự phòng |

# 

# \### 9.3. `GET/POST /test-ai`

# 

# Endpoint kiểm thử nội bộ. Bắt buộc gửi header:

# 

# ```text

# X-Internal-API-Key: <INTERNAL\_API\_KEY>

# ```

# 

# Ví dụ PowerShell:

# 

# ```powershell

# $headers = @{

# &#x20;   "X-Internal-API-Key" = "YOUR\_INTERNAL\_API\_KEY"

# }

# 

# Invoke-RestMethod `

# &#x20;   -Method Post `

# &#x20;   -Uri "http://127.0.0.1:5000/test-ai" `

# &#x20;   -Headers $headers `

# &#x20;   -ContentType "application/json" `

# &#x20;   -Body '{"user\_id":"test-web","question":"menu"}'

# ```

# 

# \### 9.4. `POST /api/chat`

# 

# API chat nội bộ, dùng chung luồng xử lý với Zalo. Endpoint này cũng yêu cầu `X-Internal-API-Key`.

# 

# \### 9.5. `GET/POST /webhook`

# 

# \- `GET`: kiểm tra webhook đang hoạt động.

# \- `POST`: nhận sự kiện Zalo OA.

# \- Chỉ xử lý sự kiện `user\\\_send\\\_text`.

# \- Các sự kiện khác được bỏ qua an toàn.

# \- `message\\\_id` được ghi nhớ tạm thời để chống webhook trùng.

# 

# \## 10. Kiểm thử

# 

# Chạy toàn bộ bộ test hiện tại:

# 

# ```powershell

# python -m pytest -v tests/test\_core.py

# ```

# 

# Mốc kiểm thử sau Bước 23:

# 

# ```text

# 21 passed

# ```

# 

# Cảnh báo `DeprecationWarning` từ thư viện Google không làm bài test thất bại.

# 

# Các nhóm kiểm thử hiện có:

# 

# \- Chuẩn hóa tiếng Việt và số điện thoại.

# \- Chia và gửi tin nhắn Zalo.

# \- Chống webhook trùng.

# \- Giới hạn bộ nhớ chống trùng.

# \- Đọc, lưu và xóa session.

# \- CCCD đủ 14 tuổi.

# \- FAQ thoát khỏi context thủ tục cũ.

# \- Tra cứu PCTP.

# \- Trình báo đúng bộ phận.

# \- CSKV đúng địa bàn.

# \- Câu hỏi chi tiết giữ đúng thủ tục.

# \- Thủ tục mới ghi đè context cũ.

# \- Địa bàn ngoài danh sách không mở rộng.

# \- CCCD ghi đè context phương tiện giao thông.

# \- Tạm trú ghi đè context đăng ký xe tạm thời.

# 

# Sau mỗi lần sửa router:

# 

# ```powershell

# python -m pytest -v tests/test\_core.py

# ```

# 

# Chỉ deploy khi toàn bộ bài test đạt.

# 

# \## 11. Deploy Render

# 

# \### 11.1. Build command

# 

# ```text

# pip install -r requirements.txt

# ```

# 

# \### 11.2. Start command

# 

# `Procfile` hiện dùng:

# 

# ```text

# gunicorn app:app --workers 1 --threads 8 --timeout 120 --keep-alive 5

# ```

# 

# \### 11.3. Cấu hình Render

# 

# 1\. Tạo Web Service từ repository.

# 2\. Khai báo toàn bộ biến môi trường.

# 3\. Không tải `credentials.json` hoặc file chứa token lên repository.

# 4\. Build và deploy.

# 5\. Mở `/`.

# 6\. Mở `/health`.

# 7\. Kiểm tra webhook Zalo.

# 8\. Kiểm thử các câu hồi quy quan trọng trên Zalo OA.

# 

# \## 12. AI Optional

# 

# AI chỉ được gọi khi các cổng trong `SETTING\\\_AI` cho phép.

# 

# Cấu hình vận hành khuyến nghị:

# 

# ```text

# AI\_ENABLED=TRUE

# AI\_IS\_CORE=FALSE

# AI\_MODE=OPTIONAL

# AI\_STATUS=ONLINE

# STRICT\_SHEET\_ONLY=TRUE

# ENABLE\_CONTEXT=TRUE

# ENABLE\_RAG=TRUE

# ENABLE\_AI\_SUMMARIZE=TRUE

# ENABLE\_AI\_GENERAL\_KNOWLEDGE=FALSE

# ALLOW\_AI\_WITHOUT\_SHEET\_CONTEXT=FALSE

# ALLOW\_AI\_PROCEDURE\_WITHOUT\_DATA=FALSE

# ```

# 

# Khi có `ai\\\_context`, Gemini chỉ được diễn đạt lại nội dung đã xác minh từ Google Sheets. AI không được bổ sung thông tin ngoài dữ liệu được cấp.

# 

# Nếu Gemini lỗi, hệ thống giữ câu trả lời từ Google Sheets hoặc trả thông báo dự phòng; lỗi AI không được làm gián đoạn luồng chính.

# 

# \## 13. Cache và khả năng chịu lỗi

# 

# \- Dữ liệu Google Sheets được cache để giảm số lần đọc.

# \- Cache còn mới được dùng bình thường.

# \- Cache cũ trong giới hạn cho phép chỉ dùng khi Google Sheets lỗi.

# \- Cache quá hạn bị từ chối.

# \- `/health` hiển thị số sheet có dữ liệu, số sheet còn mới, số sheet dự phòng và số sheet hết hạn.

# \- Kết quả health check cũng có TTL riêng để tránh liên tục gọi Google Sheets.

# 

# \## 14. Session

# 

# \- Context được giữ trong bộ nhớ để xử lý nhanh.

# \- `BOT\\\_SESSION` dùng để khôi phục khi tiến trình khởi động lại.

# \- `save\\\_context()` chỉ ghi khi ngữ cảnh kỹ thuật thay đổi.

# \- `clear\\\_context()` xóa cả bộ nhớ và dòng session.

# \- Không áp dụng cơ chế tự thoát ngữ cảnh chỉ vì hết thời gian.

# \- Câu hỏi chi tiết ngắn tiếp tục dùng thủ tục hiện tại.

# \- Khi người dân nêu rõ thủ tục khác, thủ tục mới được ưu tiên.

# 

# \## 15. Log và theo dõi

# 

# Hệ thống ghi:

# 

# \- Lịch sử hội thoại.

# \- Nguồn định tuyến.

# \- Trạng thái gọi AI.

# \- Model AI.

# \- Câu hỏi chưa có dữ liệu.

# \- Lỗi gửi Zalo.

# \- Lỗi webhook.

# \- Lỗi Google Sheets.

# \- Trạng thái cache dự phòng.

# 

# Không bật log toàn bộ payload webhook trong môi trường vận hành.

# 

# \## 16. Bảo mật

# 

# \- Không commit `.env`, credentials, token hoặc API key.

# \- Bảo vệ `/test-ai` và `/api/chat` bằng `INTERNAL\\\_API\\\_KEY`.

# \- Không đưa khóa bí mật vào response `/health`.

# \- Không ghi token vào log.

# \- Chỉ cấp quyền Google Sheets cho Service Account cần thiết.

# \- Khi nghi ngờ lộ khóa, thay khóa và token ngay.

# \- Google Sheets là nguồn dữ liệu nghiệp vụ; không chuyển dữ liệu nghiệp vụ sang biến môi trường.

# 

# \## 17. Quy trình sửa lỗi

# 

# 1\. Ghi nhận câu hỏi và kết quả sai.

# 2\. Kiểm tra log và nguồn định tuyến.

# 3\. Xác định file và hàm liên quan.

# 4\. Khoanh đúng vùng code cần vá.

# 5\. Không thay đổi cấu trúc hoặc nghiệp vụ ngoài phạm vi lỗi.

# 6\. Thêm hoặc cập nhật bài test hồi quy.

# 7\. Chạy toàn bộ test.

# 8\. Chỉ deploy khi test đạt.

# 9\. Kiểm tra lại trên Zalo OA.

# 10\. Ghi nhận kết quả triển khai.

# 

# \## 18. Xử lý lỗi thường gặp

# 

# \### Thiếu `GOOGLE\\\_SHEET\\\_ID`

# 

# Kiểm tra biến môi trường:

# 

# ```text

# GOOGLE\_SHEET\_ID

# ```

# 

# Không chạy test hồi quy bằng dữ liệu thật. Các test router phải monkeypatch toàn bộ nguồn Google Sheets liên quan.

# 

# \### Không đọc được credentials Google

# 

# Kiểm tra một trong hai biến:

# 

# ```text

# GOOGLE\_CREDENTIALS\_JSON

# GOOGLE\_CREDENTIALS\_FILE

# ```

# 

# Khi dùng JSON trên Render, kiểm tra nội dung còn nguyên định dạng và Service Account đã được chia sẻ quyền trên Google Sheets.

# 

# \### `/test-ai` hoặc `/api/chat` trả `401`

# 

# Kiểm tra header:

# 

# ```text

# X-Internal-API-Key

# ```

# 

# Giá trị phải trùng `INTERNAL\\\_API\\\_KEY`.

# 

# \### Zalo không nhận câu trả lời

# 

# Kiểm tra:

# 

# \- `ZALO\\\_ACCESS\\\_TOKEN`.

# \- Kết quả gửi trong log `ZALO\\\_SEND`.

# \- Webhook Zalo.

# \- `event\\\_name=user\\\_send\\\_text`.

# \- `sender.id`.

# \- `message.text`.

# 

# \### Test báo đọc `SETTING\\\_CHAT` thật

# 

# Bài test cần monkeypatch đúng đối tượng mà `router\\\_service` đang gọi, đặc biệt là hàm định dạng thủ tục. Không để test hồi quy phụ thuộc Google Sheets thật.

# 

# \## 19. Checklist trước deploy

# 

# \- \[ ] `python -m pytest -v tests/test\\\_core.py` đạt toàn bộ.

# \- \[ ] Không có token hoặc credentials trong Git.

# \- \[ ] `INTERNAL\\\_API\\\_KEY` đã cấu hình.

# \- \[ ] `GOOGLE\\\_SHEET\\\_ID` đã cấu hình.

# \- \[ ] `GOOGLE\\\_CREDENTIALS\\\_JSON` hợp lệ.

# \- \[ ] `ZALO\\\_ACCESS\\\_TOKEN` hợp lệ.

# \- \[ ] `/` trả `200`.

# \- \[ ] `/health` trả trạng thái phù hợp.

# \- \[ ] Webhook GET trả `Webhook OK`.

# \- \[ ] Tin nhắn `menu` hoạt động.

# \- \[ ] Tra cứu thủ tục hoạt động.

# \- \[ ] Tra cứu liên hệ hoạt động.

# \- \[ ] Câu hỏi nối tiếp giữ đúng context.

# \- \[ ] Câu nêu thủ tục mới ghi đè context cũ.

# \- \[ ] Tin nhắn dài được gửi đủ các phần.

# \- \[ ] Không phát sinh hai câu trả lời cho một webhook.

# 

# \## 20. Trạng thái hiện tại

# 

# \- Kiến trúc Google Sheets trung tâm: hoàn thành.

# \- AI Optional và `STRICT\\\_SHEET\\\_ONLY`: hoàn thành.

# \- Cache và health check: hoàn thành.

# \- Session và chống webhook trùng: hoàn thành.

# \- Chia tin nhắn dài: hoàn thành.

# \- Chuẩn hóa log: hoàn thành.

# \- Kiểm thử tự động và hồi quy: hoàn thành.

# \- Tách tiện ích router sang `router\\\_utils.py`: hoàn thành.

# \- Bộ test hiện tại: `21 passed`.

# \- Chuẩn hóa deploy và checklist bàn giao: hoàn thành về mã nguồn và tài liệu.

# \- Tiến độ hoàn thiện hệ thống: `25/25 bước` sau khi xác nhận deploy Render và câu test Zalo cuối cùng.

