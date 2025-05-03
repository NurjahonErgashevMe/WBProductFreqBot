import os
import json
import asyncio
import pandas as pd
from aiogram import Bot
from aiogram import types
import datetime
from src.config.settings import settings

class FileService:
    def __init__(self, bot: Bot, log_service):
        self.bot = bot
        self.log_service = log_service
        os.makedirs(settings.OUTPUT_DIR, exist_ok=True)

    async def save_to_json(self, data: dict, path: str = settings.EVIRMA_JSON_PATH):
        """Сохранение данных в JSON"""
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            await self.log_service.log_to_file(f"Saved JSON to {path}", "info")
        except Exception as e:
            await self.log_service.log_to_file(f"Error saving JSON: {e}", "error")

    async def save_to_excel(self, data: list, filename: str):
        """Сохранение данных в Excel"""
        if not data:
            await self.log_service.log_to_file("No data to save to Excel", "warning")
            return None

        df = pd.DataFrame(data)
        file_path = os.path.join(settings.OUTPUT_DIR, f'{filename}.xlsx')
        try:
            with pd.ExcelWriter(file_path, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='data', index=False)
                worksheet = writer.sheets['data']
                worksheet.set_column('A:A', 50)
                worksheet.set_column('B:B', 25)
                worksheet.set_column('C:C', 25)
            await self.log_service.log_to_file(f"Saved Excel to {file_path}", "info")
            return file_path
        except Exception as e:
            await self.log_service.log_to_file(f"Error saving Excel: {e}", "error")
            return None

    async def send_excel_to_user(self, file_path: str, filename: str, user_id: int):
        """Отправка Excel-файла пользователю с последующим удалением"""
        if not os.path.exists(file_path):
            await self.bot.send_message(user_id, f"❌ Файл отчета {file_path} не найден!", parse_mode="Markdown")
            await self.log_service.log_to_file(f"Excel file not found: {file_path}", "error")
            return

        today = datetime.datetime.now().strftime("%d.%m.%Y")
        caption = f"📊 *Анализ категории Wildberries* ({today})"
        try:
            with open(file_path, "rb") as file:
                await self.bot.send_document(
                    user_id,
                    types.InputFile(file, f'{filename}.xlsx'),
                    caption=caption,
                    parse_mode="Markdown"
                )
            await self.log_service.log_to_file(f"Excel report sent to user {user_id}: {file_path}", "info")
            asyncio.create_task(self.delete_file_after_delay(file_path))
        except Exception as e:
            await self.log_service.log_to_file(f"Failed to send Excel to user {user_id}: {e}", "error")

    async def delete_file_after_delay(self, file_path: str):
        """Удаление файла через 15 секунд"""
        await asyncio.sleep(settings.FILE_DELETE_DELAY)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                await self.log_service.log_to_file(f"File deleted: {file_path}", "info")
            else:
                await self.log_service.log_to_file(f"File not found for deletion: {file_path}", "warning")
        except Exception as e:
            await self.log_service.log_to_file(f"Failed to delete file {file_path}: {e}", "error")