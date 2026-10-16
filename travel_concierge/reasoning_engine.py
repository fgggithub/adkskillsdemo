"""
Vertex AI Reasoning Engine for Travel Concierge.
Provides query and stream_query interfaces for Vertex AI and Gemini Enterprise,
conforming to the ADK App and Reasoning Engine specification.
"""
import os
import logging
from typing import Any, AsyncIterable, Dict, Iterator, List, Optional, Union

logger = logging.getLogger(__name__)


class TravelConciergeReasoningEngine:
    """
    Reasoning Engine interface for Gemini Enterprise and Vertex AI.
    Implements ADK Application lifecycle and event streaming for Gemini Enterprise StreamAssist.
    """

    def __init__(self):
        self._orchestrator = None
        self._adk_app = None

    def set_up(self):
        """Initializes dependencies and ADK runtime in the remote container."""
        from travel_concierge.agents.root_agent import (
            TravelConciergeRootAgent,
            create_travel_concierge_root_agent,
        )
        from vertexai.preview.reasoning_engines import AdkApp

        # Set default environment variables for remote container if not present
        os.environ.setdefault("PROJECT_ID", "qwiklabs-gcp-01-21fab9f22a4a")
        os.environ.setdefault("LOCATION", "us-central1")
        os.environ.setdefault("MODEL_NAME", "gemini-2.5-flash")
        os.environ.setdefault(
            "AGENT_GATEWAY_URL",
            "https://agent-gateway-pep-825245236792.us-central1.run.app",
        )
        os.environ.setdefault(
            "HOTEL_SERVICE_URL",
            "https://hotel-booking-specialist-825245236792.us-central1.run.app",
        )
        os.environ.setdefault(
            "RESTAURANT_SERVICE_URL",
            "https://restaurant-booking-specialist-825245236792.us-central1.run.app",
        )
        os.environ.setdefault(
            "VERIFICATION_SERVICE_URL",
            "https://final-verification-agent-825245236792.us-central1.run.app",
        )

        if self._orchestrator is None:
            self._orchestrator = TravelConciergeRootAgent()

        if self._adk_app is None:
            root_agent = create_travel_concierge_root_agent()
            self._adk_app = AdkApp(
                agent=root_agent,
                env_vars={
                    "PROJECT_ID": os.environ.get("PROJECT_ID", "qwiklabs-gcp-01-21fab9f22a4a"),
                    "LOCATION": os.environ.get("LOCATION", "us-central1"),
                    "AGENT_GATEWAY_URL": os.environ.get("AGENT_GATEWAY_URL", "https://agent-gateway-pep-825245236792.us-central1.run.app"),
                    "HOTEL_SERVICE_URL": os.environ.get("HOTEL_SERVICE_URL", "https://hotel-booking-specialist-825245236792.us-central1.run.app"),
                    "RESTAURANT_SERVICE_URL": os.environ.get("RESTAURANT_SERVICE_URL", "https://restaurant-booking-specialist-825245236792.us-central1.run.app"),
                    "VERIFICATION_SERVICE_URL": os.environ.get("VERIFICATION_SERVICE_URL", "https://final-verification-agent-825245236792.us-central1.run.app"),
                    "MODEL_NAME": os.environ.get("MODEL_NAME", "gemini-2.5-flash"),
                },
            )
            self._adk_app.set_up()

    def register_operations(self) -> Dict[str, List[str]]:
        """Registers operations supported by this reasoning engine for Vertex AI and Gemini Enterprise."""
        return {
            "": [
                "query",
                "create_session",
                "get_session",
                "list_sessions",
                "delete_session",
            ],
            "async": [
                "async_get_session",
                "async_list_sessions",
                "async_create_session",
                "async_delete_session",
            ],
            "stream": [
                "stream_query",
                "streaming_agent_run_with_events",
            ],
            "async_stream": [
                "async_stream_query",
            ],
        }

    def query(
        self,
        prompt: str = "Plan a luxury trip to Tokyo with vegan dining",
        destination: Optional[str] = None,
        dining_query: Optional[str] = None,
        context_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Executes a trip planning query synchronously."""
        if self._orchestrator is None:
            self.set_up()

        user_input = destination or prompt
        if "message" in kwargs and kwargs["message"]:
            user_input = kwargs["message"]
        elif "query" in kwargs and kwargs["query"]:
            user_input = kwargs["query"]
        elif "input" in kwargs and kwargs["input"]:
            user_input = str(kwargs["input"])

        dest = destination or user_input or "Tokyo Shinjuku"
        dining = dining_query or "vegan dinner options near the hotel"

        return self._orchestrator.plan_trip(
            destination=dest,
            dining_query=dining,
            context_id=context_id,
        )

    def stream_query(
        self,
        prompt: str = "Plan a luxury trip to Tokyo with vegan dining",
        destination: Optional[str] = None,
        dining_query: Optional[str] = None,
        context_id: Optional[str] = None,
        message: Optional[Union[str, Dict[str, Any]]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        run_config: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Iterator[Dict[str, Any]]:
        """Executes a trip planning query and streams steps."""
        if self._orchestrator is None:
            self.set_up()

        # If standard ADK stream query is invoked with message and user_id, delegate to ADK app
        if message is not None and user_id is not None and self._adk_app is not None:
            yield from self._adk_app.stream_query(
                message=message,
                user_id=user_id,
                session_id=session_id,
                run_config=run_config,
                **kwargs,
            )
            return

        user_input = destination or prompt
        if "query" in kwargs and kwargs["query"]:
            user_input = kwargs["query"]
        elif "input" in kwargs and kwargs["input"]:
            user_input = str(kwargs["input"])

        dest = destination or user_input or "Tokyo Shinjuku"
        dining = dining_query or "vegan dinner options near the hotel"

        yield {
            "status": "PROCESSING",
            "message": f"Analyzing travel planning request for destination: {dest}...",
            "destination": dest,
        }

        result = self._orchestrator.plan_trip(
            destination=dest,
            dining_query=dining,
            context_id=context_id,
        )

        yield {
            "status": "SUCCEEDED",
            "message": "Itinerary planned and verified successfully.",
            "result": result,
        }

    def streaming_agent_run_with_events(self, request_json: str):
        """
        Executes streaming agent run with events for Gemini Enterprise StreamAssist.
        """
        if self._adk_app is None:
            self.set_up()

        logger.info("Executing streaming_agent_run_with_events for StreamAssist")
        yield from self._adk_app.streaming_agent_run_with_events(request_json)

    def create_session(
        self,
        *,
        user_id: str,
        session_id: Optional[str] = None,
        state: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Creates a session in the ADK runtime."""
        if self._adk_app is None:
            self.set_up()
        return self._adk_app.create_session(user_id=user_id, session_id=session_id, state=state, **kwargs)

    def get_session(
        self,
        *,
        user_id: str,
        session_id: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Retrieves a session from the ADK runtime."""
        if self._adk_app is None:
            self.set_up()
        return self._adk_app.get_session(user_id=user_id, session_id=session_id, **kwargs)

    def list_sessions(
        self,
        *,
        user_id: str,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Lists sessions for a user from the ADK runtime."""
        if self._adk_app is None:
            self.set_up()
        return self._adk_app.list_sessions(user_id=user_id, **kwargs)

    def delete_session(
        self,
        *,
        user_id: str,
        session_id: str,
        **kwargs: Any,
    ) -> None:
        """Deletes a session from the ADK runtime."""
        if self._adk_app is None:
            self.set_up()
        return self._adk_app.delete_session(user_id=user_id, session_id=session_id, **kwargs)

    async def async_get_session(
        self,
        *,
        user_id: str,
        session_id: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Asynchronously retrieves a session."""
        if self._adk_app is None:
            self.set_up()
        return await self._adk_app.async_get_session(user_id=user_id, session_id=session_id, **kwargs)

    async def async_list_sessions(
        self,
        *,
        user_id: str,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Asynchronously lists sessions."""
        if self._adk_app is None:
            self.set_up()
        return await self._adk_app.async_list_sessions(user_id=user_id, **kwargs)

    async def async_create_session(
        self,
        *,
        user_id: str,
        session_id: Optional[str] = None,
        state: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Asynchronously creates a session."""
        if self._adk_app is None:
            self.set_up()
        return await self._adk_app.async_create_session(user_id=user_id, session_id=session_id, state=state, **kwargs)

    async def async_delete_session(
        self,
        *,
        user_id: str,
        session_id: str,
        **kwargs: Any,
    ) -> None:
        """Asynchronously deletes a session."""
        if self._adk_app is None:
            self.set_up()
        return await self._adk_app.async_delete_session(user_id=user_id, session_id=session_id, **kwargs)

    async def async_stream_query(
        self,
        *,
        message: Union[str, Dict[str, Any]],
        user_id: str,
        session_id: Optional[str] = None,
        run_config: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> AsyncIterable[Dict[str, Any]]:
        """Asynchronously streams query events."""
        if self._adk_app is None:
            self.set_up()
        async for chunk in self._adk_app.async_stream_query(
            message=message,
            user_id=user_id,
            session_id=session_id,
            run_config=run_config,
            **kwargs,
        ):
            yield chunk
