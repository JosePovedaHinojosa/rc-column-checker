"""
pdf_report_detailed.py
======================
Educational step-by-step PDF report.
Shows every major calculation with its symbolic equation, substituted values,
and numeric result — intended for students learning ACI 318-25 / ASCE 41.

Entry point
-----------
    from pdf_report_detailed import build_detailed_pdf_report
    pdf_bytes: bytes = build_detailed_pdf_report(ctx)

ctx has the same structure as the one passed to build_pdf_report().
"""
from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

import matplotlib
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from constants import (
    ACI_ALPHA1, ACI_BETA1_FC_PIVOT, ACI_BETA1_FC_STEP,
    ACI_BETA1_MAX, ACI_BETA1_MIN, ACI_BETA1_SLOPE,
    ACI_ECU, ACI_ES_MPA, ACI_FYE_FACTOR,
    ACI_PHI_COMPRESSION, ACI_PHI_TENSION, ACI_PHI_SHEAR, ACI_PHI_JOINT,
    ACI_PHI_TRANSITION_STRAIN,
    ACI_LO_MIN_MM, ACI_LO_HEIGHT_DIVISOR,
    ACI_HX_GENERAL_MM, ACI_SO_MIN_MM, ACI_SO_MAX_MM,
    ACI_RHO_S_RECT_A, ACI_RHO_S_RECT_B, ACI_RHO_S_RECT_C,
    ACI_SCWB_FACTOR, ACI_VC_COEFF, ACI_VC_ZERO_AXIAL_DIVISOR,
    ASCE41_A_AXIAL_CAP, ASCE41_A_AXIAL_COEFF, ASCE41_A_INTERCEPT,
    ASCE41_A_RHOT_COEFF, ASCE41_A_VRATIO_COEFF,
    ASCE41_B_DENOM_AXIAL_DIV, ASCE41_B_DENOM_INTERCEPT,
    ASCE41_B_NUMERATOR, ASCE41_B_SUBTRACTION,
    ASCE41_C_AXIAL_COEFF, ASCE41_C_INTERCEPT,
    ASCE41_THETA_IO_FACTOR, ASCE41_THETA_IO_MAX,
    ASCE41_THETA_LS_FACTOR, ASCE41_THETA_CP_FACTOR,
    ASCE41_FYE_DEFAULT, ASCE41_FYTE_DEFAULT,
)
from constants import ACI_RHO_LONG_MAX_SMF
from frame_types import GRAVITY, IMF, OMF, SMF, frame_class

# ── Unicode font ──────────────────────────────────────────────────────────────
def _register_fonts() -> tuple[str, str]:
    try:
        _ttf = Path(matplotlib.get_data_path()) / 'fonts' / 'ttf'
        pdfmetrics.registerFont(TTFont('DVSans',      str(_ttf / 'DejaVuSans.ttf')))
        pdfmetrics.registerFont(TTFont('DVSans-Bold', str(_ttf / 'DejaVuSans-Bold.ttf')))
        pdfmetrics.registerFontFamily('DVSans', normal='DVSans', bold='DVSans-Bold')
        return 'DVSans', 'DVSans-Bold'
    except Exception:
        return 'Helvetica', 'Helvetica-Bold'

_FONT, _FONT_BOLD = _register_fonts()

# ── page geometry ──────────────────────────────────────────────────────────────
_W, _H   = A4
_MARGIN  = 18 * mm
_INNER_W = _W - 2 * _MARGIN

# ── colours ────────────────────────────────────────────────────────────────────
_BLACK   = colors.HexColor('#1a1a1a')
_GRAY    = colors.HexColor('#555555')
_LGRAY   = colors.HexColor('#f4f4f4')
_MGRAY   = colors.HexColor('#cccccc')
_DGRAY   = colors.HexColor('#888888')
_HDR_BG  = colors.HexColor('#2d2d2d')
_SEC_BG  = colors.HexColor('#e8f0f8')
_SEC_LN  = colors.HexColor('#3a6ea5')

# ── styles ─────────────────────────────────────────────────────────────────────
_BASE = getSampleStyleSheet()

_S_TITLE = ParagraphStyle('DTitle', parent=_BASE['Normal'],
    fontSize=13, fontName=_FONT_BOLD, textColor=_BLACK,
    spaceAfter=1*mm, spaceBefore=0)
_S_SUBTITLE = ParagraphStyle('DSubtitle', parent=_BASE['Normal'],
    fontSize=9, fontName=_FONT, textColor=_GRAY,
    spaceAfter=3*mm, spaceBefore=0)
_S_H2 = ParagraphStyle('DH2', parent=_BASE['Normal'],
    fontSize=9.5, fontName=_FONT_BOLD, textColor=colors.white,
    spaceAfter=0, spaceBefore=0, leftIndent=2*mm)
_S_H3 = ParagraphStyle('DH3', parent=_BASE['Normal'],
    fontSize=8.5, fontName=_FONT_BOLD, textColor=_SEC_LN,
    spaceAfter=1*mm, spaceBefore=3*mm)
_S_BODY = ParagraphStyle('DBody', parent=_BASE['Normal'],
    fontSize=7.5, fontName=_FONT, textColor=_BLACK,
    spaceAfter=1*mm, leading=10)
_S_NOTE = ParagraphStyle('DNote', parent=_BASE['Normal'],
    fontSize=6.5, fontName=_FONT, textColor=_DGRAY,
    spaceAfter=1*mm, leading=8.5, leftIndent=4*mm)
# equation styles
_S_EQ_FORMULA = ParagraphStyle('DEqFormula', parent=_BASE['Normal'],
    fontSize=8, fontName=_FONT, textColor=_BLACK,
    spaceAfter=0, leading=10, leftIndent=4*mm)
_S_EQ_SUBST = ParagraphStyle('DEqSubst', parent=_BASE['Normal'],
    fontSize=7.5, fontName=_FONT, textColor=_GRAY,
    spaceAfter=0, leading=9.5, leftIndent=12*mm)
_S_EQ_RESULT = ParagraphStyle('DEqResult', parent=_BASE['Normal'],
    fontSize=8, fontName=_FONT_BOLD, textColor=_BLACK,
    spaceAfter=2*mm, leading=10, leftIndent=12*mm)
_S_REF = ParagraphStyle('DRef', parent=_BASE['Normal'],
    fontSize=6.5, fontName=_FONT, textColor=_SEC_LN,
    alignment=2)   # right-aligned
_S_CELL = ParagraphStyle('DCell', parent=_BASE['Normal'],
    fontSize=7, leading=9, fontName=_FONT)
_S_CELL_B = ParagraphStyle('DCellB', parent=_BASE['Normal'],
    fontSize=7, leading=9, fontName=_FONT_BOLD, textColor=colors.white)
_S_SMALL = ParagraphStyle('DSmall', parent=_BASE['Normal'],
    fontSize=6.5, leading=8, textColor=_DGRAY)


# ── formatting helpers ─────────────────────────────────────────────────────────

def _f(v: object, nd: int = 2) -> str:
    try:
        return f'{float(v):,.{nd}f}'
    except Exception:
        return str(v)


def _section_header(title: str) -> list:
    """Dark navy band acting as a section heading."""
    tbl = Table([[Paragraph(title, _S_H2)]], colWidths=[_INNER_W])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), _HDR_BG),
        ('TOPPADDING',    (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
    ]))
    return [tbl, Spacer(1, 2*mm)]


def _kv_table(rows: list[tuple[str, str]]) -> Table:
    """Simple two-column key-value table."""
    data = [[Paragraph(k, _S_CELL), Paragraph(v, _S_CELL)] for k, v in rows]
    tbl = Table(data, colWidths=[70*mm, _INNER_W - 70*mm])
    tbl.setStyle(TableStyle([
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, _LGRAY]),
        ('GRID',    (0, 0), (-1, -1), 0.3, _MGRAY),
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING',   (0, 0), (-1, -1), 3),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 3),
    ]))
    return tbl


def _eq_block(formula: str, substitution: str, result: str, ref: str = '',
              note: str = '') -> list:
    """
    One calculation step:
      formula     — symbolic equation  e.g. 'Ag = b · h'
      substitution— values substituted e.g. '= 400 × 400 mm'
      result      — bold final value   e.g. '= 160,000 mm²'
      ref         — code clause shown on the right
    """
    # ref label (right-aligned) + formula on same row via a 2-col table
    ref_p = Paragraph(ref, _S_REF) if ref else Paragraph('', _S_REF)
    row1 = Table(
        [[Paragraph(formula, _S_EQ_FORMULA), ref_p]],
        colWidths=[_INNER_W - 30*mm, 30*mm],
    )
    row1.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    out = [row1]
    if substitution:
        out.append(Paragraph(substitution, _S_EQ_SUBST))
    out.append(Paragraph(result, _S_EQ_RESULT))
    if note:
        out.append(Paragraph(f'Note: {note}', _S_NOTE))
    out.append(Spacer(1, 1*mm))
    return out


def _check_line(label: str, provided: str, required: str, ok: bool) -> list:
    status = 'OK ✓' if ok else 'NG ✗'
    colour = '#1a7a1a' if ok else '#cc0000'
    text = (f'<b>{label}</b>: provided = {provided}, required {required} '
            f'→ <font color="{colour}"><b>{status}</b></font>')
    return [Paragraph(text, _S_BODY)]


# ── beta1 helper ───────────────────────────────────────────────────────────────

def _beta1(fc: float) -> float:
    if fc <= ACI_BETA1_FC_PIVOT:
        return ACI_BETA1_MAX
    val = ACI_BETA1_MAX - ACI_BETA1_SLOPE * ((fc - ACI_BETA1_FC_PIVOT) / ACI_BETA1_FC_STEP)
    return max(ACI_BETA1_MIN, min(ACI_BETA1_MAX, val))


# ── SECTION BUILDERS ──────────────────────────────────────────────────────────

def _s1_input(row: dict, section_png: str) -> list:
    story = _section_header('1  |  Input Parameters')
    params = [
        ('Column ID', str(row['column_id'])),
        ('Story', str(row['story'])),
        ('Frame type', str(row['frame_type'])),
        ('Strength basis', 'Expected (ASCE 41: fce = {:.2f}·f\'c, fye = {:.2f}·fy, φ = 1.0)'.format(
            float(row.get('asce_fce_factor', 1.5)), float(row.get('asce_fye_factor', 1.25)))
         if str(row.get('analysis_type', 'linear')).lower().startswith('n')
         else 'Design (nominal materials, ACI φ factors)'),
        ('b — width [mm]', _f(row['b_mm'], 1)),
        ('h — depth [mm]', _f(row['h_mm'], 1)),
        ('Clear cover [mm]', _f(row['cover_mm'], 1)),
        ('Clear height ℓclear [mm]', _f(row['clear_height_mm'], 1)),
        ("f'c [MPa]", _f(row['fc_MPa'], 1)),
        ('fy longitudinal [MPa]', _f(row['fy_long_MPa'], 1)),
        ('fyt transverse [MPa]', _f(row['fy_trans_MPa'], 1)),
        ('Longitudinal bar db [mm]', _f(row['bar_db_mm'], 1)),
        ('Hoop/tie diameter dbt [mm]', _f(row['tie_db_mm'], 1)),
        ('Bars — top / bottom / left / right',
         '{}/{}/{}/{}'.format(int(row['n_bars_x_top']), int(row['n_bars_x_bottom']),
                              int(row['n_bars_y_left']), int(row['n_bars_y_right']))),
        ('Tie spacing within ℓo [mm]', _f(row['tie_spacing_lo_mm'], 1)),
        ('Tie spacing outside ℓo [mm]', _f(row['tie_spacing_outside_lo_mm'], 1)),
    ]
    _SKT_MAX_W, _SKT_MAX_H = 52*mm, 62*mm
    sketch: Any = Paragraph('(section not available)', _S_SMALL)
    if section_png and Path(section_png).exists():
        try:
            ir = ImageReader(section_png)
            iw, ih = ir.getSize()
            sc = min(_SKT_MAX_W / iw, _SKT_MAX_H / ih)
            sketch = Image(str(section_png), width=iw*sc, height=ih*sc)
        except Exception:
            pass
    tbl_params = _kv_table(params)
    _left_w  = 85 * mm
    _right_w = _INNER_W - _left_w
    layout = Table([[tbl_params, sketch]], colWidths=[_left_w, _right_w])
    layout.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(KeepTogether([layout, Spacer(1, 4*mm)]))
    return story


def _s2_geometry(row: dict, geom: dict) -> list:
    story = _section_header('2  |  Cross-Section Geometry')
    b  = float(row['b_mm'])
    h  = float(row['h_mm'])
    cv = float(row['cover_mm'])
    td = float(row['tie_db_mm'])
    bd = float(row['bar_db_mm'])
    Ag  = float(geom['Ag_mm2'])
    Ach = float(geom['Ach_mm2'])
    As  = float(geom['As_mm2'])
    n   = int(geom['n_perimeter_bars'])
    As1 = math.pi * bd**2 / 4.0
    off = cv + td + bd / 2.0

    story += [Paragraph('Gross section area', _S_H3)]
    story += _eq_block(
        'Ag = b · h',
        f'= {_f(b,0)} × {_f(h,0)} mm²',
        f'= <b>{_f(Ag,0)} mm²</b>',
        'Geometry',
    )

    story += [Paragraph('Confined core area (to hoop centreline — ACI R18.7.5.4)', _S_H3)]
    bch = b - 2*(cv + td/2)
    hch = h - 2*(cv + td/2)
    story += _eq_block(
        'bc = b − 2·(cover + dbt/2)',
        f'= {_f(b,0)} − 2·({_f(cv,0)} + {_f(td/2,1)}) = {_f(bch,1)} mm',
        '',
        '',
    )
    story += _eq_block(
        'hc = h − 2·(cover + dbt/2)',
        f'= {_f(h,0)} − 2·({_f(cv,0)} + {_f(td/2,1)}) = {_f(hch,1)} mm',
        '',
        '',
    )
    story += _eq_block(
        'Ach = bc · hc',
        f'= {_f(bch,1)} × {_f(hch,1)}',
        f'= <b>{_f(Ach,0)} mm²</b>',
        'ACI R18.7.5.4',
    )

    story += [Paragraph('Longitudinal steel area', _S_H3)]
    story += _eq_block(
        'Abar = π · db² / 4',
        f'= π × {_f(bd,0)}² / 4',
        f'= {_f(As1,1)} mm²  per bar',
        'ACI 20.2.1',
    )
    story += _eq_block(
        f'As = n_bars · Abar  (n = {n})',
        f'= {n} × {_f(As1,1)}',
        f'= <b>{_f(As,1)} mm²</b>',
        'Geometry',
    )

    story += [Paragraph('Longitudinal reinforcement ratio', _S_H3)]
    rho = float(geom['rho_long'])
    _fclass = frame_class(row)
    if _fclass in (SMF, GRAVITY):
        rho_lim_txt = f'0.01 ≤ ρ ≤ {ACI_RHO_LONG_MAX_SMF}'
        rho_ref = 'ACI 18.7.4.1' if _fclass == SMF else 'ACI 18.14.3.2(b) / 18.7.4.1'
    else:
        rho_lim_txt = '0.01 ≤ ρ ≤ 0.08'
        rho_ref = 'ACI 10.6.1.1'
    story += _eq_block(
        'ρ_long = As / Ag',
        f'= {_f(As,1)} / {_f(Ag,0)}',
        f'= <b>{rho:.5f}</b>  ({rho_ref} requires {rho_lim_txt})',
        rho_ref,
        note=f'Longitudinal bar offset from outer face: d\' = cover + dbt + db/2 = {_f(off,1)} mm',
    )

    story += [Paragraph('Bar centerline offset (d\')', _S_H3)]
    story += _eq_block(
        "d' = cover + dbt + db/2",
        f'= {_f(cv,0)} + {_f(td,0)} + {_f(bd/2,1)}',
        f"= <b>{_f(off,1)} mm</b>  (centroid of outermost bar layer from face)",
        'Geometry',
    )

    story += [Paragraph('Maximum unsupported bar spacing hx', _S_H3)]
    hx = float(geom['hx_mm'])
    n_sup = int(geom['n_lateral_supported_bars'])
    story += [Paragraph(
        f'hx = maximum clear gap between consecutively supported longitudinal bars '
        f'across all four faces.<br/>'
        f'Laterally supported bars: {n_sup} of {n}. '
        f'<b>hx = {_f(hx,1)} mm</b> (limit ≤ {ACI_HX_GENERAL_MM:.0f} mm per ACI 18.7.5.2(e)).',
        _S_BODY,
    )]
    story.append(Spacer(1, 3*mm))
    return story


def _s3_axial(row: dict, geom: dict, axial: dict) -> list:
    story = _section_header('3  |  Axial Capacity  —  ACI 22.4.2')
    expected = str(row.get('analysis_type', 'linear')).lower().startswith('n')
    fce_f = float(row.get('asce_fce_factor', 1.5)) if expected else 1.0
    fye_f = float(row.get('asce_fye_factor', 1.25)) if expected else 1.0
    fc  = float(row['fc_MPa']) * fce_f
    fy  = float(row['fy_long_MPa']) * fye_f
    Ag  = float(geom['Ag_mm2'])
    As  = float(geom['As_mm2'])
    Pn0 = float(axial['Pn0_kN'])
    phi = float(axial.get('phi_axial', ACI_PHI_COMPRESSION))

    if expected:
        story += [Paragraph(
            f"Expected-strength basis (nonlinear analysis): f'ce = {fce_f:.2f}·f'c = {_f(fc,1)} MPa, "
            f'fye = {fye_f:.2f}·fy = {_f(fy,0)} MPa, φ = 1.0 (ASCE 41 §10.2.2 / Table 10-1).',
            _S_BODY,
        )]
    story += [Paragraph('Concentric axial capacity', _S_H3)]
    Cc_term = ACI_ALPHA1 * fc * (Ag - As)
    Cs_term = fy * As
    story += _eq_block(
        'Pn0 = α₁·f\'c·(Ag − As) + fy·As        (α₁ = 0.85)',
        f'= {ACI_ALPHA1} × {_f(fc,1)} × ({_f(Ag,0)} − {_f(As,1)}) + {_f(fy,0)} × {_f(As,1)}',
        f'= {_f(Cc_term/1e3,1)} + {_f(Cs_term/1e3,1)} = <b>{_f(Pn0,1)} kN</b>',
        'ACI 22.4.2.2',
    )

    story += [Paragraph('Design axial capacity', _S_H3)]
    story += _eq_block(
        f'φPn0 = φ · Pn0        (φ = {phi})',
        f'= {phi} × {_f(Pn0,1)}',
        f'= <b>{_f(axial["phiPn0_kN"],1)} kN</b>',
        'ASCE 41 expected strength' if expected else 'ACI Table 21.2.2',
    )
    story.append(Spacer(1, 3*mm))
    return story


def _s4_pm(row: dict, geom: dict, cases: list, flexure0: dict) -> list:
    story = _section_header('4  |  Flexural Capacity  —  P-M Interaction (Strain Compatibility)')

    fc = float(row['fc_MPa'])
    fy = float(row['fy_long_MPa'])
    h  = float(row['h_mm'])
    b  = float(row['b_mm'])
    b1 = _beta1(fc)

    story += [Paragraph(
        'The P-M interaction surface is computed by strain compatibility with the '
        'ACI Whitney equivalent rectangular stress block. The neutral axis depth c '
        'is varied parametrically; for each c the concrete and steel forces are '
        'integrated to give (Pn, Mn). The strength-reduction factor φ transitions '
        'from 0.65 (compression-controlled, εt ≤ εy) to 0.90 (tension-controlled, '
        f'εt ≥ εy + 0.003) per ACI 21.2.2.',
        _S_BODY,
    ), Spacer(1, 2*mm)]

    story += [Paragraph('Whitney stress block depth factor β₁', _S_H3)]
    if fc <= ACI_BETA1_FC_PIVOT:
        story += _eq_block(
            f"β₁ = {ACI_BETA1_MAX}    (f'c ≤ {ACI_BETA1_FC_PIVOT} MPa)",
            f"f'c = {_f(fc,1)} MPa ≤ {ACI_BETA1_FC_PIVOT} MPa  →  β₁ = {ACI_BETA1_MAX}",
            f'<b>β₁ = {_f(b1,4)}</b>',
            'ACI Table 22.2.2.4.3',
        )
    else:
        story += _eq_block(
            f"β₁ = {ACI_BETA1_MAX} − 0.05·(f'c − {ACI_BETA1_FC_PIVOT}) / {ACI_BETA1_FC_STEP}",
            f'= {ACI_BETA1_MAX} − 0.05 × ({_f(fc,1)} − {ACI_BETA1_FC_PIVOT}) / {ACI_BETA1_FC_STEP}',
            f'<b>β₁ = {_f(b1,4)}</b>  (bounded [{ACI_BETA1_MIN}, {ACI_BETA1_MAX}])',
            'ACI Table 22.2.2.4.3',
        )

    story += [Paragraph('Section response at a representative axial load', _S_H3)]
    # Pick representative case (max compression)
    rep = max(cases, key=lambda c: float(c['row']['Pu_kN']), default=None)
    if rep is None:
        story.append(Paragraph('No load cases available.', _S_BODY))
        return story

    cx = rep['col_x']
    Pu = float(rep['row']['Pu_kN'])
    c_pos = float(cx['c_pos_mm'])
    a_pos = min(b1 * c_pos, h)
    lc  = rep['row']['load_case']

    story.append(Paragraph(
        f'Load case: <b>{lc}</b>  |  Pu = {_f(Pu,1)} kN  '
        f'(compression-face = top, axis x)',
        _S_BODY,
    ))

    story += _eq_block(
        'a = β₁ · c     (depth of equivalent rectangular stress block)',
        f'= {_f(b1,4)} × {_f(c_pos,1)} mm',
        f'= <b>{_f(a_pos,1)} mm</b>',
        'ACI 22.2.2.4.1',
    )
    Cc = ACI_ALPHA1 * fc * b * a_pos / 1e3
    story += _eq_block(
        "Cc = α₁ · f'c · b · a    (resultant concrete compression force)",
        f"= {ACI_ALPHA1} × {_f(fc,1)} × {_f(b,0)} × {_f(a_pos,1)} / 1000",
        f'= <b>{_f(Cc,1)} kN</b>',
        'ACI 22.2.1.3',
    )

    story += [Paragraph(
        'For each bar i, the strain is computed from the linear strain diagram '
        '(εcu = 0.003 at the compression face), and the stress is bounded by ±fy:',
        _S_BODY,
    )]
    story += _eq_block(
        'εᵢ = εcu · (1 − dᵢ / c)',
        f'εcu = {ACI_ECU}   (ACI 22.2.2.1)',
        f'',
        'ACI 22.2.2',
        note='dᵢ = distance from compression face to bar i centroid. '
             'Negative εᵢ → tension bar.',
    )
    story += _eq_block(
        'fᵢ = Es · εᵢ  bounded by [−fy, +fy]',
        f'Es = {ACI_ES_MPA/1000:.0f} GPa (ACI 20.2.2.2)',
        '',
        'ACI 20.2.2.2',
    )
    story += _eq_block(
        'Pn = Cc + Σ (fᵢ · Aᵢ)  ;  Mn = |Cc · arm_c + Σ fᵢ · Aᵢ · armᵢ|',
        'Arms measured from section centroid',
        f'φMn,x (at Pu = {_f(Pu,1)} kN) = <b>{_f(cx["phiMn_kNm"],1)} kN·m</b>',
        'ACI 22.4.2',
    )

    story += [Paragraph('Probable flexural strength (for seismic demand)', _S_H3)]
    story += [Paragraph(
        f'Mpr is computed with fye = {ACI_FYE_FACTOR}·fy = {_f(ACI_FYE_FACTOR*float(row["fy_long_MPa"]),0)} MPa '
        f'(ACI 18.6.5 / R18.7.6) and φ = 1.0.',
        _S_BODY,
    )]
    story += _eq_block(
        'fye = 1.25 · fy',
        f'= 1.25 × {_f(fy,0)}',
        f'= <b>{_f(1.25*fy,0)} MPa</b>',
        'ACI 18.6.5',
    )
    story.append(Paragraph(
        f'Mpr,x (at Pu = {_f(Pu,1)} kN) = <b>{_f(cx["Mpr_pos_kNm"],1)} kN·m</b>  '
        f'(compression face top)  |  '
        f'<b>{_f(cx["Mpr_neg_kNm"],1)} kN·m</b>  (compression face bottom)',
        _S_BODY,
    ))
    story.append(Spacer(1, 3*mm))
    return story


def _s5_shear(row: dict, geom: dict, shear_base: dict, cases: list) -> list:
    story = _section_header('5  |  Shear Capacity  —  ACI 22.5 / 18.7.6')
    fc  = float(row['fc_MPa'])
    fyt = float(row['fy_trans_MPa'])
    b   = float(row['b_mm'])
    h   = float(row['h_mm'])
    cv  = float(row['cover_mm'])
    s   = float(row['tie_spacing_lo_mm'])
    phi = ACI_PHI_SHEAR
    d_x = h - cv
    d_y = b - cv
    Av_x = float(shear_base['Av_x_mm2'])
    Av_y = float(shear_base['Av_y_mm2'])
    Vc_x = float(shear_base['Vc_x_kN'])
    Vc_y = float(shear_base['Vc_y_kN'])
    Vs_x = float(shear_base['Vs_x_kN'])
    Vs_y = float(shear_base['Vs_y_kN'])

    story += [Paragraph(
        'Simplified Vc equation (ACI 22.5.5.1). '
        'For shear capacity d is taken conservatively as h − cover (no stirrup diameter subtracted).',
        _S_BODY,
    )]

    story += [Paragraph('Effective shear depths', _S_H3)]
    story += _eq_block(
        'd_x = h − cover   (effective depth for bending about x-axis)',
        f'= {_f(h,0)} − {_f(cv,0)}',
        f'= <b>{_f(d_x,0)} mm</b>',
        'Geometry',
    )
    story += _eq_block(
        'd_y = b − cover   (effective depth for bending about y-axis)',
        f'= {_f(b,0)} − {_f(cv,0)}',
        f'= <b>{_f(d_y,0)} mm</b>',
        'Geometry',
    )

    story += [Paragraph('Concrete shear contribution Vc', _S_H3)]
    story += _eq_block(
        "Vc,x = 0.17 · √f'c · b · d_x",
        f'= 0.17 × √{_f(fc,1)} × {_f(b,0)} × {_f(d_x,0)} / 1000',
        f'= <b>{_f(Vc_x,1)} kN</b>',
        'ACI 22.5.5.1',
    )
    story += _eq_block(
        "Vc,y = 0.17 · √f'c · h · d_y",
        f'= 0.17 × √{_f(fc,1)} × {_f(h,0)} × {_f(d_y,0)} / 1000',
        f'= <b>{_f(Vc_y,1)} kN</b>',
        'ACI 22.5.5.1',
    )

    story += [Paragraph('Steel shear contribution Vs', _S_H3)]
    n_top  = int(geom['n_supported_top'])
    n_left = int(geom['n_supported_left'])
    story += [Paragraph(
        f'Av,x = legs on top face × Atbar = {n_top} × {_f(Av_x/n_top if n_top else 0,1)} = {_f(Av_x,1)} mm²/set.  '
        f'Av,y = {n_left} × {_f(Av_y/n_left if n_left else 0,1)} = {_f(Av_y,1)} mm²/set.',
        _S_BODY,
    )]
    story += _eq_block(
        'Vs,x = Av,x · fyt · d_x / s',
        f'= {_f(Av_x,1)} × {_f(fyt,0)} × {_f(d_x,0)} / {_f(s,0)} / 1000',
        f'= <b>{_f(Vs_x,1)} kN</b>',
        'ACI 22.5.8.5.3',
    )
    story += _eq_block(
        'Vs,y = Av,y · fyt · d_y / s',
        f'= {_f(Av_y,1)} × {_f(fyt,0)} × {_f(d_y,0)} / {_f(s,0)} / 1000',
        f'= <b>{_f(Vs_y,1)} kN</b>',
        'ACI 22.5.8.5.3',
    )

    story += [Paragraph('Design shear strength', _S_H3)]
    story += _eq_block(
        f'φVn,x = φ · (Vc,x + Vs,x)   (φ = {phi})',
        f'= {phi} × ({_f(Vc_x,1)} + {_f(Vs_x,1)})',
        f'= <b>{_f(shear_base["phiVn_x_kN"],1)} kN</b>',
        'ACI Table 21.2.1(c)',
    )
    story += _eq_block(
        f'φVn,y = φ · (Vc,y + Vs,y)',
        f'= {phi} × ({_f(Vc_y,1)} + {_f(Vs_y,1)})',
        f'= <b>{_f(shear_base["phiVn_y_kN"],1)} kN</b>',
        'ACI Table 21.2.1(c)',
    )

    _fclass = frame_class(row)
    if _fclass in (SMF, GRAVITY):
        story += [Paragraph('ACI 18.7.6.2.1 — Vc = 0 rule', _S_H3)]
        story += [Paragraph(
            "Vc shall be taken as zero when both conditions (a) and (b) apply:<br/>"
            f"(a) The earthquake-induced shear Ve ≥ 0.5·Vu_design;<br/>"
            f"(b) Pu,factored &lt; Ag·f'c / {ACI_VC_ZERO_AXIAL_DIVISOR:.0f}.",
            _S_BODY,
        )]
    else:
        story += [Paragraph(
            'The Vc = 0 rule (ACI 18.7.6.2.1) applies to SMF and gravity columns only; '
            'it is not invoked by ACI 18.3 (OMF) or 18.4 (IMF).',
            _S_NOTE,
        )]

    rep = max(cases, key=lambda c: float(c['row']['Pu_kN']), default=None)
    if rep:
        ps = rep['prob_shear']
        if _fclass in (SMF, GRAVITY):
            story += [Paragraph('Probable seismic shear (Ve) — representative case', _S_H3)]
            story += _eq_block(
                'Ve = (Mpr,top + Mpr,bot) / ℓu',
                f'= ({_f(ps["col_Mpr_top_x_eff_kNm"],1)} + {_f(ps["col_Mpr_bot_x_eff_kNm"],1)}) / {_f(ps["lu_m"],2)} m',
                f'= <b>{_f(ps["Ve_col_x_kN"],1)} kN</b>  (axis x)',
                'ACI 18.7.6.1',
                note='Mpr values are limited by connected beam joint Mpr when beams are present.',
            )
        else:
            ve_ref = 'ACI 18.4.3.1(a)' if _fclass == IMF else 'ACI 18.3.3(a)'
            story += [Paragraph('Nominal-strength hinging shear (Ve) — representative case', _S_H3)]
            story += _eq_block(
                'Ve = (Mn,top + Mn,bot) / ℓu',
                f'= ({_f(ps["col_Mn_top_x_kNm"],1)} + {_f(ps["col_Mn_bot_x_kNm"],1)}) / {_f(ps["lu_m"],2)} m',
                f'= <b>{_f(ps["Ve_col_Mn_x_kN"],1)} kN</b>  (axis x)',
                ve_ref,
                note='OMF: required only for columns with lu ≤ 5·c1 (ACI 18.3.3).' if _fclass == OMF else '',
            )

    story.append(Spacer(1, 3*mm))
    return story


def _s6_confinement(row: dict, geom: dict, tr_meta: dict) -> list:
    branch = str(tr_meta.get('frame_branch', 'SMF'))
    if branch == 'OMF':
        story = _section_header('6  |  Tie Spacing  —  ACI 25.7.2 (Ordinary Moment Frame)')
        smax = float(tr_meta['smax_lo_mm'])
        s_lo = float(row['tie_spacing_lo_mm'])
        s_out = float(row['tie_spacing_outside_lo_mm'])
        story += [Paragraph(
            'OMF columns have no Chapter 18 confinement region; ties follow the general '
            'Chapter 10 / 25.7.2 rules over the full height: s ≤ min(16db, 48dbt, least dimension).',
            _S_BODY,
        )]
        story += _check_line('Tie spacing (end regions)', f's = {_f(s_lo,0)} mm', f'≤ {_f(smax,0)} mm', s_lo <= smax)
        story += _check_line('Tie spacing (mid-height)', f's = {_f(s_out,0)} mm', f'≤ {_f(smax,0)} mm', s_out <= smax)
        story.append(Spacer(1, 3*mm))
        return story
    if branch == 'IMF':
        story = _section_header('6  |  Hoop Region ℓo and Spacing  —  ACI 18.4.3.3 (Intermediate Moment Frame)')
        lo = float(tr_meta['lo_x_mm'])
        smax_lo = float(tr_meta['smax_lo_mm'])
        smax_out = float(tr_meta['smax_outside_lo_mm'])
        s_lo = float(row['tie_spacing_lo_mm'])
        s_out = float(row['tie_spacing_outside_lo_mm'])
        fyl = float(row['fy_long_MPa'])
        db = float(row['bar_db_mm'])
        grade_txt = f'min(8db = {_f(8*db,0)}, 200)' if fyl <= 420.0 else f'min(6db = {_f(6*db,0)}, 150)'
        story += _eq_block(
            'ℓo = max(ℓclear/6, max(b, h), 450 mm)',
            f"= max({_f(float(row['clear_height_mm'])/6,0)}, {_f(max(float(row['b_mm']), float(row['h_mm'])),0)}, 450)",
            f'= <b>{_f(lo,0)} mm</b>',
            'ACI 18.4.3.3(d)-(f)',
        )
        story += [Paragraph(
            f'Hoop spacing within ℓo: so ≤ min({grade_txt}, min_dim/2) = <b>{_f(smax_lo,0)} mm</b>.',
            _S_BODY,
        )]
        story += _check_line('Spacing within ℓo', f's = {_f(s_lo,0)} mm', f'≤ {_f(smax_lo,0)} mm', s_lo <= smax_lo)
        story += _check_line(
            'Spacing outside ℓo', f's = {_f(s_out,0)} mm',
            f'≤ {_f(smax_out,0)} mm  (Table 10.7.6.5.2 / 25.7.2.1)',
            s_out <= smax_out,
        )
        story.append(Spacer(1, 3*mm))
        return story

    story = _section_header('6  |  Confinement Region ℓo and Tie Spacing  —  ACI 18.7.5')
    b   = float(row['b_mm'])
    h   = float(row['h_mm'])
    lch = float(row['clear_height_mm'])
    db  = float(row['bar_db_mm'])
    fyl = float(row['fy_long_MPa'])
    hx  = float(geom['hx_mm'])
    lo_x = float(tr_meta['lo_x_mm'])
    lo_y = float(tr_meta['lo_y_mm'])
    so  = float(tr_meta['so_eq_mm'])
    s_lo = float(row['tie_spacing_lo_mm'])
    s_out = float(row['tie_spacing_outside_lo_mm'])
    min_dim = min(b, h)
    db_limit = 6*db if fyl <= 420.0 else 5*db
    smax_lo = float(tr_meta.get('smax_lo_mm', min(min_dim/4, db_limit, so)))

    story += [Paragraph('Special confinement length ℓo (measured from each joint face)', _S_H3)]
    story += _eq_block(
        'ℓo = max(h, ℓclear / 6, 450 mm)',
        f'max({_f(h,0)}, {_f(lch,0)}/6 = {_f(lch/6,0)}, 450)',
        f'= <b>{_f(lo_x,0)} mm</b>',
        'ACI 18.7.5.1',
    )

    story += [Paragraph('Equivalent maximum tie spacing so (within ℓo)', _S_H3)]
    story += _eq_block(
        'so = 100 + (350 − hx) / 3',
        f'= 100 + (350 − {_f(hx,1)}) / 3',
        f'= {_f(100 + (350-hx)/3,1)} mm  →  bounded [100, 150] mm  →  <b>{_f(so,0)} mm</b>',
        'ACI 18.7.5.3',
    )

    story += [Paragraph('Maximum tie spacing within ℓo', _S_H3)]
    story += [Paragraph(
        f'smax,lo = min(min_dim/4, {int(6 if fyl<=420 else 5)}·db, so)'
        f' = min({_f(min_dim/4,0)}, {_f(db_limit,0)}, {_f(so,0)}) = <b>{_f(smax_lo,0)} mm</b>',
        _S_BODY,
    )]
    story += _check_line(
        'Spacing within ℓo', f's = {_f(s_lo,0)} mm',
        f'≤ {_f(smax_lo,0)} mm',
        s_lo <= smax_lo,
    )

    story += [Paragraph('Maximum tie spacing outside ℓo', _S_H3)]
    smax_out = float(tr_meta.get('smax_outside_lo_mm', min(150.0, db_limit)))
    story += _check_line(
        'Spacing outside ℓo', f's = {_f(s_out,0)} mm',
        f'≤ {_f(smax_out,0)} mm  (min(150, {int(6 if fyl<=420 else 5)}·db))',
        s_out <= smax_out,
    )
    story.append(Spacer(1, 3*mm))
    return story


def _s7_rhos(row: dict, geom: dict, tr_meta: dict, cases: list) -> list:
    branch = str(tr_meta.get('frame_branch', 'SMF'))
    if branch in ('IMF', 'OMF'):
        story = _section_header('7  |  Minimum Transverse Reinforcement  —  ACI Table 18.7.5.4')
        story += [Paragraph(
            f'Not required for {branch} columns. The Table 18.7.5.4 minimum transverse '
            'reinforcement ratio applies to columns of special moment frames (18.7.5.4) '
            'and, at half the (a)/(b) amounts, to gravity columns with Pu &gt; 0.35Po '
            '(18.14.3.2(c)). '
            + ('IMF columns are governed by the hoop spacing rules of 18.4.3.3 shown in Section 6.'
               if branch == 'IMF' else
               'OMF columns are governed by the general tie rules of 25.7.2 shown in Section 6.'),
            _S_BODY,
        ), Spacer(1, 3*mm)]
        return story

    story = _section_header('7  |  Minimum Transverse Reinforcement  —  ACI Table 18.7.5.4')
    fc   = float(row['fc_MPa'])
    fyt  = float(row['fy_trans_MPa'])
    Ag   = float(geom['Ag_mm2'])
    Ach  = float(geom['Ach_mm2'])
    # prop_row has no Pu — use max compression from load cases
    _rep_pu = max((float(c['row']['Pu_kN']) for c in cases), default=0.0) if cases else 0.0
    Pu_N = max(_rep_pu, 0.0) * 1e3
    kf   = float(tr_meta['kf'])
    kn   = float(tr_meta['kn'])
    ns   = int(geom['n_lateral_supported_bars'])
    rho_req = float(tr_meta['rho_s_req'])
    rho_x   = float(tr_meta['rho_s_x'])
    rho_y   = float(tr_meta['rho_s_y'])

    story += [Paragraph(
        'ACI Table 18.7.5.4 requires the volumetric transverse reinforcement ratio '
        'ρs to satisfy three expressions (a), (b), and (c) for rectangular sections. '
        'The governing value is ρs,req = max(a, b, c).',
        _S_BODY,
    ), Spacer(1, 2*mm)]

    story += [Paragraph('kf — concrete strength modification factor', _S_H3)]
    story += _eq_block(
        "kf = max(f'c / 175 + 0.6,  1.0)",
        f'= max({_f(fc,1)}/175 + 0.6, 1.0) = max({_f(fc/175+0.6,4)}, 1.0)',
        f'= <b>{_f(kf,4)}</b>',
        'ACI Table 18.7.5.4',
    )

    story += [Paragraph('kn — leg efficiency factor', _S_H3)]
    story += _eq_block(
        'kn = nl / (nl − 2)    (nl = number of laterally supported bars)',
        f'nl = {ns}  →  kn = {ns} / ({ns} − 2)',
        f'= <b>{_f(kn,4)}</b>',
        'ACI Table 18.7.5.4',
    )

    expr_a = ACI_RHO_S_RECT_A * max(Ag/max(Ach,1e-9)-1, 0) * (fc/max(fyt,1e-9))
    expr_b = ACI_RHO_S_RECT_B * (fc/max(fyt,1e-9))
    expr_c = ACI_RHO_S_RECT_C * kf * kn * Pu_N / max(fyt*Ach, 1e-9)

    story += [Paragraph('Expression (a)', _S_H3)]
    story += _eq_block(
        "ρs,(a) = 0.3·(Ag/Ach − 1)·(f'c/fyt)",
        f"= 0.3×({_f(Ag,0)}/{_f(Ach,0)}−1)×({_f(fc,1)}/{_f(fyt,0)})",
        f'= <b>{expr_a:.6f}</b>',
        'ACI Table 18.7.5.4(a)',
    )

    story += [Paragraph('Expression (b)', _S_H3)]
    story += _eq_block(
        "ρs,(b) = 0.09·(f'c/fyt)",
        f"= 0.09×({_f(fc,1)}/{_f(fyt,0)})",
        f'= <b>{expr_b:.6f}</b>',
        'ACI Table 18.7.5.4(b)',
    )

    story += [Paragraph('Expression (c)  [triggered only when Pu > 0.3·Ag·f\'c or f\'c > 70 MPa]',
                        _S_H3)]
    story += _eq_block(
        "ρs,(c) = 0.2·kf·kn·Pu / (fyt·Ach)",
        f"= 0.2×{_f(kf,4)}×{_f(kn,4)}×{_f(Pu_N/1e3,1)}kN×1000 / ({_f(fyt,0)}×{_f(Ach,0)})",
        f'= <b>{expr_c:.6f}</b>',
        'ACI Table 18.7.5.4(c)',
    )

    story += [Paragraph('Governing required ratio', _S_H3)]
    story += _eq_block(
        'ρs,req = max(ρs,(a), ρs,(b), ρs,(c))',
        f'= max({expr_a:.6f}, {expr_b:.6f}, {expr_c:.6f})',
        f'= <b>{rho_req:.6f}</b>',
        'ACI Table 18.7.5.4',
    )
    story += _check_line('ρs about x', f'{rho_x:.6f}', f'≥ {rho_req:.6f}', rho_x >= rho_req)
    story += _check_line('ρs about y', f'{rho_y:.6f}', f'≥ {rho_req:.6f}', rho_y >= rho_req)
    story.append(Spacer(1, 3*mm))
    return story


def _s8_scwb(row: dict, cases: list) -> list:
    story = _section_header('8  |  Strong Column – Weak Beam  —  ACI 18.7.3.2')
    _fclass = frame_class(row)
    if _fclass != SMF:
        label = {IMF: 'intermediate moment frames (ACI 18.4)',
                 OMF: 'ordinary moment frames (ACI 18.3)',
                 GRAVITY: 'members not designated as part of the SFRS (ACI 18.14)'}[_fclass]
        story += [Paragraph(
            f'Not required. The strong-column/weak-beam provision (18.7.3.2) applies only to '
            f'columns of special moment frames; this column belongs to {label}.',
            _S_BODY,
        ), Spacer(1, 3*mm)]
        return story
    story += [Paragraph(
        'ACI 18.7.3.2 requires that at each beam-column joint the sum of the nominal '
        'flexural strengths of the columns exceeds the sum of the nominal flexural '
        'strengths of the beams framing into that joint, multiplied by 1.2:',
        _S_BODY,
    )]
    story += _eq_block(
        'ΣMnc ≥ (6/5) · ΣMnb',
        '(sum of column Mnc at joint above + below) ≥ 1.2 × (sum of beam Mn at joint)',
        '',
        'ACI 18.7.3.2',
    )

    rep = max(cases, key=lambda c: float(c['row']['Pu_kN']), default=None)
    if rep:
        scwb = rep['scwb']
        for joint in ['top', 'bottom']:
            for axis in ['x', 'y']:
                key = f'scwb_{joint}_{axis}'
                this  = float(scwb.get(f'{key}_this_col_mnc_kNm', 0.0))
                other = float(scwb.get(f'{key}_other_col_mnc_kNm', 0.0))
                sumC  = float(scwb.get(f'{key}_sum_mnc_kNm', 0.0))
                sumB  = float(scwb.get(f'{key}_sum_mnb_kNm', 0.0))
                ratio = float(scwb.get(f'{key}_ratio', 0.0))
                if sumB < 0.01:
                    continue
                req = ACI_SCWB_FACTOR * sumB
                story += [Paragraph(f'<b>{joint.capitalize()} joint — axis {axis}</b>',
                                    _S_H3)]
                story += _eq_block(
                    f'ΣMnc = Mnc (this) + Mnc (adjacent col)',
                    f'= {_f(this,1)} + {_f(other,1)} kN·m',
                    f'= {_f(sumC,1)} kN·m',
                    'ACI 18.7.3.2',
                )
                story += _eq_block(
                    f'Required = 1.2 · ΣMnb = 1.2 × {_f(sumB,1)}',
                    '',
                    f'= {_f(req,1)} kN·m',
                    '',
                )
                story += _check_line(
                    f'SCWB {joint}-{axis}',
                    f'ΣMnc = {_f(sumC,1)} kN·m',
                    f'≥ {_f(req,1)} kN·m  (ratio = {ratio:.3f})',
                    ratio >= 1.0,
                )
    story.append(Spacer(1, 3*mm))
    return story


def _s9_joint(row: dict, joint_static: dict, cases: list, beam_static: dict) -> list:
    _fclass = frame_class(row)
    smf = _fclass == SMF
    phi_j = float(joint_static.get('phi_joint', ACI_PHI_JOINT))
    table_ref = str(joint_static.get('joint_table_ref', 'ACI Table 18.8.4.3'))
    phi_ref = str(joint_static.get('joint_phi_ref', 'ACI 21.2.4.4'))
    if smf:
        section_ref = 'ACI 18.8.4'
        T_sym, T_fy_txt = 'Tpr', '1.25fy'
        ve_sym_txt = 'Ve,col = (Mpr,top,eff + Mpr,bot,eff) / lu'
        demand_ref, ve_ref = 'ACI 18.8.2.1 / 18.8.4.1', 'ACI 18.7.6.1'
    else:
        section_ref = {IMF: 'ACI 18.4.4.7', OMF: 'ACI 18.3.4 / 15.5', GRAVITY: 'ACI 18.14.3.2(d) / 15.5'}[_fclass]
        T_sym, T_fy_txt = 'Tn', 'fy'
        ve_sym_txt = 'Ve,col = (Mn,top,eff + Mn,bot,eff) / lu'
        demand_ref = {IMF: 'ACI 18.4.4.7.2 / 18.3.4', OMF: 'ACI 18.3.4', GRAVITY: 'ACI 15.4.2.1(b)'}[_fclass]
        ve_ref = 'ACI 18.3.4'
    story = _section_header(f'9  |  Joint Shear Capacity & Demand  —  {section_ref}')
    story += [Paragraph(
        f'Capacity: Vn = αj · √f\'c · Aj  ({table_ref}, φ = {phi_j} per {phi_ref}).  '
        f'Demand: Vj = {T_sym},beams − Ve,col  ({demand_ref}).  '
        f'{T_sym} uses {T_fy_txt}; {ve_sym_txt}.',
        _S_BODY,
    ), Spacer(1, 2*mm)]

    fc  = float(row['fc_MPa'])
    fy  = float(row['fy_long_MPa'])
    any_active = False

    for joint in ['top', 'bottom']:
        for axis in ['x', 'y']:
            if not joint_static.get(f'joint_{joint}_{axis}_active', False):
                continue
            any_active = True

            coeff = float(joint_static[f'joint_{joint}_{axis}_coeff'])
            Aj    = float(joint_static[f'joint_{joint}_{axis}_Aj_mm2'])
            Vn    = float(joint_static[f'joint_{joint}_{axis}_Vn_kN'])
            pVn   = float(joint_static[f'joint_{joint}_{axis}_phiVn_kN'])
            conf  = bool(joint_static[f'joint_{joint}_{axis}_confined'])
            eff_w = float(joint_static[f'joint_{joint}_{axis}_eff_width_mm'])
            h_j   = float(joint_static[f'joint_{joint}_{axis}_h_joint_mm'])

            story += [Paragraph(
                f'<b>{joint.capitalize()} joint — axis {axis.upper()}</b>'
                f'  (confined: {"yes" if conf else "no"},  αj = {coeff})',
                _S_H3,
            )]

            # ── Capacity ─────────────────────────────────────────────────────
            story += [Paragraph('<b>Capacity</b>', _S_BODY)]
            story += _eq_block(
                'Aj = h_joint · beff    (effective joint area)',
                f'= {_f(h_j,0)} mm × {_f(eff_w,0)} mm',
                f'= <b>{_f(Aj,0)} mm²</b>',
                'ACI R15.4.2.4',
            )
            story += _eq_block(
                "Vn = αj · √f'c · Aj",
                f'= {coeff} × √{_f(fc,1)} × {_f(Aj,0)} / 1000',
                f'= <b>{_f(Vn,1)} kN</b>',
                table_ref,
            )
            story += _eq_block(
                f'φVn = {phi_j} · Vn',
                f'= {phi_j} × {_f(Vn,1)}',
                f'= <b>{_f(pVn,1)} kN</b>',
                phi_ref,
            )

            # ── Demand ───────────────────────────────────────────────────────
            # Joint tension is constant (depends only on beam geometry, not load)
            T_key = 'joint_Tpr' if smf else 'joint_Tn'
            T_val  = float(beam_static.get(f'beam_{joint}_{axis}_{T_key}_kN', 0.0))
            As_top = float(beam_static.get(f'beam_{joint}_{axis}_As_top_mm2', 0.0))
            As_bot = float(beam_static.get(f'beam_{joint}_{axis}_As_bot_mm2', 0.0))
            fy_factor_txt = '1.25' if smf else '1.0'

            valid_cases = [
                (i, c) for i, c in enumerate(cases)
                if f'joint_{joint}_{axis}_Vu_kN' in c.get('joint_case', {})
            ]
            if not valid_cases:
                continue

            crit_idx, crit_case = max(
                valid_cases,
                key=lambda ic: float(ic[1]['joint_case'].get(f'joint_{joint}_{axis}_Vu_kN', 0.0)),
            )
            crit_Vj = float(crit_case['joint_case'].get(f'joint_{joint}_{axis}_Vu_kN', 0.0))
            Ve_crit = float(crit_case['joint_case'].get(f'joint_{joint}_{axis}_Ve_col_kN', 0.0))
            if smf:
                M_top = float(crit_case['prob_shear'].get(f'col_Mpr_top_{axis}_eff_kNm', 0.0))
                M_bot = float(crit_case['prob_shear'].get(f'col_Mpr_bot_{axis}_eff_kNm', 0.0))
            else:
                M_top = float(crit_case['prob_shear'].get(f'col_Mn_top_{axis}_eff_kNm', 0.0))
                M_bot = float(crit_case['prob_shear'].get(f'col_Mn_bot_{axis}_eff_kNm', 0.0))
            lu_m    = float(crit_case['prob_shear'].get('lu_m', 1.0))
            Pu_crit = float(crit_case['row'].get('Pu_kN', 0.0))
            lc_name = str(crit_case['row'].get('load_case', ''))
            ratio_c = crit_Vj / max(pVn, 1e-9)

            story += [Spacer(1, 2*mm), Paragraph(
                f'<b>Demand  —  critical case: {lc_name}  (Pu = {_f(Pu_crit,1)} kN)</b>',
                _S_BODY,
            )]
            scen_a = float(beam_static.get(f'beam_{joint}_{axis}_{T_key}_scen_a_kN', 0.0))
            scen_b = float(beam_static.get(f'beam_{joint}_{axis}_{T_key}_scen_b_kN', 0.0))
            n_sides = int(beam_static.get(f'beam_{joint}_{axis}_n_active', 1))
            if n_sides == 2:
                story += _eq_block(
                    f'{T_sym} = max(T_neg,s1 + T_pos,s2 ; T_pos,s1 + T_neg,s2)    (critical seismic scenario)',
                    f'Scen. A (s1 hogs + s2 sags) = {_f(scen_a,1)} kN  |  Scen. B (s1 sags + s2 hogs) = {_f(scen_b,1)} kN',
                    f'= <b>{_f(T_val,1)} kN</b>',
                    demand_ref,
                )
            else:
                story += _eq_block(
                    f'{T_sym} = max(As,top, As,bot) × {T_fy_txt}    (one-sided joint, critical direction)',
                    f'= max({_f(As_top,0)}, {_f(As_bot,0)}) mm² × {fy_factor_txt} × {_f(fy,0)} / 1000',
                    f'= <b>{_f(T_val,1)} kN</b>',
                    demand_ref,
                )
            story += _eq_block(
                ve_sym_txt + ('    (column probable shear)' if smf else '    (column shear consistent with Mn)'),
                f'= ({_f(M_top,1)} + {_f(M_bot,1)}) kN·m / {_f(lu_m,3)} m',
                f'= <b>{_f(Ve_crit,1)} kN</b>',
                ve_ref,
            )
            story += _eq_block(
                f'Vj = {T_sym} − Ve,col',
                f'= {_f(T_val,1)} − {_f(Ve_crit,1)}',
                f'= <b>{_f(crit_Vj,1)} kN</b>',
                demand_ref,
            )
            story += _check_line(
                f'Joint {joint}-{axis}',
                f'Vj = {_f(crit_Vj,1)} kN',
                f'≤ φVn = {_f(pVn,1)} kN  (D/C = {ratio_c:.3f})',
                ratio_c <= 1.0,
            )

            # ── All-cases table ───────────────────────────────────────────────
            if len(cases) > 1:
                story += [Spacer(1, 2*mm), Paragraph('<b>All load cases</b>', _S_BODY)]
                cws = [_INNER_W / 7.0] * 7
                hdr_row = [
                    Paragraph('Case',        _S_CELL_B),
                    Paragraph('Pu [kN]',     _S_CELL_B),
                    Paragraph(f'{T_sym} [kN]', _S_CELL_B),
                    Paragraph('Ve,col [kN]', _S_CELL_B),
                    Paragraph('Vj [kN]',     _S_CELL_B),
                    Paragraph('φVn [kN]',    _S_CELL_B),
                    Paragraph('D/C',         _S_CELL_B),
                ]
                tbl_data = [hdr_row]
                crit_row_indices: list[int] = []
                for ci, c in enumerate(cases):
                    Vj_c  = float(c['joint_case'].get(f'joint_{joint}_{axis}_Vu_kN', 0.0))
                    Ve_c  = float(c['joint_case'].get(f'joint_{joint}_{axis}_Ve_col_kN', 0.0))
                    Tpr_c = float(c['joint_case'].get(f'joint_{joint}_{axis}_Tpr_kN', 0.0))
                    dc_c  = Vj_c / max(pVn, 1e-9)
                    is_c  = (ci == crit_idx)
                    if is_c:
                        crit_row_indices.append(ci + 1)  # +1 for header row
                    st = _S_CELL_B if is_c else _S_CELL
                    tbl_data.append([
                        Paragraph(str(c['row'].get('load_case', '')), st),
                        Paragraph(_f(c['row'].get('Pu_kN', 0.0), 1), st),
                        Paragraph(_f(Tpr_c, 1), st),
                        Paragraph(_f(Ve_c, 1), st),
                        Paragraph(_f(Vj_c, 1), st),
                        Paragraph(_f(pVn, 1), st),
                        Paragraph(_f(dc_c, 3), st),
                    ])
                ts = [
                    ('BACKGROUND',    (0, 0), (-1, 0),  _HDR_BG),
                    ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, _LGRAY]),
                    ('GRID',          (0, 0), (-1, -1), 0.3, _MGRAY),
                    ('TOPPADDING',    (0, 0), (-1, -1), 2),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                    ('LEFTPADDING',   (0, 0), (-1, -1), 3),
                    ('RIGHTPADDING',  (0, 0), (-1, -1), 3),
                ]
                for ri in crit_row_indices:
                    ts.append(('BACKGROUND', (0, ri), (-1, ri), _SEC_BG))
                tbl = Table(tbl_data, colWidths=cws)
                tbl.setStyle(TableStyle(ts))
                story += [tbl, Spacer(1, 2*mm)]

    if not any_active:
        story.append(Paragraph('No active beam-column joints in this model.', _S_BODY))
    story.append(Spacer(1, 3*mm))
    return story


def _s10_asce41(row: dict, geom: dict, cases: list) -> list:
    story = _section_header('10  |  ASCE 41 Plastic Rotation  —  Table 10-8')
    story += [Paragraph(
        'ASCE 41 Table 10-8 provides modelling parameters (a, b) and acceptance '
        'criteria (c) for RC columns with conforming hoops, expressed as plastic '
        'chord rotation. Acceptance is checked as: demand / θcap ≤ 1.0.',
        _S_BODY,
    ), Spacer(1, 2*mm)]

    rep = max(cases, key=lambda c: float(c['asce_rot']['ratio_x']), default=None)
    if rep is None:
        story.append(Paragraph('No load cases available.', _S_BODY))
        return story

    ar = rep['asce_rot']
    xd = ar['x']

    fc   = float(row['fc_MPa'])
    fy   = float(row['fy_long_MPa'])
    fyt  = float(row['fy_trans_MPa'])
    Ag   = float(geom['Ag_mm2'])
    Pu   = abs(float(rep['row']['Pu_kN']))
    fye  = ASCE41_FYE_DEFAULT * fy
    fyte = ASCE41_FYTE_DEFAULT * fyt
    rho_t_raw = float(xd['rho_t_raw'])
    rho_t = float(xd['rho_t_used'])
    nu = float(xd['axial_ratio'])
    v  = float(xd['vye_over_vcoloe'])
    a  = float(xd['a'])
    b_val = float(xd['b'])
    c_val = float(xd['c'])
    th_io = float(xd['theta_io'])
    th_ls = float(xd['theta_ls'])
    th_cp = float(xd['theta_cp'])
    th_cap = float(xd['theta_cap'])
    ds = str(xd['damage_state'])
    rot_demand = float(ar['RotX'])
    ratio = float(xd['ratio'])

    story += [Paragraph('Governing direction: X  (highest D/C ratio across all cases)', _S_H3)]

    story += _eq_block(
        "ν = Pu / (Ag · f'c)    (axial load ratio)",
        f'= {_f(Pu,1)}×10³ / ({_f(Ag,0)} × {_f(fc,1)})',
        f'= <b>{nu:.4f}</b>   (capped at {ASCE41_A_AXIAL_CAP} for parameter a)',
        'ASCE 41 Table 10-8',
    )
    story += _eq_block(
        'ρt = min(ρs,x, ρs,y)    (transverse reinforcement ratio)',
        f'= min({float(geom["rho_s_x"]):.6f}, {float(geom["rho_s_y"]):.6f})',
        f'= {rho_t_raw:.6f}  →  clipped to valid range  →  <b>{rho_t:.6f}</b>',
        'ASCE 41 Table 10-8, note',
    )
    story += _eq_block(
        'Vye/VColOE    (shear ratio — not less than 0.2)',
        f'= {v:.4f}',
        f'<b>v = {v:.4f}</b>',
        'ASCE 41 Table 10-8',
    )

    story += [Paragraph('Plastic rotation parameter a (pre-peak rotation)', _S_H3)]
    r_eff = min(nu, ASCE41_A_AXIAL_CAP)
    a_raw = (ASCE41_A_INTERCEPT - ASCE41_A_AXIAL_COEFF*r_eff
             + ASCE41_A_RHOT_COEFF*rho_t - ASCE41_A_VRATIO_COEFF*v)
    story += _eq_block(
        f'a = {ASCE41_A_INTERCEPT} − {ASCE41_A_AXIAL_COEFF}·ν_eff '
        f'+ {ASCE41_A_RHOT_COEFF}·ρt − {ASCE41_A_VRATIO_COEFF}·(Vye/VColOE)',
        f'= {ASCE41_A_INTERCEPT} − {ASCE41_A_AXIAL_COEFF}×{r_eff:.4f} + '
        f'{ASCE41_A_RHOT_COEFF}×{rho_t:.6f} − {ASCE41_A_VRATIO_COEFF}×{v:.4f}',
        f'= <b>{a:.5f} rad</b>',
        'ASCE 41 Table 10-8',
    )

    story += [Paragraph('Plastic rotation parameter b (post-peak rotation)', _S_H3)]
    denom = ASCE41_B_DENOM_INTERCEPT + (r_eff/ASCE41_B_DENOM_AXIAL_DIV)*(fc/max(rho_t*fyte, 1e-9))
    b_raw = ASCE41_B_NUMERATOR/denom - ASCE41_B_SUBTRACTION
    story += _eq_block(
        f'b = {ASCE41_B_NUMERATOR} / '
        f'({ASCE41_B_DENOM_INTERCEPT} + (ν/{ASCE41_B_DENOM_AXIAL_DIV})·(f\'c/(ρt·fyte))) '
        f'− {ASCE41_B_SUBTRACTION}',
        f'denom = {ASCE41_B_DENOM_INTERCEPT} + ({r_eff:.4f}/{ASCE41_B_DENOM_AXIAL_DIV})'
        f'×({_f(fc,1)}/({rho_t:.6f}×{_f(fyte,0)})) = {denom:.4f}',
        f'= {ASCE41_B_NUMERATOR}/{denom:.4f} − {ASCE41_B_SUBTRACTION} = '
        f'<b>{b_val:.5f} rad</b>  (≥ a)',
        'ASCE 41 Table 10-8',
    )

    story += [Paragraph('Plastic rotation parameter c (residual strength ratio)', _S_H3)]
    story += _eq_block(
        f'c = max({ASCE41_C_INTERCEPT} − {ASCE41_C_AXIAL_COEFF}·max(ν, 0.1), 0)',
        f'= max({ASCE41_C_INTERCEPT} − {ASCE41_C_AXIAL_COEFF}×{max(nu,0.1):.4f}, 0)',
        f'= <b>{c_val:.5f}</b>',
        'ASCE 41 Table 10-8',
    )

    story += [Paragraph('Acceptance criteria', _S_H3)]
    story += _eq_block(
        f'θIO = min({ASCE41_THETA_IO_FACTOR}·a, {ASCE41_THETA_IO_MAX})',
        f'= min({ASCE41_THETA_IO_FACTOR}×{a:.5f}, {ASCE41_THETA_IO_MAX})',
        f'= <b>{th_io:.5f} rad</b>',
        'ASCE 41 Table 10-8',
    )
    story += _eq_block(
        f'θLS = {ASCE41_THETA_LS_FACTOR}·b',
        f'= {ASCE41_THETA_LS_FACTOR} × {b_val:.5f}',
        f'= <b>{th_ls:.5f} rad</b>',
        'ASCE 41 Table 10-8',
    )
    story += _eq_block(
        f'θCP = {ASCE41_THETA_CP_FACTOR}·b',
        f'= {ASCE41_THETA_CP_FACTOR} × {b_val:.5f}',
        f'= <b>{th_cp:.5f} rad</b>',
        'ASCE 41 Table 10-8',
    )

    story += [Paragraph(f'Demand / Capacity  (damage state: {ds})', _S_H3)]
    story += _eq_block(
        f'θcap = θ{ds} = {th_cap:.5f} rad',
        f'θd (rotation demand) = {rot_demand:.5f} rad',
        f'D/C = {rot_demand:.5f} / {th_cap:.5f} = <b>{ratio:.3f}</b>',
        f'ASCE 41 §7.3.1',
    )
    ok = ratio <= 1.0
    story += _check_line('ASCE 41 rotation', f'D/C = {ratio:.3f}', '≤ 1.0', ok)
    story.append(Spacer(1, 3*mm))
    return story


def _s11_pm_diagrams(pm_paths: dict) -> list:
    story = _section_header('11  |  P-M Interaction Diagrams')
    story += [Paragraph(
        'Nominal (Mn), design (φMn), and probable (Mpr) interaction curves are shown '
        'for both principal axes. Demand points (×) correspond to each factored load '
        'combination. Points inside the design curve satisfy the P-M check.',
        _S_BODY,
    )]
    img_w = _INNER_W * 0.82
    img_h = img_w * (5.8 / 7.2)
    added = False
    for axis, key in [('x', 'pm_png_x'), ('y', 'pm_png_y')]:
        png = pm_paths.get(key, '')
        if png and Path(png).exists():
            story.append(Paragraph(f'Axis {axis}', _S_SMALL))
            story.append(Image(str(png), width=img_w, height=img_h))
            story.append(Spacer(1, 4*mm))
            added = True
    if not added:
        story.append(Paragraph('(P-M diagrams not generated for this run)', _S_SMALL))
    return story


# ── header / footer ────────────────────────────────────────────────────────────

def _make_on_page(logo_path: str | None, pry_name: str, column_id: str):
    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(_BLACK)
        canvas.setLineWidth(0.5)
        canvas.line(_MARGIN, _H - 14*mm, _W - _MARGIN, _H - 14*mm)

        canvas.setFont(_FONT, 8)
        canvas.setFillColor(_BLACK)
        label = f'PROJECT: {pry_name}   |   {column_id}' if pry_name else column_id
        canvas.drawString(_MARGIN, _H - 8*mm, label)

        if logo_path and Path(logo_path).exists():
            try:
                _logo_w = 44*mm
                _gap    = 2*mm
                canvas.setFont(_FONT, 6)
                _pb = 'powered by'
                _pb_w = canvas.stringWidth(_pb, 'Helvetica', 6)
                canvas.setFillColor(colors.HexColor('#aaaaaa'))
                canvas.drawString(_W - _MARGIN - _logo_w - _gap - _pb_w,
                                  _H - 8.5*mm, _pb)
                canvas.drawImage(logo_path, _W - _MARGIN - _logo_w, _H - 13*mm,
                                 width=_logo_w, height=10*mm,
                                 preserveAspectRatio=True, anchor='sw')
            except Exception:
                pass

        canvas.line(_MARGIN, 12*mm, _W - _MARGIN, 12*mm)
        canvas.setFont(_FONT, 7.5)
        canvas.setFillColor(_GRAY)
        canvas.drawCentredString(_W / 2, 9*mm, str(doc.page))
        canvas.setFont(_FONT, 6)
        canvas.setFillColor(colors.HexColor('#aaaaaa'))
        canvas.drawCentredString(
            _W / 2, 5*mm,
            '© 2026 Torrefuerte-Estructural · www.torrefuerte.ec · '
            'Beta version — not extensively validated · use under engineer\'s responsibility',
        )
        canvas.restoreState()
    return on_page


# ── main entry point ───────────────────────────────────────────────────────────

def build_detailed_pdf_report(ctx: dict) -> bytes:
    """
    Build the step-by-step educational PDF report and return as bytes.
    ctx has the same schema as the dict passed to build_pdf_report().
    """
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
    column_id    = str(ctx['column_id'])
    section_png  = ctx.get('section_png_path', '')
    logo_path    = str(Path(__file__).parent / 'assets' / 'Logo_horizontal_Torrefuerte.png')

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=_MARGIN, rightMargin=_MARGIN,
        topMargin=18*mm, bottomMargin=18*mm,
        title=f'RC Column Detailed Report — {column_id}',
        author='rc-column-checker',
    )

    on_page = _make_on_page(logo_path, pry_name, column_id)

    story: list[Any] = [
        Spacer(1, 4*mm),
        Paragraph('RC Column — Detailed Calculation Report', _S_TITLE),
        Paragraph(
            f'{column_id}'
            + (f'  ·  {pry_name}' if pry_name else '')
            + '  ·  ACI 318-25 / ASCE 41',
            _S_SUBTITLE,
        ),
        HRFlowable(width='100%', thickness=0.5, color=_BLACK, spaceAfter=4*mm),
    ]

    story += _s1_input(row, section_png)
    story += _s2_geometry(row, geom)
    story += _s3_axial(row, geom, axial)
    story += _s4_pm(row, geom, cases, flexure0)
    story += _s5_shear(row, geom, shear_base, cases)
    story += _s6_confinement(row, geom, tr_meta)
    story += _s7_rhos(row, geom, tr_meta, cases)
    story += _s8_scwb(row, cases)
    story += _s9_joint(row, joint_static, cases, beam_static)
    story += _s10_asce41(row, geom, cases)
    story += _s11_pm_diagrams(pm_paths)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
