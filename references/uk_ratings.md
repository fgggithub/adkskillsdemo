# United Kingdom Food Hygiene Rating Scheme (FHRS) Reference

## Overview
The Food Standards Agency (FSA), in partnership with local authorities across England, Wales, and Northern Ireland, operates the Food Hygiene Rating Scheme (FHRS). Scotland operates the Food Hygiene Information Scheme (FHIS).

## Rating Scale (0 to 5)
In the UK, ratings are scored from 5 down to 0, where **5 represents the highest standard**.

| FHRS Rating | Regulatory Descriptor | Normalized Hygiene Score (0-100) | Description |
| :--- | :--- | :--- | :--- |
| **5** | Very Good | **100.0** | Highest standards of food hygiene and management. |
| **4** | Good | **80.0** | Standards are good; minor improvements possible. |
| **3** | Generally Satisfactory | **60.0** | Acceptable compliance with food safety legislation. |
| **2** | Improvement Necessary | **40.0** | Some hazards identified; corrective action needed. |
| **1** | Major Improvement Necessary | **20.0** | Significant failure to comply; poor hygiene standards. |
| **0** | Urgent Improvement Necessary | **0.0** | Severe hygiene failures; risk of immediate closure. |
| **Exempt / Awaiting** | Awaiting Inspection | **50.0** | Recently opened or inspection pending. |

## Normalization Formula
```python
def normalize_uk_rating(rating: str) -> float:
    rating_map = {
        "5": 100.0,
        "4": 80.0,
        "3": 60.0,
        "2": 40.0,
        "1": 20.0,
        "0": 0.0,
        "AWAITING INSPECTION": 50.0,
        "EXEMPT": 50.0,
    }
    return rating_map.get(str(rating).strip().upper(), 50.0)
```

## Gotchas & Dining Guardrails
1. **Raw scores are non-linear:** An FHRS 4 is approximately equivalent to an NYC Grade B or Tokyo Good.
2. **Allergen labelling regulation:** UK law requires disclosure of 14 allergens, but cross-contact controls vary by kitchen.
3. **Filter first, rank second:** Never prioritize a 5-rated venue that does not meet the diner's required dietary constraints (e.g. Halal or Vegan).
