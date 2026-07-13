# ACI 318-25 column check matrix — rc-column-checker

Reference of every column verification the app performs, by frame type
(`frame_type` input on each Assembly: **SMF / IMF / OMF / Gravity**).
Section numbers follow **ACI 318-25**: 18.3 = OMF, 18.4 = IMF, 18.7/18.8 = SMF
columns/joints, 18.14 = members not designated as part of the SFRS (gravity),
Ch. 15 = beam-column joints (non-SMF), Ch. 10 / 25.7.2 = general columns.

## Design regime by frame type

| Aspect | SMF | IMF | OMF | Gravity (SDC D–F) |
|---|---|---|---|---|
| Column shear demand Ve | Mpr hinging, capped by beam joint Mpr, ≥ analysis Vu (18.7.6.1.1) | **Mn** hinging (18.4.3.1(a)) | **Mn** hinging, required **only if ℓu ≤ 5c1** (18.3.3) | Same as SMF via 18.14.3.2(b) → 18.7.6 |
| Vc = 0 rule | 18.7.6.2.1 | not invoked | not invoked | applies (via 18.7.6) |
| Joint shear demand | beam tension @ **1.25fy** + column shear from Mpr (18.8.2.1 / 18.8.4.1) | beam tension @ **fy** (18.4.4.7.2 → 18.3.4) | beam tension @ **fy** (18.3.4) | beam tension @ fy (15.4.2.1(b)) |
| Joint Vn coefficients | Table 18.8.4.3 (1.7 / 1.3 / 1.0 / 0.7) | Table 18.8.4.3 (18.4.4.7.4) | **Table 15.5.2.1 (2.0 / 1.7 / 1.3 / 1.0)** | Table 15.5.2.1 |
| Joint φ | **0.85** (21.2.4.4) | **0.75** (18.4.4.7.3 → 21.2.1) | **0.75** (15.5.1.2 → 21.2.1) | 0.75 |
| SCWB ΣMnc ≥ 1.2·ΣMnb | 18.7.3.2 | not required | not required | not required |
| ρl limits | 0.01 – **0.06** (18.7.4.1) | 0.01 – 0.08 (10.6.1.1) | 0.01 – 0.08 (10.6.1.1) | 0.01 – **0.06** (18.14.3.2(b) → 18.7.4.1) |
| Dimensional limits | ≥ 300 mm; b/h ≥ 0.4 (18.7.2.1) | none | none | none |
| Ties within ℓo | s ≤ min(min_dim/4, 6db [5db G550], so = 100+(350−hx)/3) (18.7.5.3); ρs per Table 18.7.5.4; hx ≤ 350 / 200 (18.7.5.2(e)(f)) | so ≤ min(8db, 200) G420 / min(6db, 150) G550 / min_dim/2 (18.4.3.3(a–c)); ℓo ≥ max(ℓu/6, **max(b,h)**, 450) (18.4.3.3(d–f)); no ρs, no hx | no ℓo — general ties full height: s ≤ min(16db, 48dbt, least dim) (25.7.2.1(b)) | s ≤ min(6db, 150) full height + 18.7.5.2(a–e) over ℓo; if Pu > 0.35Po: ½·Table 18.7.5.4(a)(b) (18.14.3.2(b)(c)) |
| Ties outside ℓo | s ≤ min(150, 6db/5db) (18.7.5.5) | Table 10.7.6.5.2 (d/2 branch, ≤ 600) + 25.7.2.1(b) (18.4.3.5) | same 25.7.2.1(b) rule | full-height rule above |
| ASCE 41 rotation | checked (assessment layer, all frame types) | checked | checked | checked |

## Check-by-check inventory

Status codes: ✅ implemented · 🔧 fixed/added in the 2026-07 frame-type update · ➖ not applicable · 🚫 out of scope (documented below).

### Geometry / longitudinal (`aci_longitudinal_checks.py`)

| Check name | SMF | IMF | OMF | Gravity | Clause | Status |
|---|---|---|---|---|---|---|
| `min_dimension` (≥ 300 mm) | ✔ | project rule | project rule | project rule | 18.7.2.1(a) | 🔧 relabeled for SMF |
| `aspect_ratio` (≥ 0.4) | ✔ | ➖ | ➖ | ➖ | 18.7.2.1(b) | 🔧 new |
| `rho_longitudinal_min` (≥ 0.01) | ✔ | ✔ | ✔ | ✔ | 18.7.4.1 / 10.6.1.1 | ✅ |
| `rho_longitudinal_max` | ≤ **0.06** | ≤ 0.08 | ≤ 0.08 | ≤ **0.06** | 18.7.4.1 / 10.6.1.1 / 18.14.3.2(b) | 🔧 was 0.08 for all |
| `n_bars_min_rect`, `bars_each_face_min`, `free_spacing_long_bars`, `core_geometry_positive` | ✔ | ✔ | ✔ | ✔ | 10.7.3.1 / 25.2.3 / model rules | ✅ |

### Transverse (`aci_transverse_checks.py`)

| Check name | Frame | Clause | Status |
|---|---|---|---|
| `sdc_frame_type_consistency` (OMF→SDC B only; IMF→≤C) | all | 18.2.1.1 | 🔧 new warning |
| `lo_x_length` / `lo_y_length` | SMF, Gravity | 18.7.5.1 | ✅ |
| `tie_spacing_within_lo` / `tie_spacing_outside_lo` | SMF | 18.7.5.3 / 18.7.5.5 | ✅ |
| `hook_angle_rectilinear`, `crosstie_diameter`, `crosstie_alternate_anchorage` | SMF | 18.7.5.2(b)(c) | ✅ |
| `hx_general_limit` (≤350) / `hx_special_limit` (≤200) / `all_perimeter_bars_supported` | SMF | 18.7.5.2(e)(f) | ✅ |
| `rho_s_x_required` / `rho_s_y_required` — Table 18.7.5.4 | SMF | Table 18.7.5.4 | 🔧 **kf·kn now only in expr (c); circular (f) kf only** (was over-applied to (a),(b),(d),(e)) |
| `cover_additional_transverse_*` (cover > 100 mm) | SMF, Gravity | 18.7.5.7 | ✅ |
| `imf_lo_length` — ℓo ≥ max(ℓu/6, max(b,h), 450) | IMF | 18.4.3.3(d–f) | 🔧 new |
| `imf_hoop_spacing_within_lo` — min(8db,200)/min(6db,150)/min_dim/2 | IMF | 18.4.3.3(a–c) | 🔧 new |
| `imf_hook_angle_hoops` (seismic hooks) | IMF | 18.4.3.3 / 25.7.4 | 🔧 new |
| `imf_tie_spacing_outside_lo` — min(d/2, 600, 16db, 48dbt, min_dim) | IMF | 18.4.3.5 / 10.7.6.5.2 / 25.7.2.1 | 🔧 new (uses low-Vs branch of Table 10.7.6.5.2, conservative) |
| `imf_tie_diameter` / `omf_tie_diameter` — No.10 (≤No.32 bars) / No.13 | IMF, OMF | 25.7.2.2 | 🔧 new |
| `omf_tie_spacing` / `omf_tie_spacing_midheight` — min(16db, 48dbt, least dim) | OMF | 25.7.2.1(b) | 🔧 new |
| `gravity_*` family (full-height min(6db,150), 18.7.5.2(a–e) over ℓo, 0.35Po trigger → ½·Table(a)(b), cover) | Gravity | 18.14.3.2(b)(c)(d) | ✅ |

### Strength (per load case, `main.py` + `section_capacity.py`)

| Check name | Frame | Basis | Clause | Status |
|---|---|---|---|---|
| `pm_ratio_x/y` | all | P-M interaction at Pu, φ per 21.2.2 | Ch. 22 | ✅ |
| `shear_ratio_analysis_x/y` | all | analysis Vu vs φVn_eff | 22.5 | ✅ |
| `shear_ratio_probable_x/y` | SMF, Gravity | Ve = max((Mpr,t+Mpr,b)/ℓu ∩ beam cap, Vu) | 18.7.6.1 / 18.14.3.2(b) | ✅ |
| `shear_ratio_probable_x/y` | IMF | Ve = (Mn,t+Mn,b)/ℓu | 18.4.3.1(a) | 🔧 new (option (b) ΩoE not computable — (a) is conservative) |
| `shear_ratio_probable_x/y` | OMF | as IMF, only when ℓu ≤ 5c1 (else INFO "n/a") | 18.3.3(a) | 🔧 new |
| `Vc_zero_rule_x/y` (warning + capacity reduction) | SMF, Gravity | Vc = 0 within ℓo if Ve_eq ≥ 0.5Vu and Pu < Agf'c/20 | 18.7.6.2.1 | 🔧 now skipped for IMF/OMF |
| `scwb_top/bottom_x/y` (≥ 1.0 on ΣMnc/1.2ΣMnb) | SMF only | Mnc at case Pu both directions | 18.7.3.2 | 🔧 was run for IMF/OMF too |
| `joint_*_shear_ratio` | all | see regime table | 18.8.4 / 18.4.4.7 / 18.3.4 / 15.5 | 🔧 φ, αj table and fy-factor now frame-dependent |
| `joint_*_depth_20db` — h_joint ≥ 20db (G420) / 26db (G550) of largest beam bar | SMF | 18.8.2.3 | 🔧 new |
| `joint_*_15.5.2.5_a..d` (transverse-beam confinement conditions) | all | Table 15.5.2.5 | ✅ |
| `asce41_rot_ratio_x/y` + parameters | all | ASCE 41-17 Table 10-8 | ✅ |

## Implementation notes

- Joint tension for two-sided joints is scenario-based:
  `T = max(T_neg,s1 + T_pos,s2 ; T_pos,s1 + T_neg,s2)` at 1.25fy (SMF) or fy (others).
- Non-SMF joint column shear uses column Mn capped by beam joint Mn
  (`Ve_col_Mn_joint`), mirroring the SMF Mpr cap — consistent joint free-body.
- Frame classification lives in `frame_types.py::frame_class()`; unknown values
  default to SMF (most demanding).

## Known out-of-scope items (🚫)

| Provision | Why |
|---|---|
| 18.7.4.3 bond/splitting (1.25ℓd ≤ ℓu/2 or Ktr ≥ 1.2db) | needs ℓd computation (25.4.2); no input for Ktr |
| 18.7.4.4 lap-splice location/class | no splice inputs (ASCE 41 splice flags are assessment-only) |
| 18.4.3.4 first hoop ≤ so/2 from joint face | no "first hoop offset" input |
| 18.4.4.4 joint transverse spacing within deepest beam | joint ties not modeled |
| 18.4.4.2 deep-beam joints (beam h > 2× column depth) → strut-and-tie | outside simplified joint model |
| 18.4.3.1(b) / 18.3.3(b) ΩoE-amplified analysis shear alternative | load input doesn't separate the E component; option (a) used (conservative) |
| 18.7.5.6 / 18.4.3.6 columns under discontinued stiff members | no wall-discontinuity input |
| 18.7.3.1 SCWB exemption (discontinuous column above + Pu < Agf'c/10) | SCWB always checked when beams present (conservative) |
| High-Vs branch of Table 10.7.6.5.2 (d/4, 300) for IMF outside ℓo | d/2 branch used together with 25.7.2.1(b); flag if Vs > 0.33√f'c·bw·d governs |
