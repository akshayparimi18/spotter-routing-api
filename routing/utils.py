import requests
import math
from django.conf import settings
from routing.models import FuelStation

def haversine(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees).
    Returns distance in miles.
    """
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])

    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a)) 
    r = 3956 # Radius of earth in miles
    return c * r

def get_route_data(start_coords, finish_coords):
    """
    Calls OpenRouteService API to get route geometry and distance.
    start_coords and finish_coords should be tuples of (lat, lon).
    """
    api_key = getattr(settings, 'ORS_API_KEY', 'YOUR_ORS_API_KEY')
    
    url = 'https://api.openrouteservice.org/v2/directions/driving-car/geojson'
    
    headers = {
        'Accept': 'application/json, application/geo+json, application/gpx+xml, img/png; charset=utf-8',
        'Authorization': api_key,
        'Content-Type': 'application/json; charset=utf-8'
    }
    
    body = {
        "coordinates": [
            [start_coords[1], start_coords[0]], # ORS expects [lon, lat]
            [finish_coords[1], finish_coords[0]]
        ]
    }
    
    response = requests.post(url, json=body, headers=headers)
    if response.status_code != 200:
        raise Exception(f"OpenRouteService API Error: {response.status_code} {response.text}")
        
    data = response.json()
    
    distance_meters = data['features'][0]['properties']['summary']['distance']
    total_distance_miles = distance_meters * 0.000621371
    
    coords = data['features'][0]['geometry']['coordinates']
    route_geometry = [[lat, lon] for lon, lat in coords]
    
    return {
        'total_distance_miles': total_distance_miles,
        'route_geometry': route_geometry 
    }

def calculate_optimal_stops(route_geometry, total_distance_miles):
    """
    Strict Pure Python implementation of the Dynamic Tank Greedy Algorithm.
    Correctly models 500-mile max range, 50-gallon tank constraints, and the final trip leg.
    """
    max_range = 500.0
    tank_capacity = 50.0
    mpg = 10.0
    
    # 1. Fetch all geocoded stations into memory (SQLite approach)
    all_stations = list(FuelStation.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True).values(
        'opis_id', 'name', 'address', 'city', 'state', 'retail_price', 'latitude', 'longitude'
    ))
    
    # 2. Pre-calculate route cumulative distances (mile markers)
    route_distances = [0.0]
    for i in range(1, len(route_geometry)):
        dist = haversine(
            route_geometry[i-1][0], route_geometry[i-1][1],
            route_geometry[i][0], route_geometry[i][1]
        )
        route_distances.append(route_distances[-1] + dist)

    # 3. Assign a "mile marker" to each valid station near the route
    stations_on_route = []
    
    # Sub-sample the route to optimize Python memory performance. 
    # Checking every 10th coordinate is sufficiently accurate for a 5-mile buffer search.
    sub_route = list(enumerate(route_geometry))[::10]
    
    for station in all_stations:
        closest_idx = 0
        closest_dist = float('inf')
        
        for i, p in sub_route:
            d = haversine(station['latitude'], station['longitude'], p[0], p[1])
            if d < closest_dist:
                closest_dist = d
                closest_idx = i
                
        # If the station is within ~5 miles of the route, add it to our playable list
        if closest_dist <= 5.0:
            stations_on_route.append({
                'station': station,
                'mile': route_distances[closest_idx]
            })
            
    # Sort strictly by mile marker ascending
    stations_on_route.sort(key=lambda x: x['mile'])
    
    # Filter out stations that require backtracking (mile marker < 0)
    stations_on_route = [s for s in stations_on_route if s['mile'] >= 0]

    # 4. Dynamic Tank Greedy Optimization Algorithm
    current_mile = 0.0
    current_gallons = 0.0 # Vehicle starts empty
    total_cost = 0.0
    stops = []
    
    while current_mile < total_distance_miles:
        # Determine stations reachable from our current position
        reachable_stations = [s for s in stations_on_route if s['mile'] > current_mile and s['mile'] <= current_mile + max_range]
        distance_to_destination = total_distance_miles - current_mile
        
        # If no stations are reachable, check if we can just drive to the destination
        if not reachable_stations and distance_to_destination > max_range:
            raise Exception("No reachable fuel stations found. Route cannot be completed.")
            
        current_price = float('inf')
        if stops:
            current_price = stops[-1]['price']
            
        # SCENARIO A: Find the first reachable station that is CHEAPER than our current station
        cheaper_station = None
        for s in reachable_stations:
            if s['station']['retail_price'] < current_price:
                cheaper_station = s
                break
                
        if cheaper_station:
            distance_to_next = cheaper_station['mile'] - current_mile
            gallons_needed = distance_to_next / mpg
            gallons_to_buy = max(0, gallons_needed - current_gallons)
            
            price_to_use = current_price
            if price_to_use == float('inf'):
                price_to_use = cheaper_station['station']['retail_price']
            
            if gallons_to_buy > 0:
                cost = gallons_to_buy * price_to_use
                total_cost += cost
                if stops:
                    stops[-1]['money_spent'] += cost
                else:
                    # We had to buy fuel at the starting location to reach this first station
                    stops.append({
                        "name": "Starting Location Fill-Up",
                        "location": "Origin",
                        "price": price_to_use,
                        "money_spent": cost
                    })
                
            current_mile = cheaper_station['mile']
            current_gallons = 0.0 # Arrive completely empty
            
            stops.append({
                "name": cheaper_station['station']['name'],
                "location": f"{cheaper_station['station']['address']}, {cheaper_station['station']['city']}, {cheaper_station['station']['state']}",
                "price": cheaper_station['station']['retail_price'],
                "money_spent": 0.0
            })
            continue

        # SCENARIO C: The destination is reachable, and there are NO cheaper stations before it
        if distance_to_destination <= max_range:
            gallons_needed = distance_to_destination / mpg
            gallons_to_buy = max(0, gallons_needed - current_gallons)
            
            price_to_use = current_price
            if price_to_use == float('inf'):
                # Just use an average price of $3.50 if there are no stations at all
                price_to_use = reachable_stations[0]['station']['retail_price'] if reachable_stations else 3.50
                
            if gallons_to_buy > 0:
                cost = gallons_to_buy * price_to_use
                total_cost += cost
                if stops:
                    stops[-1]['money_spent'] += cost
                else:
                    stops.append({
                        "name": "Starting Location Fill-Up",
                        "location": "Origin",
                        "price": price_to_use,
                        "money_spent": cost
                    })
                    
            break
            
        # SCENARIO B: We are at the absolute cheapest station within the 500-mile lookahead, 
        # AND we cannot reach the destination. Fill the tank completely.
        next_cheapest = min(reachable_stations, key=lambda x: x['station']['retail_price'])
        
        gallons_to_buy = tank_capacity - current_gallons
        cost = gallons_to_buy * current_price
        total_cost += cost
        
        if not stops:
             stops.append({
                "name": "Starting Location Fill-Up",
                "location": "Origin",
                "price": next_cheapest['station']['retail_price'], # Adopt the first station's price for the origin
                "money_spent": cost
            })
        else:
            stops[-1]['money_spent'] += cost
        
        distance_to_next = next_cheapest['mile'] - current_mile
        current_mile = next_cheapest['mile']
        current_gallons = tank_capacity - (distance_to_next / mpg)
        
        stops.append({
            "name": next_cheapest['station']['name'],
            "location": f"{next_cheapest['station']['address']}, {next_cheapest['station']['city']}, {next_cheapest['station']['state']}",
            "price": next_cheapest['station']['retail_price'],
            "money_spent": 0.0
        })

    return {
        "route_map": route_geometry,
        "total_distance_miles": round(total_distance_miles, 2),
        "total_cost": round(total_cost, 2),
        "fuel_stops": [s for s in stops if s['money_spent'] > 0]
    }
