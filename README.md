# Fuel Optimizer API

A high-performance Django REST API designed to calculate the mathematically optimal fuel stops for a truck traveling across the USA. 

## Features
- **Intelligent Routing Algorithm:** Uses a Greedy algorithm with a 500-mile lookahead and dynamic tank tracking to find the cheapest fuel stops.
- **In-Memory Spatial Querying:** Implements Haversine distance calculations in pure Python to filter thousands of stations instantly without needing complex PostGIS extensions.
- **OpenRouteService Integration:** Automatically fetches accurate turn-by-turn driving polyline geometries.

---

## ⚡ Quick Start: Pre-Loaded Database

> **IMPORTANT:** The `db.sqlite3` file included in this repository is **pre-loaded with over 6,400 valid, geocoded truck stops**. 
> You do **not** need to run the 24-hour geocoding data-loading script. The API is ready to test immediately out of the box and will deliver sub-5-second response times.

---

## Setup Instructions

### 1. Environment Configuration
You must provide an OpenRouteService API Key to use the routing features.
Create a new file named `.env` in the root of the project and add your key:

```env
ORS_API_KEY="your_open_route_service_api_key_here"
```

### 2. Install Dependencies
Ensure you have Python installed, then install the required packages:
```bash
pip install django djangorestframework geopy pandas requests python-dotenv
```

### 3. Start the Server
Run the Django development server:
```bash
python manage.py runserver
```

---

## API Usage

### Endpoint
`POST /api/routing/optimize/`

### Request Format
Send a JSON payload with the `start_location` and `finish_location` strings.

**Example Request:**
```json
{
    "start_location": "New York, NY",
    "finish_location": "Los Angeles, CA"
}
```

### Example Response
The API will return a JSON object detailing the full coordinate path, total miles, total cost, and the exact chronological itinerary of the optimal fuel stops.

```json
{
    "route_map": [[-74.006, 40.7128], ...],
    "total_distance_miles": 2790.15,
    "total_cost": 894.20,
    "fuel_stops": [
        {
            "name": "Flying J Travel Center",
            "location": "123 Highway Blvd, Allentown, PA",
            "price": 3.12,
            "money_spent": 156.00
        },
        ...
    ]
}
```

---

## Technical Details

### The Greedy Optimization Algorithm
The algorithm is designed around a truck with a 50-gallon tank that gets 10 Miles Per Gallon (500-mile max range). 
It tracks the state of the tank dynamically as it travels along the route. If a cheaper station exists within the 500-mile range, the truck will buy *only* enough fuel to reach that cheaper station. If no cheaper station exists, the truck will fill the tank to the absolute maximum to capitalize on the lower price before continuing its journey.
