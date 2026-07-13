# RC Column Checker

A structural verification tool for reinforced concrete columns under seismic loading. Available as a **browser-based web app** (Streamlit) and a **command-line interface**. Implements **ACI 318-25** and **ASCE 41** checks for all four column classes — **special (SMF), intermediate (IMF), and ordinary (OMF) moment frames, plus gravity columns (18.14)** — and produces CSV result tables, P-M interaction diagrams, cross-section sketches, and two PDF report formats: a concise summary report and a detailed step-by-step educational report — both generated with ReportLab (no LaTeX required).

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Requirements](#requirements)
3. [Installation](#installation)
4. [Quick Start](#quick-start)
5. [Streamlit GUI](#streamlit-gui)
6. [CLI Arguments](#cli-arguments)
7. [Input Files](#input-files)
   - [Column Sections CSV](#1-column-sections-csv)
   - [Beam Sections CSV](#2-beam-sections-csv)
   - [Column-Beam Properties CSV](#3-column-beam-properties-csv)
   - [Loads CSV](#4-loads-csv)
8. [Output Files](#output-files)
   - [column\_results.csv](#column_resultscsv)
   - [column\_checks.csv](#column_checkscsv)
   - [column\_failures.csv](#column_failurescsv)
   - [P-M Diagrams](#pm-diagrams)
   - [Reports (PDF)](#reports-pdf)
9. [Implemented Checks](#implemented-checks)
   - [Frame types (SMF / IMF / OMF / Gravity)](#frame-types-smf--imf--omf--gravity)
   - [ACI 318-25: Longitudinal Reinforcement](#aci-318-25-longitudinal-reinforcement)
   - [ACI 318-25: Transverse Reinforcement](#aci-318-25-transverse-reinforcement)
   - [ACI 318-25: Flexure and Axial Capacity](#aci-318-25-flexure-and-axial-capacity)
   - [ACI 318-25: Seismic Shear](#aci-318-25-seismic-shear)
   - [ACI 318-25: Strong Column Weak Beam](#aci-318-25-strong-column-weak-beam)
   - [ACI 318-25: Joint Shear](#aci-318-25-joint-shear)
   - [ACI 318-25: Gravity Columns (18.14.3)](#aci-318-25-gravity-columns-18143)
   - [ASCE 41: Plastic Rotation Acceptance Criteria](#asce-41-plastic-rotation-acceptance-criteria)
10. [Code Architecture](#code-architecture)
11. [Notes and Limitations](#notes-and-limitations)

---

## What It Does

RC Column Checker takes a **project `.json` file** (the GUI save format) or four CSV input files describing column sections, beam sections, column-to-beam joint assemblies, and load combinations. For each column under each load case, it:

- Computes geometric properties (gross area, confined core area, reinforcement ratios, maximum unsupported bar spacing).
- Builds the biaxial P-M interaction surface using strain-compatibility analysis with a Whitney stress block.
- Calculates nominal, probable, and design-level flexural and shear capacities.
- Evaluates beam-column joint shear demand and capacity with the φ factor, Vn coefficient table, and demand basis (1.25fy vs fy) selected by frame type.
- Applies the strong-column weak-beam (SCWB) rule (SMF columns).
- Runs the ACI 318-25 detailing checks applicable to the column's frame type — SMF (18.7/18.8), IMF (18.4), OMF (18.3 + Ch. 10), or gravity (18.14).
- Computes ASCE 41 plastic rotation parameters and checks demand against IO / LS / CP acceptance criteria.
- Exports results to CSV tables, SVG/PDF/PNG P-M diagrams, cross-section sketch PNGs, and two PDF report formats.

---

## Requirements

- **Python 3.11 or later** (required — ReportLab uses `hashlib` features introduced in 3.11)
- `matplotlib`
- `numpy`
- `pandas`
- `reportlab` — PDF report generation (pure Python, no system dependencies)
- `streamlit` — web GUI

All packages are listed in `requirements.txt`. Install them with:

```bash
pip install -r requirements.txt
```

**Optional — LaTeX source compilation (CLI only):**
A TeX distribution (`pdflatex` / `latexmk`) to compile the `.tex` source output. The PDF report itself does **not** require LaTeX.

---

## Installation

```bash
git clone https://github.com/JosePovedaHinojosa/rc-column-checker.git
cd rc-column-checker
pip install -r requirements.txt
```

No build step is needed. All calculation logic is in pure Python.

---

## Quick Start

Run one of the bundled example projects (see [`inputs-tests/`](inputs-tests/)):

```bash
python main.py --project inputs-tests/smf_interior_column.json --outdir outputs
```

This creates an `outputs/` directory containing:

```
outputs/
├── _project_csvs/            # The four solver CSVs generated from the .json
├── column_results.csv        # Capacity and demand summary (one row per load case)
├── column_checks.csv         # All individual checks with status OK / NG / WARNING / INFO
└── column_failures.csv       # Subset of checks with status NG or WARNING only
```

With `--report-columns` or `--report-all`, additional subdirectories are created:

```
outputs/
├── ...
├── sections/
│   └── SMF-C1.png                       # Auto-generated cross-section sketch
├── pm_diagrams/
│   ├── SMF-C1_PM_x.svg/.pdf/.png
│   └── SMF-C1_PM_y.svg/.pdf/.png
└── latex_reports/
    ├── SMF-C1_memoria.pdf               # Summary report (ReportLab)
    ├── SMF-C1_memoria.tex               # LaTeX source (optional, for pdflatex)
    └── SMF-C1_detailed.pdf              # Step-by-step educational report (ReportLab)
```

Generate PDF reports for all columns:

```bash
python main.py --project inputs-tests/smf_interior_column.json --outdir outputs --report-all --detailed-report-all
```

The four CSVs can still be passed individually instead of `--project` (see [CLI Arguments](#cli-arguments)).

### Example projects (`inputs-tests/`)

One realistic case per ACI 318-25 column class — open them in the GUI (**Load project**) or run them from the CLI with `--project`:

| File | Frame type | Scenario |
|---|---|---|
| `smf_interior_column.json` | **SMF** | 600×600 interior column of an 8-story office (SDC D): Mpr shear, SCWB, Table 18.7.5.4 confinement, joint φ = 0.85 with 1.25fy demand, 18.8.2.3 joint depth |
| `imf_edge_column.json` | **IMF** | 500×500 edge column, 4-story clinic (SDC C): Mn hinging shear (18.4.3.1a), 18.4.3.3 hoop limits, joint φ = 0.75 with fy demand |
| `omf_lowrise_column.json` | **OMF** | 400×400 two-story commercial (SDC B), two columns: a slender one where 18.3.3 does not apply (ℓu > 5c1) and a squat basement column where it governs |
| `gravity_column_sdc_d.json` | **Gravity** | 350×350 flat-plate parking column in an SDC D building: 18.14 full-height ties, Pu > 0.35Po trigger, drift-induced ASCE 41 rotation demand |

---

## Streamlit GUI

`app.py` provides a browser-based interface covering the same calculation pipeline as `main.py`. It is also deployed on Streamlit Cloud.

### Launching locally

```bash
python -m streamlit run app.py
```

Streamlit opens a browser tab automatically (default `http://localhost:8501`). Stop the server with **Ctrl+C** in the terminal.

### Tabs

| Tab | Purpose |
|---|---|
| **Column Section** | Define column cross-sections: dimensions, materials, longitudinal reinforcement (bar count and diameter per face), and transverse reinforcement (hoop type, diameter, spacing, hook angle, crossties). A live cross-section sketch updates in real time alongside the form. |
| **Beam Sections** | Define beam cross-sections. A live section sketch is shown alongside the form. |
| **Assembly** | Assemble the column instance: story, frame type, clear height, adjacent column sections, and all eight beam slot assignments (four joint faces × two sides). |
| **Loads** | Enter factored load combinations (Pu, Mux, Muy, Vux, Vuy, RotX, RotY) and ASCE 41 performance level (IO / LS / CP) per case. |
| **Results** | Run the full pipeline and view colour-coded output. Download CSV results, summary PDF, and detailed PDF reports. |

### Report generation

Expand the **Report options** section on the Results tab before clicking **▶ Run Checks**:

- Toggle **Generate PDF report** to produce reports.
- Use the multiselect to choose which column instances get a report (all selected = all columns).
- Enter an optional **Project name** for the report header.

Once the run completes, two download buttons appear side by side:

| Button | File | Contents |
|---|---|---|
| **⬇ Summary report** | `*_memoria.pdf` | Input summary, capacities, checks table, P-M diagrams |
| **⬇ Detailed report** | `*_detailed.pdf` | Step-by-step calculations with equations for every check (educational) |

If more than one column was selected, all PDFs of each type are bundled into separate `.zip` archives automatically.

### Save / Load projects

Use the **💾 Project file — save / load** panel above the tabs to export the current session as a JSON file, or load a previously saved project. Loading a new project clears all previous results automatically.

---

## CLI Arguments

| Argument | Required | Default | Description |
|---|---|---|---|
| `--project PATH` | Yes* | — | Project `.json` file (GUI save format); replaces the four CSV arguments |
| `--column-sections PATH` | Yes* | — | CSV library of column cross-sections |
| `--beam-sections PATH` | Yes* | — | CSV library of beam cross-sections |
| `--column-beam PATH` | Yes* | — | CSV of column instances and joint assemblies |
| `--loads PATH` | Yes* | — | CSV of load combinations per column |
| `--outdir PATH` | No | `outputs` | Output directory (created if absent) |
| `--skip-pm` | No | off | Skip P-M diagram generation |
| `--report-columns COL1,COL2` | No | — | Generate reports only for listed `column_id` values |
| `--report-all` | No | off | Generate reports for every column |
| `--pry-name "Name"` | No | — | Project name shown in report headers |
| `--hide-rotation-table` | No | off | Omit the ASCE 41 rotation table from summary reports |
| `--hide-beam-table` | No | off | Omit the connected beam capacity table from summary reports |
| `--hide-joint-table` | No | off | Omit the joint shear capacity table from summary reports |

\* Provide either `--project` **or** all four CSV arguments.

---

## Input Files

The tool requires **four CSV files**. All use comma-separated format with a header row. Unrecognised columns are ignored. Fields marked *optional* have internal defaults and may be omitted from the CSV.

---

### 1. Column Sections CSV

Defines a reusable library of column cross-sections. One row per section ID.

**Example:** generated automatically from any `inputs-tests/*.json` under `outputs/_project_csvs/col_sections.csv`

#### Geometry and Materials

| Field | Type | Description |
|---|---|---|
| `column_section_id` | string | Unique section identifier |
| `b_mm` | float | Width of section (mm) |
| `h_mm` | float | Height of section (mm) |
| `cover_mm` | float | Clear cover to transverse reinforcement (mm) |
| `fc_MPa` | float | Concrete compressive strength f'c (MPa) |
| `fy_long_MPa` | float | Yield strength of longitudinal steel (MPa) |
| `fy_trans_MPa` | float | Yield strength of transverse steel (MPa) |

#### Longitudinal Reinforcement

| Field | Type | Description |
|---|---|---|
| `n_bars_x_top` | int | Number of bars on the top face (parallel to x-axis) |
| `n_bars_x_bottom` | int | Number of bars on the bottom face |
| `n_bars_y_left` | int | Number of bars on the left face (parallel to y-axis) |
| `n_bars_y_right` | int | Number of bars on the right face |
| `bar_db_mm` | float | Longitudinal bar diameter (mm) |

The model places bars along the perimeter using the four face counts. Corner bars are shared, so the total bar count is `(n_bars_x_top - 2) + (n_bars_x_bottom - 2) + n_bars_y_left + n_bars_y_right + 4` (minimum 4).

#### Transverse Reinforcement

| Field | Type | Description |
|---|---|---|
| `tie_type` | string | `rectilinear`, `circular`, or `spiral` |
| `tie_db_mm` | float | Hoop/tie bar diameter (mm) |
| `tie_spacing_lo_mm` | float | Tie spacing within the confinement region *lo* (mm) |
| `tie_spacing_outside_lo_mm` | float | Tie spacing outside *lo* (mm) |
| `crosstie_db_mm` | float | Crosstie bar diameter (mm) |
| `hook_angle_deg` | float | Hook angle for ties (typically 135) |
| `crosstie_alt_anchorage` | bool | `True` if consecutive crossties alternate end-for-end (ACI 18.7.5.2(c)) |
| `overlapping_hoops` | bool | `True` if overlapping hoops are used instead of crossties |
| `spiral_provided` | bool | `True` if continuous spiral is provided |

#### Lateral Support Lines

These define the positions of intermediate hoops and crossties along each face, used to compute the maximum unsupported bar spacing *hx*.

| Field | Format | Description |
|---|---|---|
| `support_lines_top_mm` | `"v1;v2;v3;..."` | Distances from the left edge of the top face where lateral support is provided (mm) |
| `support_lines_bottom_mm` | `"v1;v2;..."` | Same for bottom face |
| `support_lines_left_mm` | `"v1;v2;..."` | Distances from bottom edge on left face |
| `support_lines_right_mm` | `"v1;v2;..."` | Distances from bottom edge on right face |

#### ASCE 41 Parameters (Optional)

| Field | Default | Description |
|---|---|---|
| `asce_fye_factor` | `1.25` | Expected/nominal strength ratio for longitudinal steel (*fye/fy*) |
| `asce_fyte_factor` | `1.25` | Expected/nominal strength ratio for transverse steel (*fyte/fyt*) |
| `asce_splice_controlled` | `False` | `True` if lap splices control rotational behavior |
| `asce_splice_two_tie_groups` | `True` | `True` if two or more tie groups overlap the splice |
| `asce_ties_adequately_anchored` | `True` | `True` if ties at the splice are adequately anchored |

#### Normative Defaults (Optional Overrides)

| Field | Default | Description |
|---|---|---|
| `min_dim_required_mm` | `300` | Minimum column dimension (project rule) |
| `rho_min` | `0.01` | Minimum longitudinal reinforcement ratio |
| `rho_max` | `0.08` | Maximum longitudinal reinforcement ratio |
| `n_bars_min_rect` | `4` | Minimum number of bars for rectangular section |
| `free_spacing_min_mm` | `40` | Minimum clear spacing between longitudinal bars |

---

### 2. Beam Sections CSV

Defines a reusable library of beam cross-sections.

**Example:** generated automatically from any `inputs-tests/*.json` under `outputs/_project_csvs/beam_sections.csv`

| Field | Type | Description |
|---|---|---|
| `beam_section_id` | string | Unique section identifier |
| `bw_mm` | float | Web width (mm) |
| `h_mm` | float | Total depth (mm) |
| `cover_mm` | float | Clear cover (mm) |
| `fc_MPa` | float | Concrete compressive strength (MPa) |
| `fy_long_MPa` | float | Yield strength of longitudinal steel (MPa) |
| `fy_trans_MPa` | float | Yield strength of transverse steel (MPa) |
| `n_bars_top` | int | Number of top longitudinal bars |
| `db_top_mm` | float | Top bar diameter (mm) |
| `n_bars_bot` | int | Number of bottom longitudinal bars |
| `db_bot_mm` | float | Bottom bar diameter (mm) |
| `stirrup_db_mm` | float | Stirrup bar diameter (mm) |

---

### 3. Column-Beam Properties CSV

One row per column instance. References a column section and defines the structural context.

**Example:** generated automatically from any `inputs-tests/*.json` under `outputs/_project_csvs/col_beam.csv`

#### Column Identity and Context

| Field | Type | Default | Description |
|---|---|---|---|
| `column_id` | string | — | Unique column instance identifier |
| `story` | int/string | — | Story number or label |
| `frame_type` | string | — | `SMF`, `IMF`, `OMF`, `Gravity`, or other |
| `column_section_id` | string | — | ID of the section in the column sections CSV |
| `clear_height_mm` | float | — | Clear height between restraints (mm) |
| `lu_mm` | float | `clear_height_mm` | Unbraced length; defaults to clear height if omitted |

#### Adjacent Column Sections

| Field | Type | Description |
|---|---|---|
| `top_other_column_section_id` | string | Column section above (`same`, `none`, or a section ID) |
| `bottom_other_column_section_id` | string | Column section below |
| `joint_top` | bool | `True` if the column continues through the top joint |
| `joint_bottom` | bool | `True` if the column continues through the bottom joint |

#### Beam Definitions (8 slots: 4 faces × 2 sides)

For each `{face}_{side}` combination (e.g., `beam_top_x_side1`):

| Field | Type | Description |
|---|---|---|
| `{face}_{side}_section_id` | string | Beam section ID, or `none` |
| `{face}_{side}_ln_mm` | float | Clear span of beam (mm) |
| `{face}_{side}_wu_kN_per_m` | float | Factored gravity load (kN/m) |
| `{face}_{side}_x_mm` | float | Lateral offset from column centerline (mm) |
| `{face}_{side}_ext_mm` | float | Beam extension beyond the joint face (mm) |
| `{face}_{side}_continuous` | bool | `True` if beam is continuous through the joint |

---

### 4. Loads CSV

One row per load combination per column.

**Example:** generated automatically from any `inputs-tests/*.json` under `outputs/_project_csvs/loads.csv`

| Field | Type | Default | Description |
|---|---|---|---|
| `column_id` | string | — | Must match a `column_id` in the column-beam file |
| `load_case` | string | — | Load combination label |
| `Pu_kN` | float | — | Factored axial force (kN); positive = compression |
| `Mux_kNm` | float | — | Factored moment about the x-axis (kN·m) |
| `Muy_kNm` | float | — | Factored moment about the y-axis (kN·m) |
| `Vux_kN` | float | — | Factored shear in x-direction (kN) |
| `Vuy_kN` | float | — | Factored shear in y-direction (kN) |
| `RotX` | float | `0.0` | Plastic rotation demand about x-axis (rad) |
| `RotY` | float | `0.0` | Plastic rotation demand about y-axis (rad) |
| `damage_state` | string | `'CP'` | Performance level: `IO`, `LS`, or `CP` |

---

## Output Files

All outputs are written to the directory specified by `--outdir`.

---

### column\_results.csv

One row per column per load case. Contains all computed capacity and demand values.

---

### column\_checks.csv

All individual code checks in tabular form.

| Column | Description |
|---|---|
| `column_id` | Column instance |
| `load_case` | `ALL` for load-independent checks, otherwise the specific combination |
| `check_name` | Short identifier (e.g., `rho_longitudinal_min`, `hx_general_limit`) |
| `status` | `OK`, `NG`, `WARNING`, or `INFO` |
| `provided` | Computed value |
| `required` | Requirement string (e.g., `>= 0.010`) |
| `code_ref` | Code clause (e.g., `ACI 18.7.5.2(e)`) |
| `message` | Plain-language explanation |

---

### column\_failures.csv

Identical format to `column_checks.csv`, filtered to `NG` and `WARNING` rows only.

---

### P-M Diagrams

Stored in `<outdir>/pm_diagrams/`. Generated for each column in SVG, PDF, and PNG formats, for both x- and y-axis bending.

Each diagram shows: nominal curve (Mn), design curve (φMn), probable curve (Mpr), and demand points for all load cases.

---

### Reports (PDF)

Stored in `<outdir>/latex_reports/`. Triggered by `--report-columns` or `--report-all`.

For each requested column, **three files** are written:

| File | Description |
|---|---|
| `{slug}_memoria.pdf` | **Summary report** — input summary, capacities, all checks, P-M diagrams. Ready to open; no LaTeX needed. |
| `{slug}_memoria.tex` | **LaTeX source** — for users who want to customise or recompile with `pdflatex`. |
| `{slug}_detailed.pdf` | **Detailed step-by-step report** — every major calculation shown with symbolic equation, substituted values, and result. Intended for learning and independent verification. |

#### Summary report contents

1. Input summary + cross-section sketch
2. Derived properties (Ag, Ach, As, ρ, hx, lo)
3. Column capacities (axial, flexural, shear)
4. Static detailing checks (ACI longitudinal and transverse)
5. Results by load combination
6. Load-dependent checks — critical combination
7. ASCE 41 rotation table
8. Connected beam capacity table
9. Joint shear capacity table
10. P-M diagrams (x and y axes)

#### Detailed report contents (step-by-step)

| Section | Code |
|---|---|
| 1. Input parameters + section sketch | — |
| 2. Cross-section geometry: Ag, Ach, As, ρ, hx, d' | ACI geometry |
| 3. Axial capacity: Pn0, φPn0 | ACI 22.4.2 |
| 4. P-M interaction: β₁, strain compatibility, Mpr | ACI 22.2, 21.2 |
| 5. Shear: Vc, Vs, φVn, Vc = 0 rule, Ve | ACI 22.5, 18.7.6 |
| 6. Confinement: ℓo, so, smax | ACI 18.7.5 |
| 7. Min. transverse ratio: kf, kn, expressions (a)(b)(c) | ACI Table 18.7.5.4 |
| 8. Strong column – weak beam | ACI 18.7.3.2 |
| 9. Joint shear: Aj, αj, Vn, φVn | ACI 15.4.2.1 |
| 10. ASCE 41 rotation: a, b, c, θIO/LS/CP, D/C | ASCE 41 Table 10-8 |
| 11. P-M diagrams | — |

Each calculation step shows: symbolic equation → substituted values → result, with the relevant code clause referenced on each line.

---

## Implemented Checks

### Frame types (SMF / IMF / OMF / Gravity)

Every assembly declares a **frame type**, and the checker selects the applicable ACI 318-25 regime — capacity-design shear basis (Mpr vs Mn), joint φ and Vn coefficient table, tie rules, ρ limits, SCWB applicability, and the Vc = 0 rule. A consistency warning is raised when the frame type is weaker than the seismic design category allows (18.2.1.1). The complete check-by-check matrix, with clause references and the documented out-of-scope items, is in [`docs/aci318_25_column_checks.md`](docs/aci318_25_column_checks.md).

The tables below describe the SMF path; the matrix documents how each row changes for IMF, OMF, and gravity columns.

### ACI 318-25: Longitudinal Reinforcement

| Check | Clause | Description |
|---|---|---|
| `min_dimension` | ACI 18.7.2.1(a) | Shortest SMF column dimension ≥ 300 mm (project rule for other frames) |
| `aspect_ratio` | ACI 18.7.2.1(b) | SMF only: shortest/perpendicular dimension ≥ 0.4 |
| `rho_longitudinal_min` | ACI 18.7.4.1 / 10.6.1.1 | ρ_long ≥ 1% |
| `rho_longitudinal_max` | ACI 18.7.4.1 / 10.6.1.1 | ρ_long ≤ **6%** (SMF and gravity SDC D–F) or 8% (IMF/OMF) |
| `n_bars_min_rect` | ACI 10.7.3.1 | At least 4 bars for rectangular sections |
| `bars_each_face_min` | Geometry | At least 2 bars per face |
| `free_spacing_long_bars` | ACI 25.2.3 | Clear spacing between bars ≥ 40 mm |
| `core_geometry_positive` | Derived | Confined core dimensions bc, hc must be positive |

---

### ACI 318-25: Transverse Reinforcement

| Check | Clause | Description |
|---|---|---|
| `lo_x_length` / `lo_y_length` | ACI 18.7.5.1 | lo ≥ max(h, lclear/6, 450 mm) |
| `hook_angle_rectilinear` | ACI 18.7.5.2(b) | Rectilinear hoops must have 135-degree hooks |
| `crosstie_diameter` | ACI 18.7.5.2(c) | Crosstie diameter ≥ hoop diameter |
| `crosstie_alternate_anchorage` | ACI 18.7.5.2(c) | Consecutive crossties alternated end-for-end |
| `hx_general_limit` | ACI 18.7.5.2(e) | Maximum unsupported bar spacing ≤ 350 mm |
| `hx_special_limit` | ACI 18.7.5.2(f) | Reduced limit of 200 mm when Pu > 0.3 Ag f'c or f'c > 70 MPa |
| `tie_spacing_within_lo` | ACI 18.7.5.3 | Spacing within lo ≤ min(b/4, 6db [5db Gr. 550], so) |
| `tie_spacing_outside_lo` | ACI 18.7.5.5 | Spacing outside lo ≤ min(150, 6db) mm |
| `rho_s_x_required` / `rho_s_y_required` | ACI Table 18.7.5.4 | Transverse ratio ≥ governing table expression (kf·kn only in expr. (c)) |
| `imf_*` family | ACI 18.4.3.3 / 18.4.3.5 | IMF: hoop spacing min(8db, 200) Gr. 420 within lo = max(lu/6, max(b,h), 450); Table 10.7.6.5.2 outside |
| `omf_*` family | ACI 25.7.2.1(b) / 25.7.2.2 | OMF: general ties min(16db, 48dbt, least dim) full height, minimum tie size |
| `sdc_frame_type_consistency` | ACI 18.2.1.1 | Warns if frame type is weaker than the SDC permits (e.g. OMF in SDC C+) |

---

### ACI 318-25: Flexure and Axial Capacity

Capacity is computed using **strain compatibility** with:
- Whitney rectangular stress block for concrete (α₁ = 0.85, β₁ per ACI Table 22.2.2.4.3).
- Bilinear steel model (εy = fy/Es, Es = 200 GPa).
- Ultimate concrete strain εcu = 0.003.
- φ factor: 0.65 (compression-controlled) to 0.90 (tension-controlled), linear transition.

180+ interaction points are generated; capacity at applied Pu is found by interpolation.

For **probable strength**: fye = 1.25 × fy, φ = 1.0.

---

### ACI 318-25: Seismic Shear

- **SMF / gravity (18.7.6.1 / 18.14.3.2(b)):** Ve = (Mpr_top + Mpr_bottom) / lu, capped by the beam joint Mpr and never less than the analysis shear.
- **IMF (18.4.3.1(a)):** Ve = (Mn_top + Mn_bottom) / lu.
- **OMF (18.3.3(a)):** same as IMF, but required only for columns with lu ≤ 5c1.

**Vc = 0 rule** (ACI 18.7.6.2.1, SMF/gravity only) applies when Ve ≥ 0.5 × Vu_design **and** Pu < Ag × f'c / 20.

---

### ACI 318-25: Strong Column Weak Beam

ΣMnc ≥ 1.2 × ΣMnb  (ACI 18.7.3.2) — SMF columns only.

---

### ACI 318-25: Joint Shear

Vn = αj × √f'c × Aj with the coefficient table and φ selected by frame type:

| Frame | Demand basis | Vn table | φ |
|---|---|---|---|
| SMF | beam tension at **1.25fy** + column Mpr shear (18.8.2.1 / 18.8.4.1) | Table 18.8.4.3 (1.7 / 1.3 / 1.0 / 0.7) | 0.85 (21.2.4.4) |
| IMF | beam tension at fy (18.4.4.7.2) | Table 18.8.4.3 | 0.75 |
| OMF / Gravity | beam tension at fy (18.3.4 / 15.4.2.1(b)) | Table 15.5.2.1 (2.0 / 1.7 / 1.3 / 1.0) | 0.75 |

For two-sided joints the beam tension is the critical seismic scenario max(T_neg,s1 + T_pos,s2 ; T_pos,s1 + T_neg,s2). SMF joints additionally check the joint depth against 20db (Gr. 420) / 26db (Gr. 550) of the largest beam bar (18.8.2.3).

---

### ACI 318-25: Gravity Columns (18.14.3)

For gravity-frame columns in SDC D/E/F, a simplified transverse check is applied per ACI 18.14.3.2. Additional requirements are triggered when Pu > 0.35 × Po.

---

### ASCE 41: Plastic Rotation Acceptance Criteria

Per ASCE 41 Table 10-8, plastic rotation parameters:

```
a = max(0.042 − 0.043·ν_eff + 0.63·ρt − 0.023·v, 0)
b = max(0.5 / (5 + (ν_eff/0.8)·(f'c/(ρt·fyte))) − 0.01, a)
c = max(0.24 − 0.4·max(ν, 0.1), 0)
```

Acceptance criteria: θIO = 0.15·a (max 0.005), θLS = 0.5·b, θCP = 0.7·b.

Demand/capacity ratio: |θd| / θcap ≤ 1.0.

---

## Code Architecture

```
rc-column-checker/
├── main.py                      # CLI entry point; orchestration, result assembly
├── app.py                       # Streamlit GUI
├── io_utils.py                  # CSV reading, validation, project-JSON -> CSV conversion
├── geometry_utils.py            # Geometric properties (Ag, Ach, As, hx, rho_s)
├── section_capacity.py          # Strain-compatibility, interaction curves, shear/joint
├── frame_types.py               # SMF / IMF / OMF / GRAVITY classification
├── aci_longitudinal_checks.py   # ACI longitudinal detailing checks
├── aci_transverse_checks.py     # ACI transverse detailing checks (per frame type)
├── asce41_rotation.py           # ASCE 41 Table 10-8 plastic rotation
├── pm_diagram.py                # P-M diagram + cross-section sketch (matplotlib)
├── reporting.py                 # LaTeX report assembly
├── pdf_report.py                # Summary PDF report (ReportLab)
├── pdf_report_detailed.py       # Step-by-step educational PDF report (ReportLab)
├── constants.py                 # All normative constants with code clause references
├── requirements.txt
├── .python-version              # Pins Python 3.11 for Streamlit Cloud
├── inputs-tests/                # Example projects: one .json per frame type
│   ├── smf_interior_column.json
│   ├── imf_edge_column.json
│   ├── omf_lowrise_column.json
│   └── gravity_column_sdc_d.json
├── docs/
│   └── aci318_25_column_checks.md   # Check matrix by frame type
├── templates/                   # LaTeX report template
└── assets/
    ├── logo_black_horizontal.png        # Black logo for LaTeX report headers
    ├── Logo_horizontal_Torrefuerte.png  # Colour logo for PDF reports + Streamlit GUI
    └── logo_browser.PNG                 # Favicon for the Streamlit web app
```

### Data Flow

```
project .json ──io_utils.write_project_csvs()──► 4 CSV inputs
                                                     │
                                                     ▼
                                          io_utils.read_inputs()
                                                     │
                                                     ▼
For each column:
    ├─ compute_geometry()              → Ag, Ach, As, rho_long, hx, bar positions
    ├─ compute_beam_actions()          → beam flexural capacities per joint face
    ├─ pure_axial_capacity()           → Pn0, phiPn0
    ├─ pure_flexure_capacity()         → Mn0, Mpr0 at Pu = 0
    ├─ shear_capacity_base()           → Vc + Vs
    ├─ joint_capacity_static()         → αj, Aj, Vn_joint
    ├─ longitudinal_checks()           → static detailing checks
    ├─ transverse_checks()             → static detailing checks
    └─ interaction_points()            → full P-M curve (180+ points)
    │
    └─ For each load case:
        ├─ column_strengths_at_Pu()        → Mn, Mpr, phi at current Pu
        ├─ probable_shear_for_column()     → Ve (probable seismic shear)
        ├─ shear_capacity_case()           → phiVn with Vc = 0 rule applied
        ├─ strong_column_weak_beam()       → SCWB ratio
        ├─ joint_shear_demand_case()       → joint shear demand
        ├─ compute_asce41_rotation()       → a, b, c, theta_io/ls/cp, D/C ratio
        ├─ [write to column_results.csv]
        └─ [write to column_checks.csv]
    │
    └─ If reports requested:
        ├─ export_section_sketch()         → sections/{slug}.png
        ├─ export_pm_diagram()             → pm_diagrams/{id}_PM_x/y.svg/.pdf/.png
        ├─ build_latex_report()            → latex_reports/{slug}_memoria.tex
        ├─ build_pdf_report()              → latex_reports/{slug}_memoria.pdf
        └─ build_detailed_pdf_report()     → latex_reports/{slug}_detailed.pdf
```

---

## Notes and Limitations

1. **Section geometry**: Only rectangular perimeter bar layouts are supported. Circular, spiral, or non-uniform bar arrangements are not modelled.

2. **Interaction surface**: The P-M analysis uses the Whitney equivalent rectangular stress block. It does not perform fibre-by-fibre integration, so results are approximate for sections with clustered reinforcement or significant cover-to-depth ratios.

3. **Biaxial interaction**: x- and y-directions are checked independently. No Bresler-type biaxial interaction check is currently applied.

4. **Beam flexure**: Beam capacities use simplified rectangular beam theory (tension-controlled, no T-section slab contribution). Adequate for joint and SCWB screening; may differ from a full section analysis.

5. **Adjacent column references**:
   - `same` — reuses the current column section.
   - `none` — zero contribution (column terminates at the joint).
   - Any other string — must match a `column_section_id` in the column sections CSV.

6. **Report outputs**: Three files are written per column when reports are requested: `*_memoria.pdf` (summary, ReportLab), `*_memoria.tex` (LaTeX source for customisation), and `*_detailed.pdf` (step-by-step educational report, ReportLab). The PDFs embed the cross-section sketch and P-M diagrams from the same run. To compile the `.tex` file with `pdflatex`, keep `assets/logo_black_horizontal.png` accessible as `../../assets/` and section images at `../sections/` relative to the `latex_reports/` directory.

7. **Version history**: beta.
