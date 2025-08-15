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
    federal_data = get_federal_tax_data(year)
    if 'deductions' in federal_data:
        deduction = federal_data['deductions'][status] if deduction_override is None else deduction_override
    else:
        deduction = 0 if deduction_override is None else deduction_override
    tax_brackets = federal_data['brackets'][status]
    federal_tax = _tax_using_brackets(income - deduction, tax_brackets)

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

def main():
    """Main function to parse arguments and calculate tax."""
    parser = argparse.ArgumentParser(description="Calculate federal income tax.")
    parser.add_argument('income', type=float, help="Your annual income.")
    parser.add_argument('--year', '-y', type=int, default=datetime.now().year,
                        help="The tax year (default: current year).")
    parser.add_argument('--status', type=str, default='single',
                        choices=['single', 'married_filing_jointly', 'married_filing_separately', 'head_of_household'],
                        help="Your filing status (default: single).")
    parser.add_argument('--state', type=str, default='new-york',
                        help="The state you live in (default: new-york).")
    parser.add_argument('--city', type=str, default='new-york-city',
                        help="The city you live in (default: new-york-city).")
    args = parser.parse_args()


    # try:
    federal_result = calculate_federal_tax(args.income, args.year, args.status)
    fica_result = calculate_federal_fica(args.income, args.year)

    total_federal_tax = federal_result['federal_tax']['tax_amount'] + fica_result['total_fica_tax']

    state_result = calculate_state_tax(args.income, args.year, args.state, args.status)
    city_result = calculate_city_tax(args.income, args.year, args.city, args.status)
    
    total_tax = total_federal_tax + state_result['tax_amount'] + city_result['tax_amount']
    total_tax_rate = total_tax / args.income

    print(f"For an income of ${args.income:,.2f} in {args.year} with '{args.status}' filing status:")
    print(f"Federal tax owed: ${federal_result['federal_tax']['tax_amount']:,.2f}")
    print(f"FICA tax owed: ${fica_result['total_fica_tax']:,.2f}")
    print(f"Total tax owed: ${total_federal_tax:,.2f}")

    print(f"--------------------------------")
    print(f"Federal tax rate: {federal_result['federal_tax_rate']:.2%}")
    print(f"FICA tax rate: {fica_result['total_fica_tax_rate']:.2%}")
    print(f"Total tax rate: {(federal_result['federal_tax']['tax_amount'] + fica_result['total_fica_tax']) / args.income:.2%}")

    print(f"--------------------------------")
    print(f"Federal taxable income: ${federal_result['taxable_income']:,.2f}")
    print(f"Federal deduction: ${federal_result['deduction']:,.2f}")

    print(f"--------------------------------")
    print(f"State tax owed: ${state_result['tax_amount']:,.2f}")
    print(f"City tax owed: ${city_result['tax_amount']:,.2f}")
    print(f"Total tax owed: ${state_result['tax_amount'] + city_result['tax_amount']:,.2f}")

    print(f"--------------------------------")
    print(f"State tax rate: {state_result['tax_amount'] / args.income:.2%}")
    print(f"City tax rate: {city_result['tax_amount'] / args.income:.2%}")
    print(f"Total tax rate: {(state_result['tax_amount'] + city_result['tax_amount']) / args.income:.2%}")

    print(f"--------------------------------")
    print(f"Total Tax: ${total_tax:,.2f}")
    print(f"Total Tax Rate: {total_tax_rate:.2%}")

    # except KeyError as e:
    #     print(f"Error: {e}")
    # except Exception as e:
    #     print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main() 