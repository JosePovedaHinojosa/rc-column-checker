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


def add_info(results, column_id, load_case, check_name, provided, message, code_ref=''):
    results.append({
        'column_id': column_id,
        'load_case': load_case,
        'check_name': check_name,
        'status': 'INFO',
        'provided': provided,
        'required': '-',
        'code_ref': code_ref,
        'message': message,
    })


def add_warning(results, column_id, load_case, check_name, provided, required, message, code_ref=''):
    results.append({
        'column_id': column_id,
        'load_case': load_case,
        'check_name': check_name,
        'status': 'WARNING',
        'provided': provided,
        'required': required,
        'code_ref': code_ref,
        'message': message,
    })


def calc_lo_mm(h_col_mm: float, clear_height_mm: float) -> float:
    return max(h_col_mm, clear_height_mm / 6.0, 450.0)


def calc_so_eq_mm(hx_mm: float) -> float:
    so = 100.0 + (350.0 - hx_mm) / 3.0
    return max(100.0, min(150.0, so))


def calc_kf(fc_MPa: float) -> float:
    return max(fc_MPa / 175.0 + 0.6, 1.0)


def calc_kn(n_lateral_supported_bars: int) -> float:
    n = int(n_lateral_supported_bars)
    if n <= 2:
        return 1.0
    return n / (n - 2.0)


def _is_gravity_frame(row: Dict[str, object]) -> bool:
    return str(row.get('frame_type', '')).strip().upper().startswith('G')


def _table_18_7_5_4_rect_parts(row: Dict[str, object], geom: Dict[str, object]) -> tuple[float, float, float]:
    fc = float(row['fc_MPa'])
    fyt = float(row['fy_trans_MPa'])
    Ag = float(geom['Ag_mm2'])
    Ach = float(geom['Ach_mm2'])
    Pu_N = float(row['Pu_kN']) * 1e3
    kf = calc_kf(fc)
    kn = calc_kn(int(geom['n_lateral_supported_bars']))

    expr_a = 0.3 * max(Ag / max(Ach, 1e-9) - 1.0, 0.0) * (fc / max(fyt, 1e-9)) * kf * kn
    expr_b = 0.09 * (fc / max(fyt, 1e-9)) * kf * kn
    expr_c = 0.2 * kf * kn * Pu_N / max(fyt * Ach, 1e-9)
    return expr_a, expr_b, expr_c


def _table_18_7_5_4_circ_parts(row: Dict[str, object], geom: Dict[str, object]) -> tuple[float, float, float]:
    fc = float(row['fc_MPa'])
    fyt = float(row['fy_trans_MPa'])
    Ag = float(geom['Ag_mm2'])
    Ach = float(geom['Ach_mm2'])
    Pu_N = float(row['Pu_kN']) * 1e3
    kf = calc_kf(fc)
    kn = calc_kn(int(geom['n_lateral_supported_bars']))

    expr_d = 0.45 * max(Ag / max(Ach, 1e-9) - 1.0, 0.0) * (fc / max(fyt, 1e-9))
    expr_e = 0.12 * (fc / max(fyt, 1e-9))
    expr_f = 0.35 * Pu_N / max(fyt * Ach, 1e-9)
    return expr_d * kf * kn, expr_e * kf * kn, expr_f * kf * kn


def required_transverse_ratio(row: Dict[str, object], geom: Dict[str, object]) -> float:
    fc = float(row['fc_MPa'])
    Ag = float(geom['Ag_mm2'])
    Pu_N = float(row['Pu_kN']) * 1e3
    trigger_high = (Pu_N > 0.3 * Ag * fc) or (fc > 70.0)
    tie_type = str(row.get('tie_type', 'rectilinear')).strip().lower()
    if tie_type in {'circular', 'spiral'}:
        expr_d, expr_e, expr_f = _table_18_7_5_4_circ_parts(row, geom)
        return max(expr_d, expr_e, expr_f) if trigger_high else max(expr_d, expr_e)
    expr_a, expr_b, expr_c = _table_18_7_5_4_rect_parts(row, geom)
    return max(expr_a, expr_b, expr_c) if trigger_high else max(expr_a, expr_b)


def _gravity_half_table_ratio(row: Dict[str, object], geom: Dict[str, object]) -> float:
    tie_type = str(row.get('tie_type', 'rectilinear')).strip().lower()
    if tie_type in {'circular', 'spiral'}:
        expr_d, expr_e, _ = _table_18_7_5_4_circ_parts(row, geom)
        return 0.5 * max(expr_d, expr_e)
    expr_a, expr_b, _ = _table_18_7_5_4_rect_parts(row, geom)
    return 0.5 * max(expr_a, expr_b)


def _po_nominal_kN(row: Dict[str, object], geom: Dict[str, object]) -> float:
    fc = float(row['fc_MPa'])
    fy = float(row['fy_long_MPa'])
    Ag = float(geom['Ag_mm2'])
    As = float(geom['As_mm2'])
    return (0.85 * fc * (Ag - As) + fy * As) / 1e3


def transverse_checks(row: Dict[str, object], geom: Dict[str, object]) -> tuple[List[Dict[str, object]], Dict[str, float]]:
    cid = str(row['column_id'])
    load_case = str(row.get('load_case', 'U1'))
    results: List[Dict[str, object]] = []

    b = float(row['b_mm'])
    h = float(row['h_mm'])
    clear_height = float(row['clear_height_mm'])
    db_long = float(row['bar_db_mm'])
    fy_long = float(row['fy_long_MPa'])
    tie_db = float(row['tie_db_mm'])
    crosstie_db = float(row['crosstie_db_mm'])
    hook_angle = float(row['hook_angle_deg'])
    tie_spacing_lo = float(row['tie_spacing_lo_mm'])
    tie_spacing_out = float(row['tie_spacing_outside_lo_mm'])
    hx = float(geom['hx_mm'])
    fc = float(row['fc_MPa'])
    Ag = float(geom['Ag_mm2'])
    Pu_N = float(row['Pu_kN']) * 1e3
    frame_is_gravity = _is_gravity_frame(row)
    sdc = str(row.get('seismic_design_category', 'D')).strip().upper()
    gravity_actions_checked = bool(row.get('gravity_design_actions_checked', True))
    addl_cov = float(row.get('cover_additional_transverse_cover_mm', 999.0))
    addl_sp = float(row.get('cover_additional_transverse_spacing_mm', 999.0))

    lo_x = calc_lo_mm(h, clear_height)
    lo_y = calc_lo_mm(b, clear_height)
    min_dim = min(b, h)
    so_eq = calc_so_eq_mm(hx)
    db_limit_smf = 6.0 * db_long if fy_long <= 420.0 else 5.0 * db_long
    db_limit_gravity = 6.0 * db_long
    smax_lo_smf = min(min_dim / 4.0, db_limit_smf, so_eq)
    smax_out_smf = min(150.0, db_limit_smf)
    smax_full_gravity = min(150.0, db_limit_gravity)
    rho_s_req = required_transverse_ratio(row, geom)
    rho_s_x = float(geom['rho_s_x'])
    rho_s_y = float(geom['rho_s_y'])
    trigger_high = (Pu_N > 0.3 * Ag * fc) or (fc > 70.0)

    add_check(results, cid, load_case, 'lo_x_length', lo_x >= 450.0, round(lo_x, 1), '>= max(h, lclear/6, 450)', 'Special confining reinforcement length in x.', 'ACI 18.7.5.1')
    add_check(results, cid, load_case, 'lo_y_length', lo_y >= 450.0, round(lo_y, 1), '>= max(b, lclear/6, 450)', 'Special confining reinforcement length in y.', 'ACI 18.7.5.1')

    cover_trigger = float(row.get('cover_mm', 0.0)) > 100.0
    if cover_trigger:
        add_check(results, cid, load_case, 'cover_additional_transverse_cover', addl_cov <= 100.0, round(addl_cov, 1), '<= 100 mm', 'Additional transverse reinforcement cover outside confining reinforcement.', 'ACI 18.7.5.7')
        add_check(results, cid, load_case, 'cover_additional_transverse_spacing', addl_sp <= 300.0, round(addl_sp, 1), '<= 300 mm', 'Additional transverse reinforcement spacing outside confining reinforcement.', 'ACI 18.7.5.7')
    else:
        add_info(results, cid, load_case, 'cover_additional_transverse_not_required', f"cover={float(row.get('cover_mm', 0.0)):.1f} mm", 'Concrete cover outside confining transverse reinforcement does not exceed 100 mm.', 'ACI 18.7.5.7')

    if frame_is_gravity:
        po_kN = _po_nominal_kN(row, geom)
        gravity_trigger = max(float(row['Pu_kN']), 0.0) > 0.35 * po_kN
        gravity_rho_req = _gravity_half_table_ratio(row, geom) if gravity_trigger else 0.0

        add_info(results, cid, load_case, 'gravity_column_mode', 'ACI 18.14.3.2(b)-(c)', 'Gravity-column detailing branch enabled from frame_type.', 'ACI 18.14.3.2')
        add_check(results, cid, load_case, 'gravity_scope_sdc', sdc in {'D', 'E', 'F'}, sdc, 'D/E/F', 'Section 18.14 applies to non-SFRS members in structures assigned to SDC D, E, or F.', 'ACI 18.14.1.1')
        add_check(results, cid, load_case, 'gravity_design_actions_checked', gravity_actions_checked, gravity_actions_checked, True, 'Member is being evaluated for gravity load combinations including vertical ground motion effects acting simultaneously with design displacement demands.', 'ACI 18.14.2.1')
        add_info(results, cid, load_case, 'gravity_Po_kN', round(po_kN, 1), 'Nominal concentric axial strength proxy used for 0.35Po trigger.', 'ACI 18.14.3.2(c)')
        add_check(results, cid, load_case, 'gravity_tie_spacing_lo_full_length', tie_spacing_lo <= smax_full_gravity, round(tie_spacing_lo, 1), f'<= {smax_full_gravity:.1f} mm', 'Full-length gravity-column transverse reinforcement spacing within lo.', 'ACI 18.14.3.2(b)')
        add_check(results, cid, load_case, 'gravity_tie_spacing_outside_lo_full_length', tie_spacing_out <= smax_full_gravity or bool(row['spiral_provided']), round(tie_spacing_out, 1), f'<= {smax_full_gravity:.1f} mm', 'Full-length gravity-column transverse reinforcement spacing outside lo.', 'ACI 18.14.3.2(b)')
        add_check(results, cid, load_case, 'gravity_hook_angle_rectilinear', hook_angle >= 135.0, hook_angle, '>= 135 deg', 'Over lo from each joint face, transverse reinforcement to satisfy 18.7.5.2(b).', 'ACI 18.14.3.2(b) / 18.7.5.2(b)')
        add_check(results, cid, load_case, 'gravity_crosstie_diameter', crosstie_db >= tie_db, crosstie_db, f'>= {tie_db}', 'Over lo from each joint face, crosstie diameter shall not be smaller than hoop diameter.', 'ACI 18.14.3.2(b) / 18.7.5.2(c)')
        add_check(results, cid, load_case, 'gravity_crosstie_alternate_anchorage', bool(row['crosstie_alt_anchorage']), bool(row['crosstie_alt_anchorage']), True, 'Consecutive crossties alternated end for end over lo.', 'ACI 18.14.3.2(b) / 18.7.5.2(c)')
        add_check(results, cid, load_case, 'gravity_hx_general_limit', hx <= 350.0, round(hx, 1), '<= 350 mm', 'Maximum spacing between laterally supported longitudinal bars over lo.', 'ACI 18.14.3.2(b) / 18.7.5.2(e)')
        add_info(results, cid, load_case, 'gravity_joints_chapter15', 'See joint checks', 'Gravity columns shall have joints satisfying Chapter 15.', 'ACI 18.14.3.2(d)')

        if gravity_trigger:
            add_warning(results, cid, load_case, 'gravity_high_axial_flag', True, f'> 0.35Po = {0.35 * po_kN:.1f} kN', 'Gravity axial force exceeds 0.35Po; apply 18.14.3.2(c) branch.', 'ACI 18.14.3.2(c)')
            add_check(results, cid, load_case, 'gravity_rho_s_x_half_table', rho_s_x >= gravity_rho_req, round(rho_s_x, 5), f'>= {gravity_rho_req:.5f}', 'Minimum transverse ratio about x for gravity column with Pu_grav > 0.35Po.', 'ACI 18.14.3.2(c) / Table 18.7.5.4')
            add_check(results, cid, load_case, 'gravity_rho_s_y_half_table', rho_s_y >= gravity_rho_req, round(rho_s_y, 5), f'>= {gravity_rho_req:.5f}', 'Minimum transverse ratio about y for gravity column with Pu_grav > 0.35Po.', 'ACI 18.14.3.2(c) / Table 18.7.5.4')
            if cover_trigger:
                add_check(results, cid, load_case, 'gravity_cover_additional_transverse_required', (addl_cov <= 100.0) and (addl_sp <= 300.0), f'cover={addl_cov:.1f} mm, s={addl_sp:.1f} mm', 'cover <= 100 mm and s <= 300 mm', 'Additional transverse reinforcement outside confining reinforcement required when cover exceeds 100 mm.', 'ACI 18.14.3.2(c) / 18.7.5.7')
            else:
                add_info(results, cid, load_case, 'gravity_cover_additional_transverse_required', 'Not required', 'Concrete cover outside confining reinforcement does not exceed 100 mm.', 'ACI 18.14.3.2(c) / 18.7.5.7')
        else:
            add_check(results, cid, load_case, 'gravity_high_axial_flag', True, True, '<= 0.35Po', 'Gravity axial force does not exceed 0.35Po; 18.14.3.2(c) additional minimum transverse amount not triggered.', 'ACI 18.14.3.2(c)')

        meta = {
            'lo_x_mm': lo_x,
            'lo_y_mm': lo_y,
            'smax_lo_mm': smax_full_gravity,
            'smax_outside_lo_mm': smax_full_gravity,
            'tie_spacing_lo_mm': tie_spacing_lo,
            'tie_spacing_outside_lo_mm': tie_spacing_out,
            'rho_s_req': gravity_rho_req,
            'rho_s_x': rho_s_x,
            'rho_s_y': rho_s_y,
            'so_eq_mm': so_eq,
            'kn': calc_kn(int(geom['n_lateral_supported_bars'])),
            'kf': calc_kf(fc),
            'frame_branch': 'GRAVITY',
            'po_nominal_kN': po_kN,
            'gravity_trigger_0_35Po': gravity_trigger,
        }
        return results, meta

    add_check(results, cid, load_case, 'hook_angle_rectilinear', hook_angle >= 135.0, hook_angle, '>= 135 deg', 'Rectilinear hoops shall have 135-degree hooks.', 'ACI 18.7.5.2(b)')
    add_check(results, cid, load_case, 'crosstie_diameter', crosstie_db >= tie_db, crosstie_db, f'>= {tie_db}', 'Crosstie diameter shall not be smaller than hoop diameter.', 'ACI 18.7.5.2(c)')
    add_check(results, cid, load_case, 'crosstie_alternate_anchorage', bool(row['crosstie_alt_anchorage']), bool(row['crosstie_alt_anchorage']), True, 'Consecutive crossties alternated end for end.', 'ACI 18.7.5.2(c)')
    add_check(results, cid, load_case, 'hx_general_limit', hx <= 350.0, round(hx, 1), '<= 350 mm', 'Maximum spacing between laterally supported longitudinal bars.', 'ACI 18.7.5.2(e)')
    if trigger_high:
        add_check(results, cid, load_case, 'hx_special_limit', hx <= 200.0, round(hx, 1), '<= 200 mm', 'Special limit for high Pu or fc.', 'ACI 18.7.5.2(f)')
        add_check(results, cid, load_case, 'all_perimeter_bars_supported', int(geom['n_lateral_supported_bars']) >= int(geom['n_perimeter_bars']), f"{int(geom['n_lateral_supported_bars'])}/{int(geom['n_perimeter_bars'])}", 'all perimeter bars supported', 'All perimeter bars should be laterally supported.', 'ACI 18.7.5.2(f)')
    add_check(results, cid, load_case, 'tie_spacing_within_lo', tie_spacing_lo <= smax_lo_smf, round(tie_spacing_lo, 1), f'<= {smax_lo_smf:.1f} mm', 'Within lo tie spacing.', 'ACI 18.7.5.3')
    add_check(results, cid, load_case, 'tie_spacing_outside_lo', tie_spacing_out <= smax_out_smf or bool(row['spiral_provided']), round(tie_spacing_out, 1), f'<= {smax_out_smf:.1f} mm', 'Outside lo tie spacing.', 'ACI 18.7.5.5')
    add_check(results, cid, load_case, 'rho_s_x_required', rho_s_x >= rho_s_req, round(rho_s_x, 5), f'>= {rho_s_req:.5f}', 'Transverse reinforcement ratio about x.', 'ACI Table 18.7.5.4')
    add_check(results, cid, load_case, 'rho_s_y_required', rho_s_y >= rho_s_req, round(rho_s_y, 5), f'>= {rho_s_req:.5f}', 'Transverse reinforcement ratio about y.', 'ACI Table 18.7.5.4')

    meta = {
        'lo_x_mm': lo_x,
        'lo_y_mm': lo_y,
        'smax_lo_mm': smax_lo_smf,
        'smax_outside_lo_mm': smax_out_smf,
        'tie_spacing_lo_mm': tie_spacing_lo,
        'tie_spacing_outside_lo_mm': tie_spacing_out,
        'rho_s_req': rho_s_req,
        'rho_s_x': rho_s_x,
        'rho_s_y': rho_s_y,
        'so_eq_mm': so_eq,
        'kn': calc_kn(int(geom['n_lateral_supported_bars'])),
        'kf': calc_kf(fc),
        'frame_branch': 'SMF',
        'po_nominal_kN': _po_nominal_kN(row, geom),
        'gravity_trigger_0_35Po': False,
    }
    return results, meta
