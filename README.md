# tax-man

Estimate US federal, FICA, state and city taxes on W-2 wage income, and compare
your tax burden across states and cities.

## Setup

```bash
./setup.sh              # creates .venv with uv and installs requirements
source .venv/bin/activate
```

## Web UI

```bash
streamlit run app.py
```

- **Estimate** – salary, filing status and year in the sidebar; pick a state or
  city (or federal only) to see total tax, effective/marginal rate, take-home
  pay and a line-by-line breakdown.
- **Compare locations** – pick several states and/or cities. Each uses the
  sidebar salary by default; type a salary under a location to override it
  (clear the field to go back to the shared salary). Shows a side-by-side
  table, take-home difference vs the first location, and a stacked chart.

## CLI

```bash
python calculator.py 120000 --status married_filing_jointly --state california
python calculator.py 120000 --city new-york-city   # city implies its state
```

## Data

| Path | Contents |
|------|----------|
| `data/federal/<year>.json` | Federal brackets (1862–2025) and standard deductions |
| `data/federal/fica_rates.json` | Social Security / Medicare rates and wage base |
| `data/state/<slug>/<year>.json` | State income tax (2025) |
| `data/city/<slug>/<year>.json` | City / county income tax (2025), linked to its state |

State and city files share one schema: `deductions` and `brackets`
(`[[threshold, rate_percent], ...]`) per filing status, plus optional
`credits` (flat nonrefundable credits), `payroll_taxes` (employee-side SDI /
paid leave, applied to gross wages), `state_tax_surcharge` (e.g. Yonkers,
percent of state tax), `notes` and `sources`. City files carry a `state` slug.

Federal data is generated from the CSVs in `transform/`:

```bash
python transform/convert_federal_deductions.py && python transform/merge_federal_data.py
```

## Simplifications

Wage income only, standard deduction, no dependents or credits (other than
the flat state credits in the data), no pre-tax contributions, and no
deduction/exemption phase-outs or state "recapture" rules. For married
filing jointly, payroll taxes (FICA, SDI) are computed as if one person earns
the whole salary. See each location's `notes`.

## Tests

```bash
pytest
```
