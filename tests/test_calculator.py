import json
from pathlib import Path

import pytest

import calculator as calc

STATUSES = list(calc.FILING_STATUSES)


def test_brackets_basic():
    brackets = [[0, 10], [100, 20], [200, 30]]
    assert calc.tax_using_brackets(0, brackets) == 0
    assert calc.tax_using_brackets(-50, brackets) == 0
    assert calc.tax_using_brackets(50, brackets) == pytest.approx(5)
    assert calc.tax_using_brackets(100, brackets) == pytest.approx(10)
    assert calc.tax_using_brackets(150, brackets) == pytest.approx(20)
    assert calc.tax_using_brackets(300, brackets) == pytest.approx(10 + 20 + 30)


def test_federal_2025_single_100k():
    # OBBBA standard deduction 15,750 -> taxable 84,250
    r = calc.calculate_federal_tax(100_000, 2025, 'single')
    assert r['taxable_income'] == 84_250
    assert r['tax_amount'] == pytest.approx(1192.5 + 4386 + (84_250 - 48_475) * 0.22)


def test_income_below_deduction_is_zero_tax():
    assert calc.calculate(10_000, 2025, 'single').by_category()['federal'] == 0


def test_fica_cap_and_additional_medicare():
    r = calc.calculate_federal_fica(300_000, 2025, 'single')
    assert r['oasdi_tax'] == pytest.approx(176_100 * 0.062)
    assert r['medicare_tax'] == pytest.approx(300_000 * 0.0145 + 100_000 * 0.009)
    mfj = calc.calculate_federal_fica(300_000, 2025, 'married_filing_jointly')
    assert mfj['medicare_tax'] == pytest.approx(300_000 * 0.0145 + 50_000 * 0.009)


def test_marginal_rates():
    r = calc.calculate(100_000, 2025, 'single')
    assert r.marginal_rate == pytest.approx(22 + 6.2 + 1.45)
    above_cap = calc.calculate(250_000, 2025, 'single')
    assert above_cap.marginal_rate == pytest.approx(32 + 1.45 + 0.9)


def test_old_year_without_deductions_or_fica():
    r = calc.calculate(5_000, 1913, 'single')
    assert r.by_category()['fica'] == 0


def test_ny_state_and_nyc():
    ny = calc.calculate_state_tax(100_000, 2025, 'new-york', 'single')
    assert ny['tax_amount'] == pytest.approx(340 + 144 + 115.5 + 3671.25 + 681)
    nyc = calc.calculate_city_tax(100_000, 2025, 'new-york-city', 'single')
    assert nyc['tax_amount'] == pytest.approx(369.36 + 489.06 + 954.75 + 1627.92)


def test_city_implies_state():
    r = calc.calculate(100_000, 2025, 'single', city='new-york-city')
    assert r.state == 'new-york'
    assert r.by_category()['state'] > 0


def _location_files():
    return sorted(calc.DATA_DIR.glob('state/*/*.json')) + sorted(calc.DATA_DIR.glob('city/*/*.json'))


@pytest.mark.parametrize('path', _location_files(), ids=lambda p: f'{p.parent.parent.name}/{p.parent.name}')
def test_location_data_is_well_formed(path: Path):
    data = json.loads(path.read_text())
    assert data['name'] and data['type'] in ('state', 'city')
    assert data['year'] == int(path.stem)
    for status in STATUSES:
        assert status in data['deductions']
        brackets = data['brackets'][status]
        assert brackets[0][0] == 0
        thresholds = [b[0] for b in brackets]
        assert thresholds == sorted(thresholds) and len(set(thresholds)) == len(thresholds)
        assert all(0 <= b[1] < 20 for b in brackets)
    for p in data.get('payroll_taxes', []):
        assert 'flat' in p or 'brackets' in p
    if data['type'] == 'city':
        assert (calc.DATA_DIR / 'state' / data['state'] / path.name).exists()
    # Every location computes for every status.
    for status in STATUSES:
        kw = {'city': path.parent.name} if data['type'] == 'city' else {'state': path.parent.name}
        assert calc.calculate(150_000, data['year'], status, **kw).total > 0


def test_2026_federal_and_fica():
    r = calc.calculate(100_000, 2026, 'single')
    # 2026 standard deduction 16,100 -> taxable 83,900
    assert r.by_category()['federal'] == pytest.approx(1240 + (50_400 - 12_400) * 0.12 + (83_900 - 50_400) * 0.22)
    assert calc.calculate_federal_fica(200_000, 2026)['oasdi_tax'] == pytest.approx(184_500 * 0.062)


def test_latest_year():
    assert calc.latest_year() == calc.federal_years()[0]
    assert calc.latest_year(state='oregon') == 2025
    with pytest.raises(calc.TaxDataNotFoundError):
        calc.latest_year(state='atlantis')


def test_cli_formats(capsys, monkeypatch):
    monkeypatch.setattr('sys.argv', ['calculator.py', '100000', '--state', 'texas', '--city', 'new-york-city', '-f', 'csv'])
    calc.main()
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 3 and lines[0].startswith('income,year')
    monkeypatch.setattr('sys.argv', ['calculator.py', '100000', '-f', 'json'])
    calc.main()
    assert json.loads(capsys.readouterr().out)[0]['total_tax'] > 0
