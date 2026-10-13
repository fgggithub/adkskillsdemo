#!/usr/bin/env python3
"""
scripts/compare_ratings.py

Normalizes restaurant hygiene and food-safety scores across international regulatory systems:
- New York City (NYC Health Dept Letter Grades: A, B, C)
- United Kingdom (Food Hygiene Rating Scheme: 0 to 5)
- Tokyo (Metropolitan Sanitation Standard: EXCELLENT, GOOD, STANDARD, NEEDS_IMPROVEMENT)

Usage:
  python scripts/compare_ratings.py '[{"name":"Curry Spot B","system":"uk_hygiene","rating":"4"}]'
"""
import sys
import json
from typing import List, Dict, Any, Union


def normalize_nyc(rating: str) -> float:
    r = str(rating).strip().upper()
    mapping = {
        "A": 100.0,
        "B": 80.0,
        "C": 60.0,
        "PENDING": 50.0,
        "GRADE PENDING": 50.0,
    }
    return mapping.get(r, 50.0)


def normalize_uk(rating: str) -> float:
    r = str(rating).strip().upper()
    mapping = {
        "5": 100.0,
        "4": 80.0,
        "3": 60.0,
        "2": 40.0,
        "1": 20.0,
        "0": 0.0,
        "EXEMPT": 50.0,
        "AWAITING INSPECTION": 50.0,
        "AWAITING_INSPECTION": 50.0,
    }
    return mapping.get(r, 50.0)


def normalize_tokyo(rating: str) -> float:
    r = str(rating).strip().upper()
    mapping = {
        "EXCELLENT": 100.0,
        "YURYO": 100.0,
        "GOOD": 80.0,
        "TEKIGO": 80.0,
        "STANDARD": 60.0,
        "NEEDS_IMPROVEMENT": 40.0,
        "UNKNOWN": 50.0,
    }
    return mapping.get(r, 50.0)


def normalize_rating(system: str, rating: str) -> float:
    sys_lower = system.lower().replace("-", "_").replace(" ", "_")
    if "uk" in sys_lower or "fhrs" in sys_lower:
        return normalize_uk(rating)
    elif "nyc" in sys_lower or "new_york" in sys_lower or "dohmh" in sys_lower:
        return normalize_nyc(rating)
    elif "tokyo" in sys_lower or "japan" in sys_lower:
        return normalize_tokyo(rating)
    else:
        # Fallback numeric scale attempt
        try:
            val = float(rating)
            if 0.0 <= val <= 5.0:
                return round(val * 20.0, 1)
            elif 0.0 <= val <= 100.0:
                return round(val, 1)
        except ValueError:
            pass
        return 50.0


def compare_and_rank_venues(venues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalizes and ranks venues by hygiene score while preserving original system ratings.
    """
    ranked = []
    for v in venues:
        name = v.get("name", "Unknown Venue")
        system = v.get("system", "unknown")
        original_rating = str(v.get("rating", "UNKNOWN"))
        score = normalize_rating(system, original_rating)
        item = dict(v)
        item["original_system"] = system
        item["original_rating"] = original_rating
        item["normalized_score"] = score
        ranked.append(item)

    ranked.sort(key=lambda x: x["normalized_score"], reverse=True)
    return ranked


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/compare_ratings.py '<json_array_of_venues>' or <path_to_json_file>")
        sys.exit(1)

    arg = sys.argv[1].strip()
    try:
        if arg.startswith("[") or arg.startswith("{"):
            data = json.loads(arg)
        else:
            with open(arg, "r", encoding="utf-8") as f:
                data = json.load(f)
    except Exception as e:
        print(f"Error parsing input JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if isinstance(data, dict):
        data = [data]

    results = compare_and_rank_venues(data)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
