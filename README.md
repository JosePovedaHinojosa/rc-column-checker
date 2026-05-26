# rc_column_checker_v18

Version focused on **cleaner inputs** and **more robust report generation**.

## Input architecture

The property input is split into **three CSV files**, plus the loads file:

1. `sample_column_sections_v18.csv`
   - reusable column section library
   - geometry, materials, longitudinal steel, transverse steel, support lines, and optional section-level overrides
   - most normative defaults such as `rho_min`, `rho_max`, and `min_dim_required_mm` are now handled internally, so they can be omitted from the CSV unless you want to override them

2. `sample_beam_sections_v18.csv`
   - reusable beam section library
   - beam geometry, materials, top/bottom steel, and stirrup diameter

3. `sample_column_beam_prop_v18.csv`
   - one row per column/joint assembly
   - references one `column_section_id`
   - references **two explicit beams per joint face**
   - `lu_mm` is now optional; when omitted, the code uses `clear_height_mm`
   - `gravity_design_actions_checked` is optional; when omitted, the default is `True`

4. `sample_loads_v18.csv`
   - load combinations linked by `column_id`

## Main additions in v18

- Keeps explicit `side1` / `side2` beam definitions from v17.
- Cleans the sample inputs by removing redundant normative defaults from the visible CSVs.
- `lu_mm` is optional and defaults to `clear_height_mm`.
- `gravity_design_actions_checked` is optional and defaults to `True`.
- LaTeX reports can now hide sections using CLI flags:
  - `--hide-rotation-table`
  - `--hide-beam-table`
  - `--hide-joint-table`
- Static checks in the report no longer print `INFO` rows.
- Empty report tables are rendered safely without `\bottomrule` issues.
- `WARN`, `NG`, and D/C ratios greater than 1.0 are highlighted in red in the LaTeX report.

## Run

```bash
python main.py ^
  --column-sections sample_column_sections_v18.csv ^
  --beam-sections sample_beam_sections_v18.csv ^
  --column-beam sample_column_beam_prop_v18.csv ^
  --loads sample_loads_v18.csv ^
  --outdir outputs
```

Generate LaTeX reports only for selected columns:

```bash
python main.py ^
  --column-sections sample_column_sections_v18.csv ^
  --beam-sections sample_beam_sections_v18.csv ^
  --column-beam sample_column_beam_prop_v18.csv ^
  --loads sample_loads_v18.csv ^
  --outdir outputs ^
  --report-columns COL_150x100,COL_150x100_ROOF ^
  --pry-name "Mi Proyecto"
```

Generate LaTeX reports for all columns:

```bash
python main.py ^
  --column-sections sample_column_sections_v18.csv ^
  --beam-sections sample_beam_sections_v18.csv ^
  --column-beam sample_column_beam_prop_v18.csv ^
  --loads sample_loads_v18.csv \^
  --outdir outputs ^
  --report-all ^
  --pry-name "Mi Proyecto"
```

Example hiding some report sections:

```bash
python main.py ^
  --column-sections sample_column_sections_v18.csv ^
  --beam-sections sample_beam_sections_v18.csv ^
  --column-beam sample_column_beam_prop_v18.csv ^
  --loads sample_loads_v18.csv ^
  --outdir outputs_2 ^
  --report-columns COL_150x100 ^
  --pry-name "Mi Proyecto" ^
  --hide-rotation-table ^
  --hide-joint-table
```

## Notes

- Column flexure uses strain compatibility with a simplified rectangular section, Whitney stress block, and bilinear steel.
- Beam flexure and joint shear demand remain simplified engineering checks intended for automation and screening.
- For adjacent columns:
  - `same` uses the current column section
  - `none` uses zero contribution
  - any other value must match a `column_section_id` in the column-section library
- To compile the generated LaTeX report with the requested logo header, keep `logo_black_horizontal.png` two levels above the generated `.tex` file, matching the relative path `../../logo_black_horizontal.png`.
- To compile the generated LaTeX report with the section plots, keep sections folder two levels above the generated `.tex` file, matching the relative path `../../sections/COL150x100.png`.
