import csv
import json
from datetime import datetime

from custom_encoder import CustomEncoder, FlatRow


def load_oasdi_limits():
    """
    Loads the OASDI taxable earnings limits from a CSV file.

    This function reads 'transform/fica_oasdi_limit.csv', parses year ranges,
    and returns a dictionary mapping each year to its OASDI limit.
    """
    limits_csv_path = 'transform/fica_oasdi_limit.csv'
    oasdi_limits = {}

    with open(limits_csv_path, mode='r', encoding='utf-8') as csvfile:
        csv_reader = csv.reader(csvfile)
        header = next(csv_reader)  # Skip header

        for row in csv_reader:
            year_str, limit_str = row
            limit = int(limit_str)

            if '–' in year_str:
                start_year, end_year = map(int, year_str.split('–'))
                for year in range(start_year, end_year + 1):
                    oasdi_limits[year] = limit
            elif '-' in year_str:
                start_year, end_year = map(int, year_str.split('-'))
                for year in range(start_year, end_year + 1):
                    oasdi_limits[year] = limit
            else:
                try:
                    year = int(year_str)
                    oasdi_limits[year] = limit
                except ValueError:
                    print(f"Could not parse year from limit row: {row}")
    return oasdi_limits


def convert_fica_csv_to_json():
    """
    Converts FICA rates from a CSV file to a JSON file.

    The script reads from 'transform/fica_rates.csv', processes year ranges
    and special values, and writes the structured data to
    'data/federal/fica_rates.json'.
    """
    csv_file_path = 'transform/fica_rates.csv'
    json_file_path = 'data/federal/fica_rates.json'
    
    fica_data = {}
    oasdi_limits = load_oasdi_limits()


    with open(csv_file_path, mode='r', encoding='utf-8') as csvfile:
        csv_reader = csv.reader(csvfile)
        header = next(csv_reader)  # Skip header row

        for row in csv_reader:
            year_str, oasdi_rate_str, hi_rate_str = row[0], row[1], row[2]

            # Parse rates, handling '--' for missing values
            oasdi_rate = float(oasdi_rate_str) if oasdi_rate_str != '--' else 0.0
            hi_rate = float(hi_rate_str) if hi_rate_str != '--' else 0.0
            
            # Process year column for ranges and single years
            def process_year(year, oasdi_rate, hi_rate):
                """Helper function to format the data for a given year."""
                limit = oasdi_limits.get(year)
                if limit is not None:
                    fica_data[str(year)] = {
                        "OASDI": [[0, oasdi_rate], [limit, 0]],
                        "HI": [[0, hi_rate]]
                    }
                else:
                    # Handle years where there is no limit data
                    fica_data[str(year)] = {
                        "OASDI": [[0, oasdi_rate]],
                        "HI": [[0, hi_rate]]
                    }

            if '–' in year_str:  # Year range e.g., 1937–1949
                start_year, end_year = map(int, year_str.split('–'))
                for year in range(start_year, end_year + 1):
                    process_year(year, oasdi_rate, hi_rate)
            elif 'onward' in year_str:  # e.g., 1990 onward
                start_year = int(year_str.split(' ')[0])
                current_year = datetime.now().year
                for year in range(start_year, current_year + 1):
                    process_year(year, oasdi_rate, hi_rate)
            else:
                try:
                    year = int(year_str)
                    process_year(year, oasdi_rate, hi_rate)
                except ValueError:
                    print(f"Could not parse year from row: {row}")

    for year, year_data in fica_data.items():
        for key, value in year_data.items():
            if len(value) > 0:
                year_data[key] = FlatRow(value)
    # sort the keys in reverse order
    fica_data = dict(sorted(fica_data.items(), key=lambda item: int(item[0]), reverse=True))

    with open(json_file_path, 'w', encoding='utf-8') as jsonfile:
        json.dump(fica_data, jsonfile, indent=4, cls=CustomEncoder)

    print(f"Successfully converted {csv_file_path} to {json_file_path}")

if __name__ == '__main__':
    convert_fica_csv_to_json() 