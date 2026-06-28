"""
===========================================================
FILE: services/sheet_api.py
PROJECT : AI AGENT ZALO OA
AUTHOR  : ChatGPT
VERSION : 1.0
===========================================================

Chức năng:

- Kết nối Google Sheets
- Đọc dữ liệu từ các Sheet
- Ghi lịch sử chat
- Ghi log lỗi
- Cache dữ liệu
- Refresh dữ liệu tự động
- Hỗ trợ tìm kiếm nhanh
- Là tầng truy xuất dữ liệu duy nhất của Bot

"""

from __future__ import annotations

import os
import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

import gspread
from google.oauth2.service_account import Credentials

# ==========================================================
# HẰNG SỐ
# ==========================================================

# Scope truy cập Google Sheets
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# ==========================================================
# SYSTEM SHEETS
# ==========================================================

MENU_SHEET = "MENU"

SETTING_SYSTEM_SHEET = "SETTING_SYSTEM"

SETTING_AI_SHEET = "SETTING_AI"

SETTING_CHAT_SHEET = "SETTING_CHAT"

PROMPT_SHEET = "PROMPT"

THONGTIN_SHEET = "THONGTIN"

FAQ_SHEET = "FAQ"

CONTACT_SHEET = "TRA_CUU_LIEN_HE"

CHAT_HISTORY_SHEET = "LICH_SU_CHAT"

ERROR_LOG_SHEET = "LOG_ERROR"

# ==========================================================
# PROCEDURE SHEETS
# ==========================================================

PROCEDURE_SHEETS = {

    "ANTT": "THU_TUC_ANTT",

    "CCCD": "THU_TUC_CCCD",

    "CUTRU": "THU_TUC_CUTRU",

    "VNEID": "THU_TUC_VNEID",

    "LLTP": "THU_TUC_LLTP",

    "PTGT": "THU_TUC_PTGT",

    "PCCC": "THU_TUC_PCCC",

    "VKVLN": "THU_TUC_VKVLN"

}

# ==========================================================
# CACHE
# ==========================================================

CACHE_EXPIRE_SECONDS = 300

# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger("sheet_api")

logger.setLevel(logging.INFO)

# ==========================================================
# CLASS
# ==========================================================

class SheetAPI:
    """
    =======================================================
    Lớp quản lý toàn bộ việc làm việc với Google Sheets.

    Chỉ module này được phép:

        - mở Spreadsheet
        - đọc Sheet
        - ghi Sheet
        - cache dữ liệu
        - refresh cache

    Những module khác tuyệt đối không gọi gspread trực tiếp.
    =======================================================
    """

    def __init__(
        self,
        spreadsheet_id: str,
        credentials_file: str = "credentials.json",
        cache_seconds: int = CACHE_EXPIRE_SECONDS
    ):

        # ----------------------------------------------
        # Thông tin Spreadsheet
        # ----------------------------------------------

        self.spreadsheet_id = spreadsheet_id

        self.credentials_file = credentials_file

        self.cache_seconds = cache_seconds

        # ----------------------------------------------
        # Đối tượng Google
        # ----------------------------------------------

        self.gc = None

        self.spreadsheet = None

        # ----------------------------------------------
        # Cache dữ liệu
        # ----------------------------------------------

        self.cache: Dict[str, Any] = {}

        self.cache_time: Dict[str, float] = {}

        # ----------------------------------------------
        # Trạng thái
        # ----------------------------------------------

        self.connected = False

        self.last_refresh = None

        self.version = "1.0"

        logger.info("SheetAPI initialized")

    # =====================================================
    # Các phương thức sẽ được xây dựng ở các phần tiếp theo:
    #
    # connect()
    # get_sheet()
    # read_menu()
    # read_faq()
    # read_thu_tuc()
    # read_prompt()
    # append_chat_history()
    # append_error_log()
    # refresh_cache()
    # clear_cache()
    # search()
    # close()
    # =====================================================
      # =====================================================
    # KẾT NỐI GOOGLE SHEETS
    # =====================================================

    def connect(self) -> bool:
        """
        Kết nối Google Sheets bằng Service Account.

        Returns:
            bool:
                True  -> Kết nối thành công
                False -> Kết nối thất bại
        """

        try:

            logger.info("Connecting to Google Sheets...")

            # ------------------------------------------
            # Kiểm tra file credentials
            # ------------------------------------------

            if not os.path.exists(self.credentials_file):
                raise FileNotFoundError(
                    f"Không tìm thấy file: {self.credentials_file}"
                )

            # ------------------------------------------
            # Xác thực
            # ------------------------------------------

            credentials = Credentials.from_service_account_file(
                self.credentials_file,
                scopes=SCOPES
            )

            self.gc = gspread.authorize(credentials)

            # ------------------------------------------
            # Mở Spreadsheet
            # ------------------------------------------

            self.spreadsheet = self.gc.open_by_key(
                self.spreadsheet_id
            )

            self.connected = True

            self.last_refresh = datetime.now()

            logger.info(
                "Connected successfully: %s",
                self.spreadsheet.title
            )

            return True

        except Exception as e:

            logger.exception("Google Sheets connection failed")

            self.connected = False

            self.gc = None

            self.spreadsheet = None

            raise RuntimeError(
                f"Không thể kết nối Google Sheets: {e}"
            )

    # =====================================================
    # KIỂM TRA KẾT NỐI
    # =====================================================

    def is_connected(self) -> bool:
        """
        Kiểm tra trạng thái kết nối.
        """

        return (
            self.connected
            and self.gc is not None
            and self.spreadsheet is not None
        )

    # =====================================================
    # LẤY ĐỐI TƯỢNG SPREADSHEET
    # =====================================================

    def get_spreadsheet(self):
        """
        Trả về đối tượng Spreadsheet.
        """

        if not self.is_connected():
            self.connect()

        return self.spreadsheet

    # =====================================================
    # LẤY WORKSHEET
    # =====================================================

    def get_sheet(self, sheet_name: str):
        """
        Lấy Worksheet theo tên.

        Args:
            sheet_name (str):
                Tên Sheet.

        Returns:
            Worksheet
        """

        if not self.is_connected():
            self.connect()

        try:

            worksheet = self.spreadsheet.worksheet(
                sheet_name
            )

            return worksheet

        except gspread.WorksheetNotFound:

            logger.error(
                "Worksheet '%s' không tồn tại.",
                sheet_name
            )

            raise

    # =====================================================
    # KIỂM TRA SHEET TỒN TẠI
    # =====================================================

    def sheet_exists(self, sheet_name: str) -> bool:
        """
        Kiểm tra Sheet có tồn tại hay không.
        """

        try:

            self.get_sheet(sheet_name)

            return True

        except Exception:

            return False

    # =====================================================
    # DANH SÁCH TẤT CẢ SHEET
    # =====================================================

    def list_sheets(self) -> List[str]:
        """
        Trả về danh sách tên tất cả các Sheet.
        """

        if not self.is_connected():
            self.connect()

        return [
            ws.title
            for ws in self.spreadsheet.worksheets()
        ]

    # =====================================================
    # ĐÓNG KẾT NỐI (RESET)
    # =====================================================

    def disconnect(self):
        """
        Reset trạng thái kết nối.
        """

        self.gc = None

        self.spreadsheet = None

        self.connected = False

        logger.info("Disconnected Google Sheets.")
          # =====================================================
    # CACHE
    # =====================================================

    def _is_cache_valid(self, cache_key: str) -> bool:
        """
        Kiểm tra cache còn hiệu lực hay không.
        """

        if cache_key not in self.cache:
            return False

        if cache_key not in self.cache_time:
            return False

        age = time.time() - self.cache_time[cache_key]

        return age < self.cache_seconds


    def _save_cache(self, cache_key: str, data: Any):
        """
        Lưu dữ liệu vào cache.
        """

        self.cache[cache_key] = data
        self.cache_time[cache_key] = time.time()


    def _get_cache(self, cache_key: str):

        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]

        return None


    # =====================================================
    # MENU
    # =====================================================

    def read_menu(
        self,
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Đọc toàn bộ Sheet MENU.

        Trả về:
            [
                {
                    "ID": "1",
                    "TEN": "Làm CCCD",
                    "TU_KHOA": "...",
                    "TRA_LOI": "...",
                    ...
                }
            ]
        """

        cache_key = "MENU"

        # ----------------------------------------------
        # Đọc từ cache
        # ----------------------------------------------

        if not force_refresh:

            cache = self._get_cache(cache_key)

            if cache is not None:

                logger.info("MENU loaded from cache")

                return cache

        # ----------------------------------------------
        # Đọc Google Sheets
        # ----------------------------------------------

        worksheet = self.get_sheet(MENU_SHEET)

        records = worksheet.get_all_records()

        menus = []

        for row in records:

            item = {}

            for key, value in row.items():

                if isinstance(value, str):

                    value = value.strip()

                item[str(key).strip()] = value

            menus.append(item)

        self._save_cache(cache_key, menus)

        logger.info(
            "Loaded %d MENU records",
            len(menus)
        )

        return menus


    # =====================================================
    # MENU THEO ID
    # =====================================================

    def get_menu_by_id(
        self,
        menu_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Tìm menu theo ID.
        """

        menus = self.read_menu()

        menu_id = str(menu_id).strip()

        for item in menus:

            if str(item.get("ID", "")).strip() == menu_id:

                return item

        return None


    # =====================================================
    # MENU THEO TÊN
    # =====================================================

    def get_menu_by_name(
        self,
        name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Tìm menu theo tên.
        """

        menus = self.read_menu()

        keyword = name.lower().strip()

        for item in menus:

            menu_name = str(
                item.get("TEN", "")
            ).lower()

            if menu_name == keyword:

                return item

        return None


    # =====================================================
    # TÌM MENU THEO TỪ KHÓA
    # =====================================================

    def search_menu(
        self,
        keyword: str
    ) -> List[Dict[str, Any]]:
        """
        Tìm kiếm menu theo từ khóa.
        """

        keyword = keyword.lower().strip()

        results = []

        for item in self.read_menu():

            text = json.dumps(
                item,
                ensure_ascii=False
            ).lower()

            if keyword in text:

                results.append(item)

        logger.info(
            "MENU search '%s' -> %d results",
            keyword,
            len(results)
        )

        return results
          # =====================================================
    # FAQ
    # =====================================================

    def read_faq(
        self,
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Đọc toàn bộ dữ liệu từ Sheet FAQ.

        Returns:
            List[Dict]:
                Danh sách các câu hỏi thường gặp.
        """

        cache_key = "FAQ"

        # ----------------------------------------------
        # Đọc từ cache
        # ----------------------------------------------

        if not force_refresh:

            cache = self._get_cache(cache_key)

            if cache is not None:

                logger.info("FAQ loaded from cache")

                return cache

        # ----------------------------------------------
        # Đọc Google Sheets
        # ----------------------------------------------

        worksheet = self.get_sheet(FAQ_SHEET)

        records = worksheet.get_all_records()

        faqs = []

        for row in records:

            item = {}

            for key, value in row.items():

                if isinstance(value, str):
                    value = value.strip()

                item[str(key).strip()] = value

            faqs.append(item)

        self._save_cache(cache_key, faqs)

        logger.info(
            "Loaded %d FAQ records",
            len(faqs)
        )

        return faqs

    # =====================================================
    # FAQ THEO ID
    # =====================================================

    def get_faq_by_id(
        self,
        faq_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Tìm FAQ theo ID.
        """

        faq_id = str(faq_id).strip()

        for item in self.read_faq():

            if str(item.get("ID", "")).strip() == faq_id:
                return item

        return None

    # =====================================================
    # FAQ THEO TỪ KHÓA
    # =====================================================

    def search_faq(
        self,
        keyword: str
    ) -> List[Dict[str, Any]]:
        """
        Tìm FAQ theo từ khóa.

        Tìm trong:
        - CÂU_HỎI
        - TỪ_KHÓA
        - TRẢ_LỜI
        """

        keyword = keyword.lower().strip()

        results = []

        for item in self.read_faq():

            question = str(
                item.get("CAU_HOI", "")
            ).lower()

            keywords = str(
                item.get("TU_KHOA", "")
            ).lower()

            answer = str(
                item.get("TRA_LOI", "")
            ).lower()

            if (
                keyword in question
                or keyword in keywords
                or keyword in answer
            ):
                results.append(item)

        logger.info(
            "FAQ search '%s' -> %d results",
            keyword,
            len(results)
        )

        return results

    # =====================================================
    # FAQ KHỚP NHẤT
    # =====================================================

    def find_best_faq(
        self,
        question: str
    ) -> Optional[Dict[str, Any]]:
        """
        Tìm bản ghi FAQ phù hợp nhất bằng so khớp đơn giản.
        """

        question = question.lower().strip()

        best_item = None
        best_score = 0

        for item in self.read_faq():

            score = 0

            question_text = str(
                item.get("CAU_HOI", "")
            ).lower()

            keyword_text = str(
                item.get("TU_KHOA", "")
            ).lower()

            if question in question_text:
                score += 10

            if question in keyword_text:
                score += 8

            for word in question.split():

                if len(word) < 2:
                    continue

                if word in question_text:
                    score += 2

                if word in keyword_text:
                    score += 1

            if score > best_score:

                best_score = score
                best_item = item

        if best_item:

            logger.info(
                "Best FAQ score: %d",
                best_score
            )

        return best_item

    # =====================================================
    # LẤY TOÀN BỘ TỪ KHÓA FAQ
    # =====================================================

    def get_all_faq_keywords(self) -> List[str]:
        """
        Trả về danh sách toàn bộ từ khóa trong Sheet FAQ.
        """

        keywords = []

        for item in self.read_faq():

            value = str(
                item.get("TU_KHOA", "")
            )

            for keyword in value.split(","):

                keyword = keyword.strip()

                if keyword:
                    keywords.append(keyword)

        return sorted(set(keywords))
      
