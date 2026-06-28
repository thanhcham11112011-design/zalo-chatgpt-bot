import os
import json
import time
import re
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


SYSTEM_SHEETS = {
    "MENU",
    "SETTING_SYSTEM",
    "SETTING_AI",
    "SETTING_CHAT",
    "PROMPT",
    "THONGTIN",
    "FAQ",
    "TRA_CUU_LIEN_HE",
    "LICH_SU_CHAT",
}


def normalize_text(text):
    text = str(text or "").lower().strip()
    text = text.replace("đ", "d")
    text = re.sub(r"\s+", " ", text)
    return text


def split_keywords(value):
    if not value:
        return []

    parts = re.split(r"[,;|\n]+", str(value))

    return [
        normalize_text(x)
        for x in parts
        if normalize_text(x)
    ]


class SheetAPI:
    def __init__(self, sheet_id=None, credentials_file=None, cache_seconds=300):
        self.sheet_id = sheet_id or os.getenv("GOOGLE_SHEET_ID")
        self.credentials_file = credentials_file or os.getenv(
            "GOOGLE_CREDENTIALS_FILE",
            "credentials.json"
        )

        self.cache_seconds = cache_seconds
        self.client = None
        self.spreadsheet = None
        self.cache = {}
        self.cache_time = {}

    def connect(self):
        if self.spreadsheet:
            return self.spreadsheet

        credentials = Credentials.from_service_account_file(
            self.credentials_file,
            scopes=SCOPES
        )

        self.client = gspread.authorize(credentials)
        self.spreadsheet = self.client.open_by_key(self.sheet_id)

        return self.spreadsheet

    def get_sheet(self, sheet_name):
        self.connect()
        return self.spreadsheet.worksheet(sheet_name)

    def is_cache_valid(self, key):
        if key not in self.cache:
            return False

        last_time = self.cache_time.get(key, 0)

        return time.time() - last_time < self.cache_seconds

    def read_sheet(self, sheet_name, force_refresh=False):
        if not force_refresh and self.is_cache_valid(sheet_name):
            return self.cache.get(sheet_name, [])

        try:
            worksheet = self.get_sheet(sheet_name)
            rows = worksheet.get_all_records()

            data = []

            for row in rows:
                clean = {}

                for key, value in row.items():
                    clean_key = str(key).strip()
                    clean_value = value.strip() if isinstance(value, str) else value
                    clean[clean_key] = clean_value

                clean["_SOURCE_SHEET"] = sheet_name
                data.append(clean)

            self.cache[sheet_name] = data
            self.cache_time[sheet_name] = time.time()

            return data

        except Exception as e:
            print(f"SHEET READ ERROR [{sheet_name}]:", e)
            return []

    def read_menu(self):
        return self.read_sheet("MENU")

    def read_faq(self):
        return self.read_sheet("FAQ")

    def read_thongtin(self):
        return self.read_sheet("THONGTIN")

    def read_contacts(self):
        return self.read_sheet("TRA_CUU_LIEN_HE")

    def get_menu_sheet_name(self, row):
        possible_columns = [
            "Sheet dữ liệu",
            "SHEET_DU_LIEU",
            "SHEET",
            "SHEET_NAME",
            "TEN_SHEET",
            "Sheet",
            "sheet"
        ]

        for col in possible_columns:
            value = row.get(col)
            if value:
                return str(value).strip()

        return ""

    def get_menu_title(self, row):
        possible_columns = [
            "Tên chức năng",
            "TEN_CHUC_NANG",
            "TEN",
            "TIEU_DE",
            "CHU_DE",
            "Mô tả",
            "MO_TA"
        ]

        for col in possible_columns:
            value = row.get(col)
            if value:
                return str(value).strip()

        return ""

    def get_menu_keywords(self, row):
        possible_columns = [
            "Từ khóa",
            "TU_KHOA",
            "KEYWORDS",
            "Tu khoa",
            "tu_khoa"
        ]

        keywords = []

        for col in possible_columns:
            value = row.get(col)
            keywords.extend(split_keywords(value))

        title = self.get_menu_title(row)

        if title:
            keywords.append(normalize_text(title))

        return list(set(keywords))

    def get_dynamic_data_sheets(self):
        menu_rows = self.read_menu()
        sheets = []

        for row in menu_rows:
            sheet_name = self.get_menu_sheet_name(row)

            if sheet_name and sheet_name not in sheets:
                sheets.append(sheet_name)

        return sheets

    def get_sheet_by_menu_number(self, question):
        q = normalize_text(question)

        if not q.isdigit():
            return ""

        menu_rows = self.read_menu()
        index = int(q) - 1

        if index < 0 or index >= len(menu_rows):
            return ""

        return self.get_menu_sheet_name(menu_rows[index])

    def get_sheet_by_menu_keyword(self, question):
        q = normalize_text(question)

        menu_rows = self.read_menu()

        best_sheet = ""
        best_score = 0

        for row in menu_rows:
            sheet_name = self.get_menu_sheet_name(row)
            keywords = self.get_menu_keywords(row)

            score = 0

            for kw in keywords:
                if kw and kw in q:
                    score += 10

                if kw and q in kw:
                    score += 5

            title = normalize_text(self.get_menu_title(row))

            if title and title in q:
                score += 10

            if score > best_score:
                best_score = score
                best_sheet = sheet_name

        if best_score > 0:
            return best_sheet

        return ""

    def read_dynamic_knowledge(self):
        if self.is_cache_valid("_DYNAMIC_KNOWLEDGE"):
            return self.cache.get("_DYNAMIC_KNOWLEDGE", [])

        all_rows = []

        for sheet_name in self.get_dynamic_data_sheets():
            rows = self.read_sheet(sheet_name)

            for row in rows:
                row["_SOURCE_SHEET"] = sheet_name
                all_rows.append(row)

        faq_rows = self.read_faq()
        for row in faq_rows:
            row["_SOURCE_SHEET"] = "FAQ"
            all_rows.append(row)

        thongtin_rows = self.read_thongtin()
        for row in thongtin_rows:
            row["_SOURCE_SHEET"] = "THONGTIN"
            all_rows.append(row)

        contact_rows = self.read_contacts()
        for row in contact_rows:
            row["_SOURCE_SHEET"] = "TRA_CUU_LIEN_HE"
            all_rows.append(row)

        self.cache["_DYNAMIC_KNOWLEDGE"] = all_rows
        self.cache_time["_DYNAMIC_KNOWLEDGE"] = time.time()

        return all_rows

    def score_row(self, question, row):
        q = normalize_text(question)

        score = 0

        priority_fields = {
            "TU_KHOA": 30,
            "Từ khóa": 30,
            "TEN_THU_TUC": 25,
            "Tên thủ tục": 25,
            "CHU_DE": 20,
            "Chủ đề": 20,
            "GOI_Y_CAU_HOI": 15,
            "FAQ": 15,
            "TRA_LOI_NGAN": 10,
            "TRA_LOI_DAY_DU": 8,
            "MO_TA": 8,
            "Mô tả": 8,
        }

        for field, weight in priority_fields.items():
            value = normalize_text(row.get(field, ""))

            if not value:
                continue

            if q and q in value:
                score += weight

            for word in q.split():
                if len(word) >= 2 and word in value:
                    score += max(1, weight // 5)

        keywords = split_keywords(
            row.get("TU_KHOA")
            or row.get("Từ khóa")
            or ""
        )

        for kw in keywords:
            if kw and kw in q:
                score += 30

            if kw and q in kw:
                score += 15

        all_text = normalize_text(
            json.dumps(row, ensure_ascii=False)
        )

        if q and q in all_text:
            score += 5

        return score

    def search_in_sheet(self, question, sheet_name, limit=5):
        rows = self.read_sheet(sheet_name)
        results = []

        for row in rows:
            score = self.score_row(question, row)

            if score > 0:
                results.append({
                    "score": score,
                    "data": row
                })

        results.sort(key=lambda x: x["score"], reverse=True)

        return [x["data"] for x in results[:limit]]

    def search(self, question, limit=5):
        q = normalize_text(question)

        if not q:
            return []

        target_sheet = self.get_sheet_by_menu_number(q)

        if not target_sheet:
            target_sheet = self.get_sheet_by_menu_keyword(q)

        if target_sheet:
            results = self.search_in_sheet(
                question=question,
                sheet_name=target_sheet,
                limit=limit
            )

            if results:
                return results

            rows = self.read_sheet(target_sheet)

            if rows:
                return rows[:limit]

        all_rows = self.read_dynamic_knowledge()

        results = []

        for row in all_rows:
            score = self.score_row(question, row)

            if score > 0:
                results.append({
                    "score": score,
                    "data": row
                })

        results.sort(key=lambda x: x["score"], reverse=True)

        return [x["data"] for x in results[:limit]]

    def append_chat_history(self, user_id, user_message, bot_reply):
        try:
            worksheet = self.get_sheet("LICH_SU_CHAT")

            worksheet.append_row([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                user_id,
                user_message,
                bot_reply
            ])

            return True

        except Exception as e:
            print("CHAT HISTORY ERROR:", e)
            return False


sheet_api = SheetAPI()
