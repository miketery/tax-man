import json
import os

def merge_tax_data():
    """
    Merges federal tax brackets and standard deductions into a single JSON file.
    """
    # Construct paths relative to the script's location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    brackets_path = os.path.join(project_root, 'data', 'federal', 'tax_brackets.json')
    deductions_path = os.path.join(project_root, 'data', 'federal', 'standard_deductions.json')
    output_path = os.path.join(project_root, 'data', 'federal', 'federal_tax_data.json')

    # Load the tax brackets and standard deductions data
    with open(brackets_path, 'r') as f:
        tax_brackets_data = json.load(f)

    with open(deductions_path, 'r') as f:
        standard_deductions_data = json.load(f)

    # Merge the data
    merged_data = {}
    all_years = set(tax_brackets_data.keys()) | set(standard_deductions_data.keys())

    for year in sorted(all_years, key=int, reverse=True):
        year_data = {}
        if year in tax_brackets_data:
            year_data['brackets'] = tax_brackets_data[year]
        if year in standard_deductions_data:
            year_data['deductions'] = standard_deductions_data[year]
        
        if year_data:
            merged_data[year] = year_data

    for year in merged_data.keys():
        with open(os.path.join(project_root, 'data', 'federal', f'{year}.json'), 'w') as f:
            json.dump(merged_data[year], f, indent=4)

    # Write the merged data to a new file
    # with open(output_path, 'w') as f:
    #     json.dump(merged_data, f, indent=4)

    print(f"Successfully merged data into {output_path}")

if __name__ == '__main__':
    merge_tax_data()
