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

def get_tax_brackets(year, status):
    tax_data = load_json('data/federal/tax_brackets.json')
    try:
        return tax_data[str(year)][status]
    except KeyError:
        filing_statuses = list(tax_data[str(year)].keys())
        raise KeyError(f"Invalid filing status '{status}' for year {year}. Available statuses: {', '.join(filing_statuses)}")

def get_deduction(year, status):
    standard_deductions = load_json('data/federal/standard_deductions.json')
    try:
        return standard_deductions[str(year)][status]
    except KeyError:
        filing_statuses = list(standard_deductions[str(year)].keys())
        raise KeyError(f"Invalid filing status '{status}' for year {year}. Available statuses: {', '.join(filing_statuses)}")


def _tax_using_brackets(income, brackets):
    tax = 0.0
    marginal_tax_rate = 0.0
    for i in range(len(brackets)):
        bracket_start, rate = brackets[i]
        next_bracket_start, next_rate = brackets[i+1] if i+1 < len(brackets) else (None, None)

        if next_bracket_start is not None and income > float(next_bracket_start):
            owed = (float(next_bracket_start) - float(bracket_start)) * float(rate)
            marginal_tax_rate = float(rate)
        else:
            owed = (income - float(bracket_start)) * float(rate)

        tax += owed 

        if next_bracket_start is None or income < float(next_bracket_start):
            break

    return {
        'tax_amount': tax,
        'marginal_tax_rate': marginal_tax_rate,
    }

def calculate_federal_tax(income, year, status, deduction_override: int=None):
    """Calculates the federal income tax."""
    deduction = get_deduction(year, status) if deduction_override is None else deduction_override
    brackets = get_tax_brackets(year, status)

    # federal income tax
    federal_tax = _tax_using_brackets(income - deduction, brackets)

    return {
        'federal_tax': federal_tax,
        'federal_tax_rate': federal_tax['tax_amount'] / income,
        'federal_marginal_tax_rate': federal_tax['marginal_tax_rate'],
        'taxable_income': income - deduction,
        'deduction': deduction,
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
        result = calculate_federal_tax(args.income, args.year, args.status)
        print(f"For an income of ${args.income:,.2f} in {args.year} with '{args.status}' filing status:")
        print(f"Federal tax owed: ${result['federal_tax']['tax_amount']:,.2f}")
        print(f"Tax rate: {result['federal_tax_rate']:.2%}")
        print(f"Taxable income: ${result['taxable_income']:,.2f}")
        print(f"Deduction: ${result['deduction']:,.2f}")
    except KeyError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main() 