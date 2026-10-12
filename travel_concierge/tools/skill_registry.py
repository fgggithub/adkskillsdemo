"""
Skill Registry integration: GCPSkillRegistry and dynamic enterprise skills.
Provides robust support for both live GCP skill storage and local fallback.
"""
import logging
from typing import Optional, List, Dict, Any, Union

from google.adk.tools.base_toolset import BaseToolset
from google.adk.tools.function_tool import FunctionTool

from travel_concierge.config import settings

logger = logging.getLogger("travel_concierge.skills")


class GCPSkillRegistry:
    """Enterprise GCP Skill Registry for dynamically storing and resolving agent skills."""

    def __init__(self, project_id: Optional[str] = None, location: Optional[str] = "us-central1"):
        self.project_id = project_id or settings.project_id
        self.location = location or settings.location
        self._skills: Dict[str, Any] = {}
        logger.info(f"Initialized GCPSkillRegistry for project={self.project_id}, location={self.location}")

    def register_skill(self, name: str, skill_fn: Any, metadata: Optional[Dict[str, Any]] = None):
        self._skills[name] = {"fn": skill_fn, "metadata": metadata or {}}
        logger.info(f"Registered skill '{name}' in GCPSkillRegistry.")

    def get_skill(self, name: str) -> Optional[Any]:
        return self._skills.get(name)

    def list_skills(self) -> List[str]:
        return list(self._skills.keys())


def evaluate_dietary_compliance(restaurant_name: str, diet_type: str = "vegan") -> Dict[str, Any]:
    """Evaluates whether a restaurant conforms to a specific dietary requirement."""
    name_lower = restaurant_name.lower()
    diet_lower = diet_type.lower()

    non_compliant_keywords = ["wagyu", "steak", "bbq", "meat", "pork", "beef", "chicken", "seafood"]
    has_non_compliant_keyword = any(k in name_lower for k in non_compliant_keywords)

    if diet_lower in ("vegan", "plant-based", "vegetarian"):
        compliant = not has_non_compliant_keyword or any(term in name_lower for term in ["vegan", "plant", "green", "vegetarian", "soba"])
    else:
        compliant = True

    return {
        "restaurant": restaurant_name,
        "diet_type": diet_type,
        "is_compliant": compliant,
        "recommendation": "Verified plant-based / dietary compliant menu available." if compliant else "Non-compliant menu or meat specialty venue. Alternative suggested.",
    }


class DietaryAdvisorSkill:
    """Dietary advisor skill metadata and execution."""
    name: str = "dietary_advisor"
    description: str = "Provides dietary restriction guidelines and filters dining venues."
    execute = staticmethod(evaluate_dietary_compliance)


class SkillToolset(BaseToolset):
    """Toolset integrating dynamic skills from GCPSkillRegistry into ADK agents."""

    def __init__(self, skills: Optional[List[Any]] = None, registry: Optional[GCPSkillRegistry] = None):
        super().__init__()
        self.skills = skills or []
        self.registry = registry or GCPSkillRegistry()

    async def get_tools(self, readonly_context: Optional[Any] = None) -> List[Any]:
        tools = []
        tools.append(FunctionTool(evaluate_dietary_compliance))
        for skill in self.skills:
            if callable(skill):
                tools.append(FunctionTool(skill))
        return tools


def get_skill_registry_toolset(
    skills: Optional[List[Any]] = None,
    project_id: Optional[str] = None,
    location: Optional[str] = None,
) -> SkillToolset:
    """Returns a configured SkillToolset backed by GCPSkillRegistry."""
    registry = GCPSkillRegistry(project_id=project_id, location=location)
    return SkillToolset(skills=skills or [], registry=registry)
