import asyncio
from duckduckgo_search import DDGS
import wikipediaapi
from newsapi import NewsApiClient
import httpx
import logging


class WebSearcher:
    def __init__(self, newsapi_key: str):
        self.wiki = wikipediaapi.Wikipedia('en')
        self.newsapi = NewsApiClient(api_key=newsapi_key)
        self.http_client = httpx.AsyncClient(timeout=10)

    async def duckduckgo_search(self, query, max_results=5):
        try:
            with DDGS() as ddgs:
                results = [r for r in ddgs.text(query, max_results=max_results)]
            return results or []
        except Exception as e:
            logging.warning(f"DuckDuckGo search failed: {e}")
            return []

    async def wikipedia_summary(self, query):
        try:
            page = self.wiki.page(query)
            if page.exists():
                return page.summary[0:1000]  # limit length
            return ""
        except Exception as e:
            logging.warning(f"Wikipedia fetch failed: {e}")
            return ""

    async def news_search(self, query, max_results=5):
        try:
            articles = self.newsapi.get_everything(q=query, language='en', page_size=max_results)
            return articles.get('articles', [])
        except Exception as e:
            logging.warning(f"NewsAPI search failed: {e}")
            return []

    async def combined_search(self, query):
        # Run all concurrently for speed
        ddg_task = asyncio.create_task(self.duckduckgo_search(query))
        wiki_task = asyncio.create_task(self.wikipedia_summary(query))
        news_task = asyncio.create_task(self.news_search(query))

        ddg_results = await ddg_task
        wiki_summary = await wiki_task
        news_results = await news_task

        return {
            "duckduckgo": ddg_results,
            "wikipedia": wiki_summary,
            "news": news_results,
        }

    async def close(self):
        await self.http_client.aclose()
