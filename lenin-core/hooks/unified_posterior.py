#!/usr/bin/env python3
"""unified_posterior.py — Unified Bayesian posterior for Ядро Ленин.

Two-layer architecture (v3, 2026-05-28):
  - LONG-TERM: cumulative Dirichlet with adaptive decay (T2-compliant)
  - SESSION: fast-adapting posterior, resets each session (T1→T2 per session)

Session posterior implements T4/T8 in practice:
  low total concentration → high contraction rate → fast adaptation.

All writes are PID-scoped + flock-protected for concurrent safety.
"""
from __future__ import annotations

import fcntl
import json
import math
import os
import tempfile
from datetime import datetime
from pathlib import Path

from _paths import kernel_dir, owner

HOOKS_DIR = Path(__file__).resolve().parent
ROOT = kernel_dir()
_STORE_DIR = ROOT / ".claude" / "lenin"
_STORE_DIR.mkdir(parents=True, exist_ok=True)
STORE_PATH = _STORE_DIR / "posterior_cache.json"
LOCK_PATH = _STORE_DIR / "posterior_cache.lock"

DIMS = ["E", "C", "S", "P", "Ph", "T", "X", "M", "N", "A", "R", "I", "L", "G"]
N_DIMS = len(DIMS)

# Calibrated 2026-06-01: empirical from 136 transcripts, 50/50 blend with uniform (T1 guard)
BEHAVIORAL_PRIOR = {
    "E": 0.0846, "C": 0.0928, "S": 0.0577, "P": 0.1647,
    "Ph": 0.0436, "T": 0.0423, "X": 0.0356, "M": 0.1705,
    "N": 0.0413, "A": 0.0671, "R": 0.0569, "I": 0.0429,
    "L": 0.0466, "G": 0.0532,
}

DEFAULT_THRESHOLDS = {
    "curiosity": 0.36, "memory": 0.56, "state": 0.15,
    "gap-architect": 0.41, "verifier": 0.20, "forecaster": 0.47, "self": 0.34,
    "therapist": 0.45, "pedagogue": 0.47, "builder": 0.66,
    "entrepreneur": 0.42, "synthesist": 0.36,
}

MAX_SIGNAL_HISTORY = 200
EFFECTIVE_MEMORY_CAP = 500

# Session posterior config
SESSION_INITIAL_ALPHA = 1.0   # T1 max-entropy: all α_i = 1
SESSION_MAX_BETA = 0.7        # max session weight in blend
SESSION_RAMP_OBS = 20         # observations to reach full β


def _dirichlet_posterior(concentrations: dict[str, float]) -> dict[str, float]:
    total = sum(concentrations.values())
    if total <= 0:
        return {d: 1.0 / N_DIMS for d in DIMS}
    return {d: concentrations[d] / total for d in DIMS}


def _normalize_simplex(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        return {d: 1.0 / N_DIMS for d in DIMS}
    return {d: round(v / total, 6) for d, v in weights.items()}


def _atomic_write(path: Path, data: dict) -> None:
    pid = os.getpid()
    tmp = path.with_suffix(f".tmp.{pid}")
    lock = LOCK_PATH
    try:
        lock_fd = open(lock, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
    except OSError:
        pass
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def _prior_to_concentrations(prior: dict[str, float], strength: float = 20.0) -> dict[str, float]:
    return {d: prior.get(d, 1.0 / N_DIMS) * strength for d in DIMS}


class UnifiedPosterior:
    """Two-layer Bayesian posterior: long-term (slow) + session (fast).

    Blended: w_i = (1-β)*long_i + β*session_i
    β = min(0.7, session_obs / 20)
    """
    def __init__(self, session_id: str | None = None):
        self._session_id = session_id or self._detect_session_id()
        self._data = self._load_or_initialize()
        self._ensure_session_layer()

    def _detect_session_id(self) -> str:
        now = datetime.now()
        return f"{now.strftime('%Y-%m-%d')}_{now.hour:02d}"

    def _load_or_initialize(self) -> dict:
        if STORE_PATH.exists():
            try:
                data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
                if data.get("posterior_14d") and len(data["posterior_14d"]) == N_DIMS:
                    if "concentrations" not in data:
                        data["concentrations"] = self._migrate_to_concentrations(data)
                    return data
            except (json.JSONDecodeError, OSError):
                pass

        concentrations = self._init_concentrations_from_fallbacks()
        posterior = _dirichlet_posterior(concentrations)
        now = datetime.now().isoformat()
        return {
            "version": "3.0",
            "user_id": "phil",
            "last_updated": now,
            "posterior_14d": posterior,
            "concentrations": concentrations,
            "signal_history": [],
            "atom_thresholds": dict(DEFAULT_THRESHOLDS),
            "calibration": {
                "n_prompts_processed": 0,
                "n_fep_observations": 0,
                "total_observations": 0,
                "last_phil_weekly": None,
                "avg_prediction_error": None,
                "last_threshold_calibration": None,
            },
            "metadata": {"initialized_at": now, "initialized_from": "fallback"},
        }

    def _ensure_session_layer(self) -> None:
        prev = self._data.get("session", {}).get("session_id")
        if prev != self._session_id:
            self._data["session"] = {
                "session_id": self._session_id,
                "started_at": datetime.now().isoformat(),
                "concentrations": {d: SESSION_INITIAL_ALPHA for d in DIMS},
                "posterior": {d: 1.0 / N_DIMS for d in DIMS},
                "n_observations": 0,
            }

    def _migrate_to_concentrations(self, data: dict) -> dict[str, float]:
        w = data.get("posterior_14d", {})
        n_obs = data.get("calibration", {}).get("n_prompts_processed", 0)
        strength = max(20.0, n_obs * 2.0)
        if "total_observations" not in data.get("calibration", {}):
            data["calibration"]["total_observations"] = n_obs
        return _prior_to_concentrations(w, strength)

    def _init_concentrations_from_fallbacks(self) -> dict[str, float]:
        prior = dict(BEHAVIORAL_PRIOR)
        source = "behavioral_prior"

        ts = ROOT / "library" / "formal" / "python" / "temporal_store.json"
        if ts.exists():
            try:
                store = json.loads(ts.read_text(encoding="utf-8"))
                for uid in [owner(), "owner"]:
                    entries = store.get("users", {}).get(uid, [])
                    if entries:
                        w = entries[-1].get("weights_14d", {})
                        if w and len(w) == N_DIMS:
                            prior = w
                            source = f"temporal_store:{uid}"
                            break
            except Exception:
                pass

        tc = ROOT / "library" / "formal" / "python" / "trained_configs_full.json"
        if tc.exists() and source == "behavioral_prior":
            try:
                configs = json.loads(tc.read_text(encoding="utf-8"))
                if configs:
                    avg = {d: 0.0 for d in DIMS}
                    for c in configs.values():
                        wi = c.get("w_inferred", {})
                        for d in DIMS:
                            avg[d] += wi.get(d, 1.0 / N_DIMS)
                    n = len(configs)
                    avg = {d: avg[d] / n for d in DIMS}
                    total = sum(avg.values())
                    if total > 0:
                        prior = {d: avg[d] / total for d in DIMS}
                        source = "trained_configs_average"
            except Exception:
                pass

        result = _normalize_simplex(prior)
        return _prior_to_concentrations(result, strength=20.0)

    # ─── Update mechanics ───

    def _compute_decay(self) -> float:
        c = self._data["calibration"].get("total_observations", 0)
        c_eff = min(c, EFFECTIVE_MEMORY_CAP)
        return 1.0 - 1.0 / (c_eff + 10.0)

    def _session_beta(self) -> float:
        n = self._data.get("session", {}).get("n_observations", 0)
        return min(SESSION_MAX_BETA, n / SESSION_RAMP_OBS)

    def _conjugate_update(self, counts: dict[str, float]) -> None:
        # Long-term
        gamma = self._compute_decay()
        conc = self._data["concentrations"]
        for d in DIMS:
            conc[d] = conc[d] * gamma + counts.get(d, 0) + 0.01
        total_alpha = sum(conc.values())
        max_alpha = EFFECTIVE_MEMORY_CAP * N_DIMS
        if total_alpha > max_alpha:
            scale = max_alpha / total_alpha
            for d in DIMS:
                conc[d] *= scale
        self._data["posterior_14d"] = _dirichlet_posterior(conc)
        self._data["calibration"]["total_observations"] = (
            self._data["calibration"].get("total_observations", 0) + 1
        )

        # Session
        session = self._data.get("session", {})
        if session:
            sc = session.get("concentrations", {d: SESSION_INITIAL_ALPHA for d in DIMS})
            for d in DIMS:
                sc[d] = sc.get(d, SESSION_INITIAL_ALPHA) + counts.get(d, 0)
            session["concentrations"] = sc
            session["posterior"] = _dirichlet_posterior(sc)
            session["n_observations"] = session.get("n_observations", 0) + 1

    def update_from_swarm(self, dim_hits: dict, text_len: int,
                          activated_atoms: list[str] | None = None) -> dict[str, float]:
        scale = min(2.0, text_len / 200.0) if text_len > 0 else 0.5
        counts = {d: dim_hits.get(d, 0) * scale for d in DIMS}
        self._conjugate_update(counts)

        entry = {
            "ts": datetime.now().isoformat(),
            "source": "atom_swarm",
            "dim_hits": {d: dim_hits.get(d, 0) for d in DIMS},
            "text_len": text_len,
            "activated_atoms": activated_atoms or [],
        }
        self._data["signal_history"].append(entry)
        self._data["signal_history"] = self._data["signal_history"][-MAX_SIGNAL_HISTORY:]
        self._data["calibration"]["n_prompts_processed"] += 1
        self._data["last_updated"] = datetime.now().isoformat()
        self.save()

        if self._data["calibration"]["n_prompts_processed"] % 50 == 0:
            self.calibrate_thresholds()

        return dict(self._data["posterior_14d"])

    def update_from_fep(self, prediction: str, actual: str,
                        error: float | None, atom: str | None) -> None:
        entry = {
            "ts": datetime.now().isoformat(),
            "source": "fep_observe",
            "prediction": prediction[:200],
            "actual": actual[:200],
            "error": error,
            "atom": atom,
        }
        self._data["signal_history"].append(entry)
        self._data["signal_history"] = self._data["signal_history"][-MAX_SIGNAL_HISTORY:]
        self._data["calibration"]["n_fep_observations"] += 1

        if error is not None:
            old_avg = self._data["calibration"].get("avg_prediction_error")
            n = self._data["calibration"]["n_fep_observations"]
            if old_avg is not None:
                self._data["calibration"]["avg_prediction_error"] = round(
                    old_avg + (error - old_avg) / n, 4)
            else:
                self._data["calibration"]["avg_prediction_error"] = round(error, 4)

        self._data["last_updated"] = datetime.now().isoformat()
        self.save()

    def update_from_weekly(self, likert: dict[str, int]) -> None:
        total = sum(likert.values())
        if total <= 0:
            return
        w_reported = _normalize_simplex({d: likert.get(d, 5) for d in DIMS})
        counts = {d: w_reported[d] * 10.0 for d in DIMS}
        self._conjugate_update(counts)
        self._data["calibration"]["last_phil_weekly"] = datetime.now().isoformat()
        self._data["last_updated"] = datetime.now().isoformat()
        self.save()

    # ─── Read methods ───

    def get_posterior(self) -> dict[str, float]:
        return dict(self._data["posterior_14d"])

    def get_session_posterior(self) -> dict[str, float]:
        session = self._data.get("session", {})
        return dict(session.get("posterior", {d: 1.0 / N_DIMS for d in DIMS}))

    def get_blended_posterior(self) -> dict[str, float]:
        beta = self._session_beta()
        long_w = self.get_posterior()
        sess_w = self.get_session_posterior()
        blended = {}
        for d in DIMS:
            blended[d] = (1 - beta) * long_w.get(d, 1 / N_DIMS) + beta * sess_w.get(d, 1 / N_DIMS)
        return _normalize_simplex(blended)

    def get_session_info(self) -> dict:
        session = self._data.get("session", {})
        return {
            "session_id": session.get("session_id", "?"),
            "n_observations": session.get("n_observations", 0),
            "beta": self._session_beta(),
            "session_posterior": self.get_session_posterior(),
            "long_term_posterior": self.get_posterior(),
            "blended_posterior": self.get_blended_posterior(),
        }

    def get_concentrations(self) -> dict[str, float]:
        return dict(self._data.get("concentrations", {}))

    def get_atom_thresholds(self) -> dict[str, float]:
        thresholds = self._data.get("atom_thresholds", {})
        return dict(thresholds) if thresholds else dict(DEFAULT_THRESHOLDS)

    def get_signal_count(self) -> int:
        return self._data["calibration"].get("n_prompts_processed", 0)

    def get_fep_count(self) -> int:
        return self._data["calibration"].get("n_fep_observations", 0)

    # ─── Threshold calibration ───

    def calibrate_thresholds(self) -> dict[str, float]:
        history = self._data.get("signal_history", [])
        swarm_events = [h for h in history if h.get("source") == "atom_swarm"]
        if len(swarm_events) < 10:
            return self.get_atom_thresholds()

        recent = swarm_events[-100:]
        n = len(recent)

        activation_counts: dict[str, int] = {}
        for atom_name in DEFAULT_THRESHOLDS:
            activation_counts[atom_name] = sum(
                1 for e in recent if atom_name in e.get("activated_atoms", []))

        baseline_atoms = {"curiosity", "memory", "verifier"}
        new_thresholds = {}
        for atom, default_t in DEFAULT_THRESHOLDS.items():
            rate = activation_counts.get(atom, 0) / n if n > 0 else 0
            old_t = self._data["atom_thresholds"].get(atom, default_t)
            target = 0.70 if atom in baseline_atoms else 0.30

            if rate > target + 0.10:
                delta = min(0.05, (rate - target) * 0.3)
                new_t = round(min(0.50, old_t + delta), 3)
            elif rate < target - 0.10 and rate > 0:
                delta = min(0.05, (target - rate) * 0.3)
                new_t = round(max(0.02, old_t - delta), 3)
            elif rate == 0:
                new_t = default_t
            else:
                new_t = old_t
            new_thresholds[atom] = new_t

        self._data["atom_thresholds"] = new_thresholds
        self._data["calibration"]["last_threshold_calibration"] = datetime.now().isoformat()
        self.save()
        return new_thresholds

    # ─── Rebalance ───

    def rebalance(self, blend: float = 0.3) -> dict[str, float]:
        w = self._data["posterior_14d"]
        blended = {}
        for d in DIMS:
            blended[d] = (1 - blend) * w.get(d, 1 / N_DIMS) + blend * BEHAVIORAL_PRIOR.get(d, 1 / N_DIMS)
        blended = _normalize_simplex(blended)
        self._data["concentrations"] = _prior_to_concentrations(blended, strength=20.0)
        self._data["posterior_14d"] = blended
        self._data["last_updated"] = datetime.now().isoformat()
        self.save()
        return blended

    # ─── Persistence ───

    def save(self) -> None:
        try:
            _atomic_write(STORE_PATH, self._data)
        except OSError:
            pass

    # ─── Health ───

    def entropy(self, weights: dict[str, float] | None = None) -> float:
        w = weights or self._data["posterior_14d"]
        return -sum(p * math.log2(p) for p in w.values() if p > 0)

    def kl_to_uniform(self, weights: dict[str, float] | None = None) -> float:
        h_max = math.log2(N_DIMS)
        return round(h_max - self.entropy(weights), 4)

    # ─── Semantic novelty (Konayev extension #1) ───

    def semantic_novelty(self, before: dict[str, float] | None = None) -> float:
        """KL(posterior_after || posterior_before) — how much new information
        the last exchange added. High = genuine thinking. Low = interpolation.

        Interpreting Konayev: "meaning = entropy change".
        If posterior didn't move, the answer didn't contain new meaning.
        """
        p = before or self._data.get("_prev_posterior", self._data["posterior_14d"])
        q = self._data["posterior_14d"]
        kl = 0.0
        for d in DIMS:
            p_i = max(p.get(d, 1 / N_DIMS), 1e-10)
            q_i = max(q.get(d, 1 / N_DIMS), 1e-10)
            kl += p_i * math.log2(p_i / q_i)
        return round(kl, 4)

    def snapshot_posterior(self) -> None:
        """Save current posterior as 'before' snapshot for next novelty calc."""
        self._data["_prev_posterior"] = dict(self._data["posterior_14d"])
        self.save()

    def novelty_label(self, kl: float | None = None) -> str:
        """Human-readable label for novelty score."""
        if kl is None:
            kl = self.semantic_novelty()
        if kl < 0.01:
            return "interpolation"
        elif kl < 0.05:
            return "clarification"
        elif kl < 0.15:
            return "insight"
        else:
            return "breakthrough"

    # ─── Domain-specific posterior (Konayev extension #2) ───

    DOMAIN_KEYWORDS = {
        "therapy": ['пациент', 'терапи', 'сесси', 'тревог', 'депресс', 'травм',
                     'аддикц', 'эмпати', 'клиент', 'психотерап', 'CBT', 'MBCT',
                     'трансфер', 'контрперенос', 'сопротивлен', 'абьюз', 'границ'],
        "business": ['бюджет', 'прибыл', 'ROI', 'масштаб', 'выручк', 'инвести',
                      'рынок', 'конкурент', 'партнёр', 'договор', 'миллион', 'FREEC',
                      'Зависть', 'Полдень', 'Полночь', 'Лапшин', 'alignment',
                      'подрядчик', 'команд', 'метрик', 'воронк', 'конверси'],
        "personal": ['мам', 'пап', 'бабушк', 'сын', 'доч', 'семь', 'люблю',
                      'боюсь', 'устал', 'хочу', 'мечт', 'счасть', 'одиночество',
                      'сон', 'здоров', 'спорт', 'музык', 'книг'],
    }

    def _detect_domain(self, text: str) -> str | None:
        """Detect which domain a prompt belongs to."""
        tl = text.lower()
        scores = {}
        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            scores[domain] = sum(tl.count(kw) for kw in keywords)
        if not scores or max(scores.values()) == 0:
            return None
        best = max(scores, key=scores.get)
        if scores[best] < 2:
            return None
        return best

    def update_domain_posterior(self, domain: str, counts: dict[str, float]) -> None:
        """Update a domain-specific posterior (separate from main)."""
        if "domain_posteriors" not in self._data:
            self._data["domain_posteriors"] = {}
        dp = self._data["domain_posteriors"]

        if domain not in dp:
            dp[domain] = {
                "concentrations": {d: SESSION_INITIAL_ALPHA for d in DIMS},
                "posterior": {d: 1.0 / N_DIMS for d in DIMS},
                "n_observations": 0,
                "cracks": [],
            }

        dom = dp[domain]
        conc = dom["concentrations"]
        for d in DIMS:
            conc[d] = conc.get(d, SESSION_INITIAL_ALPHA) + counts.get(d, 0)
        dom["posterior"] = _dirichlet_posterior(conc)
        dom["n_observations"] = dom.get("n_observations", 0) + 1

    def detect_cracks(self) -> list[dict]:
        """Find dimensions where domain posteriors diverge significantly."""
        dp = self._data.get("domain_posteriors", {})
        if len(dp) < 2:
            return []
        domains = list(dp.keys())
        cracks = []
        for d in DIMS:
            vals = {dom: dp[dom]["posterior"].get(d, 1 / N_DIMS) for dom in domains}
            max_v = max(vals.values())
            min_v = min(vals.values())
            ratio = max_v / min_v if min_v > 0.001 else float("inf")
            if ratio > 2.0:
                cracks.append({
                    "dim": d,
                    "ratio": round(ratio, 2),
                    "domains": vals,
                    "interpretation": f"{d} diverges {ratio:.1f}x across domains",
                })
        return cracks

    def summary(self) -> str:
        w = self._data["posterior_14d"]
        top3 = sorted(DIMS, key=lambda d: w.get(d, 0), reverse=True)[:3]
        conc = self._data.get("concentrations", {})
        total_conc = sum(conc.values()) if conc else 0
        total_obs = self._data["calibration"].get("total_observations", 0)

        sess_w = self.get_session_posterior()
        sess_top3 = sorted(DIMS, key=lambda d: sess_w.get(d, 0), reverse=True)[:3]
        n_sess = self._data.get("session", {}).get("n_observations", 0)
        beta = self._session_beta()

        blended = self.get_blended_posterior()
        blend_top3 = sorted(DIMS, key=lambda d: blended.get(d, 0), reverse=True)[:3]

        return (
            f"LONG-TERM: {', '.join(f'{d}={w[d]:.3f}' for d in top3)} | "
            f"Σα={total_conc:.0f} obs={total_obs}\n"
            f"SESSION:   {', '.join(f'{d}={sess_w[d]:.3f}' for d in sess_top3)} | "
            f"obs={n_sess} β={beta:.2f}\n"
            f"BLENDED:   {', '.join(f'{d}={blended[d]:.3f}' for d in blend_top3)} | "
            f"H_long={self.entropy():.3f} H_sess={self.entropy(sess_w):.3f} "
            f"I_kl_long={self.kl_to_uniform():.3f} I_kl_sess={self.kl_to_uniform(sess_w):.3f}"
        )


if __name__ == "__main__":
    up = UnifiedPosterior()
    print("=" * 60)
    print("ДВУХУРОВНЕВЫЙ POSTERIOR (v3)")
    print("=" * 60)
    print(up.summary())
