import asyncio
import datetime
import logging
import os
import sys
from typing import List, Optional, Set, Union

import aiohttp
import pandas as pd
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

from wb_categories_parser import WBCategoriesParser
from pytz import timezone
from apscheduler.triggers.cron import CronTrigger

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
        self.scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
        self.scheduler.add_jobstore('memory')  # Добавляем хранилище заданий
        self.parser = WBCategoriesParser()
        self.current_users = set(self.config.admin_ids)  # Автоподписка админов

        # Регистрация обработчиков только для админов
        self.dp.register_message_handler(self.start, commands=["start"], user_id=self.config.admin_ids)
        self.dp.register_message_handler(self.subscribe, commands=["subscribe"], user_id=self.config.admin_ids)
        self.dp.register_message_handler(self.unsubscribe, commands=["unsubscribe"], user_id=self.config.admin_ids)
        self.dp.register_message_handler(self.manual_update, commands=["update"], user_id=self.config.admin_ids)
        self.dp.register_message_handler(self.list_subscribers, commands=["list"], user_id=self.config.admin_ids)
        
        # Обработчик для всех остальных сообщений от неадминов
        self.dp.register_message_handler(self.unauthorized_access)

    async def unauthorized_access(self, message: types.Message):
        """Обработчик для неавторизованных пользователей"""
        user_id = message.from_user.id
        logger.warning(f"Unauthorized access attempt from user {user_id}")
        # Не отвечаем ничего неавторизованным пользователям

    async def start(self, message: types.Message):
        """Обработчик команды /start"""
        welcome_text = (
            "🛍️ *Wildberries Categories Analyzer Bot*\n\n"
            "Этот бот автоматически анализирует категории Wildberries "
            "и предоставляет актуальную статистику.\n\n"
            "Доступные команды:\n"
            "/subscribe - Подписаться на автоматические обновления\n"
            "/unsubscribe - Отписаться от обновлений\n"
            "/update - Запросить обновление вручную\n\n"
            "Данные обновляются в 09:00 и 15:00 по Москве."
        )
        await message.answer(welcome_text, parse_mode="Markdown")

    async def subscribe(self, message: types.Message):
        """Подписка пользователя на обновления"""
        user_id = message.from_user.id
        if user_id in self.current_users:
            await message.answer("ℹ️ Вы уже подписаны на обновления.")
            return

        self.current_users.add(user_id)
        logger.info(f"User {user_id} subscribed to updates")
        await message.answer(
            "✅ Вы успешно подписались на обновления!\n"
            "Теперь вы будете получать свежие отчеты автоматически."
        )

    async def unsubscribe(self, message: types.Message):
        """Отписка пользователя от обновлений"""
        user_id = message.from_user.id
        if user_id not in self.current_users:
            await message.answer("ℹ️ Вы не были подписаны на обновления.")
            return

        self.current_users.remove(user_id)
        logger.info(f"User {user_id} unsubscribed from updates")
        await message.answer("❌ Вы отписались от обновлений.")

    async def list_subscribers(self, message: types.Message):
        """Показать список подписчиков (только для админов)"""
        subscribers = "\n".join([f"- {user_id}" for user_id in self.current_users])
        await message.answer(f"📋 Список подписчиков:\n{subscribers}")

    async def manual_update(self, message: types.Message):
        """Ручной запрос обновления данных"""
        user_id = message.from_user.id
        await message.answer("🔄 Запускаю обновление данных вручную...")
        await self.generate_and_send_report(single_user_id=user_id)

    async def send_status(self, text: str, markdown: bool = False, user_ids: Union[List[int], Set[int], None] = None):
        """
        Отправка статуса пользователям
        
        :param text: Текст сообщения
        :param markdown: Использовать ли Markdown
        :param user_ids: ID пользователей для отправки (если None, отправка всем подписчикам)
        """
        if user_ids is None:
            user_ids = self.current_users
        
        if not user_ids:
            logger.warning("No users to send status to.")
            return

        logger.info(f"Sending status to {len(user_ids)} users: {text}")
        for user_id in user_ids:
            try:
                if markdown or ("*" in text or "_" in text):
                    await self.bot.send_message(user_id, text, parse_mode="Markdown")
                else:
                    await self.bot.send_message(user_id, text)
            except Exception as e:
                logger.error(f"Failed to send status to user {user_id}: {e}")

    async def generate_and_send_report(self, single_user_id=None):
        """
        Генерация и отправка отчета
        
        :param single_user_id: Если указан, отправить отчет только этому пользователю.
                              Если None и есть подписчики, отправить всем подписчикам.
        """
        # Если указан конкретный пользователь, отправляем только ему
        # Иначе отправляем всем текущим подписчикам
        recipients = [single_user_id] if single_user_id else self.current_users
        logger.info(f"Generating report for users: {recipients}")
        
        try:
            # Статус: Начало работы
            await self.send_status("🟢 *Начинаем работу*", markdown=True, user_ids=recipients)

            # Получаем категории
            await self.send_status("📋 *Получаем категории с Wildberries...*", markdown=True, user_ids=recipients)
            categories = self.parser.get_wb_categories()
            
            # Извлекаем иерархию
            await self.send_status("🧩 *Обрабатываем иерархию категорий...*", markdown=True, user_ids=recipients)
            category_hierarchy = self.parser.extract_category_hierarchy(categories)
            
            # Получаем SEO ключи
            seo_keywords = [cat["SEO"] for cat in category_hierarchy if cat["SEO"]]
            
            # Запрашиваем данные с Evirma API
            await self.send_status("📡 *Отправляем запрос к Evirma API...*", markdown=True, user_ids=recipients)
            evirma_data = self.parser.get_evirma_data(seo_keywords)
            
            # Объединяем данные
            await self.send_status("🔗 *Объединяем данные...*", markdown=True, user_ids=recipients)
            merged_data = self.parser.merge_data(category_hierarchy, evirma_data)
            
            # Сохраняем в Excel
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            filename = f"wb_categories_{today}.xlsx"
            await self.send_status("💾 *Сохраняем отчет в Excel...*", markdown=True, user_ids=recipients)
            self.parser.save_to_excel(merged_data, filename)
            
            # Отправляем файл пользователям
            await self.send_status("✅ *Отчет успешно сформирован!*", markdown=True, user_ids=recipients)
            await self.send_excel_to_users(filename, user_ids=recipients)
            
        except Exception as e:
            error_msg = f"❌ *Ошибка при формировании отчета:*\n`{str(e)}`"
            await self.send_status(error_msg, markdown=True, user_ids=recipients)
            logger.exception("Error generating report")

    async def send_excel_to_users(self, filename: str, user_ids: Union[List[int], Set[int], None] = None):
        """
        Отправка Excel-файла пользователям
        
        :param filename: Имя файла для отправки
        :param user_ids: ID пользователей для отправки (если None, отправка всем подписчикам)
        """
        if user_ids is None:
            user_ids = self.current_users
            
        if not user_ids:
            logger.warning("No users to send Excel to.")
            return

        if not os.path.exists(filename):
            error_msg = f"❌ Файл отчета {filename} не найден!"
            await self.send_status(error_msg, markdown=True, user_ids=user_ids)
            logger.error(error_msg)
            return

        today = datetime.datetime.now().strftime("%d.%m.%Y")
        caption = f"📊 *Анализ категорий Wildberries* ({today})"

        for user_id in user_ids:
            try:
                with open(filename, "rb") as file:
                    await self.bot.send_document(
                        user_id,
                        types.InputFile(file, filename),
                        caption=caption,
                        parse_mode="Markdown"
                    )
                logger.info(f"Excel report sent to user {user_id}")
            except Exception as e:
                logger.error(f"Failed to send Excel to user {user_id}: {e}")


    def schedule_jobs(self):
        try:
            self.scheduler.add_job(
                self.generate_and_send_report,
                trigger='cron',
                hour=9,
                minute=0,
                args=[None],
                id="daily_morning_report",
                replace_existing=True
            )
            self.scheduler.add_job(
                self.generate_and_send_report,
                trigger='cron',
                hour=15,
                minute=0,
                args=[None],
                id="daily_afternoon_report",
                replace_existing=True
            )
            logger.info("Scheduled daily jobs at 09:00 and 15:00 Europe/Moscow")
        except Exception as e:
            logger.error(f"Failed to schedule job: {e}")


    async def on_startup(self, _):
        logger.info("Bot starting up...")
        self.schedule_jobs()
        logger.info("Jobs scheduled")
        self.scheduler.start()
        logger.info("Scheduler started")

        # Показываем список задач
        for job in self.scheduler.get_jobs():
            logger.info(f"Scheduled job: {job}")

        # Уведомление админов
        for admin_id in self.config.admin_ids:
            try:
                await self.bot.send_message(
                    admin_id,
                    "🤖 *Бот запущен и готов к работе!*\n"
                    f"Обновления выполняются ежедневно в 09:00 и 15:00 по Москве.\n"
                    f"Ваш ID: {admin_id}\n"
                    "Используйте /subscribe для получения обновлений.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")


    async def on_shutdown(self, _):
        """Действия при остановке бота"""
        logger.info("Bot shutting down...")
        self.scheduler.shutdown()
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