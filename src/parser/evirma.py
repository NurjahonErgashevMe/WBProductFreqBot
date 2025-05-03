import requests
from typing import List, Dict, Optional
from src.config.settings import settings

class EvirmaClient:
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }

    def __init__(self, file_service):
        self.file_service = file_service

    async def query_evirma_api(self, keywords: List[str]) -> Optional[Dict]:
        """Запрос к Evirma API для анализа ключевых слов"""
        payload = {
            "keywords": keywords,
            "an": False
        }
        
        response = requests.post(settings.EVIRMA_API_URL, json=payload, headers=self.HEADERS)
        response.raise_for_status()
        
        response_data = response.json()
        filtered_data = {
            "data": {
                "keywords": {
                    keyword: data for keyword, data in response_data.get("data", {}).get("keywords", {}).items()
                    if data.get("cluster") is not None
                }
            }
        }
        
        if not filtered_data["data"]["keywords"]:
            return None
        
        # await self.file_service.save_to_json(filtered_data)
        return filtered_data

    async def parse_evirma_response(self, evirma_data: Dict) -> List[Dict]:
        """Анализ ответа от Evirma API"""
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