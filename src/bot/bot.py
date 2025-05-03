from aiogram import Bot, Dispatcher
from aiogram.utils import executor
from src.config.settings import settings
from src.services.log_service import LogService
from src.services.file_service import FileService
from src.parser.evirma import EvirmaClient
from src.parser.wildberries import WildberriesParser
from src.bot.handlers import BotHandlers

class WBCategoriesBot:
    def __init__(self):
        self.bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        self.dp = Dispatcher(self.bot)
        self.log_service = LogService(self.bot)
        self.file_service = FileService(self.bot, self.log_service)
        self.evirma_client = EvirmaClient(self.file_service)
        self.parser = WildberriesParser(self.file_service, self.evirma_client, self.log_service)
        self.handlers = BotHandlers(self.dp, self.bot, self.parser, self.log_service)

    async def on_startup(self, _):
        await self.log_service.log_to_file("Bot starting up...", "info")
        for admin_id in settings.ADMIN_IDS:
            try:
                await self.bot.send_message(
                    admin_id,
                    "🤖 *Бот запущен и готов к работе!*\n"
                    f"Ваш ID: {admin_id}\n"
                    "Используйте /start для начала работы.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                await self.log_service.log_to_file(f"Failed to notify admin {admin_id}: {e}", "error")

    async def on_shutdown(self, _):
        await self.log_service.log_to_file("Bot shutting down...", "info")
        await self.bot.close()

    def run(self):
        executor.start_polling(
            self.dp,
            skip_updates=True,
            on_startup=self.on_startup,
            on_shutdown=self.on_shutdown
        )