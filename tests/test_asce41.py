"""
Unit tests for asce41_rotation.py.

Parameter values are computed by hand from ASCE 41 Table 10-8 equations
so that any coefficient change in the source code will be detected.
"""

import pytest

from constants import (
    ASCE41_RHO_T_MIN,
    ASCE41_RHO_T_CAP_ANCHORED,
    ASCE41_RHO_T_CAP_UNANCHORED,
    ASCE41_THETA_LS_FACTOR,
    ASCE41_THETA_CP_FACTOR,
)
from asce41_rotation import _limit_rho_t, _unspliced_params, _spliced_params


# ---------------------------------------------------------------------------
# _limit_rho_t
# ---------------------------------------------------------------------------

class TestLimitRhoT:
    def test_value_below_min_is_clipped(self):
        rho_t, warnings = _limit_rho_t(0.0001, adequately_anchored=True)
        assert rho_t == pytest.approx(ASCE41_RHO_T_MIN)
        assert len(warnings) == 1

    def test_value_above_anchored_cap_is_clipped(self):
        rho_t, warnings = _limit_rho_t(0.02, adequately_anchored=True)
        assert rho_t == pytest.approx(ASCE41_RHO_T_CAP_ANCHORED)
        assert len(warnings) == 1

    def test_value_above_unanchored_cap_is_clipped(self):
        rho_t, warnings = _limit_rho_t(0.01, adequately_anchored=False)
        assert rho_t == pytest.approx(ASCE41_RHO_T_CAP_UNANCHORED)
        assert len(warnings) == 1

    def test_valid_value_passes_through(self):
        rho_t, warnings = _limit_rho_t(0.01, adequately_anchored=True)
        assert rho_t == pytest.approx(0.01)
        assert warnings == []


# ---------------------------------------------------------------------------
# _unspliced_params
# ---------------------------------------------------------------------------

class TestUnsplicedParams:
    # Reference case: hand-computed values
    # axial_ratio=0.3, rho_t=0.01, fc=50 MPa, fyte=525 MPa, v_ratio=0.3
    axial_ratio = 0.3
    rho_t = 0.01
    fc = 50.0
    fyte = 525.0  # 1.25 * 420
    v_ratio = 0.3

    def _expected(self):
        r = min(self.axial_ratio, 0.5)
        a = max(0.042 - 0.043 * r + 0.63 * self.rho_t - 0.023 * self.v_ratio, 0.0)
        denom = 5.0 + (r / 0.8) * (self.fc / max(self.rho_t * self.fyte, 1e-9))
        b = max(0.5 / denom - 0.01, a)
        c = max(0.24 - 0.4 * max(self.axial_ratio, 0.1), 0.0)
        return a, b, c

    def test_a_matches_formula(self):
        a, b, c = _unspliced_params(self.axial_ratio, self.rho_t, self.fc, self.fyte, self.v_ratio)
        a_exp, _, _ = self._expected()
        assert a == pytest.approx(a_exp, rel=1e-6)

    def test_b_matches_formula(self):
        a, b, c = _unspliced_params(self.axial_ratio, self.rho_t, self.fc, self.fyte, self.v_ratio)
        _, b_exp, _ = self._expected()
        assert b == pytest.approx(b_exp, rel=1e-6)

    def test_c_matches_formula(self):
        a, b, c = _unspliced_params(self.axial_ratio, self.rho_t, self.fc, self.fyte, self.v_ratio)
        _, _, c_exp = self._expected()
        assert c == pytest.approx(c_exp, rel=1e-6)

    def test_b_never_less_than_a(self):
        # b >= a must always hold
        for axial in [0.1, 0.3, 0.5, 0.7]:
            a, b, c = _unspliced_params(axial, 0.005, 30.0, 420.0, 0.5)
            assert b >= a - 1e-10

    def test_all_params_nonnegative(self):
        for axial in [0.1, 0.3, 0.5, 0.6, 0.8]:
            a, b, c = _unspliced_params(axial, 0.005, 30.0, 420.0, 0.5)
            assert a >= 0.0
            assert b >= 0.0
            assert c >= 0.0

    def test_high_axial_reduces_a_and_b(self):
        # For axial_ratio > 0.5 the scaling factor reduces a and b
        a_low, b_low, _ = _unspliced_params(0.3, 0.01, 50.0, 525.0, 0.3)
        a_high, b_high, _ = _unspliced_params(0.6, 0.01, 50.0, 525.0, 0.3)
        assert a_high <= a_low
        assert b_high <= b_low


# ---------------------------------------------------------------------------
# _spliced_params
# ---------------------------------------------------------------------------

class TestSplicedParams:
    def test_no_two_tie_groups_gives_zero_a(self):
        a, b, c = _spliced_params(0.3, 0.01, 0.02, 420.0, 525.0, two_tie_groups=False)
        assert a == pytest.approx(0.0)

    def test_b_never_less_than_a(self):
        a, b, c = _spliced_params(0.3, 0.01, 0.02, 420.0, 525.0, two_tie_groups=True)
        assert b >= a - 1e-10

    def test_c_within_bounds(self):
        a, b, c = _spliced_params(0.3, 0.01, 0.02, 420.0, 525.0, two_tie_groups=True)
        assert 0.0 <= c <= 0.4

    def test_a_within_bounds(self):
        # a_sp is capped at ASCE41_SP_A_CAP = 0.025
        a, b, c = _spliced_params(0.1, 0.0175, 0.005, 420.0, 525.0, two_tie_groups=True)
        assert a <= 0.025


# ---------------------------------------------------------------------------
# Acceptance criteria factors from constants
# ---------------------------------------------------------------------------

class TestAcceptanceCriteriaFactors:
    def test_ls_is_half_b(self):
        # theta_ls = 0.5 * b
        assert ASCE41_THETA_LS_FACTOR == pytest.approx(0.5)

    def test_cp_is_0_7_b(self):
        # theta_cp = 0.7 * b
        assert ASCE41_THETA_CP_FACTOR == pytest.approx(0.7)
