import csv
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

base = Path('/home/yyr/hypatia/work-space/visualization')
user_csv = base / 'user_distribution.csv'
gs_basic = base / 'ground_stations.basic.txt'
out_txt = base / 'user_distribution_with_latlon.txt'
out_unmatched = base / 'user_distribution_with_latlon_unmatched.txt'
cache_csv = base / 'user_distribution_geocode_cache.csv'

def norm(s: str) -> str:
    s = s.strip().lower()
    s = s.replace('’', "'")
    s = re.sub(r'\s+', ' ', s)
    return s


def load_cache(path: Path):
    cache = {}
    if not path.exists():
        return cache
    with path.open('r', encoding='utf-8', newline='') as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) < 3:
                continue
            key = norm(row[0])
            cache[key] = (row[1], row[2])
    return cache


def save_cache(path: Path, cache: dict):
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['city', 'latitude', 'longitude'])
        for city_key in sorted(cache.keys()):
            lat, lon = cache[city_key]
            writer.writerow([city_key, lat, lon])


def geocode_city(query: str):
    params = urllib.parse.urlencode({
        'q': query,
        'format': 'jsonv2',
        'limit': 1,
        'accept-language': 'en',
    })
    url = f'https://nominatim.openstreetmap.org/search?{params}'
    req = urllib.request.Request(url, headers={'User-Agent': 'hypatia-user-distribution-geocoder/1.0'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode('utf-8'))
    if not payload:
        return None
    return payload[0].get('lat'), payload[0].get('lon')

# Build city -> (lat, lon) map from ground stations
coord = {}
with gs_basic.open('r', encoding='utf-8', newline='') as f:
    reader = csv.reader(f)
    for row in reader:
        if len(row) < 4:
            continue
        name = row[1].strip()
        lat = row[2].strip()
        lon = row[3].strip()
        city = name.split(';')[0].strip()
        if city:
            coord.setdefault(norm(city), (lat, lon))

# handle frequent alias/typo in user file
aliases = {
    norm('Colombus'): norm('Columbus'),
    norm('Longyearben'): norm('Longyearbyen'),
    norm('Washington D.C.'): norm('Washington'),
    norm('New York City'): norm('New York'),
}

geocode_query_overrides = {
    norm('Longyearben'): 'Longyearbyen, Svalbard',
    norm('Longyearbyen'): 'Longyearbyen, Svalbard, Norway',
    norm('Minnesota'): 'Saint Paul, Minnesota, USA',
    norm('Rome'): 'Rome, Italy',
    norm('Mumbai'): 'Mumbai, India',
    norm('Washington D.C.'): 'Washington, District of Columbia, USA',
    norm('Brasilia'): 'Brasilia, Brazil',
    norm('Christchurch'): 'Christchurch, New Zealand',
    norm('Majuro'): 'Majuro, Marshall Islands',
    norm('Avarua District'): 'Avarua, Cook Islands',
    norm('Mariehamn'): 'Mariehamn, Aland Islands, Finland',
    norm('Yaren'): 'Yaren, Nauru',
    norm('Tripoli'): 'Tripoli, Libya',
    norm('Johannesburg'): 'Johannesburg, South Africa',
    norm('Denver'): 'Denver, Colorado, USA',
    norm('Wilmington'): 'Wilmington, Delaware, USA',
}

fixed_coordinates = {
    norm('Majuro'): ('7.089700', '171.380300'),
    norm('Yaren'): ('-0.547700', '166.920900'),
    norm('Wilmington'): ('39.744700', '-75.548400'),
}

cache = load_cache(cache_csv)

rows_out = []
unmatched = []

with user_csv.open('r', encoding='utf-8', newline='') as f:
    reader = csv.reader(f)
    header = next(reader, None)
    for row in reader:
        if not row:
            continue
        city_raw = row[0].strip().strip('"') if len(row) > 0 else ''
        users_raw = row[1].strip().strip('"') if len(row) > 1 else ''
        users_raw = users_raw.replace(',', '')
        key = norm(city_raw)
        key = aliases.get(key, key)
        if key in coord:
            lat, lon = coord[key]
            rows_out.append((city_raw, users_raw, lat, lon))
        elif key in fixed_coordinates:
            lat, lon = fixed_coordinates[key]
            rows_out.append((city_raw, users_raw, lat, lon))
            cache[key] = (lat, lon)
            coord[key] = (lat, lon)
        elif key in cache:
            lat, lon = cache[key]
            rows_out.append((city_raw, users_raw, lat, lon))
        else:
            query = geocode_query_overrides.get(key, city_raw)
            lat = ''
            lon = ''
            try:
                result = geocode_city(query)
                if result is not None:
                    lat_raw, lon_raw = result
                    lat = f'{float(lat_raw):.6f}'
                    lon = f'{float(lon_raw):.6f}'
                    cache[key] = (lat, lon)
                    coord[key] = (lat, lon)
            except Exception:
                pass
            time.sleep(1.0)
            rows_out.append((city_raw, users_raw, lat, lon))
            if lat == '' or lon == '':
                unmatched.append(city_raw)

with out_txt.open('w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['city', 'users', 'latitude', 'longitude'])
    writer.writerows(rows_out)

with out_unmatched.open('w', encoding='utf-8') as f:
    for city in unmatched:
        f.write(city + '\n')

save_cache(cache_csv, cache)

print(f'wrote: {out_txt}')
print(f'matched: {len(rows_out)}')
print(f'unmatched: {len(unmatched)}')
print(f'unmatched list: {out_unmatched}')
