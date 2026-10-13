#!/usr/bin/env python3
"""
scripts/register_skills.py

Automates the registration of enterprise skills into the GCP Agent Runtime
Skills Registry and local skill catalogs.

Parses skills with YAML frontmatter, registers tools, binds execution scripts,
and links regional compliance references (NYC, UK, Tokyo).
"""
import os
import sys
import yaml
import json
import logging
import argparse
from typing import Dict, Any, List

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from travel_concierge.tools.skill_registry import GCPSkillRegistry, evaluate_dietary_compliance
from travel_concierge.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("travel_concierge.skills.automation")


def parse_skill_markdown(filepath: str) -> Dict[str, Any]:
    """Extracts YAML frontmatter and body from markdown skill specification."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    frontmatter = {}
    body = content

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            raw_yaml = parts[1]
            body = parts[2].strip()
            try:
                frontmatter = yaml.safe_load(raw_yaml) or {}
            except Exception as e:
                logger.warning(f"Error parsing YAML frontmatter in {filepath}: {e}")

    return {
        "metadata": frontmatter,
        "body": body,
        "filepath": filepath,
    }


def register_all_skills(project_id: str, location: str) -> List[Dict[str, Any]]:
    """
    Automates registration of all skill definitions found in skills/ and project root.
    """
    registry = GCPSkillRegistry(project_id=project_id, location=location)
    registered = []

    skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")
    skill_files = []

    if os.path.exists(skills_dir):
        for root, _, files in os.walk(skills_dir):
            for file in files:
                if file.endswith((".md", ".yaml", ".yml")):
                    skill_files.append(os.path.join(root, file))

    # Also check root dietary_advisor.md
    root_skill = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dietary_advisor.md")
    if os.path.exists(root_skill) and root_skill not in skill_files:
        skill_files.append(root_skill)

    logger.info(f"Discovered {len(skill_files)} skill definition candidate(s)...")

    for sf in skill_files:
        parsed = parse_skill_markdown(sf)
        meta = parsed.get("metadata", {})
        skill_name = meta.get("name", os.path.splitext(os.path.basename(sf))[0])
        description = meta.get("description", "Enterprise ADK Skill")

        # Bind executable logic
        if "dietary" in skill_name.lower():
            exec_fn = evaluate_dietary_compliance
        else:
            exec_fn = lambda *args, **kwargs: {"status": "skill_executed"}

        registration_payload = {
            "name": skill_name,
            "description": description,
            "source_file": sf,
            "references": [
                "references/nyc_ratings.md",
                "references/uk_ratings.md",
                "references/tokyo_ratings.md",
            ],
            "normalization_script": "scripts/compare_ratings.py",
        }

        registry.register_skill(skill_name, exec_fn, metadata=registration_payload)
        registered.append(registration_payload)
        logger.info(f"✓ Registered '{skill_name}' into GCP Agent Runtime Skills Registry.")

    return registered


def main():
    parser = argparse.ArgumentParser(description="Register skills into GCP Agent Runtime Skills Registry")
    parser.add_argument("--project-id", type=str, default=settings.project_id, help="GCP Project ID")
    parser.add_argument("--location", type=str, default=settings.location, help="GCP Region/Location")
    args = parser.parse_args()

    print("\n" + "=" * 65)
    print("      GCP AGENT RUNTIME SKILLS REGISTRY AUTOMATION")
    print("=" * 65)
    print(f"Target Project:  {args.project_id}")
    print(f"Target Region:   {args.location}")
    print("-" * 65)

    results = register_all_skills(project_id=args.project_id, location=args.location)

    print(f"\nSuccessfully registered {len(results)} skill(s):")
    for r in results:
        print(f"  • Skill: {r['name']}")
        print(f"    Description: {r['description']}")
        print(f"    Normalization: {r['normalization_script']}")
        print(f"    References: {', '.join(r['references'])}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
