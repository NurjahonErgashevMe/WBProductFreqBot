import json
import gzip
import pandas as pd
from seleniumwire import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import urllib.parse
import time

class WildberriesParser:
    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.base_api_url = "https://search.wb.ru/exactmatch/sng/common/v13/search"
        self.driver = self._setup_driver()

    def _setup_driver(self) -> webdriver.Chrome:
        """Настройка Chrome с использованием установленного chromedriver и пользовательского профиля."""
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(
            "--user-data-dir=C:/Users/nurja/AppData/Local/Google/Chrome/User Data/Profile 1"
        )

        # Настройки selenium-wire для перехвата HTTPS
        wire_options = {
            'suppress_connection_errors': True,
            'verify_ssl': False
        }

        service = Service("C:\\chromedriver\\chromedriver.exe")
        driver = webdriver.Chrome(service=service, options=options, seleniumwire_options=wire_options)
        return driver

    def _wait_for_element(self, by: str, value: str, timeout: int = None) -> bool:
        """Ожидает появления элемента на странице и добавляет задержку после нахождения."""
        try:
            WebDriverWait(self.driver, timeout or self.timeout).until(
                EC.presence_of_element_located((by, value))
            )
            time.sleep(3)  # Задержка 3 секунды после нахождения элемента
            return True
        except:
            return False

    def _wait_for_api_request(self, max_attempts: int = 10, interval: float = 0.5) -> dict | None:
        """Ожидает появления API-запроса к search.wb.ru."""
        for _ in range(max_attempts):
            for request in self.driver.requests:
                if (
                    request.response
                    and self.base_api_url in request.url
                    and request.response.status_code == 200
                ):
                    print(f"\n✅ Перехвачен API-запрос: {request.url}")
                    return request
            time.sleep(interval)
        print("❌ Не найден API-запрос.")
        return None

    def _get_search_frequency(self, search_query: str) -> tuple[str, str]:
        """Получает частоту запросов из EVIRMA 2 и URL результатов."""
        try:
            # Загружаем главную страницу Wildberries
            self.driver.get("https://www.wildberries.ru")
            if not self._wait_for_element(By.ID, "searchInput"):
                print("Ошибка: Поле поиска не найдено")
                return "N/A", ""

            # Вводим поисковый запрос
            search_input = self.driver.find_element(By.ID, "searchInput")
            search_input.clear()
            search_input.send_keys(search_query)

            # Ожидаем появления частоты (EVIRMA 2)
            frequency = "N/A"
            try:
                freq_element = WebDriverWait(self.driver, self.timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".freqNum"))
                )
                time.sleep(3)  # Дополнительная задержка после нахождения частоты
                frequency = freq_element.text.replace(" ", "")
                print(f"Найдена частота запросов: {frequency}")
            except:
                print("Частота запросов не найдена (EVIRMA 2 не показал данные)")

            # Очищаем список запросов перед поиском
            del self.driver.requests

            # Нажимаем кнопку поиска
            search_button = self.driver.find_element(By.ID, "applySearchBtn")
            search_button.click()

            # Ожидаем загрузки страницы результатов
            if not self._wait_for_element(By.CSS_SELECTOR, ".product-card-list"):
                print("Ошибка: Страница результатов не загрузилась")

            results_url = self.driver.current_url
            return frequency, results_url

        except Exception as e:
            print(f"Ошибка при поиске: {e}")
            return "N/A", ""

    def _parse_products_from_api(self, search_query: str) -> list:
        """Парсит товары из перехваченного API-запроса."""
        try:
            request = self._wait_for_api_request()
            if not request:
                return []

            # Получаем тело ответа
            response_body = request.response.body

            # Проверяем сжатие (Content-Encoding: gzip)
            content_encoding = request.response.headers.get('Content-Encoding', '')
            if 'gzip' in content_encoding.lower():
                response_body = gzip.decompress(response_body)

            # Декодируем тело ответа
            response_text = response_body.decode('utf-8', errors='ignore')

            # Парсим JSON
            try:
                data = json.loads(response_text)
            except json.JSONDecodeError as e:
                print(f"❌ Ошибка: Ответ не является валидным JSON: {e}")
                print(f"Содержимое ответа: {response_text[:500]}...")
                return []

            # Извлекаем товары
            products = []
            for product in data.get("data", {}).get("products", []):
                products.append({
                    "id": product.get("id"),
                    "name": product.get("name"),
                    "brand": product.get("brand"),
                    "price": product.get("priceU", 0) / 100,
                    "price_before_discount": product.get("salePriceU", 0) / 100,
                    "rating": product.get("rating"),
                    "feedbacks": product.get("feedbacks"),
                    "supplier": product.get("supplier"),
                    "supplierRating": product.get("supplierRating"),
                    "colors": ", ".join([c.get("name", "") for c in product.get("colors", [])]),
                    "promoText": product.get("promoTextCard", "")
                })

            print(f"Найдено {len(products)} товаров")
            return products

        except Exception as e:
            print(f"❌ Ошибка при разборе API-запроса: {e}")
            return []

    def parse(self, search_query: str) -> list:
        """Основной метод парсинга."""
        print(f"\nНачинаем парсинг для запроса: '{search_query}'")

        # Получаем частоту и URL результатов
        frequency, results_url = self._get_search_frequency(search_query)
        print(f"Частота запросов: {frequency}")
        print(f"URL результатов: {results_url}")

        # Парсим товары через API
        products = self._parse_products_from_api(search_query)
        print(f"Найдено товаров: {len(products)}")

        # Добавляем частоту в данные
        for product in products:
            product["query_frequency"] = frequency

        # Сохраняем в Excel
        if products:
            df = pd.DataFrame(products)
            filename = f"wb_results_{urllib.parse.quote(search_query)}.xlsx"
            df.to_excel(filename, index=False)
            print(f"\nРезультаты сохранены в файл: {filename}")
            print("\nПримеры товаров:")
            print(df.head(3).to_string(index=False))

        return products

    def close(self):
        """Закрывает драйвер."""
        try:
            self.driver.quit()
        except Exception as e:
            print(f"Ошибка при закрытии драйвера: {e}")

if __name__ == "__main__":
    parser = WildberriesParser()
    try:
        search_query = input("Введите поисковый запрос (например: 'шорты мужские'): ").strip()
        if not search_query:
            search_query = "шорты мужские"
        parser.parse(search_query)
    finally:
        parser.close()