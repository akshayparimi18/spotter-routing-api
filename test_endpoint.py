import os
import sys
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'demo_project.settings')
django.setup()

from django.test import Client

def run_test():
    client = Client()
    print("Sending POST request to /api/routing/optimize/ ...")
    response = client.post('/api/routing/optimize/', {
        'start_location': 'Springfield, IL',
        'finish_location': 'Columbus, OH'
    }, content_type='application/json')
    
    print(f"Status Code: {response.status_code}")
    try:
        print("Response JSON:")
        print(json.dumps(response.json(), indent=2))
    except Exception as e:
        print("Raw Response:")
        print(response.content.decode('utf-8'))

if __name__ == '__main__':
    run_test()
