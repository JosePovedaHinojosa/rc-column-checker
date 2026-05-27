from __future__ import annotations

import re
from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

FACE_BY_AXIS = {'x': ('top', 'bottom'), 'y': ('left', 'right')}


def _bar_positions(n: int, dim_mm: float, cover_mm: float,
                   tie_db_mm: float, bar_db_mm: float) -> list:
    if n <= 0:
        return []
    offset = cover_mm + tie_db_mm + bar_db_mm / 2.0
    if n == 1:
        return [dim_mm / 2.0]
    return [offset + i * (dim_mm - 2 * offset) / (n - 1) for i in range(n)]


def _plot_curve(ax, points, p_key: str, m_key: str, label: str, linestyle: str = '-', linewidth: float = 1.6):
    ax.plot([p[m_key] for p in points], [p[p_key] for p in points], linestyle=linestyle, linewidth=linewidth, label=label)


def export_pm_diagram(column_id: str, col_strengths, demand_rows, outdir: str | Path, axis: str = 'x'):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(7.2, 5.8))
    face_pos, face_neg = FACE_BY_AXIS[axis]

    _plot_curve(ax, col_strengths['Mn_points_pos'], 'Pn_kN', 'Mn_kNm', f'Nominal {face_pos}', '-')
    _plot_curve(ax, col_strengths['Mn_points_neg'], 'Pn_kN', 'Mn_kNm', f'Nominal {face_neg}', '-')
    _plot_curve(ax, col_strengths['Design_points_pos'], 'phiPn_kN', 'phiMn_kNm', f'Design $\\phi$ {face_pos}', '--')
    _plot_curve(ax, col_strengths['Design_points_neg'], 'phiPn_kN', 'phiMn_kNm', f'Design $\\phi$ {face_neg}', '--')
    _plot_curve(ax, col_strengths['Mpr_points_pos'], 'Pn_kN', 'Mn_kNm', f'Probable {face_pos}', '-.')
    _plot_curve(ax, col_strengths['Mpr_points_neg'], 'Pn_kN', 'Mn_kNm', f'Probable {face_neg}', '-.')

    for row in demand_rows:
        demand_M = abs(float(row['Mux_kNm'] if axis == 'x' else row['Muy_kNm']))
        demand_P = float(row['Pu_kN'])
        ax.plot([demand_M], [demand_P], 'x', markersize=7)
        ax.annotate(str(row.get('load_case', 'U1')), (demand_M, demand_P), textcoords='offset points', xytext=(4, 4), fontsize=7)

    ax.set_xlabel('Moment [kN·m]')
    ax.set_ylabel('Axial force P [kN]')
    ax.set_title(f'P-M Diagram - {column_id} - axis {axis}')
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, ncols=2)
    fig.tight_layout()

    stem = f'{column_id}_PM_{axis}'
    svg_path = outdir / f'{stem}.svg'
    pdf_path = outdir / f'{stem}.pdf'
    png_path = outdir / f'{stem}.png'
    fig.savefig(svg_path)
    fig.savefig(pdf_path)
    fig.savefig(png_path, dpi=200)
    plt.close(fig)
    return str(svg_path), str(pdf_path), str(png_path)


def export_section_sketch(column_id: str, prop_row: dict, outdir: str | Path) -> Path:
    """Generate a cross-section PNG for this column and return the full PNG Path.

    The PNG filename stem matches ``reporting.section_image_key(column_id)`` and
    the ``<<section_key>>`` placeholder in the LaTeX template, so both the
    LaTeX report and the ReportLab PDF builder can embed it directly.
    """
    # If a PNG was already placed here (e.g. by the Streamlit app from the
    # live session-state preview), reuse it — avoids regenerating from CSV data.
    _slug_early = re.split(r'_chain|_st\d+|_story\d+', str(column_id).strip(), maxsplit=1)[0].replace('_', '')
    _early_path = Path(outdir) / 'sections' / f'{_slug_early}.png'
    if _early_path.exists():
        return _early_path

    b      = float(prop_row.get('b_mm', 400))
    h      = float(prop_row.get('h_mm', 400))
    cover  = float(prop_row.get('cover_mm', 40))
    tie_db = float(prop_row.get('tie_db_mm', 10))
    bar_db = float(prop_row.get('bar_db_mm', 20))
    n_top  = int(prop_row.get('n_bars_x_top', 3))
    n_bot  = int(prop_row.get('n_bars_x_bottom', 3))
    n_lft  = int(prop_row.get('n_bars_y_left', 3))
    n_rgt  = int(prop_row.get('n_bars_y_right', 3))

    def _count_sl(val: object) -> int:
        v = str(val).strip()
        return len([x for x in v.split(';') if x.strip()]) if v else 2

    n_lx = max(2, min(_count_sl(prop_row.get('support_lines_top_mm',  '')), n_top))
    n_ly = max(2, min(_count_sl(prop_row.get('support_lines_left_mm', '')), n_lft))

    bar_off = cover + tie_db + bar_db / 2.0
    tie_off = cover + tie_db / 2.0
    bar_r   = bar_db / 2.0
    hoop_lw = max(1.0, tie_db / 5.0)

    xs_top = _bar_positions(n_top, b, cover, tie_db, bar_db)
    xs_bot = _bar_positions(n_bot, b, cover, tie_db, bar_db)
    ys_lft = _bar_positions(n_lft, h, cover, tie_db, bar_db)
    ys_rgt = _bar_positions(n_rgt, h, cover, tie_db, bar_db)

    y_top_bar = h - bar_off
    y_bot_bar = bar_off
    x_lft_bar = bar_off
    x_rgt_bar = b - bar_off

    def _intermediate_ct(n_legs: int, bar_pos: list) -> list:
        if len(bar_pos) < 2:
            return []
        n = max(2, min(n_legs, len(bar_pos)))
        m = len(bar_pos) - 1
        idx = sorted({round(k * m / (n - 1)) for k in range(n)})
        return [bar_pos[j] for j in idx if 0 < j < m]

    ct_x = _intermediate_ct(n_lx, xs_top)
    ct_y = _intermediate_ct(n_ly, ys_lft)

    fig_w = 5.0
    fig_h = max(3.5, min(fig_w * h / b + 0.8, 9.0))
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_aspect('equal', adjustable='datalim')

    pad = max(b, h) * 0.22
    ax.set_xlim(-pad, b + pad)
    ax.set_ylim(-pad * 1.4, h + pad * 0.5)
    ax.axis('off')

    ax.add_patch(mpatches.Rectangle(
        (0, 0), b, h, facecolor='#d4c8b3', edgecolor='#555555', linewidth=1.5, zorder=1,
    ))
    ax.add_patch(mpatches.Rectangle(
        (tie_off, tie_off), b - 2 * tie_off, h - 2 * tie_off,
        facecolor='none', edgecolor='#1a1a8c', linewidth=hoop_lw, zorder=2,
    ))

    for cx in ct_x:
        ax.plot([cx, cx], [y_bot_bar, y_top_bar],
                color='#1a1a8c', lw=hoop_lw * 0.7, solid_capstyle='round', zorder=2)
    for cy in ct_y:
        ax.plot([x_lft_bar, x_rgt_bar], [cy, cy],
                color='#1a1a8c', lw=hoop_lw * 0.7, solid_capstyle='round', zorder=2)

    bc, be = '#1a1a1a', '#999999'
    for x in xs_top:
        ax.add_patch(mpatches.Circle((x, y_top_bar), bar_r, fc=bc, ec=be, lw=0.5, zorder=3))
    for x in xs_bot:
        ax.add_patch(mpatches.Circle((x, y_bot_bar), bar_r, fc=bc, ec=be, lw=0.5, zorder=3))
    for y in ys_lft[1:-1]:
        ax.add_patch(mpatches.Circle((x_lft_bar, y), bar_r, fc=bc, ec=be, lw=0.5, zorder=3))
    for y in ys_rgt[1:-1]:
        ax.add_patch(mpatches.Circle((x_rgt_bar, y), bar_r, fc=bc, ec=be, lw=0.5, zorder=3))

    arr_kw = dict(arrowstyle='<->', color='#444444', lw=0.8)
    txt_kw = dict(fontsize=8, color='#444444')

    y_ann = -pad * 0.75
    ax.annotate('', xy=(b, y_ann), xytext=(0, y_ann),
                arrowprops=arr_kw, annotation_clip=False)
    ax.text(b / 2, y_ann - pad * 0.3, f'b = {b:.0f} mm',
            ha='center', va='top', **txt_kw)

    x_ann = -pad * 0.75
    ax.annotate('', xy=(x_ann, h), xytext=(x_ann, 0),
                arrowprops=arr_kw, annotation_clip=False)
    ax.text(x_ann - pad * 0.2, h / 2, f'h = {h:.0f} mm',
            ha='right', va='center', rotation=90, **txt_kw)

    fig.tight_layout(pad=0.2)

    slug = re.split(r'_chain|_st\d+|_story\d+', str(column_id).strip(), maxsplit=1)[0].replace('_', '')
    sections_dir = Path(outdir) / 'sections'
    sections_dir.mkdir(parents=True, exist_ok=True)
    png_path = sections_dir / f'{slug}.png'

    fig.savefig(str(png_path), dpi=150, bbox_inches='tight')
    plt.close(fig)
    return png_path
