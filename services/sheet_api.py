import os
import json
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

PROCEDURE_SHEETS = [
    "THU_TUC_ANTT",
    "THU_TUC_CCCD",
    "THU_TUC_CUTRU",
    "THU_TUC_VNEID",
    "THU_TUC_LLTP",
    "THU_TUC_PTGT",
    "THU_TUC_PCCC",
    "THU_TUC_VKVLN",
]


class SheetAPI:
    def __init__(self, sheet_id=None, credentials_file=None):
        self.sheet_id = sheet_id or os.getenv("GOOGLE_SHEET_ID")
        self.credentials_file = credentials_file or os.getenv(
            "GOOGLE_CREDENTIALS_FILE",
            "credentials.json"
        )
        self.client = None
        self.spreadsheet = None

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

    def read_sheet(self, sheet_name):
        try:
            worksheet = self.get_sheet(sheet_name)
            rows = worksheet.get_all_records()

            data = []
            for row in rows:
                clean_row = {}
                for key, value in row.items():
                    clean_key = str(key).strip()
                    clean_value = value.strip() if isinstance(value, str) else value
                    clean_row[clean_key] = clean_value
                data.append(clean_row)

            return data

        except Exception as e:
            print(f"Lỗi đọc sheet {sheet_name}: {e}")
            return []

    def read_menu(self):
        return self.read_sheet("MENU")

    def read_faq(self):
        return self.read_sheet("FAQ")

    def read_thongtin(self):
        return self.read_sheet("THONGTIN")

    def read_prompts(self):
        return self.read_sheet("PROMPT")

    def read_contacts(self):
        return self.read_sheet("TRA_CUU_LIEN_HE")

    def read_all_procedures(self):
        all_data = []

        for sheet_name in PROCEDURE_SHEETS:
            rows = self.read_sheet(sheet_name)

            for row in rows:
                row["SOURCE_SHEET"] = sheet_name
                all_data.append(row)

        return all_data

    def search(self, question, limit=5):
        question = question.lower().strip()
        results = []

        sources = []
        sources.extend(self.read_faq())
        sources.extend(self.read_all_procedures())
        sources.extend(self.read_thongtin())

        for row in sources:
            text = json.dumps(row, ensure_ascii=False).lower()

            score = 0
            for word in question.split():
                if len(word) >= 2 and word in text:
                    score += 1

            if question in text:
                score += 10

            if score > 0:
                results.append({
                    "score": score,
                    "data": row
                })

        results.sort(key=lambda x: x["score"], reverse=True)

        return [item["data"] for item in results[:limit]]

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
            print(f"Lỗi ghi LICH_SU_CHAT: {e}")
            return False


sheet_api = SheetAPI()
