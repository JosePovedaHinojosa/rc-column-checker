from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Tuple

BEAM_FACES = ['beam_top_x', 'beam_bottom_x', 'beam_top_y', 'beam_bottom_y']
BEAM_SIDES = ['side1', 'side2']

COLUMN_SECTION_REQUIRED = [
    'column_section_id',
    'b_mm', 'h_mm', 'cover_mm',
    'fc_MPa', 'fy_long_MPa', 'fy_trans_MPa',
    'n_bars_x_top', 'n_bars_x_bottom', 'n_bars_y_left', 'n_bars_y_right',
    'bar_db_mm',
    'tie_type', 'tie_db_mm', 'tie_spacing_lo_mm', 'tie_spacing_outside_lo_mm',
    'crosstie_db_mm', 'hook_angle_deg', 'crosstie_alt_anchorage', 'overlapping_hoops', 'spiral_provided',
    'support_lines_top_mm', 'support_lines_bottom_mm', 'support_lines_left_mm', 'support_lines_right_mm',
]

BEAM_SECTION_REQUIRED = [
    'beam_section_id',
    'bw_mm', 'h_mm', 'cover_mm',
    'fc_MPa', 'fy_long_MPa', 'fy_trans_MPa',
    'n_bars_top', 'db_top_mm',
    'n_bars_bot', 'db_bot_mm',
    'stirrup_db_mm',
]

COLUMN_BEAM_REQUIRED = [
    'column_id', 'story', 'frame_type', 'column_section_id',
    'clear_height_mm',
    'top_other_column_section_id', 'bottom_other_column_section_id',
    'joint_top', 'joint_bottom', 'yielding_region_expected',
]
for face in BEAM_FACES:
    for side in BEAM_SIDES:
        COLUMN_BEAM_REQUIRED.extend([
            f'{face}_{side}_section_id', f'{face}_{side}_ln_mm', f'{face}_{side}_wu_kN_per_m',
            f'{face}_{side}_x_mm', f'{face}_{side}_ext_mm', f'{face}_{side}_continuous',
        ])

OPTIONAL_COLUMN_SECTION_NUMERIC = {
    'min_dim_required_mm': 300.0,
    'rho_min': 0.01,
    'rho_max': 0.08,
    'n_bars_min_rect': 4,
    'free_spacing_min_mm': 40.0,
    'asce_fye_factor': 1.25,
    'asce_fyte_factor': 1.25,
    'cover_additional_transverse_cover_mm': 999.0,
    'cover_additional_transverse_spacing_mm': 999.0,
}
OPTIONAL_COLUMN_SECTION_BOOL = {
    'asce_splice_controlled': False,
    'asce_splice_two_tie_groups': True,
    'asce_ties_adequately_anchored': True,
}
OPTIONAL_COLUMN_SECTION_TEXT = {'notes': ''}

OPTIONAL_COLUMN_BEAM_TEXT = {
    'top_other_column_section_id': 'same',
    'bottom_other_column_section_id': 'same',
    'seismic_design_category': 'D',
    'notes': '',
}
OPTIONAL_COLUMN_BEAM_BOOL = {'gravity_design_actions_checked': True}

LOAD_REQUIRED = ['column_id', 'load_case', 'Pu_kN', 'Mux_kNm', 'Muy_kNm', 'Vux_kN', 'Vuy_kN']
LOAD_OPTIONAL_NUMERIC = {'RotX': 0.0, 'RotY': 0.0}
LOAD_OPTIONAL_TEXT = {'damage_state': 'CP'}

COLUMN_SECTION_BOOL_COLUMNS = {
    'crosstie_alt_anchorage', 'overlapping_hoops', 'spiral_provided',
    *OPTIONAL_COLUMN_SECTION_BOOL.keys(),
}
COLUMN_SECTION_TEXT_COLUMNS = {
    'column_section_id', 'tie_type', 'support_lines_top_mm', 'support_lines_bottom_mm',
    'support_lines_left_mm', 'support_lines_right_mm', 'notes',
}

COLUMN_BEAM_BOOL_COLUMNS = {
    'joint_top', 'joint_bottom', 'yielding_region_expected',
    *OPTIONAL_COLUMN_BEAM_BOOL.keys(),
}
COLUMN_BEAM_TEXT_COLUMNS = {
    'column_id', 'story', 'frame_type', 'column_section_id', 'top_other_column_section_id',
    'bottom_other_column_section_id', 'seismic_design_category', 'notes',
}
for face in BEAM_FACES:
    for side in BEAM_SIDES:
        COLUMN_BEAM_BOOL_COLUMNS.add(f'{face}_{side}_continuous')
        COLUMN_BEAM_TEXT_COLUMNS.add(f'{face}_{side}_section_id')


# sample CSVs can omit these and the code will derive/use defaults
OPTIONAL_COLUMN_BEAM_NUMERIC = {'lu_mm': None}


def parse_bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {'1', 'true', 't', 'yes', 'y'}


def _to_float(row_num: int, name: str, value: object) -> float:
    try:
        return float(value)
    except Exception as exc:
        raise ValueError(f"Row {row_num}: could not parse numeric field '{name}' with value '{value}'") from exc


def _read_csv(path: str | Path) -> List[Dict[str, str]]:
    path = Path(path)
    with path.open('r', newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Project JSON (GUI save format) -> solver CSVs
# ---------------------------------------------------------------------------

def bar_positions(n: int, dim_mm: float, cover_mm: float,
                  tie_db_mm: float, bar_db_mm: float) -> List[float]:
    if n <= 0:
        return []
    offset = cover_mm + tie_db_mm + bar_db_mm / 2.0
    if n == 1:
        return [dim_mm / 2.0]
    return [offset + i * (dim_mm - 2 * offset) / (n - 1) for i in range(n)]


def support_lines_from_legs(n_legs: int, n_bars: int, dim_mm: float,
                            cover_mm: float, tie_db_mm: float, bar_db_mm: float) -> str:
    positions = bar_positions(n_bars, dim_mm, cover_mm, tie_db_mm, bar_db_mm)
    if not positions:
        return ''
    n_legs = max(2, min(n_legs, len(positions)))
    if n_legs >= len(positions):
        return ';'.join(f'{p:.0f}' for p in positions)
    m = len(positions) - 1
    indices = sorted({round(i * m / (n_legs - 1)) for i in range(n_legs)})
    return ';'.join(f'{positions[i]:.0f}' for i in indices)


def _write_dict_rows(path: Path, rows: List[Dict[str, object]]) -> None:
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def write_project_csvs(data: Dict[str, object], outdir: str | Path) -> Dict[str, Path]:
    """Convert a project dict (the GUI .json save format, version 1) into the four
    solver CSVs under `outdir`. Returns the paths keyed by CLI argument name."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    sec_rows: List[Dict[str, object]] = []
    for sec in data['column_sections']:
        n_lx = max(2, min(int(sec['n_legs_x']), int(sec['n_bars_x_top'])))
        n_ly = max(2, min(int(sec['n_legs_y']), int(sec['n_bars_y_left'])))
        sec_rows.append({
            'column_section_id':             sec['section_id'],
            'b_mm':                          sec['b_mm'],
            'h_mm':                          sec['h_mm'],
            'cover_mm':                      sec['cover_mm'],
            'fc_MPa':                        sec['fc_MPa'],
            'fy_long_MPa':                   sec['fy_long_MPa'],
            'fy_trans_MPa':                  sec['fy_trans_MPa'],
            'n_bars_x_top':                  sec['n_bars_x_top'],
            'n_bars_x_bottom':               sec['n_bars_x_bottom'],
            'n_bars_y_left':                 sec['n_bars_y_left'],
            'n_bars_y_right':                sec['n_bars_y_right'],
            'bar_db_mm':                     sec['bar_db_mm'],
            'tie_type':                      sec['tie_type'],
            'tie_db_mm':                     sec['tie_db_mm'],
            'tie_spacing_lo_mm':             sec['tie_spacing_lo_mm'],
            'tie_spacing_outside_lo_mm':     sec['tie_spacing_outside_lo_mm'],
            'crosstie_db_mm':                sec['crosstie_db_mm'],
            'hook_angle_deg':                int(sec['hook_angle_deg']),
            'crosstie_alt_anchorage':        sec['crosstie_alt_anchorage'],
            'overlapping_hoops':             sec['overlapping_hoops'],
            'spiral_provided':               sec['spiral_provided'],
            'support_lines_top_mm':          support_lines_from_legs(n_lx, int(sec['n_bars_x_top']),    float(sec['b_mm']), float(sec['cover_mm']), float(sec['tie_db_mm']), float(sec['bar_db_mm'])),
            'support_lines_bottom_mm':       support_lines_from_legs(n_lx, int(sec['n_bars_x_bottom']), float(sec['b_mm']), float(sec['cover_mm']), float(sec['tie_db_mm']), float(sec['bar_db_mm'])),
            'support_lines_left_mm':         support_lines_from_legs(n_ly, int(sec['n_bars_y_left']),   float(sec['h_mm']), float(sec['cover_mm']), float(sec['tie_db_mm']), float(sec['bar_db_mm'])),
            'support_lines_right_mm':        support_lines_from_legs(n_ly, int(sec['n_bars_y_right']),  float(sec['h_mm']), float(sec['cover_mm']), float(sec['tie_db_mm']), float(sec['bar_db_mm'])),
            'asce_splice_controlled':        sec['asce_splice_controlled'],
            'asce_splice_two_tie_groups':    sec['asce_splice_two_tie_groups'],
            'asce_ties_adequately_anchored': sec['asce_ties_adequately_anchored'],
        })

    beam_rows = list(data.get('beam_sections') or [])
    if not beam_rows:
        beam_rows = [dict(beam_section_id='_NONE', bw_mm=200, h_mm=400, cover_mm=40,
                          fc_MPa=28, fy_long_MPa=420, fy_trans_MPa=420,
                          n_bars_top=2, db_top_mm=12, n_bars_bot=2, db_bot_mm=12,
                          stirrup_db_mm=8)]

    cb_rows: List[Dict[str, object]] = []
    load_rows: List[Dict[str, object]] = []
    for asm in data['assemblies']:
        row: Dict[str, object] = {
            'column_id':                      asm['col_id'],
            'story':                          asm['story'],
            'frame_type':                     asm['frame_type'],
            'column_section_id':              asm['col_section_id'],
            'clear_height_mm':                asm['clear_height_mm'],
            'top_other_column_section_id':    asm['top_other_col_id'],
            'bottom_other_column_section_id': asm['bottom_other_col_id'],
            'joint_top':                      asm['joint_top'],
            'joint_bottom':                   asm['joint_bottom'],
            'yielding_region_expected':       asm['yielding_region_expected'],
            'seismic_design_category':        asm.get('seismic_design_category', 'D'),
            'lu_mm':                          asm.get('lu_mm', ''),  # blank -> clear_height_mm
        }
        for face in BEAM_FACES:
            for side in BEAM_SIDES:
                k = f'{face}_{side}'
                bfd = asm['beam_faces'][k]
                row[f'{k}_section_id']  = bfd['section_id']
                row[f'{k}_ln_mm']       = bfd['ln_mm']
                row[f'{k}_wu_kN_per_m'] = bfd['wu_kN_per_m']
                row[f'{k}_x_mm']        = bfd['x_mm']
                row[f'{k}_ext_mm']      = bfd['ext_mm']
                row[f'{k}_continuous']  = bfd['continuous']
        cb_rows.append(row)
        for lc in asm['load_cases']:
            load_rows.append({'column_id': asm['col_id'], **lc})

    paths = {
        'column_sections': outdir / 'col_sections.csv',
        'beam_sections':   outdir / 'beam_sections.csv',
        'column_beam':     outdir / 'col_beam.csv',
        'loads':           outdir / 'loads.csv',
    }
    _write_dict_rows(paths['column_sections'], sec_rows)
    _write_dict_rows(paths['beam_sections'], beam_rows)
    _write_dict_rows(paths['column_beam'], cb_rows)
    _write_dict_rows(paths['loads'], load_rows)
    return paths


def _normalize_text(text: object) -> str:
    return str(text).strip()


def _normalize_section_id(text: object) -> str:
    return _normalize_text(text)


def read_column_sections_csv(path: str | Path) -> Dict[str, Dict[str, object]]:
    rows = _read_csv(path)
    if not rows:
        raise ValueError('Column-sections CSV is empty.')
    missing = [c for c in COLUMN_SECTION_REQUIRED if c not in rows[0]]
    if missing:
        raise ValueError(f'Missing required columns in column-sections CSV: {missing}')
    parsed: Dict[str, Dict[str, object]] = {}
    for i, row in enumerate(rows, start=2):
        out: Dict[str, object] = {**OPTIONAL_COLUMN_SECTION_NUMERIC, **OPTIONAL_COLUMN_SECTION_BOOL, **OPTIONAL_COLUMN_SECTION_TEXT, **row}
        out['_row_number'] = i
        for c in COLUMN_SECTION_BOOL_COLUMNS:
            out[c] = parse_bool(out.get(c))
        for c in COLUMN_SECTION_REQUIRED:
            if c in COLUMN_SECTION_TEXT_COLUMNS or c in COLUMN_SECTION_BOOL_COLUMNS:
                continue
            out[c] = _to_float(i, c, out.get(c))
        for c in OPTIONAL_COLUMN_SECTION_NUMERIC.keys():
            out[c] = _to_float(i, c, out.get(c))
        out['column_section_id'] = _normalize_section_id(out['column_section_id'])
        if not out['column_section_id']:
            raise ValueError(f'Row {i}: empty column_section_id in column-sections CSV')
        out['tie_type'] = _normalize_text(out['tie_type']).lower()
        out['notes'] = _normalize_text(out.get('notes', ''))
        for c in ['support_lines_top_mm', 'support_lines_bottom_mm', 'support_lines_left_mm', 'support_lines_right_mm']:
            out[c] = _normalize_text(out[c])
        if out['column_section_id'] in parsed:
            raise ValueError(f"Duplicate column_section_id '{out['column_section_id']}' in column-sections CSV")
        parsed[str(out['column_section_id'])] = out
    return parsed


def read_beam_sections_csv(path: str | Path) -> Dict[str, Dict[str, object]]:
    rows = _read_csv(path)
    if not rows:
        raise ValueError('Beam-sections CSV is empty.')
    missing = [c for c in BEAM_SECTION_REQUIRED if c not in rows[0]]
    if missing:
        raise ValueError(f'Missing required columns in beam-sections CSV: {missing}')
    parsed: Dict[str, Dict[str, object]] = {}
    for i, row in enumerate(rows, start=2):
        out: Dict[str, object] = dict(row)
        out['_row_number'] = i
        for c in BEAM_SECTION_REQUIRED:
            if c == 'beam_section_id':
                continue
            out[c] = _to_float(i, c, out.get(c))
        out['beam_section_id'] = _normalize_section_id(out['beam_section_id'])
        if not out['beam_section_id']:
            raise ValueError(f'Row {i}: empty beam_section_id in beam-sections CSV')
        if out['beam_section_id'] in parsed:
            raise ValueError(f"Duplicate beam_section_id '{out['beam_section_id']}' in beam-sections CSV")
        parsed[str(out['beam_section_id'])] = out
    return parsed


def read_column_beam_csv(path: str | Path) -> Dict[str, Dict[str, object]]:
    rows = _read_csv(path)
    if not rows:
        raise ValueError('Column-beam-prop CSV is empty.')
    missing = [c for c in COLUMN_BEAM_REQUIRED if c not in rows[0]]
    if missing:
        raise ValueError(f'Missing required columns in column-beam-prop CSV: {missing}')
    parsed: Dict[str, Dict[str, object]] = {}
    for i, row in enumerate(rows, start=2):
        out: Dict[str, object] = {**OPTIONAL_COLUMN_BEAM_TEXT, **OPTIONAL_COLUMN_BEAM_BOOL, **row}
        out['_row_number'] = i
        for c in COLUMN_BEAM_BOOL_COLUMNS:
            out[c] = parse_bool(out.get(c))
        for c in COLUMN_BEAM_REQUIRED:
            if c in COLUMN_BEAM_TEXT_COLUMNS or c in COLUMN_BEAM_BOOL_COLUMNS:
                continue
            out[c] = _to_float(i, c, out.get(c))
        # optional lu_mm: if omitted or blank, use clear_height_mm
        raw_lu = row.get('lu_mm', None)
        if raw_lu is None or str(raw_lu).strip() == '':
            out['lu_mm'] = float(out['clear_height_mm'])
        else:
            out['lu_mm'] = _to_float(i, 'lu_mm', raw_lu)
        out['column_id'] = _normalize_text(out['column_id'])
        if not out['column_id']:
            raise ValueError(f'Row {i}: empty column_id in column-beam-prop CSV')
        out['story'] = _normalize_text(out['story'])
        out['frame_type'] = _normalize_text(out['frame_type'])
        out['column_section_id'] = _normalize_section_id(out['column_section_id'])
        out['top_other_column_section_id'] = _normalize_text(out.get('top_other_column_section_id', 'same')) or 'same'
        out['bottom_other_column_section_id'] = _normalize_text(out.get('bottom_other_column_section_id', 'same')) or 'same'
        out['seismic_design_category'] = _normalize_text(out.get('seismic_design_category', 'D')).upper() or 'D'
        out['notes'] = _normalize_text(out.get('notes', ''))
        for face in BEAM_FACES:
            for side in BEAM_SIDES:
                out[f'{face}_{side}_section_id'] = _normalize_text(out.get(f'{face}_{side}_section_id', ''))
        if out['column_id'] in parsed:
            raise ValueError(f"Duplicate column_id '{out['column_id']}' in column-beam-prop CSV")
        parsed[str(out['column_id'])] = out
    return parsed


def read_loads_csv(path: str | Path) -> List[Dict[str, object]]:
    rows = _read_csv(path)
    if not rows:
        raise ValueError('Loads CSV is empty.')
    missing = [c for c in LOAD_REQUIRED if c not in rows[0]]
    if missing:
        raise ValueError(f'Missing required columns in loads CSV: {missing}')
    parsed: List[Dict[str, object]] = []
    for i, row in enumerate(rows, start=2):
        out: Dict[str, object] = dict(row)
        out['_row_number'] = i
        out['column_id'] = _normalize_text(out['column_id'])
        out['load_case'] = _normalize_text(out.get('load_case', 'U1')) or 'U1'
        for c in ['Pu_kN', 'Mux_kNm', 'Muy_kNm', 'Vux_kN', 'Vuy_kN']:
            out[c] = _to_float(i, c, out.get(c))
        rotx_key = 'RotX' if 'RotX' in row else ('RotX_rad' if 'RotX_rad' in row else None)
        roty_key = 'RotY' if 'RotY' in row else ('RotY_rad' if 'RotY_rad' in row else ('RotZ' if 'RotZ' in row else ('RotZ_rad' if 'RotZ_rad' in row else None)))
        out['RotX'] = _to_float(i, rotx_key or 'RotX', out.get(rotx_key, LOAD_OPTIONAL_NUMERIC['RotX']))
        out['RotY'] = _to_float(i, roty_key or 'RotY', out.get(roty_key, LOAD_OPTIONAL_NUMERIC['RotY']))
        out['damage_state'] = _normalize_text(out.get('damage_state', LOAD_OPTIONAL_TEXT['damage_state'])).upper() or 'CP'
        if out['damage_state'] not in {'IO', 'LS', 'CP'}:
            raise ValueError(f"Row {i}: damage_state must be IO, LS, or CP, got '{out['damage_state']}'")
        parsed.append(out)
    return parsed


def _zero_beam_side_fields(face: str, side: str) -> Dict[str, object]:
    prefix = f'{face}_{side}'
    return {
        f'{prefix}_section_id': '',
        f'{prefix}_bw_mm': 0.0,
        f'{prefix}_h_mm': 0.0,
        f'{prefix}_cover_mm': 0.0,
        f'{prefix}_fc_MPa': 0.0,
        f'{prefix}_fy_long_MPa': 0.0,
        f'{prefix}_fy_trans_MPa': 0.0,
        f'{prefix}_n_bars_top': 0.0,
        f'{prefix}_db_top_mm': 0.0,
        f'{prefix}_n_bars_bot': 0.0,
        f'{prefix}_db_bot_mm': 0.0,
        f'{prefix}_stirrup_db_mm': 0.0,
    }


def assemble_column_properties(column_sections: Dict[str, Dict[str, object]], beam_sections: Dict[str, Dict[str, object]], column_beam: Dict[str, Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    assembled: Dict[str, Dict[str, object]] = {}
    for column_id, inst in column_beam.items():
        column_section_id = str(inst['column_section_id'])
        if column_section_id not in column_sections:
            raise ValueError(f"column_id '{column_id}' references unknown column_section_id '{column_section_id}'")
        sec = column_sections[column_section_id]
        row: Dict[str, object] = dict(inst)
        instance_notes = str(inst.get('notes', '')).strip()
        row['column_section_id'] = column_section_id
        for key, value in sec.items():
            if key in {'column_section_id', '_row_number'}:
                continue
            row[key] = value
        row['section_notes'] = str(sec.get('notes', '')).strip()
        row['notes'] = instance_notes
        for face in BEAM_FACES:
            for side in BEAM_SIDES:
                field_prefix = f'{face}_{side}'
                beam_section_id = _normalize_text(inst.get(f'{field_prefix}_section_id', ''))
                row[f'{field_prefix}_section_id'] = beam_section_id
                if not beam_section_id or beam_section_id.lower() in {'none', 'na', 'null', '0'}:
                    row.update(_zero_beam_side_fields(face, side))
                    continue
                if beam_section_id not in beam_sections:
                    raise ValueError(f"column_id '{column_id}' references unknown {field_prefix}_section_id '{beam_section_id}'")
                bsec = beam_sections[beam_section_id]
                row[f'{field_prefix}_bw_mm'] = bsec['bw_mm']
                row[f'{field_prefix}_h_mm'] = bsec['h_mm']
                row[f'{field_prefix}_cover_mm'] = bsec['cover_mm']
                row[f'{field_prefix}_fc_MPa'] = bsec['fc_MPa']
                row[f'{field_prefix}_fy_long_MPa'] = bsec['fy_long_MPa']
                row[f'{field_prefix}_fy_trans_MPa'] = bsec['fy_trans_MPa']
                row[f'{field_prefix}_n_bars_top'] = bsec['n_bars_top']
                row[f'{field_prefix}_db_top_mm'] = bsec['db_top_mm']
                row[f'{field_prefix}_n_bars_bot'] = bsec['n_bars_bot']
                row[f'{field_prefix}_db_bot_mm'] = bsec['db_bot_mm']
                row[f'{field_prefix}_stirrup_db_mm'] = bsec['stirrup_db_mm']
        assembled[column_id] = row
    return assembled


def read_inputs(column_sections_path: str | Path, beam_sections_path: str | Path, column_beam_path: str | Path, loads_path: str | Path) -> Tuple[Dict[str, Dict[str, object]], List[Dict[str, object]], Dict[str, Dict[str, object]], Dict[str, Dict[str, object]], Dict[str, Dict[str, object]]]:
    column_sections = read_column_sections_csv(column_sections_path)
    beam_sections = read_beam_sections_csv(beam_sections_path)
    column_beam = read_column_beam_csv(column_beam_path)
    columns = assemble_column_properties(column_sections, beam_sections, column_beam)
    loads = read_loads_csv(loads_path)
    merged: List[Dict[str, object]] = []
    for load in loads:
        cid = str(load['column_id'])
        if cid not in columns:
            raise ValueError(f"Loads CSV references unknown column_id '{cid}'")
        row = dict(columns[cid])
        row.update(load)
        merged.append(row)
    return columns, merged, column_sections, beam_sections, column_beam
