import argparse
import json
from datetime import datetime

def load_json(file_path):
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: {file_path} not found.")
        return

def get_federal_tax_brackets(year, status):
    tax_data = load_json('data/federal/tax_brackets.json')
    try:
        return tax_data[str(year)][status]
    except KeyError:
        filing_statuses = list(tax_data[str(year)].keys())
        raise KeyError(f"Invalid filing status '{status}' for year {year}. Available statuses: {', '.join(filing_statuses)}")

def get_federal_standard_deduction(year, status):
    standard_deductions = load_json('data/federal/standard_deductions.json')
    try:
        return standard_deductions[str(year)][status]
    except KeyError:
        filing_statuses = list(standard_deductions[str(year)].keys())
        raise KeyError(f"Invalid filing status '{status}' for year {year}. Available statuses: {', '.join(filing_statuses)}")

def get_federal_fica_brackets(year):
    fica_data = load_json('data/federal/fica_rates.json')
    return fica_data[str(year)]


def _tax_using_brackets(income, brackets):
    tax = 0.0
    marginal_tax_rate = 0.0
    for i in range(len(brackets)):
        bracket_start, rate = brackets[i]
        next_bracket_start, next_rate = brackets[i+1] if i+1 < len(brackets) else (None, None)

        if next_bracket_start is not None and income > float(next_bracket_start):
            owed = (float(next_bracket_start) - float(bracket_start)) * float(rate) / 100.0
            marginal_tax_rate = float(rate)
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
    deduction = get_federal_standard_deduction(year, status) if deduction_override is None else deduction_override
    federal_brackets = get_federal_tax_brackets(year, status)

    federal_tax = _tax_using_brackets(income - deduction, federal_brackets)

    return {
        'federal_tax': federal_tax,
        'federal_tax_rate': federal_tax['tax_amount'] / income,
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
        'total_fica_tax_rate': (oasdi_tax['tax_amount'] + medicare_tax['tax_amount']) / income,
        'marginal_fica_tax_rate': max(oasdi_tax['marginal_tax_rate'], medicare_tax['marginal_tax_rate']),
    }

def main():
    """Main function to parse arguments and calculate tax."""
    parser = argparse.ArgumentParser(description="Calculate federal income tax.")
    parser.add_argument('income', type=float, help="Your annual income.")
    parser.add_argument('--year', '-y', type=int, default=datetime.now().year,
                        help="The tax year (default: current year).")
    parser.add_argument('--status', type=str, default='single',
                        choices=['single', 'married_filing_jointly', 'married_filing_separately', 'head_of_household'],
                        help="Your filing status (default: single).")

    args = parser.parse_args()


    try:
        federal_result = calculate_federal_tax(args.income, args.year, args.status)
        fica_result = calculate_federal_fica(args.income, args.year)

        print(f"For an income of ${args.income:,.2f} in {args.year} with '{args.status}' filing status:")
        print(f"Federal tax owed: ${federal_result['federal_tax']['tax_amount']:,.2f}")
        print(f"FICA tax owed: ${fica_result['total_fica_tax']:,.2f}")
        print(f"Total tax owed: ${federal_result['federal_tax']['tax_amount'] + fica_result['total_fica_tax']:,.2f}")

        print(f"--------------------------------")
        print(f"Federal tax rate: {federal_result['federal_tax_rate']:.2%}")
        print(f"FICA tax rate: {fica_result['total_fica_tax_rate']:.2%}")
        print(f"Total tax rate: {(federal_result['federal_tax']['tax_amount'] + fica_result['total_fica_tax']) / args.income:.2%}")

        print(f"--------------------------------")
        print(f"Federal taxable income: ${federal_result['taxable_income']:,.2f}")
        print(f"Federal deduction: ${federal_result['deduction']:,.2f}")
    except KeyError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main() 