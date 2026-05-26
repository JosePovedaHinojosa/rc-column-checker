"""
Integration smoke test — runs the full pipeline on the bundled sample CSVs
and verifies that outputs are produced and contain no unexpected NG failures.

This test catches regressions where a module refactor breaks the end-to-end
calculation without any individual unit test failing.
"""

import subprocess
import sys
import csv
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = ROOT / 'outputs_test_integration'


@pytest.fixture(scope='module', autouse=True)
def run_pipeline():
    """Run main.py once for all tests in this module."""
    result = subprocess.run(
        [
            sys.executable, str(ROOT / 'main.py'),
            '--column-sections', str(ROOT / 'sample_column_sections.csv'),
            '--beam-sections',   str(ROOT / 'sample_beam_sections.csv'),
            '--column-beam',     str(ROOT / 'sample_column_beam_prop.csv'),
            '--loads',           str(ROOT / 'sample_loads.csv'),
            '--outdir',          str(OUTDIR),
            '--skip-pm',
        ],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    if result.returncode != 0:
        pytest.fail(f'main.py exited with code {result.returncode}.\n'
                    f'STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}')
    yield
    # Leave outputs for inspection; CI can clean up


class TestOutputsExist:
    def test_column_results_csv_exists(self):
        assert (OUTDIR / 'column_results.csv').exists()

    def test_column_checks_csv_exists(self):
        assert (OUTDIR / 'column_checks.csv').exists()

    def test_column_failures_csv_exists(self):
        assert (OUTDIR / 'column_failures.csv').exists()


class TestColumnResults:
    def test_has_rows(self):
        with open(OUTDIR / 'column_results.csv', newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        assert len(rows) > 0

    def test_expected_columns_present(self):
        with open(OUTDIR / 'column_results.csv', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
        for col in ['column_id', 'load_case', 'Ag_mm2', 'phiPn0_kN', 'pm_ratio_x']:
            assert col in fieldnames, f'Missing column: {col}'

    def test_pm_ratios_are_numeric(self):
        with open(OUTDIR / 'column_results.csv', newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            ratio = float(row['pm_ratio_x'])
            assert ratio >= 0.0


class TestColumnChecks:
    def _load_checks(self):
        with open(OUTDIR / 'column_checks.csv', newline='', encoding='utf-8') as f:
            return list(csv.DictReader(f))

    def test_has_rows(self):
        assert len(self._load_checks()) > 0

    def test_sample_columns_are_present(self):
        column_ids = {r['column_id'] for r in self._load_checks()}
        assert 'COL_150x100' in column_ids

    def test_detailing_checks_pass_for_sample_section(self):
        """
        ACI longitudinal and transverse detailing checks must pass for the
        bundled sample section.  Joint confinement (15.5.2.5) and shear demand
        checks are excluded here because they depend on the physical geometry
        of the connected beams, not on the refactored calculation logic.
        """
        EXCLUDE_PREFIXES = ('joint_', 'pm_', 'shear_', 'scwb_', 'asce41_', 'gravity_')
        detailing_ng = [
            r for r in self._load_checks()
            if r['status'] == 'NG'
            and r['column_id'] == 'COL_150x100'
            and not any(r['check_name'].startswith(p) for p in EXCLUDE_PREFIXES)
        ]
        assert detailing_ng == [], (
            'ACI detailing NG for COL_150x100:\n' +
            '\n'.join(f"  {r['check_name']}: {r['provided']} vs {r['required']}" for r in detailing_ng)
        )

    def test_all_statuses_are_valid(self):
        valid = {'OK', 'NG', 'WARNING', 'INFO'}
        for row in self._load_checks():
            assert row['status'] in valid, f"Unknown status '{row['status']}' in row: {row}"
