"""
rc-column-checker – Streamlit GUI

Didactic interface for ACI 318-22 / ASCE 41 RC column verification.
Fills in CSV inputs interactively, runs main.py, and displays colour-coded results.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

import streamlit as st

ROOT = Path(__file__).parent

BEAM_FACES = ['beam_top_x', 'beam_bottom_x', 'beam_top_y', 'beam_bottom_y']
FACE_LABELS = {
    'beam_top_x':    'Top-X  — joint above, bending about x-axis',
    'beam_bottom_x': 'Bottom-X — joint below, bending about x-axis',
    'beam_top_y':    'Top-Y  — joint above, bending about y-axis',
    'beam_bottom_y': 'Bottom-Y — joint below, bending about y-axis',
}

# Session-state keys that hold project data (not widget state).
# Everything outside this set is a widget key and gets wiped on project load.
_DATA_KEYS: frozenset[str] = frozenset({
    'column_sections', 'beam_sections', 'assemblies',
    'report_requested', 'report_detailed_requested', 'project_name', 'report_columns',
    '_results', '_checks', '_failures', '_stdout',
    '_csv_results', '_csv_checks', '_csv_failures',
    '_tex_content', '_tex_filename', '_pdf_bytes', '_pdf_compiled',
    '_pdf_det_bytes', '_pdf_det_filename',
    '_loaded_hash',
})


def _apply_project_data(data: dict) -> None:
    """Replace session state with loaded project data, clearing all widget keys."""
    for k in [k for k in list(st.session_state.keys()) if k not in _DATA_KEYS]:
        del st.session_state[k]
    # Clear stale results from any previous run so the new project starts fresh.
    for k in (
        '_results', '_checks', '_failures', '_stdout',
        '_csv_results', '_csv_checks', '_csv_failures',
        '_tex_content', '_tex_filename', '_pdf_bytes', '_pdf_compiled',
        '_pdf_det_bytes', '_pdf_det_filename',
    ):
        st.session_state.pop(k, None)
    st.session_state['column_sections'] = data['column_sections']
    st.session_state['beam_sections']   = data['beam_sections']
    st.session_state['assemblies']      = data['assemblies']
    st.session_state['project_name']    = data.get('project_name', '')
    st.session_state['report_columns']  = []


def _project_io_panel() -> None:
    """Save / load panel rendered above the main tabs."""
    col_dl, col_up = st.columns(2)

    with col_dl:
        st.markdown('**Save project**')
        project_data = {
            'version': 1,
            'project_name':    st.session_state.get('project_name', ''),
            'column_sections': st.session_state['column_sections'],
            'beam_sections':   st.session_state['beam_sections'],
            'assemblies':      st.session_state['assemblies'],
        }
        fname = (st.session_state.get('project_name') or 'rc_project').replace(' ', '_') + '.json'
        st.download_button(
            '⬇ Download project (.json)',
            data=json.dumps(project_data, indent=2, ensure_ascii=False),
            file_name=fname,
            mime='application/json',
            help=(
                'Saves all column sections, beam sections, assemblies, and load cases '
                'to a JSON file. Re-open it with **Load project** to restore the session.'
            ),
        )

    with col_up:
        st.markdown('**Load project**')
        uploaded = st.file_uploader(
            'Select .json file', type='json',
            key='_proj_uploader', label_visibility='collapsed',
        )
        if uploaded is not None:
            content   = uploaded.getvalue()
            file_hash = hashlib.md5(content).hexdigest()
            if st.session_state.get('_loaded_hash') == file_hash:
                st.caption('✅ Project already loaded.')
            else:
                if st.button('📂 Apply', key='_proj_apply',
                             help='Replace the current session with the contents of this file.'):
                    try:
                        data = json.loads(content.decode('utf-8'))
                        if data.get('version') not in (1,):
                            st.error('Unsupported file version.')
                        else:
                            _apply_project_data(data)
                            st.session_state['_loaded_hash'] = file_hash
                            st.rerun()
                    except Exception as exc:
                        st.error(f'Failed to load project: {exc}')


# ─────────────────────────────────────────────────────────────────────────────
# Default factories
# ─────────────────────────────────────────────────────────────────────────────

def _default_column_section(section_id: str = 'COL_SEC_1') -> dict:
    return {
        'section_id':                    section_id,
        'b_mm':                          400.0,
        'h_mm':                          400.0,
        'cover_mm':                      40.0,
        'fc_MPa':                        28.0,
        'fy_long_MPa':                   420.0,
        'fy_trans_MPa':                  420.0,
        'n_bars_x_top':                  3,
        'n_bars_x_bottom':               3,
        'n_bars_y_left':                 3,
        'n_bars_y_right':                3,
        'bar_db_mm':                     20.0,
        'tie_type':                      'rectilinear',
        'tie_db_mm':                     10.0,
        'tie_spacing_lo_mm':             100.0,
        'tie_spacing_outside_lo_mm':     200.0,
        'crosstie_db_mm':                10.0,
        'hook_angle_deg':                135.0,
        'crosstie_alt_anchorage':        True,
        'overlapping_hoops':             False,
        'spiral_provided':               False,
        'asce_splice_controlled':        False,
        'asce_splice_two_tie_groups':    True,
        'asce_ties_adequately_anchored': True,
        'n_legs_x':                      3,
        'n_legs_y':                      3,
    }


def _default_assembly(col_id: str = 'COL_1', col_section_id: str = 'COL_SEC_1') -> dict:
    beam_faces: dict = {}
    for face in BEAM_FACES:
        for side in ('side1', 'side2'):
            beam_faces[f'{face}_{side}'] = {
                'section_id':  'none',
                'ln_mm':       0.0,
                'wu_kN_per_m': 0.0,
                'x_mm':        0.0,
                'ext_mm':      0.0,
                'continuous':  True,
            }
    return {
        'col_id':                   col_id,
        'col_section_id':           col_section_id,
        'story':                    '1',
        'frame_type':               'SMF',
        'clear_height_mm':          3000.0,
        'top_other_col_id':         'same',
        'bottom_other_col_id':      'same',
        'joint_top':                True,
        'joint_bottom':             True,
        'yielding_region_expected': True,
        'beam_faces':               beam_faces,
        'load_cases': [
            {'load_case': 'U1', 'Pu_kN': 1500.0, 'Mux_kNm': 300.0, 'Muy_kNm': 200.0,
             'Vux_kN': 100.0, 'Vuy_kN': 80.0, 'RotX': 0.0, 'RotY': 0.0, 'damage_state': 'CP'},
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Session-state initialisation
# ─────────────────────────────────────────────────────────────────────────────

def _init_state() -> None:
    if 'column_sections' not in st.session_state:
        st.session_state['column_sections'] = [_default_column_section('COL_SEC_1')]

    if 'beam_sections' not in st.session_state:
        st.session_state['beam_sections'] = [
            dict(beam_section_id='BEAM_X', bw_mm=300.0, h_mm=500.0, cover_mm=40.0,
                 fc_MPa=28.0, fy_long_MPa=420.0, fy_trans_MPa=420.0,
                 n_bars_top=4, db_top_mm=16.0, n_bars_bot=3, db_bot_mm=16.0,
                 stirrup_db_mm=10.0),
        ]

    if 'assemblies' not in st.session_state:
        first_sec = st.session_state['column_sections'][0]['section_id']
        st.session_state['assemblies'] = [_default_assembly('COL_1', first_sec)]

    for key, val in {'report_requested': False, 'report_detailed_requested': False,
                     'project_name': '', 'report_columns': []}.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ─────────────────────────────────────────────────────────────────────────────
# Geometry helpers
# ─────────────────────────────────────────────────────────────────────────────

def _bar_positions(n: int, dim_mm: float, cover_mm: float,
                   tie_db_mm: float, bar_db_mm: float) -> list[float]:
    if n <= 0:
        return []
    offset = cover_mm + tie_db_mm + bar_db_mm / 2.0
    if n == 1:
        return [dim_mm / 2.0]
    return [offset + i * (dim_mm - 2 * offset) / (n - 1) for i in range(n)]


def _support_lines_from_legs(n_legs: int, n_bars: int, dim_mm: float,
                              cover_mm: float, tie_db_mm: float, bar_db_mm: float) -> str:
    positions = _bar_positions(n_bars, dim_mm, cover_mm, tie_db_mm, bar_db_mm)
    if not positions:
        return ''
    n_legs = max(2, min(n_legs, len(positions)))
    if n_legs >= len(positions):
        return ';'.join(f'{p:.0f}' for p in positions)
    m = len(positions) - 1
    indices = sorted({round(i * m / (n_legs - 1)) for i in range(n_legs)})
    return ';'.join(f'{positions[i]:.0f}' for i in indices)


def _hx_from_legs(n_legs: int, n_bars: int, dim_mm: float,
                  cover_mm: float, tie_db_mm: float, bar_db_mm: float) -> float:
    positions = _bar_positions(n_bars, dim_mm, cover_mm, tie_db_mm, bar_db_mm)
    if len(positions) <= 1:
        return 0.0
    n_legs = max(2, min(n_legs, len(positions)))
    m = len(positions) - 1
    indices = sorted({round(i * m / (n_legs - 1)) for i in range(n_legs)})
    pts = [positions[i] for i in indices]
    return max((b - a) for a, b in zip(pts[:-1], pts[1:]))


# ─────────────────────────────────────────────────────────────────────────────
# Cross-section sketch helpers
# ─────────────────────────────────────────────────────────────────────────────

def _draw_column_section(sec: dict) -> plt.Figure:
    b      = float(sec['b_mm'])
    h      = float(sec['h_mm'])
    cover  = float(sec['cover_mm'])
    tie_db = float(sec['tie_db_mm'])
    bar_db = float(sec['bar_db_mm'])
    n_top  = int(sec['n_bars_x_top'])
    n_bot  = int(sec['n_bars_x_bottom'])
    n_lft  = int(sec['n_bars_y_left'])
    n_rgt  = int(sec['n_bars_y_right'])
    n_lx   = max(2, min(int(sec['n_legs_x']), n_top))
    n_ly   = max(2, min(int(sec['n_legs_y']), n_lft))

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

    fig_w = 4.0
    fig_h = max(3.0, min(fig_w * h / b + 0.6, 7.5))
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
    txt_kw = dict(fontsize=7, color='#444444')

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
    return fig


def _draw_beam_section(bsec: dict) -> plt.Figure:
    bw      = float(bsec['bw_mm'])
    h       = float(bsec['h_mm'])
    cover   = float(bsec['cover_mm'])
    stir_db = float(bsec['stirrup_db_mm'])
    n_top   = int(bsec['n_bars_top'])
    db_top  = float(bsec['db_top_mm'])
    n_bot   = int(bsec['n_bars_bot'])
    db_bot  = float(bsec['db_bot_mm'])

    stir_off  = cover + stir_db / 2.0
    y_top_bar = h - (cover + stir_db + db_top / 2.0)
    y_bot_bar = cover + stir_db + db_bot / 2.0
    stir_lw   = max(1.0, stir_db / 5.0)

    xs_top = _bar_positions(n_top, bw, cover, stir_db, db_top)
    xs_bot = _bar_positions(n_bot, bw, cover, stir_db, db_bot)

    fig_w = 4.0
    fig_h = max(3.0, min(fig_w * h / bw + 0.6, 7.5))
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_aspect('equal', adjustable='datalim')

    pad = max(bw, h) * 0.22
    ax.set_xlim(-pad, bw + pad)
    ax.set_ylim(-pad * 1.4, h + pad * 0.5)
    ax.axis('off')

    ax.add_patch(mpatches.Rectangle(
        (0, 0), bw, h, facecolor='#d4c8b3', edgecolor='#555555', linewidth=1.5, zorder=1,
    ))
    ax.add_patch(mpatches.Rectangle(
        (stir_off, stir_off), bw - 2 * stir_off, h - 2 * stir_off,
        facecolor='none', edgecolor='#1a1a8c', linewidth=stir_lw, zorder=2,
    ))

    bc, be = '#1a1a1a', '#999999'
    for x in xs_top:
        ax.add_patch(mpatches.Circle((x, y_top_bar), db_top / 2, fc=bc, ec=be, lw=0.5, zorder=3))
    for x in xs_bot:
        ax.add_patch(mpatches.Circle((x, y_bot_bar), db_bot / 2, fc=bc, ec=be, lw=0.5, zorder=3))

    arr_kw = dict(arrowstyle='<->', color='#444444', lw=0.8)
    txt_kw = dict(fontsize=7, color='#444444')

    y_ann = -pad * 0.75
    ax.annotate('', xy=(bw, y_ann), xytext=(0, y_ann),
                arrowprops=arr_kw, annotation_clip=False)
    ax.text(bw / 2, y_ann - pad * 0.3, f'bw = {bw:.0f} mm',
            ha='center', va='top', **txt_kw)

    x_ann = -pad * 0.75
    ax.annotate('', xy=(x_ann, h), xytext=(x_ann, 0),
                arrowprops=arr_kw, annotation_clip=False)
    ax.text(x_ann - pad * 0.2, h / 2, f'h = {h:.0f} mm',
            ha='right', va='center', rotation=90, **txt_kw)

    fig.tight_layout(pad=0.2)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# CSV writers
# ─────────────────────────────────────────────────────────────────────────────

def _write_column_sections_csv(path: Path) -> None:
    sections = st.session_state['column_sections']
    rows = []
    for sec in sections:
        n_lx = max(2, min(int(sec['n_legs_x']), sec['n_bars_x_top']))
        n_ly = max(2, min(int(sec['n_legs_y']), sec['n_bars_y_left']))
        sl_top = _support_lines_from_legs(n_lx, sec['n_bars_x_top'],    sec['b_mm'], sec['cover_mm'], sec['tie_db_mm'], sec['bar_db_mm'])
        sl_bot = _support_lines_from_legs(n_lx, sec['n_bars_x_bottom'], sec['b_mm'], sec['cover_mm'], sec['tie_db_mm'], sec['bar_db_mm'])
        sl_lft = _support_lines_from_legs(n_ly, sec['n_bars_y_left'],   sec['h_mm'], sec['cover_mm'], sec['tie_db_mm'], sec['bar_db_mm'])
        sl_rgt = _support_lines_from_legs(n_ly, sec['n_bars_y_right'],  sec['h_mm'], sec['cover_mm'], sec['tie_db_mm'], sec['bar_db_mm'])
        rows.append({
            'column_section_id':              sec['section_id'],
            'b_mm':                           sec['b_mm'],
            'h_mm':                           sec['h_mm'],
            'cover_mm':                       sec['cover_mm'],
            'fc_MPa':                         sec['fc_MPa'],
            'fy_long_MPa':                    sec['fy_long_MPa'],
            'fy_trans_MPa':                   sec['fy_trans_MPa'],
            'n_bars_x_top':                   sec['n_bars_x_top'],
            'n_bars_x_bottom':                sec['n_bars_x_bottom'],
            'n_bars_y_left':                  sec['n_bars_y_left'],
            'n_bars_y_right':                 sec['n_bars_y_right'],
            'bar_db_mm':                      sec['bar_db_mm'],
            'tie_type':                       sec['tie_type'],
            'tie_db_mm':                      sec['tie_db_mm'],
            'tie_spacing_lo_mm':              sec['tie_spacing_lo_mm'],
            'tie_spacing_outside_lo_mm':      sec['tie_spacing_outside_lo_mm'],
            'crosstie_db_mm':                 sec['crosstie_db_mm'],
            'hook_angle_deg':                 int(sec['hook_angle_deg']),
            'crosstie_alt_anchorage':         sec['crosstie_alt_anchorage'],
            'overlapping_hoops':              sec['overlapping_hoops'],
            'spiral_provided':                sec['spiral_provided'],
            'support_lines_top_mm':           sl_top,
            'support_lines_bottom_mm':        sl_bot,
            'support_lines_left_mm':          sl_lft,
            'support_lines_right_mm':         sl_rgt,
            'asce_splice_controlled':         sec['asce_splice_controlled'],
            'asce_splice_two_tie_groups':     sec['asce_splice_two_tie_groups'],
            'asce_ties_adequately_anchored':  sec['asce_ties_adequately_anchored'],
        })
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _write_beam_sections_csv(path: Path) -> None:
    rows = st.session_state['beam_sections']
    if not rows:
        rows = [dict(beam_section_id='_NONE', bw_mm=200, h_mm=400, cover_mm=40,
                     fc_MPa=28, fy_long_MPa=420, fy_trans_MPa=420,
                     n_bars_top=2, db_top_mm=12, n_bars_bot=2, db_bot_mm=12,
                     stirrup_db_mm=8)]
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _write_column_beam_csv(path: Path) -> None:
    assemblies = st.session_state['assemblies']
    rows = []
    for asm in assemblies:
        row: dict = {
            'column_id':                      asm['col_id'],
            'story':                          asm['story'],
            'frame_type':                     asm['frame_type'],
            'column_section_id':              asm['col_section_id'],
            'clear_height_mm':                asm['clear_height_mm'],
            'top_other_column_section_id':    asm['top_other_col_id'],
            'bottom_other_column_section_id': asm['bottom_other_col_id'],
            'joint_top':                      asm['joint_top'],
            'joint_bottom':                   asm['joint_bottom'],
            'yielding_region_expected':       asm['yielding_region_expected'],
        }
        for face in BEAM_FACES:
            for side in ('side1', 'side2'):
                k = f'{face}_{side}'
                bfd = asm['beam_faces'][k]
                row[f'{k}_section_id']  = bfd['section_id']
                row[f'{k}_ln_mm']       = bfd['ln_mm']
                row[f'{k}_wu_kN_per_m'] = bfd['wu_kN_per_m']
                row[f'{k}_x_mm']        = bfd['x_mm']
                row[f'{k}_ext_mm']      = bfd['ext_mm']
                row[f'{k}_continuous']  = bfd['continuous']
        rows.append(row)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _write_loads_csv(path: Path) -> None:
    rows = []
    for asm in st.session_state['assemblies']:
        for lc in asm['load_cases']:
            rows.append({'column_id': asm['col_id'], **lc})
    if not rows:
        return
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Tab 1 – Column Sections (library)
# ─────────────────────────────────────────────────────────────────────────────

def tab_section() -> None:
    st.subheader('Column Section Library')
    st.caption(
        'Define one or more column cross-sections. '
        'In the **Assembly** tab you select which section belongs to each column instance '
        'and which sections represent adjacent columns above/below for the SCWB check.'
    )

    sections: list[dict] = st.session_state['column_sections']

    for i, sec in enumerate(sections):
        label = sec.get('section_id', f'Section {i + 1}')
        with st.expander(f'**{label}**', expanded=(i == 0)):

            sec['section_id'] = st.text_input(
                'Section ID', value=sec['section_id'], key=f'csec_id_{i}',
                help=(
                    'Unique identifier. Referenced in the Assembly tab as '
                    '"Column section", "Adjacent above", or "Adjacent below".'
                ),
            )

            _col_form, _col_sketch = st.columns([3, 1])
            with _col_form:
                with st.expander('📐 Geometry', expanded=True):
                    c1, c2, c3 = st.columns(3)
                    sec['cover_mm'] = c1.number_input(
                        'Clear cover [mm]', value=float(sec['cover_mm']),
                        min_value=10.0, step=5.0, key=f'csec_cov_{i}',
                        help='**ACI 20.6.1.3** — Clear cover to outer face of hoop/tie. Typically 40 mm.',
                    )
                    sec['b_mm'] = c2.number_input(
                        'b — width [mm]', value=float(sec['b_mm']),
                        min_value=100.0, step=25.0, key=f'csec_b_{i}',
                        help='**ACI 18.7.2.1** — Width perpendicular to x-bending axis.',
                    )
                    sec['h_mm'] = c3.number_input(
                        'h — depth [mm]', value=float(sec['h_mm']),
                        min_value=100.0, step=25.0, key=f'csec_h_{i}',
                        help='**ACI 18.7.2.1** — Depth perpendicular to y-bending axis.',
                    )

                with st.expander('🧱 Materials', expanded=True):
                    c1, c2, c3 = st.columns(3)
                    sec['fc_MPa'] = c1.number_input(
                        "f'c [MPa]", value=float(sec['fc_MPa']),
                        min_value=17.0, step=5.0, key=f'csec_fc_{i}',
                        help=(
                            "**ACI 19.2.1** — Specified compressive strength. "
                            "f'c ≥ 21 MPa required for SMF. "
                            "f'c > 69 MPa triggers additional checks (ACI 18.7.2.3)."
                        ),
                    )
                    sec['fy_long_MPa'] = c2.number_input(
                        'fy longitudinal [MPa]', value=float(sec['fy_long_MPa']),
                        min_value=200.0, step=10.0, key=f'csec_fy_{i}',
                        help='**ACI 20.2.2.4** — Yield strength of longitudinal bars. fye = 1.25 fy for Mpr/SCWB.',
                    )
                    sec['fy_trans_MPa'] = c3.number_input(
                        'fy transverse [MPa]', value=float(sec['fy_trans_MPa']),
                        min_value=200.0, step=10.0, key=f'csec_fyt_{i}',
                        help='**ACI 18.7.5.3** — Yield strength of hoops/crossties. Capped at 550 MPa in Ash equations.',
                    )

                with st.expander('🔩 Longitudinal Reinforcement', expanded=True):
                    st.markdown(
                        'Bars per face — **corner bars are shared**: '
                        'total = n_top + n_bottom + n_left + n_right − 4.'
                    )
                    c1, c2, c3, c4 = st.columns(4)
                    sec['n_bars_x_top'] = c1.number_input(
                        'Bars – top', value=int(sec['n_bars_x_top']),
                        min_value=2, step=1, key=f'csec_nxt_{i}',
                        help='Bars on top face (b-direction), including shared corner bars.',
                    )
                    sec['n_bars_x_bottom'] = c2.number_input(
                        'Bars – bottom', value=int(sec['n_bars_x_bottom']),
                        min_value=2, step=1, key=f'csec_nxb_{i}',
                    )
                    sec['n_bars_y_left'] = c3.number_input(
                        'Bars – left', value=int(sec['n_bars_y_left']),
                        min_value=2, step=1, key=f'csec_nyl_{i}',
                        help='Bars on left face (h-direction).',
                    )
                    sec['n_bars_y_right'] = c4.number_input(
                        'Bars – right', value=int(sec['n_bars_y_right']),
                        min_value=2, step=1, key=f'csec_nyr_{i}',
                    )
                    sec['bar_db_mm'] = st.number_input(
                        'Bar diameter db [mm]', value=float(sec['bar_db_mm']),
                        min_value=6.0, step=2.0, key=f'csec_db_{i}',
                        help='**ACI 20.2.1** — All longitudinal bars share one diameter. Common: 12, 16, 20, 25, 32 mm.',
                    )
                    n_bars = (sec['n_bars_x_top'] + sec['n_bars_x_bottom']
                              + sec['n_bars_y_left'] + sec['n_bars_y_right'] - 4)
                    As_mm2 = n_bars * math.pi * sec['bar_db_mm'] ** 2 / 4.0
                    rho = As_mm2 / (sec['b_mm'] * sec['h_mm'])
                    cm1, cm2, cm3 = st.columns(3)
                    cm1.metric('Total bars', n_bars)
                    cm2.metric('As [mm²]', f'{As_mm2:,.0f}')
                    cm3.metric('ρ_long', f'{rho:.4f}',
                               help='**ACI 18.7.4.1** — Must satisfy 0.01 ≤ ρ ≤ 0.08.')
                    if rho < 0.01:
                        st.warning('⚠️ ρ < 0.01 — below ACI 18.7.4.1 minimum (1 %).')
                    elif rho > 0.08:
                        st.error('❌ ρ > 0.08 — exceeds ACI 18.7.4.1 maximum (8 %).')

                with st.expander('🔗 Transverse Reinforcement', expanded=True):
                    c1, c2 = st.columns(2)
                    tie_options = ['rectilinear', 'spiral']
                    tie_idx = tie_options.index(sec['tie_type']) if sec['tie_type'] in tie_options else 0
                    sec['tie_type'] = c1.selectbox(
                        'Tie type', tie_options, index=tie_idx, key=f'csec_ttype_{i}',
                        help='**ACI 18.7.5.2** — *rectilinear*: rectangular hoops ± crossties. *spiral*: continuous circular.',
                    )
                    sec['tie_db_mm'] = c2.number_input(
                        'Hoop/tie diameter dbt [mm]', value=float(sec['tie_db_mm']),
                        min_value=6.0, step=2.0, key=f'csec_tdb_{i}',
                        help='**ACI 18.7.5.1** — Min ≥ No.3 (9.5 mm) for longitudinal bars ≤ No.10.',
                    )
                    c3, c4 = st.columns(2)
                    sec['tie_spacing_lo_mm'] = c3.number_input(
                        'Spacing in lo zone [mm]', value=float(sec['tie_spacing_lo_mm']),
                        min_value=25.0, step=25.0, key=f'csec_slo_{i}',
                        help=(
                            '**ACI 18.7.5.3** — Spacing within lo. '
                            'Must not exceed min(b/4, 6db_long, so_eq, 150 mm). '
                            'lo = max(h, ℓclear/6, 450 mm).'
                        ),
                    )
                    sec['tie_spacing_outside_lo_mm'] = c4.number_input(
                        'Spacing outside lo [mm]', value=float(sec['tie_spacing_outside_lo_mm']),
                        min_value=25.0, step=25.0, key=f'csec_solo_{i}',
                        help='**ACI 18.7.5.5** — Must not exceed 6db_long or 150 mm.',
                    )
                    c5, c6 = st.columns(2)
                    sec['crosstie_db_mm'] = c5.number_input(
                        'Crosstie diameter [mm]', value=float(sec['crosstie_db_mm']),
                        min_value=6.0, step=2.0, key=f'csec_ctdb_{i}',
                        help='**ACI 25.7.2** — 135° seismic hook at one end, 90° standard hook at other.',
                    )
                    hook_options = [90.0, 135.0]
                    hook_idx = hook_options.index(sec['hook_angle_deg']) if sec['hook_angle_deg'] in hook_options else 1
                    sec['hook_angle_deg'] = c6.selectbox(
                        'Hook angle [°]', hook_options, index=hook_idx, key=f'csec_hook_{i}',
                        help='**ACI 18.6.4 / 25.3.4** — 135° seismic hook required for SMF.',
                    )
                    c7, c8, c9 = st.columns(3)
                    sec['crosstie_alt_anchorage'] = c7.checkbox(
                        'Alternate anchorage', value=bool(sec['crosstie_alt_anchorage']),
                        key=f'csec_alt_{i}',
                        help=(
                            '**ACI 18.7.5.2(e)** — Crossties alternate 90° hook ends on successive hoops. '
                            'Allows hx ≤ 350 mm (otherwise 200 mm when Pu > 0.3f\'c·Ag).'
                        ),
                    )
                    sec['overlapping_hoops'] = c8.checkbox(
                        'Overlapping hoops', value=bool(sec['overlapping_hoops']),
                        key=f'csec_olap_{i}',
                        help='**ACI 18.7.5.2(b)** — Two single-leg hoops overlapping to enclose section.',
                    )
                    sec['spiral_provided'] = c9.checkbox(
                        'Spiral provided', value=bool(sec['spiral_provided']),
                        key=f'csec_spir_{i}',
                    )

                    st.markdown('---')
                    st.markdown('**Extra legs (crossties)**')
                    st.caption(
                        'The perimeter hoop always provides **2 corner legs** per face. '
                        'Controls: (1) **hx** — max unsupported bar gap; '
                        '(2) **Ash** = n_legs × tie_area; '
                        '(3) **kn** = n_supported/(n_supported − 2).'
                    )
                    cx1, cx2 = st.columns(2)
                    max_lx = max(2, sec['n_bars_x_top'])
                    max_ly = max(2, sec['n_bars_y_left'])
                    n_lx = max(2, min(int(sec['n_legs_x']), max_lx))
                    n_ly = max(2, min(int(sec['n_legs_y']), max_ly))
                    sec['n_legs_x'] = cx1.number_input(
                        'Legs on top/bottom faces  (= 2 corners + n crossties in h-dir)',
                        min_value=2, max_value=max_lx, value=n_lx, step=1,
                        key=f'csec_nlx_{i}',
                        help=(
                            '**ACI 18.7.5.2(e)/(f)** — Total tie legs on top/bottom face. '
                            '2 = hoop only (no crossties). Max = n_bars on that face. '
                            'Determines hx on top/bottom and Ash,x.'
                        ),
                    )
                    sec['n_legs_y'] = cx2.number_input(
                        'Legs on left/right faces  (= 2 corners + n crossties in b-dir)',
                        min_value=2, max_value=max_ly, value=n_ly, step=1,
                        key=f'csec_nly_{i}',
                        help='Total tie legs on left/right face. Determines hx on left/right and Ash,y.',
                    )

                    n_lx_cur = max(2, min(int(sec['n_legs_x']), sec['n_bars_x_top']))
                    n_ly_cur = max(2, min(int(sec['n_legs_y']), sec['n_bars_y_left']))
                    tie_area = math.pi * sec['tie_db_mm'] ** 2 / 4.0
                    hx_top = _hx_from_legs(n_lx_cur, sec['n_bars_x_top'],  sec['b_mm'], sec['cover_mm'], sec['tie_db_mm'], sec['bar_db_mm'])
                    hx_lft = _hx_from_legs(n_ly_cur, sec['n_bars_y_left'], sec['h_mm'], sec['cover_mm'], sec['tie_db_mm'], sec['bar_db_mm'])
                    hx_max = max(hx_top, hx_lft)
                    ash_x = n_lx_cur * tie_area
                    ash_y = n_ly_cur * tie_area

                    fm1, fm2, fm3, fm4 = st.columns(4)
                    fm1.metric('hx_max [mm]', f'{hx_max:.0f}',
                               help='Max gap between consecutive supported bars across all faces.')
                    fm2.metric('so_eq [mm]', f'{max(100, min(150, 100 + (350 - hx_max) / 3)):.0f}',
                               help='ACI 18.7.5.3 — so = 100 + (350−hx)/3, clamped [100, 150] mm.')
                    fm3.metric('Ash,x [mm²]', f'{ash_x:.0f}')
                    fm4.metric('Ash,y [mm²]', f'{ash_y:.0f}')

                    if hx_max > 350.0:
                        st.error(f'❌ hx = {hx_max:.0f} mm > 350 mm — fails ACI 18.7.5.2(e). Add more crossties.')
                    elif hx_max > 200.0:
                        trigger_axial = 0.3 * sec['fc_MPa'] * sec['b_mm'] * sec['h_mm'] / 1e3
                        st.warning(
                            f'⚠️ hx = {hx_max:.0f} mm. If Pu > **{trigger_axial:.0f} kN** '
                            f'(= 0.3f\'cAg), ACI 18.7.5.2(f) requires hx ≤ 200 mm '
                            f'and **all** perimeter bars laterally supported.'
                        )
                    else:
                        st.success(f'✅ hx = {hx_max:.0f} mm ≤ 200 mm — satisfies 18.7.5.2(e) and (f).')

                    n_bars_total = (sec['n_bars_x_top'] + sec['n_bars_x_bottom']
                                    + sec['n_bars_y_left'] + sec['n_bars_y_right'] - 4)
                    n_sup = n_lx_cur + (n_lx_cur - 2) + n_ly_cur + (n_ly_cur - 2) - 4
                    st.caption(
                        f'Approx. {min(n_sup, n_bars_total)}/{n_bars_total} perimeter bars laterally supported. '
                        f'ACI 18.7.5.2(f) requires ALL when Pu > 0.3f\'cAg.'
                    )

                with st.expander('📏 ASCE 41 Splice / Anchorage Parameters', expanded=False):
                    st.caption('Control the plastic rotation model in ASCE 41 Table 10-8.')
                    c1, c2, c3 = st.columns(3)
                    sec['asce_splice_controlled'] = c1.checkbox(
                        'Splice-controlled', value=bool(sec['asce_splice_controlled']),
                        key=f'csec_spl_{i}',
                        help='**ASCE 41 Table 10-8** — Lap splices in hinge zone → uses lower-capacity splice branch.',
                    )
                    sec['asce_splice_two_tie_groups'] = c2.checkbox(
                        'Two tie groups at splice', value=bool(sec['asce_splice_two_tie_groups']),
                        key=f'csec_spl2_{i}',
                        help='**ASCE 41 note (e)** — ≥ 2 tie groups overlap the splice length.',
                    )
                    sec['asce_ties_adequately_anchored'] = c3.checkbox(
                        'Ties adequately anchored', value=bool(sec['asce_ties_adequately_anchored']),
                        key=f'csec_anch_{i}',
                        help='**ASCE 41 note (c)** — True if ALL tie hooks are 135°.',
                    )

            with _col_sketch:
                st.caption('Preview')
                _fig = _draw_column_section(sec)
                st.pyplot(_fig, use_container_width=True)
                plt.close(_fig)

            if len(sections) > 1:
                if st.button(f'🗑 Remove section {i + 1}', key=f'del_csec_{i}'):
                    st.session_state['column_sections'].pop(i)
                    remaining = [s['section_id'] for s in st.session_state['column_sections']]
                    for asm in st.session_state['assemblies']:
                        if asm.get('col_section_id') not in remaining:
                            asm['col_section_id'] = remaining[0] if remaining else ''
                        for adj_key in ('top_other_col_id', 'bottom_other_col_id'):
                            if asm.get(adj_key) not in remaining and asm.get(adj_key) not in ('same', 'none'):
                                asm[adj_key] = 'same'
                    st.rerun()

    if st.button('➕ Add column section'):
        n = len(sections) + 1
        st.session_state['column_sections'].append(_default_column_section(f'COL_SEC_{n}'))
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Tab 2 – Beam Sections (library)
# ─────────────────────────────────────────────────────────────────────────────

def tab_beams() -> None:
    st.subheader('Beam Section Library')
    st.caption(
        'Define beam cross-sections. Each section ID can be assigned to one or more '
        'beam faces inside each assembly.'
    )
    beam_sections: list[dict] = st.session_state['beam_sections']

    for i, bsec in enumerate(beam_sections):
        label = bsec.get('beam_section_id', f'Beam {i+1}')
        with st.expander(f'**{label}**', expanded=(i == 0)):
            bsec['beam_section_id'] = st.text_input(
                'Section ID', value=bsec['beam_section_id'], key=f'bsec_id_{i}',
                help='Unique identifier — used in the Assembly tab to assign to beam faces.',
            )
            _col_form, _col_sketch = st.columns([3, 1])
            with _col_form:
                c1, c2, c3, c4 = st.columns(4)
                bsec['bw_mm'] = c1.number_input(
                    'bw [mm]', value=float(bsec['bw_mm']), min_value=100.0, step=25.0, key=f'bw_{i}',
                    help='**ACI 18.6.2.1** — Web width. SMF: ≥ 0.3h, ≥ 250 mm.',
                )
                bsec['h_mm'] = c2.number_input(
                    'h [mm]', value=float(bsec['h_mm']), min_value=100.0, step=25.0, key=f'bh_{i}',
                    help='Total beam depth. SMF clear span/depth ≥ 4.',
                )
                bsec['cover_mm'] = c3.number_input(
                    'Cover [mm]', value=float(bsec['cover_mm']), min_value=10.0, step=5.0, key=f'bcov_{i}',
                    help='**ACI 20.6.1** — Clear cover to outer stirrup face.',
                )
                bsec['stirrup_db_mm'] = c4.number_input(
                    'Stirrup db [mm]', value=float(bsec['stirrup_db_mm']), min_value=6.0, step=2.0, key=f'bstir_{i}',
                )
                c5, c6, c7 = st.columns(3)
                bsec['fc_MPa'] = c5.number_input(
                    "f'c [MPa]", value=float(bsec['fc_MPa']), min_value=17.0, step=5.0, key=f'bfc_{i}',
                )
                bsec['fy_long_MPa'] = c6.number_input(
                    'fy_long [MPa]', value=float(bsec['fy_long_MPa']), min_value=200.0, step=10.0, key=f'bfy_{i}',
                    help='fye = 1.25fy used for Mpr.',
                )
                bsec['fy_trans_MPa'] = c7.number_input(
                    'fy_trans [MPa]', value=float(bsec['fy_trans_MPa']), min_value=200.0, step=10.0, key=f'bfyt_{i}',
                )
                st.markdown('**Top reinforcement** (hogging)')
                ct1, ct2 = st.columns(2)
                bsec['n_bars_top'] = ct1.number_input(
                    'n bars top', value=int(bsec['n_bars_top']), min_value=2, step=1, key=f'ntop_{i}',
                    help='**ACI 18.6.3.1** — ≥ 2 continuous. Controls Mpr⁻.',
                )
                bsec['db_top_mm'] = ct2.number_input(
                    'db top [mm]', value=float(bsec['db_top_mm']), min_value=6.0, step=2.0, key=f'dbtop_{i}',
                )
                st.markdown('**Bottom reinforcement** (sagging)')
                cb1, cb2 = st.columns(2)
                bsec['n_bars_bot'] = cb1.number_input(
                    'n bars bottom', value=int(bsec['n_bars_bot']), min_value=2, step=1, key=f'nbot_{i}',
                    help='**ACI 18.6.3.2** — Positive Mn at face ≥ ½ max negative Mn along span.',
                )
                bsec['db_bot_mm'] = cb2.number_input(
                    'db bottom [mm]', value=float(bsec['db_bot_mm']), min_value=6.0, step=2.0, key=f'dbbot_{i}',
                )
            with _col_sketch:
                st.caption('Preview')
                _fig = _draw_beam_section(bsec)
                st.pyplot(_fig, use_container_width=True)
                plt.close(_fig)

            if st.button(f'🗑 Remove section {i+1}', key=f'del_bsec_{i}'):
                st.session_state['beam_sections'].pop(i)
                st.rerun()

    if st.button('➕ Add beam section'):
        n = len(st.session_state['beam_sections']) + 1
        st.session_state['beam_sections'].append(
            dict(beam_section_id=f'BEAM_{n}', bw_mm=300.0, h_mm=500.0, cover_mm=40.0,
                 fc_MPa=28.0, fy_long_MPa=420.0, fy_trans_MPa=420.0,
                 n_bars_top=4, db_top_mm=16.0, n_bars_bot=3, db_bot_mm=16.0, stirrup_db_mm=10.0)
        )
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Tab 3 – Assembly (library of column instances)
# ─────────────────────────────────────────────────────────────────────────────

def _render_asm_identity(asm: dict, i: int, sec_ids: list[str]) -> None:
    adj_opts = sec_ids + ['same', 'none']

    c1, c2, c3 = st.columns(3)
    asm['col_id'] = c1.text_input(
        'Column ID (instance)', value=asm['col_id'], key=f'asm_{i}_col_id',
        help='Unique identifier for this column instance. Used in the Loads CSV to link demands.',
    )
    cur_sec = asm.get('col_section_id', sec_ids[0] if sec_ids else '')
    if cur_sec not in sec_ids:
        cur_sec = sec_ids[0] if sec_ids else ''
    asm['col_section_id'] = c2.selectbox(
        'Column section', sec_ids,
        index=sec_ids.index(cur_sec) if cur_sec in sec_ids else 0,
        key=f'asm_{i}_sec_sel',
        help='Cross-section assigned to this instance. Defined in the Column Sections tab.',
    )
    asm['story'] = c3.text_input(
        'Story / Level', value=asm['story'], key=f'asm_{i}_story',
        help='Informational label. Not used in calculations.',
    )

    c4, c5, c6 = st.columns(3)
    frame_opts = ['SMF', 'IMF', 'OMF', 'Gravity']
    ft_idx = frame_opts.index(asm['frame_type']) if asm['frame_type'] in frame_opts else 0
    asm['frame_type'] = c4.selectbox(
        'Frame type', frame_opts, index=ft_idx, key=f'asm_{i}_ftype',
        help=(
            '**ACI 18 / ASCE 7** — Special Moment Frame (SMF), Intermediate (IMF), '
            'Ordinary (OMF), or Gravity. Determines which Chapter 18 checks apply.'
        ),
    )
    asm['clear_height_mm'] = c5.number_input(
        'Clear height [mm]', value=float(asm['clear_height_mm']),
        min_value=500.0, step=100.0, key=f'asm_{i}_height',
        help='**ACI 18.7.5.1** — Clear height between beams/slabs. lo = max(h, ℓclear/6, 450 mm).',
    )

    top_val = asm.get('top_other_col_id', 'same')
    if top_val not in adj_opts:
        top_val = 'same'
    asm['top_other_col_id'] = c6.selectbox(
        'Adjacent column above', adj_opts,
        index=adj_opts.index(top_val), key=f'asm_{i}_top_sel',
        help=(
            '**ACI 18.7.3.2 (SCWB)** — Section of column above this joint. '
            '"same" = this section; "none" = no column above.'
        ),
    )

    c7, c8, c9, c10 = st.columns(4)
    bot_val = asm.get('bottom_other_col_id', 'same')
    if bot_val not in adj_opts:
        bot_val = 'same'
    asm['bottom_other_col_id'] = c7.selectbox(
        'Adjacent column below', adj_opts,
        index=adj_opts.index(bot_val), key=f'asm_{i}_bot_sel',
        help='"same" = this section; "none" = base column.',
    )
    asm['joint_top'] = c8.checkbox(
        'Joint at top', value=bool(asm['joint_top']), key=f'asm_{i}_jt',
        help='**ACI 15.5.2 / 18.8** — True if a beam-column joint exists at top.',
    )
    asm['joint_bottom'] = c9.checkbox(
        'Joint at bottom', value=bool(asm['joint_bottom']), key=f'asm_{i}_jb',
        help='True if a joint exists at bottom. False for base columns.',
    )
    asm['yielding_region_expected'] = c10.checkbox(
        'Yielding region', value=bool(asm['yielding_region_expected']), key=f'asm_{i}_yield',
        help='**ACI 18.7.5** — True: full confinement at ends required.',
    )


def _render_asm_beams(asm: dict, i: int) -> None:
    beam_ids = [b['beam_section_id'] for b in st.session_state['beam_sections']] + ['none']
    for face in BEAM_FACES:
        st.markdown(f'**{FACE_LABELS[face]}**')
        for side in ('side1', 'side2'):
            k = f'{face}_{side}'
            bfd = asm['beam_faces'][k]
            side_label = 'Side 1 (left / near)' if side == 'side1' else 'Side 2 (right / far)'
            cols = st.columns([2, 2, 2, 2, 2, 1])

            cur_id = bfd.get('section_id', 'none')
            if cur_id not in beam_ids:
                cur_id = 'none'
            bfd['section_id'] = cols[0].selectbox(
                side_label, beam_ids, index=beam_ids.index(cur_id),
                key=f'asm_{i}_bf_{k}_sec',
                help='Beam section from the library. "none" = no beam on this side.',
            )
            bfd['ln_mm'] = cols[1].number_input(
                'ℓn [mm]', value=float(bfd['ln_mm']), min_value=0.0, step=100.0,
                key=f'asm_{i}_bf_{k}_ln',
                help='**ACI 18.6.5.1** — Clear span. Ve = (Mpr⁺+Mpr⁻)/ℓn + wu·ℓn/2.',
            )
            bfd['wu_kN_per_m'] = cols[2].number_input(
                'wu [kN/m]', value=float(bfd['wu_kN_per_m']), min_value=0.0, step=1.0,
                key=f'asm_{i}_bf_{k}_wu',
                help='Factored gravity load per unit length. Typical: 15–50 kN/m.',
            )
            bfd['x_mm'] = cols[3].number_input(
                'x [mm]', value=float(bfd['x_mm']), min_value=0.0, step=25.0,
                key=f'asm_{i}_bf_{k}_x',
                help='**ACI R15.5.2.2** — Offset from column face to beam centroid. Aj = b_col×(h_col+x).',
            )
            bfd['ext_mm'] = cols[4].number_input(
                'ext [mm]', value=float(bfd['ext_mm']), min_value=0.0, step=25.0,
                key=f'asm_{i}_bf_{k}_ext',
                help='**ACI 15.5.2.5(c)** — Beam extension beyond far joint face. ≥ h_beam required.',
            )
            bfd['continuous'] = cols[5].checkbox(
                'Cont.', value=bool(bfd['continuous']),
                key=f'asm_{i}_bf_{k}_cont',
                help='**ACI 18.6.3** — True if bars are continuous through joint.',
            )
        st.divider()


def _render_asm_loads(asm: dict, i: int) -> None:
    st.caption(
        'Factored demand values per load combination. '
        'RotX / RotY are plastic chord rotations from nonlinear analysis '
        '(compared to ASCE 41 Table 10-8 acceptance criteria).'
    )
    load_cases: list[dict] = asm['load_cases']

    for j, lc in enumerate(load_cases):
        label = lc.get('load_case', f'Case {j+1}')
        with st.expander(f'**{label}**', expanded=(j == 0)):
            c1, c2 = st.columns([3, 1])
            lc['load_case'] = c1.text_input(
                'Load case name', value=lc['load_case'], key=f'asm_{i}_lc_{j}_name',
                help='Label (e.g. "1.2D+1.6L", "RSA_X+0.3Y+0.5D").',
            )
            ds_opts = ['IO', 'LS', 'CP']
            ds_idx = ds_opts.index(lc['damage_state']) if lc['damage_state'] in ds_opts else 2
            lc['damage_state'] = c2.selectbox(
                'Damage state', ds_opts, index=ds_idx, key=f'asm_{i}_lc_{j}_ds',
                help=(
                    '**ASCE 41 §2.4.1** — Performance level:\n'
                    '- **IO**: θ_IO = 0.10 × θ_b\n'
                    '- **LS**: θ_LS = 0.50 × θ_b\n'
                    '- **CP**: θ_CP = 0.70 × θ_b'
                ),
            )
            c3, c4, c5, c6, c7 = st.columns(5)
            lc['Pu_kN'] = c3.number_input(
                'Pu [kN]', value=float(lc['Pu_kN']), step=100.0,
                key=f'asm_{i}_lc_{j}_pu',
                help='Factored axial. **Positive = compression**. Affects φ factor and Vc.',
            )
            lc['Mux_kNm'] = c4.number_input(
                'Mux [kN·m]', value=float(lc['Mux_kNm']), step=50.0,
                key=f'asm_{i}_lc_{j}_mux',
                help='Factored moment about x-axis. Compared to φMn,x(Pu).',
            )
            lc['Muy_kNm'] = c5.number_input(
                'Muy [kN·m]', value=float(lc['Muy_kNm']), step=50.0,
                key=f'asm_{i}_lc_{j}_muy',
            )
            lc['Vux_kN'] = c6.number_input(
                'Vux [kN]', value=float(lc['Vux_kN']), step=10.0,
                key=f'asm_{i}_lc_{j}_vux',
                help='Factored shear x. Vc may be zeroed per ACI 18.7.6.2.',
            )
            lc['Vuy_kN'] = c7.number_input(
                'Vuy [kN]', value=float(lc['Vuy_kN']), step=10.0,
                key=f'asm_{i}_lc_{j}_vuy',
            )
            cr1, cr2 = st.columns(2)
            lc['RotX'] = cr1.number_input(
                'RotX [rad]', value=float(lc['RotX']), format='%.5f', step=0.001,
                key=f'asm_{i}_lc_{j}_rotx',
                help='**ASCE 41 §10.4.2.2** — Plastic chord rotation demand about x from nonlinear analysis.',
            )
            lc['RotY'] = cr2.number_input(
                'RotY [rad]', value=float(lc['RotY']), format='%.5f', step=0.001,
                key=f'asm_{i}_lc_{j}_roty',
            )
            if st.button(f'🗑 Remove case {j+1}', key=f'asm_{i}_del_lc_{j}'):
                asm['load_cases'].pop(j)
                st.rerun()

    if st.button('➕ Add load case', key=f'asm_{i}_add_lc'):
        n = len(load_cases) + 1
        asm['load_cases'].append(
            dict(load_case=f'U{n}', Pu_kN=0.0, Mux_kNm=0.0, Muy_kNm=0.0,
                 Vux_kN=0.0, Vuy_kN=0.0, RotX=0.0, RotY=0.0, damage_state='CP')
        )
        st.rerun()


def tab_assembly() -> None:
    st.subheader('Column Instance Library')
    st.caption(
        'Define one or more column instances. Each instance has its own section assignment, '
        'story, frame type, beam connections, and load cases. '
        'All instances are run together when you click **▶ Run Checks**.'
    )

    assemblies: list[dict] = st.session_state['assemblies']
    sec_ids = [sec['section_id'] for sec in st.session_state['column_sections']]

    for i, asm in enumerate(assemblies):
        label = (
            f"**{asm['col_id']}**  —  "
            f"Story {asm['story']}  |  {asm['frame_type']}  |  "
            f"Section: {asm.get('col_section_id', '?')}"
        )
        with st.expander(label, expanded=(i == 0)):
            sub_id, sub_beams, sub_loads = st.tabs([
                '📍 Identity & Geometry',
                '🔗 Connected Beams',
                '📋 Load Cases',
            ])
            with sub_id:
                _render_asm_identity(asm, i, sec_ids)
            with sub_beams:
                _render_asm_beams(asm, i)
            with sub_loads:
                _render_asm_loads(asm, i)

            if len(assemblies) > 1:
                if st.button(f'🗑 Remove instance {i + 1}', key=f'del_asm_{i}'):
                    st.session_state['assemblies'].pop(i)
                    st.rerun()

    if st.button('➕ Add column instance'):
        n = len(assemblies) + 1
        first_sec = sec_ids[0] if sec_ids else 'COL_SEC_1'
        st.session_state['assemblies'].append(_default_assembly(f'COL_{n}', first_sec))
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Tab 4 – Results
# ─────────────────────────────────────────────────────────────────────────────

STATUS_ICON = {'OK': '🟢', 'NG': '🔴', 'WARNING': '🟡', 'INFO': '🔵'}


def tab_results() -> None:
    st.subheader('Run & Results')

    with st.expander('📄 Report options', expanded=False):
        _ro1, _ro2 = st.columns(2)
        st.session_state['report_requested'] = _ro1.checkbox(
            'Generate summary report',
            value=st.session_state.get('report_requested', False),
            help='Concise report: input summary, capacities, checks, P-M diagrams.',
        )
        st.session_state['report_detailed_requested'] = _ro2.checkbox(
            'Generate detailed report',
            value=st.session_state.get('report_detailed_requested', False),
            help='Step-by-step calculations with equations — for learning and verification.',
        )
        _any_report = st.session_state['report_requested'] or st.session_state['report_detailed_requested']
        if _any_report:
            all_col_ids = [asm['col_id'] for asm in st.session_state['assemblies']]
            stored = [c for c in st.session_state.get('report_columns', []) if c in all_col_ids]
            default_sel = stored if stored else all_col_ids
            st.session_state['report_columns'] = st.multiselect(
                'Generate report for',
                options=all_col_ids,
                default=default_sel,
                help='Select column instances. Applies to both report types.',
            )
        st.session_state['project_name'] = st.text_input(
            'Project name (appears in report header)',
            value=st.session_state.get('project_name', ''),
            help='Optional. Passed as --pry-name.',
        )
        st.caption(
            '⚠️ Report generation includes P-M diagram export (slower). '
            'Uncheck when iterating quickly.'
        )

    run = st.button('▶ Run Checks', type='primary')
    if run:
        with st.spinner('Running calculations…'):
            try:
                _run_pipeline()
            except Exception as exc:
                st.error(f'Error: {exc}')
                return

    if '_results' not in st.session_state:
        st.info(
            'Complete the **Column Sections**, **Beam Sections**, and **Assembly** tabs, '
            'then click **▶ Run Checks**.'
        )
        return

    results  = st.session_state['_results']
    checks   = st.session_state['_checks']
    failures = st.session_state['_failures']

    n_ng   = sum(1 for r in checks if r['status'] == 'NG')
    n_warn = sum(1 for r in checks if r['status'] == 'WARNING')
    n_ok   = sum(1 for r in checks if r['status'] == 'OK')
    n_info = sum(1 for r in checks if r['status'] == 'INFO')
    n_cols = len({r['column_id'] for r in checks}) if checks else 0

    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric('🟢 OK',       n_ok)
    mc2.metric('🔴 NG',       n_ng)
    mc3.metric('🟡 Warnings', n_warn)
    mc4.metric('🔵 Info',     n_info)

    if n_ng > 0:
        st.error(f'{n_ng} FAILED check(s) across {n_cols} column instance(s) — see details below.')
    elif n_warn > 0:
        st.warning(f'All strength checks PASSED with {n_warn} warning(s) across {n_cols} instance(s).')
    else:
        st.success(f'All checks PASSED for all {n_cols} column instance(s).')

    try:
        import pandas as pd
        HAS_PANDAS = True
    except ImportError:
        HAS_PANDAS = False

    with st.expander('📊 Capacity & Demand by Column / Load Case', expanded=True):
        key_cols = [
            'column_id', 'load_case', 'damage_state',
            'phiPn0_kN', 'rho_long',
            'phiMn_x_kNm', 'phiMn_y_kNm',
            'phiVn_x_kN', 'phiVn_y_kN',
            'pm_ratio_x', 'pm_ratio_y',
            'shear_ratio_x', 'shear_ratio_y',
            'probable_shear_ratio_x', 'probable_shear_ratio_y',
            'asce41_rot_ratio_x', 'asce41_rot_ratio_y',
        ]
        if HAS_PANDAS:
            df = pd.DataFrame(results)
            avail = [c for c in key_cols if c in df.columns]
            st.dataframe(df[avail], use_container_width=True)
        else:
            st.json(results)

    if failures:
        with st.expander(f'❌ Failures & Warnings  ({len(failures)} items)', expanded=True):
            if HAS_PANDAS:
                st.dataframe(pd.DataFrame(failures), use_container_width=True)
            else:
                for row in failures:
                    icon = STATUS_ICON.get(row['status'], '⚪')
                    st.markdown(
                        f"{icon} **{row['column_id']} / {row['check_name']}** — "
                        f"provided={row['provided']}  required={row['required']}  "
                        f"({row['code_ref']})"
                    )

    with st.expander('🔍 All Checks (detailed)'):
        if HAS_PANDAS:
            df_all = pd.DataFrame(checks)
            df_all.insert(0, '', df_all['status'].map(lambda s: STATUS_ICON.get(s, '⚪')))
            st.dataframe(df_all, use_container_width=True)
        else:
            st.json(checks)

    st.subheader('Download Results')
    dc1, dc2, dc3 = st.columns(3)
    dc1.download_button(
        '⬇ column_results.csv', data=st.session_state['_csv_results'],
        file_name='column_results.csv', mime='text/csv',
    )
    dc2.download_button(
        '⬇ column_checks.csv', data=st.session_state['_csv_checks'],
        file_name='column_checks.csv', mime='text/csv',
    )
    dc3.download_button(
        '⬇ column_failures.csv', data=st.session_state['_csv_failures'],
        file_name='column_failures.csv', mime='text/csv',
    )

    pdf      = st.session_state.get('_pdf_bytes')
    pdf_name = st.session_state.get('_tex_filename') or 'report_memoria.pdf'
    pdf_det      = st.session_state.get('_pdf_det_bytes')
    pdf_det_name = st.session_state.get('_pdf_det_filename') or 'report_detailed.pdf'

    if pdf or pdf_det:
        st.subheader('📄 PDF Reports')
        dl1, dl2 = st.columns(2)
        if pdf:
            is_zip = pdf_name.endswith('.zip')
            dl1.download_button(
                '⬇ Summary report' + (' (.zip)' if is_zip else ' (.pdf)'),
                data=pdf,
                file_name=pdf_name,
                mime='application/zip' if is_zip else 'application/pdf',
                help='Concise report: input summary, capacities, checks, and P-M diagrams.',
            )
        if pdf_det:
            is_zip_det = pdf_det_name.endswith('.zip')
            dl2.download_button(
                '⬇ Detailed report' + (' (.zip)' if is_zip_det else ' (.pdf)'),
                data=pdf_det,
                file_name=pdf_det_name,
                mime='application/zip' if is_zip_det else 'application/pdf',
                help='Step-by-step calculations with equations — intended for learning and verification.',
            )
    elif st.session_state.get('report_requested'):
        st.warning('Report was requested but no PDF was generated. Check the calculation log.')

    with st.expander('🖥 Calculation log'):
        st.code(st.session_state.get('_stdout', ''))


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline helpers
# ─────────────────────────────────────────────────────────────────────────────

def _run_pipeline() -> None:
    generate_report          = bool(st.session_state.get('report_requested', False))
    generate_detailed_report = bool(st.session_state.get('report_detailed_requested', False))
    project_name             = str(st.session_state.get('project_name', '')).strip()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        col_sec  = tmp / 'col_sections.csv'
        beam_sec = tmp / 'beam_sections.csv'
        col_beam = tmp / 'col_beam.csv'
        loads_f  = tmp / 'loads.csv'
        outdir   = tmp / 'out'
        outdir.mkdir()

        # Pre-generate section PNGs from live session state so the PDF report
        # contains exactly the sketch shown in the Column Sections preview tab.
        # pm_diagram.export_section_sketch will skip regenerating if the file exists.
        _sec_lookup = {s['section_id']: s for s in st.session_state['column_sections']}
        _sections_dir = outdir / 'sections'
        _sections_dir.mkdir(parents=True, exist_ok=True)
        for _asm in st.session_state['assemblies']:
            _sec = _sec_lookup.get(str(_asm.get('col_section_id', '')))
            if _sec is None:
                continue
            _slug = re.split(
                r'_chain|_st\d+|_story\d+',
                str(_asm['col_id']).strip(), maxsplit=1,
            )[0].replace('_', '')
            _fig = _draw_column_section(_sec)
            _fig.savefig(str(_sections_dir / f'{_slug}.png'), dpi=150, bbox_inches='tight')
            plt.close(_fig)

        _write_column_sections_csv(col_sec)
        _write_beam_sections_csv(beam_sec)
        _write_column_beam_csv(col_beam)
        _write_loads_csv(loads_f)

        cmd = [
            sys.executable, str(ROOT / 'main.py'),
            '--column-sections', str(col_sec),
            '--beam-sections',   str(beam_sec),
            '--column-beam',     str(col_beam),
            '--loads',           str(loads_f),
            '--outdir',          str(outdir),
        ]
        selected_cols = st.session_state.get('report_columns', [])
        all_col_ids   = [asm['col_id'] for asm in st.session_state['assemblies']]
        _all_selected = not selected_cols or set(selected_cols) >= set(all_col_ids)
        if generate_report:
            cmd += ['--report-all'] if _all_selected else ['--report-columns', ','.join(selected_cols)]
        if generate_detailed_report:
            cmd += ['--detailed-report-all'] if _all_selected else ['--detailed-report-columns', ','.join(selected_cols)]
        if (generate_report or generate_detailed_report) and project_name:
            cmd += ['--pry-name', project_name]
        if not generate_report and not generate_detailed_report:
            cmd += ['--skip-pm']

        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))

        if proc.returncode != 0:
            raise RuntimeError(
                f'main.py exited with code {proc.returncode}.\n'
                f'{proc.stderr or proc.stdout}'
            )

        def _read(p: Path) -> list[dict]:
            with p.open(newline='', encoding='utf-8') as f:
                return list(csv.DictReader(f))

        st.session_state['_results']      = _read(outdir / 'column_results.csv')
        st.session_state['_checks']       = _read(outdir / 'column_checks.csv')
        st.session_state['_failures']     = _read(outdir / 'column_failures.csv')
        st.session_state['_stdout']       = proc.stdout
        st.session_state['_csv_results']  = (outdir / 'column_results.csv').read_text(encoding='utf-8')
        st.session_state['_csv_checks']   = (outdir / 'column_checks.csv').read_text(encoding='utf-8')
        st.session_state['_csv_failures'] = (outdir / 'column_failures.csv').read_text(encoding='utf-8')

        st.session_state['_tex_content']      = None
        st.session_state['_tex_filename']     = None
        st.session_state['_pdf_bytes']        = None
        st.session_state['_pdf_compiled']     = False
        st.session_state['_pdf_det_bytes']    = None
        st.session_state['_pdf_det_filename'] = None

        if generate_report:
            report_dir = outdir / 'latex_reports'
            # Summary reports (*_memoria.pdf)
            summary_pdfs = sorted(report_dir.glob('*_memoria.pdf')) if report_dir.exists() else []
            if len(summary_pdfs) == 1:
                st.session_state['_pdf_bytes']    = summary_pdfs[0].read_bytes()
                st.session_state['_tex_filename'] = summary_pdfs[0].name
                st.session_state['_pdf_compiled'] = True
            elif len(summary_pdfs) > 1:
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for pf in summary_pdfs:
                        zf.write(pf, pf.name)
                st.session_state['_pdf_bytes']    = buf.getvalue()
                st.session_state['_tex_filename'] = 'column_reports.zip'
                st.session_state['_pdf_compiled'] = True
            # Detailed step-by-step reports (*_detailed.pdf)
            det_pdfs = sorted(report_dir.glob('*_detailed.pdf')) if report_dir.exists() else []
            if len(det_pdfs) == 1:
                st.session_state['_pdf_det_bytes']    = det_pdfs[0].read_bytes()
                st.session_state['_pdf_det_filename'] = det_pdfs[0].name
            elif len(det_pdfs) > 1:
                buf2 = io.BytesIO()
                with zipfile.ZipFile(buf2, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for pf in det_pdfs:
                        zf.write(pf, pf.name)
                st.session_state['_pdf_det_bytes']    = buf2.getvalue()
                st.session_state['_pdf_det_filename'] = 'column_reports_detailed.zip'


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    _favicon = ROOT / 'assets' / 'logo_browser.PNG'
    st.set_page_config(
        page_title='RC Column Checker',
        page_icon=str(_favicon) if _favicon.exists() else '🏗️',
        layout='wide',
        initial_sidebar_state='collapsed',
    )
    _init_state()

    _col_title, _col_logo = st.columns([3, 1])
    with _col_title:
        st.title('RC Column Checker')
        st.caption('ACI 318-22 / ASCE 41  ·  Interactive verification tool')
    with _col_logo:
        logo_path = ROOT / 'assets' / 'Logo_horizontal_Torrefuerte.png'
        if logo_path.exists():
            st.markdown(
                '<p style="text-align:right; color:#999999; font-size:0.75rem; '
                'margin-bottom:2px;">powered by</p>',
                unsafe_allow_html=True,
            )
            st.image(str(logo_path), use_container_width=True)

    st.warning(
        '**⚠️ Beta version — not extensively validated.**  '
        'This application is under active development and **has not been exhaustively validated**. '
        'Results must be reviewed and verified by a qualified structural engineer '
        'before use in any real project. '
        'Torrefuerte-Estructural assumes no responsibility for the use of this tool.',
    )

    with st.expander('💾 Project file  —  save / load', expanded=False):
        _project_io_panel()

    st.markdown("""
<style>
/* ── Main navigation tabs ─────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 3px;
    padding: 0 2px;
    border-bottom: 2px solid #d0d0d0;
}
.stTabs [data-baseweb="tab"] {
    height: auto;
    padding: 10px 26px;
    font-size: 1.05rem;
    font-weight: 700;
    letter-spacing: 0.01em;
    color: #666666;
    background-color: #f2f2f2;
    border-radius: 6px 6px 0 0;
    border: 1px solid #d8d8d8;
    border-bottom: none;
    margin-bottom: -2px;
    transition: background-color 0.15s, color 0.15s;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #1a1a1a;
    background-color: #e6e6e6;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    color: #1a1a1a !important;
    background-color: #ffffff !important;
    border-color: #d0d0d0 !important;
    border-bottom: 3px solid #1a1a1a !important;
}
</style>
""", unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs([
        '🏛️ Column Sections',
        '📏 Beam Sections',
        '🏗️ Assembly',
        '📊 Results',
    ])
    with tab1:
        tab_section()
    with tab2:
        tab_beams()
    with tab3:
        tab_assembly()
    with tab4:
        tab_results()

    st.markdown("""
<hr style="margin-top:2.5rem; border:none; border-top:1px solid #e0e0e0;">
<div style="text-align:center; color:#999999; font-size:0.78rem;
            padding:6px 0 20px 0; line-height:2.0;">
    &copy; 2026 &nbsp;<strong style="color:#666666;">Torrefuerte-Estructural</strong>
    &nbsp;&bull;&nbsp;
    <a href="https://www.torrefuerte.ec" target="_blank"
       style="color:#666666; text-decoration:none;">www.torrefuerte.ec</a>
    &nbsp;&bull;&nbsp; All rights reserved
    <br>
    <span style="font-size:0.72rem;">
        RC Column Verification Tool &mdash;
        ACI&nbsp;318-22&nbsp;/&nbsp;ASCE&nbsp;41 &mdash; Beta version
    </span>
</div>
""", unsafe_allow_html=True)


if __name__ == '__main__':
    main()
