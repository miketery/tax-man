import csv
import json

class NoIndent:
    def __init__(self, value):
        self.value = ",".join(value)

class FlatRow:
    def __init__(self, value):
        self.value = json.dumps(value)

class CustomEncoder(json.JSONEncoder):
    def default(self, o):
        # if isinstance(o, NoIndent):
        #     return '["' + '", "'.join(o.value.split(",")) + '"]'
        if isinstance(o, FlatRow):
            x = json.loads(o.value)
            z = [f"{y[0]}, {y[1]}" for y in x]
            return ', '.join(z)
        return super().default(o)

    def iterencode(self, o, _one_shot=False):
        if self.indent is None:
            return super().iterencode(o, _one_shot)

        def _iterencode(o, current_indent):
            if isinstance(o, FlatRow):
                yield o.value
            elif isinstance(o, (list, tuple)):
                if not o:
                    yield '[]'
                    return
                yield '['
                next_indent = current_indent + self.indent
                first = True
                for value in o:
                    if not first:
                        yield ','
                    yield ' ' * next_indent
                    yield from _iterencode(value, next_indent)
                    first = False
                yield' ' * current_indent + ']'
            elif isinstance(o, dict):
                if not o:
                    yield '{}'
                    return
                yield '{'
                next_indent = current_indent + self.indent
                first = True
                for key, value in o.items():
                    if not first:
                        yield ','
                    yield '\n' + ' ' * next_indent
                    yield json.dumps(key) + ': '
                    yield from _iterencode(value, next_indent)
                    first = False
                yield '\n' + ' ' * current_indent + '}'
            else:
                yield json.dumps(o, ensure_ascii=self.ensure_ascii)

        return _iterencode(o, 0)

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
            parsed_data[key].append([str(float(amount)), str(float(rate) / 100)])
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