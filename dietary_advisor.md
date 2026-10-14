---
name: dietary-advisor
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
