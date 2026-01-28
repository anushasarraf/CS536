#!/usr/bin/env python3

import subprocess
import re
import requests
import math
import matplotlib.pyplot as plt
import os

# ===============================
# CONFIG
# ===============================

PING_COUNT = 10
PING_INTERVAL = 0.2 # time between two consecutive pings
DEBUG = False

os.makedirs("plots", exist_ok=True)

def load_ips(filename="ips.txt"):
    with open(filename, "r") as f:
        return [line.strip() for line in f if line.strip()]

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
            text=True,
            timeout=20
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

def get_my_public_ip():
    r = requests.get("https://ipinfo.io/ip", timeout=5)
    return r.text.strip()

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
# PLOT
# ===============================

def save_scatter(x, y, xlabel, ylabel, title, filename):
    plt.figure()
    plt.scatter(x, y)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.grid(True)
    plt.savefig(filename)
    plt.close()


# ===============================
# MAIN
# ===============================

def main():
    IP_LIST = load_ips()

    print("Determining your own location...")
    my_ip = get_my_public_ip() 
    my_lat, my_lon = get_location(my_ip)

    if DEBUG:
        print("MY IP:", my_ip)
        print(f"My lat and lon: {my_lat}, {my_lon}")

    if my_lat is None:
        print("Failed to get your own location.")
        return

    # add our IP address to the IP list
    if my_ip:
        IP_LIST = [my_ip] + IP_LIST

    results = []

    for ip in IP_LIST:
        print(f"\nProcessing {ip}")

        min_rtt, avg_rtt, max_rtt = ping_ip(ip)
        if ip == my_ip:
            lat, lon = my_lat, my_lon
        else:
            lat, lon = get_location(ip)
            
        if DEBUG:
            print(f"Min RTT: {min_rtt}, Avg RTT: {avg_rtt}, Max RTT: {max_rtt}")
            print(f"Lat: {lat}, Lon: {lon}")

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
    
    min_rtts = [r["min_rtt"] for r in results]
    avg_rtts = [r["avg_rtt"] for r in results]
    max_rtts = [r["max_rtt"] for r in results]

    save_scatter(
        distances, min_rtts,
        "Geographical Distance (km)", "Min RTT (ms)",
        "Distance vs Minimum RTT",
        "plots/distance_vs_min_rtt.pdf"
    )

    save_scatter(
        distances, avg_rtts,
        "Geographical Distance (km)", "Average RTT (ms)",
        "Distance vs Average RTT",
        "plots/distance_vs_avg_rtt.pdf"
    )

    save_scatter(
        distances, max_rtts,
        "Geographical Distance (km)", "Max RTT (ms)",
        "Distance vs Maximum RTT",
        "plots/distance_vs_max_rtt.pdf"
    )

if __name__ == "__main__":
    main()
