from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from aci_longitudinal_checks import longitudinal_checks
from aci_transverse_checks import transverse_checks
from asce41_rotation import compute_asce41_rotation
from constants import (
    ACI_JOINT_DEPTH_DB_G420, ACI_JOINT_DEPTH_DB_G550, ACI_OMF_SHEAR_LU_C1_FACTOR,
    ACI_PN_MAX_SPIRAL, ACI_PN_MAX_TIED,
)
from frame_types import GRAVITY, IMF, OMF, SMF, frame_class
from geometry_utils import compute_geometry
from io_utils import read_inputs, write_project_csvs
from pdf_report import build_pdf_report
from pdf_report_detailed import build_detailed_pdf_report
from pm_diagram import export_pm_diagram, export_section_sketch
from reporting import build_latex_report, slugify, write_csv
from section_capacity import (
    compute_beam_actions,
    column_strengths_at_Pu,
    expected_strength_row,
    interaction_points,
    is_expected_basis,
    joint_capacity_static,
    joint_shear_demand_case,
    probable_shear_for_column,
    pure_axial_capacity,
    pure_flexure_capacity,
    shear_capacity_base,
    shear_capacity_case,
    strong_column_weak_beam,
)


def overall_status(check_rows):
    statuses = {r['status'] for r in check_rows}
    if 'NG' in statuses:
        return 'NG'
    if 'WARNING' in statuses:
        return 'WARNING'
    return 'OK'


def parse_report_columns(value: str | None) -> set[str]:
    if not value:
        return set()
    return {v.strip() for v in value.split(',') if v.strip()}


def add_ratio_check(checks, row, name, provided, required, code_ref, message):
    checks.append({
        'column_id': row['column_id'], 'load_case': row.get('load_case', 'U1'), 'check_name': name,
        'status': 'OK' if provided <= required else 'NG', 'provided': round(provided, 3), 'required': f'<= {required:.3f}',
        'code_ref': code_ref, 'message': message,
    })


def add_min_check(checks, row, name, provided, required, code_ref, message):
    checks.append({
        'column_id': row['column_id'], 'load_case': row.get('load_case', 'U1'), 'check_name': name,
        'status': 'OK' if provided >= required else 'NG', 'provided': round(provided, 3), 'required': f'>= {required:.3f}',
        'code_ref': code_ref, 'message': message,
    })


def add_info_check(checks, row, name, value, code_ref, message):
    checks.append({
        'column_id': row['column_id'], 'load_case': row.get('load_case', 'ALL'), 'check_name': name,
        'status': 'INFO', 'provided': value, 'required': '-', 'code_ref': code_ref, 'message': message,
    })


def add_warning_flag(checks, row, name, flag, code_ref, message_if_true, message_if_false='Not triggered.'):
    checks.append({
        'column_id': row['column_id'], 'load_case': row.get('load_case', 'U1'), 'check_name': name,
        'status': 'WARNING' if flag else 'OK', 'provided': bool(flag), 'required': 'False', 'code_ref': code_ref,
        'message': message_if_true if flag else message_if_false,
    })


def representative_row_for_pm(rows):
    return max(rows, key=lambda r: abs(float(r['Pu_kN'])))


def _apply_column_section(target_row, section_row):
    out = dict(target_row)
    for key, value in section_row.items():
        if key in {'column_section_id', '_row_number'}:
            continue
        out[key] = value
    return out


def resolve_other_column_mnc(section_ref, run_row, axis, column_sections_map, cache):
    text = str(section_ref).strip()
    low = text.lower()
    if low in {'same', 'self', ''}:
        return 'same'
    if low in {'none', '0'}:
        return 'none'
    if text not in column_sections_map:
        raise ValueError(f"column_id '{run_row['column_id']}' references unknown adjacent column section '{text}'")
    key = (text, float(run_row['Pu_kN']))
    if key not in cache:
        other_row = _apply_column_section(run_row, column_sections_map[text])
        geom = compute_geometry(other_row)
        cache[key] = {
            'x': column_strengths_at_Pu(other_row, geom, axis='x')['Mnc_kNm'],
            'y': column_strengths_at_Pu(other_row, geom, axis='y')['Mnc_kNm'],
        }
    return cache[key][axis]


def main():
    parser = argparse.ArgumentParser(description='ACI RC column checker v18 with cleaned inputs, optional report sections, and robust empty-table rendering.')
    parser.add_argument('--project', default='', help='Path to a project .json file (GUI save format); replaces the four CSV arguments')
    parser.add_argument('--column-sections', default='', help='Path to column-sections CSV')
    parser.add_argument('--beam-sections', default='', help='Path to beam-sections CSV')
    parser.add_argument('--column-beam', default='', help='Path to column-beam-prop CSV')
    parser.add_argument('--loads', default='', help='Path to loads CSV')
    parser.add_argument('--outdir', default='outputs', help='Output directory')
    parser.add_argument('--skip-pm', action='store_true', help='Skip P-M plot export')
    parser.add_argument('--report-columns', default='', help='Comma-separated column_id values to generate summary reports')
    parser.add_argument('--report-all', action='store_true', help='Generate summary reports for all columns')
    parser.add_argument('--detailed-report-columns', default='', help='Comma-separated column_id values to generate detailed step-by-step reports')
    parser.add_argument('--detailed-report-all', action='store_true', help='Generate detailed step-by-step reports for all columns')
    parser.add_argument('--pry-name', default='', help='Project name for report header')
    parser.add_argument('--hide-rotation-table', action='store_true', help='Hide the ASCE 41 rotation table in LaTeX reports')
    parser.add_argument('--hide-beam-table', action='store_true', help='Hide the connected beam capacities table in LaTeX reports')
    parser.add_argument('--hide-joint-table', action='store_true', help='Hide the joint capacity table in LaTeX reports')
    args = parser.parse_args()

    if args.project:
        import json
        with open(args.project, encoding='utf-8') as f:
            data = json.load(f)
        if data.get('version') not in (1,):
            parser.error(f"Unsupported project file version in '{args.project}' (expected 1).")
        csv_paths = write_project_csvs(data, Path(args.outdir) / '_project_csvs')
        args.column_sections = str(csv_paths['column_sections'])
        args.beam_sections = str(csv_paths['beam_sections'])
        args.column_beam = str(csv_paths['column_beam'])
        args.loads = str(csv_paths['loads'])
        if not args.pry_name:
            args.pry_name = str(data.get('project_name', ''))
    elif not all([args.column_sections, args.beam_sections, args.column_beam, args.loads]):
        parser.error('Provide either --project <file.json> or all four CSV arguments '
                     '(--column-sections, --beam-sections, --column-beam, --loads).')

    columns_map, rows, column_sections_map, beam_sections_map, column_beam_map = read_inputs(args.column_sections, args.beam_sections, args.column_beam, args.loads)
    grouped = defaultdict(list)
    for row in rows:
        grouped[str(row['column_id'])].append(row)

    outdir = Path(args.outdir)
    pm_dir = outdir / 'pm_diagrams'
    report_dir = outdir / 'latex_reports'
    requested_reports  = set(grouped.keys()) if args.report_all  else parse_report_columns(args.report_columns)
    requested_detailed = set(grouped.keys()) if args.detailed_report_all else parse_report_columns(args.detailed_report_columns)
    other_col_cache = {}

    results_rows = []
    check_rows = []
    report_contexts = []

    for column_id, col_rows in grouped.items():
        prop_row = dict(columns_map[column_id])
        geom = compute_geometry(prop_row)
        beam_actions = compute_beam_actions(prop_row)

        # Strength basis: demands from nonlinear analysis are checked against
        # ASCE 41 expected-strength capacities (fce, fye) with phi = 1.0;
        # linear (design) demands keep nominal materials and ACI phi factors.
        col_expected = is_expected_basis(prop_row)
        cap_prop_row = expected_strength_row(prop_row) if col_expected else prop_row

        axial = pure_axial_capacity(cap_prop_row, geom)
        shear_base = shear_capacity_base(cap_prop_row, geom)
        flexure0_x = pure_flexure_capacity(cap_prop_row, geom, axis='x')
        flexure0_y = pure_flexure_capacity(cap_prop_row, geom, axis='y')
        joint_static = joint_capacity_static(cap_prop_row, beam_actions)
        if col_expected:
            axial['phiPn0_kN'] = axial['Pn0_kN']
            axial['phi_axial'] = 1.0
            for ax in ['x', 'y']:
                shear_base[f'phiVn_{ax}_kN'] = shear_base[f'Vn_{ax}_kN']
            shear_base['phi_shear'] = 1.0
            for fx in [flexure0_x, flexure0_y]:
                fx['phiMn_pos_kNm'] = fx['Mn_pos_kNm']
                fx['phiMn_neg_kNm'] = fx['Mn_neg_kNm']
                fx['phiMn_min_kNm'] = fx['Mn_min_kNm']
            joint_static['phi_joint'] = 1.0
            joint_static['joint_phi_ref'] = 'ASCE 41 expected strength (phi = 1.0)'
            for joint in ['top', 'bottom']:
                for axis in ['x', 'y']:
                    if joint_static.get(f'joint_{joint}_{axis}_active', False):
                        joint_static[f'joint_{joint}_{axis}_phiVn_kN'] = joint_static[f'joint_{joint}_{axis}_Vn_kN']

        long_checks, _ = longitudinal_checks({**prop_row, 'load_case': 'ALL'}, geom)
        pu_values = [float(r['Pu_kN']) for r in col_rows]
        max_comp_pu = max([v for v in pu_values if v > 0.0], default=0.0)
        ref_pu_static = max_comp_pu if max_comp_pu > 0.0 else max(abs(v) for v in pu_values)
        tr_checks, tr_meta = transverse_checks({**prop_row, 'load_case': 'ALL', 'Pu_kN': ref_pu_static}, geom)
        static_checks = long_checks + tr_checks

        info_row = {**prop_row, 'load_case': 'ALL'}
        basis_txt = ('nonlinear — capacities use ASCE 41 expected strengths '
                     f"(fce = {float(prop_row.get('asce_fce_factor', 1.5))}·f'c, fye = {float(prop_row.get('asce_fye_factor', 1.25))}·fy, phi = 1.0)"
                     ) if col_expected else 'linear — capacities use nominal materials and ACI phi factors'
        add_info_check(static_checks, info_row, 'strength_basis', str(prop_row.get('analysis_type', 'linear')), 'ASCE 41 10.2.2 / ACI Ch. 21', f'Strength basis: {basis_txt}.')
        add_info_check(static_checks, info_row, 'capacity_Pn0_kN', round(axial['Pn0_kN'], 1), 'ACI 22 / simplified', 'Concentric axial capacity Pn0 (strength-basis materials).')
        add_info_check(static_checks, info_row, 'capacity_phiPn0_kN', round(axial['phiPn0_kN'], 1), 'ACI 22 / simplified', 'Design axial capacity phi*Pn0 (phi = 1.0 under expected basis).')
        add_info_check(static_checks, info_row, 'capacity_phiVn_x_base_kN', round(shear_base['phiVn_x_kN'], 1), 'ACI 22.5 / simplified', 'Base design shear capacity in x with Vc + Vs.')
        add_info_check(static_checks, info_row, 'capacity_phiVn_y_base_kN', round(shear_base['phiVn_y_kN'], 1), 'ACI 22.5 / simplified', 'Base design shear capacity in y with Vc + Vs.')
        add_info_check(static_checks, info_row, 'capacity_Mn0_x_kNm', round(flexure0_x['Mn_min_kNm'], 1), 'Strain compatibility', 'Pure flexure nominal capacity at Pu = 0 in x; simplified rectangular section.')
        add_info_check(static_checks, info_row, 'capacity_Mpr0_x_kNm', round(flexure0_x['Mpr_min_kNm'], 1), 'Strain compatibility', 'Pure flexure probable capacity at Pu = 0 in x; simplified rectangular section.')
        add_info_check(static_checks, info_row, 'capacity_Mn0_y_kNm', round(flexure0_y['Mn_min_kNm'], 1), 'Strain compatibility', 'Pure flexure nominal capacity at Pu = 0 in y; simplified rectangular section.')
        add_info_check(static_checks, info_row, 'capacity_Mpr0_y_kNm', round(flexure0_y['Mpr_min_kNm'], 1), 'Strain compatibility', 'Pure flexure probable capacity at Pu = 0 in y; simplified rectangular section.')

        for face in ['beam_top_x', 'beam_bottom_x', 'beam_top_y', 'beam_bottom_y']:
            add_info_check(static_checks, info_row, f'{face}_n_active', int(beam_actions[f'{face}_n_active']), 'Beam assembly', 'Number of connected beams explicitly modeled on this face.')
            add_info_check(static_checks, info_row, f'{face}_joint_Mn_kNm', round(beam_actions[f'{face}_joint_Mn_kNm'], 1), 'Simplified beam flexure', 'Sum of connected beam nominal joint flexural strengths on this face.')
            add_info_check(static_checks, info_row, f'{face}_joint_Mpr_kNm', round(beam_actions[f'{face}_joint_Mpr_kNm'], 1), 'Simplified beam flexure', 'Sum of connected beam probable joint flexural strengths on this face.')
            for side in ['side1', 'side2']:
                prefix = f'{face}_{side}'
                if not beam_actions.get(f'{prefix}_active', False):
                    continue
                add_info_check(static_checks, info_row, f'{prefix}_As_top_mm2', round(beam_actions[f'{prefix}_As_top_mm2'], 1), 'Beam input auto-calc', 'Connected beam top steel area computed from n bars and diameter.')
                add_info_check(static_checks, info_row, f'{prefix}_As_bot_mm2', round(beam_actions[f'{prefix}_As_bot_mm2'], 1), 'Beam input auto-calc', 'Connected beam bottom steel area computed from n bars and diameter.')
                add_info_check(static_checks, info_row, f'{prefix}_joint_Mn_kNm', round(beam_actions[f'{prefix}_joint_Mn_kNm'], 1), 'Simplified beam flexure', 'Connected beam nominal joint flexural strength for this explicit beam.')
                add_info_check(static_checks, info_row, f'{prefix}_joint_Mpr_kNm', round(beam_actions[f'{prefix}_joint_Mpr_kNm'], 1), 'Simplified beam flexure', 'Connected beam probable joint flexural strength for this explicit beam.')

        col_fclass = frame_class(prop_row)
        for joint in ['top', 'bottom']:
            for axis in ['x', 'y']:
                if not joint_static.get(f'joint_{joint}_{axis}_active', False):
                    continue
                add_info_check(static_checks, info_row, f'joint_{joint}_{axis}_Aj_mm2', round(joint_static[f'joint_{joint}_{axis}_Aj_mm2'], 1), 'ACI R15.5.2.2', 'Effective joint area Aj.')
                add_info_check(static_checks, info_row, f'joint_{joint}_{axis}_phiVn_kN', round(joint_static[f'joint_{joint}_{axis}_phiVn_kN'], 1), str(joint_static.get('joint_table_ref', 'ACI Table 18.8.4.3')), f"Design joint shear strength (phi = {joint_static.get('phi_joint', 0.85)}).")
                if col_fclass == SMF:
                    db_beam_max = 0.0
                    for side in ['side1', 'side2']:
                        prefix = f'beam_{joint}_{axis}_{side}'
                        if not beam_actions.get(f'{prefix}_active', False):
                            continue
                        db_beam_max = max(db_beam_max, float(beam_actions.get(f'{prefix}_db_top_mm', 0.0)), float(beam_actions.get(f'{prefix}_db_bot_mm', 0.0)))
                    if db_beam_max > 0.0:
                        db_factor = ACI_JOINT_DEPTH_DB_G420 if float(prop_row['fy_long_MPa']) <= 420.0 else ACI_JOINT_DEPTH_DB_G550
                        h_joint = float(joint_static[f'joint_{joint}_{axis}_h_joint_mm'])
                        add_min_check(static_checks, info_row, f'joint_{joint}_{axis}_depth_20db', h_joint, db_factor * db_beam_max, 'ACI 18.8.2.3', f'Joint depth parallel to beam bars vs {db_factor:.0f}db of largest beam bar (db = {db_beam_max:.0f} mm) passing through the joint.')
                # 15.5.2.5(a)-(d) classify the joint as confined/unconfined for the
                # Vn coefficient table; failing them is not a code violation, so
                # they are reported as INFO, not NG.
                add_info_check(static_checks, info_row, f'joint_{joint}_{axis}_15.5.2.5_a', 'Y' if joint_static[f'joint_{joint}_{axis}_cond_a'] else 'N', 'ACI 15.5.2.5(a)', 'Transverse beam width coverage criterion (joint confinement classification).')
                add_info_check(static_checks, info_row, f'joint_{joint}_{axis}_15.5.2.5_b', 'Y' if joint_static[f'joint_{joint}_{axis}_cond_b'] else 'N', 'ACI 15.5.2.5(b)', 'Transverse beam area coverage criterion (joint confinement classification).')
                add_info_check(static_checks, info_row, f'joint_{joint}_{axis}_15.5.2.5_c', 'Y' if joint_static[f'joint_{joint}_{axis}_cond_c'] else 'N', 'ACI 15.5.2.5(c)', 'Transverse beam extension beyond joint face (joint confinement classification).')
                add_info_check(static_checks, info_row, f'joint_{joint}_{axis}_15.5.2.5_d', 'Y' if joint_static[f'joint_{joint}_{axis}_cond_d'] else 'N', 'ACI 15.5.2.5(d)', 'Transverse beam longitudinal bars and stirrups (joint confinement classification).')

        check_rows.extend(static_checks)

        rep_row = representative_row_for_pm(col_rows)
        # P-M diagrams use the same strength basis as the checks so demand points
        # overlay the curves the ratios were computed against.
        pm_row = dict(cap_prop_row)
        pm_row.update(rep_row)
        fy_rep = float(pm_row['fy_long_MPa'])
        col_x_pm = {
            'Mn_points_pos': interaction_points(pm_row, geom, axis='x', fy_long_mpa=fy_rep, compression_face='top'),
            'Mn_points_neg': interaction_points(pm_row, geom, axis='x', fy_long_mpa=fy_rep, compression_face='bottom'),
            'Design_points_pos': interaction_points(pm_row, geom, axis='x', fy_long_mpa=fy_rep, compression_face='top'),
            'Design_points_neg': interaction_points(pm_row, geom, axis='x', fy_long_mpa=fy_rep, compression_face='bottom'),
            'Mpr_points_pos': interaction_points(pm_row, geom, axis='x', fy_long_mpa=1.25 * fy_rep, compression_face='top'),
            'Mpr_points_neg': interaction_points(pm_row, geom, axis='x', fy_long_mpa=1.25 * fy_rep, compression_face='bottom'),
        }
        col_y_pm = {
            'Mn_points_pos': interaction_points(pm_row, geom, axis='y', fy_long_mpa=fy_rep, compression_face='left'),
            'Mn_points_neg': interaction_points(pm_row, geom, axis='y', fy_long_mpa=fy_rep, compression_face='right'),
            'Design_points_pos': interaction_points(pm_row, geom, axis='y', fy_long_mpa=fy_rep, compression_face='left'),
            'Design_points_neg': interaction_points(pm_row, geom, axis='y', fy_long_mpa=fy_rep, compression_face='right'),
            'Mpr_points_pos': interaction_points(pm_row, geom, axis='y', fy_long_mpa=1.25 * fy_rep, compression_face='left'),
            'Mpr_points_neg': interaction_points(pm_row, geom, axis='y', fy_long_mpa=1.25 * fy_rep, compression_face='right'),
        }

        pm_svg_x = pm_pdf_x = pm_png_x = ''
        pm_svg_y = pm_pdf_y = pm_png_y = ''
        section_png_path = ''
        if requested_reports and column_id in requested_reports:
            section_png_path = str(export_section_sketch(column_id, prop_row, outdir))
            if not args.skip_pm:
                pm_svg_x, pm_pdf_x, pm_png_x = export_pm_diagram(column_id, col_x_pm, col_rows, pm_dir, axis='x')
                pm_svg_y, pm_pdf_y, pm_png_y = export_pm_diagram(column_id, col_y_pm, col_rows, pm_dir, axis='y')

        report_case_contexts = []
        for row in col_rows:
            run_row = dict(prop_row)
            run_row.update(row)
            all_checks = []
            fclass = frame_class(run_row)

            # Capacity structs use the strength-basis materials; demand-side
            # structs (Mpr hinging, SCWB, joint tension) stay on nominal values.
            cap_run_row = {**cap_prop_row, **row} if col_expected else run_row
            col_x = column_strengths_at_Pu(cap_run_row, geom, axis='x')
            col_y = column_strengths_at_Pu(cap_run_row, geom, axis='y')
            if col_expected:
                for c in (col_x, col_y):
                    c['phiMn_kNm'] = c['Mnc_kNm']
                    c['phiMn_pos_kNm'] = c['Mn_pos_kNm']
                    c['phiMn_neg_kNm'] = c['Mn_neg_kNm']
                    c['phi_pos'] = c['phi_neg'] = 1.0
                col_x_dem = column_strengths_at_Pu(run_row, geom, axis='x')
                col_y_dem = column_strengths_at_Pu(run_row, geom, axis='y')
            else:
                col_x_dem, col_y_dem = col_x, col_y
            prob_shear = probable_shear_for_column(run_row, beam_actions, col_x_dem, col_y_dem)
            shear_case = shear_capacity_case(cap_run_row, geom, prob_shear)
            if col_expected:
                for ax in ['x', 'y']:
                    shear_case[f'phiVn_eff_{ax}_kN'] = shear_case[f'Vn_eff_{ax}_kN']
                shear_case['phi_shear'] = 1.0
            basis_tag = ' [expected]' if col_expected else ''
            run_row['other_col_top_x_Mnc_kNm'] = resolve_other_column_mnc(run_row.get('top_other_column_section_id', 'same'), run_row, 'x', column_sections_map, other_col_cache)
            run_row['other_col_top_y_Mnc_kNm'] = resolve_other_column_mnc(run_row.get('top_other_column_section_id', 'same'), run_row, 'y', column_sections_map, other_col_cache)
            run_row['other_col_bottom_x_Mnc_kNm'] = resolve_other_column_mnc(run_row.get('bottom_other_column_section_id', 'same'), run_row, 'x', column_sections_map, other_col_cache)
            run_row['other_col_bottom_y_Mnc_kNm'] = resolve_other_column_mnc(run_row.get('bottom_other_column_section_id', 'same'), run_row, 'y', column_sections_map, other_col_cache)
            scwb = strong_column_weak_beam(run_row, beam_actions, col_x_dem, col_y_dem)
            joint_case = joint_shear_demand_case(run_row, beam_actions, prob_shear)

            demand_ratio_pm_x = abs(float(run_row['Mux_kNm'])) / max(col_x['phiMn_kNm'], 1e-9)
            demand_ratio_pm_y = abs(float(run_row['Muy_kNm'])) / max(col_y['phiMn_kNm'], 1e-9)
            shear_ratio_x = abs(float(run_row['Vux_kN'])) / max(shear_case['phiVn_eff_x_kN'], 1e-9)
            shear_ratio_y = abs(float(run_row['Vuy_kN'])) / max(shear_case['phiVn_eff_y_kN'], 1e-9)

            # Frame-dependent capacity-design column shear demand:
            #   SMF (18.7.6.1.1) / gravity (18.14.3.2(b)): Ve from column Mpr, capped by
            #   beam joint Mpr, never less than the analysis shear.
            #   IMF (18.4.3.1(a)): Ve from column Mn hinging in reverse curvature.
            #   OMF (18.3.3(a)): same as IMF but required only when lu <= 5*c1.
            lu_mm = float(run_row['lu_mm'])
            Ve_check = {}
            Ve_ref = {}
            omf_shear_applicable = {}
            for axis, c1_mm in [('x', float(run_row['h_mm'])), ('y', float(run_row['b_mm']))]:
                if fclass == IMF:
                    Ve_check[axis] = float(prob_shear[f'Ve_col_Mn_{axis}_kN'])
                    Ve_ref[axis] = 'ACI 18.4.3.1(a)'
                elif fclass == OMF:
                    applicable = lu_mm <= ACI_OMF_SHEAR_LU_C1_FACTOR * c1_mm
                    omf_shear_applicable[axis] = applicable
                    Ve_check[axis] = float(prob_shear[f'Ve_col_Mn_{axis}_kN']) if applicable else 0.0
                    Ve_ref[axis] = 'ACI 18.3.3(a)'
                else:
                    Ve_check[axis] = float(prob_shear[f'Ve_design_{axis}_kN'])
                    Ve_ref[axis] = 'ACI 18.7.6.1' if fclass == SMF else 'ACI 18.14.3.2(b) / 18.7.6.1'
            probable_shear_ratio_x = Ve_check['x'] / max(shear_case['phiVn_eff_x_kN'], 1e-9)
            probable_shear_ratio_y = Ve_check['y'] / max(shear_case['phiVn_eff_y_kN'], 1e-9)
            asce_rot = compute_asce41_rotation(run_row, geom, v_ratio_x=max(shear_ratio_x, 0.2), v_ratio_y=max(shear_ratio_y, 0.2))

            add_ratio_check(all_checks, run_row, 'pm_ratio_x', demand_ratio_pm_x, 1.0, f'Section strength{basis_tag}', 'Bending demand over flexural capacity in x (strength-basis materials).')
            add_ratio_check(all_checks, run_row, 'pm_ratio_y', demand_ratio_pm_y, 1.0, f'Section strength{basis_tag}', 'Bending demand over flexural capacity in y (strength-basis materials).')

            # Axial compression cap: ACI 22.4.2.1 Pn,max for design-basis columns;
            # expected concentric capacity Po,e (phi = 1.0) for nonlinear results.
            Pu_case = float(run_row['Pu_kN'])
            if col_expected:
                axial_cap_kN = float(axial['Pn0_kN'])
                cap_ref = 'ASCE 41 expected Po [expected]'
                cap_msg = 'Compression demand over expected concentric capacity Po,e (phi = 1.0).'
            else:
                pn_factor = ACI_PN_MAX_SPIRAL if bool(run_row.get('spiral_provided', False)) else ACI_PN_MAX_TIED
                axial_cap_kN = pn_factor * float(axial['phiPn0_kN'])
                cap_ref = 'ACI 22.4.2.1'
                cap_msg = f'Compression demand over maximum design axial strength {pn_factor:.2f}*phi*Po.'
            axial_cap_ratio = max(Pu_case, 0.0) / max(axial_cap_kN, 1e-9)
            add_ratio_check(all_checks, run_row, 'axial_cap_ratio', axial_cap_ratio, 1.0, cap_ref, cap_msg)

            add_ratio_check(all_checks, run_row, 'shear_ratio_analysis_x', shear_ratio_x, 1.0, f'Section shear{basis_tag}', 'Analysis shear demand over effective shear capacity in x.')
            add_ratio_check(all_checks, run_row, 'shear_ratio_analysis_y', shear_ratio_y, 1.0, f'Section shear{basis_tag}', 'Analysis shear demand over effective shear capacity in y.')
            shear_msg = {
                SMF: 'Probable (Mpr) design shear over effective design shear strength in {a}.',
                GRAVITY: 'Probable (Mpr) design shear over effective design shear strength in {a}.',
                IMF: 'Nominal-strength (Mn) hinging shear over design shear strength in {a}.',
                OMF: 'Nominal-strength (Mn) hinging shear over design shear strength in {a}.',
            }[fclass]
            for axis, ratio in [('x', probable_shear_ratio_x), ('y', probable_shear_ratio_y)]:
                if fclass == OMF and not omf_shear_applicable.get(axis, False):
                    add_info_check(all_checks, run_row, f'shear_ratio_probable_{axis}', 'n/a', 'ACI 18.3.3', f'18.3.3 column shear provision not required in {axis}: lu = {lu_mm:.0f} mm > 5*c1.')
                    continue
                add_ratio_check(all_checks, run_row, f'shear_ratio_probable_{axis}', ratio, 1.0, Ve_ref[axis] + basis_tag, shear_msg.format(a=axis))
            if fclass in (SMF, GRAVITY):
                add_warning_flag(all_checks, run_row, 'Vc_zero_rule_x', bool(shear_case['vc_zero_applies_x']), 'ACI 18.7.6.2.1', 'Vc set to zero in x within lo for this load case.')
                add_warning_flag(all_checks, run_row, 'Vc_zero_rule_y', bool(shear_case['vc_zero_applies_y']), 'ACI 18.7.6.2.1', 'Vc set to zero in y within lo for this load case.')

            # Net axial tension companions: Vc = 0 for the shear ratios of this
            # case (already applied in shear_case), development/splice demand at
            # fye, and the uplift load path at base stories.
            if bool(shear_case.get('vc_zero_tension', False)):
                add_warning_flag(all_checks, run_row, 'Vc_zero_tension', True, 'ACI 22.5.7', f"Net axial tension (Pu = {Pu_case:.0f} kN): Vc taken as zero for the shear capacity of this load case.")
                splice_note = ('Column is flagged splice-controlled: lap splices under net tension are a force-controlled, potentially brittle action — verify splice location/length can develop fye.'
                               if bool(run_row.get('asce_splice_controlled', False)) else
                               'Verify longitudinal bars are continuous or spliced/developed to yield fye over the clear height and into the joints (force-controlled action under net tension).')
                add_warning_flag(all_checks, run_row, 'tension_splice_development', True, 'ASCE 41 10.3.5 / ACI 25.4-25.5', splice_note)
                if str(run_row.get('story', '')).strip() in {'0', '1'}:
                    add_warning_flag(all_checks, run_row, 'foundation_uplift', True, 'ASCE 41 Ch. 7 force-controlled / 10.13', f"Net tension at base story '{run_row.get('story', '')}': verify the uplift load path — column-to-footing anchorage, footing weight/soil uplift capacity (outside the scope of this checker).")
            if fclass == SMF:
                add_min_check(all_checks, run_row, 'scwb_top_x', scwb['scwb_top_x_ratio'], 1.0, 'ACI 18.7.3.2', 'Strong-column weak-beam ratio at top joint in x.')
                add_min_check(all_checks, run_row, 'scwb_bottom_x', scwb['scwb_bottom_x_ratio'], 1.0, 'ACI 18.7.3.2', 'Strong-column weak-beam ratio at bottom joint in x.')
                add_min_check(all_checks, run_row, 'scwb_top_y', scwb['scwb_top_y_ratio'], 1.0, 'ACI 18.7.3.2', 'Strong-column weak-beam ratio at top joint in y.')
                add_min_check(all_checks, run_row, 'scwb_bottom_y', scwb['scwb_bottom_y_ratio'], 1.0, 'ACI 18.7.3.2', 'Strong-column weak-beam ratio at bottom joint in y.')
            add_ratio_check(all_checks, run_row, 'asce41_rot_ratio_x', asce_rot['ratio_x'], 1.0, f"ASCE 41 Table 10-8 ({asce_rot['damage_state']})", 'Plastic rotation demand/capacity ratio for RotX.')
            add_ratio_check(all_checks, run_row, 'asce41_rot_ratio_y', asce_rot['ratio_y'], 1.0, f"ASCE 41 Table 10-8 ({asce_rot['damage_state']})", 'Plastic rotation demand/capacity ratio for RotY.')
            for dir_key, dir_data in [('x', asce_rot['x']), ('y', asce_rot['y'])]:
                add_info_check(all_checks, run_row, f'asce41_{dir_key}_param_a', round(dir_data['a'], 5), 'ASCE 41 Table 10-8', f'Modeling parameter a for Rot{dir_key.upper()}.')
                add_info_check(all_checks, run_row, f'asce41_{dir_key}_param_b', round(dir_data['b'], 5), 'ASCE 41 Table 10-8', f'Modeling parameter b for Rot{dir_key.upper()}.')
                add_info_check(all_checks, run_row, f'asce41_{dir_key}_param_c', round(dir_data['c'], 5), 'ASCE 41 Table 10-8', f'Residual strength ratio c for Rot{dir_key.upper()}.')
                add_info_check(all_checks, run_row, f'asce41_{dir_key}_theta_io', round(dir_data['theta_io'], 5), 'ASCE 41 Table 10-8', f'IO rotation capacity for Rot{dir_key.upper()}.')
                add_info_check(all_checks, run_row, f'asce41_{dir_key}_theta_ls', round(dir_data['theta_ls'], 5), 'ASCE 41 Table 10-8', f'LS rotation capacity for Rot{dir_key.upper()}.')
                add_info_check(all_checks, run_row, f'asce41_{dir_key}_theta_cp', round(dir_data['theta_cp'], 5), 'ASCE 41 Table 10-8', f'CP rotation capacity for Rot{dir_key.upper()}.')
                add_info_check(all_checks, run_row, f'asce41_{dir_key}_v_ratio', round(dir_data['vye_over_vcoloe'], 5), 'ASCE 41 Table 10-8', f'Vye/VcolOE parameter for Rot{dir_key.upper()}, automated from shear ratio but not less than 0.2.')
            if asce_rot['warnings']:
                add_warning_flag(all_checks, run_row, 'asce41_parameter_warning', True, 'ASCE 41 Table 10-8 notes', ' | '.join(asce_rot['warnings']))

            joint_demand_ref = {
                SMF: ('ACI 18.8.4', 'ACI 18.8.4.1 simplified', 'Simplified joint shear demand using probable (1.25fy) beam tension minus column shear.'),
                IMF: ('ACI 18.4.4.7', 'ACI 18.4.4.7.2 / 18.3.4 simplified', 'Simplified joint shear demand using nominal (fy) beam tension minus column shear.'),
                OMF: ('ACI 18.3.4 / 15.5', 'ACI 18.3.4 simplified', 'Simplified joint shear demand using nominal (fy) beam tension minus column shear.'),
                GRAVITY: ('ACI 18.14.3.2(d) / 15.5', 'ACI 15.4.2.1(b) simplified', 'Simplified joint shear demand using nominal (fy) beam tension minus column shear.'),
            }[fclass]
            for joint in ['top', 'bottom']:
                for axis in ['x', 'y']:
                    if not joint_static.get(f'joint_{joint}_{axis}_active', False):
                        continue
                    ratio = joint_case[f'joint_{joint}_{axis}_Vu_kN'] / max(joint_static[f'joint_{joint}_{axis}_phiVn_kN'], 1e-9)
                    add_ratio_check(all_checks, run_row, f'joint_{joint}_{axis}_shear_ratio', ratio, 1.0, joint_demand_ref[0] + basis_tag, f'Simplified joint shear demand/capacity ratio at {joint} joint in {axis}.')
                    add_info_check(all_checks, run_row, f'joint_{joint}_{axis}_Vu_kN', round(joint_case[f'joint_{joint}_{axis}_Vu_kN'], 1), joint_demand_ref[1], joint_demand_ref[2])

            check_rows.extend(all_checks)

            results_rows.append({
                'column_id': run_row['column_id'], 'story': run_row['story'], 'load_case': run_row.get('load_case', 'U1'),
                'damage_state': run_row.get('damage_state', 'CP'), 'status': overall_status(static_checks + all_checks),
                'Ag_mm2': round(float(geom['Ag_mm2']), 1), 'Ach_mm2': round(float(geom['Ach_mm2']), 1), 'As_mm2': round(float(geom['As_mm2']), 1),
                'rho_long': round(float(geom['rho_long']), 5), 'n_lateral_supported_bars': int(geom['n_lateral_supported_bars']), 'hx_mm': round(float(geom['hx_mm']), 1),
                'phiPn0_kN': round(axial['phiPn0_kN'], 1), 'phiMn_x_kNm': round(col_x['phiMn_kNm'], 1), 'phiMn_y_kNm': round(col_y['phiMn_kNm'], 1),
                'Mnc_x_kNm': round(col_x['Mnc_kNm'], 1), 'Mnc_y_kNm': round(col_y['Mnc_kNm'], 1),
                'Mpr_top_x_kNm': round(col_x_dem['Mpr_pos_kNm'], 1), 'Mpr_bot_x_kNm': round(col_x_dem['Mpr_neg_kNm'], 1),
                'Mpr_top_y_kNm': round(col_y_dem['Mpr_pos_kNm'], 1), 'Mpr_bot_y_kNm': round(col_y_dem['Mpr_neg_kNm'], 1),
                'analysis_basis': 'expected' if col_expected else 'design',
                'axial_cap_ratio': round(axial_cap_ratio, 3),
                'phiVn_x_kN': round(shear_case['phiVn_eff_x_kN'], 1), 'phiVn_y_kN': round(shear_case['phiVn_eff_y_kN'], 1),
                'Vc_zero_x': bool(shear_case['vc_zero_applies_x']), 'Vc_zero_y': bool(shear_case['vc_zero_applies_y']),
                'Ve_column_x_kN': round(prob_shear['Ve_col_x_kN'] if fclass in (SMF, GRAVITY) else prob_shear['Ve_col_Mn_x_kN'], 1),
                'Ve_column_y_kN': round(prob_shear['Ve_col_y_kN'] if fclass in (SMF, GRAVITY) else prob_shear['Ve_col_Mn_y_kN'], 1),
                'Ve_design_x_kN': round(Ve_check['x'], 1), 'Ve_design_y_kN': round(Ve_check['y'], 1),
                'RotX': round(float(run_row.get('RotX', 0.0)), 6), 'RotY': round(float(run_row.get('RotY', run_row.get('RotZ', 0.0))), 6),
                'asce41_x_a': round(asce_rot['x']['a'], 6), 'asce41_x_b': round(asce_rot['x']['b'], 6), 'asce41_x_c': round(asce_rot['x']['c'], 6),
                'asce41_x_theta_io': round(asce_rot['x']['theta_io'], 6), 'asce41_x_theta_ls': round(asce_rot['x']['theta_ls'], 6), 'asce41_x_theta_cp': round(asce_rot['x']['theta_cp'], 6),
                'asce41_x_v_ratio': round(asce_rot['x']['vye_over_vcoloe'], 6),
                'asce41_y_a': round(asce_rot['y']['a'], 6), 'asce41_y_b': round(asce_rot['y']['b'], 6), 'asce41_y_c': round(asce_rot['y']['c'], 6),
                'asce41_y_theta_io': round(asce_rot['y']['theta_io'], 6), 'asce41_y_theta_ls': round(asce_rot['y']['theta_ls'], 6), 'asce41_y_theta_cp': round(asce_rot['y']['theta_cp'], 6),
                'asce41_y_v_ratio': round(asce_rot['y']['vye_over_vcoloe'], 6),
                'asce41_rot_ratio_x': round(asce_rot['ratio_x'], 3), 'asce41_rot_ratio_y': round(asce_rot['ratio_y'], 3),
                'joint_top_x_phiVn_kN': round(float(joint_static.get('joint_top_x_phiVn_kN', 0.0)), 1),
                'joint_top_y_phiVn_kN': round(float(joint_static.get('joint_top_y_phiVn_kN', 0.0)), 1),
                'joint_bottom_x_phiVn_kN': round(float(joint_static.get('joint_bottom_x_phiVn_kN', 0.0)), 1),
                'joint_bottom_y_phiVn_kN': round(float(joint_static.get('joint_bottom_y_phiVn_kN', 0.0)), 1),
                'joint_top_x_Vu_kN': round(float(joint_case.get('joint_top_x_Vu_kN', 0.0)), 1),
                'joint_top_y_Vu_kN': round(float(joint_case.get('joint_top_y_Vu_kN', 0.0)), 1),
                'joint_bottom_x_Vu_kN': round(float(joint_case.get('joint_bottom_x_Vu_kN', 0.0)), 1),
                'joint_bottom_y_Vu_kN': round(float(joint_case.get('joint_bottom_y_Vu_kN', 0.0)), 1),
                'scwb_top_x_ratio': round(scwb['scwb_top_x_ratio'], 3), 'scwb_bottom_x_ratio': round(scwb['scwb_bottom_x_ratio'], 3),
                'scwb_top_y_ratio': round(scwb['scwb_top_y_ratio'], 3), 'scwb_bottom_y_ratio': round(scwb['scwb_bottom_y_ratio'], 3),
                'pm_ratio_x': round(demand_ratio_pm_x, 3), 'pm_ratio_y': round(demand_ratio_pm_y, 3),
                'shear_ratio_x': round(shear_ratio_x, 3), 'shear_ratio_y': round(shear_ratio_y, 3),
                'probable_shear_ratio_x': round(probable_shear_ratio_x, 3), 'probable_shear_ratio_y': round(probable_shear_ratio_y, 3),
                'pm_svg_x': pm_svg_x, 'pm_pdf_x': pm_pdf_x, 'pm_svg_y': pm_svg_y, 'pm_pdf_y': pm_pdf_y,
            })

            report_case_contexts.append({
                'row': run_row, 'checks': static_checks + all_checks, 'col_x': col_x, 'col_y': col_y,
                'beam_actions': beam_actions, 'prob_shear': prob_shear, 'shear_case': shear_case,
                'scwb': scwb, 'joint_case': joint_case, 'asce_rot': asce_rot,
            })

        report_contexts.append({
            'column_id': column_id, 'prop_row': prop_row, 'geom': geom, 'tr_meta': tr_meta, 'axial': axial,
            'shear_base': shear_base, 'beam_static': beam_actions,
            'joint_static': joint_static, 'flexure0': {'x': flexure0_x, 'y': flexure0_y}, 'static_checks': static_checks,
            'pm_paths': {
                'pm_svg_x': pm_svg_x, 'pm_pdf_x': pm_pdf_x, 'pm_png_x': pm_png_x,
                'pm_svg_y': pm_svg_y, 'pm_pdf_y': pm_pdf_y, 'pm_png_y': pm_png_y,
            },
            'cases': report_case_contexts, 'pry_name': args.pry_name,
            'beam_actions': beam_actions,
            'section_png_path': section_png_path,
            'report_options': {
                'hide_rotation_table': args.hide_rotation_table,
                'hide_beam_table': args.hide_beam_table,
                'hide_joint_table': args.hide_joint_table,
            },
        })

    write_csv(outdir / 'column_results.csv', results_rows)
    write_csv(outdir / 'column_checks.csv', check_rows)
    failure_rows = [r for r in check_rows if str(r.get('status')) in {'NG', 'WARNING'}]
    write_csv(outdir / 'column_failures.csv', failure_rows, fieldnames=list(check_rows[0].keys()) if check_rows else None)
    print(f'Wrote {outdir / "column_results.csv"}')
    print(f'Wrote {outdir / "column_checks.csv"}')
    print(f'Wrote {outdir / "column_failures.csv"}')
    if requested_reports and not args.skip_pm:
        print(f'Wrote P-M diagrams under {pm_dir}')

    any_reports = requested_reports or requested_detailed
    if any_reports:
        report_dir.mkdir(parents=True, exist_ok=True)
        n_summary = n_detailed = 0
        all_requested = requested_reports | requested_detailed
        for ctx in report_contexts:
            if ctx['column_id'] not in all_requested:
                continue
            slug = slugify(str(ctx['column_id']))
            if ctx['column_id'] in requested_reports:
                # LaTeX source (for CLI users with pdflatex)
                tex = build_latex_report(ctx)
                (report_dir / f'{slug}_memoria.tex').write_text(tex, encoding='utf-8')
                # Summary PDF (ReportLab)
                try:
                    pdf_bytes = build_pdf_report(ctx)
                    (report_dir / f'{slug}_memoria.pdf').write_bytes(pdf_bytes)
                    n_summary += 1
                except Exception as exc:
                    print(f'Warning: Summary PDF failed for {ctx["column_id"]}: {exc}')
            if ctx['column_id'] in requested_detailed:
                # Detailed step-by-step educational PDF
                try:
                    pdf_det = build_detailed_pdf_report(ctx)
                    (report_dir / f'{slug}_detailed.pdf').write_bytes(pdf_det)
                    n_detailed += 1
                except Exception as exc:
                    print(f'Warning: Detailed PDF failed for {ctx["column_id"]}: {exc}')
        parts = []
        if n_summary:  parts.append(f'{n_summary} summary')
        if n_detailed: parts.append(f'{n_detailed} detailed')
        print(f'Wrote {", ".join(parts)} report(s) under {report_dir}')
    else:
        print('No reports requested.')


if __name__ == '__main__':
    main()
