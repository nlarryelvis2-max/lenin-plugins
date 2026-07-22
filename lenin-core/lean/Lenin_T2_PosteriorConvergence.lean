/-
  Lenin — T2 : Bayesian Posterior Convergence
  =============================================

  Теорема о сходимости байесова постериора с uniform-приором (из T1).

  T2a: Σ w_i = 1 (simplex membership)
  T2b: w_i > 0 (positivity)
  T2c: w_i = C/(C+N) · f_i + 1/(C+N) (convex combination)
  T2d: |w_i - f_i| ≤ (N-1)/(C+N) (shrinkage)
  T2e: |w_i - p_i| ≤ |f_i - p_i| + (N-1)/(C+N) (convergence guarantee)

  Значение для Ленина:
    Система гарантированно учится — постериор сходится к истинным весам.
    N=14, C=34: shrinkage ≤ 0.27. C=100: ≤ 0.11. C=1000: ≤ 0.013.

  Статус: All theorems proved (0 sorry). T2a uses sum_mul + mul_inv_cancel₀,
  T2c uses sum_div + field_simp, T2d uses div_sub_div + abs_div + div_le_iff₀.
-/

import Mathlib.Analysis.SpecialFunctions.Log.Basic
import Mathlib.Data.Real.Basic
import Mathlib.Data.NNReal.Basic
import Mathlib.Tactic.NormNum
import Mathlib.Tactic.Linarith
import Mathlib.Tactic.FieldSimp
import Mathlib.Algebra.BigOperators.Ring.Finset
import Mathlib.Topology.MetricSpace.Basic
import Lenin_T1_MaxEntropy

open Real BigOperators Finset

namespace Lenin.T2

def dimN : ℕ := 14

/-- Байесов постериор: w_i = (c_i + 1) / (C + N) -/
noncomputable def posterior {N : ℕ} (counts : Fin N → ℝ) (i : Fin N) : ℝ :=
  (counts i + 1) / (∑ j, counts j + (N : ℝ))

/-- Эмпирическая частота: f_i = c_i / C -/
noncomputable def empiricalFreq {N : ℕ} (counts : Fin N → ℝ) (i : Fin N) : ℝ :=
  counts i / ∑ j, counts j

/- ============================================================ -/
/-  T2a: Σ w_i = 1                                                 -/
/- ============================================================ -/

/-- T2a: Сумма постериоров = 1.
    Proof: Σ (c_i + 1) = C + N, so Σ (c_i + 1)/(C+N) = (C+N)/(C+N) = 1. -/
theorem T2a_posterior_sum_eq_one {N : ℕ} (hN : 0 < N)
    (counts : Fin N → ℝ) (hc : ∀ i, 0 ≤ counts i) :
    ∑ i, posterior counts i = 1 := by
  unfold posterior
  have h_sum : ∑ i, (counts i + 1) = ∑ i, counts i + (N : ℝ) := by
    rw [sum_add_distrib, sum_const, card_univ, Fintype.card_fin, nsmul_eq_mul, mul_one]
  have h_den_pos : (0 : ℝ) < ∑ j, counts j + (N : ℝ) := by
    have : (0 : ℝ) < (N : ℝ) := by exact_mod_cast hN
    have h_sum_nn : (0 : ℝ) ≤ ∑ j, counts j := sum_nonneg (fun j _ => hc j)
    linarith
  have h_den_ne : ∑ j, counts j + (N : ℝ) ≠ 0 := ne_of_gt h_den_pos
  -- ∑ (c_i+1)/(C+N) = (∑ (c_i+1))/(C+N) = (C+N)/(C+N) = 1
  -- The factoring step: ∑ (f_i / d) = (∑ f_i) / d
  simp only [div_eq_mul_inv]
  have : ∑ i, (counts i + 1) * (∑ j, counts j + (N : ℝ))⁻¹ =
      (∑ i, (counts i + 1)) * (∑ j, counts j + (N : ℝ))⁻¹ := by
    rw [Finset.sum_mul]
  rw [this, h_sum]
  exact mul_inv_cancel₀ h_den_ne

/- ============================================================ -/
/-  T2b: w_i > 0                                                   -/
/- ============================================================ -/

/-- T2b: Постериор положителен. -/
theorem T2b_posterior_pos {N : ℕ} (hN : 0 < N)
    (counts : Fin N → ℝ) (hc : ∀ i, 0 ≤ counts i) (i : Fin N) :
    0 < posterior counts i := by
  unfold posterior
  have h_num : (0 : ℝ) < counts i + 1 := by linarith [hc i]
  have hN_cast : (0 : ℝ) < (N : ℝ) := by exact_mod_cast hN
  have h_den : (0 : ℝ) < ∑ j, counts j + (N : ℝ) := by
    have h_sum_nn : (0 : ℝ) ≤ ∑ j, counts j := sum_nonneg (fun j _ => hc j)
    linarith
  exact div_pos h_num h_den

/- ============================================================ -/
/-  T2c: Decomposition                                             -/
/- ============================================================ -/

/-- T2c: w_i = C/(C+N) · f_i + 1/(C+N) (convex combination of freq and prior).
    Prior coefficient N/(C+N) → 0 as C → ∞, so prior washes out. -/
theorem T2c_posterior_decomposition {N : ℕ} (_hN : 0 < N)
    (counts : Fin N → ℝ) (i : Fin N)
    (hC : (0 : ℝ) < ∑ j, counts j) :
    posterior counts i =
      (∑ j, counts j / (∑ k, counts k + (N : ℝ))) * (counts i / ∑ j, counts j) +
      (1 / (∑ j, counts j + (N : ℝ))) := by
  unfold posterior
  have hC_ne : (∑ j, counts j : ℝ) ≠ 0 := ne_of_gt hC
  have hCN_ne : (∑ j, counts j : ℝ) + (N : ℝ) ≠ 0 := by linarith [le_of_lt hC]
  -- (c_i+1)/(C+N) = c_i/(C+N) + 1/(C+N) = [C/(C+N)]·[c_i/C] + 1/(C+N)
  -- First simplify: ∑ j, counts j / (C+N) = C / (C+N)
  have h_sum_div : ∑ j, counts j / (∑ k, counts k + (N : ℝ)) =
      (∑ j, counts j) / (∑ k, counts k + (N : ℝ)) := by
    simp only [div_eq_mul_inv, Finset.sum_mul]
  rw [h_sum_div]
  -- Now: (c_i+1)/(C+N) = [C/(C+N)] * [c_i/C] + 1/(C+N) -- pure field arithmetic
  field_simp [hC_ne, hCN_ne]

/- ============================================================ -/
/-  T2d: Posterior shrinkage                                       -/
/- ============================================================ -/

/-- T2d: |w_i - f_i| ≤ (N-1)/(C+N).
    Math: w_i - f_i = (C - N·c_i)/(C·(C+N)), and |C - N·c_i| ≤ C(N-1) for c_i ∈ [0, C].
    The key bound |C - Nc_i| ≤ C(N-1) is fully proved. Only the final
    field manipulation from the bound to the target inequality uses sorry. -/
theorem T2d_posterior_shrinkage {N : ℕ} (hN : 2 ≤ N)
    (counts : Fin N → ℝ) (hc : ∀ i, 0 ≤ counts i) (i : Fin N)
    (hC : (0 : ℝ) < ∑ j, counts j) :
    abs (posterior counts i - empiricalFreq counts i) ≤
      ((N - 1 : ℝ) / (∑ j, counts j + (N : ℝ))) := by
  unfold posterior empiricalFreq
  have h_ci_nn : (0 : ℝ) ≤ counts i := hc i
  have h_ci_le : counts i ≤ ∑ j, counts j :=
    single_le_sum (fun j _ => hc j) (mem_univ i)
  have hC_nn : (0 : ℝ) ≤ ∑ j, counts j := le_of_lt hC
  -- Key bound: |C - N·c_i| ≤ C(N-1) for c_i ∈ [0,C] and N ≥ 2
  have h_bound : abs (∑ j, counts j - (N : ℝ) * counts i) ≤
      (∑ j, counts j) * (N - 1) := by
    have h_upper : ∑ j, counts j - (N : ℝ) * counts i ≤
        (∑ j, counts j) * (N - 1) := by
      nlinarith [show (2 : ℝ) ≤ (N : ℝ) from by exact_mod_cast hN]
    have h_lower : -((∑ j, counts j) * (N - 1)) ≤
        ∑ j, counts j - (N : ℝ) * counts i := by nlinarith
    rw [abs_le]; exact ⟨h_lower, h_upper⟩
  -- From h_bound: |C - Nc_i| ≤ C(N-1)
  -- Therefore |(C-Nc_i)/(C(C+N))| ≤ C(N-1)/(C(C+N)) = (N-1)/(C+N)
  have hC_ne : (∑ j, counts j : ℝ) ≠ 0 := ne_of_gt hC
  have hCN_pos : (0 : ℝ) < ∑ j, counts j + (N : ℝ) := by linarith
  have hCN_ne : (∑ j, counts j : ℝ) + (N : ℝ) ≠ 0 := ne_of_gt hCN_pos
  -- Rewrite subtraction with common denominator: a/b - c/d = (a*d - b*c)/(b*d)
  rw [div_sub_div (counts i + 1) (counts i) hCN_ne hC_ne]
  rw [abs_div]
  -- Denominator |(C+N)*C| = (C+N)*C since both > 0
  rw [abs_of_pos (mul_pos hCN_pos hC)]
  -- Goal: |numerator| / ((C+N)*C) ≤ (N-1)/(C+N)
  -- Cross-multiply by (C+N)*C > 0
  rw [div_le_iff₀ (mul_pos hCN_pos hC)]
  -- Simplify numerator: (c_i+1)*C - (C+N)*c_i = C - N*c_i
  have h_num_simp : (counts i + 1) * ∑ j, counts j -
      (∑ j, counts j + (N : ℝ)) * counts i =
      ∑ j, counts j - (N : ℝ) * counts i := by ring
  rw [h_num_simp]
  -- Simplify RHS: (↑N-1)/(C+N) * ((C+N)*C) = (↑N-1)*C
  have h_rhs : (↑N - 1) / (∑ j, counts j + ↑N) * ((∑ j, counts j + ↑N) * ∑ j, counts j) =
      (↑N - 1) * ∑ j, counts j := by
    field_simp [hCN_ne]
  rw [h_rhs]
  -- Goal: |C - ↑N*c_i| ≤ (↑N - 1) * C
  -- h_bound: |C - ↑N*c_i| ≤ C * (↑N - 1) = (↑N - 1) * C by mul_comm
  -- Also need: ∑ j, counts j - ↑N * counts i = ∑ j, counts j - counts i * ↑N
  have h_mul_comm : ↑N * counts i = counts i * ↑N := mul_comm ..
  rw [h_mul_comm] at h_num_simp h_bound ⊢
  linarith [show (∑ j, counts j) * (↑N - 1) = (↑N - 1) * ∑ j, counts j from mul_comm ..]

/- ============================================================ -/
/-  T2e: Convergence guarantee                                    -/
/- ============================================================ -/

/-- T2e: |w_i - p_i| ≤ |f_i - p_i| + (N-1)/(C+N).
    Triangle inequality + T2d shrinkage.
    Both summands → 0 as C → ∞, so w_i → p_i. -/
theorem T2e_convergence_bound {N : ℕ} (hN : 2 ≤ N)
    (counts : Fin N → ℝ) (hc : ∀ i, 0 ≤ counts i) (i : Fin N)
    (hC : (0 : ℝ) < ∑ j, counts j)
    (p_i : ℝ) :
    abs (posterior counts i - p_i) ≤
      abs (empiricalFreq counts i - p_i) + ((N - 1 : ℝ) / (∑ j, counts j + (N : ℝ))) := by
  have h_shrink := T2d_posterior_shrinkage hN counts hc i hC
  have h_tri : dist (posterior counts i) p_i ≤
      dist (posterior counts i) (empiricalFreq counts i) +
      dist (empiricalFreq counts i) p_i :=
    dist_triangle (posterior counts i) (empiricalFreq counts i) p_i
  simp only [Real.dist_eq] at h_tri
  linarith

/- ============================================================ -/
/-  T2 specializations for Ленин (N=14)                           -/
/- ============================================================ -/

/-- N=14, C=34: |w_i - f_i| ≤ 13/48 ≈ 0.27 -/
theorem T2_lenin_shrinkage_34 :
    ∀ (counts : Fin 14 → ℝ) (_hc : ∀ i, 0 ≤ counts i)
      (_hC : ∑ j, counts j = 34),
    ∀ i, abs (posterior counts i - empiricalFreq counts i) ≤ (13 : ℝ) / 48 := by
  intro counts hc hC i
  have hN : (2 : ℕ) ≤ 14 := by norm_num
  have hC_pos : (0 : ℝ) < ∑ j, counts j := by rw [hC]; norm_num
  have h_bound := T2d_posterior_shrinkage hN counts hc i hC_pos
  rw [hC] at h_bound; norm_num at h_bound ⊢; linarith

/-- N=14, C=100: |w_i - f_i| ≤ 13/114 ≈ 0.11 -/
theorem T2_lenin_shrinkage_100 :
    ∀ (counts : Fin 14 → ℝ) (_hc : ∀ i, 0 ≤ counts i)
      (_hC : ∑ j, counts j = 100),
    ∀ i, abs (posterior counts i - empiricalFreq counts i) ≤ (13 : ℝ) / 114 := by
  intro counts hc hC i
  have hN : (2 : ℕ) ≤ 14 := by norm_num
  have hC_pos : (0 : ℝ) < ∑ j, counts j := by rw [hC]; norm_num
  have h_bound := T2d_posterior_shrinkage hN counts hc i hC_pos
  rw [hC] at h_bound; norm_num at h_bound ⊢; linarith

/-- N=14, C=1000: |w_i - f_i| ≤ 13/1014 ≈ 0.013 -/
theorem T2_lenin_shrinkage_1000 :
    ∀ (counts : Fin 14 → ℝ) (_hc : ∀ i, 0 ≤ counts i)
      (_hC : ∑ j, counts j = 1000),
    ∀ i, abs (posterior counts i - empiricalFreq counts i) ≤ (13 : ℝ) / 1014 := by
  intro counts hc hC i
  have hN : (2 : ℕ) ≤ 14 := by norm_num
  have hC_pos : (0 : ℝ) < ∑ j, counts j := by rw [hC]; norm_num
  have h_bound := T2d_posterior_shrinkage hN counts hc i hC_pos
  rw [hC] at h_bound; norm_num at h_bound ⊢; linarith

end Lenin.T2
