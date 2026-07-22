#!/usr/bin/env python3
"""state_proximity.py — вычисляет близость текущего состояния к оптимальному.

Использование:
  python3 state_proximity.py              # человекочитаемый отчёт
  python3 state_proximity.py --json       # для парсинга
  python3 state_proximity.py --recommend  # рекомендации по задачам

Интеграция:
  - session_gradient.py → proximity к optimal → рекомендация атомов
  - atom_swarm.py → proximity влияет на trajectory bonus
  - CLAUDE.md → правило формирования задач через состояние
"""
import json
import math
import sys
import os
from pathlib import Path

DIMS = ["E", "C", "S", "P", "Ph", "T", "X", "M", "N", "A", "R", "I", "L", "G"]

from _paths import kernel_dir
ROOT = kernel_dir()  # папка ядра владельца
OPTIMAL_PATH = ROOT / "hot" / "optimal_state.json"
CACHE_PATH = ROOT / ".claude" / "lenin" / "posterior_cache.json"


def cosine_similarity(a: dict, b: dict) -> float:
    """Cosine similarity between two dim profiles."""
    dims = list(a.keys())
    va = [a.get(d, 0) for d in dims]
    vb = [b.get(d, 0) for d in dims]
    dot = sum(x * y for x, y in zip(va, vb))
    mag_a = math.sqrt(sum(x ** 2 for x in va))
    mag_b = math.sqrt(sum(x ** 2 for x in vb))
    if mag_a * mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def shannon_entropy(profile: dict) -> float:
    """Shannon entropy of a probability distribution."""
    return -sum(v * math.log2(v) for v in profile.values() if v > 0)


def load_optimal() -> dict | None:
    """Load optimal state profile."""
    if not OPTIMAL_PATH.exists():
        return None
    try:
        data = json.loads(OPTIMAL_PATH.read_text(encoding="utf-8"))
        return data
    except Exception:
        return None


def load_current() -> dict | None:
    """Load current posterior from cache."""
    if not CACHE_PATH.exists():
        return None
    try:
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))

        # Blended posterior (session + long-term)
        session = cache.get("session", {})
        long_term = cache.get("posterior_14d", {})

        if session and session.get("posterior"):
            beta = min(0.7, session.get("n_observations", 0) / 20)
            sess_w = session.get("posterior", {})
            blended = {}
            for d in DIMS:
                blended[d] = (1 - beta) * long_term.get(d, 1/14) + beta * sess_w.get(d, 1/14)
            total = sum(blended.values())
            if total > 0:
                return {d: blended[d] / total for d in DIMS}

        if long_term and len(long_term) == 14:
            return {d: long_term.get(d, 1/14) for d in DIMS}

    except Exception:
        pass
    return None


def load_session_dim_profile() -> dict | None:
    """Load dim profile from signal history (what actually happened this session)."""
    if not CACHE_PATH.exists():
        return None
    try:
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        history = cache.get("signal_history", [])[-30:]
        if not history:
            return None

        totals = {d: 0 for d in DIMS}
        for evt in history:
            hits = evt.get("dim_hits", {})
            for d in DIMS:
                totals[d] += hits.get(d, 0)

        total = sum(totals.values())
        if total == 0:
            return None
        return {d: totals[d] / total for d in DIMS}
    except Exception:
        return None


def compute_proximity(current: dict, optimal: dict) -> dict:
    """Compute proximity metrics between current and optimal state."""
    # Cosine similarity (direction alignment)
    cos_sim = cosine_similarity(current, optimal)

    # Entropy comparison
    h_curr = shannon_entropy(current)
    h_opt = shannon_entropy(optimal)
    h_max = math.log2(14)
    entropy_ratio = h_curr / h_max
    opt_entropy_ratio = h_opt / h_max

    # Dim-level gaps (positive = over-represented vs optimal, negative = under)
    gaps = {}
    for d in DIMS:
        curr_val = current.get(d, 0)
        opt_val = optimal.get(d, 0)
        gaps[d] = round(curr_val - opt_val, 4)

    # Top needs: dims furthest below optimal (need boosting)
    needs_boost = sorted(
        [(d, gaps[d]) for d in DIMS if gaps[d] < -0.02],
        key=lambda x: x[1]
    )
    # Top excess: dims furthest above optimal (need calming)
    needs_calm = sorted(
        [(d, gaps[d]) for d in DIMS if gaps[d] > 0.02],
        key=lambda x: -x[1]
    )

    # Overall proximity score (0-1, 1 = perfect match)
    proximity = max(0, cos_sim)

    # Zone classification
    if proximity > 0.85:
        zone = "optimal"
    elif proximity > 0.65:
        zone = "near"
    elif proximity > 0.45:
        zone = "degraded"
    else:
        zone = "far"

    return {
        "proximity": round(proximity, 4),
        "cosine": round(cos_sim, 4),
        "zone": zone,
        "entropy_ratio": round(entropy_ratio, 3),
        "opt_entropy_ratio": round(opt_entropy_ratio, 3),
        "gaps": gaps,
        "needs_boost": needs_boost[:5],
        "needs_calm": needs_calm[:5],
        "current_top3": sorted(current, key=lambda d: -current[d])[:3],
        "optimal_top3": sorted(optimal, key=lambda d: -optimal[d])[:3],
    }


# Open threads mapped to primary dims for specific recommendations.
# Пустой по умолчанию — владелец наполняет своими открытыми задачами/проектами.
# Формат: "<название>": {"dims": [...], "action": "...", "source": "..."}
THREAD_MAP = {}



def recommend_tasks(proximity: dict) -> list[dict]:
    """Recommend tasks based on proximity to optimal state.
    Generic dim-based + specific thread matching.
    """
    zone = proximity["zone"]
    boost = [d for d, _ in proximity["needs_boost"]]
    boost_set = set(boost)
    calm = [d for d, _ in proximity["needs_calm"]]

    tasks = []

    if zone == "optimal":
        tasks.append({
            "priority": "maintain",
            "action": "Продолжать текущий ритм — ты в оптимальном состоянии",
            "dims": proximity["current_top3"],
            "type": "synthesis",
        })

    # Match open threads to boost dims
    thread_scores = []
    for name, info in THREAD_MAP.items():
        thread_dims = set(info["dims"])
        overlap = len(boost_set & thread_dims)
        if overlap > 0:
            thread_scores.append((overlap, name, info))

    thread_scores.sort(key=lambda x: -x[0])

    for overlap, name, info in thread_scores[:3]:
        tasks.append({
            "priority": "high" if overlap >= 2 else "medium",
            "action": info["action"],
            "dims": info["dims"],
            "type": "thread",
        })

    # Generic fallback if no threads matched
    if not thread_scores:
        if "M" in boost:
            tasks.append({
                "priority": "high",
                "action": "Спроектировать систему или модель — M ниже оптимального",
                "dims": ["M", "A"],
                "type": "architect",
            })
        if "A" in boost:
            tasks.append({
                "priority": "high",
                "action": "Сделать что-то конкретное — A ниже оптимального",
                "dims": ["A"],
                "type": "action",
            })

    # Corrective: dims above optimal
    if "E" in calm:
        tasks.append({
            "priority": "medium",
            "action": "Снизить эмоциональную нагрузку — E выше оптимального",
            "dims": ["C", "M"],
            "type": "ground",
        })
    if "E" in boost:
        tasks.append({
            "priority": "medium",
            "action": "Контакт с людьми, собака, телесность — E ниже оптимального",
            "dims": ["E", "S", "Ph"],
            "type": "connect",
        })
    if "C" in calm:
        tasks.append({
            "priority": "medium",
            "action": "Перейти от анализа к действию — C выше оптимального",
            "dims": ["A", "G"],
            "type": "act",
        })
    if "R" in calm:
        tasks.append({
            "priority": "low",
            "action": "Ослабить контроль — R выше оптимального",
            "dims": ["E", "T"],
            "type": "relax",
        })

    if not tasks:
        tasks.append({
            "priority": "maintain",
            "action": "Состояние близко к оптимальному — работай в своём ритме",
            "dims": proximity["current_top3"],
            "type": "maintain",
        })

    return tasks


def format_report(proximity: dict, tasks: list[dict], as_json: bool = False) -> str:
    if as_json:
        return json.dumps({
            "proximity": proximity,
            "tasks": tasks,
        }, ensure_ascii=False, indent=2)

    lines = []
    zone_labels = {
        "optimal": "ОПТИМАЛЬНОЕ",
        "near": "БЛИЗКО К ОПТИМАЛЬНОМУ",
        "degraded": "УХУДШЕНО",
        "far": "ДАЛЕКО ОТ ОПТИМАЛЬНОГО",
    }

    lines.append(f"{'='*60}")
    lines.append(f"PROXIMITY К ОПТИМАЛЬНОМУ СОСТОЯНИЮ")
    lines.append(f"{'='*60}")
    lines.append(f"  Зона: {zone_labels.get(proximity['zone'], '?')}")
    lines.append(f"  Cosine: {proximity['cosine']:.3f}")
    lines.append(f"  Entropy: {proximity['entropy_ratio']:.3f} (opt: {proximity['opt_entropy_ratio']:.3f})")
    lines.append(f"  Текущие топ-3: {proximity['current_top3']}")
    lines.append(f"  Оптимальные топ-3: {proximity['optimal_top3']}")

    if proximity["needs_boost"]:
        lines.append(f"\n  Нужно усилить:")
        for d, gap in proximity["needs_boost"][:5]:
            lines.append(f"    {d}: -{abs(gap):.3f}")

    if proximity["needs_calm"]:
        lines.append(f"\n  Нужно успокоить:")
        for d, gap in proximity["needs_calm"][:5]:
            lines.append(f"    {d}: +{gap:.3f}")

    lines.append(f"\n{'─'*60}")
    lines.append(f"РЕКОМЕНДАЦИИ ПО ЗАДАЧАМ")
    lines.append(f"{'─'*60}")
    for t in tasks:
        p = t["priority"].upper()
        lines.append(f"  [{p}] {t['action']}")
        lines.append(f"         dims: {t['dims']} | type: {t['type']}")

    return "\n".join(lines)


def main():
    as_json = "--json" in sys.argv
    show_tasks = "--recommend" in sys.argv or not as_json

    optimal_data = load_optimal()
    if not optimal_data:
        msg = "NO_OPTIMAL: hot/optimal_state.json не найден"
        print(json.dumps({"error": msg}) if as_json else msg)
        return

    optimal_profile = optimal_data.get("dim_profile", {})
    if not optimal_profile:
        print("ERROR: dim_profile пустой в optimal_state.json")
        return

    # Try session dim profile first (more accurate for current state)
    current = load_session_dim_profile()
    source = "session_history"
    if not current:
        current = load_current()
        source = "posterior_cache"

    if not current:
        msg = "NO_CURRENT: нет данных о текущем состоянии"
        print(json.dumps({"error": msg}) if as_json else msg)
        return

    proximity = compute_proximity(current, optimal_profile)

    if show_tasks:
        tasks = recommend_tasks(proximity)
        print(format_report(proximity, tasks, as_json=as_json))
    else:
        print(json.dumps(proximity, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
