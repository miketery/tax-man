import csv
import json
from pathlib import Path


def convert_currency_to_int(currency_str: str) -> int:
    """Converts a currency string like '$1,234' to an integer 1234."""
    return int(currency_str.strip().replace('$', '').replace(',', ''))


def main():
    """
    Reads federal standard deduction data from a CSV file, transforms it,
    and saves it as a JSON file.
    """
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent
    csv_file_path = project_root / 'transform' / 'federal_deductions.csv'
    output_dir = project_root / 'data' / 'federal'
    json_file_path = output_dir / 'standard_deductions.json'

    output_dir.mkdir(parents=True, exist_ok=True)

    deductions_by_year = {}

    with open(csv_file_path, mode='r', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        for row in reader:
            try:
                year = int(row['year'])
                deductions_by_year[year] = {
                    key: convert_currency_to_int(value)
                    for key, value in row.items()
                    if key != 'year'
                }
            except (ValueError, TypeError) as e:
                print(f"Skipping row {reader.line_num} due to data error: {e}")
                continue

    # Sort the dictionary by year (keys) in descending order for the JSON output
    sorted_deductions = dict(sorted(deductions_by_year.items(), key=lambda item: item[0], reverse=True))

    with open(json_file_path, mode='w', encoding='utf-8') as outfile:
        json.dump(sorted_deductions, outfile, indent=2)

    print(f"Successfully converted {csv_file_path} to {json_file_path}")


if __name__ == "__main__":
    main()
