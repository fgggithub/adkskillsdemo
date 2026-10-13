# Tokyo Sanitation Standards & Food Hygiene Reference

## Overview
Food safety inspections in Tokyo are overseen by the Tokyo Metropolitan Government Bureau of Public Health (東京都保健医療局) under Japan's Food Sanitation Act (食品衛生法). Health centers (保健所 - Hokenjo) conduct audits and award sanitation certifications.

## Rating Classifications
Tokyo inspections designate venues into standardized qualitative tiers based on sanitation facility audits, temperature controls, and food handler certifications.

| Tokyo Designation | Japanese Descriptor | Normalized Hygiene Score (0-100) | Description |
| :--- | :--- | :--- | :--- |
| **EXCELLENT** | 優良施設 (Yūryō Shisetsu) | **100.0** | Outstanding hygiene standards; superior food safety protocols. |
| **GOOD** | 適合 (Tekigō - Conforming) | **80.0** | Full compliance with municipal hygiene regulations. |
| **STANDARD** | 改善指導済 (Kaizen Shidō) | **60.0** | Meets baseline safety; minor corrective guidance issued. |
| **NEEDS_IMPROVEMENT** | 要改善 (Yō Kaizen) | **40.0** | Substandard conditions; reinspection mandate. |
| **UNKNOWN** | 未確認 | **50.0** | Uninspected or unlisted venue. |

## Normalization Formula
```python
def normalize_tokyo_rating(rating: str) -> float:
    rating_map = {
        "EXCELLENT": 100.0,
        "YURYO": 100.0,
        "GOOD": 80.0,
        "TEKIGO": 80.0,
        "STANDARD": 60.0,
        "NEEDS_IMPROVEMENT": 40.0,
        "UNKNOWN": 50.0,
    }
    return rating_map.get(str(rating).strip().upper(), 50.0)
```

## Gotchas & Dining Guardrails
1. **Dashi & hidden ingredients:** Traditional Tokyo cuisine frequently uses bonito fish flakes (katsuobushi) or pork extract in stocks without explicit vegetarian labeling.
2. **Halal vs Muslim-friendly:** "Muslim-friendly" in Tokyo often means pork-free menu items rather than certified Halal meat or dedicated cookware.
3. **Filter first, rank second:** An "EXCELLENT" Tokyo sanitation rating does NOT certify that a venue is Vegan or Halal. Always filter dietary constraints first!
