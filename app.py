"""Streamlit UI for the tax calculator.

Run with:  streamlit run app.py
"""
import altair as alt
import pandas as pd
import streamlit as st

import calculator as calc

CATEGORY_LABELS = {'federal': 'Federal income', 'fica': 'FICA', 'state': 'State', 'city': 'City / local'}
# Fixed categorical order (validated palette, adjacent pairs): category keeps its color across views.
CATEGORY_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100']

st.set_page_config(page_title='Tax Man', page_icon='💸', layout='wide')


def money(x):
    return f'${x:,.0f}'


def pct(x):
    return f'{x:.2f}%'


# ---------------------------------------------------------------------------
# Location options: states, plus "City (State)" entries that imply their state.
# A location key is "state:<slug>" or "city:<slug>".
# ---------------------------------------------------------------------------

def location_options(year):
    states = calc.available_states(year)
    cities = calc.available_cities(year)
    options = {f'state:{slug}': name for slug, name in states.items()}
    for slug, info in cities.items():
        state_name = states.get(info['state'], info['state'] or '?')
        options[f'city:{slug}'] = f"{info['name']} ({state_name})"
    return dict(sorted(options.items(), key=lambda kv: kv[1]))


def run(income, year, status, location_key):
    if not location_key:
        return calc.calculate(income, year, status)
    kind, slug = location_key.split(':', 1)
    if kind == 'city':
        return calc.calculate(income, year, status, city=slug)
    return calc.calculate(income, year, status, state=slug)


def breakdown_frame(result):
    return pd.DataFrame(
        [
            {
                'Tax': line.name,
                'Type': CATEGORY_LABELS[line.category],
                'Amount': line.amount,
                '% of income': line.amount / result.income * 100 if result.income else 0.0,
                'Marginal rate': line.marginal_rate,
            }
            for line in result.lines
        ]
    )


def stacked_bar(df, y_field, y_title):
    """Horizontal stacked bar of tax by category, one bar per `y_field` value."""
    order = list(CATEGORY_LABELS.values())
    return (
        alt.Chart(df)
        .mark_bar(cornerRadiusEnd=0, stroke='white', strokeWidth=2, height={'band': 0.6})
        .encode(
            y=alt.Y(f'{y_field}:N', title=y_title, sort=None, axis=alt.Axis(labelLimit=300)),
            x=alt.X('Amount:Q', title='Taxes ($)', axis=alt.Axis(format='$,.0f', grid=True)),
            color=alt.Color(
                'Type:N',
                scale=alt.Scale(domain=order, range=CATEGORY_COLORS),
                legend=alt.Legend(title=None, orient='top'),
            ),
            order=alt.Order('order:Q'),
            tooltip=[
                alt.Tooltip(f'{y_field}:N', title=y_title),
                alt.Tooltip('Type:N'),
                alt.Tooltip('Amount:Q', format='$,.0f'),
            ],
        )
        .properties(height=max(120, 70 * df[y_field].nunique()))
    )


def category_frame(result, label):
    totals = result.by_category()
    return [
        {'Location': label, 'Type': CATEGORY_LABELS[c], 'Amount': totals.get(c, 0.0), 'order': i}
        for i, c in enumerate(CATEGORY_LABELS)
        if c in totals
    ]


def location_notes(location_key, year):
    if not location_key:
        return []
    kind, slug = location_key.split(':', 1)
    data = calc.get_city_tax_data(year, slug) if kind == 'city' else calc.get_state_tax_data(year, slug)
    notes = list(data.get('notes', []))
    if kind == 'city' and data.get('state'):
        notes = list(calc.get_state_tax_data(year, data['state']).get('notes', [])) + notes
    return notes


# ---------------------------------------------------------------------------
# Sidebar: shared inputs
# ---------------------------------------------------------------------------

years = calc.federal_years()
# Years that have at least one state file are the useful default range.
with st.sidebar:
    st.header('Your situation')
    income = st.number_input('Annual gross salary ($)', min_value=0, value=100_000, step=5_000, format='%d')
    status = st.selectbox(
        'Filing status', list(calc.FILING_STATUSES), format_func=calc.FILING_STATUSES.get
    )
    year = st.selectbox('Tax year', years, index=0)
    st.caption(
        'Estimates for W-2 wage income using the standard deduction. '
        'Ignores credits, itemized deductions, pre-tax contributions (401k, HSA) and phase-outs.'
    )

options = location_options(year)
if not options:
    st.sidebar.warning(f'No state or city data for {year}; only federal taxes are available.')

st.title('💸 Tax Man')
tab_estimate, tab_compare = st.tabs(['Estimate', 'Compare locations'])

# ---------------------------------------------------------------------------
# Tab 1: single estimate
# ---------------------------------------------------------------------------

with tab_estimate:
    default_key = 'state:new-york' if 'state:new-york' in options else None
    keys = [None] + list(options)
    location = st.selectbox(
        'State or city',
        keys,
        index=keys.index(default_key) if default_key in keys else 0,
        format_func=lambda k: 'Federal only' if k is None else options[k],
    )
    result = run(income, year, status, location)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Total tax', money(result.total))
    c2.metric('Effective rate', pct(result.effective_rate))
    c3.metric('Marginal rate', pct(result.marginal_rate), help='Tax on your next dollar of salary, all taxes combined.')
    c4.metric('Take-home pay', money(result.take_home), help=f'{money(result.take_home / 12)} / month')

    st.subheader('Breakdown')
    df = breakdown_frame(result)
    st.dataframe(
        df,
        hide_index=True,
        width='stretch',
        column_config={
            'Amount': st.column_config.NumberColumn(format='$%,.0f'),
            '% of income': st.column_config.NumberColumn(format='%.2f%%'),
            'Marginal rate': st.column_config.NumberColumn(format='%.2f%%'),
        },
    )

    notes = location_notes(location, year)
    if notes:
        with st.expander('Data notes & simplifications'):
            for n in notes:
                st.markdown(f'- {n}')

# ---------------------------------------------------------------------------
# Tab 2: compare locations
# ---------------------------------------------------------------------------

with tab_compare:
    st.caption(
        f'Pick states or cities to compare. Each uses your salary ({money(income)}) unless you override it.'
    )
    defaults = [k for k in ('state:new-york', 'state:texas', 'city:new-york-city') if k in options]
    selected = st.multiselect(
        'Locations', list(options), default=defaults[:2], format_func=options.get, placeholder='Choose states or cities'
    )

    if not selected:
        st.info('Select at least one location.')
    else:
        # Per-location salary. Blank means "same as base salary", so it follows the sidebar value.
        salaries = {}
        cols = st.columns(min(len(selected), 4))
        for i, key in enumerate(selected):
            with cols[i % len(cols)]:
                override = st.number_input(
                    options[key],
                    min_value=0,
                    value=None,
                    step=5_000,
                    format='%d',
                    placeholder=f'{money(income)} (base)',
                    key=f'salary:{key}',
                    help='Leave blank to use the base salary. Clear it to reset.',
                )
                salaries[key] = income if override is None else override

        results = {key: run(salaries[key], year, status, key) for key in selected}
        baseline_key = selected[0]
        baseline = results[baseline_key]

        # Summary table: one column per location.
        rows = {
            'Salary': lambda r: money(r.income),
            'Federal income tax': lambda r: money(r.by_category().get('federal', 0)),
            'FICA': lambda r: money(r.by_category().get('fica', 0)),
            'State tax': lambda r: money(r.by_category().get('state', 0)),
            'City / local tax': lambda r: money(r.by_category().get('city', 0)),
            'Total tax': lambda r: money(r.total),
            'Effective rate': lambda r: pct(r.effective_rate),
            'Marginal rate': lambda r: pct(r.marginal_rate),
            'Take-home pay': lambda r: money(r.take_home),
            'Take-home / month': lambda r: money(r.take_home / 12),
            f'Take-home vs {options[baseline_key]}': lambda r: (
                '—' if r is baseline else f'{r.take_home - baseline.take_home:+,.0f}'
            ),
        }
        table = pd.DataFrame({options[k]: {label: fn(r) for label, fn in rows.items()} for k, r in results.items()})
        st.dataframe(table, width='stretch', height=35 * (len(table) + 1) + 3)

        best = max(results, key=lambda k: results[k].take_home)
        if len(results) > 1:
            gap = results[best].take_home - min(r.take_home for r in results.values())
            st.success(f'**{options[best]}** leaves you the most take-home pay — {money(gap)} more per year than the lowest.')

        chart_df = pd.DataFrame([row for k, r in results.items() for row in category_frame(r, options[k])])
        st.altair_chart(stacked_bar(chart_df, 'Location', None), width='stretch')

        with st.expander('Line-by-line breakdown'):
            detail = pd.concat(
                [breakdown_frame(r).assign(Location=options[k]) for k, r in results.items()], ignore_index=True
            )
            pivot = detail.pivot_table(index=['Type', 'Tax'], columns='Location', values='Amount', aggfunc='sum', sort=False)
            st.dataframe(pivot[[options[k] for k in selected]].fillna(0).style.format('${:,.0f}'), width='stretch')

        with st.expander('Data notes & simplifications'):
            for k in selected:
                notes = location_notes(k, year)
                if notes:
                    st.markdown(f'**{options[k]}**')
                    for n in notes:
                        st.markdown(f'- {n}')
