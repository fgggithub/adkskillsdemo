"""
Explicit Context Caching Manager for Vertex AI / Google GenAI.
"""
import datetime
import logging
import os
from dataclasses import dataclass
from typing import Optional, Any, List

from google import genai
from google.genai import types

from travel_concierge.config import settings

logger = logging.getLogger("travel_concierge.context_cache")


@dataclass
class MockCachedContent:
    """Mock cache representation used for testing or when credentials are dummy."""
    name: str
    model: str
    display_name: str
    expire_time: str
    contents: List[str]


class ExplicitContextCacheManager:
    """
    Manages creation, lifecycle, and retrieval of Vertex AI / Gemini Explicit Cached Content.
    Allows significant cost reductions (75% discount) on long system instructions and tool schemas.
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        use_mock: bool = False,
    ):
        self.project_id = project_id or settings.project_id
        self.location = location or settings.location
        self.use_mock = use_mock
        self._client: Optional[genai.Client] = None

    @property
    def client(self) -> Optional[genai.Client]:
        if self._client is None and not self.use_mock:
            try:
                self._client = genai.Client(
                    vertexai=True,
                    project=self.project_id,
                    location=self.location,
                )
            except Exception as e:
                logger.warning(
                    f"GenAI Client initialization failed ({e}). Enabling mock cache mode."
                )
                self.use_mock = True
        return self._client

    def create_agent_context_cache(
        self,
        model: Optional[str] = None,
        system_instruction: str = "",
        ttl_minutes: int = 60,
        display_name: str = "travel_concierge_shared_context",
    ) -> Any:
        """
        Creates an explicit cached content object for shared agent instructions,
        system context, and tools schema.
        """
        target_model = model or settings.model_name

        if self.use_mock or self.client is None:
            expire_time = (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(minutes=ttl_minutes)
            ).isoformat()
            cache_id = f"projects/{self.project_id}/locations/{self.location}/cachedContents/mock-cache-{int(datetime.datetime.now().timestamp())}"
            logger.info(f"[Mock Cache] Created Cache: {cache_id}")
            return MockCachedContent(
                name=cache_id,
                model=target_model,
                display_name=display_name,
                expire_time=expire_time,
                contents=[system_instruction],
            )

        try:
            cache = self.client.caches.create(
                model=target_model,
                config=types.CreateCachedContentConfig(
                    display_name=display_name,
                    contents=[system_instruction],
                    ttl=f"{ttl_minutes * 60}s",
                ),
            )
            logger.info(
                f"[Context Cache] Created Cache ID: {cache.name} (Expires: {cache.expire_time})"
            )
            return cache
        except Exception as e:
            logger.warning(
                f"Failed to create remote Vertex AI cached content: {e}. Falling back to mock cache."
            )
            expire_time = (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(minutes=ttl_minutes)
            ).isoformat()
            return MockCachedContent(
                name=f"projects/{self.project_id}/locations/{self.location}/cachedContents/fallback-cache",
                model=target_model,
                display_name=display_name,
                expire_time=expire_time,
                contents=[system_instruction],
            )

    def delete_cache(self, name: str) -> bool:
        """Deletes a cached content resource."""
        if self.use_mock or self.client is None or "mock" in name or "fallback" in name:
            logger.info(f"[Mock Cache] Deleted cache: {name}")
            return True

        try:
            self.client.caches.delete(name=name)
            logger.info(f"[Context Cache] Deleted cache: {name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete cache {name}: {e}")
            return False
