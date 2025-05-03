from aiogram import types, Dispatcher
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import re
from src.config.settings import settings

class BotHandlers:
    def __init__(self, dp: Dispatcher, bot, parser, log_service):
        self.dp = dp
        self.bot = bot
        self.parser = parser
        self.log_service = log_service
        self.waiting_for_url = {}

        # Регистрация обработчиков
        self.dp.register_message_handler(self.start, commands=["start"], user_id=settings.ADMIN_IDS)
        self.dp.register_message_handler(self.list_admins, commands=["list"], user_id=settings.ADMIN_IDS)
        self.dp.register_message_handler(self.manual_parse, commands=["parse"], user_id=settings.ADMIN_IDS)
        self.dp.register_message_handler(self.handle_text, user_id=settings.ADMIN_IDS)
        self.dp.register_message_handler(self.unauthorized_access)

    def get_main_menu(self, user_id: int) -> ReplyKeyboardMarkup:
        """Создание главного меню"""
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        keyboard.add(KeyboardButton("Парсить"))
        if user_id in settings.ADMIN_IDS:
            keyboard.add(KeyboardButton("Список подписчиков"))
        return keyboard

    def get_url_input_menu(self) -> ReplyKeyboardMarkup:
        """Создание меню для ввода URL"""
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        keyboard.add(KeyboardButton("Отмена"))
        return keyboard

    async def start(self, message: types.Message):
        """Обработчик команды /start"""
        user_id = message.from_user.id
        welcome_text = (
            "🛍️ *Wildberries Categories Analyzer Bot*\n\n"
            "Этот бот анализирует категории Wildberries и предоставляет статистику.\n\n"
            "Доступные команды:\n"
            "/parse - Запросить анализ категории\n"
            "/list - Показать список админов (только для админов)"
        )
        await message.answer(welcome_text, parse_mode="Markdown", reply_markup=self.get_main_menu(user_id))

    async def list_admins(self, message: types.Message):
        """Показать список админов"""
        admins = "\n".join([f"- {admin_id}" for admin_id in settings.ADMIN_IDS])
        await message.answer(f"📋 Список админов:\n{admins}", reply_markup=self.get_main_menu(message.from_user.id))

    async def manual_parse(self, message: types.Message):
        """Ручной запрос парсинга"""
        user_id = message.from_user.id
        self.waiting_for_url[user_id] = 'manual'
        await message.answer(
            "🔗 Пожалуйста, отправьте URL категории Wildberries в формате:\n"
            "https://www.wildberries.ru/catalog/<category>/<subcategory>/<subsubcategory>\n"
            "Например: https://www.wildberries.ru/catalog/dom-i-dacha/vannaya/aksessuary",
            parse_mode="Markdown",
            reply_markup=self.get_url_input_menu()
        )

    async def handle_text(self, message: types.Message):
        """Обработка текстовых сообщений"""
        user_id = message.from_user.id
        text = message.text.strip()

        if text == "Парсить":
            await self.manual_parse(message)
            return
        elif text == "Список подписчиков":
            await self.list_admins(message)
            return
        elif text == "Отмена" and user_id in self.waiting_for_url:
            del self.waiting_for_url[user_id]
            await message.answer(
                "❌ Ввод URL отменён.",
                parse_mode="Markdown",
                reply_markup=self.get_main_menu(user_id)
            )
            return

        if user_id in self.waiting_for_url:
            url = text
            url_pattern = r'^https://www\.wildberries\.ru/catalog/[\w-]+/[\w-]+/[\w-]+$'
            if not re.match(url_pattern, url):
                await message.answer(
                    "❌ Ошибка: URL некорректен. Пожалуйста, используйте формат:\n"
                    "https://www.wildberries.ru/catalog/<category>/<subcategory>/<subsubcategory>\n"
                    "Например: https://www.wildberries.ru/catalog/dom-i-dacha/vannaya/aksessuary\n\n"
                    "Попробуйте снова или нажмите 'Отмена'.",
                    parse_mode="Markdown",
                    reply_markup=self.get_url_input_menu()
                )
                return

            await message.answer("🔄 Запускаю анализ категории...", reply_markup=self.get_url_input_menu())
            success = await self.parser.parse_category(url, user_id)
            await self.log_service.clear_log_messages(user_id)
            if success:
                del self.waiting_for_url[user_id]
                await message.answer(
                    "✅ Парсинг завершён.",
                    parse_mode="Markdown",
                    reply_markup=self.get_main_menu(user_id)
                )
            else:
                await message.answer(
                    "❌ Ошибка: Категория не найдена или URL некорректен. Пожалуйста, используйте формат:\n"
                    "https://www.wildberries.ru/catalog/<category>/<subcategory>/<subsubcategory>\n"
                    "Например: https://www.wildberries.ru/catalog/dom-i-dacha/vannaya/aksessuary\n\n"
                    "Попробуйте снова или нажмите 'Отмена'.",
                    parse_mode="Markdown",
                    reply_markup=self.get_url_input_menu()
                )

    async def unauthorized_access(self, message: types.Message):
        """Обработчик для неавторизованных пользователей"""
        user_id = message.from_user.id
        await self.log_service.log_to_file(f"Unauthorized access attempt from user {user_id}", "warning")
        await message.answer("❌ У вас нет доступа к этому боту.", parse_mode="Markdown")