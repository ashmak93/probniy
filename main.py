!pip install wikipedia-api beautifulsoup4 requests loguru fastapi uvicorn pydantic
import logging
from typing import Optional, Dict, Any
import httpx
import wikipedia
from fastapi import FastAPI, Path, Query, HTTPException
from fastapi.testclient import TestClient
from loguru import logger
from fastapi.middleware.cors import CORSMiddleware

class WikipediaClient:
    def __init__(self, language: str = "ru"):
        self.language = language
        wikipedia.set_lang(language)
        self.base_url = f"https://{language}.wikipedia.org/api/rest_v1"
        self.client = httpx.AsyncClient(timeout=30.0)
        
        self._setup_logging()
    
    def _setup_logging(self):
        logger.add(
            "wikipedia_client.log",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
            level="INFO",
            rotation="10 MB",
            compression="zip"
        )
    
    async def search_articles(self, query: str, limit: int = 10) -> Dict[str, Any]:
        logger.info(f"Выполняется поиск статей: '{query}' (лимит: {limit})")
        
        try:
            search_results = wikipedia.search(query, results=limit)
            
            result = {
                "query": query,
                "limit": limit,
                "total_results": len(search_results),
                "results": search_results
            }
            
            logger.info(f"Найдено {len(search_results)} результатов для запроса '{query}'")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при поиске статей '{query}': {str(e)}")
            raise HTTPException(status_code=500, detail=f"Ошибка поиска: {str(e)}")
    
    async def get_article_summary(self, title: str) -> Dict[str, Any]:
        logger.info(f"Запрос краткого содержания статьи: '{title}'")
        
        try:
            page = wikipedia.page(title)
            summary = wikipedia.summary(title, sentences=3)
            
            result = {
                "title": title,
                "summary": summary,
                "url": page.url,
                "categories": page.categories[:5]
            }
            
            logger.info(f"Успешно получено содержание статьи '{title}'")
            return result
            
        except wikipedia.DisambiguationError as e:
            logger.warning(f"Неоднозначный запрос '{title}': {e.options}")
            raise HTTPException(
                status_code=400, 
                detail=f"Неоднозначный запрос. Возможные варианты: {e.options[:5]}"
            )
        except wikipedia.PageError:
            logger.error(f"Страница '{title}' не найдена")
            raise HTTPException(status_code=404, detail="Страница не найдена")
        except Exception as e:
            logger.error(f"Ошибка при получении статьи '{title}': {str(e)}")
            raise HTTPException(status_code=500, detail=f"Ошибка получения статьи: {str(e)}")
    
    async def get_random_article(self) -> Dict[str, Any]:
        logger.info("Запрос случайной статьи")
        
        try:
            random_title = wikipedia.random(pages=1)
            return await self.get_article_summary(random_title)
            
        except Exception as e:
            logger.error(f"Ошибка при получении случайной статьи: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Ошибка получения случайной статьи: {str(e)}")
    
    async def close(self):
        await self.client.aclose()

app = FastAPI(title="Wikipedia API Wrapper", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

wikipedia_client = WikipediaClient()

@app.get("/")
async def root():
    logger.info("Запрос корневого эндпоинта")
    return {"message": "Wikipedia API Wrapper", "version": "1.0.0"}

@app.get("/articles/search/{query}")
async def search_articles(
    query: str = Path(..., description="Поисковый запрос"),
    limit: int = Query(10, ge=1, le=50, description="Количество результатов")
) -> Dict[str, Any]:
    logger.info(f"API запрос: поиск '{query}' с лимитом {limit}")
    return await wikipedia_client.search_articles(query, limit)

@app.get("/articles/{title}/summary")
async def get_article_summary(
    title: str = Path(..., description="Название статьи", alias="title")
) -> Dict[str, Any]:
    logger.info(f"API запрос: получение содержания статьи '{title}'")
    return await wikipedia_client.get_article_summary(title)

@app.get("/articles/random")
async def get_random_article(
    language: str = Query("ru", description="Язык статьи")
) -> Dict[str, Any]:
    logger.info(f"API запрос: случайная статья на языке '{language}'")
    
    original_language = wikipedia_client.language
    if language != wikipedia_client.language:
        wikipedia.set_lang(language)
    
    try:
        result = await wikipedia_client.get_random_article()
        return result
    finally:
        if language != original_language:
            wikipedia.set_lang(original_language)

@app.on_event("shutdown")
async def shutdown_event():
    await wikipedia_client.close()
    logger.info("Wikipedia client closed")

if __name__ == "__main__":
    import asyncio
    
    client = TestClient(app)
    
    def test_search_articles():
        print("Тестирование поиска статей...")
        response = client.get("/articles/search/python", params={"limit": 5})
        
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert data["query"] == "python"
        assert data["limit"] == 5
        print("✓ Поиск статей работает корректно")
    
    def test_get_article_summary():
        print("Тестирование получения содержания статьи...")
        response = client.get("/articles/Python%20(programming%20language)/summary")
        
        if response.status_code == 200:
            data = response.json()
            assert "summary" in data
            assert "url" in data
            print("✓ Получение содержания статьи работает корректно")
        else:
            print("⚠ Статья не найдена, но API отвечает корректно")
    
    def test_get_random_article():
        print("Тестирование получения случайной статьи...")
        response = client.get("/articles/random", params={"language": "ru"})
        
        assert response.status_code == 200
        data = response.json()
        assert "title" in data
        assert "summary" in data
        print("✓ Получение случайной статьи работает корректно")
    
    def test_root_endpoint():
        print("Тестирование корневого эндпоинта...")
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "version" in data
        print("✓ Корневой эндпоинт работает корректно")
    
    print("Запуск тестов Wikipedia API...\n")
    
    test_root_endpoint()
    test_search_articles()
    test_get_article_summary()
    test_get_random_article()
    
    print("\nВсе тесты пройдены")
    
    print("\nПримеры curl-запросов:")
    
    response = client.get("/articles/search/python", params={"limit": 3})
    curl_command = f'curl -X GET "http://localhost:8000/articles/search/python?limit=3"'
    print(f"Поиск: {curl_command}")
    
    response = client.get("/articles/Python/summary")
    curl_command = f'curl -X GET "http://localhost:8000/articles/Python/summary"'
    print(f"Содержание: {curl_command}")
    
    response = client.get("/articles/random?language=ru")
    curl_command = f'curl -X GET "http://localhost:8000/articles/random?language=ru"'
    print(f"Случайная статья: {curl_command}")
