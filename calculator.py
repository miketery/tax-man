import argparse
import json
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


@lru_cache(maxsize=None)
def load_json(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Tax data not found: {path.relative_to(DATA_DIR.parent)}")
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

def main():
    years = federal_years()
    parser = argparse.ArgumentParser(description="Estimate US income and payroll taxes on wage income.")
    parser.add_argument('income', type=float, help="Your annual gross wage income.")
    parser.add_argument('--year', '-y', type=int, default=years[0],
                        help=f"The tax year (default: {years[0]}, the latest with data).")
    parser.add_argument('--status', type=str, default='single', choices=list(FILING_STATUSES),
                        help="Your filing status (default: single).")
    parser.add_argument('--state', type=str, default=None,
                        help="State slug, e.g. new-york (see data/state/). Omit for federal only.")
    parser.add_argument('--city', type=str, default=None,
                        help="City slug, e.g. new-york-city (see data/city/). Implies its state.")
    args = parser.parse_args()

    result = calculate(args.income, args.year, args.status, args.state, args.city)

    print(f"Income ${result.income:,.2f} | {args.year} | {FILING_STATUSES[args.status]}")
    print('-' * 64)
    print(f"{'Tax':<36}{'Amount':>14}{'Marginal':>14}")
    for line in result.lines:
        print(f"{line.name:<36}{line.amount:>14,.2f}{line.marginal_rate:>13.2f}%")
    print('-' * 64)
    print(f"{'Total':<36}{result.total:>14,.2f}{result.marginal_rate:>13.2f}%")
    print(f"Effective rate: {result.effective_rate:.2f}%")
    print(f"Take-home pay:  ${result.take_home:,.2f}")


if __name__ == "__main__":
    main()
