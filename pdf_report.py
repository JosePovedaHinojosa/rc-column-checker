"""
pdf_report.py
=============
Builds the column verification "Memoria de cálculo" as a pure-Python PDF
using ReportLab (no LaTeX / pdflatex required).

Entry point
-----------
    from pdf_report import build_pdf_report
    pdf_bytes: bytes = build_pdf_report(ctx)
"""
from __future__ import annotations

import io
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── page geometry ─────────────────────────────────────────────────────────────
_W, _H   = A4                        # 595 × 842 pt
_MARGIN  = 18 * mm
_INNER_W = _W - 2 * _MARGIN         # ≈ 174 mm

# ── colours ───────────────────────────────────────────────────────────────────
_BLACK      = colors.HexColor('#1a1a1a')   # titles, section headings, rule lines
_HDR_BG     = colors.HexColor('#2d2d2d')   # table header row background
_LIGHT_GRAY = colors.HexColor('#f4f4f4')   # alternating body row background
_MID_GRAY   = colors.HexColor('#cccccc')   # grid lines
_RED_NG     = colors.HexColor('#cc0000')   # NG status
_AMBER      = colors.HexColor('#d06000')   # WARNING status

# ── paragraph styles ──────────────────────────────────────────────────────────
_BASE = getSampleStyleSheet()

_S_TITLE = ParagraphStyle(
    'ReportTitle', parent=_BASE['Normal'], fontSize=14, fontName='Helvetica-Bold',
    textColor=_BLACK, spaceAfter=2 * mm, spaceBefore=0,
)
_S_H2 = ParagraphStyle(
    'ReportH2', parent=_BASE['Normal'], fontSize=10, fontName='Helvetica-Bold',
    textColor=_BLACK, spaceAfter=2 * mm, spaceBefore=4 * mm,
)
_S_CELL = ParagraphStyle(
    'Cell', parent=_BASE['Normal'], fontSize=7.5, leading=9.5,
    fontName='Helvetica',
)
_S_CELL_B = ParagraphStyle(
    'CellBold', parent=_BASE['Normal'], fontSize=7.5, leading=9.5,
    fontName='Helvetica-Bold', textColor=colors.white,
)
_S_SMALL = ParagraphStyle(
    'Small', parent=_BASE['Normal'], fontSize=7, leading=9,
    textColor=colors.HexColor('#555555'),
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _fmt(v: object, nd: int = 2) -> str:
    try:
        return f'{float(v):.{nd}f}'
    except Exception:
        return str(v)


def _p(text: str, bold: bool = False) -> Paragraph:
    """Wrap text in a Paragraph (enables word-wrap inside table cells)."""
    style = _S_CELL_B if bold else _S_CELL
    return Paragraph(str(text), style)


# ── table factory ─────────────────────────────────────────────────────────────

def _tbl(data: list[list], col_widths: list[float],
         status_col: int | None = None) -> Table:
    """
    Standard table with navy header row, alternating body rows, and
    optional colour-coding in ``status_col`` (0-based index of data column).
    """
    n_cols = len(col_widths)
    tbl = Table(data, colWidths=col_widths, repeatRows=1)

    ts: list = [
        # header
        ('BACKGROUND', (0, 0), (n_cols - 1, 0), _HDR_BG),
        ('TEXTCOLOR',  (0, 0), (n_cols - 1, 0), colors.white),
        ('FONTNAME',   (0, 0), (n_cols - 1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',   (0, 0), (n_cols - 1, 0), 7.5),
        # body
        ('FONTNAME',   (0, 1), (n_cols - 1, -1), 'Helvetica'),
        ('FONTSIZE',   (0, 1), (n_cols - 1, -1), 7.5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, _LIGHT_GRAY]),
        # grid
        ('GRID',       (0, 0), (-1, -1), 0.3, _MID_GRAY),
        # padding
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING',   (0, 0), (-1, -1), 3),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 3),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]

    if status_col is not None:
        for ri, row in enumerate(data[1:], start=1):
            val = row[status_col]
            s = (val.text if isinstance(val, Paragraph) else str(val)).strip().upper()
            if s == 'NG':
                ts += [
                    ('TEXTCOLOR', (status_col, ri), (status_col, ri), _RED_NG),
                    ('FONTNAME',  (status_col, ri), (status_col, ri), 'Helvetica-Bold'),
                ]
            elif s in ('WARNING', 'WARN'):
                ts += [
                    ('TEXTCOLOR', (status_col, ri), (status_col, ri), _AMBER),
                    ('FONTNAME',  (status_col, ri), (status_col, ri), 'Helvetica-Bold'),
                ]

    tbl.setStyle(TableStyle(ts))
    return tbl


def _side_by_side(left: Any, right: Any,
                  left_w: float, right_w: float) -> Table:
    tbl = Table([[left, right]], colWidths=[left_w, right_w])
    tbl.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return tbl


# ── section builders ──────────────────────────────────────────────────────────

def _s_input_summary(row: dict, section_png: str) -> list:
    params = [
        [_p('Parámetro', bold=True), _p('Valor', bold=True)],
        ['Column ID',       str(row['column_id'])],
        ['Story',           str(row['story'])],
        ['Frame type',      str(row['frame_type'])],
        ['b [mm]',          _fmt(row['b_mm'], 1)],
        ['h [mm]',          _fmt(row['h_mm'], 1)],
        ['Cover [mm]',      _fmt(row['cover_mm'], 1)],
        ['l_clear [mm]',    _fmt(row['clear_height_mm'], 1)],
        ["f'c [MPa]",       _fmt(row['fc_MPa'], 2)],
        ['fy,long [MPa]',   _fmt(row['fy_long_MPa'], 2)],
        ['fyt [MPa]',       _fmt(row['fy_trans_MPa'], 2)],
        ['Barras T/B/L/R',  '{}/{}/{}/{}'.format(
            int(row['n_bars_x_top']), int(row['n_bars_x_bottom']),
            int(row['n_bars_y_left']), int(row['n_bars_y_right']))],
    ]
    param_tbl = _tbl(params, [48 * mm, 32 * mm])

    _SKT_MAX_W = 58 * mm   # max sketch width
    _SKT_MAX_H = 85 * mm   # max sketch height (allows tall columns without overflowing)
    if section_png and Path(section_png).exists():
        try:
            _ir = ImageReader(section_png)
            _iw, _ih = _ir.getSize()
            _scale = min(_SKT_MAX_W / _iw, _SKT_MAX_H / _ih)
            sketch: Any = Image(str(section_png), width=_iw * _scale, height=_ih * _scale)
        except Exception:
            sketch: Any = Paragraph('(sección no disponible)', _S_SMALL)
    else:
        sketch = Paragraph('(sección no disponible)', _S_SMALL)

    return [
        Paragraph('Resumen del input', _S_H2),
        _side_by_side(param_tbl, sketch, 85 * mm, _INNER_W - 85 * mm),
        Spacer(1, 3 * mm),
    ]


def _s_derived(geom: dict, tr_meta: dict) -> list:
    data = [
        [_p('Propiedad', bold=True), _p('Valor', bold=True)],
        ['Ag [mm²]',            _fmt(geom['Ag_mm2'], 1)],
        ['Ach [mm²]',           _fmt(geom['Ach_mm2'], 1)],
        ['As [mm²]',            _fmt(geom['As_mm2'], 1)],
        ['ρ_long [-]',          _fmt(geom['rho_long'], 5)],
        ['n barras soportadas', _fmt(geom['n_lateral_supported_bars'], 0)],
        ['hx_max [mm]',         _fmt(geom['hx_mm'], 1)],
        ['lo,x [mm]',           _fmt(tr_meta['lo_x_mm'], 1)],
        ['lo,y [mm]',           _fmt(tr_meta['lo_y_mm'], 1)],
    ]
    return [
        Paragraph('Propiedades derivadas', _S_H2),
        _tbl(data, [70 * mm, 40 * mm]),
        Spacer(1, 3 * mm),
    ]


def _s_capacity(axial: dict, flexure0: dict, shear_base: dict) -> list:
    cap_data = [
        [_p('Magnitud', bold=True), _p('Valor', bold=True)],
        ['Pn0 [kN]',       _fmt(axial['Pn0_kN'], 1)],
        ['φPn0 [kN]',      _fmt(axial['phiPn0_kN'], 1)],
        ['Mn0,x [kN·m]',   _fmt(flexure0['x']['Mn_min_kNm'], 1)],
        ['φMn0,x [kN·m]',  _fmt(flexure0['x']['phiMn_min_kNm'], 1)],
        ['Mpr0,x [kN·m]',  _fmt(flexure0['x']['Mpr_min_kNm'], 1)],
        ['Mn0,y [kN·m]',   _fmt(flexure0['y']['Mn_min_kNm'], 1)],
        ['φMn0,y [kN·m]',  _fmt(flexure0['y']['phiMn_min_kNm'], 1)],
        ['Mpr0,y [kN·m]',  _fmt(flexure0['y']['Mpr_min_kNm'], 1)],
    ]
    shear_data = [
        [_p('Eje', bold=True), _p('Vc [kN]', bold=True),
         _p('Vs [kN]', bold=True), _p('φVn [kN]', bold=True)],
        ['x', _fmt(shear_base['Vc_x_kN'], 1), _fmt(shear_base['Vs_x_kN'], 1), _fmt(shear_base['phiVn_x_kN'], 1)],
        ['y', _fmt(shear_base['Vc_y_kN'], 1), _fmt(shear_base['Vs_y_kN'], 1), _fmt(shear_base['phiVn_y_kN'], 1)],
    ]
    cap_tbl   = _tbl(cap_data,   [60 * mm, 40 * mm])
    shear_tbl = _tbl(shear_data, [18 * mm, 26 * mm, 26 * mm, 26 * mm])
    return [
        Paragraph('Capacidades de la columna', _S_H2),
        _side_by_side(cap_tbl, shear_tbl, 105 * mm, _INNER_W - 105 * mm),
        Spacer(1, 3 * mm),
    ]


def _s_static_checks(static_checks: list) -> list:
    rows = [[
        _p('Chequeo', bold=True), _p('Estado', bold=True), _p('Ref.', bold=True),
        _p('Provisto', bold=True), _p('Requerido', bold=True), _p('Comentario', bold=True),
    ]]
    for chk in static_checks:
        if str(chk.get('status')) == 'INFO':
            continue
        rows.append([
            _p(str(chk['check_name']).replace('_', ' ')),
            str(chk['status']),
            _p(str(chk.get('code_ref', ''))),
            _p(str(chk['provided'])),
            _p(str(chk['required'])),
            _p(str(chk['message'])),
        ])
    return [
        Paragraph('Chequeos de reforzamiento', _S_H2),
        _tbl(rows, [42 * mm, 14 * mm, 26 * mm, 20 * mm, 20 * mm, 52 * mm], status_col=1),
        Spacer(1, 3 * mm),
    ]


def _s_beam_capacities(beam_static: dict) -> list:
    faces = ['beam_top_x', 'beam_bottom_x', 'beam_top_y', 'beam_bottom_y']
    rows: list[list] = []
    for face in faces:
        for side in ['side1', 'side2']:
            p = f'{face}_{side}'
            if not beam_static.get(f'{p}_active', False):
                continue
            rows.append([
                _p(p.replace('_', ' ')),
                _fmt(beam_static[f'{p}_As_top_mm2'], 1),
                _fmt(beam_static[f'{p}_As_bot_mm2'], 1),
                _fmt(beam_static[f'{p}_Mn_pos_kNm'], 1),
                _fmt(beam_static[f'{p}_Mn_neg_kNm'], 1),
                _fmt(beam_static[f'{p}_Mpr_pos_kNm'], 1),
                _fmt(beam_static[f'{p}_Mpr_neg_kNm'], 1),
                'Sí' if beam_static.get(f'{p}_continuous', False) else 'No',
            ])
    if not rows:
        return []
    header = [[
        _p('Viga', bold=True), _p('As,top\n[mm²]', bold=True), _p('As,bot\n[mm²]', bold=True),
        _p('Mn+\n[kN·m]', bold=True), _p('Mn-\n[kN·m]', bold=True),
        _p('Mpr+\n[kN·m]', bold=True), _p('Mpr-\n[kN·m]', bold=True),
        _p('Cont.', bold=True),
    ]]
    return [
        Paragraph('Capacidades de vigas conectadas', _S_H2),
        _tbl(header + rows, [40*mm, 18*mm, 18*mm, 20*mm, 20*mm, 20*mm, 20*mm, 12*mm]),
        Spacer(1, 3 * mm),
    ]


def _s_joint(joint_static: dict) -> list:
    rows: list[list] = []
    for joint in ['top', 'bottom']:
        for axis in ['x', 'y']:
            if not joint_static.get(f'joint_{joint}_{axis}_active', False):
                continue
            conds = '{}{}{}{}'.format(
                'Y' if joint_static[f'joint_{joint}_{axis}_cond_a'] else 'N',
                'Y' if joint_static[f'joint_{joint}_{axis}_cond_b'] else 'N',
                'Y' if joint_static[f'joint_{joint}_{axis}_cond_c'] else 'N',
                'Y' if joint_static[f'joint_{joint}_{axis}_cond_d'] else 'N',
            )
            rows.append([
                joint, axis,
                _fmt(joint_static[f'joint_{joint}_{axis}_Aj_mm2'], 1),
                _fmt(joint_static[f'joint_{joint}_{axis}_coeff'], 2),
                'Sí' if joint_static[f'joint_{joint}_{axis}_confined'] else 'No',
                _fmt(joint_static[f'joint_{joint}_{axis}_Vn_kN'], 1),
                _fmt(joint_static[f'joint_{joint}_{axis}_phiVn_kN'], 1),
                conds,
            ])
    if not rows:
        return []
    header = [[
        _p('Nudo', bold=True), _p('Eje', bold=True),
        _p('Aj [mm²]', bold=True), _p('αj', bold=True), _p('Conf.', bold=True),
        _p('Vn [kN]', bold=True), _p('φVn [kN]', bold=True), _p('15.5.2.5', bold=True),
    ]]
    return [
        Paragraph('Capacidad de nudo / joint', _S_H2),
        _tbl(header + rows, [18*mm, 10*mm, 28*mm, 14*mm, 14*mm, 22*mm, 22*mm, 22*mm]),
        Spacer(1, 3 * mm),
    ]


def _s_rotation(cases: list) -> list:
    rows: list[list] = []
    for direction, key, bucket in [('RotX', 'ratio_x', 'x'), ('RotY', 'ratio_y', 'y')]:
        if not cases:
            continue
        crit = max(cases, key=lambda c: float(c['asce_rot'].get(key, 0.0)))
        ar = crit['asce_rot'][bucket]
        rr = crit['row']
        rows.append([
            direction, str(rr['load_case']), str(ar['damage_state']),
            _fmt(rr.get(direction, 0.0), 5),
            _fmt(ar['theta_io'], 5), _fmt(ar['theta_ls'], 5), _fmt(ar['theta_cp'], 5),
            _fmt(ar['theta_cap'], 5),
            _fmt(ar['ratio'], 3),
            _fmt(ar['vye_over_vcoloe'], 3),
            'Sí' if ar['splice_controlled'] else 'No',
        ])
    if not rows:
        return []
    header = [[
        _p('Dir.', bold=True), _p('Caso', bold=True), _p('DS', bold=True),
        _p('θd', bold=True), _p('θIO', bold=True), _p('θLS', bold=True),
        _p('θCP', bold=True), _p('θcap', bold=True), _p('D/C', bold=True),
        _p('Vye/Vco', bold=True), _p('Splice', bold=True),
    ]]
    return [
        Paragraph('ASCE 41 Tabla 10-8 — rotaciones plásticas', _S_H2),
        _tbl(
            header + rows,
            [12*mm, 18*mm, 10*mm, 15*mm, 15*mm, 15*mm, 15*mm, 15*mm, 14*mm, 18*mm, 12*mm],
            status_col=8,
        ),
        Spacer(1, 3 * mm),
    ]


def _s_load_results(cases: list) -> list:
    header = [[
        _p('Caso', bold=True), _p('Pu\n[kN]', bold=True), _p('Mux\n[kN·m]', bold=True),
        _p('Muy\n[kN·m]', bold=True), _p('Mn,x\n[kN·m]', bold=True),
        _p('Mn,y\n[kN·m]', bold=True), _p('φVn,x\n[kN]', bold=True),
        _p('φVn,y\n[kN]', bold=True),
        _p('Vj,top,x\n[kN]', bold=True), _p('Vj,top,y\n[kN]', bold=True),
    ]]
    rows: list[list] = []
    for case in cases:
        r  = case['row']
        cx = case['col_x']
        cy = case['col_y']
        sh = case['shear_case']
        jc = case['joint_case']
        rows.append([
            str(r['load_case']),
            _fmt(r['Pu_kN'], 1), _fmt(r['Mux_kNm'], 1), _fmt(r['Muy_kNm'], 1),
            _fmt(cx['Mnc_kNm'], 1), _fmt(cy['Mnc_kNm'], 1),
            _fmt(sh['phiVn_eff_x_kN'], 1), _fmt(sh['phiVn_eff_y_kN'], 1),
            _fmt(jc.get('joint_top_x_Vu_kN', 0.0), 1),
            _fmt(jc.get('joint_top_y_Vu_kN', 0.0), 1),
        ])
    cw = _INNER_W / 10
    return [
        Paragraph('Resultados por combinación', _S_H2),
        _tbl(header + rows, [cw] * 10),
        Spacer(1, 3 * mm),
    ]


def _s_critical_checks(cases: list) -> list:
    grouped: dict = defaultdict(list)
    for case in cases:
        for chk in case['checks']:
            if chk.get('load_case') == 'ALL' or chk.get('status') == 'INFO':
                continue
            grouped[chk['check_name']].append(chk)

    critical: list = []
    for name, chk_rows in grouped.items():
        def score(r: dict) -> tuple:
            req = str(r.get('required', ''))
            try:
                target = float(re.sub(r'[^0-9.eE+-]', '', req))
            except Exception:
                target = 1.0
            try:
                prov = float(r.get('provided', 0.0))
            except Exception:
                prov = 0.0
            margin = prov - target if '>=' in req else target - prov
            return (0 if r['status'] == 'NG' else 1, margin)
        critical.append(sorted(chk_rows, key=score)[0])
    critical.sort(key=lambda r: (r['status'] != 'NG', str(r['check_name'])))
    if not critical:
        return []

    header = [[
        _p('Caso', bold=True), _p('Chequeo', bold=True), _p('Estado', bold=True),
        _p('Ref.', bold=True), _p('Provisto', bold=True), _p('Requerido', bold=True),
    ]]
    rows: list[list] = []
    for chk in critical:
        rows.append([
            _p(str(chk['load_case'])),
            _p(str(chk['check_name']).replace('_', ' ')),
            str(chk['status']),
            _p(str(chk.get('code_ref', ''))),
            _p(str(chk['provided'])),
            _p(str(chk['required'])),
        ])
    return [
        Paragraph('Chequeos dependientes de carga — combinación crítica', _S_H2),
        _tbl(header + rows, [20*mm, 48*mm, 14*mm, 30*mm, 28*mm, 28*mm], status_col=2),
        Spacer(1, 3 * mm),
    ]


def _s_pm_diagrams(pm_paths: dict) -> list:
    story = [Paragraph('Diagrama P-M', _S_H2)]
    img_w = _INNER_W * 0.82
    img_h = img_w * (5.8 / 7.2)
    added = False
    for axis, key in [('x', 'pm_png_x'), ('y', 'pm_png_y')]:
        png = pm_paths.get(key, '')
        if png and Path(png).exists():
            story.append(Paragraph(f'Eje {axis}', _S_SMALL))
            story.append(Image(str(png), width=img_w, height=img_h))
            story.append(Spacer(1, 4 * mm))
            added = True
    if not added:
        return []
    return story


# ── header / footer ───────────────────────────────────────────────────────────

def _make_on_page(logo_path: str | None, pry_name: str, column_id: str):
    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(_BLACK)
        canvas.setLineWidth(0.5)
        canvas.line(_MARGIN, _H - 14 * mm, _W - _MARGIN, _H - 14 * mm)
        if logo_path and Path(logo_path).exists():
            try:
                canvas.drawImage(
                    logo_path, _MARGIN, _H - 13 * mm,
                    width=50 * mm, height=10 * mm,
                    preserveAspectRatio=True, anchor='sw',
                )
            except Exception:
                pass
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(_BLACK)
        label = f'PROYECTO: {pry_name}   |   {column_id}' if pry_name else column_id
        canvas.drawRightString(_W - _MARGIN, _H - 8 * mm, label)
        canvas.line(_MARGIN, 12 * mm, _W - _MARGIN, 12 * mm)
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(colors.HexColor('#555555'))
        canvas.drawCentredString(_W / 2, 9 * mm, str(doc.page))
        canvas.setFont('Helvetica', 6)
        canvas.setFillColor(colors.HexColor('#aaaaaa'))
        canvas.drawCentredString(
            _W / 2, 5 * mm,
            '© 2025 Torrefuerte-Estructural · www.torrefuerte.ec · '
            'Versión beta — no validada exhaustivamente · uso bajo responsabilidad del ingeniero',
        )
        canvas.restoreState()
    return on_page


# ── main entry point ──────────────────────────────────────────────────────────

def build_pdf_report(ctx: dict) -> bytes:
    """Assemble the full verification report and return as PDF bytes."""
    row          = ctx['prop_row']
    geom         = ctx['geom']
    tr_meta      = ctx['tr_meta']
    axial        = ctx['axial']
    shear_base   = ctx['shear_base']
    flexure0     = ctx['flexure0']
    joint_static = ctx['joint_static']
    beam_static  = ctx['beam_static']
    cases        = ctx['cases']
    pm_paths     = ctx['pm_paths']
    pry_name     = ctx.get('pry_name', '')
    opts         = ctx.get('report_options', {})
    column_id    = str(ctx['column_id'])
    section_png  = ctx.get('section_png_path', '')
    logo_path    = str(Path(__file__).parent / 'assets' / 'Logo_horizontal_Torrefuerte.png')

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=_MARGIN, rightMargin=_MARGIN,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f'Memoria RC — {column_id}',
        author='rc-column-checker',
    )

    on_page = _make_on_page(logo_path, pry_name, column_id)

    story: list[Any] = [
        Spacer(1, 4 * mm),
        Paragraph('Memoria de cálculo de columna RC', _S_TITLE),
        Paragraph(column_id, _S_H2),
        HRFlowable(width='100%', thickness=0.5, color=_BLACK, spaceAfter=4 * mm),
    ]

    story += _s_input_summary(row, section_png)
    story += _s_derived(geom, tr_meta)
    story += _s_capacity(axial, flexure0, shear_base)
    story += _s_static_checks(ctx['static_checks'])
    if not opts.get('hide_beam_table'):
        story += _s_beam_capacities(beam_static)
    if not opts.get('hide_joint_table'):
        story += _s_joint(joint_static)
    if not opts.get('hide_rotation_table'):
        story += _s_rotation(cases)
    story += _s_load_results(cases)
    story += _s_critical_checks(cases)
    story += _s_pm_diagrams(pm_paths)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
