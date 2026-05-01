import pandas as pd
import time
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from django.core.management.base import BaseCommand
from routing.models import FuelStation

class Command(BaseCommand):
    help = 'Load fuel prices from CSV and geocode locations'

    def add_arguments(self, parser):
        parser.add_argument('--csv_path', type=str, default='fuel-prices-for-be-assessment.csv', help='Path to the fuel prices CSV file')

    def handle(self, *args, **options):
        csv_path = options['csv_path']
        self.stdout.write(self.style.NOTICE(f'Loading data from {csv_path}...'))
        
        try:
            df = pd.read_csv(csv_path)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'File not found: {csv_path}'))
            return
        
        geolocator = Nominatim(user_agent="fuel_optimizer_geocoder_1.0")
        
        total_rows = len(df)
        processed = 0
        newly_geocoded = 0
        skipped = 0

        self.stdout.write(self.style.NOTICE(f'Found {total_rows} rows. Starting processing...'))

        for index, row in df.iterrows():
            opis_id = row['OPIS Truckstop ID']
            name = row['Truckstop Name']
            address = row['Address']
            city = row['City']
            state = row['State']
            rack_id = row['Rack ID']
            retail_price = row['Retail Price']

            station, created = FuelStation.objects.get_or_create(
                opis_id=opis_id,
                defaults={
                    'name': name,
                    'address': address,
                    'city': city,
                    'state': state,
                    'rack_id': rack_id,
                    'retail_price': retail_price,
                }
            )

            # Resumable: Only geocode if latitude/longitude is missing
            if station.latitude is None or station.longitude is None:
                queries_to_try = [
                    f"{address}, {city}, {state}, USA",
                    f"{city}, {state}, USA"  # Fallback
                ]
                
                geocoded = False
                for query in queries_to_try:
                    success = False
                    retries = 3
                    for attempt in range(retries):
                        try:
                            # 1.2s sleep before EVERY call to respect strict rate limits
                            time.sleep(1.2)
                            location = geolocator.geocode(query, timeout=10)
                            if location:
                                station.latitude = location.latitude
                                station.longitude = location.longitude
                                station.save()
                                geocoded = True
                            success = True
                            break
                        except (GeocoderTimedOut, GeocoderServiceError) as e:
                            self.stdout.write(self.style.WARNING(f'Geocoding failed for {query}: {e}. Retrying in 5 seconds... ({attempt+1}/{retries})'))
                            time.sleep(5)
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f'Unexpected error geocoding {query}: {e}'))
                            success = True
                            break
                    
                    if geocoded:
                        newly_geocoded += 1
                        break
                    else:
                        self.stdout.write(self.style.WARNING(f'Geocoding returned None for {query}'))
                
                if not geocoded:
                    skipped += 1
                    self.stdout.write(self.style.ERROR(f'Fallback also failed for station {opis_id} in {city}, {state}. Skipping.'))

            processed += 1
            if processed % 100 == 0 or processed == total_rows:
                self.stdout.write(self.style.SUCCESS(f'Processed {processed}/{total_rows}...'))

        self.stdout.write(self.style.SUCCESS(
            f'Finished. Total processed: {processed}. '
            f'Newly geocoded: {newly_geocoded}. Skipped/Failed: {skipped}.'
        ))
