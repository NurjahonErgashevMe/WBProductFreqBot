import logging
import os
from aiogram import Bot
from src.config.settings import settings

class LogService:
    def __init__(self, bot: Bot):
        self.bot = bot
        os.makedirs(settings.LOG_DIR, exist_ok=True)
        log_file = os.path.join(settings.LOG_DIR, "wb_parser.log")
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ],
        )
        self.logger = logging.getLogger(__name__)
        self.log_messages = {}  # Для хранения message_id и логов в Telegram

    async def log_to_file(self, message: str, level: str = "info"):
        """Логирование в файл"""
        if level == "info":
            self.logger.info(message)
        elif level == "error":
            self.logger.error(message)
        elif level == "warning":
            self.logger.warning(message)

    async def update_log_message(self, user_id: int, log_message: str):
        """Обновление логов в Telegram"""
        await self.log_to_file(log_message, "info")
        if user_id not in self.log_messages:
            message = await self.bot.send_message(user_id, f"📄 *Логи парсинга:*\n{log_message}", parse_mode="Markdown")
            self.log_messages[user_id] = {'message_id': message.message_id, 'text': [log_message]}
        else:
            current_logs = self.log_messages[user_id]['text']
            current_logs.append(log_message)
            new_text = "📄 *Логи парсинга:*\n" + "\n".join(current_logs)  # Ограничение на 10 строк
            try:
                await self.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=self.log_messages[user_id]['message_id'],
                    text=new_text,
                    parse_mode="Markdown"
                )
                self.log_messages[user_id]['text'] = current_logs
            except Exception as e:
                await self.log_to_file(f"Failed to update log message for user {user_id}: {e}", "error")

    async def clear_log_messages(self, user_id: int):
        """Очистка логов в Telegram"""
        if user_id in self.log_messages:
            del self.log_messages[user_id]