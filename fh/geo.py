"""Geography helpers: a small city table and great-circle distance."""
import math

# name, lat, lon, country
CITY = [
    ("Mumbai", 19.08, 72.88, "IN"), ("Delhi", 28.61, 77.21, "IN"),
    ("Bengaluru", 12.97, 77.59, "IN"), ("London", 51.51, -0.13, "GB"),
    ("New York", 40.71, -74.01, "US"), ("San Francisco", 37.77, -122.42, "US"),
    ("Singapore", 1.35, 103.82, "SG"), ("Dubai", 25.20, 55.27, "AE"),
    ("Sydney", -33.87, 151.21, "AU"), ("Berlin", 52.52, 13.40, "DE"),
    ("Tokyo", 35.68, 139.69, "JP"), ("Sao Paulo", -23.55, -46.63, "BR"),
    ("Lagos", 6.52, 3.38, "NG"), ("Toronto", 43.65, -79.38, "CA"),
]


def hav(a1, o1, a2, o2):
    """Great-circle distance in km."""
    p1, p2 = math.radians(a1), math.radians(a2)
    da, do = p2 - p1, math.radians(o2 - o1)
    h = math.sin(da / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(do / 2) ** 2
    return 12742.0 * math.asin(min(1.0, math.sqrt(h)))
