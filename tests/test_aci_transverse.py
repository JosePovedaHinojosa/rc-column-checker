"""
Unit tests for aci_transverse_checks.py helper functions.

Values are verified against ACI 318-22 clauses cited inline.
"""

import pytest

from constants import ACI_LO_MIN_MM, ACI_SO_MIN_MM, ACI_SO_MAX_MM
from aci_transverse_checks import calc_lo_mm, calc_so_eq_mm, calc_kf, calc_kn


# ---------------------------------------------------------------------------
# calc_lo_mm  —  ACI 18.7.5.1
# ---------------------------------------------------------------------------

class TestCalcLoMm:
    def test_governed_by_section_height(self):
        # h=600, lclear=3000 -> max(600, 500, 450) = 600
        assert calc_lo_mm(600.0, 3000.0) == pytest.approx(600.0)

    def test_governed_by_clear_height_over_6(self):
        # h=400, lclear=3600 -> max(400, 600, 450) = 600
        assert calc_lo_mm(400.0, 3600.0) == pytest.approx(600.0)

    def test_governed_by_absolute_minimum(self):
        # h=300, lclear=2400 -> max(300, 400, 450) = 450
        assert calc_lo_mm(300.0, 2400.0) == pytest.approx(ACI_LO_MIN_MM)

    def test_all_equal_returns_minimum(self):
        # h=450, lclear=2700 -> max(450, 450, 450) = 450
        assert calc_lo_mm(450.0, 2700.0) == pytest.approx(ACI_LO_MIN_MM)


# ---------------------------------------------------------------------------
# calc_so_eq_mm  —  ACI 18.7.5.3
# ---------------------------------------------------------------------------

class TestCalcSoEqMm:
    def test_high_hx_yields_minimum_so(self):
        # hx=350 -> so = 100 + 0/3 = 100 -> clamp to [100, 150] -> 100
        assert calc_so_eq_mm(350.0) == pytest.approx(ACI_SO_MIN_MM)

    def test_low_hx_yields_maximum_so(self):
        # hx=100 -> so = 100 + 250/3 = 183 -> clamped to 150
        assert calc_so_eq_mm(100.0) == pytest.approx(ACI_SO_MAX_MM)

    def test_midpoint(self):
        # hx=200 -> so = 100 + 150/3 = 150 -> exactly at max
        assert calc_so_eq_mm(200.0) == pytest.approx(ACI_SO_MAX_MM)

    def test_between_bounds(self):
        # hx=275 -> so = 100 + 75/3 = 125 -> within [100, 150]
        assert calc_so_eq_mm(275.0) == pytest.approx(125.0)


# ---------------------------------------------------------------------------
# calc_kf  —  ACI 18.7.5.4 (kf factor)
# ---------------------------------------------------------------------------

class TestCalcKf:
    def test_normal_strength_concrete_returns_one(self):
        # fc=28 -> 28/175 + 0.6 = 0.76 -> max(0.76, 1.0) = 1.0
        assert calc_kf(28.0) == pytest.approx(1.0)

    def test_high_strength_concrete(self):
        # fc=350 -> 350/175 + 0.6 = 2.6
        assert calc_kf(350.0) == pytest.approx(2.6, rel=1e-6)

    def test_threshold_for_kf_above_one(self):
        # kf = fc/175 + 0.6 = 1.0 when fc = 0.4*175 = 70
        assert calc_kf(70.0) == pytest.approx(1.0, abs=1e-9)
        assert calc_kf(71.0) > 1.0


# ---------------------------------------------------------------------------
# calc_kn  —  ACI 18.7.5.4 (kn factor)
# ---------------------------------------------------------------------------

class TestCalcKn:
    def test_two_bars_returns_one(self):
        # ACI: kn = n/(n-2); for n<=2 kn=1.0
        assert calc_kn(2) == pytest.approx(1.0)

    def test_one_bar_returns_one(self):
        assert calc_kn(1) == pytest.approx(1.0)

    def test_four_bars(self):
        # kn = 4 / (4-2) = 2.0
        assert calc_kn(4) == pytest.approx(2.0)

    def test_six_bars(self):
        # kn = 6 / (6-2) = 1.5
        assert calc_kn(6) == pytest.approx(1.5)

    def test_large_n_approaches_one(self):
        # As n -> inf, kn -> 1
        assert calc_kn(100) == pytest.approx(100 / 98, rel=1e-6)
