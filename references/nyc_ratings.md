# New York City Health Department Restaurant Grading Reference

## Overview
The New York City Department of Health and Mental Hygiene (DOHMH) uses an inspection letter-grading system (A, B, C) based on violation points accumulated during unannounced sanitary inspections.

## Grading System & Point Thresholds
Violation points are assigned for sanitary and food safety infractions. **Lower points indicate better sanitary conditions.**

| Grade | Violation Points | Normalized Hygiene Score (0-100) | Description |
| :--- | :--- | :--- | :--- |
| **Grade A** | 0 to 13 points | **100.0** | Best sanitary compliance; excellent food handling and hygiene practices. |
| **Grade B** | 14 to 27 points | **80.0** | Moderate sanitary issues; reinspection required; acceptable for dining. |
| **Grade C** | 28+ points | **60.0** | Serious food safety violations; close regulatory monitoring. |
| **Grade Pending** | N/A | **50.0** | Under contestation or reinspection cycle; unconfirmed status. |

## Normalization Formula
```python
def normalize_nyc_rating(grade: str) -> float:
    grade_map = {
        "A": 100.0,
        "B": 80.0,
        "C": 60.0,
        "GRADE PENDING": 50.0,
        "PENDING": 50.0,
    }
    return grade_map.get(grade.strip().upper(), 50.0)
```

## Gotchas & Dining Guardrails
1. **Letters do not mean allergen safety:** A Grade A restaurant has good sanitation, but may still practice cross-contact with allergens.
2. **Missing grade means unknown:** Never assume an unlisted NYC restaurant has Grade A.
3. **Filter first, rank second:** Always filter candidates by user dietary requirements (e.g. Halal, Vegan) before ranking by NYC hygiene score.
