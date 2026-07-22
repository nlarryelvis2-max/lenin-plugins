#!/usr/bin/env python3
"""
Естественное накопление разнообразия (не форсированная чистка).
Запускается на SessionStart. Применяет мягкое экспоненциальное старение
к signal_history: старые сигналы теряют вес с периодом полураспада ~10 дней,
очень старые (>45 дней) отсекаются. Это даёт новому разнообразию набирать
вес само, без стирания недавнего обучения.

Реализация решения Фила (2026-06-03): «дать разнообразию накопиться
естественно следующими сессиями» — оформлено как постоянный механизм.
"""
import json, math
from datetime import datetime
from pathlib import Path

CACHE = Path(__file__).parent / "posterior_cache.json"
HALFLIFE_DAYS = 10.0      # период полураспада веса сигнала
HARD_CAP_DAYS = 45.0      # старше — отсекаются
EXPLORE_FLOOR = 0.15      # минимальный uniform-подмес в posterior_14d

def main():
    if not CACHE.exists(): return
    try:
        d = json.loads(CACHE.read_text())
    except Exception:
        return

    now = datetime.now()
    sh = d.get("signal_history", [])
    if not isinstance(sh, list) or not sh:
        return

    kept, decayed_total, dropped = [], 0.0, 0
    for s in sh:
        ts = s.get("ts")
        if not ts:
            kept.append(s); continue
        try:
            age = (now - datetime.fromisoformat(ts)).total_seconds() / 86400.0
        except Exception:
            kept.append(s); continue
        if age > HARD_CAP_DAYS:
            dropped += 1
            continue
        # экспоненциальный вес по возрасту
        w = 0.5 ** (age / HALFLIFE_DAYS)
        s["decay_w"] = round(w, 4)
        decayed_total += w
        kept.append(s)

    d["signal_history"] = kept

    # σ-SOURCE против collapse (ОДЕ dP/dt = −k·P + σ, error_cycles_ode.md).
    # σ = последнее ЗДОРОВОЕ состояние (не uniform!). Здоровый постериор запоминается,
    # коллапс — лечится из памяти. Это источник, а не только тормоз распада.
    SIGMA_FLOOR = 30.0
    HEALTHY_IKL = 0.05    # выше — состояние здоровое, сохраняем как baseline
    COLLAPSE_IKL = 0.02   # ниже — коллапс, восстанавливаем из baseline
    post = d.get("posterior_14d")
    if isinstance(post, dict) and post:
        u = 1.0 / len(post)
        Hmax = math.log(len(post))
        H = -sum(v * math.log(v) for v in post.values() if v > 0)
        ikl = Hmax - H  # концентрация постериора

        # baseline: последний здоровый снапшот ИЛИ корпус-домен-постериор (grounded, не выдуман)
        def _corpus_baseline():
            try:
                dp = json.loads((CACHE.parent.parent.parent / "library/formal/python/domain_posteriors.json").read_text())
                dims = list(post.keys())
                acc = {k: 0.0 for k in dims}
                for dom in dp.values():
                    for k in dims: acc[k] += float(dom.get("means", {}).get(k, 0))
                tot = sum(acc.values()) or 1
                return {k: v / tot for k, v in acc.items()}
            except Exception:
                return None

        if ikl >= HEALTHY_IKL:
            # ЗДОРОВО → запомнить как σ-источник, лёгкий exploration-подмес
            d.setdefault("metadata", {})["baseline_posterior"] = post
            if decayed_total > SIGMA_FLOOR:
                mixed = {k: (1 - EXPLORE_FLOOR) * v + EXPLORE_FLOOR * u for k, v in post.items()}
                tot = sum(mixed.values()) or 1
                d["posterior_14d"] = {k: v / tot for k, v in mixed.items()}
        elif ikl < COLLAPSE_IKL:
            # КОЛЛАПС → восстановить из baseline (σ-источник), НЕ оставлять uniform
            base = d.get("metadata", {}).get("baseline_posterior") or _corpus_baseline()
            if base and abs(sum(base.values()) - 1.0) < 0.1:
                # тянем текущий (уплывший) к последнему здоровому: 70% baseline + 30% текущий
                restored = {k: 0.7 * base.get(k, u) + 0.3 * post.get(k, u) for k in post}
                tot = sum(restored.values()) or 1
                d["posterior_14d"] = {k: v / tot for k, v in restored.items()}
                d.setdefault("metadata", {})["collapse_repaired"] = now.isoformat()

    d.setdefault("metadata", {})["last_diversity_decay"] = now.isoformat()
    d["metadata"]["effective_signals"] = round(decayed_total, 2)

    CACHE.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    print(f"[diversity_decay] сигналов: {len(kept)} (отсечено {dropped}), "
          f"эффективный вес {decayed_total:.1f}, halflife={HALFLIFE_DAYS}д")

if __name__ == "__main__":
    main()
