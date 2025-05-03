import requests
import pandas as pd
from typing import List, Dict, Optional
from retry import retry
import time

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
    MAX_PAGES = 50  # Максимальное количество страниц для парсинга
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
    
    @retry(Exception, tries=3, delay=2)
    def scrape_wb_page(self, page: int, category: Dict) -> Optional[Dict]:
        """Парсинг страницы товаров Wildberries"""
        url = (
            f'https://catalog.wb.ru/catalog/{category["shard"]}/catalog?appType=1&curr=rub'
            f'&dest=-1257786&locale=ru&page={page}'
            f'&sort=popular&spp=0&{category["query"]}'
        )
        
        try:
            response = requests.get(url, headers=self.HEADERS)
            response.raise_for_status()
            
            products_count = len(response.json().get("data", {}).get("products", []))
            print(f'Страница {page}: получено {products_count} товаров')
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                print(f"Ошибка 429 на странице {page}: товары закончились")
                return None
            raise
    
    @retry(Exception, tries=3, delay=2)
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
        
        try:
            with pd.ExcelWriter(f'{filename}.xlsx', engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='data', index=False)
                
                # Get the xlsxwriter workbook and worksheet objects
                workbook = writer.book
                worksheet = writer.sheets['data']
                
                # Set the column widths
                worksheet.set_column('A:A', 50)  # Column A width = 50
                worksheet.set_column('B:B', 25)  # Column B width = 25
                worksheet.set_column('C:C', 25)  # Column C width = 25
            
            print(f"Данные сохранены в файл: {filename}.xlsx")
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
                wb_data = self.scrape_wb_page(page=page, category=category)
                
                # Если товары закончились (ошибка 429)
                if wb_data is None:
                    if self.results:
                        filename = f"{category['name']}_analysis_{int(time.time())}"
                        self.save_to_excel(filename)
                        print(f"\nПарсинг завершён: товары закончились. Сохранено {len(self.results)} товаров")
                    else:
                        print("\nТовары не найдены по заданным критериям.")
                    break
                
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
        finally:
            elapsed_time = time.time() - start_time
            print(f"\nОбщее время работы: {elapsed_time:.2f} секунд")

def main():
    """Интерактивный режим работы с парсером"""
    print("Парсер Wildberries + Evirma API")
    print("------------------------------\n")
    
    parser = WildberriesEvirmaParser()
    
    while True:
        try:
            url = input('Введите URL категории Wildberries (или "q" для выхода):\n').strip()
            if url.lower() == 'q':
                break
                
            if 'wildberries.ru' not in url:
                print("Ошибка: URL должен быть с домена wildberries.ru")
                continue
                
            parser.parse_category(url)
            
        except KeyboardInterrupt:
            print("\nРабота прервана пользователем")
            break
        except Exception as e:
            print(f"Неожиданная ошибка: {str(e)}")

if __name__ == '__main__':
    main()