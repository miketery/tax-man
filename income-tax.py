import argparse
import json
from datetime import datetime

def calculate_federal_tax(income, year, status, tax_data):
    """Calculates the federal income tax."""
    try:
        brackets = tax_data[str(year)][status]
    except KeyError:
        filing_statuses = list(tax_data[str(year)].keys())
        raise KeyError(f"Invalid filing status '{status}' for year {year}. Available statuses: {', '.join(filing_statuses)}")

    tax = 0.0

    for i in range(len(brackets)):
        bracket_start, rate = brackets[i]
        next_bracket_start, next_rate = brackets[i+1] if i+1 < len(brackets) else (None, None)

        if next_bracket_start is not None and income > float(next_bracket_start):
            owed = (float(next_bracket_start) - float(bracket_start)) * float(rate)
        else:
            owed = (income - float(bracket_start)) * float(rate)

        print(owed, bracket_start, rate)
        tax += owed 

        if next_bracket_start is None or income < float(next_bracket_start):
            break

    return tax

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
        with open('data/federal/tax_brackets.json', 'r') as f:
            tax_data = json.load(f)
    except FileNotFoundError:
        print("Error: tax_brackets.json not found.")
        return
    except json.JSONDecodeError:
        print("Error: Could not decode tax_brackets.json.")
        return

    try:
        tax_amount = calculate_federal_tax(args.income - 14600, args.year, args.status, tax_data)
        rate = tax_amount / args.income
        print(f"For an income of ${args.income:,.2f} in {args.year} with '{args.status}' filing status:")
        print(f"Federal tax owed: ${tax_amount:,.2f}")
        print(f"Tax rate: {rate:.2%}")
    except KeyError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main() 