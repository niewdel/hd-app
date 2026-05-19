"""Server-side authoritative pricing defaults for the proposal/job-costing engine.

These were previously hardcoded as JS literals inside index.html, which meant
anyone with network access could view-source the login page and read every
material cost, crew daily rate, productivity figure, and markup default.

They now live here, and are injected into the SPA at render time via a
placeholder replacement in `app.py` (`render_index`). Only authenticated
sessions ever receive them, because only authenticated sessions are served
the rendered SPA.
"""

# Material unit costs in USD ($/<unit>).
MAT = {
    'ABC': 30, '#57 Stone': 35,
    'S9.5B': 100, 'S9.5C': 90, 'I19.0C': 90, 'B25.0C': 90,
    'Concrete': 200,
    'Tack Coat': 5, 'Paving Fabric': 2,
    'Rip Rap': 50, 'Gravel': 28,
    'Select Fill': 12, 'Structural Fill': 15, 'Topsoil': 25,
    'RCP Pipe': 35, 'HDPE Pipe': 22, 'Precast Structure': 2500,
    'PVC Pipe': 14, 'DIP Pipe': 30, 'Fire Hydrant': 3500, 'Gate Valve': 800,
    'Silt Fence': 1.50, 'Erosion Blanket': 1.50, 'Seed Mix': 1500,
    'Traffic Paint': 0.15, 'Thermoplastic': 0.80,
    'Sign Post': 200, 'Bollard': 150, 'Wheel Stop': 50,
    'Sod': 2, 'Mulch': 35, 'Plant Material': 50, 'Fence Material': 15,
}

# Unit of measure per material.
MAT_UNIT = {
    'ABC': 'TON', '#57 Stone': 'TON',
    'S9.5B': 'TON', 'S9.5C': 'TON', 'I19.0C': 'TON', 'B25.0C': 'TON',
    'Concrete': 'CY',
    'Tack Coat': 'GAL', 'Paving Fabric': 'SY',
    'Rip Rap': 'TON', 'Gravel': 'TON',
    'Select Fill': 'CY', 'Structural Fill': 'CY', 'Topsoil': 'CY',
    'RCP Pipe': 'LF', 'HDPE Pipe': 'LF', 'Precast Structure': 'EA',
    'PVC Pipe': 'LF', 'DIP Pipe': 'LF', 'Fire Hydrant': 'EA', 'Gate Valve': 'EA',
    'Silt Fence': 'LF', 'Erosion Blanket': 'SY', 'Seed Mix': 'AC',
    'Traffic Paint': 'LF', 'Thermoplastic': 'LF',
    'Sign Post': 'EA', 'Bollard': 'EA', 'Wheel Stop': 'EA',
    'Sod': 'SY', 'Mulch': 'CY', 'Plant Material': 'EA', 'Fence Material': 'LF',
}

# Trade/category badge key per material.
MAT_TRADE = {
    'ABC': 'b-stone', '#57 Stone': 'b-stone',
    'S9.5B': 'b-asphalt', 'S9.5C': 'b-asphalt', 'I19.0C': 'b-asphalt', 'B25.0C': 'b-asphalt',
    'Concrete': 'b-general',
    'Tack Coat': 'b-asphalt', 'Paving Fabric': 'b-asphalt',
    'Rip Rap': 'b-stone', 'Gravel': 'b-stone',
    'Select Fill': 'b-grading', 'Structural Fill': 'b-grading', 'Topsoil': 'b-grading',
    'RCP Pipe': 'b-utility', 'HDPE Pipe': 'b-utility', 'Precast Structure': 'b-utility',
    'PVC Pipe': 'b-utility', 'DIP Pipe': 'b-utility',
    'Fire Hydrant': 'b-utility', 'Gate Valve': 'b-utility',
    'Silt Fence': 'b-erosion', 'Erosion Blanket': 'b-erosion', 'Seed Mix': 'b-grading',
    'Traffic Paint': 'b-striping', 'Thermoplastic': 'b-striping',
    'Sign Post': 'b-striping', 'Bollard': 'b-striping', 'Wheel Stop': 'b-striping',
    'Sod': 'b-grading', 'Mulch': 'b-grading', 'Plant Material': 'b-grading',
    'Fence Material': 'b-general',
}

# Job-costing engine defaults.
JC_CREW_RATE_DEFAULT = 5000          # $/day, fallback when crew lookup fails
JC_PRODUCTIVITY_DEFAULT = 400        # units/day (asphalt-flavored fallback)
TRUCK_RATE_DEFAULT = 100             # $/hr per truck
TRUCK_HOURS_DEFAULT = 8              # hours per truck day
TONS_PER_TRUCK_DEFAULT = 100         # tons hauled per truck per day
MOB_PRICE_DEFAULT = 10000            # $ default mobilization line-item price
MOB_COST_DEFAULT = 5000              # $ default mobilization internal cost

# Crew roster — each crew has a name, trade badge, daily rate, productivity, and unit.
CREWS_DEFAULT = [
    {'id': 1,  'name': 'Asphalt Crew',         'trade': 'b-asphalt',  'daily_rate': 5000, 'productivity': 400,  'prod_unit': 'TON'},
    {'id': 2,  'name': 'Stone Crew',           'trade': 'b-stone',    'daily_rate': 2500, 'productivity': 800,  'prod_unit': 'TON'},
    {'id': 4,  'name': 'Grading Crew',         'trade': 'b-grading',  'daily_rate': 4000, 'productivity': 500,  'prod_unit': 'CY'},
    {'id': 5,  'name': 'Utility Crew',         'trade': 'b-utility',  'daily_rate': 3500, 'productivity': 120,  'prod_unit': 'LF'},
    {'id': 8,  'name': 'Erosion Control Crew', 'trade': 'b-erosion',  'daily_rate': 1800, 'productivity': 2000, 'prod_unit': 'LF'},
    {'id': 9,  'name': 'Striping Crew',        'trade': 'b-striping', 'daily_rate': 2500, 'productivity': 5000, 'prod_unit': 'LF'},
    {'id': 12, 'name': 'Signage Crew',         'trade': 'b-signage',  'daily_rate': 1000, 'productivity': 40,   'prod_unit': 'EA'},
]

# Per-material production rates / densities / default depths used by the takeoff math.
DRATE_DEFAULT = {
    'ABC': 50, '#57 Stone': 50,
    'S9.5B': 150, 'S9.5C': 150, 'I19.0C': 150, 'B25.0C': 150,
    'Concrete': 0,
}
LBS_DEFAULT = {
    'ABC': 150, '#57 Stone': 150,
    'S9.5B': 115, 'S9.5C': 115, 'I19.0C': 115, 'B25.0C': 115,
    'Concrete': 150, 'Rip Rap': 150, 'Gravel': 150,
}
DDEPTH_DEFAULT = {
    'ABC': 0, '#57 Stone': 0,
    'S9.5B': 0, 'S9.5C': 0, 'I19.0C': 0, 'B25.0C': 0,
    'Concrete': 0,
}
DDEPTH_INITIAL = {
    'ABC': 6, '#57 Stone': 3,
    'S9.5B': 1.5, 'S9.5C': 2, 'I19.0C': 2.5, 'B25.0C': 4,
    'Concrete': 4,
}


def serialize():
    """Return a JSON-ready dict of all defaults, keyed by the JS global name
    that consumes them in index.html."""
    return {
        'MAT': MAT,
        'MAT_UNIT': MAT_UNIT,
        'MAT_TRADE': MAT_TRADE,
        'CREWS_DEFAULT': CREWS_DEFAULT,
        'JC_CREW_RATE_DEFAULT': JC_CREW_RATE_DEFAULT,
        'JC_PRODUCTIVITY_DEFAULT': JC_PRODUCTIVITY_DEFAULT,
        'TRUCK_RATE_DEFAULT': TRUCK_RATE_DEFAULT,
        'TRUCK_HOURS_DEFAULT': TRUCK_HOURS_DEFAULT,
        'TONS_PER_TRUCK_DEFAULT': TONS_PER_TRUCK_DEFAULT,
        'MOB_PRICE_DEFAULT': MOB_PRICE_DEFAULT,
        'MOB_COST_DEFAULT': MOB_COST_DEFAULT,
        'DRATE_DEFAULT': DRATE_DEFAULT,
        'LBS_DEFAULT': LBS_DEFAULT,
        'DDEPTH_DEFAULT': DDEPTH_DEFAULT,
        'DDEPTH_INITIAL': DDEPTH_INITIAL,
    }
