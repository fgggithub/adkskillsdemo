# Dietary Advisor Skill

> **Name:** dietary_advisor

**Description:** Rules for filtering dining options based on dietary restrictions, allergies, and safety ratings. Use when evaluating restaurant safety or food standards.

The Dietary Advisor skill filters restaurant options against required dietary constraints
and then compares food-safety or hygiene ratings across different regional systems.
The critical design principle is to separate **mandatory filtering** from
**comparative ranking**.

```text
Restaurant candidates
        ↓
Apply dietary constraints
        ↓
Apply allergy / cross-contact requirements
        ↓
Remove non-compliant venues
        ↓
Normalize regional hygiene ratings
        ↓
Rank remaining venues
        ↓
Return recommendation with original rating + normalized score
```

## 1. Workflow

1. Cross-reference hotel area recommendations with dietary constraints such as Vegan, Halal, or Gluten-Free.
2. Prioritize venues with explicit allergy labeling in their menus.
3. Use `scripts/compare_ratings.py` to normalize and compare restaurant hygiene scores across local regulatory systems such as NYC Grade, UK Hygiene Rating, and Tokyo Standard.
4. For detailed compliance rules, consult the regional guides in `references/`.

| Region | Reference |
| --- | --- |
| New York City | `references/nyc_ratings.md` |
| United Kingdom | `references/uk_ratings.md` |
| Tokyo | `references/tokyo_ratings.md` |

## 2. Core Filtering Rule

> **Filter first, rank second.** A venue that fails a mandatory dietary or allergy requirement should not remain in the candidate set simply because it has an excellent hygiene score.

## 3. Gotchas

| Gotcha | Why It Matters |
| --- | --- |
| **Dietary labels are not always certifications.** | Do not present restaurant labeling as third-party certification unless the source explicitly establishes that. |
| **Allergy-safe is stricter than ingredient-compatible.** | A dish may omit an allergen but still involve shared fryers, utensils, surfaces, or preparation areas. |
| **Raw hygiene ratings are not directly comparable across countries.** | Normalize NYC, UK, and Tokyo systems before cross-region ranking. |
| **Normalized scores do not replace local context.** | Show the original local rating alongside the normalized value. |
| **Missing dietary data means unknown.** | Do not infer Halal, Vegan, Gluten-Free, or allergy compliance from missing information. |
| **All constraints must pass.** | A highly rated venue should still be excluded if it fails a required dietary restriction. |
| **Regional guidance can change.** | Consult the appropriate regional file in `references/`. |
| **Filtering and ranking are different stages.** | Remove unsuitable venues before comparing hygiene or preference scores. |
| **Ratings are not guarantees.** | Ratings and certifications reduce uncertainty but do not guarantee safety. |
| **Explain meaningful exclusions.** | State why a venue was removed when that reason helps make the recommendation auditable. |

## 4. Rating Normalization

**compare_ratings.py**

```python
python scripts/compare_ratings.py '[{"name":"Curry Spot B","system":"uk_hygiene","rating":"4"}]'
```

> **Keep both values:** Use the normalized score for cross-region comparison, but retain the original local rating in the recommendation.

## 5. Example

| Venue | Region / Rating | Halal | Vegan | Decision |
| --- | --- | --- | --- | --- |
| Ramen Spot A | Tokyo — EXCELLENT | No | Yes | Exclude because a required Halal constraint is not met. |
| Curry Spot B | UK — 4 | Yes | Yes | Keep and normalize hygiene rating. |

> **Curry Spot B** (UK Hygiene Rating: 4 / Score: 80.0) — Meets Halal & Vegan requirements with strong sanitation standards.

## 6. Recommended Reasoning Order

```text
1. Identify mandatory dietary constraints
        ↓
2. Identify allergy / cross-contact constraints
        ↓
3. Remove known non-compliant venues
        ↓
4. Mark missing information as UNKNOWN
        ↓
5. Consult regional rating reference
        ↓
6. Normalize hygiene ratings
        ↓
7. Rank remaining candidates
        ↓
8. Explain selection and exclusions
```

## 7. Updated Skill Source

**dietary_advisor.md**

```markdown
---
name: dietary_advisor
description: Rules for filtering dining options based on dietary restrictions, allergies, and safety ratings. Use when evaluating restaurant safety or food standards.
---

# Dietary Advisor Workflow

1. Cross-reference hotel area recommendations with dietary constraints (e.g., Vegan, Halal, Gluten-Free).
2. Prioritize venues with explicit allergy labeling in their menus.
3. Use `scripts/compare_ratings.py` to normalize and compare restaurant hygiene scores across local regulatory systems (e.g., NYC Grade, UK Hygiene Rating, Tokyo Standard).
4. For detailed compliance rules, consult regional guides in `references/`:
   - NYC health grading: `references/nyc_ratings.md`
   - UK Food Hygiene Scheme: `references/uk_ratings.md`
   - Tokyo sanitation standards: `references/tokyo_ratings.md`

## Gotchas

- **Dietary labels are not always certifications.** A menu item marked "Halal," "Vegan," or "Gluten-Free" may reflect restaurant labeling rather than third-party certification. Do not treat a label as certification unless the source explicitly says so.
- **Allergy-safe is stricter than ingredient-compatible.** A dish can omit an allergen but still be unsafe because of shared fryers, prep surfaces, utensils, or kitchens. Prefer venues that explicitly describe cross-contact controls when allergies are involved.
- **Do not compare raw hygiene ratings across countries.** A NYC letter grade, UK numeric hygiene rating, and Tokyo sanitation designation are different systems. Normalize them with `scripts/compare_ratings.py` before ranking venues across regions.
- **A normalized score does not erase local context.** Use the normalized score for comparison, but retain the original local rating in the final recommendation so the user can understand the source rating.
- **Missing dietary information is not a positive match.** If Halal, Vegan, Gluten-Free, or allergy information is absent, mark it as unknown rather than assuming compliance.
- **A restaurant can satisfy one constraint and fail another.** Apply all required dietary constraints before ranking by hygiene score. A highly rated venue should still be filtered out if it fails a required restriction.
- **Regional guidance can change.** When interpreting a rating, use the appropriate guide in `references/` rather than assuming that the same thresholds or terminology apply everywhere.
- **Keep filtering and ranking separate.** First remove venues that fail mandatory dietary or allergy requirements; then compare the remaining venues using hygiene/safety scores and other preferences.
- **Do not overstate food-safety guarantees.** Ratings and certifications reduce uncertainty but do not guarantee that a diner will avoid an allergic reaction or other food-safety issue.
- **Explain exclusions when useful.** If a venue appears attractive but is removed for a dietary or safety reason, state the reason clearly so the recommendation is auditable.

## Example

**Input**:
- User constraints: Vegan, Halal
- Venues:
  - *Ramen Spot A* (Tokyo, Rating: EXCELLENT, Halal: No, Vegan: Yes)
  - *Curry Spot B* (UK, Rating: 4, Halal: Yes, Vegan: Yes)

**Execution**:
1. Run `python scripts/compare_ratings.py '[{"name":"Curry Spot B","system":"uk_hygiene","rating":"4"}]'` → Score: 80.0.
2. Filter out *Ramen Spot A* due to missing Halal certification.

**Output Recommendation**:
> **Curry Spot B** (UK Hygiene Rating: 4 / Score: 80.0) — Meets Halal & Vegan requirements with strong sanitation standards.
```
