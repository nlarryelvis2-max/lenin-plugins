#!/usr/bin/env python3
"""session_gradient.py — ∇d checkpoint при старте сессии.

Считает разрыв понимания между:
  - w_reported: owner weekly self-report (самоотчёт пользователя)
  - w_inferred: Bayesian posterior (оценка ядра из keyword frequency)

Вывод: топ слепых зон + рекомендация каких атомов активировать.

Использование:
  python3 .claude/hooks/session_gradient.py
  python3 .claude/hooks/session_gradient.py --json  (для парсинга)
"""

import json
import sys
from pathlib import Path

from _paths import kernel_dir, owner

DIMS = ["E", "C", "S", "P", "Ph", "T", "X", "M", "N", "A", "R", "I", "L", "G"]
DIM_NAMES = {
    "E": "эмоции", "C": "когниции", "S": "социум", "P": "проекты",
    "Ph": "тело", "T": "ритм", "X": "контекст", "M": "смысл",
    "N": "нейро", "A": "действия", "R": "саботаж", "I": "инсайт",
    "L": "обучение", "G": "рост",
}

ATOM_14D = {
    "curiosity":    {"I": 0.30, "L": 0.25, "G": 0.25, "M": 0.20},
    "memory":       {"C": 0.35, "M": 0.30, "S": 0.20, "E": 0.15},
    "state":        {"T": 0.30, "Ph": 0.30, "N": 0.25, "X": 0.15},
    "gap-architect": {"R": 0.30, "P": 0.25, "A": 0.25, "N": 0.20},
    "verifier":     {"C": 0.40, "N": 0.30, "R": 0.30},
    "forecaster":   {"A": 0.30, "P": 0.25, "E": 0.25, "T": 0.20},
    "self":         {"M": 0.30, "G": 0.25, "X": 0.25, "I": 0.20},
    "therapist":    {"S": 0.30, "E": 0.30, "P": 0.20, "N": 0.20},
    "pedagogue":    {"L": 0.30, "G": 0.25, "M": 0.25, "C": 0.20},
    "builder":      {"M": 0.30, "A": 0.30, "P": 0.25, "T": 0.15},
    "entrepreneur": {"P": 0.30, "A": 0.25, "R": 0.25, "G": 0.20},
    "synthesist":   {"M": 0.30, "I": 0.25, "X": 0.25, "S": 0.20},
}


def normalize_rank(weights: dict) -> dict:
    sorted_d = sorted(weights, key=lambda d: weights[d], reverse=True)
    n = len(sorted_d)
    return {d: 1.0 - (i / (n - 1)) for i, d in enumerate(sorted_d)}


def compute_deltas(w_reported: dict, w_inferred: dict) -> dict:
    r1 = normalize_rank(w_reported)
    r2 = normalize_rank(w_inferred)
    return {d: round(abs(r1[d] - r2[d]), 3) for d in DIMS}


def atom_activation(deltas: dict) -> dict:
    result = {}
    for atom, dw in ATOM_14D.items():
        total = sum(dw.values())
        act = sum(dw.get(d, 0) * deltas.get(d, 0) for d in DIMS) / total
        result[atom] = round(act, 3)
    return result


def load_latest_owner_weekly() -> dict | None:
    pw = kernel_dir() / "library" / "measurements" / f"{owner()}_weekly.md"
    if not pw.exists():
        return None
    latest = {}
    for line in pw.read_text().splitlines():
        if line.startswith("| 2026-"):
            parts = [p.strip() for p in line.split("|")]
            vals = [p for p in parts if p][1:15]  # skip date, take 14 dims
            if len(vals) == 14 and all(v.isdigit() for v in vals):
                latest = {DIMS[i]: int(vals[i]) for i in range(14)}
    return latest if latest else None


def load_posterior() -> dict | None:
    """Load Bayesian posterior from unified posterior store.

    Fallback chain:
      1. posterior_cache.json (real-time, updated by atom_swarm + fep)
      2. temporal_store.json (Phil's trajectory)
      3. trained_configs_full.json (batch training average)
      4. None → uniform
    """
    # Primary: unified posterior cache
    cache = kernel_dir() / ".claude" / "lenin" / "posterior_cache.json"
    if cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            # v3: prefer blended (session + long-term) over raw long-term
            session_info = data.get("session", {})
            if session_info and session_info.get("posterior"):
                beta = min(0.7, session_info.get("n_observations", 0) / 20)
                long_w = data.get("posterior_14d", {})
                sess_w = session_info.get("posterior", {})
                if long_w and len(long_w) == 14:
                    blended = {}
                    for d in long_w:
                        blended[d] = (1 - beta) * long_w[d] + beta * sess_w.get(d, 1/14)
                    total = sum(blended.values())
                    return {d: blended[d]/total for d in blended}
            posterior = data.get("posterior_14d")
            if posterior and len(posterior) == 14:
                return posterior
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback 1: temporal store
    ts = kernel_dir() / "library" / "formal" / "python" / "temporal_store.json"
    if ts.exists():
        try:
            store = json.loads(ts.read_text(encoding="utf-8"))
            for uid in [owner(), "owner"]:
                entries = store.get("users", {}).get(uid, [])
                if entries:
                    w = entries[-1].get("weights_14d", {})
                    if w and len(w) == 14:
                        return w
        except Exception:
            pass

    # Fallback 2: trained configs average
    tc = kernel_dir() / "library" / "formal" / "python" / "trained_configs_full.json"
    if tc.exists():
        try:
            configs = json.loads(tc.read_text(encoding="utf-8"))
            if configs:
                avg = {d: 0.0 for d in DIMS}
                for c in configs.values():
                    wi = c.get("w_inferred", {})
                    for d in DIMS:
                        avg[d] += wi.get(d, 1.0 / 14)
                n = len(configs)
                avg = {d: avg[d] / n for d in DIMS}
                total = sum(avg.values())
                if total > 0:
                    return {d: avg[d] / total for d in DIMS}
        except Exception:
            pass

    return None


def main():
    as_json = "--json" in sys.argv

    w_reported = load_latest_owner_weekly()
    w_inferred = load_posterior()

    if not w_reported:
        msg = "NO_DATA: weekly self-report пуст — нет данных для ∇d"
        if as_json:
            print(json.dumps({"error": msg}))
        else:
            print(msg)
        return

    if not w_inferred:
        msg = "NO_POSTERIOR: posterior_cache.json не найден — запусти card_weights.py"
        if as_json:
            print(json.dumps({"error": msg}))
        else:
            print(msg)
        return

    deltas = compute_deltas(w_reported, w_inferred)
    activations = atom_activation(deltas)
    blind = sorted([d for d in DIMS if deltas[d] > 0.4], key=lambda d: -deltas[d])
    understood = [d for d in DIMS if deltas[d] < 0.15]
    top_atoms = sorted(activations, key=activations.get, reverse=True)[:3]
    avg_d = round(sum(deltas.values()) / len(deltas), 3)

    result = {
        "avg_delta": avg_d,
        "blind_zones": blind,
        "understood": understood,
        "top_atoms": top_atoms,
        "deltas": deltas,
        "activations": activations,
        "w_reported": w_reported,
        "w_inferred": w_inferred,
    }

    # State proximity to optimal (from state_proximity.py)
    try:
        sp_path = Path(__file__).resolve().parent / "state_proximity.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location("state_proximity", sp_path)
        sp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sp)
        opt_data = sp.load_optimal()
        if opt_data:
            opt_profile = opt_data.get("dim_profile", {})
            curr = sp.load_session_dim_profile() or sp.load_current()
            if curr and opt_profile:
                prox = sp.compute_proximity(curr, opt_profile)
                result["state_proximity"] = prox
                tasks = sp.recommend_tasks(prox)
                result["task_recommendations"] = tasks[:3]
    except Exception:
        pass

    # Balance ODE — hemisphere balance + project conflicts
    try:
        bode_path = Path(__file__).resolve().parent / "balance_ode.py"
        spec = importlib.util.spec_from_file_location("balance_ode", bode_path)
        bode_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bode_mod)
        ode = bode_mod.lenin_default()
        if w_inferred:
            ode.inject_signal(w_inferred)
            ode.full_step(dt=1.0)
        bal = ode.hemisphere_balance()
        conflicts = ode.project_conflicts()
        result["balance"] = {
            "index": round(bal["balance_index"], 3),
            "dominant": bal["dominant"],
            "left": round(bal["left_sum"], 3),
            "right": round(bal["right_sum"], 3),
            "corpus": round(bal["corpus_sum"], 3),
        }
        if conflicts:
            result["balance"]["top_conflict"] = conflicts[0]
    except Exception as e:
        result["balance_error"] = str(e)

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"∇d checkpoint: avg={avg_d}, слепых={len(blind)}/{len(DIMS)}")
        if blind:
            print(f"  Слепые: {', '.join(f'{d}({DIM_NAMES[d]}={deltas[d]})' for d in blind)}")
        print(f"  Top атомы: {', '.join(f'{a}={activations[a]}' for a in top_atoms)}")

        prox = result.get("state_proximity", {})
        if prox:
            zone_labels = {"optimal": "ОПТИМАЛЬНОЕ", "near": "БЛИЗКО",
                           "degraded": "УХУДШЕНО", "far": "ДАЛЕКО"}
            zone = prox.get("zone", "?")
            cos = prox.get("cosine", 0)
            print(f"  Состояние: {zone_labels.get(zone, zone)} (cos={cos:.3f})")

        tasks = result.get("task_recommendations", [])
        if tasks:
            print(f"  Рекомендация задач:")
            for t in tasks[:3]:
                print(f"    [{t['priority']}] {t['action']}")

        bal = result.get("balance", {})
        if bal:
            print(f"  Balance: BI={bal['index']} {bal['dominant']} L={bal['left']} R={bal['right']} C={bal['corpus']}")
            tc = bal.get("top_conflict")
            if tc:
                print(f"  Конфликт: {tc}")

        if not tasks:
            print(f"  Рекомендация: активировать {top_atoms[0]} + уточнить {blind[0] if blind else '—'}")


if __name__ == "__main__":
    main()
