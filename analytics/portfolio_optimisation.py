"""Portfolio construction and optimisation module supporting all 8 required allocation methods."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from core.schemas import OptimisationMethod


def _project_onto_capped_simplex(
    raw_weights: np.ndarray,
    max_weight: float = 0.10,
    min_weight: float = 0.0,
) -> np.ndarray:
    """Project non-negative weights onto the simplex `{w: sum(w)=1, min_w <= w_i <= max_w}`."""
    n = len(raw_weights)
    if n == 0:
        return raw_weights
    # Ensure feasibility if n * max_weight < 1.0
    effective_max = max(max_weight, 1.0 / n)
    w = np.maximum(raw_weights.astype(float), 0.0)
    if w.sum() <= 0:
        w = np.ones(n, dtype=float) / n
    else:
        w = w / w.sum()

    for _ in range(30):
        w = np.clip(w, min_weight, effective_max)
        total = w.sum()
        if abs(total - 1.0) < 1e-7:
            break
        if total < 1.0:
            free = w < (effective_max - 1e-7)
            if not np.any(free):
                w = w / total
                break
            deficit = 1.0 - total
            free_sum = w[free].sum()
            if free_sum > 0:
                w[free] += deficit * (w[free] / free_sum)
            else:
                w[free] += deficit / np.sum(free)
        else:
            free = w > (min_weight + 1e-7)
            if not np.any(free):
                w = w / total
                break
            excess = total - 1.0
            w[free] -= excess * (w[free] / w[free].sum())

    w = np.clip(w, min_weight, effective_max)
    return w / w.sum()


def _enforce_subsector_caps(
    weights_dict: dict[str, float],
    category_map: dict[str, str],
    max_single_stock_pct: float = 10.0,
    max_subsector_pct: float = 30.0,
) -> dict[str, float]:
    """Iteratively enforce both single-stock and subsector weight caps."""
    syms = list(weights_dict.keys())
    n = len(syms)
    if n == 0:
        return {}
    w = np.array([weights_dict[s] for s in syms], dtype=float)
    w = _project_onto_capped_simplex(w, max_weight=max_single_stock_pct / 100.0)

    for _ in range(15):
        cat_totals: dict[str, float] = {}
        for idx, s in enumerate(syms):
            cat = category_map.get(s, "OTHER")
            cat_totals[cat] = cat_totals.get(cat, 0.0) + w[idx]

        violated = {c: tot for c, tot in cat_totals.items() if tot > (max_subsector_pct / 100.0) + 1e-4}
        if not violated:
            break

        # Check if non-violating categories have enough capacity to absorb the excess
        non_violated_indices = [i for i, s in enumerate(syms) if category_map.get(s, "OTHER") not in violated]
        if not non_violated_indices:
            break

        for cat, tot in violated.items():
            scale = (max_subsector_pct / 100.0) / tot
            for i, s in enumerate(syms):
                if category_map.get(s, "OTHER") == cat:
                    w[i] *= scale

        deficit = 1.0 - w.sum()
        if deficit > 1e-6 and non_violated_indices:
            nv_sum = sum(w[i] for i in non_violated_indices)
            for i in non_violated_indices:
                if nv_sum > 0:
                    w[i] += deficit * (w[i] / nv_sum)
                else:
                    w[i] += deficit / len(non_violated_indices)

        w = _project_onto_capped_simplex(w, max_weight=max_single_stock_pct / 100.0)

    return {syms[i]: round(float(w[i] * 100.0), 2) for i in range(n)}


def optimise_portfolio_weights(
    symbols: list[str],
    method: str = OptimisationMethod.CONVICTION_WEIGHT.value,
    returns_df: pd.DataFrame | None = None,
    conviction_scores: dict[str, float] | None = None,
    market_caps: dict[str, float] | None = None,
    category_map: dict[str, str] | None = None,
    max_single_stock_pct: float = 15.0,
    max_subsector_pct: float = 35.0,
    risk_free_rate_pct: float = 6.8,
) -> dict[str, float]:
    """Compute optimal portfolio weights (summing to 100.0%) using one of the 8 supported methods."""
    clean_syms = [s.strip().upper() for s in symbols if s.strip()]
    n = len(clean_syms)
    if n == 0:
        return {}
    if n == 1:
        return {clean_syms[0]: 100.0}

    scores = {s: max(1.0, float((conviction_scores or {}).get(s, 65.0))) for s in clean_syms}
    mcaps = {s: max(100.0, float((market_caps or {}).get(s, 10000.0))) for s in clean_syms}
    cats = category_map or {s: "OTHER" for s in clean_syms}

    # Prepare covariance matrix and annualised expected returns if returns_df is available
    cov_mat: np.ndarray | None = None
    hist_mu: np.ndarray | None = None
    if returns_df is not None and not returns_df.empty:
        avail_cols = [s for s in clean_syms if s in returns_df.columns]
        if len(avail_cols) == n and len(returns_df) >= 20:
            sub = returns_df[clean_syms].fillna(0.0).astype(float)
            cov_mat = sub.cov().values * 252.0 + np.eye(n) * 1e-4
            hist_mu = sub.mean().values * 252.0

    if cov_mat is None:
        # Construct realistic synthetic covariance matrix from sector shared structure
        vols = np.array([0.24 if mcaps[s] >= 25000 else (0.30 if mcaps[s] >= 5000 else 0.36) for s in clean_syms])
        corr = np.eye(n)
        for i in range(n):
            for j in range(i + 1, n):
                c = 0.55 if cats.get(clean_syms[i]) == cats.get(clean_syms[j]) else 0.30
                corr[i, j] = c
                corr[j, i] = c
        cov_mat = np.outer(vols, vols) * corr

    method_u = method.upper()

    if method_u == OptimisationMethod.EQUAL_WEIGHT.value:
        raw = np.ones(n) / n

    elif method_u == OptimisationMethod.CONVICTION_WEIGHT.value:
        raw = np.array([scores[s] ** 1.35 for s in clean_syms])

    elif method_u == OptimisationMethod.INVERSE_VOLATILITY.value:
        vols = np.sqrt(np.maximum(1e-6, np.diag(cov_mat)))
        raw = 1.0 / vols

    elif method_u == OptimisationMethod.MINIMUM_VARIANCE.value:
        inv_cov = np.linalg.pinv(cov_mat)
        ones = np.ones(n)
        w_unconstrained = inv_cov @ ones
        raw = np.maximum(w_unconstrained, 0.01)

    elif method_u == OptimisationMethod.MAXIMUM_SHARPE.value:
        rf = risk_free_rate_pct / 100.0
        if hist_mu is not None:
            # Blend historical return with conviction expected return so noisy short windows don't dominate
            conv_mu = np.array([rf + (scores[s] / 100.0) * 0.18 for s in clean_syms])
            mu = 0.45 * hist_mu + 0.55 * conv_mu
        else:
            mu = np.array([rf + (scores[s] / 100.0) * 0.18 for s in clean_syms])
        excess = np.maximum(0.01, mu - rf)
        inv_cov = np.linalg.pinv(cov_mat)
        raw = np.maximum(inv_cov @ excess, 0.01)

    elif method_u == OptimisationMethod.HRP.value:
        # Hierarchical Risk Parity via recursive bisection on correlation-distance ordered assets
        raw = _compute_hrp_weights(cov_mat)

    elif method_u == OptimisationMethod.BLACK_LITTERMAN.value:
        # Black-Litterman combining market-cap equilibrium implied returns with AI Exposure Score views
        w_mkt = np.array([mcaps[s] for s in clean_syms], dtype=float)
        w_mkt = w_mkt / w_mkt.sum()
        delta = 2.5  # risk aversion
        tau = 0.05
        pi = delta * (cov_mat @ w_mkt)  # Implied equilibrium excess returns
        # Absolute views Q derived from AI Exposure Score
        q_views = np.array([((scores[s] - 50.0) / 50.0) * 0.12 + 0.08 for s in clean_syms])
        p_mat = np.eye(n)
        omega = np.diag(np.diag(tau * (p_mat @ cov_mat @ p_mat.T)))
        tau_cov_inv = np.linalg.pinv(tau * cov_mat)
        omega_inv = np.linalg.pinv(omega)
        bl_mu = np.linalg.pinv(tau_cov_inv + p_mat.T @ omega_inv @ p_mat) @ (
            tau_cov_inv @ pi + p_mat.T @ omega_inv @ q_views
        )
        raw = np.maximum(np.linalg.pinv(delta * cov_mat) @ bl_mu, 0.01)

    elif method_u == OptimisationMethod.CORE_SATELLITE.value:
        # 65% Core (Large-cap utilities, power equipment & liquid leaders) + 35% Satellite (High-growth small/mid suppliers)
        core_mask = np.array([1.0 if mcaps[s] >= 25000.0 else 0.0 for s in clean_syms])
        sat_mask = 1.0 - core_mask
        if core_mask.sum() == 0 or sat_mask.sum() == 0:
            raw = np.array([scores[s] for s in clean_syms])
        else:
            core_w = (core_mask * np.array([scores[s] for s in clean_syms]))
            core_w = (core_w / core_w.sum()) * 0.65
            sat_w = (sat_mask * np.array([scores[s] for s in clean_syms]))
            sat_w = (sat_w / sat_w.sum()) * 0.35
            raw = core_w + sat_w

    else:
        raw = np.ones(n) / n

    raw_dict = {clean_syms[i]: float(raw[i]) for i in range(n)}
    capped = _enforce_subsector_caps(
        raw_dict,
        category_map=cats,
        max_single_stock_pct=max_single_stock_pct,
        max_subsector_pct=max_subsector_pct,
    )
    return capped


def _compute_hrp_weights(cov: np.ndarray) -> np.ndarray:
    """Compute Hierarchical Risk Parity weights using correlation distance ordering and recursive bisection."""
    n = cov.shape[0]
    vols = np.sqrt(np.maximum(1e-8, np.diag(cov)))
    corr = cov / np.outer(vols, vols)
    corr = np.clip(corr, -1.0, 1.0)
    dist = np.sqrt(0.5 * (1.0 - corr))

    # Greedy nearest-neighbour seriation starting from lowest-volatility asset
    start = int(np.argmin(vols))
    ordered = [start]
    remaining = set(range(n)) - {start}
    while remaining:
        last = ordered[-1]
        nxt = min(remaining, key=lambda idx: dist[last, idx])
        ordered.append(nxt)
        remaining.remove(nxt)

    weights = np.ones(n, dtype=float)

    def _cluster_var(indices: list[int]) -> float:
        sub_cov = cov[np.ix_(indices, indices)]
        ivp = 1.0 / np.maximum(1e-8, np.diag(sub_cov))
        ivp = ivp / ivp.sum()
        return float(ivp.T @ sub_cov @ ivp)

    clusters = [ordered]
    while clusters:
        new_clusters: list[list[int]] = []
        for cl in clusters:
            if len(cl) <= 1:
                continue
            mid = len(cl) // 2
            left = cl[:mid]
            right = cl[mid:]
            var_l = _cluster_var(left)
            var_r = _cluster_var(right)
            alpha = 1.0 - var_l / max(1e-8, var_l + var_r)
            for idx in left:
                weights[idx] *= alpha
            for idx in right:
                weights[idx] *= 1.0 - alpha
            if len(left) > 1:
                new_clusters.append(left)
            if len(right) > 1:
                new_clusters.append(right)
        clusters = new_clusters

    return weights / weights.sum()
