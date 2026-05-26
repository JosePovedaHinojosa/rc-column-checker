from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

def section_image_key(column_id: str) -> str:
    text = str(column_id).strip()
    text = re.split(r'_chain|_st\d+|_story\d+', text, maxsplit=1)[0]
    return text.replace('_', '')

def write_csv(path: str | Path, rows: list[dict], fieldnames: list[str] | None = None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if rows:
        if fieldnames is None:
            fieldnames = list(rows[0].keys())
    else:
        if fieldnames is None:
            fieldnames = []

    with path.open('w', newline='', encoding='utf-8') as f:
        if fieldnames:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            if rows:
                writer.writerows(rows)


def latex_escape(value: object) -> str:
    text = str(value)
    replacements = {
        '\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#',
        '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _red(text: str) -> str:
    return r'\textcolor{red}{' + text + '}'


def prettify_check_name(value: object) -> str:
    text = str(value).replace('_', ' ')
    return latex_escape(text)


def prettify_status(value: object) -> str:
    text = str(value).strip()
    low = text.lower()
    if low in {'warning', 'warn'}:
        return _red('WARN')
    if low == 'ng':
        return _red('NG')
    return latex_escape(text)


def slugify(text: str) -> str:
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', text)


def fmt_num(value: object, ndigits: int = 2) -> str:
    try:
        return f"{float(value):.{ndigits}f}"
    except Exception:
        return latex_escape(value)


def fmt_num_color_if_gt1(value: object, ndigits: int = 3) -> str:
    try:
        num = float(value)
        txt = f"{num:.{ndigits}f}"
        return _red(txt) if num > 1.0 else txt
    except Exception:
        return latex_escape(value)


def _load_template() -> str:
    template_path = Path(__file__).resolve().parent / 'templates' / 'column_report_template.tex'
    return template_path.read_text(encoding='utf-8')


def _replace(text: str, key: str, value: object) -> str:
    return text.replace(f'<<{key}>>', str(value))


def _critical_checks(cases):
    grouped = defaultdict(list)
    for case in cases:
        for chk in case['checks']:
            if chk.get('load_case') == 'ALL' or chk.get('status') == 'INFO':
                continue
            grouped[chk['check_name']].append(chk)
    out = []
    for name, rows in grouped.items():
        def score(r):
            req = str(r.get('required', ''))
            try:
                target = float(re.sub(r'[^0-9.eE+-]', '', req))
            except Exception:
                target = 1.0
            try:
                prov = float(r.get('provided', 0.0))
            except Exception:
                prov = 0.0
            if '>=' in req:
                margin = prov - target
            else:
                margin = target - prov
            return (0 if r['status'] == 'NG' else 1, margin)
        crit = sorted(rows, key=score)[0]
        out.append(crit)
    return sorted(out, key=lambda r: (r['status'] != 'NG', str(r['check_name'])))


def _critical_rotation_cases(cases):
    rows = []
    for direction, key, bucket in [('RotX', 'ratio_x', 'x'), ('RotY', 'ratio_y', 'y')]:
        if not cases:
            continue
        crit = max(cases, key=lambda c: float(c['asce_rot'].get(key, 0.0)))
        ar = crit['asce_rot'][bucket]
        rr = crit['row']
        parts = [
            latex_escape(direction), latex_escape(rr['load_case']), latex_escape(ar['damage_state']),
            fmt_num(rr.get(direction, 0.0), 5), fmt_num(ar['theta_io'], 5), fmt_num(ar['theta_ls'], 5), fmt_num(ar['theta_cp'], 5),
            fmt_num(ar['theta_cap'], 5), fmt_num_color_if_gt1(ar['ratio'], 3), fmt_num(ar['vye_over_vcoloe'], 3),
            fmt_num(ar['a'], 5), fmt_num(ar['b'], 5), fmt_num(ar['c'], 5),
            latex_escape('Yes' if ar['splice_controlled'] else 'No'),
        ]
        rows.append(' & '.join(parts) + r' \\')
    return rows


def _render_longtable(section_title: str, colspec: str, header: str, rows: list[str], empty_text: str) -> str:
    if not rows:
        return f"\\section*{{{section_title}}}\n{empty_text}\n"
    return (
        f"\\section*{{{section_title}}}\n"
        r'\small' + '\n'
        + rf'\begin{{longtable}}{{{colspec}}}' + '\n'
        + r'\toprule' + '\n'
        + header + '\\\\' + '\n'
        + r'\midrule' + '\n'
        + r'\endfirsthead' + '\n'
        + r'\toprule' + '\n'
        + header + '\\\\' + '\n'
        + r'\midrule' + '\n'
        + r'\endhead' + '\n'
        + '\n'.join(rows) + '\n'
        + r'\bottomrule' + '\n'
        + r'\end{longtable}' + '\n'
        + r'\normalsize' + '\n'
    )


def _render_tabular_section(section_title: str, colspec: str, header: str, rows: list[str], intro: str = '', empty_text: str = '') -> str:
    if not rows:
        if not empty_text:
            return ''
        return f"\\section*{{{section_title}}}\n{intro}\n{empty_text}\n"
    out = f"\\section*{{{section_title}}}\n"
    if intro:
        out += intro + '\n\n'
    out += rf'\begin{{tabular}}{{{colspec}}}' + '\n'
    out += r'\toprule' + '\n'
    out += header + '\\\\' + '\n'
    out += r'\midrule' + '\n'
    out += '\n'.join(rows) + '\n'
    out += r'\bottomrule' + '\n'
    out += r'\end{tabular}' + '\n'
    return out


def build_latex_report(ctx):
    row = ctx['prop_row']
    geom = ctx['geom']
    tr_meta = ctx['tr_meta']
    axial = ctx['axial']
    shear_base = ctx['shear_base']
    joint_static = ctx['joint_static']
    beam_static = ctx['beam_static']
    flexure0 = ctx['flexure0']
    cases = ctx['cases']
    pm_paths = ctx['pm_paths']
    pry_name = ctx.get('pry_name', '')
    report_options = ctx.get('report_options', {})


    static_checks = [chk for chk in ctx['static_checks'] if str(chk.get('status')) != 'INFO']
    static_check_rows = [
        '{} & {} & {} & {} & {} & {} \\\\'.format(
            prettify_check_name(chk['check_name']), prettify_status(chk['status']), latex_escape(chk.get('code_ref', '')),
            latex_escape(chk['provided']), latex_escape(chk['required']), latex_escape(chk['message'])
        ) for chk in static_checks
    ]
    static_checks_section = _render_longtable(
        'Chequeos reforzamiento ',
        'p{3.0cm}p{1cm}p{2.4cm}p{2.2cm}p{2.2cm}p{5.3cm}',
        r"Chequeo & Estado & Ref. código & Provisto & Requerido & Comentario ",
        static_check_rows,
        'Sin chequeos estáticos.'
    )

    beam_rows = []
    for face in ['beam_top_x', 'beam_bottom_x', 'beam_top_y', 'beam_bottom_y']:
        for side in ['side1', 'side2']:
            p = f'{face}_{side}'
            if not beam_static.get(f'{p}_active', False):
                continue
            beam_rows.append(
                '{} & {} & {} & {} & {} & {} & {} & {} \\\\'.format(
                    latex_escape(p), fmt_num(beam_static[f'{p}_As_top_mm2'], 1), fmt_num(beam_static[f'{p}_As_bot_mm2'], 1),
                    fmt_num(beam_static[f'{p}_Mn_pos_kNm'], 1), fmt_num(beam_static[f'{p}_Mn_neg_kNm'], 1),
                    fmt_num(beam_static[f'{p}_Mpr_pos_kNm'], 1), fmt_num(beam_static[f'{p}_Mpr_neg_kNm'], 1),
                    latex_escape('Yes' if beam_static.get(f'{p}_continuous', False) else 'No')
                )
            )
    beam_intro = (
        r"Las áreas de acero de vigas se calculan automáticamente como $A_s = n_{bars}\,\pi d_b^2/4$. "
        r"El momento nominal se idealiza con:" + '\n'
        r"\[" + '\n'
        r"M_n = A_s f_y (d-a/2), \qquad M_{pr}=A_s(1.25f_y)(d-a/2)" + '\n'
        r"\]"
    )
    beam_section = '' if report_options.get('hide_beam_table', False) else _render_tabular_section(
        'Capacidades de vigas conectadas',
        'lrrrrrrr',
        r'Viga & $A_{s,top}$ & $A_{s,bot}$ & $M_{n}^{+}$ & $M_{n}^{-}$ & $M_{pr}^{+}$ & $M_{pr}^{-}$ & Cont. ',
        beam_rows,
        intro=beam_intro,
        empty_text='Sin vigas conectadas.'
    )

    joint_rows = []
    for joint in ['top', 'bottom']:
        for axis in ['x', 'y']:
            if not joint_static.get(f'joint_{joint}_{axis}_active', False):
                continue
            joint_rows.append(
                '{} & {} & {} & {} & {} & {} & {} & {} \\\\'.format(
                    latex_escape(joint), latex_escape(axis),
                    fmt_num(joint_static[f'joint_{joint}_{axis}_Aj_mm2'], 1),
                    fmt_num(joint_static[f'joint_{joint}_{axis}_coeff'], 2),
                    latex_escape('Yes' if joint_static[f'joint_{joint}_{axis}_confined'] else 'No'),
                    fmt_num(joint_static[f'joint_{joint}_{axis}_Vn_kN'], 1),
                    fmt_num(joint_static[f'joint_{joint}_{axis}_phiVn_kN'], 1),
                    latex_escape('a,b,c,d = {} {} {} {}'.format(
                        'Y' if joint_static[f'joint_{joint}_{axis}_cond_a'] else 'N',
                        'Y' if joint_static[f'joint_{joint}_{axis}_cond_b'] else 'N',
                        'Y' if joint_static[f'joint_{joint}_{axis}_cond_c'] else 'N',
                        'Y' if joint_static[f'joint_{joint}_{axis}_cond_d'] else 'N'))
                )
            )
    joint_intro = (
        r"Se usa la resistencia nominal:" + '\n'
        r"\[" + '\n'
        r"V_n = \alpha_j \lambda \sqrt{f'_c} A_j" + '\n'
        r"\]" + '\n'
        r"con $\lambda=1.0$ para concreto de peso normal y $A_j$ calculada con la anchura efectiva del nudo usando el desplazamiento $x$ de la viga respecto a la cara de la columna. "
        r"El confinamiento transversal del nudo se revisa con 15.5.2.5(a) a (d)."
    )
    joint_section = '' if report_options.get('hide_joint_table', False) else _render_tabular_section(
        'Capacidad de nudo / joint',
        'llrrrrrl',
        r'Nudo & Eje & $A_j$ [mm$^2$] & $\alpha_j$ & Conf. & $V_n$ [kN] & $\phi V_n$ [kN] & 15.5.2.5 ',
        joint_rows,
        intro=joint_intro,
        empty_text='Sin nudos activos.'
    )

    critical_rows = []
    for chk in _critical_checks(cases):
        critical_rows.append(
            '{} & {} & {} & {} & {} & {} \\\\'.format(
                latex_escape(chk['load_case']), prettify_check_name(chk['check_name']), prettify_status(chk['status']),
                latex_escape(chk.get('code_ref', '')), latex_escape(chk['provided']), latex_escape(chk['required'])
            )
        )
    critical_checks_section = _render_longtable(
        'Chequeos dependientes de carga -- solo combinación crítica',
        'p{1.8cm}p{3.6cm}p{1cm}p{2.3cm}p{2.2cm}p{2.2cm}',
        r"Caso & Chequeo & Estado & Ref. c\'odigo & Provisto & Requerido ",
        critical_rows,
        'Sin chequeos dependientes de carga.'
    )
    critical_intro = (
        r"Para la revisión de corte en $l_o$, si se cumplen ACI 18.7.6.2.1(a) y (b), se usa $V_c=0$ y se reporta la advertencia correspondiente en los chequeos."
    )
    if critical_rows:
        critical_checks_section = critical_checks_section.replace(
            r'\section*{Chequeos dependientes de carga -- solo combinación crítica}' + '\n',
            r'\section*{Chequeos dependientes de carga -- solo combinación crítica}' + '\n' + critical_intro + '\n\n'
        )

    load_rows = []
    for case in cases:
        r = case['row']
        cx = case['col_x']
        cy = case['col_y']
        sh = case['shear_case']
        js = case['joint_case']
        parts = [
            latex_escape(r['load_case']), fmt_num(r['Pu_kN'], 1), fmt_num(r['Mux_kNm'], 1), fmt_num(r['Muy_kNm'], 1),
            fmt_num(cx['Mnc_kNm'], 1), fmt_num(cy['Mnc_kNm'], 1),
            fmt_num(sh['phiVn_eff_x_kN'], 1), fmt_num(sh['phiVn_eff_y_kN'], 1),
            fmt_num(js.get('joint_top_x_Vu_kN', 0.0), 1), fmt_num(js.get('joint_top_y_Vu_kN', 0.0), 1),
        ]
        load_rows.append(' & '.join(parts) + r' \\')
    load_table_section = _render_tabular_section(
        'Resultados por combinación',
        'lrrrrrrrrr',
        r'Caso & $P_u$ & $M_{ux}$ & $M_{uy}$ & $M_{n,x}$ & $M_{n,y}$ & $\phi V_{n,x}$ eff & $\phi V_{n,y}$ eff & $V_{j,top,x}$ & $V_{j,top,y}$ ',
        load_rows,
        empty_text='Sin combinaciones de carga.'
    )

    rotation_rows = _critical_rotation_cases(cases)
    rotation_intro = (
        r"Se evaluaron los parámetros de modelación $a$, $b$ y $c$ usando la Tabla 10-8 para columnas rectangulares con hoops sísmicos. "
        r"El parámetro $V_{ye}/V_{ColOE}$ se automatiza a partir de la relación \emph{shear ratio analysis} de cada dirección, con un valor mínimo de 0.20. "
        r"La capacidad de rotación empleada depende del estado de daño de cada combinación:" + '\n'
        r"\[" + '\n'
        r"\theta_{IO}=\min(0.15a,0.005),\qquad \theta_{LS}=0.5b,\qquad \theta_{CP}=0.7b" + '\n'
        r"\]" + '\n'
        r"(para columnas controladas por desarrollo o traslapes inadecuados, $\theta_{IO}=0$). La relación demanda/capacidad se reporta solo para la combinación crítica por dirección."
    )
    rotation_section = '' if report_options.get('hide_rotation_table', False) else _render_tabular_section(
        'ASCE 41 Tabla 10-8 -- rotaciones plásticas',
        'l l l r r r r r r r l',
        r'Dir. & Caso & DS & $\theta_d$ & $\theta_{IO}$ & $\theta_{LS}$ & $\theta_{CP}$ & $\theta_{cap}$ & D/C & $V_{ye}/V_{ColOE}$ & Splice ctrl. ',
        rotation_rows,
        intro=rotation_intro,
        empty_text='Sin rotaciones.'
    )

    pm_figs = []
    pm_x = Path(pm_paths.get('pm_pdf_x', ''))
    pm_y = Path(pm_paths.get('pm_pdf_y', ''))
    if pm_x.name:
        pm_figs.append(r'\subsection*{Diagrama P-M eje x}' + '\n' + r'\includegraphics[width=0.82\textwidth]{../pm_diagrams/' + pm_x.name + '}')
    if pm_y.name:
        pm_figs.append(r'\subsection*{Diagrama P-M eje y}' + '\n' + r'\includegraphics[width=0.82\textwidth]{../pm_diagrams/' + pm_y.name + '}')
    pm_figs_section = '\n\n'.join(pm_figs)

    tex = _load_template()
    replacements = {
        'pry_name': latex_escape(pry_name),
        'column_id': latex_escape(row['column_id']),
        'story': latex_escape(row['story']),
        'frame_type': latex_escape(row['frame_type']),
        'b_mm': fmt_num(row['b_mm'], 1), 'h_mm': fmt_num(row['h_mm'], 1), 'cover_mm': fmt_num(row['cover_mm'], 1),
        'clear_height_mm': fmt_num(row['clear_height_mm'], 1), 'lu_mm': fmt_num(row['lu_mm'], 1),
        'fc_MPa': fmt_num(row['fc_MPa'], 2), 'fy_long_MPa': fmt_num(row['fy_long_MPa'], 2), 'fy_trans_MPa': fmt_num(row['fy_trans_MPa'], 2),
        'bars_faces': '{} / {} / {} / {}'.format(fmt_num(row['n_bars_x_top'], 0), fmt_num(row['n_bars_x_bottom'], 0), fmt_num(row['n_bars_y_left'], 0), fmt_num(row['n_bars_y_right'], 0)),
        'Ag_mm2': fmt_num(geom['Ag_mm2'], 1), 'Ach_mm2': fmt_num(geom['Ach_mm2'], 1), 'As_mm2': fmt_num(geom['As_mm2'], 1),
        'n_lateral_supported_bars': fmt_num(geom['n_lateral_supported_bars'], 0), 'hx_mm': fmt_num(geom['hx_mm'], 1),
        'section_key':latex_escape(section_image_key(ctx.get("column_id", ""))),
        'lo_x_mm': fmt_num(tr_meta['lo_x_mm'], 1), 'lo_y_mm': fmt_num(tr_meta['lo_y_mm'], 1),
        'Pn0_kN': fmt_num(axial['Pn0_kN'], 1), 'phiPn0_kN': fmt_num(axial['phiPn0_kN'], 1),
        'Mn0_x_kNm': fmt_num(flexure0['x']['Mn_min_kNm'], 1), 'phiMn0_x_kNm': fmt_num(flexure0['x']['phiMn_min_kNm'], 1), 'Mpr0_x_kNm': fmt_num(flexure0['x']['Mpr_min_kNm'], 1),
        'Mn0_y_kNm': fmt_num(flexure0['y']['Mn_min_kNm'], 1), 'phiMn0_y_kNm': fmt_num(flexure0['y']['phiMn_min_kNm'], 1), 'Mpr0_y_kNm': fmt_num(flexure0['y']['Mpr_min_kNm'], 1),
        'Vc_x_kN': fmt_num(shear_base['Vc_x_kN'], 1), 'Vs_x_kN': fmt_num(shear_base['Vs_x_kN'], 1), 'phiVn_x_kN': fmt_num(shear_base['phiVn_x_kN'], 1),
        'Vc_y_kN': fmt_num(shear_base['Vc_y_kN'], 1), 'Vs_y_kN': fmt_num(shear_base['Vs_y_kN'], 1), 'phiVn_y_kN': fmt_num(shear_base['phiVn_y_kN'], 1),
        'static_checks_section': static_checks_section,
        'beam_section': beam_section,
        'joint_section': joint_section,
        'load_table_section': load_table_section,
        'critical_checks_section': critical_checks_section,
        'rotation_section': rotation_section,
        'pm_figs_section': pm_figs_section,
    }
    for key, value in replacements.items():
        tex = _replace(tex, key, value)
    return tex
