python main.py
!pip install wikipedia-api beautifulsoup4 requests loguru fastapi uvicorn pydantic
from fastapi import FastAPI, Path, Query, HTTPException
from fastapi.testclient import TestClient
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import httpx
import wikipedia
from loguru import logger
from typing import Dict, Any
import os

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
        logger.info(f"Поиск статей: '{query}' (лимит: {limit})")
        
        try:
            search_results = wikipedia.search(query, results=limit)
            
            result = {
                "query": query,
                "limit": limit,
                "total_results": len(search_results),
                "results": search_results
            }
            
            logger.info(f"Найдено {len(search_results)} результатов для '{query}'")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при поиске '{query}': {str(e)}")
            raise HTTPException(status_code=500, detail=f"Ошибка поиска: {str(e)}")
    
    async def get_article_summary(self, title: str) -> Dict[str, Any]:
        logger.info(f"Запрос содержания статьи: '{title}'")
        
        try:
            page = wikipedia.page(title)
            summary = wikipedia.summary(title, sentences=3)
            
            result = {
                "title": title,
                "summary": summary,
                "url": page.url,
                "categories": page.categories[:5]
            }
            
            logger.info(f"Успешно получено содержание '{title}'")
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
            logger.error(f"Ошибка при получении '{title}': {str(e)}")
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

# Создаем папку для шаблонов если её нет
os.makedirs("templates", exist_ok=True)

# Монтируем статические файлы
app.mount("/static", StaticFiles(directory="templates"), name="static")

@app.get("/")
async def read_root():
    return FileResponse("templates/index.html")

@app.get("/api/")
async def root():
    logger.info("Запрос корневого эндпоинта API")
    return {"message": "Wikipedia API Wrapper", "version": "1.0.0"}

@app.get("/api/articles/search/{query}")
async def search_articles(
    query: str = Path(..., description="Поисковый запрос"),
    limit: int = Query(10, ge=1, le=50, description="Количество результатов")
) -> Dict[str, Any]:
    logger.info(f"API запрос: поиск '{query}' с лимитом {limit}")
    return await wikipedia_client.search_articles(query, limit)

@app.get("/api/articles/{title}/summary")
async def get_article_summary(
    title: str = Path(..., description="Название статьи", alias="title")
) -> Dict[str, Any]:
    logger.info(f"API запрос: получение содержания статьи '{title}'")
    return await wikipedia_client.get_article_summary(title)

@app.get("/api/articles/random")
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
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
