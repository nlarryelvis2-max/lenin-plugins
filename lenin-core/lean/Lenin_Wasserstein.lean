/-
  Lenin — Wasserstein-1 on the 14D simplex Δ¹³
  =====================================================================

  Новый ствол теорем T★. Связываем 1-Wasserstein расстояние W1 на симплексе
  Δ¹³ ⊂ ℝ¹⁴ с эмпирическим L¹-расстоянием, которое мы используем в
  `patient_timeline.py`, `directional_metric.py` и других пайплайнах.

  Ключевая идея:
    Для конечной поддержки вероятностных мер с равномерной поддерживающей
    метрикой (все пары измерений на расстоянии 1) выполнено

        W1(p, q) = TV(p, q) = (1/2) Σ_i |p_i - q_i|

    где TV — total variation. Эта эквивалентность даёт нам право переносить
    L¹-результаты с нашего дашборда в мета-теоретику оптимального транспорта.

  Структура файла:
    Section 1 — 14D simplex types (Lenin14, InSimplex14)
    Section 2 — W1 definition (uniform metric => TV)
    Section 3 — Symmetry, non-negativity, triangle  [PROVED]
    Section 4 — Identity of indiscernibles          [PROVED on simplex]
    Section 5 — Pinsker-type bound                  [conditional sorry]

  Статус: 4 теоремы доказаны (w1_symm, w1_nonneg, w1_triangle, w1_zero_iff),
  1 sorry (w1_le_sqrt_kl, conditional on classical Pinsker inequality).
-/

import Mathlib.Analysis.MeanInequalities
import Mathlib.Analysis.SpecialFunctions.Log.Basic
import Mathlib.Algebra.BigOperators.Group.Finset.Basic
import Mathlib.InformationTheory.KullbackLeibler.KLFun
import Mathlib.Tactic

open Real BigOperators Finset

namespace Lenin.Wasserstein

/- ============================================================ -/
/-  Section 1 — 14D simplex types                                 -/
/- ============================================================ -/

/-- Вектор весов на 14 измерениях Ленина (E, C, S, P, Ph, T, X, M, N, A, R, I, L, G). -/
abbrev Lenin14 := Fin 14 → ℝ

/-- Симплекс Δ¹³: неотрицательные координаты с суммой 1. -/
def InSimplex14 (p : Lenin14) : Prop :=
  (∀ i, 0 ≤ p i) ∧ (∑ i, p i = 1)

/- ============================================================ -/
/-  Section 2 — W1 = TV (uniform underlying metric)               -/
/- ============================================================ -/

/-- 1-Wasserstein расстояние на Δ¹³ с равномерной метрикой основания
    (все пары измерений на расстоянии 1). По классической теореме об
    оптимальном транспорте для конечной поддержки и uniform cost,

        W1(p, q) = TV(p, q) = (1/2) Σ_i |p_i - q_i|.

    Мы берём эту формулу за определение. Теоремы ниже устанавливают,
    что объект действительно является метрикой на Δ¹³. -/
noncomputable def W1 (p q : Lenin14) : ℝ :=
  (1 / 2) * ∑ i, |p i - q i|

/-- L¹-расстояние, как мы его используем в пайплайнах патиентов. -/
noncomputable def L1 (p q : Lenin14) : ℝ :=
  ∑ i, |p i - q i|

/-- Связь с эмпирическим L¹: W1 = L1 / 2. -/
theorem w1_eq_half_l1 (p q : Lenin14) : W1 p q = (1 / 2) * L1 p q := rfl

/- ============================================================ -/
/-  Section 3 — Symmetry, non-negativity, triangle                 -/
/- ============================================================ -/

/-- W1 симметрично: W1(p, q) = W1(q, p). -/
theorem w1_symm (p q : Lenin14) : W1 p q = W1 q p := by
  unfold W1
  congr 1
  apply Finset.sum_congr rfl
  intro i _
  exact abs_sub_comm (p i) (q i)

/-- W1 неотрицательно. -/
theorem w1_nonneg (p q : Lenin14) : 0 ≤ W1 p q := by
  unfold W1
  apply mul_nonneg
  · norm_num
  · apply Finset.sum_nonneg
    intro i _
    exact abs_nonneg _

/-- Неравенство треугольника для W1. Следует из поточечного |a - c| ≤ |a - b| + |b - c|
    после суммирования и умножения на 1/2. -/
theorem w1_triangle (p q r : Lenin14) : W1 p r ≤ W1 p q + W1 q r := by
  unfold W1
  rw [← mul_add]
  apply mul_le_mul_of_nonneg_left _ (by norm_num : (0:ℝ) ≤ 1/2)
  rw [← Finset.sum_add_distrib]
  apply Finset.sum_le_sum
  intro i _
  have h := abs_sub_le (p i) (q i) (r i)
  exact h

/- ============================================================ -/
/-  Section 4 — Identity of indiscernibles                        -/
/- ============================================================ -/

/-- Вспомогательная лемма: если сумма неотрицательных слагаемых равна нулю,
    то каждое слагаемое равно нулю. Прямое следствие Finset.sum_eq_zero_iff_of_nonneg. -/
private lemma sum_abs_eq_zero_iff (p q : Lenin14) :
    (∑ i, |p i - q i|) = 0 ↔ ∀ i ∈ (Finset.univ : Finset (Fin 14)), |p i - q i| = 0 := by
  apply Finset.sum_eq_zero_iff_of_nonneg
  intro i _
  exact abs_nonneg _

/-- W1 разделяет точки симплекса: W1(p, q) = 0 ⇔ p = q.

    На симплексе (или вообще на ℝ¹⁴) (1/2) Σ |p_i - q_i| = 0 эквивалентно
    тому, что каждая разность равна нулю, т.е. p_i = q_i для всех i. -/
theorem w1_zero_iff (p q : Lenin14) (hp : InSimplex14 p) (hq : InSimplex14 q) :
    W1 p q = 0 ↔ p = q := by
  -- гипотезы hp, hq не нужны для этой формулировки на ℝ¹⁴, но оставлены
  -- для соответствия каноничному виду метрики на симплексе.
  let _ := hp; let _ := hq
  unfold W1
  constructor
  · intro h
    have h1 : (∑ i, |p i - q i|) = 0 := by
      have : (1 / 2 : ℝ) * (∑ i, |p i - q i|) = 0 := h
      have hhalf : (1 / 2 : ℝ) ≠ 0 := by norm_num
      exact (mul_eq_zero.mp this).resolve_left hhalf
    rw [sum_abs_eq_zero_iff] at h1
    funext i
    have hi := h1 i (Finset.mem_univ i)
    have : p i - q i = 0 := abs_eq_zero.mp hi
    linarith
  · intro h
    subst h
    simp

/- ============================================================ -/
/-  Section 5 — Pinsker-type upper bound                          -/
/- ============================================================ -/

/-- KL-дивергенция для 14D вероятностей (с конвенцией 0·log 0 := 0 через negMulLog
    в эквивалентной форме p·log(p/q)). Здесь определяем как заглушку под Pinsker,
    подробное определение совпадает с `Lenin.klFromUniform` из Lenin_TStar. -/
noncomputable def KL (p q : Lenin14) : ℝ :=
  ∑ i, p i * Real.log (p i / q i)

/-- Gibbs inequality (нонотрицательность KL) на симплексе при положительной q.

    Используем поточечную лемму:  для p_i ≥ 0 и q_i > 0
        p_i - q_i ≤ p_i · log(p_i / q_i)
    (при p_i = 0 правая часть = 0, и -q_i ≤ 0; при p_i > 0 — следствие
    `Real.log_le_sub_one_of_pos` применённой к q_i/p_i.)

    Суммирование по симплексу даёт `Σ(p - q) = 0 ≤ KL`. -/
theorem kl_nonneg
    (p q : Lenin14) (hp : InSimplex14 p) (hq : InSimplex14 q)
    (hq_pos : ∀ i, 0 < q i) : 0 ≤ KL p q := by
  obtain ⟨hp_nn, hp_sum⟩ := hp
  obtain ⟨_hq_nn, hq_sum⟩ := hq
  -- Поточечная Gibbs-инеквалити
  have pointwise : ∀ i, p i - q i ≤ p i * Real.log (p i / q i) := by
    intro i
    rcases eq_or_lt_of_le (hp_nn i) with hpi | hpi
    · -- p i = 0: rhs = 0; lhs = -q i ≤ 0
      have : p i = 0 := hpi.symm
      rw [this]
      have hqi := le_of_lt (hq_pos i)
      simp; linarith
    · -- p i > 0: применяем log_le_sub_one_of_pos к q_i / p_i
      have hr : (0:ℝ) < q i / p i := div_pos (hq_pos i) hpi
      have hlog : Real.log (q i / p i) ≤ q i / p i - 1 :=
        Real.log_le_sub_one_of_pos hr
      -- log(p/q) = -log(q/p)
      have hflip : Real.log (p i / q i) = - Real.log (q i / p i) := by
        rw [← Real.log_inv]
        congr 1
        rw [inv_div]
      have hlower : 1 - q i / p i ≤ Real.log (p i / q i) := by
        rw [hflip]; linarith
      have hmul : p i * (1 - q i / p i) ≤ p i * Real.log (p i / q i) :=
        mul_le_mul_of_nonneg_left hlower (le_of_lt hpi)
      have hsimp : p i * (1 - q i / p i) = p i - q i := by
        field_simp
      linarith
  -- Σ (p i - q i) ≤ KL
  have hsum_le : (∑ i, (p i - q i)) ≤ ∑ i, p i * Real.log (p i / q i) :=
    Finset.sum_le_sum (fun i _ => pointwise i)
  -- Σ (p i - q i) = 1 - 1 = 0
  have hzero : (∑ i : Fin 14, (p i - q i)) = 0 := by
    rw [Finset.sum_sub_distrib, hp_sum, hq_sum]; ring
  unfold KL
  linarith

/-- KL равно нулю, если p = q (на положительном q). -/
theorem kl_self_eq_zero (p : Lenin14) (hp_pos : ∀ i, 0 < p i) : KL p p = 0 := by
  unfold KL
  apply Finset.sum_eq_zero
  intro i _
  rw [div_self (ne_of_gt (hp_pos i)), Real.log_one]
  ring

/-- **Мост к Mathlib `klFun`.** Стандартное представление KL как f-дивергенции:

        KL(p ‖ q) = Σ_i q_i · klFun(p_i / q_i)

    где `klFun(x) = x·log x + 1 − x` — функция Kullback-Leibler из
    `Mathlib.InformationTheory.KullbackLeibler.KLFun`. Это открывает доступ
    ко всему аппарату Mathlib для KL-дивергенции (convexity, monotonicity,
    f-divergence machinery), не переписывая её для нашего 14D случая.

    Доказательство — прямая алгебра: q · klFun(p/q) = p·log(p/q) + q − p,
    суммирование по симплексу даёт KL + 1 − 1 = KL. -/
theorem kl_eq_sum_q_klFun
    (p q : Lenin14) (hp : InSimplex14 p) (hq : InSimplex14 q)
    (hq_pos : ∀ i, 0 < q i) :
    KL p q = ∑ i, q i * InformationTheory.klFun (p i / q i) := by
  obtain ⟨_, hp_sum⟩ := hp
  obtain ⟨_, hq_sum⟩ := hq
  -- Поточечное равенство: q · klFun(p/q) = p·log(p/q) + q − p
  have step : ∀ i, q i * InformationTheory.klFun (p i / q i)
                  = p i * Real.log (p i / q i) + q i - p i := by
    intro i
    have hqi : q i ≠ 0 := ne_of_gt (hq_pos i)
    rw [InformationTheory.klFun_apply]
    field_simp
  -- Σ rhs = Σ (p·log + q − p) = Σ p·log + Σ q − Σ p = KL + 1 − 1 = KL
  have h1 : (∑ i, q i * InformationTheory.klFun (p i / q i))
          = ∑ i, (p i * Real.log (p i / q i) + q i - p i) :=
    Finset.sum_congr rfl (fun i _ => step i)
  have h2 : (∑ i, (p i * Real.log (p i / q i) + q i - p i))
          = (∑ i, p i * Real.log (p i / q i)) + (∑ i, q i) - (∑ i, p i) := by
    simp only [Finset.sum_add_distrib, Finset.sum_sub_distrib]
  unfold KL
  rw [h1, h2, hp_sum, hq_sum]
  ring

/-- **KL разделяет точки.** На положительном симплексе KL(p ‖ q) = 0 ⇔ p = q.

    Доказательство через мост `kl_eq_sum_q_klFun` + Mathlib:
    - klFun(x) ≥ 0 для x ≥ 0, и klFun(x) = 0 ⇔ x = 1 (`klFun_eq_zero_iff`).
    - q_i > 0 ⇒ q_i · klFun(p_i/q_i) = 0 ⇔ klFun(p_i/q_i) = 0 ⇔ p_i/q_i = 1 ⇔ p_i = q_i.
    - Сумма неотрицательных = 0 ⇔ каждое слагаемое = 0. -/
theorem kl_eq_zero_iff
    (p q : Lenin14) (hp : InSimplex14 p) (hq : InSimplex14 q)
    (hq_pos : ∀ i, 0 < q i) :
    KL p q = 0 ↔ p = q := by
  -- Каждое слагаемое неотрицательно
  have term_nonneg : ∀ i ∈ (Finset.univ : Finset (Fin 14)),
      0 ≤ q i * InformationTheory.klFun (p i / q i) := by
    intro i _
    have hpi : 0 ≤ p i / q i := div_nonneg (hp.1 i) (le_of_lt (hq_pos i))
    exact mul_nonneg (le_of_lt (hq_pos i))
      (InformationTheory.klFun_nonneg hpi)
  -- KL = Σ q · klFun(p/q)
  have hkl : KL p q = ∑ i, q i * InformationTheory.klFun (p i / q i) :=
    kl_eq_sum_q_klFun p q hp hq hq_pos
  constructor
  · intro h
    rw [hkl] at h
    -- Σ нонотрицательных = 0 ⇔ каждое = 0
    rw [Finset.sum_eq_zero_iff_of_nonneg term_nonneg] at h
    funext i
    have hi := h i (Finset.mem_univ i)
    -- q i ≠ 0, значит klFun(p i / q i) = 0
    have hqi_ne : q i ≠ 0 := ne_of_gt (hq_pos i)
    have hkl_term : InformationTheory.klFun (p i / q i) = 0 := by
      rcases mul_eq_zero.mp hi with h | h
      · exact absurd h hqi_ne
      · exact h
    -- klFun(x) = 0 ⇔ x = 1 на x ≥ 0
    have hpi_nn : 0 ≤ p i / q i := div_nonneg (hp.1 i) (le_of_lt (hq_pos i))
    have hratio : p i / q i = 1 :=
      (InformationTheory.klFun_eq_zero_iff hpi_nn).mp hkl_term
    -- p i / q i = 1 ⇒ p i = q i
    field_simp at hratio
    exact hratio
  · intro h
    subst h
    -- KL p p = 0 since each ratio is 1, klFun 1 = 0
    rw [hkl]
    apply Finset.sum_eq_zero
    intro i _
    rw [div_self (ne_of_gt (hq_pos i)), InformationTheory.klFun_one, mul_zero]

/-- **KL положительна, если p ≠ q.** Прямое следствие `kl_nonneg` + `kl_eq_zero_iff`. -/
theorem kl_pos_of_ne
    (p q : Lenin14) (hp : InSimplex14 p) (hq : InSimplex14 q)
    (hq_pos : ∀ i, 0 < q i) (hne : p ≠ q) :
    0 < KL p q := by
  have hnn : 0 ≤ KL p q := kl_nonneg p q hp hq hq_pos
  have hne0 : KL p q ≠ 0 := by
    intro h
    exact hne ((kl_eq_zero_iff p q hp hq hq_pos).mp h)
  exact lt_of_le_of_ne hnn (Ne.symm hne0)

/-- **Каждое слагаемое не превосходит KL.** Per-coordinate sanity bound:

        q_i · klFun(p_i / q_i)  ≤  KL(p ‖ q)

    Полезно для оценок, когда мы знаем малость KL и хотим заключить,
    что каждое отдельное отношение p_i/q_i близко к 1.

    Прямое следствие моста `kl_eq_sum_q_klFun` и нонотрицательности слагаемых
    через `Finset.single_le_sum`. -/
theorem term_le_kl
    (p q : Lenin14) (hp : InSimplex14 p) (hq : InSimplex14 q)
    (hq_pos : ∀ i, 0 < q i) (i : Fin 14) :
    q i * InformationTheory.klFun (p i / q i) ≤ KL p q := by
  rw [kl_eq_sum_q_klFun p q hp hq hq_pos]
  apply Finset.single_le_sum (f := fun j => q j * InformationTheory.klFun (p j / q j))
  · intro j _
    have hpj : 0 ≤ p j / q j := div_nonneg (hp.1 j) (le_of_lt (hq_pos j))
    exact mul_nonneg (le_of_lt (hq_pos j))
      (InformationTheory.klFun_nonneg hpj)
  · exact Finset.mem_univ i

/-- **Условный sorry [W★1].** Pinsker-style upper bound:

        W1(p, q) ≤ √(KL(p ‖ q) / 2)

    Это прямое следствие классического неравенства Пинскера

        TV(p, q) ≤ √(KL(p ‖ q) / 2)

    плюс наше тождество W1 = TV (uniform underlying metric). В Mathlib
    Пинскер на конечных вероятностных мерах формализован частично, но
    для произвольной поддержки 14D ещё нет готовой леммы. Оставляем
    sorry с явной зависимостью от `hPinsker`.

    Когда Mathlib даст `tv_le_sqrt_half_kl` для finite probability mass
    functions, доказательство закроется в одну строку. -/
theorem w1_le_sqrt_kl
    (p q : Lenin14) (_ : InSimplex14 p) (_ : InSimplex14 q)
    (hPinsker : (1/2) * (∑ i, |p i - q i|) ≤ Real.sqrt (KL p q / 2)) :
    W1 p q ≤ Real.sqrt (KL p q / 2) := by
  unfold W1
  exact hPinsker

/- ============================================================ -/
/-  Section 5b — Diameter bound on the simplex                    -/
/- ============================================================ -/

/-- W1 ограничено единицей на симплексе: W1(p, q) ≤ 1 для p, q ∈ Δ¹³.

    Доказательство: для p_i, q_i ≥ 0 имеем |p_i - q_i| ≤ p_i + q_i,
    откуда (1/2) Σ |p_i - q_i| ≤ (1/2)(Σ p_i + Σ q_i) = (1/2)(1 + 1) = 1.

    Это даёт явный диаметр симплекса в W1-метрике и используется как
    sanity-check для эмпирических дистанций в `directional_metric.py`. -/
theorem w1_le_one_on_simplex
    (p q : Lenin14) (hp : InSimplex14 p) (hq : InSimplex14 q) :
    W1 p q ≤ 1 := by
  obtain ⟨hp_nn, hp_sum⟩ := hp
  obtain ⟨hq_nn, hq_sum⟩ := hq
  unfold W1
  -- Σ |p i - q i| ≤ Σ (p i + q i)
  have hsum_le : (∑ i, |p i - q i|) ≤ ∑ i, (p i + q i) := by
    apply Finset.sum_le_sum
    intro i _
    have h1 : |p i - q i| ≤ |p i| + |q i| := abs_sub _ _
    have h2 : |p i| = p i := abs_of_nonneg (hp_nn i)
    have h3 : |q i| = q i := abs_of_nonneg (hq_nn i)
    linarith
  -- Σ (p i + q i) = Σ p i + Σ q i = 1 + 1 = 2
  have hsum_eq : (∑ i, (p i + q i)) = 2 := by
    rw [Finset.sum_add_distrib, hp_sum, hq_sum]; norm_num
  -- (1/2) * Σ |…| ≤ (1/2) * 2 = 1
  have : (1 / 2 : ℝ) * (∑ i, |p i - q i|) ≤ (1 / 2 : ℝ) * 2 := by
    apply mul_le_mul_of_nonneg_left _ (by norm_num : (0:ℝ) ≤ 1/2)
    linarith
  linarith

/- ============================================================ -/
/-  Section 6 — Bridge to L¹ pipelines                            -/
/- ============================================================ -/

/-- L¹ симметрично. -/
theorem l1_symm (p q : Lenin14) : L1 p q = L1 q p := by
  unfold L1
  apply Finset.sum_congr rfl
  intro i _
  exact abs_sub_comm (p i) (q i)

/-- L¹ неотрицательно. -/
theorem l1_nonneg (p q : Lenin14) : 0 ≤ L1 p q := by
  unfold L1
  apply Finset.sum_nonneg
  intro i _
  exact abs_nonneg _

/-- Триангль для L¹. -/
theorem l1_triangle (p q r : Lenin14) : L1 p r ≤ L1 p q + L1 q r := by
  unfold L1
  rw [← Finset.sum_add_distrib]
  apply Finset.sum_le_sum
  intro i _
  exact abs_sub_le (p i) (q i) (r i)

/-- L¹ разделяет точки: L1(p, q) = 0 ⇔ p = q. -/
theorem l1_zero_iff (p q : Lenin14) : L1 p q = 0 ↔ p = q := by
  unfold L1
  constructor
  · intro h
    rw [sum_abs_eq_zero_iff] at h
    funext i
    have hi := h i (Finset.mem_univ i)
    have : p i - q i = 0 := abs_eq_zero.mp hi
    linarith
  · intro h
    subst h
    simp

/-- L¹ ограничено двумя на симплексе: L1(p, q) ≤ 2 для p, q ∈ Δ¹³.
    Прямое следствие `w1_le_one_on_simplex` через `w1_eq_half_l1`. -/
theorem l1_le_two_on_simplex
    (p q : Lenin14) (hp : InSimplex14 p) (hq : InSimplex14 q) :
    L1 p q ≤ 2 := by
  have hw : W1 p q ≤ 1 := w1_le_one_on_simplex p q hp hq
  have heq : W1 p q = (1 / 2) * L1 p q := w1_eq_half_l1 p q
  linarith

end Lenin.Wasserstein
