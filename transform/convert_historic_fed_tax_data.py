import csv
import json

from custom_encoder import CustomEncoder, FlatRow

def clean_value(value):
    if isinstance(value, str):
        return value.replace('$', '').replace(',', '').replace('%', '').strip()
    return value

def parse_row(row, headers):
    filing_statuses = {
        "married_filing_jointly": ("Married Filing Jointly (Rates/Brackets)", 2),
        "married_filing_separately": ("Married Filing Separately (Rates/Brackets)", 5),
        "single": ("Single Filer (Rates/Brackets)", 8),
        "head_of_household": ("Head of Household (Rates/Brackets)", 11)
    }
    
    parsed_data = {}
    for key, (header, start_index) in filing_statuses.items():
        rate = clean_value(row[start_index-1])
        amount = clean_value(row[start_index+1])
        if rate and amount:
            if key not in parsed_data:
                parsed_data[key] = []
            parsed_data[key].append([float(amount), round(float(rate), 2)])
    return parsed_data

def convert_csv_to_json(csv_path, json_path):
    data = {}
    with open(csv_path, 'r') as csvfile:
        reader = csv.reader(csvfile)
        headers = next(reader)
        
        for row in reader:
            if not any(row):
                continue

            year = row[0]
            if not year.isdigit():
                continue

            if year not in data:
                data[year] = {}
            
            parsed_row = parse_row(row, headers)
            for key, value in parsed_row.items():
                if key not in data[year]:
                    data[year][key] = []
                data[year][key].extend(value)
        for year, year_data in data.items():
            for key, value in year_data.items():
                if len(value) > 0:
                    year_data[key] = FlatRow(value)

    with open(json_path, 'w') as jsonfile:
        json.dump(data, jsonfile, indent=4, cls=CustomEncoder)

if __name__ == "__main__":
    convert_csv_to_json('transform/historical_federal_1862-2021.csv', 'data/federal/tax_brackets.json') 