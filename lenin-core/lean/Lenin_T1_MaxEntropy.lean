/-
  Lenin — T1 : Uniform 1/N is the unique max-entropy prior
  =========================================================

  Научное утверждение (Джейнс, адаптированное к Ленину):
    Пусть в ядре Ленин 13.0 имеется 11 категорий, в k-й из них N_k весов.
    Пространство допустимых весов внутри категории — симплекс Δ^{N_k − 1}.
    Совокупное пространство — M = ∏_{k=1}^{11} Δ^{N_k − 1}.
    Тогда равномерное распределение w_{k,i} = 1/N_k является ЕДИНСТВЕННЫМ
    максимумом суммарной энтропии Шеннона H(w) = Σ_k Σ_i (-w_{k,i} log w_{k,i})
    на M. Это превращает хардкод 1/303, 1/102, … в weight_systems.py из магии
    в max-entropy prior (принцип максимума энтропии).

  Стратегия доказательства:
    1) Для фиксированного k строгая вогнутость `Real.negMulLog` + Jensen дают
       единственный максимум `∑ i, negMulLog (w k i)` в точке w k i = 1/N k.
    2) Сумма по k сепарабельна ⇒ максимум суммы = сумма максимумов.

  Статус: скелет (утверждения). Доказательства через Mathlib4 v4.28.
-/

import Mathlib.Analysis.SpecialFunctions.Log.Basic
import Mathlib.Analysis.MeanInequalities
import Mathlib.Analysis.Convex.SpecificFunctions.Basic
import Mathlib.Analysis.SpecialFunctions.Log.NegMulLog
-- Path corrected by Aristotle (v4.28): NegMulLog module relocated under .Log.

open Real BigOperators Finset

namespace LeninT1

/-- Категория Ленина: конечный набор признаков размера `N`. -/
abbrev Category (N : ℕ) := Fin N → ℝ

/-- Симплекс в категории: неотрицательные веса с суммой 1. -/
def InSimplex {N : ℕ} (w : Category N) : Prop :=
  (∀ i, 0 ≤ w i) ∧ (∑ i, w i = 1)

/-- Энтропия Шеннона внутри одной категории. -/
noncomputable def entropy {N : ℕ} (w : Category N) : ℝ :=
  ∑ i, Real.negMulLog (w i)

/-- Равномерное распределение внутри категории. -/
noncomputable def uniform (N : ℕ) : Category N :=
  fun _ => (1 : ℝ) / N

/-- Равномерное распределение лежит в симплексе (при N > 0). -/
lemma uniform_in_simplex {N : ℕ} (hN : 0 < N) :
    InSimplex (uniform N) := by
  refine ⟨?_, ?_⟩
  · intro i
    unfold uniform
    positivity
  · unfold uniform
    have hNne : (N : ℝ) ≠ 0 := Nat.cast_ne_zero.mpr hN.ne'
    rw [Finset.sum_const, Finset.card_univ, Fintype.card_fin, nsmul_eq_mul]
    field_simp

/-- **Атомарная лемма, доказанная Aristotle**:
    энтропия Шеннона на симплексе в `Fin N` не превосходит `log N`.
    Доказательство: Jensen для `Real.concaveOn_negMulLog` с равномерными весами `1/N`.
    См. `library/formal/aristotle/result/.../EntropyMax.lean`. -/
theorem shannonEntropy_le_log_card {N : ℕ} (hN : 0 < N)
    (w : Fin N → ℝ) (hw_nn : ∀ i, 0 ≤ w i) (hw_sum : ∑ i, w i = 1) :
    (∑ i, Real.negMulLog (w i)) ≤ Real.log N := by
  have hNne : (N : ℝ) ≠ 0 := Nat.cast_ne_zero.mpr hN.ne'
  have hNpos : (0 : ℝ) < N := by exact_mod_cast hN
  have hNinv_nn : (0 : ℝ) ≤ (N : ℝ)⁻¹ := inv_nonneg.mpr hNpos.le
  -- Jensen с равномерными весами (N⁻¹) по каждой координате
  have h_jensen : (∑ i : Fin N, ((N : ℝ)⁻¹) * Real.negMulLog (w i)) ≤
      Real.negMulLog (∑ i : Fin N, ((N : ℝ)⁻¹) * w i) := by
    refine Real.concaveOn_negMulLog.le_map_sum
      (fun i _ => hNinv_nn) ?_ (fun i _ => hw_nn i)
    simp [Finset.sum_const, Finset.card_univ, Fintype.card_fin,
          mul_inv_cancel₀ hNne]
  -- Упрощаем правую часть: (N⁻¹) · ∑ w i = N⁻¹
  have h_sum_simp : (∑ i : Fin N, ((N : ℝ)⁻¹) * w i) = (N : ℝ)⁻¹ := by
    rw [← Finset.mul_sum, hw_sum, mul_one]
  rw [h_sum_simp] at h_jensen
  -- negMulLog (N⁻¹) = N⁻¹ · log N
  have h_neg : Real.negMulLog ((N : ℝ)⁻¹) = (N : ℝ)⁻¹ * Real.log N := by
    unfold Real.negMulLog
    rw [Real.log_inv]; ring
  rw [h_neg, ← Finset.mul_sum] at h_jensen
  -- Умножаем обе стороны на N ≥ 0
  have h_mul := mul_le_mul_of_nonneg_left h_jensen hNpos.le
  rw [← mul_assoc, ← mul_assoc, mul_inv_cancel₀ hNne, one_mul, one_mul] at h_mul
  exact h_mul

/-- Энтропия равномерного = log N. Вынесено как отдельная лемма для переиспользования
    в T★ (раньше было частью `entropy_le_uniform` как `h_right`). -/
theorem entropy_uniform_eq_log_card {N : ℕ} (hN : 0 < N) :
    entropy (uniform N) = Real.log N := by
  unfold entropy uniform
  have hNne : (N : ℝ) ≠ 0 := Nat.cast_ne_zero.mpr hN.ne'
  simp [Real.negMulLog, Finset.sum_const, Finset.card_univ, Fintype.card_fin,
        Real.log_inv, hNne]

/-- **Лемма 1 (внутри категории).**
    На симплексе энтропия максимизируется равномерным распределением.
    Следствие `shannonEntropy_le_log_card` + вычисление `entropy (uniform N) = log N`. -/
theorem entropy_le_uniform {N : ℕ} (hN : 0 < N)
    (w : Category N) (hw : InSimplex w) :
    entropy w ≤ entropy (uniform N) := by
  -- Левая часть: ∑ negMulLog (w i) ≤ log N  (Aristotle)
  have h_left : entropy w ≤ Real.log N := by
    unfold entropy
    exact shannonEntropy_le_log_card hN w hw.1 hw.2
  -- Правая часть: entropy (uniform N) = log N
  have h_right : entropy (uniform N) = Real.log N := by
    unfold entropy uniform
    have hNpos : (0 : ℝ) < N := by exact_mod_cast hN
    have hNne : (N : ℝ) ≠ 0 := ne_of_gt hNpos
    simp [Real.negMulLog, Finset.sum_const, Finset.card_univ, Fintype.card_fin,
          Real.log_inv, hNne]
  linarith [h_left, h_right]

/-- **Атомарная лемма, доказанная Aristotle**: случай равенства.
    `entropy w = log N ↔ w = uniformDist N`.
    Использует строгую вогнутость `Real.strictConcaveOn_negMulLog` +
    `StrictConcaveOn.lt_map_sum`. -/
theorem shannonEntropy_eq_log_card_iff {N : ℕ} (hN : 0 < N)
    (w : Fin N → ℝ) (hw_nn : ∀ i, 0 ≤ w i) (hw_sum : ∑ i, w i = 1) :
    (∑ i, Real.negMulLog (w i)) = Real.log N ↔ w = fun _ => (1 : ℝ) / N := by
  constructor
  · intro h_eq
    have h_eq_uniform : ∀ i, w i = 1 / N := by
      contrapose! h_eq
      have h_jensen : (∑ i : Fin N, (1 / (N : ℝ)) * Real.negMulLog (w i)) <
          Real.negMulLog ((∑ i : Fin N, (1 / (N : ℝ)) * w i)) := by
        have h_sc : StrictConcaveOn ℝ (Set.Ici 0) Real.negMulLog :=
          strictConcaveOn_negMulLog
        apply_rules [h_sc.lt_map_sum]; aesop
        · simp +decide [hN.ne']
        · grind +revert
        · by_cases h_eq : ∀ i j, w i = w j
          · simp_all +decide [← h_eq ⟨0, hN⟩]
            exact h_eq.2 (eq_inv_of_mul_eq_one_right hw_sum)
          · aesop
      simp_all +decide [← Finset.mul_sum _ _ _]
      unfold Real.negMulLog at *
      rw [Real.log_inv] at h_jensen
      nlinarith [inv_pos.mpr (by positivity : 0 < (N : ℝ)),
                 mul_inv_cancel₀ (by positivity : (N : ℝ) ≠ 0)]
    exact funext h_eq_uniform
  · rintro rfl
    simp +decide [Real.negMulLog, hN.ne']

/-- **Лемма 2 (единственность внутри категории).**
    Равенство достигается только на равномерном. Следствие
    `shannonEntropy_eq_log_card_iff` + вычисление `entropy (uniform N) = log N`. -/
theorem entropy_eq_uniform_iff {N : ℕ} (hN : 0 < N)
    (w : Category N) (hw : InSimplex w) :
    entropy w = entropy (uniform N) ↔ w = uniform N := by
  have h_right : entropy (uniform N) = Real.log N := by
    unfold entropy uniform
    have hNne : (N : ℝ) ≠ 0 := Nat.cast_ne_zero.mpr hN.ne'
    simp [Real.negMulLog, Finset.sum_const, Finset.card_univ, Fintype.card_fin,
          Real.log_inv, hNne]
  constructor
  · intro h
    rw [h_right] at h
    have := (shannonEntropy_eq_log_card_iff hN w hw.1 hw.2).mp h
    funext i
    unfold uniform
    exact congrFun this i
  · intro h
    rw [h]

/-- **Атомарная лемма, доказанная Aristotle**: точечное равенство из
    равенства сумм при поточечном ≤. -/
theorem sum_eq_iff_pointwise {α : Type*} {s : Finset α} {f g : α → ℝ}
    (hfg : ∀ i ∈ s, f i ≤ g i)
    (hsum : ∑ i ∈ s, f i = ∑ i ∈ s, g i) :
    ∀ i ∈ s, f i = g i := by
  intro i hi
  refine le_antisymm (hfg i hi) ?_
  have h_nonneg : ∀ a ∈ s, 0 ≤ g a - f a := fun a ha => sub_nonneg.2 (hfg a ha)
  have h_sum_nonneg : ∑ a ∈ s, (g a - f a) = 0 := by
    rw [Finset.sum_sub_distrib]; linarith [hsum]
  have h_each_zero : g i - f i = 0 := by
    have h_le : g i - f i ≤ ∑ a ∈ s, (g a - f a) :=
      Finset.single_le_sum h_nonneg hi
    linarith [h_nonneg i hi]
  linarith [h_each_zero]

/-- Конфигурация Ленина: 11 категорий, k-я размера `N k`. -/
structure LeninShape where
  K : ℕ
  N : Fin K → ℕ
  hN : ∀ k, 0 < N k

/-- Совместный вектор весов по всем категориям. -/
def JointWeights (shape : LeninShape) : Type :=
  (k : Fin shape.K) → Category (shape.N k)

/-- Допустимый совместный вектор — каждая компонента в симплексе. -/
def JointInSimplex {shape : LeninShape} (w : JointWeights shape) : Prop :=
  ∀ k, InSimplex (w k)

/-- Совокупная энтропия по всем категориям. -/
noncomputable def jointEntropy {shape : LeninShape} (w : JointWeights shape) : ℝ :=
  ∑ k, entropy (w k)

/-- Совместный равномерный приор: в каждой категории w_{k,i} = 1/N_k. -/
noncomputable def jointUniform (shape : LeninShape) : JointWeights shape :=
  fun k => uniform (shape.N k)

/-- **Теорема T1 (главное утверждение).**
    Совместная энтропия максимизируется ТОЛЬКО равномерным приором
    `w_{k,i} = 1/N_k`. Этим обосновывается `0.0033 ≈ 1/303`,
    `0.0098 ≈ 1/102`, … в `Ядро_Ленин_13/weight_systems.py`
    как единственный max-entropy prior Джейнса на ∏_k Δ^{N_k − 1}. -/
theorem lenin_max_entropy_prior (shape : LeninShape)
    (w : JointWeights shape) (hw : JointInSimplex w) :
    jointEntropy w ≤ jointEntropy (jointUniform shape) ∧
    (jointEntropy w = jointEntropy (jointUniform shape) ↔ w = jointUniform shape) := by
  refine ⟨?_, ?_⟩
  · -- Сумма по k неравенств entropy_le_uniform.
    unfold jointEntropy jointUniform
    exact Finset.sum_le_sum (fun k _ => entropy_le_uniform (shape.hN k) (w k) (hw k))
  · constructor
    · intro hEq
      -- Равенство суммы = сумме максимумов ⇒ равенство покомпонентно
      -- ⇒ каждая компонента совпадает с uniform.
      funext k
      -- Сначала получаем покомпонентное равенство entropy (w k) = entropy (uniform (N k))
      -- из sum_eq_iff_pointwise, затем применяем entropy_eq_uniform_iff.
      have h_pointwise : ∀ k ∈ (Finset.univ : Finset (Fin shape.K)),
          entropy (w k) = entropy (uniform (shape.N k)) :=
        sum_eq_iff_pointwise
          (fun k _ => entropy_le_uniform (shape.hN k) (w k) (hw k))
          (by simpa [jointEntropy, jointUniform] using hEq)
      exact (entropy_eq_uniform_iff (shape.hN k) (w k) (hw k)).mp
        (h_pointwise k (Finset.mem_univ k))
    · intro hEq
      rw [hEq]

end LeninT1

/-
  ✅ ВСЕ SORRY ЗАКРЫТЫ. T1 доказана полностью.

  Атомарные леммы, выполненные Aristotle (Harmonic):
    • shannonEntropy_le_log_card    (run 2e1f1545) — Jensen + concaveOn_negMulLog
    • shannonEntropy_eq_log_card_iff (run f16a0781) — строгая вогнутость + StrictConcaveOn.lt_map_sum
    • sum_eq_iff_pointwise          (run f16a0781) — le_antisymm + Finset.single_le_sum

  Композиция и главная теорема `lenin_max_entropy_prior` — ведутся вручную
  поверх атомарных кирпичей через Mathlib v4.28.

  Все доказательства используют только стандартные аксиомы:
  `propext`, `Classical.choice`, `Quot.sound`.

  Это первая машинно-проверенная теорема о структуре ядра Ленин.
  Она составляет пункт (а) центральной теоремы T★ (см. library/formal/Lenin_Formalization.html):
  равномерный приор w*_{k,i} = 1/N_k есть единственный глобальный максимум
  энтропии на ∏_k Δ^{N_k−1}, задающий нулевое информационное состояние системы.
-/
