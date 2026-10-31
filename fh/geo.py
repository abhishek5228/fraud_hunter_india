"""Geography helpers: Indian cities (home markets) plus a few foreign hubs, and great-circle distance."""
import math

# name, lat, lon, country. The first NIN entries are Indian cities where customers live.
CITY = [
    ("Mumbai", 19.08, 72.88, "IN"), ("Delhi", 28.61, 77.21, "IN"), ("Bengaluru", 12.97, 77.59, "IN"),
    ("Hyderabad", 17.39, 78.49, "IN"), ("Chennai", 13.08, 80.27, "IN"), ("Kolkata", 22.57, 88.36, "IN"),
    ("Pune", 18.52, 73.86, "IN"), ("Ahmedabad", 23.02, 72.57, "IN"), ("Jaipur", 26.91, 75.79, "IN"),
    ("Lucknow", 26.85, 80.95, "IN"), ("Patna", 25.59, 85.14, "IN"), ("Chandigarh", 30.73, 76.78, "IN"),
    ("Kochi", 9.93, 76.27, "IN"), ("Indore", 22.72, 75.86, "IN"), ("Guwahati", 26.14, 91.74, "IN"),
    ("Dubai", 25.20, 55.27, "AE"), ("Singapore", 1.35, 103.82, "SG"), ("London", 51.51, -0.13, "GB"),
    ("New York", 40.71, -74.01, "US"),
]
NIN = 15
HOME_W = [7, 8, 7, 5, 5, 5, 4, 3, 2, 2, 2, 1, 1, 2, 1]  # where customers live (rough population weights)


def hav(a1, o1, a2, o2):
    """Great-circle distance in km."""
    p1, p2 = math.radians(a1), math.radians(a2)
    da, do = p2 - p1, math.radians(o2 - o1)
    h = math.sin(da / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(do / 2) ** 2
    return 12742.0 * math.asin(min(1.0, math.sqrt(h)))
