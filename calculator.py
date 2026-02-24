import argparse
import csv
import io
import json
import sys
from datetime import datetime
from itertools import product


class TaxDataNotFoundError(Exception):
    """Raised when a tax data file cannot be found."""
    pass


def load_json(file_path):
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise TaxDataNotFoundError(f"{file_path} not found.")

def get_federal_tax_data(year):
    tax_data = load_json(f'data/federal/{year}.json')
    return tax_data


def get_federal_fica_brackets(year):
    fica_data = load_json('data/federal/fica_rates.json')
    return fica_data[str(year)]


def get_state_tax_data(year, state):
    state_data = load_json(f'data/state/{state}/{year}.json')
    return state_data


def get_city_tax_brackets(year, city):
    city_data = load_json(f'data/city/{city}/{year}.json')
    return city_data

def _tax_using_brackets(income, brackets):
    tax = 0.0
    marginal_tax_rate = 0.0
    for i in range(len(brackets)):
        bracket_start, rate = brackets[i]
        next_bracket_start, next_rate = brackets[i+1] if i+1 < len(brackets) else (None, None)

        marginal_tax_rate = float(rate)
        if next_bracket_start is not None and income > float(next_bracket_start):
            owed = (float(next_bracket_start) - float(bracket_start)) * float(rate) / 100.0
        else:
            owed = (income - float(bracket_start)) * float(rate) / 100.0

        tax += owed 

        if next_bracket_start is None or income < float(next_bracket_start):
            break

    return {
        'tax_amount': tax,
        'marginal_tax_rate': marginal_tax_rate,
    }

def calculate_federal_tax(income, year, status, deduction_override: int=None):
    """Calculates the federal income tax."""
    federal_data = get_federal_tax_data(year)
    if 'deductions' in federal_data:
        deduction = federal_data['deductions'][status] if deduction_override is None else deduction_override
    else:
        deduction = 0 if deduction_override is None else deduction_override
    tax_brackets = federal_data['brackets'][status]
    federal_tax = _tax_using_brackets(income - deduction, tax_brackets)

    return {
        'federal_tax': federal_tax,
        'federal_tax_rate': federal_tax['tax_amount'] / income if income > 0 else 0,
        'federal_marginal_tax_rate': federal_tax['marginal_tax_rate'],
        'taxable_income': income - deduction,
        'deduction': deduction,
    }

def calculate_federal_fica(income, year):
    fica_brackets = get_federal_fica_brackets(year)
    oasdi_tax = _tax_using_brackets(income, fica_brackets['OASDI'])
    medicare_tax = _tax_using_brackets(income, fica_brackets['HI'])

    # afforadable medicare tax
    if year >= 2013 and income > 200000:
        medicare_tax['tax_amount'] += (income - 200000) * 0.009
        medicare_tax['marginal_tax_rate'] += 0.009

    return {
        'oasdi_tax': oasdi_tax,
        'medicare_tax': medicare_tax,
        'total_fica_tax': oasdi_tax['tax_amount'] + medicare_tax['tax_amount'],
        'total_fica_tax_rate': (oasdi_tax['tax_amount'] + medicare_tax['tax_amount']) / income if income > 0 else 0,
        'marginal_fica_tax_rate': max(oasdi_tax['marginal_tax_rate'], medicare_tax['marginal_tax_rate']),
    }

def calculate_state_tax(income, year, state, status):
    data = get_state_tax_data(year, state)
    brackets = data['brackets'][status]
    if 'deductions' in data:
        deduction = data['deductions'][status]
    else:
        deduction = 0
    income_after_deduction = income - deduction
    return _tax_using_brackets(income_after_deduction, brackets)

def calculate_city_tax(income, year, city, status):
    data = get_city_tax_brackets(year, city)
    brackets = data['brackets'][status]
    if 'deductions' in data:
        deduction = data['deductions'][status]
    else:
        deduction = 0
    income_after_deduction = income - deduction
    return _tax_using_brackets(income_after_deduction, brackets)

def build_location_combos(states, cities):
    """Build list of (state, city) tuples from CLI arguments."""
    if states is None and cities is None:
        return [(None, None)]
    if states is not None and cities is None:
        return [(s, None) for s in states]
    if states is None and cities is not None:
        return [(None, c) for c in cities]
    # Both provided
    if len(states) == len(cities):
        return list(zip(states, cities))
    return list(product(states, cities))


def compute_tax_summary(income, year, status, state=None, city=None):
    """Compute a structured tax summary dict for one location combo."""
    result = {
        'input': {
            'income': income,
            'year': year,
            'status': status,
            'state': state,
            'city': city,
        },
    }

    # Federal
    federal = calculate_federal_tax(income, year, status)
    result['federal'] = {
        'tax': federal['federal_tax']['tax_amount'],
        'effective_rate': federal['federal_tax_rate'] if income > 0 else 0,
        'marginal_rate': federal['federal_marginal_tax_rate'] / 100,
        'deduction': federal['deduction'],
        'taxable_income': federal['taxable_income'],
    }

    # FICA
    fica = calculate_federal_fica(income, year)
    result['fica'] = {
        'social_security': fica['oasdi_tax']['tax_amount'],
        'medicare': fica['medicare_tax']['tax_amount'],
        'total': fica['total_fica_tax'],
    }

    total_tax = federal['federal_tax']['tax_amount'] + fica['total_fica_tax']

    # State
    if state is not None:
        try:
            state_res = calculate_state_tax(income, year, state, status)
            result['state'] = {
                'tax': state_res['tax_amount'],
                'effective_rate': state_res['tax_amount'] / income if income > 0 else 0,
                'marginal_rate': state_res['marginal_tax_rate'] / 100,
            }
            total_tax += state_res['tax_amount']
        except TaxDataNotFoundError as e:
            result['state'] = {'error': str(e)}
    else:
        result['state'] = None

    # City
    if city is not None:
        try:
            city_res = calculate_city_tax(income, year, city, status)
            result['city'] = {
                'tax': city_res['tax_amount'],
                'effective_rate': city_res['tax_amount'] / income if income > 0 else 0,
                'marginal_rate': city_res['marginal_tax_rate'] / 100,
            }
            total_tax += city_res['tax_amount']
        except TaxDataNotFoundError as e:
            result['city'] = {'error': str(e)}
    else:
        result['city'] = None

    result['totals'] = {
        'total_tax': total_tax,
        'effective_rate': total_tax / income if income > 0 else 0,
        'take_home': income - total_tax,
    }

    return result


def format_text(results):
    """Human-readable text output."""
    parts = []
    for r in results:
        inp = r['input']
        lines = []
        label = f"Income: ${inp['income']:,.2f} | Year: {inp['year']} | Status: {inp['status']}"
        if inp['state']:
            label += f" | State: {inp['state']}"
        if inp['city']:
            label += f" | City: {inp['city']}"
        lines.append(label)
        lines.append("=" * len(label))

        # Federal
        fed = r['federal']
        lines.append(f"Federal tax owed: ${fed['tax']:,.2f}")
        lines.append(f"Federal effective rate: {fed['effective_rate']:.2%}")
        lines.append(f"Federal marginal rate: {fed['marginal_rate']:.2%}")
        lines.append(f"Federal deduction: ${fed['deduction']:,.2f}")
        lines.append(f"Federal taxable income: ${fed['taxable_income']:,.2f}")

        # FICA
        fica = r['fica']
        lines.append("--------------------------------")
        lines.append(f"FICA Social Security: ${fica['social_security']:,.2f}")
        lines.append(f"FICA Medicare: ${fica['medicare']:,.2f}")
        lines.append(f"FICA total: ${fica['total']:,.2f}")

        # State
        if r['state'] is not None:
            lines.append("--------------------------------")
            if 'error' in r['state']:
                lines.append(f"State tax: ERROR - {r['state']['error']}")
            else:
                st = r['state']
                lines.append(f"State tax owed: ${st['tax']:,.2f}")
                lines.append(f"State effective rate: {st['effective_rate']:.2%}")
                lines.append(f"State marginal rate: {st['marginal_rate']:.2%}")

        # City
        if r['city'] is not None:
            lines.append("--------------------------------")
            if 'error' in r['city']:
                lines.append(f"City tax: ERROR - {r['city']['error']}")
            else:
                ct = r['city']
                lines.append(f"City tax owed: ${ct['tax']:,.2f}")
                lines.append(f"City effective rate: {ct['effective_rate']:.2%}")
                lines.append(f"City marginal rate: {ct['marginal_rate']:.2%}")

        # Totals
        tot = r['totals']
        lines.append("================================")
        lines.append(f"Total Tax: ${tot['total_tax']:,.2f}")
        lines.append(f"Total Effective Rate: {tot['effective_rate']:.2%}")
        lines.append(f"Take Home: ${tot['take_home']:,.2f}")

        parts.append('\n'.join(lines))

    return '\n\n'.join(parts)


def format_json(results):
    """JSON output."""
    return json.dumps(results, indent=2)


def format_csv(results):
    """Flat CSV output, one row per location combo."""
    fieldnames = [
        'income', 'year', 'status', 'state', 'city',
        'federal_tax', 'federal_effective_rate', 'federal_marginal_rate',
        'federal_deduction', 'federal_taxable_income',
        'fica_social_security', 'fica_medicare', 'fica_total',
        'state_tax', 'state_effective_rate', 'state_marginal_rate',
        'city_tax', 'city_effective_rate', 'city_marginal_rate',
        'total_tax', 'total_effective_rate', 'take_home',
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for r in results:
        row = {
            'income': r['input']['income'],
            'year': r['input']['year'],
            'status': r['input']['status'],
            'state': r['input']['state'] or '',
            'city': r['input']['city'] or '',
            'federal_tax': r['federal']['tax'],
            'federal_effective_rate': r['federal']['effective_rate'],
            'federal_marginal_rate': r['federal']['marginal_rate'],
            'federal_deduction': r['federal']['deduction'],
            'federal_taxable_income': r['federal']['taxable_income'],
            'fica_social_security': r['fica']['social_security'],
            'fica_medicare': r['fica']['medicare'],
            'fica_total': r['fica']['total'],
            'total_tax': r['totals']['total_tax'],
            'total_effective_rate': r['totals']['effective_rate'],
            'take_home': r['totals']['take_home'],
        }
        # State fields
        if r['state'] is not None and 'error' not in r['state']:
            row['state_tax'] = r['state']['tax']
            row['state_effective_rate'] = r['state']['effective_rate']
            row['state_marginal_rate'] = r['state']['marginal_rate']
        else:
            row['state_tax'] = ''
            row['state_effective_rate'] = ''
            row['state_marginal_rate'] = ''
        # City fields
        if r['city'] is not None and 'error' not in r['city']:
            row['city_tax'] = r['city']['tax']
            row['city_effective_rate'] = r['city']['effective_rate']
            row['city_marginal_rate'] = r['city']['marginal_rate']
        else:
            row['city_tax'] = ''
            row['city_effective_rate'] = ''
            row['city_marginal_rate'] = ''
        writer.writerow(row)
    return buf.getvalue().rstrip('\n')


def main():
    """Main function to parse arguments and calculate tax."""
    parser = argparse.ArgumentParser(description="Calculate federal income tax.")
    parser.add_argument('income', type=float, help="Your annual income.")
    parser.add_argument('--year', '-y', type=int, default=datetime.now().year,
                        help="The tax year (default: current year).")
    parser.add_argument('--status', type=str, default='single',
                        choices=['single', 'married_filing_jointly', 'married_filing_separately', 'head_of_household'],
                        help="Your filing status (default: single).")
    parser.add_argument('--state', action='append', default=None,
                        help="State to compute taxes for (repeatable).")
    parser.add_argument('--city', action='append', default=None,
                        help="City to compute taxes for (repeatable).")
    parser.add_argument('--format', '-f', choices=['text', 'csv', 'json'], default='text',
                        help="Output format (default: text).")
    args = parser.parse_args()

    combos = build_location_combos(args.state, args.city)

    # Validate federal data is available before proceeding
    try:
        get_federal_tax_data(args.year)
        get_federal_fica_brackets(args.year)
    except TaxDataNotFoundError as e:
        print(f"Fatal: {e}", file=sys.stderr)
        sys.exit(1)

    results = []
    for state, city in combos:
        results.append(compute_tax_summary(args.income, args.year, args.status, state, city))

    formatter = {'text': format_text, 'json': format_json, 'csv': format_csv}[args.format]
    print(formatter(results))

if __name__ == "__main__":
    main() 
