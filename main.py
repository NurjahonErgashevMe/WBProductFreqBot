import asyncio
import logging
import os
import sys
import re
from typing import List, Union
import time
import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from dotenv import load_dotenv
import requests

from wildberries import WildberriesEvirmaParser

# Загрузка переменных окружения
load_dotenv()

# Настройка кодировки для Windows
if sys.platform == "win32":
    import locale
    locale.setlocale(locale.LC_ALL, 'ru_RU.UTF-8')

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("wb_parser.log", encoding='utf-8'), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

class BotConfig:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.admin_ids = [int(id_) for id_ in os.getenv("ADMIN_ID").split(",")]  # Поддержка нескольких админов

class WBCategoriesBot:
    def __init__(self):
        self.config = BotConfig()
        self.bot = Bot(token=self.config.token)
        self.dp = Dispatcher(self.bot)
        self.parser = WildberriesEvirmaParser()
        self.waiting_for_url = {}  # Словарь для отслеживания пользователей, ожидающих ввода URL
        self.log_messages = {}  # Словарь для хранения message_id и текста логов для каждого пользователя

        # Регистрация обработчиков только для админов
        self.dp.register_message_handler(self.start, commands=["start"], user_id=self.config.admin_ids)
        self.dp.register_message_handler(self.list_admins, commands=["list"], user_id=self.config.admin_ids)
        self.dp.register_message_handler(self.manual_parse, commands=["parse"], user_id=self.config.admin_ids)
        self.dp.register_message_handler(self.handle_text, user_id=self.config.admin_ids)
        
        # Обработчик для всех остальных сообщений от неадминов
        self.dp.register_message_handler(self.unauthorized_access)

    async def unauthorized_access(self, message: types.Message):
        """Обработчик для неавторизованных пользователей"""
        user_id = message.from_user.id
        logger.warning(f"Unauthorized access attempt from user {user_id}")
        await message.answer("❌ У вас нет доступа к этому боту.", parse_mode="Markdown")

    def get_main_menu(self, user_id: int) -> ReplyKeyboardMarkup:
        """Создание главного меню с кнопками"""
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        keyboard.add(KeyboardButton("Парсить"))
        if user_id in self.config.admin_ids:
            keyboard.add(KeyboardButton("Список подписчиков"))
        return keyboard

    def get_url_input_menu(self) -> ReplyKeyboardMarkup:
        """Создание меню для ввода URL с кнопкой Отмена"""
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
        """Показать список админов (только для админов)"""
        admins = "\n".join([f"- {admin_id}" for admin_id in self.config.admin_ids])
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

        # Обработка ввода URL
        if user_id in self.waiting_for_url:
            url = text

            # Проверка формата URL
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
            success = await self.generate_and_send_report(user_id=user_id, category_url=url)
            if success:
                # Если парсинг успешен, выходим из режима ввода URL
                del self.waiting_for_url[user_id]
                await message.answer(
                    "✅ Парсинг завершён.",
                    parse_mode="Markdown",
                    reply_markup=self.get_main_menu(user_id)
                )
            else:
                # Если категория не найдена, продолжаем ожидать URL
                await message.answer(
                    "❌ Ошибка: Категория не найдена или URL некорректен. Пожалуйста, используйте формат:\n"
                    "https://www.wildberries.ru/catalog/<category>/<subcategory>/<subsubcategory>\n"
                    "Например: https://www.wildberries.ru/catalog/dom-i-dacha/vannaya/aksessuary\n\n"
                    "Попробуйте снова или нажмите 'Отмена'.",
                    parse_mode="Markdown",
                    reply_markup=self.get_url_input_menu()
                )

    async def send_status(self, text: str, user_id: int, markdown: bool = False):
        """
        Отправка статуса пользователю
        
        :param text: Текст сообщения
        :param user_id: ID пользователя
        :param markdown: Использовать ли Markdown
        """
        logger.info(f"Sending status to user {user_id}: {text}")
        try:
            if markdown or ("*" in text or "_" in text):
                await self.bot.send_message(user_id, text, parse_mode="Markdown")
            else:
                await self.bot.send_message(user_id, text)
        except Exception as e:
            logger.error(f"Failed to send status to user {user_id}: {e}")

    async def update_log_message(self, user_id: int, log_message: str):
        """
        Обновление сообщения с логами для пользователя
        
        :param user_id: ID пользователя
        :param log_message: Новая строка лога для добавления
        """
        if user_id not in self.log_messages:
            # Отправляем новое сообщение
            message = await self.bot.send_message(user_id, f"📄 *Логи парсинга:*\n{log_message}", parse_mode="Markdown")
            self.log_messages[user_id] = {'message_id': message.message_id, 'text': [log_message]}
        else:
            # Обновляем существующее сообщение
            current_logs = self.log_messages[user_id]['text']
            current_logs.append(log_message)
            new_text = "📄 *Логи парсинга:*\n" + "\n".join(current_logs)
            try:
                await self.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=self.log_messages[user_id]['message_id'],
                    text=new_text,
                    parse_mode="Markdown"
                )
                self.log_messages[user_id]['text'] = current_logs
            except Exception as e:
                logger.error(f"Failed to update log message for user {user_id}: {e}")

    async def clear_log_messages(self, user_id: int):
        """
        Очистка логов для указанного пользователя
        
        :param user_id: ID пользователя
        """
        if user_id in self.log_messages:
            del self.log_messages[user_id]

    async def generate_and_send_report(self, user_id: int, category_url: str) -> bool:
        """
        Генерация и отправка отчета
        
        :param user_id: ID пользователя, которому отправляется отчет
        :param category_url: URL категории для парсинга
        :return: True, если парсинг успешен, False, если категория не найдена
        """
        logger.info(f"Generating report for user {user_id}, category: {category_url}")
        
        try:
            # Статус: Начало работы
            await self.send_status("🟢 *Начинаем анализ категории*", user_id=user_id, markdown=True)

            # Сбрасываем результаты парсера перед новой категорией
            self.parser.results = []
            
            # Модифицированный парсинг с отправкой логов
            start_time = time.time()
            try:
                category = self.parser.find_category_by_url(category_url)
                if not category:
                    return False
                
                for page in range(1, self.parser.MAX_PAGES + 1):
                    wb_data, log_message = self.parser.scrape_wb_page(page=page, category=category)
                    await self.update_log_message(user_id, log_message)
                    
                    products = self.parser.process_products(wb_data)
                    if not products:
                        await self.send_status(
                            f"Страница {page}: товары не найдены, завершаем парсинг.",
                            user_id=user_id,
                            markdown=True
                        )
                        if self.parser.results:
                            filename = f"{category['name']}_analysis_{int(time.time())}"
                            self.parser.save_to_excel(filename)
                            await self.send_excel_to_user(filename, user_id)
                        break
                    
                    evirma_response = self.parser.query_evirma_api(products)
                    if evirma_response is None:
                        if self.parser.results:
                            filename = f"{category['name']}_analysis_{int(time.time())}"
                            self.parser.save_to_excel(filename)
                            await self.send_excel_to_user(filename, user_id)
                        else:
                            await self.send_status(
                                "Товары не найдены по заданным критериям.",
                                user_id=user_id,
                                markdown=True
                            )
                        break
                    
                    page_results = self.parser.parse_evirma_response(evirma_response)
                    self.parser.results.extend(page_results)
                    
                    await asyncio.sleep(1)
                
                if self.parser.results:
                    filename = f"{category['name']}_analysis_{int(time.time())}"
                    self.parser.save_to_excel(filename)
                    await self.send_status(
                        f"Парсинг завершён: товары закончились. Сохранено {len(self.parser.results)} товаров",
                        user_id=user_id,
                        markdown=True
                    )
                    await self.send_excel_to_user(filename, user_id)
                else:
                    await self.send_status(
                        "Товары не найдены по заданным критериям.",
                        user_id=user_id,
                        markdown=True
                    )
                
                return True
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    await self.send_status(
                        "ℹ️ Максимум товаров спарсены.",
                        user_id=user_id,
                        markdown=True
                    )
                    if self.parser.results:
                        filename = f"{category['name']}_analysis_{int(time.time())}"
                        self.parser.save_to_excel(filename)
                        await self.send_status(
                            f"Парсинг завершён: максимум товаров спарсены. Сохранено {len(self.parser.results)} товаров",
                            user_id=user_id,
                            markdown=True
                        )
                        await self.send_excel_to_user(filename, user_id)
                    return True
                else:
                    error_msg = f"❌ Ошибка во время парсинга: {str(e)}"
                    await self.send_status(error_msg, user_id=user_id, markdown=True)
                    if self.parser.results:
                        filename = f"{category['name']}_analysis_{int(time.time())}"
                        self.parser.save_to_excel(filename)
                        await self.send_status(
                            f"Парсинг завершён из-за ошибки. Сохранено {len(self.parser.results)} товаров",
                            user_id=user_id,
                            markdown=True
                        )
                        await self.send_excel_to_user(filename, user_id)
                    return True
            except Exception as e:
                error_msg = f"❌ Ошибка во время парсинга: {str(e)}"
                await self.send_status(error_msg, user_id=user_id, markdown=True)
                if self.parser.results:
                    filename = f"{category['name']}_analysis_{int(time.time())}"
                    self.parser.save_to_excel(filename)
                    await self.send_status(
                        f"Парсинг завершён из-за ошибки. Сохранено {len(self.parser.results)} товаров",
                        user_id=user_id,
                        markdown=True
                    )
                    await self.send_excel_to_user(filename, user_id)
                return True
            finally:
                elapsed_time = time.time() - start_time
                await self.send_status(
                    f"Общее время работы: {elapsed_time:.2f} секунд",
                    user_id=user_id,
                    markdown=True
                )

        except Exception as e:
            error_msg = f"❌ *Ошибка при формировании отчета:*\n`{str(e)}`"
            await self.send_status(error_msg, user_id=user_id, markdown=True)
            logger.exception("Error generating report")
            return False
        finally:
            await self.clear_log_messages(user_id)

    async def delete_file_after_delay(self, file_path: str):
        """Удаление файла через 15 секунд"""
        await asyncio.sleep(15)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"File deleted: {file_path}")
            else:
                logger.warning(f"File not found for deletion: {file_path}")
        except Exception as e:
            logger.error(f"Failed to delete file {file_path}: {e}")

    async def send_excel_to_user(self, filename: str, user_id: int):
        """
        Отправка Excel-файла пользователю с последующим удалением через 15 секунд
        
        :param filename: Имя файла для отправки (без .xlsx)
        :param user_id: ID пользователя
        """
        # Формируем полный путь к файлу в папке /output
        file_path = os.path.join('output', f'{filename}.xlsx')
        
        if not os.path.exists(file_path):
            error_msg = f"❌ Файл отчета {file_path} не найден!"
            await self.send_status(error_msg, user_id=user_id, markdown=True)
            logger.error(error_msg)
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
            logger.info(f"Excel report sent to user {user_id}: {file_path}")
            # Запускаем задачу удаления файла через 15 секунд
            asyncio.create_task(self.delete_file_after_delay(file_path))
        except Exception as e:
            logger.error(f"Failed to send Excel to user {user_id}: {e}")

    async def on_startup(self, _):
        logger.info("Bot starting up...")
        # Уведомление админов
        for admin_id in self.config.admin_ids:
            try:
                await self.bot.send_message(
                    admin_id,
                    "🤖 *Бот запущен и готов к работе!*\n"
                    f"Ваш ID: {admin_id}\n"
                    "Используйте /start для начала работы.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")

    async def on_shutdown(self, _):
        """Действия при остановке бота"""
        logger.info("Bot shutting down...")
        await self.bot.close()

    def run(self):
        """Запуск бота"""
        executor.start_polling(
            self.dp,
            skip_updates=True,
            on_startup=self.on_startup,
            on_shutdown=self.on_shutdown
        )

if __name__ == "__main__":
    bot = WBCategoriesBot()
    bot.run()