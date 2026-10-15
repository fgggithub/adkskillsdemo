"""
Travel Concierge ADK Agent Entrypoint for ADK CLI and Agent Engine.
"""
from travel_concierge.agents.root_agent import (
    create_travel_concierge_root_agent,
    TravelConciergeRootAgent,
)

root_agent = create_travel_concierge_root_agent()
app = root_agent
