"""
Unit tests for geometry_utils.py.

The reference section is a 300x300 mm column with 40 mm cover, 10 mm ties,
and 20 mm longitudinal bars — simple enough to compute by hand.
"""

import math
import pytest

from geometry_utils import (
    compute_geometry,
    perimeter_bar_layout,
    parse_mm_list,
    steel_area_mm2,
    _bar_spacing_mm,
    _supported_gap_mm,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _row_300x300():
    """300x300 column with 4 bars per face (3 unique per side after corners)."""
    return {
        'b_mm': 300.0, 'h_mm': 300.0,
        'cover_mm': 40.0, 'tie_db_mm': 10.0, 'bar_db_mm': 20.0,
        'n_bars_x_top': 3, 'n_bars_x_bottom': 3,
        'n_bars_y_left': 3, 'n_bars_y_right': 3,
        'tie_spacing_lo_mm': 100.0,
        'support_lines_top_mm': '80;150;220',
        'support_lines_bottom_mm': '80;150;220',
        'support_lines_left_mm': '80;150;220',
        'support_lines_right_mm': '80;150;220',
    }


# ---------------------------------------------------------------------------
# parse_mm_list
# ---------------------------------------------------------------------------

class TestParseMmList:
    def test_semicolon_separator(self):
        assert parse_mm_list('10;20;30') == [10.0, 20.0, 30.0]

    def test_comma_separator(self):
        assert parse_mm_list('10,20,30') == [10.0, 20.0, 30.0]

    def test_empty_string(self):
        assert parse_mm_list('') == []

    def test_none_input(self):
        assert parse_mm_list(None) == []

    def test_single_value(self):
        assert parse_mm_list('150') == [150.0]


# ---------------------------------------------------------------------------
# _bar_spacing_mm
# ---------------------------------------------------------------------------

class TestBarSpacing:
    def test_evenly_spaced(self):
        # 3 bars at 0, 100, 200 -> max gap = 100
        assert _bar_spacing_mm([0.0, 100.0, 200.0]) == pytest.approx(100.0)

    def test_single_bar(self):
        assert _bar_spacing_mm([150.0]) == pytest.approx(0.0)

    def test_empty_list(self):
        assert _bar_spacing_mm([]) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _supported_gap_mm
# ---------------------------------------------------------------------------

class TestSupportedGap:
    def test_all_bars_supported(self):
        # positions [0, 50, 100], all supported -> max gap between supports = 50
        assert _supported_gap_mm([0.0, 50.0, 100.0], [0, 1, 2]) == pytest.approx(50.0)

    def test_only_endpoints_supported(self):
        # positions [0, 50, 100], only 0 and 2 supported -> gap = 100
        assert _supported_gap_mm([0.0, 50.0, 100.0], [0, 2]) == pytest.approx(100.0)

    def test_single_support(self):
        # Single supported index -> falls back to max gap between consecutive bars
        # positions [0, 50, 100]: max consecutive gap = 50
        result = _supported_gap_mm([0.0, 50.0, 100.0], [1])
        assert result == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# perimeter_bar_layout
# ---------------------------------------------------------------------------

class TestPerimeterBarLayout:
    def test_corner_bars_not_duplicated(self):
        # 3+3+3+3 bars with shared corners -> 8 unique bars
        row = _row_300x300()
        bars, _ = perimeter_bar_layout(row)
        assert len(bars) == 8

    def test_bar_area(self):
        row = _row_300x300()
        bars, _ = perimeter_bar_layout(row)
        expected_As = math.pi * 20.0 ** 2 / 4.0
        for bar in bars:
            assert bar['As_mm2'] == pytest.approx(expected_As)

    def test_bar_offset_from_cover(self):
        # Bar centreline = cover + tie_db (full diameter) + bar_db/2
        # Cover is measured to the OUTER face of the hoop.
        # = 40 + 10 + 10 = 60 mm from outer edge
        row = _row_300x300()
        bars, _ = perimeter_bar_layout(row)
        expected_offset = 40.0 + 10.0 + 20.0 / 2.0
        top_bars = [b for b in bars if b['face'] == 'top']
        for bar in top_bars:
            assert bar['y_mm'] == pytest.approx(expected_offset)


# ---------------------------------------------------------------------------
# compute_geometry
# ---------------------------------------------------------------------------

class TestComputeGeometry:
    def test_gross_area(self):
        geom = compute_geometry(_row_300x300())
        assert geom['Ag_mm2'] == pytest.approx(300.0 * 300.0)

    def test_confined_core_area(self):
        # core measured to hoop centreline: b - 2*(cover + tie_db/2)
        # = 300 - 2*(40 + 5) = 300 - 90 = 210
        geom = compute_geometry(_row_300x300())
        assert geom['core_dim_x_mm'] == pytest.approx(210.0)
        assert geom['core_dim_y_mm'] == pytest.approx(210.0)
        assert geom['Ach_mm2'] == pytest.approx(210.0 * 210.0)

    def test_steel_area(self):
        # 8 unique bars, each 20mm diameter
        geom = compute_geometry(_row_300x300())
        expected_As = 8 * steel_area_mm2(20.0)
        assert geom['As_mm2'] == pytest.approx(expected_As, rel=1e-5)

    def test_rho_long_in_valid_range(self):
        geom = compute_geometry(_row_300x300())
        assert 0.01 <= geom['rho_long'] <= 0.08

    def test_hx_not_zero(self):
        geom = compute_geometry(_row_300x300())
        assert geom['hx_mm'] > 0.0

    def test_rho_s_positive(self):
        geom = compute_geometry(_row_300x300())
        assert geom['rho_s_x'] > 0.0
        assert geom['rho_s_y'] > 0.0
