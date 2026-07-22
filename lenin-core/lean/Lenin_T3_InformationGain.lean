/-
  Lenin — T3 : Posterior Information Gain
  ========================================

  Соединяет T2 (posterior convergence) с T★ (information functional I_KL).

  ΔI = I(w_posterior) - I(w_prior) = I(w_posterior)
  поскольку I(w_prior) = I(uniform) = 0 (из T1).

  T3a: I(uniform) = 0 (приор не несёт информации)
  T3b: I(w) ≥ 0 (информация неотрицательна — следствие T1: H ≤ log N)
  T3c: I(w) ≤ log N (ограниченность информации)
  T3d: I(w_posterior) ≥ 0 (постериор всегда получает информацию)

  Значение для Ленина:
    Постериор гарантированно набирает информацию (ΔI ≥ 0).
    N=14: max I = log 14 ≈ 2.64. Информация ограничена и сходится.
-/

import Mathlib.Analysis.SpecialFunctions.Log.Basic
import Mathlib.Data.Real.Basic
import Mathlib.Data.NNReal.Basic
import Mathlib.Tactic.NormNum
import Mathlib.Tactic.Linarith
import Mathlib.Algebra.Order.BigOperators.Group.Finset
import Lenin_T1_MaxEntropy
import Lenin_T2_PosteriorConvergence

open Real BigOperators Finset

namespace Lenin.T3

/-- Размерность (14D для Ленина) -/
def dimN : ℕ := 14

/-- Information content: I(w) = D_KL(w ‖ uniform) = Σ w_i · log(w_i · N). -/
noncomputable def totalInfo {N : ℕ} (weights : Fin N → ℝ) : ℝ :=
  ∑ i, weights i * Real.log (weights i * N)

/- ============================================================ -/
/-  T3a: I(uniform) = 0                                           -/
/- ============================================================ -/

/-- T3a: Равномерное распределение несёт нулевую информацию. -/
theorem T3a_uniform_zero_info {N : ℕ} (hN : 0 < N) :
    totalInfo (fun (_ : Fin N) => (1 : ℝ) / N) = 0 := by
  -- (1/N) * log(1/N * N) = (1/N) * log 1 = (1/N) * 0 = 0
  unfold totalInfo
  refine Finset.sum_eq_zero (fun i _ => ?_)
  have hNne : (N : ℝ) ≠ 0 := Nat.cast_ne_zero.mpr hN.ne'
  show (1 : ℝ) / (N : ℝ) * Real.log ((1 : ℝ) / (N : ℝ) * (N : ℝ)) = 0
  have h_inner : (1 : ℝ) / (N : ℝ) * (N : ℝ) = 1 := by
    rw [one_div, inv_mul_cancel₀ hNne]
  rw [h_inner, Real.log_one, mul_zero]

/- ============================================================ -/
/-  T3b: I(w) ≥ 0 (from T1: H ≤ log N)                          -/
/- ============================================================ -/

/-- Bridge: negMulLog x = -x * log x for x > 0. -/
lemma negMulLog_eq {x : ℝ} (_hx : 0 < x) :
    Real.negMulLog x = -(x * Real.log x) := by
  unfold Real.negMulLog
  ring

/-- Bridge: Σ w_i log(w_i * N) = Σ w_i log w_i + log N (when Σ w_i = 1). -/
lemma info_split {N : ℕ} (hN : 0 < N) (weights : Fin N → ℝ)
    (hw_pos : ∀ i, 0 < weights i) (hw_sum : ∑ i, weights i = 1) :
    totalInfo weights = ∑ i, weights i * Real.log (weights i) + Real.log N := by
  unfold totalInfo
  -- log(w_i * N) = log w_i + log N when both > 0
  have h_log_split : ∀ i : Fin N,
      Real.log (weights i * N) = Real.log (weights i) + Real.log N := fun i => by
    have h1 : weights i ≠ 0 := ne_of_gt (hw_pos i)
    have h2 : (N : ℝ) ≠ 0 := Nat.cast_ne_zero.mpr hN.ne'
    exact Real.log_mul h1 h2
  simp only [h_log_split]
  -- Σ w_i * (log w_i + log N) = Σ (w_i * log w_i + w_i * log N)
  -- = Σ (w_i * log w_i) + log N * Σ w_i = Σ (w_i * log w_i) + log N
  -- Σ w_i * (log w_i + log N) = Σ (w_i * log w_i + w_i * log N)
  -- = Σ (w_i * log w_i) + Σ (w_i * log N)
  -- = Σ (w_i * log w_i) + log N * Σ w_i
  -- = Σ (w_i * log w_i) + log N * 1
  simp only [mul_add]
  rw [Finset.sum_add_distrib]
  -- Need: Σ (w_i * log N) = log N
  have h_const : ∑ i, weights i * Real.log N = Real.log N := by
    rw [← Finset.sum_mul, hw_sum, one_mul]
  rw [h_const]

/-- T3b: Информация неотрицательна.
    I(w) = log N - H(w) ≥ 0 since H(w) ≤ log N (T1). -/
theorem T3b_info_nonneg {N : ℕ} (hN : 0 < N)
    (weights : Fin N → ℝ) (hw_nn : ∀ i, 0 ≤ weights i)
    (hw_pos : ∀ i, 0 < weights i) (hw_sum : ∑ i, weights i = 1) :
    0 ≤ totalInfo weights := by
  -- totalInfo = Σ(w_i * log w_i) + log N
  have h_split := info_split hN weights hw_pos hw_sum
  -- entropy = Σ negMulLog(w_i) = Σ -(w_i * log w_i)
  have h_entropy : LeninT1.entropy weights = ∑ i, -(weights i * Real.log (weights i)) := by
    unfold LeninT1.entropy
    simp [Real.negMulLog, Finset.sum_neg_distrib]
  -- T1: entropy ≤ log N
  have h_bound : LeninT1.entropy weights ≤ Real.log N :=
    LeninT1.shannonEntropy_le_log_card hN weights hw_nn hw_sum
  -- So: -entropy ≥ -log N, and totalInfo = Σ(w_i * log w_i) + log N = -entropy + log N ≥ 0
  rw [h_split]
  have : ∑ i, weights i * Real.log (weights i) = -LeninT1.entropy weights := by
    have := h_entropy.symm
    rw [Finset.sum_neg_distrib] at this
    linarith
  linarith

/- ============================================================ -/
/-  T3c: I(w) ≤ log N                                             -/
/- ============================================================ -/

/-- T3c: Информация ограничена сверху log N.
    I(w) = Σ w_i log(w_i * N). Since w_i ≤ 1 on simplex, log w_i ≤ 0.
    So Σ w_i log w_i ≤ 0, hence I = Σ w_i log w_i + log N ≤ log N. -/
theorem T3c_info_bounded {N : ℕ} (hN : 1 < N)
    (weights : Fin N → ℝ) (hw_nn : ∀ i, 0 ≤ weights i)
    (hw_pos : ∀ i, 0 < weights i) (hw_sum : ∑ i, weights i = 1) :
    totalInfo weights ≤ Real.log N := by
  -- Each w_i ≤ 1 (since Σ w_j = 1 and all nonneg), so log w_i ≤ 0
  -- I = Σ w_i log w_i + log N ≤ 0 + log N = log N
  have h_wi_le_one : ∀ i, weights i ≤ 1 := fun i => by
    have : weights i ≤ ∑ j, weights j := single_le_sum (fun j _ => hw_nn j) (mem_univ i)
    linarith
  -- Each w_i ≤ 1 (since Σ w_j = 1 and all nonneg), so log w_i ≤ 0
  -- Each w_i * log w_i ≤ 0, so Σ w_i * log w_i ≤ 0
  have h_split := info_split (by omega : 0 < N) weights hw_pos hw_sum
  have h_sum_neg : ∑ i, weights i * Real.log (weights i) ≤ 0 := by
    apply Finset.sum_nonpos
    intro i _
    -- w_i > 0 and w_i ≤ 1, so log w_i ≤ 0, hence w_i * log w_i ≤ 0
    have h_wi_le : weights i ≤ 1 := h_wi_le_one i
    have h_log_le : Real.log (weights i) ≤ 0 := by
      exact Real.log_nonpos (le_of_lt (hw_pos i)) h_wi_le
    exact mul_nonpos_of_nonneg_of_nonpos (le_of_lt (hw_pos i)) h_log_le
  -- totalInfo = Σ w_i log w_i + log N ≤ 0 + log N = log N
  rw [h_split]
  linarith

/- ============================================================ -/
/-  T3d: Posterior information gain ≥ 0                           -/
/- ============================================================ -/

/-- T3d: Постериор всегда получает информацию (ΔI ≥ 0).
    Since prior is uniform (I = 0) and posterior has I ≥ 0 (T3b). -/
theorem T3d_posterior_gains_info {N : ℕ} (hN : 0 < N)
    (counts : Fin N → ℝ) (hc : ∀ i, 0 ≤ counts i) :
    0 ≤ totalInfo (fun i => T2.posterior counts i) := by
  -- Posterior is on the simplex (T2a) and nonneg/positive (T2b)
  -- So by T3b: I(posterior) ≥ 0
  have h_pos : ∀ i, 0 < T2.posterior counts i :=
    fun i => T2.T2b_posterior_pos (by exact_mod_cast hN) counts hc i
  have h_nn : ∀ i, 0 ≤ T2.posterior counts i := fun i => le_of_lt (h_pos i)
  have h_sum : ∑ i, T2.posterior counts i = 1 :=
    T2.T2a_posterior_sum_eq_one (by exact_mod_cast hN) counts hc
  exact T3b_info_nonneg (by exact_mod_cast hN) _ h_nn h_pos h_sum

/- ============================================================ -/
/-  T3: Combined theorem                                          -/
/- ============================================================ -/

/-- T3: Постериор гарантированно получает информацию.
    ΔI = I(w_posterior) ≥ 0 (T3d), bounded by log N (T3c). -/
theorem T3_posterior_information_gain {N : ℕ} (hN : 1 < N)
    (counts : Fin N → ℝ) (hc : ∀ i, 0 ≤ counts i) :
    0 ≤ totalInfo (fun i => T2.posterior counts i) ∧
    totalInfo (fun i => T2.posterior counts i) ≤ Real.log N := by
  have hNpos : 0 < N := by omega
  have h_pos : ∀ i, 0 < T2.posterior counts i :=
    fun i => T2.T2b_posterior_pos (by exact_mod_cast hNpos) counts hc i
  have h_nn : ∀ i, 0 ≤ T2.posterior counts i := fun i => le_of_lt (h_pos i)
  have h_sum : ∑ i, T2.posterior counts i = 1 :=
    T2.T2a_posterior_sum_eq_one (by exact_mod_cast hNpos) counts hc
  exact ⟨T3d_posterior_gains_info hNpos counts hc,
         T3c_info_bounded hN _ h_nn h_pos h_sum⟩

/- ============================================================ -/
/-  T3 specializations for Ленин (N=14)                           -/
/- ============================================================ -/

/-- N=14: max information gain = log 14 ≈ 2.64 nat. -/
theorem T3_lenin_bound :
    ∀ (counts : Fin 14 → ℝ) (_hc : ∀ i, 0 ≤ counts i),
    totalInfo (fun i => T2.posterior counts i) ≤ Real.log 14 := by
  intro counts hc
  have h_pos : ∀ i, 0 < T2.posterior counts i :=
    fun i => T2.T2b_posterior_pos (by norm_num) counts hc i
  have h_nn : ∀ i, 0 ≤ T2.posterior counts i := fun i => le_of_lt (h_pos i)
  have h_sum : ∑ i, T2.posterior counts i = 1 :=
    T2.T2a_posterior_sum_eq_one (by norm_num) counts hc
  exact T3c_info_bounded (by norm_num : (1 : ℕ) < 14) _ h_nn h_pos h_sum

end Lenin.T3
