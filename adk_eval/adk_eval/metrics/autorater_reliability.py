"""
Autorater Reliability & Agreement Analysis: Krippendorff's Alpha & Gwet's AC1/AC2.
Calculates statistical inter-rater agreement between LLM-as-a-judge autoraters and human / reference ratings.
"""
from typing import List, Dict, Any, Optional, Union
import math


def calculate_krippendorff_alpha(
    reliability_data: List[List[Optional[Union[int, float, str]]]],
    level_of_measurement: str = "nominal",
) -> float:
    """
    Calculates Krippendorff's Alpha (alpha) for inter-rater agreement across multiple raters/models.
    
    Args:
        reliability_data: 2D array of shape [raters, items] or [items, raters].
                          Entry can be None for missing evaluations.
        level_of_measurement: 'nominal', 'ordinal', 'interval', or 'ratio'.
        
    Returns:
        alpha value between -1.0 and 1.0 (>= 0.80 indicates good reliability, >= 0.667 tentative).
    """
    # Normalize data so rows are items, columns are raters
    # If num_rows < num_cols and looks like [raters, items], transpose
    if len(reliability_data) > 0 and len(reliability_data[0]) > len(reliability_data):
        # Assume shape is [raters, items] -> transpose to [items, raters]
        num_raters = len(reliability_data)
        num_items = len(reliability_data[0])
        data = [[reliability_data[r][u] for r in range(num_raters)] for u in range(num_items)]
    else:
        data = reliability_data

    # Collect all unique values (excluding None)
    unique_values = set()
    for row in data:
        for val in row:
            if val is not None:
                unique_values.add(val)

    values = sorted(list(unique_values))
    if len(values) <= 1:
        return 1.0  # Perfect agreement when all values identical

    # Build coincidences / coincidence matrix
    # Difference functions
    def diff(v1, v2):
        if v1 == v2:
            return 0.0
        if level_of_measurement == "nominal":
            return 1.0
        elif level_of_measurement == "ordinal":
            # Count elements between v1 and v2
            i1, i2 = values.index(v1), values.index(v2)
            # Standard ordinal distance
            return abs(i1 - i2) ** 2
        elif level_of_measurement == "interval":
            return (float(v1) - float(v2)) ** 2
        elif level_of_measurement == "ratio":
            return ((float(v1) - float(v2)) / (float(v1) + float(v2))) ** 2 if (float(v1) + float(v2)) != 0 else 0.0
        return 1.0

    # Total observed disagreement (D_o) and expected disagreement (D_e)
    # Coincidence matrix entries
    n_pairs = 0
    obs_diff_sum = 0.0
    marginals = {v: 0 for v in values}

    for u_row in data:
        valid_vals = [v for v in u_row if v is not None]
        m_u = len(valid_vals)
        if m_u > 1:
            n_pairs += m_u * (m_u - 1)
            for i in range(m_u):
                marginals[valid_vals[i]] += (m_u - 1)
                for j in range(m_u):
                    if i != j:
                        obs_diff_sum += diff(valid_vals[i], valid_vals[j])

    if n_pairs == 0:
        return 1.0

    total_n = sum(marginals.values())
    if total_n <= 1:
        return 1.0

    exp_diff_sum = 0.0
    for v1 in values:
        for v2 in values:
            exp_diff_sum += marginals[v1] * marginals[v2] * diff(v1, v2)

    D_o = obs_diff_sum / n_pairs
    D_e = exp_diff_sum / (total_n * (total_n - 1)) if total_n > 1 else 0.0

    if D_e == 0.0:
        return 1.0 if D_o == 0.0 else 0.0

    alpha = 1.0 - (D_o / D_e)
    return round(alpha, 4)


def calculate_gwets_ac1(
    ratings: List[List[Any]],
    categories: Optional[List[Any]] = None,
) -> float:
    """
    Calculates Gwet's AC1 statistic for nominal data.
    Robust to high-prevalence paradoxes common in LLM evaluation benchmarks.
    
    Args:
        ratings: 2D list of shape [items, raters].
        categories: Optional list of categorical labels.
        
    Returns:
        AC1 score between -1.0 and 1.0.
    """
    num_items = len(ratings)
    if num_items == 0:
        return 1.0

    # Collect categories
    if categories is None:
        cats = set()
        for row in ratings:
            for val in row:
                if val is not None:
                    cats.add(val)
        categories = sorted(list(cats))

    q = len(categories)
    if q <= 1:
        return 1.0

    cat_idx = {c: i for i, c in enumerate(categories)}

    # Observed agreement (p_a)
    p_a_sum = 0.0
    valid_items = 0
    pi_k = [0.0] * q

    for row in ratings:
        valid_vals = [v for v in row if v is not None]
        r = len(valid_vals)
        if r > 1:
            valid_items += 1
            # Count frequencies per category in this item
            counts = [0] * q
            for v in valid_vals:
                if v in cat_idx:
                    counts[cat_idx[v]] += 1
            
            # Agreement for this item
            p_a_i = sum(k * (k - 1) for k in counts) / (r * (r - 1))
            p_a_sum += p_a_i

            # Accumulate proportions for chance agreement
            for i, c in enumerate(counts):
                pi_k[i] += c / r

    if valid_items == 0:
        return 1.0

    p_a = p_a_sum / valid_items
    
    # Average category probabilities
    pi_k = [k / valid_items for k in pi_k]
    
    # Chance agreement p_e for Gwet's AC1
    # p_e = (1 / (q - 1)) * sum(pi_k * (1 - pi_k))
    p_e = (1.0 / (q - 1)) * sum(p * (1.0 - p) for p in pi_k)

    if (1.0 - p_e) == 0.0:
        return 1.0

    ac1 = (p_a - p_e) / (1.0 - p_e)
    return round(ac1, 4)


def calculate_gwets_ac2(
    ratings: List[List[Union[int, float]]],
    min_val: float = 1.0,
    max_val: float = 5.0,
) -> float:
    """
    Calculates Gwet's AC2 statistic for ordinal/interval rating scales (e.g. 1-5 Likert scale).
    Uses quadratic weighting for distance penalties.
    """
    num_items = len(ratings)
    if num_items == 0:
        return 1.0

    # Weight function: w_ij = 1 - ((i - j) / (max - min))^2
    scale_range = max_val - min_val if max_val != min_val else 1.0

    def weight(v1, v2):
        diff = (float(v1) - float(v2)) / scale_range
        return 1.0 - (diff ** 2)

    # Observed weighted agreement
    p_a_sum = 0.0
    valid_items = 0
    all_values = []

    for row in ratings:
        valid_vals = [v for v in row if v is not None]
        r = len(valid_vals)
        if r > 1:
            valid_items += 1
            all_values.extend(valid_vals)
            pair_sum = 0.0
            pair_count = 0
            for i in range(r):
                for j in range(r):
                    if i != j:
                        pair_sum += weight(valid_vals[i], valid_vals[j])
                        pair_count += 1
            p_a_sum += (pair_sum / pair_count) if pair_count > 0 else 1.0

    if valid_items == 0:
        return 1.0

    p_a = p_a_sum / valid_items

    # Chance agreement p_e
    if len(all_values) > 1:
        total_pairs = 0
        exp_weight_sum = 0.0
        for i in range(len(all_values)):
            for j in range(len(all_values)):
                if i != j:
                    exp_weight_sum += weight(all_values[i], all_values[j])
                    total_pairs += 1
        p_e = exp_weight_sum / total_pairs if total_pairs > 0 else 0.0
    else:
        p_e = 0.0

    if (1.0 - p_e) == 0.0:
        return 1.0

    ac2 = (p_a - p_e) / (1.0 - p_e)
    return round(ac2, 4)


def evaluate_autorater_reliability(
    gold_ratings: List[Any],
    autorater_ratings: List[Any],
    metric_type: str = "ordinal",
) -> Dict[str, Any]:
    """
    Comprehensive evaluation comparing an LLM Judge Autorater to Golden / Reference ratings.
    Calculates Krippendorff's Alpha, Gwet's AC1/AC2, and raw percentage agreement.
    """
    paired_data = []
    exact_matches = 0
    total_valid = 0

    for g, a in zip(gold_ratings, autorater_ratings):
        if g is not None and a is not None:
            paired_data.append([g, a])
            total_valid += 1
            if g == a:
                exact_matches += 1

    if total_valid == 0:
        return {"krippendorff_alpha": 0.0, "gwets_ac": 0.0, "raw_agreement": 0.0, "valid_samples": 0}

    raw_agreement = exact_matches / total_valid

    alpha = calculate_krippendorff_alpha(paired_data, level_of_measurement=metric_type)

    if metric_type == "nominal":
        gwet = calculate_gwets_ac1(paired_data)
    else:
        # Ordinal / numeric
        gwet = calculate_gwets_ac2(paired_data)

    reliability_level = "Excellent" if alpha >= 0.80 else ("Moderate / Acceptable" if alpha >= 0.67 else "Low / Needs Calibration")

    return {
        "krippendorff_alpha": alpha,
        "gwets_ac": gwet,
        "raw_agreement": round(raw_agreement, 4),
        "valid_samples": total_valid,
        "reliability_level": reliability_level,
    }
