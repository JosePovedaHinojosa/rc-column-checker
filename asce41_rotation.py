from __future__ import annotations

from typing import Dict


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _limit_rho_t(raw_rho_t: float, adequately_anchored: bool) -> tuple[float, list[str]]:
    warnings: list[str] = []
    rho_t = raw_rho_t
    if raw_rho_t < 0.0005:
        warnings.append('ASCE 41 Table 10-8 note: equations not valid for rho_t < 0.0005; value clipped to 0.0005 for screening.')
        rho_t = 0.0005
    cap = 0.0175 if adequately_anchored else 0.0075
    if raw_rho_t > cap:
        warnings.append(f'ASCE 41 Table 10-8 note: rho_t capped at {cap:.4f}.')
        rho_t = cap
    return rho_t, warnings


def _unspliced_params(axial_ratio: float, rho_t: float, fc_mpa: float, fyte_mpa: float, v_ratio: float) -> tuple[float, float, float]:
    r_eff = min(axial_ratio, 0.5)
    a = max(0.042 - 0.043 * r_eff + 0.63 * rho_t - 0.023 * v_ratio, 0.0)
    denom = 5.0 + (r_eff / 0.8) * (fc_mpa / max(rho_t * fyte_mpa, 1e-9))
    b = max(0.5 / denom - 0.01, a)
    c = max(0.24 - 0.4 * max(axial_ratio, 0.1), 0.0)

    if axial_ratio > 0.5:
        factor = max(0.0, min(1.0, (0.7 - axial_ratio) / 0.2))
        a = max(a * factor, 0.0)
        b = max(b * factor, a)
    return a, b, c


def _spliced_params(axial_ratio: float, rho_t: float, rho_l: float, fy_mpa: float, fye_mpa: float, two_tie_groups: bool) -> tuple[float, float, float]:
    if not two_tie_groups:
        a = 0.0
    else:
        a = (rho_t * fye_mpa) / max(8.0 * rho_l * fy_mpa, 1e-9)
        a = _clip(a, 0.0, 0.025)
    b = 0.012 - 0.085 * axial_ratio + 12.0 * rho_t
    b = _clip(max(b, a), 0.0, 0.06)
    c = _clip(0.15 + 36.0 * rho_t, 0.0, 0.4)
    return a, b, c


def _direction_params(
    row: Dict[str, object],
    geom: Dict[str, object],
    direction_label: str,
    rot_demand: float,
    v_ratio: float,
) -> Dict[str, object]:
    Pu_kN = abs(float(row['Pu_kN']))
    Ag = float(geom['Ag_mm2'])
    fc = float(row['fc_MPa'])
    fy = float(row['fy_long_MPa'])
    fyt = float(row['fy_trans_MPa'])

    rho_t_raw = min(float(geom['rho_s_x']), float(geom['rho_s_y']))
    anchored_default = bool(float(row['hook_angle_deg']) >= 135.0 and bool(row.get('crosstie_alt_anchorage', False)))
    adequately_anchored = bool(row.get('asce_ties_adequately_anchored', anchored_default))
    rho_t, warnings = _limit_rho_t(rho_t_raw, adequately_anchored)
    rho_l = max(float(geom['rho_long']), 1e-9)

    axial_ratio = max(Pu_kN * 1e3 / max(Ag * fc, 1e-9), 0.1)
    v_ratio_used = max(float(v_ratio), 0.2)
    fye = float(row.get('asce_fye_factor', 1.25)) * fy
    fyte = float(row.get('asce_fyte_factor', 1.25)) * fyt
    splice_controlled = bool(row.get('asce_splice_controlled', False))
    two_tie_groups = bool(row.get('asce_splice_two_tie_groups', True))

    a_un, b_un, c_un = _unspliced_params(axial_ratio, rho_t, fc, fyte, v_ratio_used)
    a = a_un
    b = b_un
    c = c_un

    if splice_controlled:
        a_sp, b_sp, c_sp = _spliced_params(axial_ratio, rho_t, rho_l, fy, fye, two_tie_groups)
        a = min(a_sp, a_un)
        b = min(max(b_sp, a), b_un)
        c = min(c_sp, c_un)

    theta_io = 0.0 if splice_controlled else min(0.15 * a, 0.005)
    theta_ls = 0.5 * b
    theta_cp = 0.7 * b

    damage_state = str(row.get('damage_state', 'CP')).upper()
    theta_cap = {'IO': theta_io, 'LS': theta_ls, 'CP': theta_cp}.get(damage_state, theta_cp)
    ratio = abs(float(rot_demand)) / max(theta_cap, 1e-12)

    return {
        'direction': direction_label,
        'splice_controlled': splice_controlled,
        'adequately_anchored': adequately_anchored,
        'rho_t_raw': rho_t_raw,
        'rho_t_used': rho_t,
        'rho_l': rho_l,
        'axial_ratio': axial_ratio,
        'vye_over_vcoloe': v_ratio_used,
        'fye_mpa': fye,
        'fyte_mpa': fyte,
        'a': a,
        'b': b,
        'c': c,
        'theta_io': theta_io,
        'theta_ls': theta_ls,
        'theta_cp': theta_cp,
        'damage_state': damage_state,
        'theta_cap': theta_cap,
        'rot_demand': abs(float(rot_demand)),
        'ratio': ratio,
        'warnings': warnings,
    }


def compute_asce41_rotation(row: Dict[str, object], geom: Dict[str, object], v_ratio_x: float, v_ratio_y: float) -> Dict[str, object]:
    """
    ASCE 41 Table 10-8 screening implementation for rectangular RC columns with
    seismic hoops. Rotation demands are taken from RotX and RotY.
    The Vye/VColOE term is automated from the governing shear-ratio analysis per
    direction, but not less than 0.2.
    """
    rot_x = abs(float(row.get('RotX', 0.0)))
    rot_y = abs(float(row.get('RotY', row.get('RotZ', 0.0))))

    x = _direction_params(row, geom, 'X', rot_x, v_ratio_x)
    y = _direction_params(row, geom, 'Y', rot_y, v_ratio_y)
    warnings = list(dict.fromkeys([*x['warnings'], *y['warnings']]))

    return {
        'damage_state': x['damage_state'],
        'x': x,
        'y': y,
        'RotX': rot_x,
        'RotY': rot_y,
        'ratio_x': x['ratio'],
        'ratio_y': y['ratio'],
        'theta_cap_x': x['theta_cap'],
        'theta_cap_y': y['theta_cap'],
        'warnings': warnings,
    }
