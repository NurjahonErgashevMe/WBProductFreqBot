import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    ADMIN_IDS = [int(id_) for id_ in os.getenv("ADMIN_ID").split(",")]
    OUTPUT_DIR = "output"
    LOG_DIR = "logs"
    EVIRMA_JSON_PATH = os.path.join(OUTPUT_DIR, "evirma.json")
    WB_CATALOG_URL = "https://static-basket-01.wbbasket.ru/vol0/data/main-menu-ru-ru-v3.json"
    EVIRMA_API_URL = "https://evirma.ru/api/v1/keyword/list"
    MAX_PAGES = 2
    PRODUCTS_PER_PAGE = 100
    FILE_DELETE_DELAY = 15  # Секунды

settings = Settings()