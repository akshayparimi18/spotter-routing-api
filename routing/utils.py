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
    Greedy algorithm to find the optimal fuel stops.
    """
    max_range = 500.0
    mpg = 10.0
    
    # In-memory fetch of all valid stations to optimize Haversine distance calculations
    all_stations = list(FuelStation.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True).values(
        'opis_id', 'name', 'address', 'city', 'state', 'retail_price', 'latitude', 'longitude'
    ))
    
    current_mile = 0.0
    stops = []
    total_cost = 0.0
    
    # Array of cumulative distances for the route geometry points
    route_distances = [0.0]
    for i in range(1, len(route_geometry)):
        dist = haversine(
            route_geometry[i-1][0], route_geometry[i-1][1],
            route_geometry[i][0], route_geometry[i][1]
        )
        route_distances.append(route_distances[-1] + dist)

    while total_distance_miles - current_mile > max_range:
        target_mile = current_mile + max_range
        
        # Determine the segment of the route we can reach
        current_index = 0
        for i, dist in enumerate(route_distances):
            if dist >= current_mile:
                current_index = i
                break
                
        target_index = 0
        for i, dist in enumerate(route_distances):
            if dist > target_mile:
                break
            target_index = i
            
        current_point = route_geometry[current_index]
        reachable_segment = route_geometry[current_index:target_index+1]
        
        # Bounding box for initial filtering (~5 mile buffer = ~0.07 degrees)
        lats = [p[0] for p in reachable_segment]
        lons = [p[1] for p in reachable_segment]
        min_lat, max_lat = min(lats) - 0.07, max(lats) + 0.07
        min_lon, max_lon = min(lons) - 0.07, max(lons) + 0.07
        
        valid_stations = []
        for station in all_stations:
            # 1. Bounding box check
            if not (min_lat <= station['latitude'] <= max_lat and min_lon <= station['longitude'] <= max_lon):
                continue
                
            # 2. Must be reachable from our current position
            dist_from_current = haversine(current_point[0], current_point[1], station['latitude'], station['longitude'])
            if dist_from_current > max_range:
                continue
                
            # 3. Must be near the reachable route segment (within 5 miles)
            min_dist_to_route = min([haversine(station['latitude'], station['longitude'], p[0], p[1]) for p in reachable_segment])
            
            if min_dist_to_route <= 5.0:
                # Find the closest point on the route to determine our new progress (effective mile)
                closest_idx = 0
                closest_dist = float('inf')
                for i, p in enumerate(reachable_segment):
                    d = haversine(station['latitude'], station['longitude'], p[0], p[1])
                    if d < closest_dist:
                        closest_dist = d
                        closest_idx = i
                
                effective_mile = route_distances[current_index + closest_idx]
                
                # Must make some forward progress (e.g., at least 10 miles)
                if effective_mile > current_mile + 10:
                    valid_stations.append({
                        'station': station,
                        'dist_from_current': dist_from_current,
                        'effective_mile': effective_mile
                    })
        
        if not valid_stations:
            raise Exception("No reachable fuel stations found along the route.")
            
        # Select the cheapest valid station
        best_station_data = min(valid_stations, key=lambda x: x['station']['retail_price'])
        best_station = best_station_data['station']
        distance_driven = best_station_data['dist_from_current']
        
        gallons_needed = distance_driven / mpg
        cost = gallons_needed * best_station['retail_price']
        
        total_cost += cost
        stops.append({
            "name": best_station['name'],
            "location": f"{best_station['address']}, {best_station['city']}, {best_station['state']}",
            "price": best_station['retail_price'],
            "money_spent": round(cost, 2)
        })
        
        current_mile = best_station_data['effective_mile']

    return {
        "route_map": route_geometry,
        "total_distance_miles": round(total_distance_miles, 2),
        "total_cost": round(total_cost, 2),
        "fuel_stops": stops
    }
