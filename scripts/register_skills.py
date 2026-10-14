#!/usr/bin/env python3
"""
scripts/register_skills.py

Automates the registration of enterprise skills into the GCP Agent Runtime
Skills Registry and local skill catalogs.

Parses skills with YAML frontmatter, registers tools, binds execution scripts,
packages archives, and publishes/activates skills in Google Cloud Agent Registry
(agentregistry.googleapis.com) under global/regional catalogs.
"""
import os
import sys
import yaml
import json
import time
import shutil
import zipfile
import logging
import argparse
import tempfile
import subprocess
from typing import Dict, Any, List, Optional

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from travel_concierge.tools.skill_registry import GCPSkillRegistry, evaluate_dietary_compliance
from travel_concierge.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("travel_concierge.skills.automation")


def run_cmd(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    """Executes a subprocess command safely returning stdout/stderr."""
    logger.debug(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and result.returncode != 0:
        logger.error(f"Command failed ({result.returncode}): {' '.join(cmd)}\nStderr: {result.stderr.strip()}")
        raise RuntimeError(f"Command failed: {result.stderr.strip()}")
    return result


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


def package_skill_archive(skill_id: str, skill_file: str, description: str) -> str:
    """Creates a standardized zip payload for GCP Agent Registry Skill revision."""
    temp_dir = tempfile.mkdtemp(prefix=f"skill_pkg_{skill_id}_")
    zip_path = os.path.join(tempfile.gettempdir(), f"{skill_id}.zip")

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Read original skill content and ensure frontmatter has hyphens for Agent Registry
    with open(skill_file, "r", encoding="utf-8") as f:
        content = f.read()

    frontmatter = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
            except Exception:
                frontmatter = {}
            body = parts[2]

    frontmatter["name"] = skill_id
    frontmatter["description"] = description
    updated_skill_md = f"---\n{yaml.dump(frontmatter)}---\n{body}"

    with open(os.path.join(temp_dir, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(updated_skill_md)

    # Include references if available
    ref_src = os.path.join(repo_root, "references")
    if os.path.exists(ref_src):
        ref_dst = os.path.join(temp_dir, "references")
        shutil.copytree(ref_src, ref_dst, dirs_exist_ok=True)

    # Include normalization scripts if available
    scripts_src = os.path.join(repo_root, "scripts")
    if os.path.exists(scripts_src):
        scripts_dst = os.path.join(temp_dir, "scripts")
        os.makedirs(scripts_dst, exist_ok=True)
        compare_script = os.path.join(scripts_src, "compare_ratings.py")
        if os.path.exists(compare_script):
            shutil.copy(compare_script, scripts_dst)

    # Create zip
    if os.path.exists(zip_path):
        os.remove(zip_path)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(temp_dir):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, temp_dir)
                zf.write(abs_path, rel_path)

    shutil.rmtree(temp_dir, ignore_errors=True)
    return zip_path


def register_to_gcp_agent_registry_skill(
    project_id: str,
    skill_name: str,
    description: str,
    source_file: str,
    location: str = "global"
) -> bool:
    """
    Registers and activates a skill in GCP Agent Registry (agentregistry.googleapis.com).
    """
    skill_id = skill_name.replace("_", "-").lower()
    zip_path = package_skill_archive(skill_id, source_file, description)

    try:
        # Check if skill exists (as private-{skill_id} or {skill_id})
        candidate_ids = [f"private-{skill_id}", skill_id]
        active_skill_name = None

        for cid in candidate_ids:
            desc_res = run_cmd(
                ["gcloud", "alpha", "agent-registry", "skills", "describe", cid,
                 f"--location={location}", f"--project={project_id}"],
                check=False
            )
            if desc_res.returncode == 0:
                active_skill_name = cid
                logger.info(f"Skill '{cid}' found in GCP Skill Registry (location: {location}).")
                break

        if not active_skill_name:
            logger.info(f"Creating skill '{skill_id}' in GCP Skill Registry (location: {location})...")
            create_res = run_cmd(
                [
                    "gcloud", "alpha", "agent-registry", "skills", "create", skill_id,
                    f"--location={location}",
                    f"--project={project_id}",
                    f"--display-name={skill_id}",
                    f"--description={description}",
                    f"--payload={zip_path}"
                ],
                check=False
            )
            if create_res.returncode == 0:
                # GCP prefixes tenant private skills with private-
                active_skill_name = f"private-{skill_id}"
                logger.info(f"✓ Created skill '{active_skill_name}' in GCP Skill Registry.")
            else:
                logger.warning(f"Could not create skill {skill_id}: {create_res.stderr.strip()}")
                return False

        # Check revision state
        desc_res = run_cmd(
            ["gcloud", "alpha", "agent-registry", "skills", "describe", active_skill_name,
             f"--location={location}", f"--project={project_id}"],
            check=False
        )

        if "STATE_ACTIVE" in desc_res.stdout and "defaultRevision" in desc_res.stdout:
            logger.info(f"✓ Skill '{active_skill_name}' is already ACTIVE in GCP Skill Registry.")
            return True

        # Create a new revision and activate
        rev_id = f"rev-{int(time.time())}"
        logger.info(f"Creating revision '{rev_id}' for skill '{active_skill_name}'...")
        rev_res = run_cmd(
            [
                "gcloud", "alpha", "agent-registry", "skills", "revisions", "create", rev_id,
                f"--skill={active_skill_name}",
                f"--location={location}",
                f"--project={project_id}",
                f"--payload={zip_path}"
            ],
            check=False
        )

        if rev_res.returncode != 0:
            logger.warning(f"Revision creation returned non-zero: {rev_res.stderr.strip()}")
            return False

        # Activate revision
        def_rev_uri = f"projects/{project_id}/locations/{location}/skills/{active_skill_name}/revisions/{rev_id}"
        logger.info(f"Activating skill '{active_skill_name}' with default revision '{rev_id}'...")
        upd_res = run_cmd(
            [
                "gcloud", "alpha", "agent-registry", "skills", "update", active_skill_name,
                f"--location={location}",
                f"--project={project_id}",
                f"--default-revision={def_rev_uri}",
                "--target-state=active"
            ],
            check=False
        )

        if upd_res.returncode == 0:
            logger.info(f"✓ Successfully activated skill '{active_skill_name}' in GCP Skill Registry.")
            return True
        else:
            logger.warning(f"Activation returned non-zero: {upd_res.stderr.strip()}")
            return False

    except Exception as e:
        logger.warning(f"GCP Skill Registry publication encountered error: {e}")
        return False
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)


def register_all_skills(project_id: str, location: str) -> List[Dict[str, Any]]:
    """
    Automates registration of all skill definitions found in skills/ and project root.
    Registers in local in-memory registry AND Google Cloud Agent Registry.
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

    processed_names = set()

    for sf in skill_files:
        parsed = parse_skill_markdown(sf)
        meta = parsed.get("metadata", {})
        raw_name = meta.get("name", os.path.splitext(os.path.basename(sf))[0])
        skill_name = raw_name.replace("-", "_")  # For Python registry
        cloud_skill_id = raw_name.replace("_", "-")  # For GCP Agent Registry
        description = meta.get("description", "Enterprise ADK Skill")

        if skill_name in processed_names:
            continue
        processed_names.add(skill_name)

        # Bind executable logic
        if "dietary" in skill_name.lower():
            exec_fn = evaluate_dietary_compliance
        else:
            exec_fn = lambda *args, **kwargs: {"status": "skill_executed"}

        registration_payload = {
            "name": skill_name,
            "cloud_id": cloud_skill_id,
            "description": description,
            "source_file": sf,
            "references": [
                "references/nyc_ratings.md",
                "references/uk_ratings.md",
                "references/tokyo_ratings.md",
            ],
            "normalization_script": "scripts/compare_ratings.py",
        }

        # 1. Local GCPSkillRegistry
        registry.register_skill(skill_name, exec_fn, metadata=registration_payload)
        logger.info(f"✓ Registered '{skill_name}' into local GCPSkillRegistry.")

        # 2. GCP Cloud Agent Registry (Skills catalog is hosted globally in Agent Registry)
        cloud_success = register_to_gcp_agent_registry_skill(
            project_id=project_id,
            skill_name=cloud_skill_id,
            description=description,
            source_file=sf,
            location="global"
        )
        registration_payload["gcp_registered"] = cloud_success

        registered.append(registration_payload)

    return registered


def main():
    parser = argparse.ArgumentParser(description="Register skills into GCP Agent Runtime Skills Registry")
    parser.add_argument("--project-id", type=str, default=None, help="GCP Project ID")
    parser.add_argument("--location", type=str, default=None, help="GCP Region/Location")
    args = parser.parse_args()
    project_id = args.project_id or os.getenv("PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or settings.project_id
    location = args.location or settings.location or "global"

    print("\n" + "=" * 65)
    print("      GCP AGENT RUNTIME SKILLS REGISTRY AUTOMATION")
    print("=" * 65)
    print(f"Target Project:  {project_id}")
    print(f"Target Location: {location}")
    print("-" * 65)

    results = register_all_skills(project_id=project_id, location=location)

    print(f"\nSuccessfully registered {len(results)} skill(s):")
    for r in results:
        status_str = "ACTIVE in GCP Registry" if r.get("gcp_registered") else "Local Runtime"
        print(f"  • Skill: {r['name']} (GCP ID: {r['cloud_id']}) [{status_str}]")
        print(f"    Description: {r['description']}")
        print(f"    Normalization: {r['normalization_script']}")
        print(f"    References: {', '.join(r['references'])}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
