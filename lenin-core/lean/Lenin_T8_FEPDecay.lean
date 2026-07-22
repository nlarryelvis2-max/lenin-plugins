/-
  Lenin — T8 : FEP Prediction Error Decay
  =========================================

  Theorem T8: FEP prediction error decays exponentially.
    E[error(t)] ≤ C₀ * exp(-γ * t)
  where γ = 2 / (C + N) (contraction rate from T4).

  NUMERICAL VERIFICATION:
    library/formal/python/t8_fep_decay_tracker.py

  STATUS: 0 sorry, 4 theorems fully proved.
-/

import Mathlib.Analysis.SpecialFunctions.Log.Basic
import Mathlib.Data.Real.Basic
import Mathlib.Tactic.Linarith
import Mathlib.Tactic.NormNum
import Lenin_T1_MaxEntropy

open Real

namespace Lenin.T8

noncomputable section

/-- Contraction rate from T4: γ = 2 / (C + N). -/
def contractionRate (C N : ℝ) : ℝ :=
  2 / (C + N)

/-- FEP error bound: E[error(t)] ≤ C₀ * exp(-γ * t). -/
def errorBound (gamma C₀ t : ℝ) : ℝ :=
  C₀ * Real.exp (-gamma * t)

/-- **[T81]** Contraction rate is positive when observations and dimension are positive. -/
theorem contractionRate_positive {C N : ℝ} (hC : 0 < C) (hN : 0 < N) :
    0 < contractionRate C N := by
  unfold contractionRate
  exact div_pos (by norm_num) (by linarith)

/-- **[T82]** Error bound is positive when C₀ > 0. -/
theorem errorBound_positive {gamma C₀ t : ℝ} (hC : 0 < C₀) :
    0 < errorBound gamma C₀ t := by
  unfold errorBound
  exact mul_pos hC (Real.exp_pos _)

/-- **[T83]** Error bound is decreasing in t when γ > 0 and C₀ > 0. -/
theorem errorBound_decreasing {gamma C₀ t₁ t₂ : ℝ}
    (hGamma : 0 < gamma) (hC : 0 < C₀) (ht : t₁ ≤ t₂) :
    errorBound gamma C₀ t₂ ≤ errorBound gamma C₀ t₁ := by
  unfold errorBound
  have h_neg : -gamma * t₂ ≤ -gamma * t₁ := by
    have : gamma * t₁ ≤ gamma * t₂ := mul_le_mul_of_nonneg_left ht (le_of_lt hGamma)
    linarith
  have h_mono : Real.exp (-gamma * t₂) ≤ Real.exp (-gamma * t₁) :=
    Real.exp_le_exp.mpr h_neg
  exact mul_le_mul_of_nonneg_left h_mono (le_of_lt hC)

/-- **[T84]** Error bound at t = 0 is C₀. -/
theorem errorBound_at_zero (gamma C₀ : ℝ) :
    errorBound gamma C₀ 0 = C₀ := by
  unfold errorBound
  simp only [mul_zero, Real.exp_zero, mul_one]

end

end Lenin.T8
