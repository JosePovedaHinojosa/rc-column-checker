from __future__ import annotations

import math
from typing import Dict, List

from constants import (
    ACI_ALPHA1,
    ACI_BETA1_FC_PIVOT, ACI_BETA1_FC_STEP, ACI_BETA1_MAX, ACI_BETA1_MIN, ACI_BETA1_SLOPE,
    ACI_ECU,
    ACI_ES_MPA,
    ACI_FYE_FACTOR,
    ACI_PHI_COMPRESSION, ACI_PHI_JOINT, ACI_PHI_SHEAR, ACI_PHI_TENSION, ACI_PHI_TRANSITION_STRAIN,
    ACI_SCWB_FACTOR,
    ACI_VC_COEFF, ACI_VC_ZERO_AXIAL_DIVISOR,
)

BEAM_PREFIXES = ['beam_top_x', 'beam_bottom_x', 'beam_top_y', 'beam_bottom_y']


def steel_area_mm2(db_mm: float) -> float:
    return math.pi * db_mm ** 2 / 4.0


def beta1(fc_mpa: float) -> float:
    if fc_mpa <= ACI_BETA1_FC_PIVOT:
        return ACI_BETA1_MAX
    val = ACI_BETA1_MAX - ACI_BETA1_SLOPE * ((fc_mpa - ACI_BETA1_FC_PIVOT) / ACI_BETA1_FC_STEP)
    return max(ACI_BETA1_MIN, min(ACI_BETA1_MAX, val))


def phi_from_tensile_strain(eps_t: float, fy_mpa: float) -> float:
    ey = fy_mpa / ACI_ES_MPA
    if eps_t <= ey:
        return ACI_PHI_COMPRESSION
    if eps_t >= ey + ACI_PHI_TRANSITION_STRAIN:
        return ACI_PHI_TENSION
    return ACI_PHI_COMPRESSION + (ACI_PHI_TENSION - ACI_PHI_COMPRESSION) * (eps_t - ey) / ACI_PHI_TRANSITION_STRAIN


def section_response(row: Dict[str, object], geom: Dict[str, object], axis: str, c_mm: float, fy_long_mpa: float, compression_face: str) -> Dict[str, float]:
    b = float(row['b_mm'])
    h = float(row['h_mm'])
    fc = float(row['fc_MPa'])
    bars = geom['bars']

    if axis == 'x':
        section_depth = h
        compression_width = b
        concrete_face_coord = 0.0 if compression_face == 'top' else h
        bar_coord_name = 'y_mm'
        centroid_coord = h / 2.0
        sign = 1.0 if compression_face == 'top' else -1.0
    else:
        section_depth = b
        compression_width = h
        concrete_face_coord = 0.0 if compression_face == 'left' else b
        bar_coord_name = 'x_mm'
        centroid_coord = b / 2.0
        sign = 1.0 if compression_face == 'left' else -1.0

    c_mm = max(min(c_mm, 10.0 * section_depth), 1e-6)
    a_mm = min(beta1(fc) * c_mm, section_depth)
    Cc_N = ACI_ALPHA1 * fc * compression_width * a_mm
    conc_coord = concrete_face_coord + sign * (a_mm / 2.0)

    Pn_N = Cc_N
    Mn_Nmm = Cc_N * (conc_coord - centroid_coord)
    max_tension_strain = 0.0

    for bar in bars:
        coord = float(bar[bar_coord_name])
        dist = sign * (coord - concrete_face_coord)
        eps = ACI_ECU * (1.0 - dist / c_mm)
        stress = max(min(ACI_ES_MPA * eps, fy_long_mpa), -fy_long_mpa)
        force = stress * float(bar['As_mm2'])
        Pn_N += force
        Mn_Nmm += force * (coord - centroid_coord)
        if eps < 0.0:
            max_tension_strain = max(max_tension_strain, -eps)

    phi = phi_from_tensile_strain(max_tension_strain, fy_long_mpa)
    return {
        'Pn_kN': Pn_N / 1e3,
        'Mn_kNm': abs(Mn_Nmm) / 1e6,
        'phiPn_kN': phi * Pn_N / 1e3,
        'phiMn_kNm': phi * abs(Mn_Nmm) / 1e6,
        'phi': phi,
        'eps_t': max_tension_strain,
        'c_mm': c_mm,
        'a_mm': a_mm,
    }


def interaction_points(row: Dict[str, object], geom: Dict[str, object], axis: str, fy_long_mpa: float, compression_face: str, npts: int = 180) -> List[Dict[str, float]]:
    section_depth = float(row['h_mm'] if axis == 'x' else row['b_mm'])
    c_values = [section_depth * (10 ** t) for t in [(-3.0 + i * (4.0 / (npts - 1))) for i in range(npts)]]
    pts = [section_response(row, geom, axis, c_mm=c, fy_long_mpa=fy_long_mpa, compression_face=compression_face) for c in c_values]
    pts.append(section_response(row, geom, axis, c_mm=100.0 * section_depth, fy_long_mpa=fy_long_mpa, compression_face=compression_face))
    return pts


def _interpolate_strength(points: List[Dict[str, float]], target_pu_kN: float, use_phi: bool) -> Dict[str, float]:
    p_key = 'phiPn_kN' if use_phi else 'Pn_kN'
    m_key = 'phiMn_kNm' if use_phi else 'Mn_kNm'
    pts = sorted(points, key=lambda p: p[p_key])

    if target_pu_kN <= pts[0][p_key]:
        best = pts[0]
        return {'P_kN': best[p_key], 'M_kNm': best[m_key], 'phi': best['phi'], 'eps_t': best['eps_t'], 'c_mm': best['c_mm']}
    if target_pu_kN >= pts[-1][p_key]:
        best = pts[-1]
        return {'P_kN': best[p_key], 'M_kNm': best[m_key], 'phi': best['phi'], 'eps_t': best['eps_t'], 'c_mm': best['c_mm']}

    for p1, p2 in zip(pts[:-1], pts[1:]):
        p_lo = p1[p_key]
        p_hi = p2[p_key]
        if p_lo <= target_pu_kN <= p_hi or p_hi <= target_pu_kN <= p_lo:
            denom = p_hi - p_lo
            ratio = 0.0 if abs(denom) < 1e-9 else (target_pu_kN - p_lo) / denom
            return {
                'P_kN': target_pu_kN,
                'M_kNm': p1[m_key] + ratio * (p2[m_key] - p1[m_key]),
                'phi': p1['phi'] + ratio * (p2['phi'] - p1['phi']),
                'eps_t': p1['eps_t'] + ratio * (p2['eps_t'] - p1['eps_t']),
                'c_mm': p1['c_mm'] + ratio * (p2['c_mm'] - p1['c_mm']),
            }

    best = min(pts, key=lambda p: abs(p[p_key] - target_pu_kN))
    return {'P_kN': best[p_key], 'M_kNm': best[m_key], 'phi': best['phi'], 'eps_t': best['eps_t'], 'c_mm': best['c_mm']}


def pure_axial_capacity(row: Dict[str, object], geom: Dict[str, object]) -> Dict[str, float]:
    fc = float(row['fc_MPa'])
    fy = float(row['fy_long_MPa'])
    Ag = float(geom['Ag_mm2'])
    As = float(geom['As_mm2'])
    Pn0_N = ACI_ALPHA1 * fc * (Ag - As) + fy * As
    phi = ACI_PHI_COMPRESSION
    return {'Pn0_kN': Pn0_N / 1e3, 'phiPn0_kN': phi * Pn0_N / 1e3, 'phi_axial': phi}


def pure_flexure_capacity(row: Dict[str, object], geom: Dict[str, object], axis: str) -> Dict[str, float]:
    fy = float(row['fy_long_MPa'])
    face1, face2 = ('top', 'bottom') if axis == 'x' else ('left', 'right')
    pts_pos = interaction_points(row, geom, axis, fy_long_mpa=fy, compression_face=face1)
    pts_neg = interaction_points(row, geom, axis, fy_long_mpa=fy, compression_face=face2)
    pts_prob_pos = interaction_points(row, geom, axis, fy_long_mpa=ACI_FYE_FACTOR * fy, compression_face=face1)
    pts_prob_neg = interaction_points(row, geom, axis, fy_long_mpa=ACI_FYE_FACTOR * fy, compression_face=face2)
    nominal_pos = _interpolate_strength(pts_pos, 0.0, use_phi=False)
    nominal_neg = _interpolate_strength(pts_neg, 0.0, use_phi=False)
    design_pos = _interpolate_strength(pts_pos, 0.0, use_phi=True)
    design_neg = _interpolate_strength(pts_neg, 0.0, use_phi=True)
    probable_pos = _interpolate_strength(pts_prob_pos, 0.0, use_phi=False)
    probable_neg = _interpolate_strength(pts_prob_neg, 0.0, use_phi=False)
    return {
        'Mn_pos_kNm': nominal_pos['M_kNm'], 'Mn_neg_kNm': nominal_neg['M_kNm'],
        'phiMn_pos_kNm': design_pos['M_kNm'], 'phiMn_neg_kNm': design_neg['M_kNm'],
        'Mpr_pos_kNm': probable_pos['M_kNm'], 'Mpr_neg_kNm': probable_neg['M_kNm'],
        'Mn_min_kNm': min(nominal_pos['M_kNm'], nominal_neg['M_kNm']),
        'phiMn_min_kNm': min(design_pos['M_kNm'], design_neg['M_kNm']),
        'Mpr_min_kNm': min(probable_pos['M_kNm'], probable_neg['M_kNm']),
    }


def column_strengths_at_Pu(row: Dict[str, object], geom: Dict[str, object], axis: str) -> Dict[str, float]:
    Pu = float(row['Pu_kN'])
    fy = float(row['fy_long_MPa'])
    face1, face2 = ('top', 'bottom') if axis == 'x' else ('left', 'right')

    pts_pos = interaction_points(row, geom, axis, fy_long_mpa=fy, compression_face=face1)
    pts_neg = interaction_points(row, geom, axis, fy_long_mpa=fy, compression_face=face2)
    nominal_pos = _interpolate_strength(pts_pos, Pu, use_phi=False)
    nominal_neg = _interpolate_strength(pts_neg, Pu, use_phi=False)
    design_pos = _interpolate_strength(pts_pos, Pu, use_phi=True)
    design_neg = _interpolate_strength(pts_neg, Pu, use_phi=True)

    fy_prob = ACI_FYE_FACTOR * fy
    pts_prob_pos = interaction_points(row, geom, axis, fy_long_mpa=fy_prob, compression_face=face1)
    pts_prob_neg = interaction_points(row, geom, axis, fy_long_mpa=fy_prob, compression_face=face2)
    probable_pos = _interpolate_strength(pts_prob_pos, Pu, use_phi=False)
    probable_neg = _interpolate_strength(pts_prob_neg, Pu, use_phi=False)

    return {
        'axis': axis,
        'Mn_pos_kNm': nominal_pos['M_kNm'],
        'Mn_neg_kNm': nominal_neg['M_kNm'],
        'phiMn_pos_kNm': design_pos['M_kNm'],
        'phiMn_neg_kNm': design_neg['M_kNm'],
        'phi_pos': design_pos['phi'], 'phi_neg': design_neg['phi'],
        'eps_t_pos': design_pos['eps_t'], 'eps_t_neg': design_neg['eps_t'],
        'c_pos_mm': design_pos['c_mm'], 'c_neg_mm': design_neg['c_mm'],
        'Mnc_kNm': min(nominal_pos['M_kNm'], nominal_neg['M_kNm']),
        'phiMn_kNm': min(design_pos['M_kNm'], design_neg['M_kNm']),
        'Mpr_pos_kNm': probable_pos['M_kNm'], 'Mpr_neg_kNm': probable_neg['M_kNm'],
        'points_pos': pts_pos, 'points_neg': pts_neg,
        'points_prob_pos': pts_prob_pos, 'points_prob_neg': pts_prob_neg,
    }


def _beam_side_strength(face: str, side: str, row: Dict[str, object]) -> Dict[str, float]:
    prefix = f"{face}_{side}"
    bw = float(row.get(f'{prefix}_bw_mm', 0.0) or 0.0)
    h = float(row.get(f'{prefix}_h_mm', 0.0) or 0.0)
    cover = float(row.get(f'{prefix}_cover_mm', 0.0) or 0.0)
    n_top = float(row.get(f'{prefix}_n_bars_top', 0.0) or 0.0)
    db_top = float(row.get(f'{prefix}_db_top_mm', 0.0) or 0.0)
    n_bot = float(row.get(f'{prefix}_n_bars_bot', 0.0) or 0.0)
    db_bot = float(row.get(f'{prefix}_db_bot_mm', 0.0) or 0.0)
    fc = float(row.get(f'{prefix}_fc_MPa', row['fc_MPa']) or 0.0)
    fy = float(row.get(f'{prefix}_fy_long_MPa', row['fy_long_MPa']) or 0.0)
    ln_m = float(row.get(f'{prefix}_ln_mm', 0.0) or 0.0) / 1000.0
    wu = float(row.get(f'{prefix}_wu_kN_per_m', 0.0) or 0.0)
    x_mm = float(row.get(f'{prefix}_x_mm', 0.0) or 0.0)
    ext_mm = float(row.get(f'{prefix}_ext_mm', 0.0) or 0.0)
    stirrup_db_mm = float(row.get(f'{prefix}_stirrup_db_mm', 0.0) or 0.0)
    continuous = bool(row.get(f'{prefix}_continuous', False))
    section_id = str(row.get(f'{prefix}_section_id', '') or '').strip()
    active = bool(section_id and section_id.lower() not in {'none', 'na', 'null', '0'} and bw > 0.0 and h > 0.0)

    As_top = n_top * steel_area_mm2(db_top)
    As_bot = n_bot * steel_area_mm2(db_bot)

    def beam_Mn(As_tension_mm2: float, fy_eff: float) -> tuple[float, float, float]:
        if bw <= 0.0 or h <= 0.0 or As_tension_mm2 <= 0.0:
            return 0.0, 0.0, 0.0
        a = As_tension_mm2 * fy_eff / max(ACI_ALPHA1 * fc * bw, 1e-9)
        d = h - cover
        jd = max(d - a / 2.0, 0.0)
        Mn = As_tension_mm2 * fy_eff * jd / 1e6
        T = As_tension_mm2 * fy_eff / 1e3
        return Mn, jd, T

    Mn_pos, jd_pos, T_pos = beam_Mn(As_bot, fy)
    Mn_neg, jd_neg, T_neg = beam_Mn(As_top, fy)
    Mpr_pos, jd_prob_pos, Tpr_pos = beam_Mn(As_bot, ACI_FYE_FACTOR * fy)
    Mpr_neg, jd_prob_neg, Tpr_neg = beam_Mn(As_top, ACI_FYE_FACTOR * fy)
    joint_Mn = max(Mn_pos, Mn_neg)
    joint_Mpr = max(Mpr_pos, Mpr_neg)
    joint_Tpr = max(Tpr_pos, Tpr_neg)
    if ln_m > 0.0:
        Ve_plus = (joint_Mpr + joint_Mpr) / ln_m + wu * ln_m / 2.0
        Ve_minus = max((joint_Mpr + joint_Mpr) / ln_m - wu * ln_m / 2.0, 0.0)
    else:
        Ve_plus = 0.0
        Ve_minus = 0.0
    return {
        'section_id': section_id, 'active': active,
        'bw_mm': bw, 'h_mm': h, 'cover_mm': cover,
        'n_bars_top': n_top, 'db_top_mm': db_top, 'As_top_mm2': As_top,
        'n_bars_bot': n_bot, 'db_bot_mm': db_bot, 'As_bot_mm2': As_bot,
        'Mn_pos_kNm': Mn_pos, 'Mn_neg_kNm': Mn_neg,
        'Mpr_pos_kNm': Mpr_pos, 'Mpr_neg_kNm': Mpr_neg,
        'Tpr_pos_kN': Tpr_pos, 'Tpr_neg_kN': Tpr_neg,
        'joint_Mn_kNm': joint_Mn, 'joint_Mpr_kNm': joint_Mpr, 'joint_Tpr_kN': joint_Tpr,
        'jd_pos_mm': jd_pos, 'jd_neg_mm': jd_neg,
        'Ve_plus_kN': Ve_plus, 'Ve_minus_kN': Ve_minus,
        'ln_m': ln_m, 'wu_kN_per_m': wu, 'x_mm': x_mm, 'ext_mm': ext_mm,
        'stirrup_db_mm': stirrup_db_mm, 'continuous': continuous,
    }


def compute_beam_actions(row: Dict[str, object]) -> Dict[str, float]:
    data: Dict[str, float] = {}
    for face in ['beam_top_x', 'beam_bottom_x', 'beam_top_y', 'beam_bottom_y']:
        sides = []
        for side in ['side1', 'side2']:
            sub = _beam_side_strength(face, side, row)
            sides.append(sub)
            for k, v in sub.items():
                data[f'{face}_{side}_{k}'] = v
        active = [s for s in sides if s['active']]
        n_active = len(active)
        data[f'{face}_n_active'] = n_active
        data[f'{face}_section_ids'] = ', '.join([str(s['section_id']) for s in active])
        data[f'{face}_single_sided'] = n_active == 1
        data[f'{face}_continuous'] = (n_active >= 2) or any(bool(s['continuous']) for s in active)
        data[f'{face}_bw_mm'] = max([float(s['bw_mm']) for s in active], default=0.0)
        data[f'{face}_h_mm'] = max([float(s['h_mm']) for s in active], default=0.0)
        data[f'{face}_cover_mm'] = max([float(s['cover_mm']) for s in active], default=0.0)
        data[f'{face}_stirrup_db_mm'] = min([float(s['stirrup_db_mm']) for s in active], default=0.0)
        data[f'{face}_n_bars_top'] = sum(float(s['n_bars_top']) for s in active)
        data[f'{face}_n_bars_bot'] = sum(float(s['n_bars_bot']) for s in active)
        data[f'{face}_As_top_mm2'] = sum(float(s['As_top_mm2']) for s in active)
        data[f'{face}_As_bot_mm2'] = sum(float(s['As_bot_mm2']) for s in active)
        data[f'{face}_Mn_pos_kNm'] = sum(float(s['Mn_pos_kNm']) for s in active)
        data[f'{face}_Mn_neg_kNm'] = sum(float(s['Mn_neg_kNm']) for s in active)
        data[f'{face}_Mpr_pos_kNm'] = sum(float(s['Mpr_pos_kNm']) for s in active)
        data[f'{face}_Mpr_neg_kNm'] = sum(float(s['Mpr_neg_kNm']) for s in active)
        data[f'{face}_joint_Mn_kNm'] = sum(float(s['joint_Mn_kNm']) for s in active)
        data[f'{face}_joint_Mpr_kNm'] = sum(float(s['joint_Mpr_kNm']) for s in active)
        # ACI 18.8.4.1: "tensile and compressive beam forces."
        # For two-sided (interior) joint: evaluate both seismic scenarios and take the max.
        #   Scenario A — side1 hogging, side2 sagging: T_neg_s1 + T_pos_s2
        #   Scenario B — side1 sagging, side2 hogging: T_pos_s1 + T_neg_s2
        # For one-sided (exterior) joint: max(T_top, T_bot) — the compression from the same
        #   beam acts in the opposite direction and does not add to joint shear.
        if n_active == 2:
            s1, s2 = active[0], active[1]
            Tn1 = float(s1['Tpr_neg_kN'])   # T_top (hogging) of side1
            Tp1 = float(s1['Tpr_pos_kN'])   # T_bot (sagging) of side1
            Tn2 = float(s2['Tpr_neg_kN'])   # T_top (hogging) of side2
            Tp2 = float(s2['Tpr_pos_kN'])   # T_bot (sagging) of side2
            scen_a = Tn1 + Tp2              # s1 hogs, s2 sags
            scen_b = Tp1 + Tn2              # s1 sags, s2 hogs
        elif n_active == 1:
            Tn1 = float(active[0]['Tpr_neg_kN'])
            Tp1 = float(active[0]['Tpr_pos_kN'])
            scen_a = scen_b = max(Tn1, Tp1)
        else:
            scen_a = scen_b = 0.0
        data[f'{face}_joint_Tpr_kN']        = max(scen_a, scen_b)
        data[f'{face}_joint_Tpr_scen_a_kN'] = scen_a
        data[f'{face}_joint_Tpr_scen_b_kN'] = scen_b
        data[f'{face}_x_mm'] = min([float(s['x_mm']) for s in active if float(s['x_mm']) > 0.0], default=0.0)
        # ext only matters for single-sided framing; otherwise not governing for current simplified logic
        data[f'{face}_ext_mm'] = float(active[0]['ext_mm']) if n_active == 1 else 0.0
        data[f'{face}_ln_m'] = max([float(s['ln_m']) for s in active], default=0.0)
        data[f'{face}_wu_kN_per_m'] = max([float(s['wu_kN_per_m']) for s in active], default=0.0)
    return data


def _resolve_other_col_value(raw: object, current_mnc: float) -> float:
    text = str(raw).strip().lower()
    if text in {'same', 'self'}:
        return current_mnc
    if text in {'none', '', '0'}:
        return 0.0
    return float(text)


def probable_shear_for_column(row: Dict[str, object], beam_actions: Dict[str, float], col_x: Dict[str, float], col_y: Dict[str, float]) -> Dict[str, float]:
    lu_m = float(row['lu_mm']) / 1000.0
    out: Dict[str, float] = {'lu_m': lu_m}
    for axis, col_data in [('x', col_x), ('y', col_y)]:
        top_raw = col_data['Mpr_pos_kNm']
        bot_raw = col_data['Mpr_neg_kNm']
        top_lim = float(beam_actions.get(f'beam_top_{axis}_joint_Mpr_kNm', 0.0))
        bot_lim = float(beam_actions.get(f'beam_bottom_{axis}_joint_Mpr_kNm', 0.0))
        top_eff = min(top_raw, top_lim) if top_lim > 0.0 else top_raw
        bot_eff = min(bot_raw, bot_lim) if bot_lim > 0.0 else bot_raw
        Ve_eq = (top_eff + bot_eff) / max(lu_m, 1e-9)
        Vu_analysis = abs(float(row['Vux_kN'] if axis == 'x' else row['Vuy_kN']))
        Ve_design = max(Ve_eq, Vu_analysis)
        out[f'col_Mpr_top_{axis}_calc_kNm'] = top_raw
        out[f'col_Mpr_bot_{axis}_calc_kNm'] = bot_raw
        out[f'beam_joint_top_{axis}_limit_kNm'] = top_lim
        out[f'beam_joint_bot_{axis}_limit_kNm'] = bot_lim
        out[f'col_Mpr_top_{axis}_eff_kNm'] = top_eff
        out[f'col_Mpr_bot_{axis}_eff_kNm'] = bot_eff
        out[f'Ve_col_{axis}_kN'] = Ve_eq
        out[f'Ve_design_{axis}_kN'] = Ve_design
    return out


def _joint_depth_and_width(row: Dict[str, object], axis: str, beam_bw_mm: float, x_mm: float) -> Dict[str, float]:
    if axis == 'x':
        h_joint = float(row['b_mm'])
    else:
        h_joint = float(row['h_mm'])
    eff_width = min(beam_bw_mm + h_joint, beam_bw_mm + 2.0 * max(x_mm, 0.0))
    eff_width = max(eff_width, beam_bw_mm)
    Aj = h_joint * eff_width
    return {'h_joint_mm': h_joint, 'eff_width_mm': eff_width, 'Aj_mm2': Aj}


def _beam_face_width(row: Dict[str, object], axis: str) -> float:
    return float(row['b_mm'] if axis == 'x' else row['h_mm'])


def _joint_confined(row: Dict[str, object], beam_actions: Dict[str, float], joint: str, axis: str) -> Dict[str, float | bool]:
    other = 'y' if axis == 'x' else 'x'
    trans_face = f'beam_{joint}_{other}'
    main_face = f'beam_{joint}_{axis}'
    face_width = _beam_face_width(row, other)
    deeper = float(beam_actions.get(f'{main_face}_h_mm', 0.0))
    active_sides = []
    for side in ['side1', 'side2']:
        p = f'{trans_face}_{side}'
        if bool(beam_actions.get(f'{p}_active', False)):
            active_sides.append({
                'bw': float(beam_actions.get(f'{p}_bw_mm', 0.0)),
                'h': float(beam_actions.get(f'{p}_h_mm', 0.0)),
                'ext': float(beam_actions.get(f'{p}_ext_mm', 0.0)),
                'n_top': float(beam_actions.get(f'{p}_n_bars_top', 0.0)),
                'n_bot': float(beam_actions.get(f'{p}_n_bars_bot', 0.0)),
                'stirrup_db': float(beam_actions.get(f'{p}_stirrup_db_mm', 0.0)),
            })
    count = len(active_sides)
    cond_a = all(s['bw'] >= 0.75 * face_width for s in active_sides) if count > 0 else False
    cond_b = all((s['bw'] * s['h']) >= 0.75 * face_width * deeper for s in active_sides) if count > 0 and deeper > 0 else False
    if count >= 2:
        cond_c = True
    elif count == 1:
        cond_c = active_sides[0]['ext'] >= active_sides[0]['h']
    else:
        cond_c = False
    cond_d = all(s['n_top'] >= 2 and s['n_bot'] >= 2 and s['stirrup_db'] >= 10.0 for s in active_sides) if count > 0 else False
    confined = count > 0 and cond_a and cond_b and cond_c and cond_d
    return {
        'count': count,
        'cond_a': cond_a, 'cond_b': cond_b, 'cond_c': cond_c, 'cond_d': cond_d,
        'confined': confined,
        'face_width_mm': face_width, 'deeper_beam_h_mm': deeper,
    }


def _joint_coefficient(column_continuous: bool, beam_continuous: bool, confined: bool) -> float:
    if column_continuous:
        if beam_continuous:
            return 1.7 if confined else 1.3
        return 1.3 if confined else 1.0
    if beam_continuous:
        return 1.3 if confined else 1.0
    return 1.0 if confined else 0.7


def joint_capacity_static(row: Dict[str, object], beam_actions: Dict[str, float]) -> Dict[str, float | bool]:
    fc = float(row['fc_MPa'])
    out: Dict[str, float | bool] = {'phi_joint': ACI_PHI_JOINT}
    for joint in ['top', 'bottom']:
        column_cont = bool(row['joint_top'] if joint == 'top' else row['joint_bottom'])
        for axis in ['x', 'y']:
            beam_face = f'beam_{joint}_{axis}'
            beam_count = float(beam_actions.get(f'{beam_face}_n_active', 0.0))
            if beam_count <= 0.0:
                out[f'joint_{joint}_{axis}_active'] = False
                continue
            beam_cont = bool(beam_actions.get(f'{beam_face}_continuous', False))
            bw = float(beam_actions.get(f'{beam_face}_bw_mm', 0.0))
            x_mm = float(beam_actions.get(f'{beam_face}_x_mm', 0.0))
            depth = _joint_depth_and_width(row, axis, bw, x_mm)
            conf = _joint_confined(row, beam_actions, joint, axis)
            coeff = _joint_coefficient(column_cont, beam_cont, bool(conf['confined']))
            Vn_kN = coeff * math.sqrt(fc) * float(depth['Aj_mm2']) / 1e3
            out[f'joint_{joint}_{axis}_active'] = True
            out[f'joint_{joint}_{axis}_column_continuous'] = column_cont
            out[f'joint_{joint}_{axis}_beam_continuous'] = beam_cont
            out[f'joint_{joint}_{axis}_confined'] = bool(conf['confined'])
            out[f'joint_{joint}_{axis}_coeff'] = coeff
            out[f'joint_{joint}_{axis}_Aj_mm2'] = float(depth['Aj_mm2'])
            out[f'joint_{joint}_{axis}_eff_width_mm'] = float(depth['eff_width_mm'])
            out[f'joint_{joint}_{axis}_h_joint_mm'] = float(depth['h_joint_mm'])
            out[f'joint_{joint}_{axis}_phiVn_kN'] = ACI_PHI_JOINT * Vn_kN
            out[f'joint_{joint}_{axis}_Vn_kN'] = Vn_kN
            for suffix in ['cond_a', 'cond_b', 'cond_c', 'cond_d', 'count', 'face_width_mm', 'deeper_beam_h_mm']:
                out[f'joint_{joint}_{axis}_{suffix}'] = conf[suffix]
    return out


def joint_shear_demand_case(row: Dict[str, object], beam_actions: Dict[str, float], probable_shear: Dict[str, float]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for joint in ['top', 'bottom']:
        for axis in ['x', 'y']:
            beam_face = f'beam_{joint}_{axis}'
            Tpr = float(beam_actions.get(f'{beam_face}_joint_Tpr_kN', 0.0))
            Ve = abs(float(probable_shear.get(f'Ve_col_{axis}_kN', 0.0)))
            Vu = max(Tpr - Ve, 0.0)
            out[f'joint_{joint}_{axis}_Tpr_kN'] = Tpr
            out[f'joint_{joint}_{axis}_Vu_kN'] = Vu
    return out


def strong_column_weak_beam(row: Dict[str, object], beam_actions: Dict[str, float], col_x: Dict[str, float], col_y: Dict[str, float]) -> Dict[str, float]:
    checks: Dict[str, float] = {}
    for axis, col_data in [('x', col_x), ('y', col_y)]:
        current = float(col_data['Mnc_kNm'])
        for joint in ['top', 'bottom']:
            other = _resolve_other_col_value(row[f'other_col_{joint}_{axis}_Mnc_kNm'], current)
            beams = float(beam_actions.get(f'beam_{joint}_{axis}_joint_Mn_kNm', 0.0))
            sum_mnc = current + other
            required = ACI_SCWB_FACTOR * beams
            ratio = sum_mnc / required if required > 0.0 else float('inf')
            checks[f'scwb_{joint}_{axis}_this_col_mnc_kNm'] = current
            checks[f'scwb_{joint}_{axis}_other_col_mnc_kNm'] = other
            checks[f'scwb_{joint}_{axis}_sum_mnc_kNm'] = sum_mnc
            checks[f'scwb_{joint}_{axis}_sum_mnb_kNm'] = beams
            checks[f'scwb_{joint}_{axis}_required_kNm'] = required
            checks[f'scwb_{joint}_{axis}_ratio'] = ratio
    return checks


def shear_capacity_base(row: Dict[str, object], geom: Dict[str, object]) -> Dict[str, float]:
    fc = float(row['fc_MPa'])
    fy_t = float(row['fy_trans_MPa'])
    s = float(row['tie_spacing_lo_mm'])
    tie_db = float(row['tie_db_mm'])
    b = float(row['b_mm'])
    h = float(row['h_mm'])
    cover = float(row['cover_mm'])
    d_x = h - cover
    d_y = b - cover
    Av_x = max(2.0, float(geom['n_supported_top'])) * steel_area_mm2(tie_db)
    Av_y = max(2.0, float(geom['n_supported_left'])) * steel_area_mm2(tie_db)
    Vc_x_N = ACI_VC_COEFF * math.sqrt(fc) * b * d_x
    Vc_y_N = ACI_VC_COEFF * math.sqrt(fc) * h * d_y
    Vs_x_N = Av_x * fy_t * d_x / max(s, 1e-9)
    Vs_y_N = Av_y * fy_t * d_y / max(s, 1e-9)
    phi = ACI_PHI_SHEAR
    return {
        'd_x_mm': d_x, 'd_y_mm': d_y,
        'Av_x_mm2': Av_x, 'Av_y_mm2': Av_y,
        'Vc_x_kN': Vc_x_N / 1e3, 'Vc_y_kN': Vc_y_N / 1e3,
        'Vs_x_kN': Vs_x_N / 1e3, 'Vs_y_kN': Vs_y_N / 1e3,
        'Vn_x_kN': (Vc_x_N + Vs_x_N) / 1e3, 'Vn_y_kN': (Vc_y_N + Vs_y_N) / 1e3,
        'phiVn_x_kN': phi * (Vc_x_N + Vs_x_N) / 1e3,
        'phiVn_y_kN': phi * (Vc_y_N + Vs_y_N) / 1e3,
        'phi_shear': phi,
    }


def shear_capacity_case(row: Dict[str, object], geom: Dict[str, object], probable_shear: Dict[str, float]) -> Dict[str, float]:
    base = shear_capacity_base(row, geom)
    fc = float(row['fc_MPa'])
    Ag = float(geom['Ag_mm2'])
    Pu_N = float(row['Pu_kN']) * 1e3
    phi = float(base['phi_shear'])

    out = dict(base)
    out['vc_zero_cond_b'] = Pu_N < Ag * fc / ACI_VC_ZERO_AXIAL_DIVISOR
    for axis in ['x', 'y']:
        Ve_eq = abs(float(probable_shear[f'Ve_col_{axis}_kN']))
        Vreq = abs(float(probable_shear[f'Ve_design_{axis}_kN']))
        cond_a = Ve_eq >= 0.5 * Vreq if Vreq > 0 else False
        apply = cond_a and out['vc_zero_cond_b']
        Vc = 0.0 if apply else float(base[f'Vc_{axis}_kN'])
        Vs = float(base[f'Vs_{axis}_kN'])
        out[f'vc_zero_cond_a_{axis}'] = cond_a
        out[f'vc_zero_applies_{axis}'] = apply
        out[f'Vc_eff_{axis}_kN'] = Vc
        out[f'Vn_eff_{axis}_kN'] = Vc + Vs
        out[f'phiVn_eff_{axis}_kN'] = phi * (Vc + Vs)
    return out
