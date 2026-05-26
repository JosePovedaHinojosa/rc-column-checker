from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

FACE_BY_AXIS = {'x': ('top', 'bottom'), 'y': ('left', 'right')}


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
