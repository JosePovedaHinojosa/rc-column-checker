from __future__ import annotations

from typing import Dict, List


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

    add_check(results, cid, load_case, 'min_dimension', min(b, h) >= float(row['min_dim_required_mm']), min(b, h), f">= {row['min_dim_required_mm']} mm", 'Minimum column dimension check.', 'Project rule')
    add_check(results, cid, load_case, 'rho_longitudinal_min', geom['rho_long'] >= float(row['rho_min']), round(float(geom['rho_long']), 5), f">= {row['rho_min']}", 'Minimum longitudinal reinforcement ratio.', 'ACI longitudinal ratio')
    add_check(results, cid, load_case, 'rho_longitudinal_max', geom['rho_long'] <= float(row['rho_max']), round(float(geom['rho_long']), 5), f"<= {row['rho_max']}", 'Maximum longitudinal reinforcement ratio.', 'ACI longitudinal ratio')
    add_check(results, cid, load_case, 'n_bars_min_rect', n_bars >= int(row['n_bars_min_rect']), n_bars, f">= {int(row['n_bars_min_rect'])}", 'Minimum number of bars for rectangular column.', 'ACI longitudinal detailing')
    add_check(results, cid, load_case, 'bars_each_face_min', min(n_top, n_bot, n_left, n_right) >= 2, f"top={n_top}, bot={n_bot}, left={n_left}, right={n_right}", '>= 2 bars on each face', 'Rectangular perimeter model requires at least 2 bars per face.', 'Input geometry rule')
    add_check(results, cid, load_case, 'free_spacing_long_bars', geom['free_spacing_min_mm'] >= float(row['free_spacing_min_mm']), round(float(geom['free_spacing_min_mm']), 1), f">= {row['free_spacing_min_mm']} mm", 'Approximate clear spacing between perimeter longitudinal bars.', 'ACI bar spacing')
    add_check(results, cid, load_case, 'core_geometry_positive', min(float(geom['core_dim_x_mm']), float(geom['core_dim_y_mm'])) > 0.0, f"bc={geom['core_dim_x_mm']:.1f}, hc={geom['core_dim_y_mm']:.1f}", '> 0', 'Computed confined core dimensions must be positive.', 'Derived geometry')

    return results, dict(geom)
