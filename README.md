# RC Column Checker

A command-line tool for automated structural verification of reinforced concrete columns under seismic loading. Implements **ACI 318-22** (Building Code Requirements for Structural Concrete) and **ASCE 41** (Seismic Evaluation and Retrofit of Existing Buildings) checks, and produces CSV result tables, P-M interaction diagrams, and compilable LaTeX engineering reports.

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Requirements](#requirements)
3. [Installation](#installation)
4. [Quick Start](#quick-start)
5. [CLI Arguments](#cli-arguments)
6. [Input Files](#input-files)
   - [Column Sections CSV](#1-column-sections-csv)
   - [Beam Sections CSV](#2-beam-sections-csv)
   - [Column-Beam Properties CSV](#3-column-beam-properties-csv)
   - [Loads CSV](#4-loads-csv)
7. [Output Files](#output-files)
   - [column\_results.csv](#column_resultscsv)
   - [column\_checks.csv](#column_checkscsv)
   - [column\_failures.csv](#column_failurescsv)
   - [P-M Diagrams](#pm-diagrams)
   - [LaTeX Reports](#latex-reports)
8. [Implemented Checks](#implemented-checks)
   - [ACI 318-22: Longitudinal Reinforcement](#aci-318-22-longitudinal-reinforcement)
   - [ACI 318-22: Transverse Reinforcement](#aci-318-22-transverse-reinforcement)
   - [ACI 318-22: Flexure and Axial Capacity](#aci-318-22-flexure-and-axial-capacity)
   - [ACI 318-22: Seismic Shear](#aci-318-22-seismic-shear)
   - [ACI 318-22: Strong Column Weak Beam](#aci-318-22-strong-column-weak-beam)
   - [ACI 318-22: Joint Shear](#aci-318-22-joint-shear)
   - [ACI 318-22: Gravity Columns (18.14.3.2)](#aci-318-22-gravity-columns-18143)
   - [ASCE 41: Plastic Rotation Acceptance Criteria](#asce-41-plastic-rotation-acceptance-criteria)
9. [Code Architecture](#code-architecture)
10. [Notes and Limitations](#notes-and-limitations)

---

## What It Does

RC Column Checker takes four CSV input files that describe column sections, beam sections, column-to-beam joint assemblies, and load combinations. For each column under each load case, it:

- Computes geometric properties (gross area, confined core area, reinforcement ratios, maximum unsupported bar spacing).
- Builds the biaxial P-M interaction surface using strain-compatibility analysis with a Whitney stress block.
- Calculates nominal, probable, and design-level flexural and shear capacities.
- Evaluates beam-column joint shear demand and capacity.
- Applies the strong-column weak-beam (SCWB) rule.
- Runs all applicable ACI 318-22 detailing checks for longitudinal and transverse reinforcement.
- Computes ASCE 41 plastic rotation parameters and checks demand against IO / LS / CP acceptance criteria.
- Exports results to CSV tables, SVG/PDF/PNG P-M diagrams, and fully compilable LaTeX engineering reports.

---

## Requirements

- Python 3.9 or later
- `matplotlib`
- `numpy`

For compiling LaTeX reports:
- A TeX distribution (TeX Live, MiKTeX, or MacTeX) with `pdflatex` and `latexmk`
- `booktabs`, `geometry`, `xcolor`, `graphicx`, `longtable` packages (included in most standard distributions)

---

## Installation

```bash
git clone https://github.com/your-org/rc-column-checker.git
cd rc-column-checker
pip install -r requirements.txt
```

No build step is needed. All calculation logic is in pure Python; `matplotlib` and `numpy` are only used for diagram generation.

---

## Quick Start

Run the bundled sample files:

```bash
python main.py ^
  --column-sections sample_column_sections_v18.csv ^
  --beam-sections sample_beam_sections_v18.csv ^
  --column-beam sample_column_beam_prop_v18.csv ^
  --loads sample_loads_v18.csv ^
  --outdir outputs
```

This creates an `outputs/` directory containing:

```
outputs/
├── column_results.csv       # Capacity and demand summary (one row per load case)
├── column_checks.csv        # All individual checks with status OK / NG / WARNING / INFO
├── column_failures.csv      # Subset of checks with status NG or WARNING only
└── pm_diagrams/
    ├── COL_150x100_PM_x.svg
    ├── COL_150x100_PM_x.pdf
    ├── COL_150x100_PM_x.png
    ├── COL_150x100_PM_y.svg
    ...
```

Generate LaTeX reports for selected columns:

```bash
python main.py ^
  --column-sections sample_column_sections_v18.csv ^
  --beam-sections sample_beam_sections_v18.csv ^
  --column-beam sample_column_beam_prop_v18.csv ^
  --loads sample_loads_v18.csv ^
  --outdir outputs ^
  --report-columns COL_150x100,COL_150x100_ROOF ^
  --pry-name "Project Name"
```

Generate LaTeX reports for all columns:

```bash
python main.py ^
  --column-sections sample_column_sections_v18.csv ^
  --beam-sections sample_beam_sections_v18.csv ^
  --column-beam sample_column_beam_prop_v18.csv ^
  --loads sample_loads_v18.csv ^
  --outdir outputs ^
  --report-all ^
  --pry-name "Project Name"
```

Generate a report while hiding optional sections:

```bash
python main.py ^
  --column-sections sample_column_sections_v18.csv ^
  --beam-sections sample_beam_sections_v18.csv ^
  --column-beam sample_column_beam_prop_v18.csv ^
  --loads sample_loads_v18.csv ^
  --outdir outputs ^
  --report-columns COL_150x100 ^
  --pry-name "Project Name" ^
  --hide-rotation-table ^
  --hide-joint-table
```

---

## CLI Arguments

| Argument | Required | Default | Description |
|---|---|---|---|
| `--column-sections PATH` | Yes | — | CSV library of column cross-sections |
| `--beam-sections PATH` | Yes | — | CSV library of beam cross-sections |
| `--column-beam PATH` | Yes | — | CSV of column instances and joint assemblies |
| `--loads PATH` | Yes | — | CSV of load combinations per column |
| `--outdir PATH` | No | `outputs` | Output directory (created if absent) |
| `--skip-pm` | No | off | Skip P-M diagram generation |
| `--report-columns COL1,COL2` | No | — | Generate LaTeX reports only for listed `column_id` values |
| `--report-all` | No | off | Generate LaTeX reports for every column |
| `--pry-name "Name"` | No | — | Project name shown in report headers |
| `--hide-rotation-table` | No | off | Omit the ASCE 41 rotation table from reports |
| `--hide-beam-table` | No | off | Omit the connected beam capacity table from reports |
| `--hide-joint-table` | No | off | Omit the joint shear capacity table from reports |

---

## Input Files

The tool requires **four CSV files**. All use comma-separated format with a header row. Unrecognised columns are ignored. Fields marked *optional* have internal defaults and may be omitted from the CSV.

---

### 1. Column Sections CSV

Defines a reusable library of column cross-sections. One row per section ID. Referenced from the column-beam properties file.

**Sample:** `sample_column_sections_v18.csv`

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

Example: `"40;190;340;500;660;810;960"` for a face with 7 bars each 150 mm apart with 40 mm end cover.

#### ASCE 41 Parameters (Optional)

| Field | Default | Description |
|---|---|---|
| `asce_fye_factor` | `1.25` | Expected/nominal strength ratio for longitudinal steel (*fye/fy*) |
| `asce_fyte_factor` | `1.25` | Expected/nominal strength ratio for transverse steel (*fyte/fyt*) |
| `asce_splice_controlled` | `False` | `True` if lap splices control rotational behavior (ASCE 41 Table 10-8 splice branch) |
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
| `cover_additional_transverse_cover_mm` | `999` | Additional cover outside confinement zone (ACI 18.7.5.7) |
| `cover_additional_transverse_spacing_mm` | `999` | Additional spacing tie requirement |

---

### 2. Beam Sections CSV

Defines a reusable library of beam cross-sections. Referenced from the column-beam properties file to describe beams framing into each joint face.

**Sample:** `sample_beam_sections_v18.csv`

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

One row per column instance (not per section). References a column section and defines the structural context: story, frame type, adjacent columns, and beams on each joint face.

**Sample:** `sample_column_beam_prop_v18.csv`

#### Column Identity and Context

| Field | Type | Default | Description |
|---|---|---|---|
| `column_id` | string | — | Unique column instance identifier |
| `story` | int/string | — | Story number or label |
| `frame_type` | string | — | `SMF` (Special Moment Frame), `IMF`, `OMF`, `Gravity`, or other |
| `column_section_id` | string | — | ID of the section in the column sections CSV |
| `clear_height_mm` | float | — | Clear height between restraints (mm) |
| `lu_mm` | float | `clear_height_mm` | Unbraced length used for transverse checks; defaults to clear height if omitted |

#### Adjacent Column Sections

Used for the Strong Column Weak Beam check. Contributions from columns above and below are summed.

| Field | Type | Description |
|---|---|---|
| `top_other_column_section_id` | string | Column section above. Use `same` to reuse current section, `none` for no column above |
| `bottom_other_column_section_id` | string | Column section below. Same `same`/`none` convention |
| `joint_top` | bool | `True` if the column continues through the top joint |
| `joint_bottom` | bool | `True` if the column continues through the bottom joint |

#### Beam Definitions (8 faces × 2 sides)

There are four joint faces (`top_x`, `bottom_x`, `top_y`, `bottom_y`) and two beam slots per face (`side1`, `side2`). For a face with only one beam, populate `side1` and leave `side2` as `none`.

For each combination `{face}_{side}` (e.g., `beam_top_x_side1`):

| Field | Type | Description |
|---|---|---|
| `{face}_{side}_section_id` | string | Beam section ID, or `none` for no beam |
| `{face}_{side}_ln_mm` | float | Clear span of beam (mm) |
| `{face}_{side}_wu_kN_per_m` | float | Factored gravity load on beam (kN/m), used for joint shear demand |
| `{face}_{side}_x_mm` | float | Lateral offset of beam centerline from column centerline (mm), used to compute effective joint width |
| `{face}_{side}_ext_mm` | float | Beam extension beyond the joint face (mm), relevant for exterior joints |
| `{face}_{side}_continuous` | bool | `True` if beam is continuous through the joint |

#### Optional Flags

| Field | Default | Description |
|---|---|---|
| `yielding_region_expected` | `True` | Whether plastic hinging is expected at this column (affects transverse check branches) |
| `gravity_design_actions_checked` | `True` | Whether gravity-only design actions have been checked (ACI 18.14.3.2) |
| `seismic_design_category` | `'D'` | SDC used to activate gravity column checks |
| `notes` | — | Free-text notes, not used in calculations |

---

### 4. Loads CSV

One row per load combination per column. A single `column_id` may have many rows (load cases).

**Sample:** `sample_loads_v18.csv`

| Field | Type | Default | Description |
|---|---|---|---|
| `column_id` | string | — | Must match a `column_id` in the column-beam file |
| `load_case` | string | — | Load combination label (e.g., `Fz_max`, `Combo_2`) |
| `Pu_kN` | float | — | Factored axial force (kN); positive = compression |
| `Mux_kNm` | float | — | Factored moment about the x-axis (kN·m) |
| `Muy_kNm` | float | — | Factored moment about the y-axis (kN·m) |
| `Vux_kN` | float | — | Factored shear in x-direction (kN) |
| `Vuy_kN` | float | — | Factored shear in y-direction (kN) |
| `RotX` | float | `0.0` | Plastic rotation demand about x-axis (rad), from nonlinear analysis |
| `RotY` | float | `0.0` | Plastic rotation demand about y-axis (rad) |
| `damage_state` | string | `'CP'` | Performance level: `IO` (Immediate Occupancy), `LS` (Life Safety), or `CP` (Collapse Prevention) |

---

## Output Files

All outputs are written to the directory specified by `--outdir`.

---

### column\_results.csv

One row per column per load case. Contains all computed capacity and demand values.

Key columns include:

| Column | Description |
|---|---|
| `column_id`, `load_case` | Identifiers |
| `Ag_mm2`, `Ach_mm2` | Gross and confined core areas |
| `As_mm2`, `rho_long` | Longitudinal steel area and ratio |
| `hx_mm`, `rho_s` | Max unsupported bar spacing and transverse steel ratio |
| `phiPn0_kN` | Design axial capacity (phi × Pn0) |
| `phiMn_x_kNm`, `phiMn_y_kNm` | Design flexural capacity at applied Pu |
| `Mpr_x_kNm`, `Mpr_y_kNm` | Probable flexural capacity at applied Pu |
| `phi_x`, `phi_y` | Strength reduction factors |
| `pm_ratio_x`, `pm_ratio_y` | P-M demand/capacity ratios (should be ≤ 1.0) |
| `Ve_x_kN`, `Ve_y_kN` | Probable seismic shear demand |
| `phiVn_x_kN`, `phiVn_y_kN` | Design shear capacity |
| `shear_ratio_x`, `shear_ratio_y` | Shear demand/capacity ratios |
| `scwb_ratio_x`, `scwb_ratio_y` | Strong-column weak-beam ratios (should be ≥ 1.2) |
| `a_x`, `b_x`, `c_x` | ASCE 41 Table 10-8 parameters for x-direction |
| `theta_io_x`, `theta_ls_x`, `theta_cp_x` | ASCE 41 rotation limits for x |
| `asce_ratio_x`, `asce_ratio_y` | ASCE 41 rotation demand/capacity ratios |
| `joint_Vn_x_kN`, `joint_Vn_y_kN` | Joint shear capacity |
| `joint_ratio_x`, `joint_ratio_y` | Joint demand/capacity ratios |

---

### column\_checks.csv

All individual code checks in tabular form. One row per check per column per load case.

| Column | Description |
|---|---|
| `column_id` | Column instance |
| `load_case` | `ALL` for static checks independent of load, otherwise the specific case |
| `check_name` | Short identifier for the check (e.g., `rho_longitudinal_min`, `hx_general_limit`) |
| `status` | `OK`, `NG`, `WARNING`, or `INFO` |
| `provided` | Computed value |
| `required` | Requirement string (e.g., `>= 0.010`, `<= 350 mm`) |
| `code_ref` | Code clause (e.g., `ACI 18.7.5.2(e)`, `ASCE 41 Table 10-8`) |
| `message` | Plain-language explanation |

**Status meanings:**

| Status | Meaning |
|---|---|
| `OK` | Check passes |
| `NG` | Check fails (No Good) — requires attention |
| `WARNING` | Condition flagged; may not be a hard failure but warrants review |
| `INFO` | Informational value only; no pass/fail threshold |

---

### column\_failures.csv

Identical format to `column_checks.csv` but filtered to rows where `status` is `NG` or `WARNING`. Useful for quickly identifying deficiencies without scanning the full checks file.

---

### P-M Diagrams

Stored in `<outdir>/pm_diagrams/`. Generated for each column in SVG, PDF, and PNG formats.

Each diagram shows:
- **Nominal curve** (Pn–Mn): using actual material strengths.
- **Probable curve** (Ppr–Mpr): using expected strengths (*fye = 1.25 fy*, *fce = 1.3 f'c* per ASCE 41).
- **Design curve** (phi×Pn – phi×Mn): applying ACI phi factors.
- **Load demand points**: all load cases for the column plotted as markers.

Both x- and y-axis bending diagrams are produced:
- `{column_id}_PM_x.svg/pdf/png`
- `{column_id}_PM_y.svg/pdf/png`

To skip diagram generation (faster batch runs), use `--skip-pm`.

---

### LaTeX Reports

Stored in `<outdir>/latex_reports/`. Triggered by `--report-columns` or `--report-all`.

Each report (`{column_id}_memoria.tex`) is a fully compilable LaTeX document containing:

1. **Section properties table**: dimensions, materials, steel areas, ratios.
2. **Capacity table**: axial, flexural, and shear capacities.
3. **Static detailing checks**: ACI longitudinal and transverse checks (load-independent).
4. **Load-dependent checks per combination**: P-M ratios, shear ratios, SCWB ratios, joint ratios.
5. **ASCE 41 rotation table** (unless `--hide-rotation-table`): parameters a, b, c, acceptance criteria, and demand/capacity ratios.
6. **Connected beam capacity table** (unless `--hide-beam-table`): beam sections and their flexural contributions.
7. **Joint shear capacity table** (unless `--hide-joint-table`): joint type, alpha factor, capacity, demand.
8. **Embedded P-M diagrams**.

Failed checks (`NG`) and warnings (`WARNING`) and D/C ratios greater than 1.0 are highlighted in red.

**Compilation:**

```bash
cd outputs/latex_reports
pdflatex COL_150x100_memoria.tex
# or using latexmk:
latexmk -pdf COL_150x100_memoria.tex
```

**Required assets for compilation:**
- `assets/logo_black_horizontal.png` — located two directory levels above the `.tex` file (i.e., `../../assets/logo_black_horizontal.png` relative to the report).
- `sections/{column_section_id}.png` — section diagram images located two levels above the `.tex` file (`../../sections/{id}.png`).

---

## Implemented Checks

### ACI 318-22: Longitudinal Reinforcement

| Check | Clause | Description |
|---|---|---|
| `min_dimension` | Project rule | Minimum column dimension ≥ `min_dim_required_mm` (default 300 mm) |
| `rho_longitudinal_min` | ACI 10.6.1 | ρ_long ≥ ρ_min (default 1%) |
| `rho_longitudinal_max` | ACI 10.6.1 | ρ_long ≤ ρ_max (default 8%) |
| `n_bars_min_rect` | ACI 18.7.4 | At least 4 bars for rectangular sections |
| `bars_each_face_min` | Geometry | At least 2 bars per face (required for perimeter model) |
| `free_spacing_long_bars` | ACI 18.7.4.2 | Clear spacing between bars ≥ 40 mm |
| `core_geometry_positive` | Derived | Confined core dimensions bc, hc must be positive |

---

### ACI 318-22: Transverse Reinforcement

| Check | Clause | Description |
|---|---|---|
| `lo_x_length` / `lo_y_length` | ACI 18.7.5.1 | Confinement length lo ≥ max(h, lclear/6, 450 mm) |
| `hook_angle_rectilinear` | ACI 18.7.5.2(b) | Rectilinear hoops must have 135-degree hooks |
| `crosstie_diameter` | ACI 18.7.5.2(c) | Crosstie diameter ≥ hoop diameter |
| `crosstie_alternate_anchorage` | ACI 18.7.5.2(c) | Consecutive crossties alternated end-for-end |
| `hx_general_limit` | ACI 18.7.5.2(e) | Maximum spacing between laterally supported bars ≤ 350 mm |
| `hx_special_limit` | ACI 18.7.5.2(f) | Reduced limit of 200 mm when Pu > 0.3 Ag f'c or f'c > 70 MPa |
| `all_perimeter_bars_supported` | ACI 18.7.5.2 | Every perimeter bar must have lateral support |
| `tie_spacing_within_lo` | ACI 18.7.5.3 | Spacing within lo ≤ minimum of (b/4, 6db, so) |
| `tie_spacing_outside_lo` | ACI 18.7.5.5 | Spacing outside lo ≤ minimum allowed |
| `rho_s_x_required` / `rho_s_y_required` | ACI Table 18.7.5.4 | Transverse reinforcement ratio ≥ required by equations (a), (b), (c) |
| `cover_additional_transverse_not_required` | ACI 18.7.5.7 | Concrete cover outside confinement ≤ 100 mm |

For **gravity columns** in SDC D/E/F (ACI 18.14.3.2), a simplified transverse check is applied based on a threshold Pu > 0.35 Po.

---

### ACI 318-22: Flexure and Axial Capacity

Capacity is computed using **strain compatibility** with:
- Whitney rectangular stress block for concrete.
- Bilinear elastic-perfectly-plastic steel model (εy = fy/Es, Es = 200 GPa).
- Ultimate concrete strain εcu = 0.003.
- Phi factor: 0.65 (compression-controlled) to 0.90 (tension-controlled), transitioning linearly.

The tool generates 180+ points for the full interaction surface and interpolates at the applied Pu to obtain Mn and phi.

For **probable strength**, expected material strengths are used: fye = asce_fye_factor × fy (default 1.25), fce = 1.3 × f'c.

---

### ACI 318-22: Seismic Shear

Per ACI 18.7.6, the design seismic shear Ve is taken as:

```
Ve = (Mpr_top + Mpr_bottom) / lu
```

where Mpr is the probable flexural capacity at the actual Pu, and lu is the clear height (or unbraced length).

The **Vc = 0 rule** (ACI 18.7.6.2.1) eliminates the concrete contribution to shear when:
- Ve ≥ 0.5 × (Vc + Vs), **and**
- Pu < Ag × f'c / 20

The shear demand/capacity ratio is checked as: Ve / (phi × Vn) ≤ 1.0.

---

### ACI 318-22: Strong Column Weak Beam

Per ACI 18.7.3.2, at each joint:

```
Σ Mnc (columns) ≥ 1.2 × Σ Mnb (beams)
```

The sum includes contributions from the column above and below the joint (using their respective sections and Pu values). The beam sum is computed from the probable flexural strength of all beams framing into the joint on each side.

---

### ACI 318-22: Joint Shear

Per ACI 18.8.4, the joint shear capacity is:

```
Vn = alpha_j × sqrt(f'c) × Aj
```

where:
- **alpha_j** depends on joint confinement: 1.7 (confined on all 4 sides), 1.2 (confined on 3 sides or two opposite sides), 1.0 (otherwise).
- **Aj** is the effective joint area, with width limited by the column dimension and beam width plus offset.

Joint shear demand is computed from the beam probable moment capacity and the column shear.

---

### ACI 318-22: Gravity Columns (18.14.3)

For columns in `frame_type` other than SMF/IMF/OMF (i.e., gravity frames) in SDC D, E, or F, the code checks whether the column was designed for the gravity load combination that includes the vertical ground motion amplification per ACI 18.14.3.2. This is flagged as a `WARNING` if `gravity_design_actions_checked` is `False` and Pu > 0.35 × Po.

---

### ASCE 41: Plastic Rotation Acceptance Criteria

Per ASCE 41 Table 10-8, plastic rotation acceptance criteria for RC columns with conforming transverse reinforcement are computed as functions of:

- **Axial ratio**: P / (Ag × f'c)
- **Transverse reinforcement ratio**: ρ_t (about x and y)
- **Shear ratio**: Vye / VColOE (expected shear to column shear capacity)
- **Splice control**: whether lap splice behavior governs

**Non-splice branch equations:**

```
a = max(0.042 − 0.043 × r_eff + 0.63 × rho_t − 0.023 × v_ratio, 0)
b = max(0.5 / (5 + (r_eff/0.8) × (f'c/(rho_t × fyte))) − 0.01, a)
c = max(0.24 − 0.4 × max(axial_ratio, 0.1), 0)
```

where r_eff = max(axial_ratio, 0.1).

Acceptance limits:
- **IO (Immediate Occupancy)**: θ_io = 0.5 × a
- **LS (Life Safety)**: θ_ls = 0.75 × a (interpolated from Table 10-8)
- **CP (Collapse Prevention)**: θ_cp = a

The plastic rotation demand from the loads CSV (`RotX`, `RotY`) is divided by the appropriate limit for the load case's `damage_state`, giving the ASCE 41 demand/capacity ratio.

---

## Code Architecture

```
rc-column-checker/
├── main.py                      # Entry point; CLI parsing, orchestration, result assembly
├── io_utils.py                  # CSV reading, validation, section/instance merging
├── geometry_utils.py            # Geometric property calculations (Ag, Ach, As, hx, rho_s)
├── section_capacity.py          # Strain-compatibility analysis, interaction curves, shear/joint capacity
├── aci_longitudinal_checks.py   # ACI longitudinal detailing checks
├── aci_transverse_checks.py     # ACI transverse detailing checks
├── asce41_rotation.py           # ASCE 41 Table 10-8 plastic rotation parameters
├── pm_diagram.py                # P-M diagram generation (matplotlib)
├── reporting.py                 # LaTeX report assembly
├── requirements.txt
├── sample_column_sections_v18.csv
├── sample_beam_sections_v18.csv
├── sample_column_beam_prop_v18.csv
├── sample_loads_v18.csv
├── sections/                    # Section diagram images for reports (PNG)
├── templates/                   # LaTeX report template
├── assets/
│   └── logo_black_horizontal.png    # Logo for report header
```

### Data Flow

```
4 CSV inputs
    │
    ▼
io_utils.read_inputs()
    ├─ read_column_sections_csv()   ─┐
    ├─ read_beam_sections_csv()      ├─ assemble_column_properties()
    ├─ read_column_beam_csv()       ─┘
    └─ read_loads_csv()
    │
    ▼
For each column:
    ├─ compute_geometry()              → Ag, Ach, As, rho_long, hx, rho_s, bar positions
    ├─ compute_beam_actions()          → beam flexural capacities per joint face
    ├─ pure_axial_capacity()           → Pn0, phiPn0
    ├─ pure_flexure_capacity()         → Mn0, Mpr0 at Pu=0
    ├─ shear_capacity_base()           → Vc + Vs
    ├─ joint_capacity_static()         → alpha_j, Aj, Vn_joint
    ├─ longitudinal_checks()           → static detailing checks (load-independent)
    ├─ transverse_checks()             → static detailing checks (load-independent)
    └─ interaction_points()            → full P-M curve (180+ points)
    │
    └─ For each load case:
        ├─ column_strengths_at_Pu()        → Mn, Mpr, phi at current Pu
        ├─ probable_shear_for_column()     → Ve (probable seismic shear demand)
        ├─ shear_capacity_case()           → adjusted phiVn (applies Vc=0 rule)
        ├─ strong_column_weak_beam()       → SCWB ratio
        ├─ joint_shear_demand_case()       → joint shear demand
        ├─ compute_asce41_rotation()       → a, b, c, theta_io/ls/cp, demand ratio
        ├─ [write to column_results.csv]
        └─ [write to column_checks.csv]
    │
    └─ If reports requested:
        ├─ export_pm_diagram()         → SVG / PDF / PNG
        └─ build_latex_report()        → .tex file
```

---

## Notes and Limitations

1. **Section geometry**: Only rectangular perimeter bar layouts are supported. Circular, spiral, or non-uniform bar arrangements are not modelled.

2. **Interaction surface**: The P-M analysis uses a simplified rectangular cross-section (equivalent Whitney stress block). It does not perform fibre-by-fibre integration, so results are approximate for sections with clustered reinforcement or significant cover-to-depth ratios.

3. **Biaxial interaction**: x- and y-directions are checked independently. No Bresler-type biaxial interaction check is currently applied.

4. **Beam flexure**: Beam capacities are computed using simplified rectangular beam theory (tension-controlled, no T-section slab contribution). These are adequate for joint and SCWB screening but may differ from a full section analysis.

5. **Adjacent column references**:
   - `same` — reuses the current column section.
   - `none` — zero contribution (column terminates at the joint).
   - Any other string — must match a `column_section_id` in the column sections CSV.

6. **Cyclic degradation**: No explicit cyclic degradation model is applied. ASCE 41 acceptance criteria are point-in-time plastic rotation limits, not hysteretic energy-based.

7. **LaTeX compilation assets**: To compile the generated report, keep `assets/logo_black_horizontal.png` two directory levels above the `.tex` file (`../../assets/logo_black_horizontal.png`), and section images at `../../sections/{column_section_id}.png`.

8. **Version history**: This is version 18 of the tool. Sample files from v17 (`*_v17.csv`) are also included for reference. Use `*_v18.csv` files for current runs.
