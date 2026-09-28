"""
Where each pro franchise played, by the city part of its era name: city,
state/province, and approximate coordinates (for the belt map, the belt's
journey and the states page). Regional names map to the home city.
"""

# name prefix -> (city, state/province, lat, lon)
CITIES = {
    "Akron": ("Akron", "OH", 41.08, -81.52), "Anaheim": ("Anaheim", "CA", 33.84, -117.91),
    "Anderson": ("Anderson", "IN", 40.11, -85.68), "Arizona": ("Phoenix", "AZ", 33.45, -112.07),
    "Atlanta": ("Atlanta", "GA", 33.75, -84.39), "Baltimore": ("Baltimore", "MD", 39.29, -76.61),
    "Boston": ("Boston", "MA", 42.36, -71.06), "Brooklyn": ("Brooklyn", "NY", 40.68, -73.94),
    "Buffalo": ("Buffalo", "NY", 42.89, -78.88), "Calgary": ("Calgary", "AB", 51.05, -114.07),
    "California": ("Anaheim", "CA", 33.84, -117.91), "California Golden Seals": ("Oakland", "CA", 37.80, -122.27),
    "Canton": ("Canton", "OH", 40.80, -81.38), "Capital": ("Landover", "MD", 38.93, -76.89),
    "Carolina": ("Raleigh", "NC", 35.78, -78.64), "Carolina Panthers": ("Charlotte", "NC", 35.23, -80.84),
    "Charlotte": ("Charlotte", "NC", 35.23, -80.84), "Chicago": ("Chicago", "IL", 41.88, -87.63),
    "Cincinnati": ("Cincinnati", "OH", 39.10, -84.51), "Cleveland": ("Cleveland", "OH", 41.50, -81.69),
    "Colorado": ("Denver", "CO", 39.74, -104.99), "Columbus": ("Columbus", "OH", 39.96, -83.00),
    "Dallas": ("Dallas", "TX", 32.78, -96.80), "Dayton": ("Dayton", "OH", 39.76, -84.19),
    "Denver": ("Denver", "CO", 39.74, -104.99), "Detroit": ("Detroit", "MI", 42.33, -83.05),
    "Edmonton": ("Edmonton", "AB", 53.55, -113.49), "Florida": ("Miami", "FL", 25.76, -80.19),
    "Florida Panthers": ("Sunrise", "FL", 26.16, -80.33), "Fort Wayne": ("Fort Wayne", "IN", 41.08, -85.14),
    "Frankford": ("Philadelphia", "PA", 40.02, -75.08), "Golden State": ("San Francisco", "CA", 37.77, -122.42),
    "Green Bay": ("Green Bay", "WI", 44.51, -88.01), "Hamilton": ("Hamilton", "ON", 43.26, -79.87),
    "Hartford": ("Hartford", "CT", 41.76, -72.69), "Houston": ("Houston", "TX", 29.76, -95.37),
    "Indiana": ("Indianapolis", "IN", 39.77, -86.16), "Indianapolis": ("Indianapolis", "IN", 39.77, -86.16),
    "Jacksonville": ("Jacksonville", "FL", 30.33, -81.66), "Kansas City": ("Kansas City", "MO", 39.10, -94.58),
    "Las Vegas": ("Las Vegas", "NV", 36.17, -115.14), "Vegas": ("Las Vegas", "NV", 36.17, -115.14),
    "Los Angeles": ("Los Angeles", "CA", 34.05, -118.24), "Louisville": ("Louisville", "KY", 38.25, -85.76),
    "Memphis": ("Memphis", "TN", 35.15, -90.05), "Miami": ("Miami", "FL", 25.76, -80.19),
    "Milwaukee": ("Milwaukee", "WI", 43.04, -87.91), "Minneapolis": ("Minneapolis", "MN", 44.98, -93.27),
    "Minnesota": ("Minneapolis", "MN", 44.98, -93.27), "Montreal": ("Montreal", "QC", 45.50, -73.57),
    "Montréal": ("Montreal", "QC", 45.50, -73.57), "Nashville": ("Nashville", "TN", 36.16, -86.78),
    "New England": ("Foxborough", "MA", 42.07, -71.25), "New Jersey": ("Newark", "NJ", 40.74, -74.17),
    "New Orleans/Oklahoma City": ("Oklahoma City", "OK", 35.47, -97.52), "New Orleans": ("New Orleans", "LA", 29.95, -90.07),
    "New York": ("New York", "NY", 40.75, -73.99), "Oakland": ("Oakland", "CA", 37.80, -122.27),
    "Oklahoma City": ("Oklahoma City", "OK", 35.47, -97.52), "Orlando": ("Orlando", "FL", 28.54, -81.38),
    "Ottawa": ("Ottawa", "ON", 45.42, -75.70), "Phil-Pitt": ("Philadelphia", "PA", 39.95, -75.17),
    "Philadelphia": ("Philadelphia", "PA", 39.95, -75.17), "Phoenix": ("Phoenix", "AZ", 33.45, -112.07),
    "Pittsburgh": ("Pittsburgh", "PA", 40.44, -80.00), "Portland": ("Portland", "OR", 45.52, -122.68),
    "Portsmouth": ("Portsmouth", "OH", 38.73, -82.998), "Pottsville": ("Pottsville", "PA", 40.69, -76.20),
    "Providence": ("Providence", "RI", 41.82, -71.41), "Quebec": ("Quebec City", "QC", 46.81, -71.21),
    "Rochester": ("Rochester", "NY", 43.16, -77.61), "Sacramento": ("Sacramento", "CA", 38.58, -121.49),
    "San Antonio": ("San Antonio", "TX", 29.42, -98.49), "San Diego": ("San Diego", "CA", 32.72, -117.16),
    "San Francisco": ("San Francisco", "CA", 37.77, -122.42), "San Jose": ("San Jose", "CA", 37.34, -121.89),
    "Seattle": ("Seattle", "WA", 47.61, -122.33), "Sheboygan": ("Sheboygan", "WI", 43.75, -87.71),
    "St. Louis": ("St. Louis", "MO", 38.63, -90.20), "Syracuse": ("Syracuse", "NY", 43.05, -76.15),
    "Tampa Bay": ("Tampa", "FL", 27.95, -82.46), "Tennessee": ("Nashville", "TN", 36.16, -86.78),
    "Texas": ("Arlington", "TX", 32.74, -97.11), "Toronto": ("Toronto", "ON", 43.65, -79.38),
    "Tri-Cities": ("Moline", "IL", 41.51, -90.52), "Troy": ("Troy", "NY", 42.73, -73.69),
    "Utah": ("Salt Lake City", "UT", 40.76, -111.89), "Vancouver": ("Vancouver", "BC", 49.28, -123.12),
    "Washington": ("Washington", "DC", 38.91, -77.04), "Winnipeg": ("Winnipeg", "MB", 49.90, -97.14),
    "Worcester": ("Worcester", "MA", 42.26, -71.80), "Athletics": ("Sacramento", "CA", 38.58, -121.49),
}
STATE_NAMES = {
    "AL": "Alabama", "AZ": "Arizona", "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DC": "Washington, D.C.",
    "FL": "Florida", "GA": "Georgia", "IL": "Illinois", "IN": "Indiana", "KY": "Kentucky", "LA": "Louisiana",
    "MA": "Massachusetts", "MD": "Maryland", "MI": "Michigan", "MN": "Minnesota", "MO": "Missouri", "NC": "North Carolina",
    "NJ": "New Jersey", "NV": "Nevada", "NY": "New York", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "WA": "Washington", "WI": "Wisconsin",
    "AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba", "ON": "Ontario", "QC": "Quebec",
}


def place(full_name):
    """(city, state, lat, lon) for a team's era name, or None."""
    best = None
    for pre, v in CITIES.items():
        if full_name == pre or full_name.startswith(pre + " ") or full_name.startswith(pre + "-"):
            if best is None or len(pre) > len(best[0]):
                best = (pre, v)
    return best[1] if best else None
