#!/usr/bin/env python3
"""
Balance ODE — Дифференциальная система балансировки Ядра Ленин.

Три слоя:
  1. Нейро-балансировка: 14 coupled ODEs для posterior dynamics (T2/T4)
  2. Гемисферная балансировка: LEFT/RIGHT/CORPUS кластеры
  3. Проектная балансировка: конкуренция параллельных процессов за dims

Формальный фундамент: T1 (prior), T2 (convergence), T4 (contraction), T7 (bifurcation).

Usage:
  from balance_ode import BalanceODE
  ode = BalanceODE()
  ode.inject_signal({'M': 3.0, 'P': 2.0, 'E': 1.0})
  state = ode.step(dt=1.0)
  balance = ode.hemisphere_balance()
  conflicts = ode.project_conflicts(active_projects)
"""
import json
import math
import os
from collections import defaultdict
from typing import Optional

DIMS = ["E", "C", "S", "P", "Ph", "T", "X", "M", "N", "A", "R", "I", "L", "G"]
N_DIMS = len(DIMS)

# ─── Гемисферные кластеры ───
LEFT = {"C", "M", "N", "R", "I"}       # Анализ, логика, система
RIGHT = {"E", "S", "Ph", "T", "X"}      # Эмоции, тело, творчество
CORPUS = {"A", "P", "L", "G"}           # Действие, проекты, рост

# Coupling matrix: dims influence each other through atom transitions
# γ_ij = how much dim j pulls dim i (from clinical transition matrix)
COUPLING = {
    "E": {"S": 0.08, "Ph": 0.06, "C": 0.04, "P": 0.03},
    "C": {"M": 0.07, "R": 0.05, "N": 0.04, "E": 0.03},
    "S": {"E": 0.09, "P": 0.04, "T": 0.03, "A": 0.02},
    "P": {"M": 0.06, "A": 0.05, "R": 0.04, "G": 0.03},
    "Ph": {"E": 0.07, "T": 0.05, "N": 0.04, "S": 0.03},
    "T": {"M": 0.05, "X": 0.04, "Ph": 0.03, "A": 0.03},
    "X": {"E": 0.06, "S": 0.05, "T": 0.04, "P": 0.02},
    "M": {"C": 0.08, "N": 0.05, "P": 0.04, "R": 0.03},
    "N": {"M": 0.06, "C": 0.05, "Ph": 0.04, "E": 0.02},
    "A": {"P": 0.07, "G": 0.05, "R": 0.04, "M": 0.03},
    "R": {"C": 0.06, "M": 0.04, "A": 0.03, "P": 0.03},
    "I": {"M": 0.07, "C": 0.06, "N": 0.04, "L": 0.03},
    "L": {"G": 0.06, "C": 0.05, "M": 0.04, "I": 0.03},
    "G": {"A": 0.06, "P": 0.05, "L": 0.04, "M": 0.03},
}

# Decay rates per dim (EMA α equivalent)
DECAY = {
    "E": 0.15, "C": 0.12, "S": 0.18, "P": 0.10,
    "Ph": 0.20, "T": 0.18, "X": 0.22, "M": 0.08,
    "N": 0.16, "A": 0.12, "R": 0.14, "I": 0.18,
    "L": 0.15, "G": 0.13,
}


class BalanceODE:
    """Three-layer dynamical system for Lenin core balance.

    Layer 1: 14D posterior dynamics (coupled ODEs)
    Layer 2: Hemisphere balance (LEFT vs RIGHT with CORPUS stabilizer)
    Layer 3: Project competition (resource allocation across parallel processes)
    """

    def __init__(self, initial_state: Optional[dict] = None):
        # State vector W(t) ∈ R^14 — current posterior weights
        if initial_state:
            self.W = dict(initial_state)
        else:
            # T1 max-entropy prior: uniform
            self.W = {d: 1.0 / N_DIMS for d in DIMS}

        # Signal accumulator (injected by external events)
        self.signals = {d: 0.0 for d in DIMS}

        # Project profiles (name → 14D vector)
        self.projects = {}

        # External contacts (name → 14D profile + coupling strength)
        self.contacts = {}

        # History for trajectory analysis
        self.history = []
        self.max_history = 200

    # ─── Layer 1: Posterior Dynamics ───

    def inject_signal(self, signal: dict):
        """Add signal to accumulator (from text, interaction, event)."""
        for d, v in signal.items():
            if d in self.signals:
                self.signals[d] += v

    def step(self, dt: float = 1.0) -> dict:
        """One integration step of the 14D ODE system.

        dW_i/dt = α_i · S_i(t) - β_i · W_i + Σ_j γ_ij · (W_j - W_i)

        T2 guarantee: system converges to unique fixed point.
        T4 guarantee: contraction rate bounded by min(β_i).
        """
        dW = {}
        for i in DIMS:
            # Signal input
            sig_term = self.signals.get(i, 0.0) * dt

            # Decay toward uniform (T1 prior pull)
            decay_term = DECAY.get(i, 0.15) * (self.W[i] - 1.0 / N_DIMS) * dt

            # Coupling: other dims pull this one
            coupling_term = 0.0
            for j, gamma in COUPLING.get(i, {}).items():
                coupling_term += gamma * (self.W.get(j, 0) - self.W[i]) * dt

            dW[i] = sig_term - decay_term + coupling_term

        # Update state
        for d in DIMS:
            self.W[d] = max(0.001, self.W[d] + dW[d])

        # Normalize to simplex
        total = sum(self.W.values())
        if total > 0:
            for d in DIMS:
                self.W[d] = self.W[d] / total

        # Clear signals after consumption
        self.signals = {d: 0.0 for d in DIMS}

        # Record history
        self.history.append(dict(self.W))
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

        return dict(self.W)

    def convergence_rate(self) -> float:
        """T4 contraction rate: how fast the system stabilizes.

        Returns λ ∈ [0, 1]. Higher = faster convergence.
        If history has <3 points, returns 0.
        """
        if len(self.history) < 3:
            return 0.0

        recent = self.history[-3:]
        deltas = []
        for i in range(1, len(recent)):
            d = sum(abs(recent[i].get(dim, 0) - recent[i-1].get(dim, 0)) for dim in DIMS)
            deltas.append(d)

        if deltas[0] == 0:
            return 1.0

        # Contraction: ratio of consecutive deltas
        return min(1.0, deltas[1] / deltas[0]) if deltas[0] > 0 else 1.0

    def detect_bifurcation(self) -> Optional[str]:
        """T7 bifurcation detection: cosine between consecutive states.

        Returns None if stable, or description of bifurcation.
        """
        if len(self.history) < 2:
            return None

        h = self.history
        curr = [h[-1].get(d, 0) for d in DIMS]
        prev = [h[-2].get(d, 0) for d in DIMS]

        dot = sum(a * b for a, b in zip(curr, prev))
        mag_c = math.sqrt(sum(a**2 for a in curr))
        mag_p = math.sqrt(sum(a**2 for a in prev))

        if mag_c * mag_p == 0:
            return None

        cosine = dot / (mag_c * mag_p)

        if cosine < 0.3:
            # Top dims changed dramatically
            top_curr = set(sorted(h[-1], key=h[-1].get, reverse=True)[:3])
            top_prev = set(sorted(h[-2], key=h[-2].get, reverse=True)[:3])
            shift = top_curr - top_prev
            if shift:
                return f"bifurcation: cosine={cosine:.3f}, dims shifted to {shift}"
        return None

    # ─── Layer 2: Hemisphere Balance ───

    def hemisphere_balance(self) -> dict:
        """Compute LEFT/RIGHT/CORPUS balance.

        Balance index = 1 - |Σ_L - Σ_R| / (Σ_L + Σ_R)
        1.0 = perfect balance, 0.0 = one hemisphere dominant.
        """
        sum_L = sum(self.W.get(d, 0) for d in LEFT)
        sum_R = sum(self.W.get(d, 0) for d in RIGHT)
        sum_C = sum(self.W.get(d, 0) for d in CORPUS)

        total = sum_L + sum_R
        imbalance = abs(sum_L - sum_R) / total if total > 0 else 0
        balance_index = 1.0 - imbalance

        # Dominant hemisphere
        if sum_L > sum_R * 1.3:
            dominant = "LEFT"
        elif sum_R > sum_L * 1.3:
            dominant = "RIGHT"
        else:
            dominant = "BALANCED"

        # Per-cluster entropy (diversity within cluster)
        def cluster_entropy(dims):
            vals = [self.W.get(d, 0.001) for d in dims]
            s = sum(vals)
            if s == 0:
                return 0
            probs = [v / s for v in vals]
            return -sum(p * math.log2(max(p, 1e-10)) for p in probs)

        return {
            "balance_index": round(balance_index, 4),
            "dominant": dominant,
            "left_sum": round(sum_L, 4),
            "right_sum": round(sum_R, 4),
            "corpus_sum": round(sum_C, 4),
            "left_entropy": round(cluster_entropy(LEFT), 4),
            "right_entropy": round(cluster_entropy(RIGHT), 4),
            "left_dims": {d: round(self.W.get(d, 0), 4) for d in LEFT},
            "right_dims": {d: round(self.W.get(d, 0), 4) for d in RIGHT},
            "corpus_dims": {d: round(self.W.get(d, 0), 4) for d in CORPUS},
        }

    # ─── Layer 3: Project Competition ───

    def register_project(self, name: str, profile: dict, activity: float = 0.5):
        """Register a project with its 14D profile and current activity level."""
        self.projects[name] = {
            "profile": {d: profile.get(d, 0) for d in DIMS},
            "activity": activity,
        }

    def register_contact(self, name: str, profile: dict, coupling: float = 0.3):
        """Register an external contact with their 14D profile."""
        self.contacts[name] = {
            "profile": {d: profile.get(d, 0) for d in DIMS},
            "coupling": coupling,
        }

    def project_load(self) -> dict:
        """Compute dim-level load from all active projects.

        load_i = Σ_k activity_k × profile_k_i
        """
        load = {d: 0.0 for d in DIMS}
        for pname, pdata in self.projects.items():
            activity = pdata["activity"]
            profile = pdata["profile"]
            for d in DIMS:
                load[d] += activity * profile.get(d, 0)
        return load

    def project_conflicts(self) -> list[dict]:
        """Detect dim-level conflicts between projects.

        Conflict = two projects compete for the same dim (both high).
        """
        conflicts = []
        pnames = list(self.projects.keys())

        for i, p1 in enumerate(pnames):
            for p2 in pnames[i+1:]:
                prof1 = self.projects[p1]["profile"]
                prof2 = self.projects[p2]["profile"]

                # Dim overlap = both projects have high demand
                for d in DIMS:
                    v1 = prof1.get(d, 0)
                    v2 = prof2.get(d, 0)
                    if v1 > 0.1 and v2 > 0.1:
                        conflict = min(v1, v2)
                        if conflict > 0.05:
                            conflicts.append({
                                "dim": d,
                                "project_1": p1,
                                "project_2": p2,
                                "conflict": round(conflict, 3),
                                "p1_demand": round(v1, 3),
                                "p2_demand": round(v2, 3),
                            })

        return sorted(conflicts, key=lambda c: c["conflict"], reverse=True)

    def contact_coupling_force(self) -> dict:
        """Compute how each external contact pulls the posterior.

        force_i = Σ_k coupling_k × (profile_k_i - W_i)
        Positive = contact pulls dim up, negative = pulls down.
        """
        forces = {d: 0.0 for d in DIMS}
        for cname, cdata in self.contacts.items():
            coupling = cdata["coupling"]
            profile = cdata["profile"]
            for d in DIMS:
                forces[d] += coupling * (profile.get(d, 0) - self.W.get(d, 0))
        return forces

    # ─── Integration ───

    def full_step(self, signal: Optional[dict] = None, dt: float = 1.0) -> dict:
        """Complete integration cycle: signal + projects + contacts + ODE step."""
        # 1. Inject direct signal
        if signal:
            self.inject_signal(signal)

        # 2. Inject project load as signal
        load = self.project_load()
        for d in DIMS:
            self.signals[d] += load.get(d, 0) * 0.3  # projects contribute at 30%

        # 3. Inject contact coupling as signal
        forces = self.contact_coupling_force()
        for d in DIMS:
            self.signals[d] += forces.get(d, 0) * 0.2  # contacts at 20%

        # 4. ODE step
        new_state = self.step(dt)

        # 5. Compute all diagnostics
        hemi = self.hemisphere_balance()
        conv = self.convergence_rate()
        bif = self.detect_bifurcation()
        conflicts = self.project_conflicts()
        forces = self.contact_coupling_force()

        return {
            "state": new_state,
            "hemisphere": hemi,
            "convergence": conv,
            "bifurcation": bif,
            "project_load": load,
            "project_conflicts": conflicts[:10],
            "contact_forces": {d: round(v, 4) for d, v in forces.items()},
        }

    # ─── I_kl and entropy ───

    def entropy(self) -> float:
        """Shannon entropy of current state."""
        return -sum(v * math.log2(max(v, 1e-10)) for v in self.W.values())

    def i_kl(self) -> float:
        """KL divergence from uniform (information content)."""
        h = self.entropy()
        h_max = math.log2(N_DIMS)
        return h_max - h

    def distance_to(self, target: dict) -> float:
        """Cosine distance to a target state (e.g., optimal state)."""
        v1 = [self.W.get(d, 0) for d in DIMS]
        v2 = [target.get(d, 0) for d in DIMS]
        dot = sum(a * b for a, b in zip(v1, v2))
        m1 = math.sqrt(sum(a**2 for a in v1))
        m2 = math.sqrt(sum(a**2 for a in v2))
        if m1 * m2 == 0:
            return 1.0
        return 1.0 - dot / (m1 * m2)


# ─── Pre-configured instances ───

def lenin_default() -> BalanceODE:
    """Create a BalanceODE pre-configured with Ленин projects and contacts."""
    ode = BalanceODE()

    # Projects (14D profiles from empirical data)
    ode.register_project("Сикорский", {
        "P": 0.8, "A": 0.7, "R": 0.6, "M": 0.5, "G": 0.4, "E": 0.2
    }, activity=0.7)
    ode.register_project("FREEC", {
        "P": 0.7, "A": 0.6, "E": 0.5, "T": 0.4, "S": 0.3, "M": 0.5
    }, activity=0.6)
    ode.register_project("Полдень·Полночь", {
        "P": 0.6, "M": 0.5, "A": 0.5, "T": 0.4, "G": 0.3, "L": 0.3
    }, activity=0.4)
    ode.register_project("Терапия", {
        "S": 0.8, "E": 0.7, "N": 0.5, "P": 0.4, "X": 0.3, "C": 0.4
    }, activity=0.8)
    ode.register_project("Ядро Ленин", {
        "M": 0.9, "C": 0.7, "N": 0.5, "I": 0.5, "L": 0.4, "A": 0.4
    }, activity=0.5)

    # External contacts
    ode.register_contact("Феликс", {
        "E": 0.7, "T": 0.6, "S": 0.5, "P": 0.4, "A": 0.3
    }, coupling=0.4)
    ode.register_contact("Лапшин", {
        "P": 0.8, "A": 0.6, "R": 0.5, "G": 0.4, "M": 0.3
    }, coupling=0.3)
    ode.register_contact("Алиса", {
        "R": 0.7, "A": 0.6, "P": 0.5, "M": 0.4, "C": 0.3
    }, coupling=0.3)
    ode.register_contact("Родион", {
        "P": 0.6, "A": 0.5, "R": 0.4, "G": 0.5, "S": 0.3
    }, coupling=0.3)
    ode.register_contact("Денис", {
        "A": 0.7, "P": 0.5, "R": 0.6, "M": 0.4, "C": 0.3
    }, coupling=0.25)
    ode.register_contact("Руся", {
        "E": 0.6, "S": 0.5, "A": 0.4, "P": 0.5, "C": 0.3
    }, coupling=0.35)
    ode.register_contact("Антон", {
        "C": 0.5, "A": 0.5, "M": 0.3, "P": 0.4, "L": 0.3
    }, coupling=0.2)

    return ode


if __name__ == "__main__":
    ode = lenin_default()

    print("=== LENIN BALANCE ODE ===")
    print(f"Initial I_kl: {ode.i_kl():.4f}")
    print()

    # Simulate: inject a business signal
    print("--- After Сикорский discussion ---")
    result = ode.full_step(signal={"P": 2.0, "A": 1.5, "R": 1.0, "M": 0.8})
    h = result["hemisphere"]
    print(f"  Balance index: {h['balance_index']}")
    print(f"  Dominant: {h['dominant']}")
    print(f"  L={h['left_sum']:.3f} R={h['right_sum']:.3f} C={h['corpus_sum']:.3f}")
    print(f"  Convergence: {result['convergence']:.3f}")
    if result["bifurcation"]:
        print(f"  BIFURCATION: {result['bifurcation']}")

    # Simulate: therapy signal
    print("\n--- After therapy session ---")
    result = ode.full_step(signal={"S": 2.5, "E": 2.0, "N": 0.5, "X": 0.3})
    h = result["hemisphere"]
    print(f"  Balance index: {h['balance_index']}")
    print(f"  Dominant: {h['dominant']}")
    print(f"  L={h['left_sum']:.3f} R={h['right_sum']:.3f} C={h['corpus_sum']:.3f}")

    # Project conflicts
    print("\n--- Project Conflicts ---")
    for c in result["project_conflicts"][:5]:
        print(f"  {c['dim']}: {c['project_1']} vs {c['project_2']} (conflict={c['conflict']:.3f})")

    print(f"\nFinal I_kl: {ode.i_kl():.4f}")
    print(f"Entropy: {ode.entropy():.4f} / {math.log2(N_DIMS):.4f}")
