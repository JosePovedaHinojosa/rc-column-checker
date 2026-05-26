from __future__ import annotations

import math
from typing import Dict, Iterable, List, Tuple


FACE_FIELDS = {
    'top': ('n_bars_x_top', 'support_lines_top_mm', 'x'),
    'bottom': ('n_bars_x_bottom', 'support_lines_bottom_mm', 'x'),
    'left': ('n_bars_y_left', 'support_lines_left_mm', 'y'),
    'right': ('n_bars_y_right', 'support_lines_right_mm', 'y'),
}


def steel_area_mm2(db_mm: float) -> float:
    return math.pi * db_mm ** 2 / 4.0


def parse_mm_list(value: object) -> List[float]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    raw = [x.strip() for x in text.replace('|', ';').replace(',', ';').split(';') if x.strip()]
    return [float(x) for x in raw]


def _distributed_positions(start_mm: float, end_mm: float, n_bars: int) -> List[float]:
    if n_bars <= 1:
        return [0.5 * (start_mm + end_mm)]
    step = (end_mm - start_mm) / (n_bars - 1)
    return [start_mm + i * step for i in range(n_bars)]


def perimeter_bar_layout(row: Dict[str, object]) -> Tuple[List[Dict[str, float]], Dict[str, List[float]]]:
    """
    Create unique perimeter bar coordinates from bars per face.
    Coordinates are referenced to the OUTER section edges.
    """
    b = float(row['b_mm'])
    h = float(row['h_mm'])
    cover = float(row['cover_mm'])
    tie_db = float(row['tie_db_mm'])
    bar_db = float(row['bar_db_mm'])

    # Column longitudinal bar centerline offset from outer edge.
    offset = cover + tie_db + bar_db / 2.0
    x_left = offset
    x_right = b - offset
    y_top = offset
    y_bottom = h - offset

    n_top = int(row['n_bars_x_top'])
    n_bottom = int(row['n_bars_x_bottom'])
    n_left = int(row['n_bars_y_left'])
    n_right = int(row['n_bars_y_right'])

    coords: Dict[Tuple[float, float], Dict[str, float]] = {}
    face_positions: Dict[str, List[float]] = {}

    top_x = _distributed_positions(x_left, x_right, n_top)
    face_positions['top'] = top_x
    for x in top_x:
        coords[(round(x, 6), round(y_top, 6))] = {'x_mm': x, 'y_mm': y_top, 'As_mm2': steel_area_mm2(bar_db), 'face': 'top'}

    bottom_x = _distributed_positions(x_left, x_right, n_bottom)
    face_positions['bottom'] = bottom_x
    for x in bottom_x:
        coords[(round(x, 6), round(y_bottom, 6))] = {'x_mm': x, 'y_mm': y_bottom, 'As_mm2': steel_area_mm2(bar_db), 'face': 'bottom'}

    left_y = _distributed_positions(y_top, y_bottom, n_left)
    face_positions['left'] = left_y
    for y in left_y:
        coords[(round(x_left, 6), round(y, 6))] = {'x_mm': x_left, 'y_mm': y, 'As_mm2': steel_area_mm2(bar_db), 'face': 'left'}

    right_y = _distributed_positions(y_top, y_bottom, n_right)
    face_positions['right'] = right_y
    for y in right_y:
        coords[(round(x_right, 6), round(y, 6))] = {'x_mm': x_right, 'y_mm': y, 'As_mm2': steel_area_mm2(bar_db), 'face': 'right'}

    bars = list(coords.values())
    return bars, face_positions


def _clean_support_lines(lines: Iterable[float], min_mm: float, max_mm: float) -> List[float]:
    cleaned = {min_mm, max_mm}
    for x in lines:
        xv = max(min_mm, min(float(x), max_mm))
        cleaned.add(round(xv, 6))
    return sorted(cleaned)


def _supported_indices(bar_positions: List[float], support_lines: List[float], tol_mm: float) -> List[int]:
    supported = []
    for i, xb in enumerate(bar_positions):
        if any(abs(xb - xs) <= tol_mm for xs in support_lines):
            supported.append(i)
    return supported


def _bar_spacing_mm(bar_positions: List[float]) -> float:
    if len(bar_positions) <= 1:
        return 0.0
    return max((b - a) for a, b in zip(bar_positions[:-1], bar_positions[1:]))


def _supported_gap_mm(bar_positions: List[float], supported_indices: List[int]) -> float:
    if len(bar_positions) <= 1:
        return 0.0
    if len(supported_indices) <= 1:
        return _bar_spacing_mm(bar_positions)
    pts = [bar_positions[i] for i in supported_indices]
    return max((b - a) for a, b in zip(pts[:-1], pts[1:]))


def _corner_adjusted_supported_count(s_face: Dict[str, List[int]], n_face: Dict[str, int]) -> int:
    total = sum(len(v) for v in s_face.values())
    corner_pairs = [
        ('top', 0, 'left', 0),
        ('top', n_face['top'] - 1, 'right', 0),
        ('bottom', 0, 'left', n_face['left'] - 1),
        ('bottom', n_face['bottom'] - 1, 'right', n_face['right'] - 1),
    ]
    duplicates = 0
    for f1, i1, f2, i2 in corner_pairs:
        if i1 in s_face.get(f1, []) and i2 in s_face.get(f2, []):
            duplicates += 1
    return total - duplicates


def compute_geometry(row: Dict[str, object]) -> Dict[str, object]:
    b = float(row['b_mm'])
    h = float(row['h_mm'])
    cover = float(row['cover_mm'])
    tie_db = float(row['tie_db_mm'])
    bar_db = float(row['bar_db_mm'])

    bars, face_positions = perimeter_bar_layout(row)
    n_face = {
        'top': int(row['n_bars_x_top']),
        'bottom': int(row['n_bars_x_bottom']),
        'left': int(row['n_bars_y_left']),
        'right': int(row['n_bars_y_right']),
    }

    Ag = b * h
    As_bar = steel_area_mm2(bar_db)
    As = sum(bar['As_mm2'] for bar in bars)
    rho_long = As / Ag if Ag > 0.0 else 0.0

    # Confined core measured to centerline of exterior hoop/tie.
    core_dim_x = b - 2.0 * (cover + tie_db / 2.0)
    core_dim_y = h - 2.0 * (cover + tie_db / 2.0)
    core_dim_x = max(core_dim_x, 0.0)
    core_dim_y = max(core_dim_y, 0.0)
    Ach = core_dim_x * core_dim_y

    # Support lines are interpreted as distances from OUTER FACES, matching typical detailing drawings.
    min_x = cover + tie_db / 2.0
    max_x = b - (cover + tie_db / 2.0)
    min_y = cover + tie_db / 2.0
    max_y = h - (cover + tie_db / 2.0)

    support_lines = {
        'top': _clean_support_lines(parse_mm_list(row['support_lines_top_mm']), min_x, max_x),
        'bottom': _clean_support_lines(parse_mm_list(row['support_lines_bottom_mm']), min_x, max_x),
        'left': _clean_support_lines(parse_mm_list(row['support_lines_left_mm']), min_y, max_y),
        'right': _clean_support_lines(parse_mm_list(row['support_lines_right_mm']), min_y, max_y),
    }

    face_spacings = {
        'top': _bar_spacing_mm(face_positions['top']),
        'bottom': _bar_spacing_mm(face_positions['bottom']),
        'left': _bar_spacing_mm(face_positions['left']),
        'right': _bar_spacing_mm(face_positions['right']),
    }
    positive_spacings = [v for v in face_spacings.values() if v > 0.0]
    support_tol = max(15.0, 0.25 * min(positive_spacings or [25.0]))

    supported_indices = {
        'top': _supported_indices(face_positions['top'], support_lines['top'], support_tol),
        'bottom': _supported_indices(face_positions['bottom'], support_lines['bottom'], support_tol),
        'left': _supported_indices(face_positions['left'], support_lines['left'], support_tol),
        'right': _supported_indices(face_positions['right'], support_lines['right'], support_tol),
    }

    n_perimeter_bars = len(bars)
    n_lateral_supported = _corner_adjusted_supported_count(supported_indices, n_face)

    hx_faces = {
        'top': _supported_gap_mm(face_positions['top'], supported_indices['top']),
        'bottom': _supported_gap_mm(face_positions['bottom'], supported_indices['bottom']),
        'left': _supported_gap_mm(face_positions['left'], supported_indices['left']),
        'right': _supported_gap_mm(face_positions['right'], supported_indices['right']),
    }
    hx_mm = max(hx_faces.values()) if hx_faces else 0.0

    clear_top = min((b2 - a2) for a2, b2 in zip(face_positions['top'][:-1], face_positions['top'][1:])) - bar_db if len(face_positions['top']) > 1 else b - 2 * (cover + tie_db + bar_db)
    clear_bottom = min((b2 - a2) for a2, b2 in zip(face_positions['bottom'][:-1], face_positions['bottom'][1:])) - bar_db if len(face_positions['bottom']) > 1 else b - 2 * (cover + tie_db + bar_db)
    clear_left = min((b2 - a2) for a2, b2 in zip(face_positions['left'][:-1], face_positions['left'][1:])) - bar_db if len(face_positions['left']) > 1 else h - 2 * (cover + tie_db + bar_db)
    clear_right = min((b2 - a2) for a2, b2 in zip(face_positions['right'][:-1], face_positions['right'][1:])) - bar_db if len(face_positions['right']) > 1 else h - 2 * (cover + tie_db + bar_db)
    free_spacing_min = min(clear_top, clear_bottom, clear_left, clear_right)

    # Simplified transverse reinforcement ratios along x and y directions.
    tie_area = steel_area_mm2(tie_db)
    rho_s_x = tie_area * max(len(support_lines['top']), 2) / max(float(row['tie_spacing_lo_mm']) * core_dim_x, 1e-9)
    rho_s_y = tie_area * max(len(support_lines['left']), 2) / max(float(row['tie_spacing_lo_mm']) * core_dim_y, 1e-9)

    return {
        'Ag_mm2': Ag,
        'Ach_mm2': Ach,
        'core_dim_x_mm': core_dim_x,
        'core_dim_y_mm': core_dim_y,
        'As_mm2': As,
        'As_bar_mm2': As_bar,
        'rho_long': rho_long,
        'n_perimeter_bars': n_perimeter_bars,
        'n_lateral_supported_bars': n_lateral_supported,
        'hx_mm': hx_mm,
        'hx_top_mm': hx_faces['top'],
        'hx_bottom_mm': hx_faces['bottom'],
        'hx_left_mm': hx_faces['left'],
        'hx_right_mm': hx_faces['right'],
        'bar_spacing_top_mm': face_spacings['top'],
        'bar_spacing_bottom_mm': face_spacings['bottom'],
        'bar_spacing_left_mm': face_spacings['left'],
        'bar_spacing_right_mm': face_spacings['right'],
        'free_spacing_min_mm': free_spacing_min,
        'rho_s_x': rho_s_x,
        'rho_s_y': rho_s_y,
        'support_tolerance_mm': support_tol,
        'n_supported_top': len(supported_indices['top']),
        'n_supported_bottom': len(supported_indices['bottom']),
        'n_supported_left': len(supported_indices['left']),
        'n_supported_right': len(supported_indices['right']),
        'support_lines_top_mm': ';'.join(f'{x:.1f}' for x in support_lines['top']),
        'support_lines_bottom_mm': ';'.join(f'{x:.1f}' for x in support_lines['bottom']),
        'support_lines_left_mm': ';'.join(f'{x:.1f}' for x in support_lines['left']),
        'support_lines_right_mm': ';'.join(f'{x:.1f}' for x in support_lines['right']),
        'bars': bars,
    }
