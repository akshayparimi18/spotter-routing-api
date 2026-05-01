from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from .utils import get_route_data, calculate_optimal_stops

class OptimizeRouteView(APIView):
    def post(self, request):
        start_location = request.data.get('start_location')
        finish_location = request.data.get('finish_location')

        if not start_location or not finish_location:
            return Response({"error": "Please provide both start_location and finish_location."}, status=status.HTTP_400_BAD_REQUEST)

        geolocator = Nominatim(user_agent="fuel_optimizer_api_1.0")

        try:
            start_loc = geolocator.geocode(start_location)
            finish_loc = geolocator.geocode(finish_location)
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            return Response({"error": f"Geocoding service error: {str(e)}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if not start_loc:
            return Response({"error": f"Could not geocode start_location: {start_location}"}, status=status.HTTP_400_BAD_REQUEST)
        if not finish_loc:
            return Response({"error": f"Could not geocode finish_location: {finish_location}"}, status=status.HTTP_400_BAD_REQUEST)

        start_coords = (start_loc.latitude, start_loc.longitude)
        finish_coords = (finish_loc.latitude, finish_loc.longitude)

        try:
            # 1. Get route from ORS
            route_data = get_route_data(start_coords, finish_coords)
            
            # 2. Calculate optimal stops
            result = calculate_optimal_stops(
                route_geometry=route_data['route_geometry'],
                total_distance_miles=route_data['total_distance_miles']
            )
            
            return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
