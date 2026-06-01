"""
pdf_report_detailed.py
======================
Educational step-by-step PDF report.
Shows every major calculation with its symbolic equation, substituted values,
and numeric result — intended for students learning ACI 318-22 / ASCE 41.

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
    fontSize=13, fontName='Helvetica-Bold', textColor=_BLACK,
    spaceAfter=1*mm, spaceBefore=0)
_S_SUBTITLE = ParagraphStyle('DSubtitle', parent=_BASE['Normal'],
    fontSize=9, fontName='Helvetica', textColor=_GRAY,
    spaceAfter=3*mm, spaceBefore=0)
_S_H2 = ParagraphStyle('DH2', parent=_BASE['Normal'],
    fontSize=9.5, fontName='Helvetica-Bold', textColor=colors.white,
    spaceAfter=0, spaceBefore=0, leftIndent=2*mm)
_S_H3 = ParagraphStyle('DH3', parent=_BASE['Normal'],
    fontSize=8.5, fontName='Helvetica-Bold', textColor=_SEC_LN,
    spaceAfter=1*mm, spaceBefore=3*mm)
_S_BODY = ParagraphStyle('DBody', parent=_BASE['Normal'],
    fontSize=7.5, fontName='Helvetica', textColor=_BLACK,
    spaceAfter=1*mm, leading=10)
_S_NOTE = ParagraphStyle('DNote', parent=_BASE['Normal'],
    fontSize=6.5, fontName='Helvetica', textColor=_DGRAY,
    spaceAfter=1*mm, leading=8.5, leftIndent=4*mm)
# equation styles
_S_EQ_FORMULA = ParagraphStyle('DEqFormula', parent=_BASE['Normal'],
    fontSize=8, fontName='Helvetica', textColor=_BLACK,
    spaceAfter=0, leading=10, leftIndent=4*mm)
_S_EQ_SUBST = ParagraphStyle('DEqSubst', parent=_BASE['Normal'],
    fontSize=7.5, fontName='Helvetica', textColor=_GRAY,
    spaceAfter=0, leading=9.5, leftIndent=12*mm)
_S_EQ_RESULT = ParagraphStyle('DEqResult', parent=_BASE['Normal'],
    fontSize=8, fontName='Helvetica-Bold', textColor=_BLACK,
    spaceAfter=2*mm, leading=10, leftIndent=12*mm)
_S_REF = ParagraphStyle('DRef', parent=_BASE['Normal'],
    fontSize=6.5, fontName='Helvetica', textColor=_SEC_LN,
    alignment=2)   # right-aligned
_S_CELL = ParagraphStyle('DCell', parent=_BASE['Normal'],
    fontSize=7, leading=9, fontName='Helvetica')
_S_CELL_B = ParagraphStyle('DCellB', parent=_BASE['Normal'],
    fontSize=7, leading=9, fontName='Helvetica-Bold', textColor=colors.white)
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
    _SKT_MAX_W, _SKT_MAX_H = 55*mm, 80*mm
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
    layout = Table([[tbl_params, sketch]], colWidths=[80*mm, _INNER_W - 80*mm])
    layout.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(layout)
    story.append(Spacer(1, 4*mm))
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
    story += _eq_block(
        'ρ_long = As / Ag',
        f'= {_f(As,1)} / {_f(Ag,0)}',
        f'= <b>{rho:.5f}</b>  (ACI 18.7.4.1 requires 0.01 ≤ ρ ≤ 0.08)',
        'ACI 18.7.4.1',
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
    fc  = float(row['fc_MPa'])
    fy  = float(row['fy_long_MPa'])
    Ag  = float(geom['Ag_mm2'])
    As  = float(geom['As_mm2'])
    Pn0 = float(axial['Pn0_kN'])
    phi = ACI_PHI_COMPRESSION

    story += [Paragraph('Nominal concentric axial capacity', _S_H3)]
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
        f'φPn0 = φ · Pn0        (φ = {phi} for compression-controlled)',
        f'= {phi} × {_f(Pn0,1)}',
        f'= <b>{_f(axial["phiPn0_kN"],1)} kN</b>',
        'ACI Table 21.2.2',
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

    story += [Paragraph('ACI 18.7.6.2.1 — Vc = 0 rule', _S_H3)]
    story += [Paragraph(
        "Vc shall be taken as zero when both conditions (a) and (b) apply:<br/>"
        f"(a) The earthquake-induced shear Ve ≥ 0.5·Vu_design;<br/>"
        f"(b) Pu,factored &lt; Ag·f'c / {ACI_VC_ZERO_AXIAL_DIVISOR:.0f}.",
        _S_BODY,
    )]

    story += [Paragraph('Probable seismic shear (Ve) — representative case', _S_H3)]
    rep = max(cases, key=lambda c: float(c['row']['Pu_kN']), default=None)
    if rep:
        ps = rep['prob_shear']
        story += _eq_block(
            'Ve = (Mpr,top + Mpr,bot) / ℓu',
            f'= ({_f(ps["col_Mpr_top_x_eff_kNm"],1)} + {_f(ps["col_Mpr_bot_x_eff_kNm"],1)}) / {_f(ps["lu_m"],2)} m',
            f'= <b>{_f(ps["Ve_col_x_kN"],1)} kN</b>  (axis x)',
            'ACI 18.7.6.1',
            note='Mpr values are limited by connected beam joint Mpr when beams are present.',
        )

    story.append(Spacer(1, 3*mm))
    return story


def _s6_confinement(row: dict, geom: dict, tr_meta: dict) -> list:
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


def _s7_rhos(row: dict, geom: dict, tr_meta: dict) -> list:
    story = _section_header('7  |  Minimum Transverse Reinforcement  —  ACI Table 18.7.5.4')
    fc   = float(row['fc_MPa'])
    fyt  = float(row['fy_trans_MPa'])
    Ag   = float(geom['Ag_mm2'])
    Ach  = float(geom['Ach_mm2'])
    Pu_N = float(row['Pu_kN']) * 1e3
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

    expr_a = ACI_RHO_S_RECT_A * max(Ag/max(Ach,1e-9)-1, 0) * (fc/max(fyt,1e-9)) * kf * kn
    expr_b = ACI_RHO_S_RECT_B * (fc/max(fyt,1e-9)) * kf * kn
    expr_c = ACI_RHO_S_RECT_C * kf * kn * Pu_N / max(fyt*Ach, 1e-9)

    story += [Paragraph('Expression (a)', _S_H3)]
    story += _eq_block(
        "ρs,(a) = 0.3·(Ag/Ach − 1)·(f'c/fyt)·kf·kn",
        f"= 0.3×({_f(Ag,0)}/{_f(Ach,0)}−1)×({_f(fc,1)}/{_f(fyt,0)})×{_f(kf,4)}×{_f(kn,4)}",
        f'= <b>{expr_a:.6f}</b>',
        'ACI Table 18.7.5.4(a)',
    )

    story += [Paragraph('Expression (b)', _S_H3)]
    story += _eq_block(
        "ρs,(b) = 0.09·(f'c/fyt)·kf·kn",
        f"= 0.09×({_f(fc,1)}/{_f(fyt,0)})×{_f(kf,4)}×{_f(kn,4)}",
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


def _s9_joint(row: dict, joint_static: dict) -> list:
    story = _section_header('9  |  Joint Shear Capacity  —  ACI 15.4.2.1')
    story += [Paragraph(
        'Joint shear strength: Vn = αj · √f\'c · Aj.  '
        'αj depends on joint continuity and confinement per ACI Table 15.4.2.3.',
        _S_BODY,
    ), Spacer(1, 2*mm)]

    fc = float(row['fc_MPa'])
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
                f'<b>{joint.capitalize()} joint — axis {axis}</b>'
                f'  (confined: {"yes" if conf else "no"},  αj = {coeff})',
                _S_H3,
            )]
            story += _eq_block(
                'Aj = h_joint · beff    (effective joint area)',
                f'= {_f(h_j,0)} × {_f(eff_w,0)}',
                f'= <b>{_f(Aj,0)} mm²</b>',
                'ACI R15.4.2.4',
            )
            story += _eq_block(
                "Vn = αj · √f'c · Aj",
                f'= {coeff} × √{_f(fc,1)} × {_f(Aj,0)} / 1000',
                f'= <b>{_f(Vn,1)} kN</b>',
                'ACI 15.4.2.1',
            )
            story += _eq_block(
                f'φVn = {ACI_PHI_JOINT} · Vn',
                f'= {ACI_PHI_JOINT} × {_f(Vn,1)}',
                f'= <b>{_f(pVn,1)} kN</b>',
                'ACI Table 21.2.1(d)',
            )
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

        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(_BLACK)
        label = f'PROJECT: {pry_name}   |   {column_id}' if pry_name else column_id
        canvas.drawString(_MARGIN, _H - 8*mm, label)

        if logo_path and Path(logo_path).exists():
            try:
                _logo_w = 44*mm
                _gap    = 2*mm
                canvas.setFont('Helvetica', 6)
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
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(_GRAY)
        canvas.drawCentredString(_W / 2, 9*mm, str(doc.page))
        canvas.setFont('Helvetica', 6)
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
            + '  ·  ACI 318-22 / ASCE 41',
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
    story += _s7_rhos(row, geom, tr_meta)
    story += _s8_scwb(row, cases)
    story += _s9_joint(row, joint_static)
    story += _s10_asce41(row, geom, cases)
    story += _s11_pm_diagrams(pm_paths)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
