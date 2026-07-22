#!/usr/bin/env python3
"""posterior_health.py — Health metrics for unified posterior.

Adapted from Larry's capsule (organism_health, echo_chamber_guard, epistemic_governor)
for a single-instance Ленин runtime.

Runs on SessionStart (after session_gradient) or manually:
  python3 .claude/hooks/posterior_health.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))
from unified_posterior import UnifiedPosterior, DIMS

DIMS_SET = set(DIMS)


def cosine_sim(a: dict, b: dict) -> float:
    """Cosine similarity between two 14D dicts."""
    dot = sum(a.get(d, 0) * b.get(d, 0) for d in DIMS)
    mag_a = math.sqrt(sum(v ** 2 for v in a.values()))
    mag_b = math.sqrt(sum(v ** 2 for v in b.values()))
    return dot / (mag_a * mag_b) if mag_a * mag_b > 0 else 0


class PosteriorHealth:
    def __init__(self, up: UnifiedPosterior | None = None):
        self.up = up or UnifiedPosterior()

    def compute_health(self) -> dict:
        """Overall health of the posterior."""
        w = self.up.get_blended_posterior()  # v3: session-aware
        vals = list(w.values())
        mean_w = sum(vals) / len(vals)
        max_w = max(vals)
        min_w = min(vals)

        h = self.up.entropy()
        h_max = math.log2(len(DIMS))
        i_kl = self.up.kl_to_uniform()

        # Coverage: how many dims above mean
        above_mean = sum(1 for v in vals if v > mean_w)
        coverage = above_mean / len(DIMS)

        # Peakiness: max/mean ratio
        peakiness = max_w / mean_w if mean_w > 0 else 0

        # Diversity: 1 - max(w) — protection against dominance
        diversity = 1 - max_w

        # Status
        if peakiness > 5 or coverage < 0.25:
            status = "collapsed"
        elif peakiness > 3 or coverage < 0.4:
            status = "degraded"
        else:
            status = "healthy"

        return {
            "entropy": round(h, 4),
            "entropy_max": round(h_max, 4),
            "i_kl": i_kl,
            "peakiness": round(peakiness, 3),
            "coverage": round(coverage, 3),
            "diversity": round(diversity, 3),
            "max_dim": max(w, key=w.get),
            "min_dim": min(w, key=w.get),
            "status": status,
            "signals": self.up.get_signal_count(),
            "fep_obs": self.up.get_fep_count(),
        }

    def check_echo_chamber(self) -> dict:
        """Detect if posterior is frozen (no movement).

        Echo chamber: cosine(posterior_t, posterior_{t-10}) > 0.95 for
        consecutive observations → posterior not learning.
        """
        data = self.up._data
        history = data.get("signal_history", [])
        swarm_events = [h for h in history if h.get("source") == "atom_swarm"]

        if len(swarm_events) < 10:
            return {"echo_chamber": False, "reason": "insufficient data", "n_events": len(swarm_events)}

        # Compare posterior at different time points by reconstructing from dim_hits
        # Simplified: check if recent dim_hits patterns are all similar
        recent = swarm_events[-20:]
        recent_hits = [e.get("dim_hits", {}) for e in recent]

        # Compute pairwise cosine between consecutive hit patterns
        similarities = []
        for i in range(1, len(recent_hits)):
            sim = cosine_sim(recent_hits[i - 1], recent_hits[i])
            similarities.append(sim)

        if not similarities:
            return {"echo_chamber": False, "reason": "no pairs", "n_events": len(swarm_events)}

        avg_sim = sum(similarities) / len(similarities)
        high_sim_count = sum(1 for s in similarities if s > 0.95)

        echo = avg_sim > 0.92 and high_sim_count > len(similarities) * 0.8

        return {
            "echo_chamber": echo,
            "avg_similarity": round(avg_sim, 4),
            "high_sim_ratio": round(high_sim_count / len(similarities), 3),
            "n_events": len(swarm_events),
            "recommendation": "inject noise: raise all thresholds by 0.05" if echo else "ok",
        }

    def epistemic_balance(self) -> dict:
        """Balance between exploitation and exploration.

        Exploitation: atoms with high activation rate + low ∇d (known territory)
        Exploration: atoms with low activation rate (under-explored)
        """
        data = self.up._data
        history = data.get("signal_history", [])
        # Only consider events with actual atom activations (exclude transcription data)
        swarm_events = [h for h in history if h.get("source") == "atom_swarm" and h.get("activated_atoms")]

        if len(swarm_events) < 10:
            return {"balance": "insufficient real-prompt data", "reason": f"only {len(swarm_events)} events with activated_atoms", "exploration_ratio": 0}

        # Count activations per atom
        atom_counts: dict[str, int] = {}
        for atom in ["curiosity", "memory", "state", "gap-architect", "verifier", "forecaster", "self",
                      "therapist", "pedagogue", "builder", "entrepreneur", "synthesist"]:
            atom_counts[atom] = sum(
                1 for e in swarm_events if atom in e.get("activated_atoms", [])
            )

        n = len(swarm_events)
        rates = {a: c / n for a, c in atom_counts.items()}
        sorted_atoms = sorted(rates, key=rates.get, reverse=True)

        # Top-2 = exploitation, bottom-2 = exploration
        exploiting = sorted_atoms[:2]
        exploring = sorted_atoms[-2:]

        exploit_rate = sum(rates[a] for a in exploiting) / 2
        explore_rate = sum(rates[a] for a in exploring) / 2

        exploration_ratio = explore_rate / (exploit_rate + explore_rate) if (exploit_rate + explore_rate) > 0 else 0

        return {
            "exploration_ratio": round(exploration_ratio, 3),
            "exploiting": [(a, round(rates[a], 3)) for a in exploiting],
            "exploring": [(a, round(rates[a], 3)) for a in exploring],
            "recommendation": "force exploration atom" if exploration_ratio < 0.15 else "balanced",
        }

    def report(self) -> str:
        """Human-readable health report."""
        health = self.compute_health()
        echo = self.check_echo_chamber()
        balance = self.epistemic_balance()

        lines = [
            f"Posterior health: {health['status']}",
            f"  H={health['entropy']:.3f}/{health['entropy_max']:.3f} I_kl={health['i_kl']:.4f}",
            f"  Peak: {health['max_dim']}={health['peakiness']:.2f}x | Coverage: {health['coverage']:.0%}",
            f"  Signals: {health['signals']} | FEP: {health['fep_obs']}",
            f"Echo chamber: {'YES' if echo['echo_chamber'] else 'no'} (sim={echo.get('avg_similarity', '?')})",
            f"Balance: explore={balance.get('exploration_ratio', '?')}",
        ]

        if health["status"] != "healthy":
            lines.append(f"  ⚠ Status: {health['status']}")
        if echo.get("echo_chamber"):
            lines.append(f"  ⚠ Echo chamber detected")
        if balance.get("exploration_ratio", 1) < 0.15:
            lines.append(f"  ⚠ Low exploration — force diversity")

        return "\n".join(lines)


if __name__ == "__main__":
    ph = PosteriorHealth()
    print(ph.report())
