import requests
from typing import List, Dict, Optional
import time
from src.config.settings import settings
import asyncio

class WildberriesParser:
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }

    def __init__(self, file_service, evirma_client, log_service):
        self.file_service = file_service
        self.evirma_client = evirma_client
        self.log_service = log_service
        self.catalog_data = None
        self.results = []

    async def fetch_wb_catalog(self) -> Dict:
        """Получение каталога Wildberries"""
        try:
            response = requests.get(settings.WB_CATALOG_URL, headers=self.HEADERS)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            await self.log_service.log_to_file(f"Error fetching WB catalog: {e}", "error")
            raise

    async def extract_category_data(self, catalog: Dict) -> List[Dict]:
        """Извлечение данных категорий"""
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

    async def find_category_by_url(self, url: str) -> Optional[Dict]:
        """Поиск категории по URL"""
        if self.catalog_data is None:
            self.catalog_data = await self.fetch_wb_catalog()
        
        categories = await self.extract_category_data(self.catalog_data)
        relative_url = url.split('https://www.wildberries.ru')[-1]
        
        for category in categories:
            if category['url'] == relative_url:
                await self.log_service.log_to_file(f"Found category: {category['name']}", "info")
                return category
        return None

    async def scrape_wb_page(self, page: int, category: Dict) -> tuple[Dict, str]:
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
        await self.log_service.log_to_file(log_message, "info")
        return data, log_message

    async def process_products(self, products_data: Dict) -> List[str]:
        """Извлечение названий товаров"""
        return [
            product['name']
            for product in products_data.get('data', {}).get('products', [])
            if 'name' in product
        ]

    async def parse_category(self, url: str, user_id: int) -> bool:
        """Основной метод парсинга категории"""
        start_time = time.time()
        self.results = []
        
        try:
            category = await self.find_category_by_url(url)
            if not category:
                await self.log_service.log_to_file("Category not found. Check the URL.", "warning")
                return False
            
            for page in range(1, settings.MAX_PAGES + 1):
                wb_data, log_message = await self.scrape_wb_page(page=page, category=category)
                await self.log_service.update_log_message(user_id, log_message)
                
                products = await self.process_products(wb_data)
                if not products:
                    await self.log_service.log_to_file(f"Page {page}: no products found, stopping parsing.", "info")
                    if self.results:
                        filename = f"{category['name']}_analysis_{int(time.time())}"
                        file_path = await self.file_service.save_to_excel(self.results, filename)
                        if file_path:
                            await self.file_service.send_excel_to_user(file_path, filename, user_id)
                            await self.log_service.log_to_file(f"Parsing finished: no more products. Saved {len(self.results)} items", "info")
                    break
                
                evirma_response = await self.evirma_client.query_evirma_api(products)
                if evirma_response is None:
                    if self.results:
                        filename = f"{category['name']}_analysis_{int(time.time())}"
                        file_path = await self.file_service.save_to_excel(self.results, filename)
                        if file_path:
                            await self.file_service.send_excel_to_user(file_path, filename, user_id)
                            await self.log_service.log_to_file(f"Parsing finished: no more products. Saved {len(self.results)} items", "info")
                    else:
                        await self.log_service.log_to_file("No products found matching criteria.", "info")
                    break
                
                page_results = await self.evirma_client.parse_evirma_response(evirma_response)
                self.results.extend(page_results)
                
                await asyncio.sleep(1)
            
            if self.results:
                filename = f"{category['name']}_analysis_{int(time.time())}"
                file_path = await self.file_service.save_to_excel(self.results, filename)
                if file_path:
                    await self.file_service.send_excel_to_user(file_path, filename, user_id)
                    await self.log_service.log_to_file(f"Parsing finished: no more products. Saved {len(self.results)} items", "info")
            else:
                await self.log_service.log_to_file("No products found matching criteria.", "info")
            
            return True
                
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                await self.log_service.log_to_file("Maximum products parsed (429 error).", "info")
                if self.results:
                    filename = f"{category['name']}_analysis_{int(time.time())}"
                    file_path = await self.file_service.save_to_excel(self.results, filename)
                    if file_path:
                        await self.file_service.send_excel_to_user(file_path, filename, user_id)
                        await self.log_service.log_to_file(f"Parsing finished: max products parsed. Saved {len(self.results)} items", "info")
                return True
            else:
                await self.log_service.log_to_file(f"Parsing error: {str(e)}", "error")
                if self.results:
                    filename = f"{category['name']}_analysis_{int(time.time())}"
                    file_path = await self.file_service.save_to_excel(self.results, filename)
                    if file_path:
                        await self.file_service.send_excel_to_user(file_path, filename, user_id)
                        await self.log_service.log_to_file(f"Parsing finished due to error. Saved {len(self.results)} items", "info")
                return True
        except Exception as e:
            await self.log_service.log_to_file(f"Parsing error: {str(e)}", "error")
            if self.results:
                filename = f"{category['name']}_analysis_{int(time.time())}"
                file_path = await self.file_service.save_to_excel(self.results, filename)
                if file_path:
                    await self.file_service.send_excel_to_user(file_path, filename, user_id)
                    await self.log_service.log_to_file(f"Parsing finished due to error. Saved {len(self.results)} items", "info")
            return True
        finally:
            elapsed_time = time.time() - start_time
            await self.log_service.log_to_file(f"Total parsing time: {elapsed_time:.2f} seconds", "info")