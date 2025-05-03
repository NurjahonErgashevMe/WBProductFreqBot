import requests
import pandas as pd
from typing import List, Dict, Optional
import time
import os

class WildberriesEvirmaParser:
    """
    Парсер данных Wildberries с интеграцией Evirma API.
    Собирает данные о товарах, анализирует их через Evirma API и сохраняет результаты в Excel.
    """
    
    WB_CATALOG_URL = 'https://static-basket-01.wbbasket.ru/vol0/data/main-menu-ru-ru-v3.json'
    EVIRMA_API_URL = 'https://evirma.ru/api/v1/keyword/list'
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    MAX_PAGES = 2  # Максимальное количество страниц для парсинга
    PRODUCTS_PER_PAGE = 100  # Количество товаров на странице
    
    def __init__(self):
        """Инициализация парсера"""
        self.catalog_data = None
        self.results = []  # Для хранения итоговых данных
    
    def fetch_wb_catalog(self) -> Dict:
        """Получение каталога Wildberries"""
        try:
            response = requests.get(self.WB_CATALOG_URL, headers=self.HEADERS)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Ошибка при получении каталога Wildberries: {e}")
            raise
    
    def extract_category_data(self, catalog: Dict) -> List[Dict]:
        """Извлечение данных категорий из каталога"""
        categories = []
        
        def process_node(node):
            if isinstance(node, dict):
                category = {
                    'name': node['name'],
                    'shard': node.get('shard'),
                    'url': node['url'],
                    'query': node.get('query')
                }
                categories.append(category)
                
                if 'childs' in node:
                    for child in node['childs']:
                        process_node(child)
            elif isinstance(node, list):
                for item in node:
                    process_node(item)
        
        process_node(catalog)
        return categories
    
    def find_category_by_url(self, url: str) -> Optional[Dict]:
        """Поиск категории по URL"""
        if self.catalog_data is None:
            self.catalog_data = self.fetch_wb_catalog()
            
        categories = self.extract_category_data(self.catalog_data)
        relative_url = url.split('https://www.wildberries.ru')[-1]
        
        for category in categories:
            if category['url'] == relative_url:
                print(f"Найдена категория: {category['name']}")
                return category
        return None
    
    def scrape_wb_page(self, page: int, category: Dict) -> tuple[Dict, str]:
        """Парсинг страницы товаров Wildberries"""
        url = (
            f'https://catalog.wb.ru/catalog/{category["shard"]}/catalog?appType=1&curr=rub'
            f'&dest=-1257786&locale=ru&page={page}'
            f'&sort=popular&spp=0&{category["query"]}'
        )
        
        response = requests.get(url, headers=self.HEADERS)
        response.raise_for_status()
        
        data = response.json()
        products_count = len(data.get("data", {}).get("products", []))
        log_message = f"Страница {page}: получено {products_count} товаров"
        print(log_message)
        return data, log_message
    
    def query_evirma_api(self, keywords: List[str]) -> Optional[Dict]:
        """Запрос к Evirma API для анализа ключевых слов"""
        payload = {
            "keywords": keywords,
            "an": False
        }
        
        response = requests.post(self.EVIRMA_API_URL, json=payload, headers=self.HEADERS)
        response.raise_for_status()
        
        # Получаем ответ и фильтруем ключевые слова с cluster: null
        response_data = response.json()
        filtered_data = {
            "data": {
                "keywords": {
                    keyword: data for keyword, data in response_data.get("data", {}).get("keywords", {}).items()
                    if data.get("cluster") is not None
                }
            }
        }
        
        # Проверяем, есть ли данные после фильтрации
        if not filtered_data["data"]["keywords"]:
            return None
        
        # Сохраняем отфильтрованные данные в JSON файл
        self.save_to_json(filtered_data)
        
        return filtered_data

    def save_to_json(self, data: Dict) -> None:
        """Сохранение ответа Evirma API в JSON файл"""
        import json
        import os
        
        try:
            with open('./evirma.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка при сохранении в JSON: {e}")
    
    def process_products(self, products_data: Dict) -> List[str]:
        """Извлечение названий товаров из данных Wildberries"""
        return [
            product['name']
            for product in products_data.get('data', {}).get('products', [])
            if 'name' in product
        ]
    
    def parse_evirma_response(self, evirma_data: Dict) -> List[Dict]:
        """Анализ ответа от Evirma API и извлечение нужных данных"""
        parsed_data = []
        
        if not isinstance(evirma_data, dict):
            return parsed_data
        
        data = evirma_data.get('data')
        if data is None:
            return parsed_data
        
        keywords = data.get('keywords')
        if not isinstance(keywords, dict):
            return parsed_data
        
        for keyword, keyword_data in keywords.items():
            if not isinstance(keyword_data, dict):
                continue
                
            cluster = keyword_data.get('cluster', {})
            parsed_data.append({
                'Название': keyword,
                'Количество товара': cluster.get('product_count', 0),
                'Частота товара': cluster.get('freq_syn', {}).get('monthly', 0)
            })
        
        return parsed_data
    
    def save_to_excel(self, filename: str) -> None:
        """Сохранение результатов в Excel файл"""
        if not self.results:
            print("Нет данных для сохранения!")
            return
        
        df = pd.DataFrame(self.results)
        
        # Формируем путь к файлу в корневой директории
        file_path = f'{filename}.xlsx'
        
        try:
            with pd.ExcelWriter(file_path, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='data', index=False)
                
                # Get the xlsxwriter workbook and worksheet objects
                workbook = writer.book
                worksheet = writer.sheets['data']
                
                # Set the column widths
                worksheet.set_column('A:A', 50)  # Column A width = 50
                worksheet.set_column('B:B', 25)  # Column B width = 25
                worksheet.set_column('C:C', 25)  # Column C width = 25
            
            print(f"Данные сохранены в файл: {file_path}")
        except Exception as e:
            print(f"Ошибка при сохранении в Excel: {e}")
    
    def parse_category(self, url: str) -> None:
        """Основной метод парсинга категории"""
        start_time = time.time()
        
        try:
            # Получаем данные категории
            category = self.find_category_by_url(url)
            if not category:
                print("Ошибка: Категория не найдена. Проверьте URL.")
                return
            
            # Парсим страницы
            for page in range(1, self.MAX_PAGES + 1):
                # Получаем данные со страницы Wildberries
                wb_data, log_message = self.scrape_wb_page(page=page, category=category)
                
                products = self.process_products(wb_data)
                if not products:
                    print(f"Страница {page}: товары не найдены, завершаем парсинг.")
                    if self.results:
                        filename = f"{category['name']}_analysis_{int(time.time())}"
                        self.save_to_excel(filename)
                        print(f"\nПарсинг завершён: товары закончились. Сохранено {len(self.results)} товаров")
                    break
                
                # Отправляем запрос в Evirma API
                evirma_response = self.query_evirma_api(products)
                
                # Если API вернул None, сохраняем текущие результаты и завершаем
                if evirma_response is None:
                    if self.results:
                        filename = f"{category['name']}_analysis_{int(time.time())}"
                        self.save_to_excel(filename)
                        print(f"\nПарсинг завершён: товары закончились. Сохранено {len(self.results)} товаров")
                    else:
                        print("\nТовары не найдены по заданным критериям.")
                    break
                
                # Обрабатываем ответ Evirma
                page_results = self.parse_evirma_response(evirma_response)
                self.results.extend(page_results)
                
                # Небольшая задержка между запросами
                time.sleep(1)
            
            # Сохраняем результаты, если они есть
            if self.results:
                filename = f"{category['name']}_analysis_{int(time.time())}"
                self.save_to_excel(filename)
                print(f"\nПарсинг завершён: товары закончились. Сохранено {len(self.results)} товаров")
            else:
                print("\nТовары не найдены по заданным критериям.")
                
        except Exception as e:
            print(f"\nОшибка во время парсинга: {str(e)}")
            if self.results:
                filename = f"{category['name']}_analysis_{int(time.time())}"
                self.save_to_excel(filename)
                print(f"\nПарсинг завершён из-за ошибки. Сохранено {len(self.results)} товаров")
        finally:
            elapsed_time = time.time() - start_time
            print(f"\nОбщее время работы: {elapsed_time:.2f} секунд")