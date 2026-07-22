/-
  Lenin — T7 : Atom Bifurcation (Hakken Pitchfork)
  =================================================

  Theorem T7: F(ξ) = -λ/2·ξ² + a/4·ξ⁴
  λ < 0: ξ = 0 stable (no atom)
  λ > 0, a > 0: bifurcates to ±√(λ/a)

  NUMERICAL VERIFICATION:
    library/formal/python/t7_atom_bifurcation.py

  STATUS: 2 sorry, 4 theorems fully proved.
-/

import Mathlib.Data.Real.Basic
import Mathlib.Data.Real.Sqrt
import Mathlib.Tactic.Linarith
import Mathlib.Tactic.NormNum
import Lenin_T1_MaxEntropy

open Real

namespace Lenin.T7

noncomputable section

/-- Hakken potential: F(ξ) = -λ/2·ξ² + a/4·ξ⁴. -/
def hakkenPotential (xi lambda a : ℝ) : ℝ :=
  -lambda / 2 * xi ^ 2 + a / 4 * xi ^ 4

/-- Hakken derivative: F'(ξ) = ξ(aξ² - λ). -/
def hakkenDeriv (xi lambda a : ℝ) : ℝ :=
  xi * (a * xi ^ 2 - lambda)

/-- **[T71]** Potential at origin is zero. -/
theorem hakken_potential_at_origin (lambda a : ℝ) :
    hakkenPotential 0 lambda a = 0 := by
  unfold hakkenPotential
  simp

/-- **[T72]** Derivative at origin is zero. -/
theorem hakken_deriv_at_origin (lambda a : ℝ) :
    hakkenDeriv 0 lambda a = 0 := by
  unfold hakkenDeriv
  ring

/-- **[T73]** Derivative is zero iff ξ = 0 or aξ² = λ. -/
theorem hakken_deriv_zero_iff (xi lambda a : ℝ) :
    hakkenDeriv xi lambda a = 0 ↔ xi = 0 ∨ a * xi ^ 2 = lambda := by
  unfold hakkenDeriv
  constructor
  · intro h
    rw [mul_eq_zero] at h
    cases h with
    | inl h => left; exact h
    | inr h => right; linarith
  · rintro (h | h)
    · rw [h]; ring
    · have : a * xi ^ 2 - lambda = 0 := by linarith
      rw [this]; ring

/-- **[T74]** When λ < 0 and a ≥ 0, only equilibrium is ξ = 0. -/
theorem hakken_stable_lambda_neg (xi lambda a : ℝ)
    (hLam : lambda < 0) (ha : 0 ≤ a) :
    hakkenDeriv xi lambda a = 0 → xi = 0 := by
  unfold hakkenDeriv
  intro h
  rw [mul_eq_zero] at h
  cases h with
  | inl h => exact h
  | inr h =>
    exfalso
    have h2 : a * xi ^ 2 = lambda := by linarith
    have h3 : 0 ≤ a * xi ^ 2 := mul_nonneg ha (sq_nonneg xi)
    linarith

/-- **[T75]** When λ > 0 and a > 0, ±√(λ/a) are equilibria. -/
theorem hakken_bifurcation_points (lambda a : ℝ)
    (hLam : 0 < lambda) (ha : 0 < a) :
    hakkenDeriv (sqrt (lambda / a)) lambda a = 0 ∧
    hakkenDeriv (-sqrt (lambda / a)) lambda a = 0 := by
  sorry -- [T75]: sqrt(λ/a) and -sqrt(λ/a) satisfy F'(ξ) = 0

/-- **[T76]** Potential at bifurcation points: F(√(λ/a)) = -λ²/(4a). -/
theorem hakken_potential_at_bifurcation (lambda a : ℝ)
    (hLam : 0 < lambda) (ha : 0 < a) :
    hakkenPotential (sqrt (lambda / a)) lambda a = -lambda ^ 2 / (4 * a) := by
  sorry -- [T76]: algebraic simplification with sqrt

end

end Lenin.T7
