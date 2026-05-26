"""
Unit tests for section_capacity.py — the core structural calculations.

Each test uses hand-computable values so that a reviewer can verify
the expected result with a calculator or by inspecting the code clause.
"""

import math
import pytest

from constants import (
    ACI_BETA1_MAX, ACI_BETA1_MIN,
    ACI_PHI_COMPRESSION, ACI_PHI_TENSION,
    ACI_FYE_FACTOR,
    ACI_SCWB_FACTOR,
)
from section_capacity import (
    beta1,
    phi_from_tensile_strain,
    pure_axial_capacity,
    shear_capacity_base,
    _joint_coefficient,
    steel_area_mm2,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_row(b=300, h=300, fc=25, fy_long=420, fy_trans=420,
                cover=40, tie_db=10, bar_db=20,
                n_top=3, n_bot=3, n_left=3, n_right=3,
                tie_spacing_lo=100.0, Pu_kN=0.0):
    return {
        'b_mm': b, 'h_mm': h, 'fc_MPa': fc,
        'fy_long_MPa': fy_long, 'fy_trans_MPa': fy_trans,
        'cover_mm': cover, 'tie_db_mm': tie_db, 'bar_db_mm': bar_db,
        'n_bars_x_top': n_top, 'n_bars_x_bottom': n_bot,
        'n_bars_y_left': n_left, 'n_bars_y_right': n_right,
        'tie_spacing_lo_mm': tie_spacing_lo,
        'Pu_kN': Pu_kN,
        'support_lines_top_mm': '',
        'support_lines_bottom_mm': '',
        'support_lines_left_mm': '',
        'support_lines_right_mm': '',
    }


def _simple_geom(Ag=90000, Ach=72900, As=1256.6,
                 n_supported_top=3, n_supported_left=3):
    return {
        'Ag_mm2': Ag, 'Ach_mm2': Ach, 'As_mm2': As,
        'n_supported_top': n_supported_top,
        'n_supported_left': n_supported_left,
    }


# ---------------------------------------------------------------------------
# steel_area_mm2
# ---------------------------------------------------------------------------

class TestSteelArea:
    def test_20mm_bar(self):
        # pi * 20^2 / 4 = 314.159...
        assert abs(steel_area_mm2(20.0) - math.pi * 400 / 4) < 0.01

    def test_25mm_bar(self):
        assert abs(steel_area_mm2(25.0) - math.pi * 625 / 4) < 0.01


# ---------------------------------------------------------------------------
# beta1
# ---------------------------------------------------------------------------

class TestBeta1:
    def test_at_pivot_returns_max(self):
        # ACI Table 22.2.2.4.3: beta1 = 0.85 for f'c <= 28 MPa
        assert beta1(28.0) == pytest.approx(ACI_BETA1_MAX)

    def test_below_pivot_returns_max(self):
        assert beta1(20.0) == pytest.approx(ACI_BETA1_MAX)

    def test_at_35_mpa(self):
        # 0.85 - 0.05 * (35-28)/7 = 0.85 - 0.05 = 0.80
        assert beta1(35.0) == pytest.approx(0.80, abs=1e-9)

    def test_at_56_mpa_reaches_min(self):
        # 0.85 - 0.05 * (56-28)/7 = 0.85 - 0.20 = 0.65
        assert beta1(56.0) == pytest.approx(ACI_BETA1_MIN)

    def test_very_high_fc_clamped_at_min(self):
        # Any f'c high enough should hit the floor
        assert beta1(100.0) == pytest.approx(ACI_BETA1_MIN)


# ---------------------------------------------------------------------------
# phi_from_tensile_strain
# ---------------------------------------------------------------------------

class TestPhiFromTensileStrain:
    fy = 420.0  # MPa
    ey = 420.0 / 200_000.0  # = 0.0021

    def test_compression_controlled(self):
        # eps_t = 0 <= ey -> phi = 0.65
        assert phi_from_tensile_strain(0.0, self.fy) == pytest.approx(ACI_PHI_COMPRESSION)

    def test_tension_controlled(self):
        # eps_t >> ey + 0.003 -> phi = 0.90
        assert phi_from_tensile_strain(0.01, self.fy) == pytest.approx(ACI_PHI_TENSION)

    def test_at_ey_boundary(self):
        # Exactly at ey -> compression-controlled
        assert phi_from_tensile_strain(self.ey, self.fy) == pytest.approx(ACI_PHI_COMPRESSION)

    def test_at_upper_boundary(self):
        # Exactly at ey + 0.003 -> tension-controlled
        assert phi_from_tensile_strain(self.ey + 0.003, self.fy) == pytest.approx(ACI_PHI_TENSION)

    def test_midpoint_transition(self):
        # eps_t = ey + 0.0015 (halfway through transition)
        # phi = 0.65 + (0.90-0.65) * 0.5 = 0.775
        eps_mid = self.ey + 0.0015
        assert phi_from_tensile_strain(eps_mid, self.fy) == pytest.approx(0.775, abs=1e-9)


# ---------------------------------------------------------------------------
# pure_axial_capacity
# ---------------------------------------------------------------------------

class TestPureAxialCapacity:
    def test_known_section(self):
        # 300x300, fc=25, fy=420, 4 bars of 20mm
        # Ag = 90000
        # As = 4 * pi*400/4 = 1256.64 mm2
        # Pn0 = 0.85*25*(90000-1256.64) + 420*1256.64 = 2413.3 kN
        # phiPn0 = 0.65 * 2413.3 = 1568.6 kN
        row = _simple_row(b=300, h=300, fc=25, fy_long=420)
        As = 4 * steel_area_mm2(20.0)
        geom = _simple_geom(Ag=90000, As=As)
        result = pure_axial_capacity(row, geom)

        expected_pn0 = (0.85 * 25 * (90000 - As) + 420 * As) / 1e3
        assert result['Pn0_kN'] == pytest.approx(expected_pn0, rel=1e-4)
        assert result['phiPn0_kN'] == pytest.approx(0.65 * expected_pn0, rel=1e-4)
        assert result['phi_axial'] == pytest.approx(ACI_PHI_COMPRESSION)

    def test_phi_is_compression_phi(self):
        row = _simple_row()
        geom = _simple_geom()
        result = pure_axial_capacity(row, geom)
        assert result['phi_axial'] == ACI_PHI_COMPRESSION


# ---------------------------------------------------------------------------
# _joint_coefficient  (ACI 18.8.4.4)
# ---------------------------------------------------------------------------

class TestJointCoefficient:
    # Tabulated values for different confinement scenarios
    @pytest.mark.parametrize("col_cont, beam_cont, confined, expected", [
        (True,  True,  True,  1.7),
        (True,  True,  False, 1.3),
        (True,  False, True,  1.3),
        (True,  False, False, 1.0),
        (False, True,  True,  1.3),
        (False, True,  False, 1.0),
        (False, False, True,  1.0),
        (False, False, False, 0.7),
    ])
    def test_coefficient(self, col_cont, beam_cont, confined, expected):
        assert _joint_coefficient(col_cont, beam_cont, confined) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# shear_capacity_base
# ---------------------------------------------------------------------------

class TestShearCapacityBase:
    def test_phi_is_shear_phi(self):
        row = _simple_row(b=300, h=300, fc=25, fy_trans=420,
                          cover=40, tie_db=10, tie_spacing_lo=100)
        geom = _simple_geom(n_supported_top=3, n_supported_left=3)
        result = shear_capacity_base(row, geom)
        assert result['phi_shear'] == pytest.approx(0.75)

    def test_vc_formula(self):
        # Vc_x = 0.17 * sqrt(fc) * b * (h - cover)
        b, h, fc, cover = 300.0, 500.0, 25.0, 40.0
        row = _simple_row(b=b, h=h, fc=fc, cover=cover, tie_db=10, tie_spacing_lo=100)
        geom = _simple_geom(n_supported_top=3, n_supported_left=3)
        result = shear_capacity_base(row, geom)

        d_x = h - cover
        expected_Vc_x = 0.17 * math.sqrt(fc) * b * d_x / 1e3
        assert result['Vc_x_kN'] == pytest.approx(expected_Vc_x, rel=1e-4)

    def test_phiVn_greater_than_Vc(self):
        row = _simple_row(b=300, h=300, fc=25, fy_trans=420, cover=40,
                          tie_db=10, tie_spacing_lo=100)
        geom = _simple_geom(n_supported_top=3, n_supported_left=3)
        result = shear_capacity_base(row, geom)
        # phiVn must be greater than phi*Vc (steel adds capacity)
        assert result['phiVn_x_kN'] > 0.75 * result['Vc_x_kN']
