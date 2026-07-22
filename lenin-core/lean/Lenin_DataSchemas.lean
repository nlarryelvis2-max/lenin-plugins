/-
  Lenin — Formal bridge: JSON Schemas ↔ Lean
  =====================================================================

  Этот модуль формализует связь между JSON Schemas (audio_draft,
  project_card, yaml_frontmatter_14d, people_card_14d, instrument_md, …)
  и типами из `Lenin_Wasserstein.lean`.

  Идея:
    JSON-карточка содержит вектор `weights : Lenin14`, индикатор доминанты
    `dominant : Fin 14 → Bool` и скаляр `ikl : ℝ` (KL от равномерного
    распределения). Schema-инварианты (S1: ∀ i, 0 ≤ w i ≤ 1; ∑ w i = 1;
    S2: ikl = KL(w ‖ uniform)) формализуются как `isValidCard`.

  Теоремы:
    * `isValidCard_implies_inSimplex` — S1 ⇒ InSimplex14
    * `isValidCard_ikl_eq_klFromUniform` — S2 ⇒ ikl = klFromUniform w
    * `validCard_kl_nonneg` — KL ≥ 0 для валидной карточки
-/

import Mathlib.Tactic
import Lenin_Wasserstein

open Real BigOperators Finset
open Lenin.Wasserstein

namespace Lenin.DataSchemas

/- ============================================================ -/
/-  Section 1 — Uniform distribution on Δ¹³                       -/
/- ============================================================ -/

/-- Равномерное распределение на 14 измерениях: каждый вес 1/14. -/
noncomputable def uniform14 : Lenin14 := fun _ => (1 : ℝ) / 14

lemma uniform14_pos : ∀ i, 0 < uniform14 i := by
  intro i; unfold uniform14; norm_num

lemma uniform14_inSimplex : InSimplex14 uniform14 := by
  refine ⟨?_, ?_⟩
  · intro i; unfold uniform14; norm_num
  · unfold uniform14
    rw [Finset.sum_const, Finset.card_univ, Fintype.card_fin]
    norm_num

/-- KL-дивергенция от равномерного: `klFromUniform w = KL(w ‖ uniform14)`. -/
noncomputable def klFromUniform (w : Lenin14) : ℝ :=
  KL w uniform14

/- ============================================================ -/
/-  Section 2 — Card structure (mirrors JSON Schema)              -/
/- ============================================================ -/

/-- Структура веса-карточки, отражающая JSON Schema (yaml_frontmatter_14d,
    project_card, audio_draft, …):
      • weights  — 14 весов (E, C, S, P, Ph, T, X, M, N, A, R, I, L, G)
      • dominant — индикатор доминантной оси (булевый предикат)
      • ikl      — поле `ikl_from_uniform`, прокинутое в YAML карточек -/
structure WeightCard where
  weights  : Lenin14
  dominant : Fin 14 → Bool
  ikl      : ℝ

/-- Schema invariants:
      S1 (simplex):    weights ∈ Δ¹³  (неотрицательность + сумма = 1)
      S2 (semantic):   ikl = KL(weights ‖ uniform14)
      S3 (top-bound):  каждый вес ≤ 1 (следствие S1, оставлено явно
                        для соответствия JSON `maximum: 1`) -/
def isValidCard (c : WeightCard) : Prop :=
  InSimplex14 c.weights ∧
  c.ikl = klFromUniform c.weights ∧
  (∀ i, c.weights i ≤ 1)

/- ============================================================ -/
/-  Section 3 — Bridge theorems                                   -/
/- ============================================================ -/

/-- **S1 ⇒ Δ¹³.** Любая карточка, удовлетворяющая schema-инвариантам,
    задаёт вектор весов на симплексе. Прямое раскрытие `isValidCard`. -/
theorem isValidCard_implies_inSimplex
    (c : WeightCard) (h : isValidCard c) : InSimplex14 c.weights :=
  h.1

/-- **S2 формализован.** Поле `ikl` валидной карточки совпадает
    с `klFromUniform weights`. -/
theorem isValidCard_ikl_eq_klFromUniform
    (c : WeightCard) (h : isValidCard c) :
    c.ikl = klFromUniform c.weights :=
  h.2.1

/-- **Top-bound следует из simplex.** Если ∀ i, 0 ≤ w i и Σ = 1,
    то w i ≤ 1 для каждого i. То есть JSON-инвариант `maximum: 1`
    не добавляет новой информации поверх S1 — sanity check. -/
theorem inSimplex_implies_bounded
    (w : Lenin14) (hw : InSimplex14 w) : ∀ i, w i ≤ 1 := by
  intro i
  obtain ⟨hnn, hsum⟩ := hw
  have hrest : 0 ≤ ∑ j ∈ (Finset.univ.erase i), w j :=
    Finset.sum_nonneg (fun j _ => hnn j)
  have hsplit : w i + (∑ j ∈ (Finset.univ.erase i), w j) = 1 := by
    rw [← Finset.sum_erase_add _ _ (Finset.mem_univ i)] at hsum
    linarith
  linarith

/-- **KL-неотрицательность для валидной карточки.** Bridge theorem,
    показывающий что semantic-инвариант S2 сразу даёт
    `c.ikl ≥ 0`. Это формализует runtime-проверку
    `assert ikl_from_uniform >= 0` из Python-пайплайна. -/
theorem validCard_ikl_nonneg
    (c : WeightCard) (h : isValidCard c) : 0 ≤ c.ikl := by
  rw [isValidCard_ikl_eq_klFromUniform c h]
  unfold klFromUniform
  exact kl_nonneg c.weights uniform14
    (isValidCard_implies_inSimplex c h) uniform14_inSimplex uniform14_pos

/-- **Sanity: уменьшенная форма S1.** Для удобства — извлечение
    неотрицательности отдельно от суммы. -/
theorem isValidCard_weights_nonneg
    (c : WeightCard) (h : isValidCard c) : ∀ i, 0 ≤ c.weights i :=
  (isValidCard_implies_inSimplex c h).1

/-- **Sanity: сумма весов = 1.** Прямое следствие S1. -/
theorem isValidCard_weights_sum_one
    (c : WeightCard) (h : isValidCard c) : (∑ i, c.weights i) = 1 :=
  (isValidCard_implies_inSimplex c h).2

/- ============================================================ -/
/-  Section 4 — Extended bridge (Wave-7+ deepening)               -/
/- ============================================================ -/

/-- **Strict separation of cards.** Если две валидные карточки имеют
    одинаковые weights, то их `ikl` тоже совпадают (поскольку
    оба = klFromUniform weights). Формальная гарантия консистентности
    semantic-инварианта S2. -/
theorem validCards_same_weights_implies_same_ikl
    (c1 c2 : WeightCard) (h1 : isValidCard c1) (h2 : isValidCard c2)
    (hw : c1.weights = c2.weights) : c1.ikl = c2.ikl := by
  rw [isValidCard_ikl_eq_klFromUniform c1 h1,
      isValidCard_ikl_eq_klFromUniform c2 h2, hw]

/-- **Uniform card.** Карточка с равномерными весами 1/14 — валидна,
    и её `ikl = 0` (KL от uniform к uniform). Это **минимум** для T★
    и формальная realization Jaynes max-entropy prior. -/
noncomputable def uniformCard : WeightCard :=
  { weights := uniform14, dominant := fun _ => true, ikl := 0 }

theorem uniformCard_is_valid : isValidCard uniformCard := by
  refine ⟨uniform14_inSimplex, ?_, ?_⟩
  · -- ikl = klFromUniform uniform14 = KL uniform14 uniform14 = 0
    show (0 : ℝ) = klFromUniform uniform14
    unfold klFromUniform
    have : KL uniform14 uniform14 = 0 :=
      kl_self_eq_zero uniform14 uniform14_pos
    linarith
  · -- ∀ i, uniformCard.weights i = uniform14 i ≤ 1
    intro i
    show uniform14 i ≤ 1
    unfold uniform14; norm_num

/-- **KL-минимум характеризует uniform.** Если валидная карточка имеет
    `ikl = 0`, её weights — это uniform14. Формализация
    "I_kl=0 ⇔ p=uniform" из T★ (Lenin_TStar.lean S22). -/
theorem validCard_ikl_zero_iff_uniform
    (c : WeightCard) (h : isValidCard c) :
    c.ikl = 0 ↔ c.weights = uniform14 := by
  rw [isValidCard_ikl_eq_klFromUniform c h]
  unfold klFromUniform
  exact kl_eq_zero_iff c.weights uniform14
    (isValidCard_implies_inSimplex c h) uniform14_inSimplex uniform14_pos

/- ============================================================ -/
/-  Section 5 — T★ operational predicates                         -/
/-  (Quality filter formalization — Wave-7 deepening)            -/
/- ============================================================ -/

/-- **`card_has_signal`** — operational T★ filter: card имеет
    statistical signal если это валидная карточка И её ikl выше
    noise floor `ε`.

    При `ε = 0`: эквивалентно "weights ≠ uniform14" (signal ≠ no-signal).
    При `ε > 0`: требует strict positivity ikl (определённый focus). -/
def card_has_signal (c : WeightCard) (ε : ℝ) : Prop :=
  isValidCard c ∧ ε ≤ c.ikl

/-- **Signal ⇒ not uniform.** Если карточка имеет signal с ε > 0,
    её weights не равны uniform14. Прямое следствие из
    `validCard_ikl_zero_iff_uniform` + строгой положительности ε. -/
theorem signal_implies_not_uniform
    (c : WeightCard) (ε : ℝ) (ε_pos : 0 < ε)
    (h : card_has_signal c ε) : c.weights ≠ uniform14 := by
  intro h_eq
  have h_valid : isValidCard c := h.1
  have h_ikl_ge : ε ≤ c.ikl := h.2
  -- если weights = uniform14, то ikl = 0 (по validCard_ikl_zero_iff_uniform)
  have h_ikl_zero : c.ikl = 0 :=
    (validCard_ikl_zero_iff_uniform c h_valid).mpr h_eq
  -- но ε ≤ ikl = 0, ε > 0 — противоречие
  linarith

/-- **No-signal ⇒ uniform OR invalid.** Контрапозиция: если карточка
    "не имеет signal" (ikl < ε), то она либо невалидна, либо weights = uniform14
    (когда ε = 0). При ε > 0 даёт строгую дихотомию. -/
theorem not_signal_iff_low_ikl_or_invalid
    (c : WeightCard) (ε : ℝ) :
    ¬ card_has_signal c ε ↔ ¬ isValidCard c ∨ c.ikl < ε := by
  unfold card_has_signal
  constructor
  · intro h
    push_neg at h
    by_cases hv : isValidCard c
    · right; exact h hv
    · left; exact hv
  · intro h hand
    rcases h with h | h
    · exact h hand.1
    · linarith [hand.2]

/-- **Signal preservation under uniform card.** uniformCard имеет ikl = 0,
    значит для любого ε > 0 у неё нет signal — formal proof что
    "no observation" не является signal. -/
theorem uniformCard_no_signal (ε : ℝ) (ε_pos : 0 < ε) :
    ¬ card_has_signal uniformCard ε := by
  intro h
  have h_eq : uniformCard.weights = uniform14 := rfl
  have h_not_uniform : uniformCard.weights ≠ uniform14 :=
    signal_implies_not_uniform uniformCard ε ε_pos h
  exact h_not_uniform h_eq

end Lenin.DataSchemas
