import argparse
import csv
import io
import json
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / 'data'

FILING_STATUSES = {
    'single': 'Single',
    'married_filing_jointly': 'Married filing jointly',
    'married_filing_separately': 'Married filing separately',
    'head_of_household': 'Head of household',
}

# Additional Medicare Tax (0.9%) thresholds, in effect since 2013. Not indexed to inflation.
ADDITIONAL_MEDICARE_RATE = 0.9
ADDITIONAL_MEDICARE_THRESHOLDS = {
    'single': 200000,
    'married_filing_jointly': 250000,
    'married_filing_separately': 125000,
    'head_of_household': 200000,
}

# Step used to measure marginal rates numerically (tax on income + step vs. tax on income).
MARGINAL_STEP = 100.0


class TaxDataNotFoundError(FileNotFoundError):
    """Raised when a tax data file cannot be found."""


@lru_cache(maxsize=None)
def load_json(path):
    path = Path(path)
    if not path.exists():
        raise TaxDataNotFoundError(f"Tax data not found: {path.relative_to(DATA_DIR.parent)}")
    with open(path, 'r') as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Data discovery
# ---------------------------------------------------------------------------

def federal_years():
    """Years with federal income tax data, newest first."""
    return sorted((int(p.stem) for p in (DATA_DIR / 'federal').glob('[0-9]*.json')), reverse=True)


def _locations(kind, year):
    found = {}
    for path in sorted((DATA_DIR / kind).glob(f'*/{year}.json')):
        found[path.parent.name] = load_json(path)
    return found


def latest_year(state=None, city=None):
    """Newest year with federal data and (if given) data for the state/city."""
    for year in federal_years():
        if state and not (DATA_DIR / 'state' / state / f'{year}.json').exists():
            continue
        if city and not (DATA_DIR / 'city' / city / f'{year}.json').exists():
            continue
        return year
    raise TaxDataNotFoundError(f"No year has data for state={state!r} city={city!r}")


def available_states(year):
    """{slug: name} of states with data for the given year, sorted by name."""
    states = _locations('state', year)
    return dict(sorted(((slug, d.get('name', slug)) for slug, d in states.items()), key=lambda kv: kv[1]))


def available_cities(year):
    """{slug: {'name', 'state'}} of cities/localities with data for the given year, sorted by name."""
    cities = _locations('city', year)
    return dict(sorted(
        ((slug, {'name': d.get('name', slug), 'state': d.get('state')}) for slug, d in cities.items()),
        key=lambda kv: kv[1]['name'],
    ))


def get_federal_tax_data(year):
    return load_json(DATA_DIR / 'federal' / f'{year}.json')


def get_federal_fica_brackets(year):
    """FICA brackets for the year, or None if FICA did not exist yet (pre-1937)."""
    return load_json(DATA_DIR / 'federal' / 'fica_rates.json').get(str(year))


def get_state_tax_data(year, state):
    return load_json(DATA_DIR / 'state' / state / f'{year}.json')


def get_city_tax_data(year, city):
    return load_json(DATA_DIR / 'city' / city / f'{year}.json')


# ---------------------------------------------------------------------------
# Core math
# ---------------------------------------------------------------------------

def tax_using_brackets(amount, brackets):
    """Progressive tax on `amount` given [[threshold, rate_percent], ...] brackets (ascending)."""
    tax = 0.0
    if amount <= 0:
        return 0.0
    for i, (start, rate) in enumerate(brackets):
        start = float(start)
        if amount <= start:
            break
        end = float(brackets[i + 1][0]) if i + 1 < len(brackets) else None
        top = amount if end is None else min(amount, end)
        tax += (top - start) * float(rate) / 100.0
    return tax


def _deduction(data, status, override=None):
    if override is not None:
        return float(override)
    return float(data.get('deductions', {}).get(status, 0))


def _income_tax(income, data, status, deduction_override=None):
    deduction = _deduction(data, status, deduction_override)
    taxable = max(0.0, income - deduction)
    tax = tax_using_brackets(taxable, data['brackets'][status])
    tax = max(0.0, tax - float(data.get('credits', {}).get(status, 0)))
    return tax, taxable, deduction


def _payroll_taxes(wages, data):
    """Employee-side payroll taxes defined on a state/city (e.g. SDI, paid family leave)."""
    lines = []
    for p in data.get('payroll_taxes', []):
        if 'flat' in p:
            amount = float(p['flat']) if wages > 0 else 0.0
        else:
            amount = tax_using_brackets(wages, p['brackets'])
        lines.append((p['name'], amount))
    return lines


# ---------------------------------------------------------------------------
# Public calculators
# ---------------------------------------------------------------------------

def calculate_federal_tax(income, year, status, deduction_override=None):
    """Federal income tax."""
    tax, taxable, deduction = _income_tax(income, get_federal_tax_data(year), status, deduction_override)
    return {'tax_amount': tax, 'taxable_income': taxable, 'deduction': deduction}


def calculate_federal_fica(income, year, status='single'):
    """Employee share of Social Security (OASDI) and Medicare (HI), incl. Additional Medicare Tax."""
    fica = get_federal_fica_brackets(year)
    if fica is None:
        return {'oasdi_tax': 0.0, 'medicare_tax': 0.0, 'total_fica_tax': 0.0}
    oasdi = tax_using_brackets(income, fica['OASDI'])
    medicare = tax_using_brackets(income, fica['HI'])
    if year >= 2013:
        threshold = ADDITIONAL_MEDICARE_THRESHOLDS[status]
        medicare += max(0.0, income - threshold) * ADDITIONAL_MEDICARE_RATE / 100.0
    return {'oasdi_tax': oasdi, 'medicare_tax': medicare, 'total_fica_tax': oasdi + medicare}


def calculate_state_tax(income, year, state, status):
    tax, taxable, deduction = _income_tax(income, get_state_tax_data(year, state), status)
    return {'tax_amount': tax, 'taxable_income': taxable, 'deduction': deduction}


def calculate_city_tax(income, year, city, status, state_tax=0.0):
    data = get_city_tax_data(year, city)
    tax, taxable, deduction = _income_tax(income, data, status)
    tax += state_tax * float(data.get('state_tax_surcharge', 0)) / 100.0
    return {'tax_amount': tax, 'taxable_income': taxable, 'deduction': deduction}


@dataclass
class TaxLine:
    category: str  # 'federal', 'fica', 'state', 'city'
    name: str
    amount: float
    marginal_rate: float = 0.0  # percent


@dataclass
class TaxResult:
    income: float
    year: int
    status: str
    state: str | None = None
    city: str | None = None
    lines: list[TaxLine] = field(default_factory=list)

    @property
    def total(self):
        return sum(line.amount for line in self.lines)

    @property
    def take_home(self):
        return self.income - self.total

    @property
    def effective_rate(self):
        return self.total / self.income * 100.0 if self.income > 0 else 0.0

    @property
    def marginal_rate(self):
        return sum(line.marginal_rate for line in self.lines)

    def by_category(self):
        totals = {}
        for line in self.lines:
            totals[line.category] = totals.get(line.category, 0.0) + line.amount
        return totals


def _tax_lines(income, year, status, state=None, city=None):
    lines = []

    federal = calculate_federal_tax(income, year, status)
    lines.append(TaxLine('federal', 'Federal income tax', federal['tax_amount']))

    fica = calculate_federal_fica(income, year, status)
    lines.append(TaxLine('fica', 'Social Security', fica['oasdi_tax']))
    lines.append(TaxLine('fica', 'Medicare', fica['medicare_tax']))

    state_tax = 0.0
    if state:
        data = get_state_tax_data(year, state)
        state_tax = calculate_state_tax(income, year, state, status)['tax_amount']
        lines.append(TaxLine('state', f"{data.get('name', state)} income tax", state_tax))
        for name, amount in _payroll_taxes(income, data):
            lines.append(TaxLine('state', name, amount))

    if city:
        data = get_city_tax_data(year, city)
        city_tax = calculate_city_tax(income, year, city, status, state_tax)['tax_amount']
        lines.append(TaxLine('city', f"{data.get('name', city)} income tax", city_tax))
        for name, amount in _payroll_taxes(income, data):
            lines.append(TaxLine('city', name, amount))

    return lines


def calculate(income, year, status='single', state=None, city=None):
    """Full breakdown of taxes on wage income for a filing status and optional state/city.

    If a city is given without a state, the city's own state is used.
    """
    if status not in FILING_STATUSES:
        raise ValueError(f"Unknown filing status {status!r}; expected one of {list(FILING_STATUSES)}")
    income = max(0.0, float(income))
    if city and not state:
        state = get_city_tax_data(year, city).get('state')

    lines = _tax_lines(income, year, status, state, city)
    bumped = _tax_lines(income + MARGINAL_STEP, year, status, state, city)
    for line, next_line in zip(lines, bumped):
        line.marginal_rate = (next_line.amount - line.amount) / MARGINAL_STEP * 100.0

    return TaxResult(income=income, year=year, status=status, state=state, city=city, lines=lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _label(result):
    return result.city or result.state or 'federal only'


def format_text(results):
    parts = []
    for r in results:
        where = f" | {_label(r)}" if (r.state or r.city) else ''
        rows = [
            f"Income ${r.income:,.2f} | {r.year} | {FILING_STATUSES[r.status]}{where}",
            '-' * 64,
            f"{'Tax':<36}{'Amount':>14}{'Marginal':>14}",
        ]
        rows += [f"{line.name:<36}{line.amount:>14,.2f}{line.marginal_rate:>13.2f}%" for line in r.lines]
        rows += [
            '-' * 64,
            f"{'Total':<36}{r.total:>14,.2f}{r.marginal_rate:>13.2f}%",
            f"Effective rate: {r.effective_rate:.2f}%",
            f"Take-home pay:  ${r.take_home:,.2f}",
        ]
        parts.append('\n'.join(rows))
    return '\n\n'.join(parts)


def _as_dict(r):
    totals = r.by_category()
    row = {
        'income': r.income, 'year': r.year, 'status': r.status, 'state': r.state, 'city': r.city,
        'federal_tax': totals.get('federal', 0.0), 'fica_tax': totals.get('fica', 0.0),
        'state_tax': totals.get('state', 0.0), 'city_tax': totals.get('city', 0.0),
        'total_tax': r.total, 'effective_rate': r.effective_rate, 'marginal_rate': r.marginal_rate,
        'take_home': r.take_home,
    }
    return {k: round(v, 2) if isinstance(v, float) else v for k, v in row.items()}


def format_json(results):
    return json.dumps(
        [{**_as_dict(r), 'lines': [vars(line) for line in r.lines]} for r in results], indent=2
    )


def format_csv(results):
    rows = [_as_dict(r) for r in results]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().rstrip('\n')


def main():
    parser = argparse.ArgumentParser(description="Estimate US income and payroll taxes on wage income.")
    parser.add_argument('income', type=float, help="Your annual gross wage income.")
    parser.add_argument('--year', '-y', type=int, default=None,
                        help="The tax year (default: the latest year with data for every location).")
    parser.add_argument('--status', type=str, default='single', choices=list(FILING_STATUSES),
                        help="Your filing status (default: single).")
    parser.add_argument('--state', action='append', default=[],
                        help="State slug, e.g. new-york (see data/state/). Repeat to compare several.")
    parser.add_argument('--city', action='append', default=[],
                        help="City slug, e.g. new-york-city (see data/city/); implies its state. Repeatable.")
    parser.add_argument('--format', '-f', choices=['text', 'csv', 'json'], default='text',
                        help="Output format (default: text).")
    args = parser.parse_args()

    # Each --state and each --city is its own location; with neither, compute federal only.
    locations = [(s, None) for s in args.state] + [(None, c) for c in args.city] or [(None, None)]

    try:
        if args.year is None:
            args.year = min(latest_year(s, c) for s, c in locations)
        results = [calculate(args.income, args.year, args.status, s, c) for s, c in locations]
    except TaxDataNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    formatter = {'text': format_text, 'json': format_json, 'csv': format_csv}[args.format]
    print(formatter(results))


if __name__ == "__main__":
    main()
