#!/usr/bin/env python3

import subprocess
import re
import requests
import math
import matplotlib.pyplot as plt

# ===============================
# CONFIG
# ===============================

PING_COUNT = 10

IP_LIST = [
    "160.242.19.254",          # Luanda, AO
    "41.110.39.130",           # Algiers, DZ
    "213.158.175.240",         # Cairo, EG
    "102.214.66.39",           # Accra, GH
    "102.214.66.19",           # Accra, GH
    "212.60.92.134",           # Banjul, GM
    "105.235.237.2",           # Bata, GQ
    "speed.mymanga.pro",       # Nairobi, KE
    "speedtestfl.telecom.mu",  # Floreal, MU
    "speedtest.telecom.mu",    # Port Louis, MU
    "41.226.22.119",           # Tunis, TN
    "41.210.185.162",          # Kampala, UG
    "169.150.238.161",         # Johannesburg, ZA
    "69.48.239.124",           # Johannesburg, ZA (FortiSASE)
    "86.96.154.106",           # Dubai, AE
    "23.249.55.42",            # Dubai, AE (FortiSASE)
    "69.48.238.200",           # Dubai, AE (FortiSASE)
    "84.17.57.129",            # Hong Kong, HK
    "23.249.58.14",            # Hong Kong, HK (FortiSASE)
    "speedtest.hkg12.hk.leaseweb.net",  # Hong Kong, HK
    "iperf.scbd.net.id",       # Curug, ID
    "103.185.255.183",         # Jakarta, ID
    "speed.netfiber.net.il",   # Jerusalem, IL
    "speed.rimon.net.il",      # Jerusalem, IL
    "169.150.202.193"          # (Asia, provider unspecified)
]


# ===============================
# PING FUNCTION
# ===============================

def ping_ip(ip):
    """
    Returns (min_rtt, avg_rtt, max_rtt) in ms
    """
    try:
        result = subprocess.run(
            ["ping", "-c", str(PING_COUNT), ip],
            capture_output=True,
            text=True
        )

        output = result.stdout
        match = re.search(r"min/avg/max.* = ([\d.]+)/([\d.]+)/([\d.]+)", output)

        if match:
            return tuple(map(float, match.groups()))
        else:
            return None, None, None

    except Exception as e:
        print(f"Ping failed for {ip}: {e}")
        return None, None, None

# ===============================
# GEOLOCATION FUNCTION
# ===============================

def get_location(ip):
    """
    Returns (latitude, longitude)
    """
    try:
        r = requests.get(f"https://ipinfo.io/{ip}/json", timeout=5)
        data = r.json()

        if "loc" in data:
            lat, lon = map(float, data["loc"].split(","))
            return lat, lon
    except Exception as e:
        print(f"Geo lookup failed for {ip}: {e}")

    return None, None

# ===============================
# HAVERSINE DISTANCE
# ===============================

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))

# ===============================
# MAIN
# ===============================

def main():
    results = []

    print("Determining your own location...")
    my_lat, my_lon = get_location("")

    if my_lat is None:
        print("Failed to get your own location.")
        return

    for ip in IP_LIST:
        print(f"\nProcessing {ip}")

        min_rtt, avg_rtt, max_rtt = ping_ip(ip)
        lat, lon = get_location(ip)

        if None in (min_rtt, avg_rtt, max_rtt, lat, lon):
            print(f"Skipping {ip}")
            continue

        distance = haversine(my_lat, my_lon, lat, lon)

        results.append({
            "ip": ip,
            "min_rtt": min_rtt,
            "avg_rtt": avg_rtt,
            "max_rtt": max_rtt,
            "distance": distance
        })

        print(f"RTT min/avg/max: {min_rtt}/{avg_rtt}/{max_rtt} ms")
        print(f"Distance: {distance:.1f} km")

    # ===============================
    # PLOT
    # ===============================

    distances = [r["distance"] for r in results]
    avg_rtts = [r["avg_rtt"] for r in results]

    plt.scatter(distances, avg_rtts)
    plt.xlabel("Geographical Distance (km)")
    plt.ylabel("Average RTT (ms)")
    plt.title("Distance vs RTT")
    plt.grid(True)
    plt.show()

if __name__ == "__main__":
    main()
