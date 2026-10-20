"""Comparable companies and value-chain similarity scoring module."""

from __future__ import annotations

from typing import Any


# Explicit curated value-chain peer groups so domain nuances (e.g., gensets vs transformers vs EMS) are captured accurately
CURATED_VALUE_CHAIN_FAMILIES: dict[str, set[str]] = {
    "TRANSFORMERS_AND_HV_SWITCHGEAR": {"ABB", "SIEMENS", "HITACHIEN", "CGPOWER", "TRIL", "TDPOWERSYS", "APARINDS"},
    "BACKUP_GENSETS_AND_ENGINES": {"CUMMINSIND", "KIRLOSENG", "TDPOWERSYS"},
    "CABLES_AND_CONDUCTORS": {"POLYCAB", "KEI", "RRKABEL", "APARINDS", "KALPATARU"},
    "EMS_AND_PCB_COMPONENTS": {"DIXON", "KAYNES", "SYRMA", "AVALON", "CYIENTDLM", "PGEL", "CENTUM", "ELIN", "MTARTECH"},
    "COOLING_HVAC_THERMAL": {"BLUESTARCO", "VOLTAS", "AMBER", "PGEL", "CUMMINSIND", "KIRLOSENG"},
    "DATACENTRE_CLOUD_AND_HPC": {"NETWEB", "E2E", "ANANTRAJ", "TATACOMM", "BLACKBOX", "DYNACONS", "BHARTIARTL", "RELIANCE"},
    "OPTICAL_FIBRE_AND_TELECOM": {"BHARTIARTL", "TATACOMM", "HFCL", "STLTECH", "INDUSTOWER", "POLYCAB"},
    "POWER_UTILITIES_AND_EPC": {"POWERGRID", "NTPC", "TATAPOWER", "JSWENERGY", "TORNTPOWER", "LT", "KALPATARU"},
    "ENTERPRISE_AI_IT_SERVICES": {"TCS", "INFY", "HCLTECH", "WIPRO", "TECHM", "PERSISTENT", "LTTS", "COFORGE", "KPITTECH"},
    "CIRCULAR_ELECTRONICS_ITAD": {"ECORECO", "NAMOEWASTE", "CEREBRAINT"},
}


def compute_business_similarity(
    target_sec: dict[str, Any],
    target_f: dict[str, Any],
    candidate_sec: dict[str, Any],
    candidate_f: dict[str, Any],
) -> float:
    """Compute a 0–100 business & supply-chain similarity score between `target` and `candidate`."""
    if target_sec["symbol"] == candidate_sec["symbol"]:
        return 100.0

    t_cats = set(target_sec.get("sector_tags", []))
    c_cats = set(candidate_sec.get("sector_tags", []))
    t_subs = set(target_sec.get("subcategories", []))
    c_subs = set(candidate_sec.get("subcategories", []))

    cat_inter = len(t_cats & c_cats)
    cat_union = max(1, len(t_cats | c_cats))
    cat_jaccard = cat_inter / cat_union

    sub_inter = len(t_subs & c_subs)
    sub_union = max(1, len(t_subs | c_subs))
    sub_jaccard = sub_inter / sub_union

    same_primary = 1.0 if target_sec.get("primary_category") == candidate_sec.get("primary_category") else 0.0

    family_bonus = 0.0
    t_sym = target_sec["symbol"]
    c_sym = candidate_sec["symbol"]
    for members in CURATED_VALUE_CHAIN_FAMILIES.values():
        if t_sym in members and c_sym in members:
            family_bonus = 0.30
            break

    # Margin & business model proximity
    t_opm = target_f.get("operating_margin_pct")
    c_opm = candidate_f.get("operating_margin_pct")
    margin_prox = 0.5
    if t_opm is not None and c_opm is not None:
        margin_prox = max(0.0, 1.0 - abs(t_opm - c_opm) / 25.0)

    raw_score = (
        0.30 * same_primary
        + 0.25 * cat_jaccard
        + 0.20 * sub_jaccard
        + family_bonus
        + 0.10 * margin_prox
    ) * 100.0
    return round(max(0.0, min(98.0, raw_score)), 1)
