from __future__ import annotations

from typing import Dict, List

from constants import ACI_RHO_LONG_MAX_SMF, ACI_SMF_ASPECT_RATIO_MIN, ACI_SMF_MIN_DIMENSION_MM
from frame_types import GRAVITY, SMF, frame_class


def add_check(results, column_id, load_case, check_name, ok, provided, required, message, code_ref=''):
    results.append({
        'column_id': column_id,
        'load_case': load_case,
        'check_name': check_name,
        'status': 'OK' if ok else 'NG',
        'provided': provided,
        'required': required,
        'code_ref': code_ref,
        'message': message,
    })


def longitudinal_checks(row: Dict[str, object], geom: Dict[str, object]) -> tuple[List[Dict[str, object]], Dict[str, object]]:
    cid = str(row['column_id'])
    load_case = str(row.get('load_case', 'U1'))
    results: List[Dict[str, object]] = []

    b = float(row['b_mm'])
    h = float(row['h_mm'])
    n_bars = int(geom['n_perimeter_bars'])
    n_top = int(row['n_bars_x_top'])
    n_bot = int(row['n_bars_x_bottom'])
    n_left = int(row['n_bars_y_left'])
    n_right = int(row['n_bars_y_right'])
    fclass = frame_class(row)

    if fclass == SMF:
        min_dim_req = max(float(row['min_dim_required_mm']), ACI_SMF_MIN_DIMENSION_MM)
        add_check(results, cid, load_case, 'min_dimension', min(b, h) >= min_dim_req, min(b, h), f'>= {min_dim_req:.0f} mm', 'Shortest cross-sectional dimension of SMF column.', 'ACI 18.7.2.1(a)')
        aspect = min(b, h) / max(b, h)
        add_check(results, cid, load_case, 'aspect_ratio', aspect >= ACI_SMF_ASPECT_RATIO_MIN, round(aspect, 3), f'>= {ACI_SMF_ASPECT_RATIO_MIN}', 'Ratio of shortest to perpendicular cross-sectional dimension of SMF column.', 'ACI 18.7.2.1(b)')
    else:
        add_check(results, cid, load_case, 'min_dimension', min(b, h) >= float(row['min_dim_required_mm']), min(b, h), f">= {row['min_dim_required_mm']} mm", 'Minimum column dimension check.', 'Project rule')

    # rho limits: Chapter 10 allows 0.01-0.08 (10.6.1.1). SMF columns are capped at
    # 0.06 (18.7.4.1); gravity columns in SDC D/E/F inherit the same cap through
    # 18.14.3.2(b), which invokes 18.7.4.1.
    if fclass in (SMF, GRAVITY):
        rho_max = min(float(row['rho_max']), ACI_RHO_LONG_MAX_SMF)
        rho_ref = 'ACI 18.7.4.1' if fclass == SMF else 'ACI 18.14.3.2(b) / 18.7.4.1'
    else:
        rho_max = float(row['rho_max'])
        rho_ref = 'ACI 10.6.1.1'
    rho_min_ref = 'ACI 18.7.4.1' if fclass == SMF else 'ACI 10.6.1.1'
    add_check(results, cid, load_case, 'rho_longitudinal_min', geom['rho_long'] >= float(row['rho_min']), round(float(geom['rho_long']), 5), f">= {row['rho_min']}", 'Minimum longitudinal reinforcement ratio.', rho_min_ref)
    add_check(results, cid, load_case, 'rho_longitudinal_max', geom['rho_long'] <= rho_max, round(float(geom['rho_long']), 5), f'<= {rho_max}', 'Maximum longitudinal reinforcement ratio.', rho_ref)
    add_check(results, cid, load_case, 'n_bars_min_rect', n_bars >= int(row['n_bars_min_rect']), n_bars, f">= {int(row['n_bars_min_rect'])}", 'Minimum number of bars for rectangular column.', 'ACI 10.7.3.1')
    add_check(results, cid, load_case, 'bars_each_face_min', min(n_top, n_bot, n_left, n_right) >= 2, f"top={n_top}, bot={n_bot}, left={n_left}, right={n_right}", '>= 2 bars on each face', 'Rectangular perimeter model requires at least 2 bars per face.', 'Input geometry rule')
    add_check(results, cid, load_case, 'free_spacing_long_bars', geom['free_spacing_min_mm'] >= float(row['free_spacing_min_mm']), round(float(geom['free_spacing_min_mm']), 1), f">= {row['free_spacing_min_mm']} mm", 'Approximate clear spacing between perimeter longitudinal bars.', 'ACI 25.2.3')
    add_check(results, cid, load_case, 'core_geometry_positive', min(float(geom['core_dim_x_mm']), float(geom['core_dim_y_mm'])) > 0.0, f"bc={geom['core_dim_x_mm']:.1f}, hc={geom['core_dim_y_mm']:.1f}", '> 0', 'Computed confined core dimensions must be positive.', 'Derived geometry')

    return results, dict(geom)
