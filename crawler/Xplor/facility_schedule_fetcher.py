#!/usr/bin/env python3
"""
facility_schedule_fetcher.py

Generic script to fetch tennis court schedule data from Xplore Recreation booking systems.
This script takes all parameters directly without loading from configuration files.

Usage:
  python facility_schedule_fetcher.py --base-url "https://cityofmenlopark.perfectmind.com" \
    --api-path "/26116/Clients/BookMe4LandingPages/FacilityAvailability" \
    --facility-page-path "/26116/Clients/BookMe4LandingPages/Facility" \
    --facility-id "f7ab9c6c-6555-488e-9e58-c7c391821631" \
    --widget-id "286f9a84-b14e-434e-acd2-cb2016c8a3cd" \
    --calendar-id "cd918767-63df-4159-972b-56a7bea51bd1" \
    --service-id "819f1be6-6add-4c70-b3fd-b5c71f5e38a3" \
    --duration-ids "c45b0f26-9b78-48fd-8007-6d2e73584d7b,4737abc7-6ddf-46b9-a5b9-a9f2e8111606" \
    --date 2025-10-13 --days 1
"""

import argparse
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import time
import os

class FacilityScheduleFetcher:
    """Generic facility schedule fetcher for Xplore Recreation booking systems."""
    
    def __init__(self, base_url: str, api_path: str, facility_page_path: str, 
                 facility_id: str, widget_id: str, calendar_id: str, 
                 service_id: str, duration_ids: List[str], 
                 duration: int = 60, fee_type: int = 0):
        self.base_url = base_url
        self.api_url = f"{base_url}{api_path}"
        self.facility_page_url = f"{base_url}{facility_page_path}"
        
        # Facility parameters
        self.facility_id = facility_id
        self.widget_id = widget_id
        self.calendar_id = calendar_id
        self.service_id = service_id
        self.duration_ids = duration_ids
        self.duration = duration
        self.fee_type = fee_type
        
        # Headers that mimic the browser request
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': f'{self.facility_page_url}?facilityId={self.facility_id}&widgetId={self.widget_id}&calendarId={self.calendar_id}',
            'X-Requested-With': 'XMLHttpRequest',
            'Connection': 'keep-alive',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
        }
        
        # Use a session to maintain cookies
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def fetch_anti_forgery_token(self) -> str:
        """
        Fetch a fresh anti-forgery token from the facility page.
        """
        print(f"🔑 Fetching fresh anti-forgery token...")
        
        try:
            # Get the facility page to extract the anti-forgery token
            response = self.session.get(f"{self.facility_page_url}?facilityId={self.facility_id}&widgetId={self.widget_id}&calendarId={self.calendar_id}")
            response.raise_for_status()
            
            # Extract the anti-forgery token from the HTML
            import re
            token_match = re.search(r'name="__RequestVerificationToken".*?value="([^"]+)"', response.text)
            if token_match:
                token = token_match.group(1)
                print(f"   ✅ Successfully fetched new token")
                return token
            else:
                raise ValueError("Could not find anti-forgery token in response")
                
        except Exception as e:
            print(f"   ❌ Error fetching anti-forgery token: {e}")
            raise
    
    def get_date_without_timezone(self, date_obj: datetime) -> str:
        """
        Convert date to ISO format without timezone (as per JavaScript getDateWithoutTimezone).
        Returns format: YYYY-MM-DDTHH:MM:SSZ
        """
        return date_obj.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    def fetch_schedule_data(self, start_date: datetime, days_count: int = 1) -> Dict:
        """
        Fetch schedule data from the API.
        """
        print(f"📅 Fetching schedule data from API")
        print(f"🔗 URL: {self.api_url}")
        print(f"📝 Method: POST (as per JavaScript analysis)")
        
        # Get fresh anti-forgery token
        anti_forgery_token = self.fetch_anti_forgery_token()
        
        # Prepare POST data
        post_data = {
            'facilityId': self.facility_id,
            'date': self.get_date_without_timezone(start_date),
            'daysCount': days_count,
            'duration': self.duration,
            'serviceId': self.service_id,
            'calendarId': self.calendar_id,
            'feeType': self.fee_type,
            '__RequestVerificationToken': anti_forgery_token
        }
        
        # Add duration IDs as individual parameters
        for i, duration_id in enumerate(self.duration_ids):
            post_data[f'durationIds[{i}]'] = duration_id
        
        print(f"\n🔄 Making POST request with data:")
        for key, value in post_data.items():
            if key != '__RequestVerificationToken':
                print(f"   {key}: {value}")
            else:
                print(f"   {key}: {value[:50]}...")
        
        try:
            response = self.session.post(self.api_url, data=post_data)
            response.raise_for_status()
            
            print(f"\n   Status: {response.status_code}")
            print(f"   Content-Type: {response.headers.get('Content-Type', 'Unknown')}")
            
            if 'application/json' in response.headers.get('Content-Type', ''):
                print(f"   ✅ Success! JSON response received")
                data = response.json()
                print(f"   Response type: {type(data)}")
                if isinstance(data, dict):
                    print(f"   Keys: {list(data.keys())}")
                    if 'availabilities' in data:
                        print(f"   Availabilities count: {len(data['availabilities'])}")
                return data
            else:
                print(f"   ❌ Not JSON response")
                print(f"   Response text (first 500 chars): {response.text[:500]}")
                return {}
                
        except requests.exceptions.RequestException as e:
            print(f"   ❌ Request failed: {e}")
            return {}
        except json.JSONDecodeError as e:
            print(f"   ❌ JSON decode error: {e}")
            print(f"   Response text (first 500 chars): {response.text[:500]}")
            return {}
    
    def parse_schedule_data(self, schedule_data: Dict) -> List[Dict]:
        """
        Parse the schedule data from the API response.
        """
        print(f"\n📋 Parsing schedule data from API response...")
        
        if not schedule_data or 'availabilities' not in schedule_data:
            print(f"   Found 0 availability slots")
            return []
        
        availabilities = schedule_data['availabilities']
        print(f"   Found {len(availabilities)} availability slots")
        
        if availabilities:
            sample_keys = list(availabilities[0].keys()) if availabilities[0] else []
            print(f"   Sample availability keys: {sample_keys}")
        
        # Create schedule data structure
        schedule = []
        for availability in availabilities:
            schedule.append({
                'date': availability.get('Date', ''),
                'availabilities': [availability]
            })
        
        print(f"   Created schedule for {len(schedule)} dates")
        return schedule
    
    def save_results(self, schedule_data: List[Dict], output_file: str = None) -> str:
        """
        Save the results to a JSON file.
        """
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"facility_schedule_{timestamp}.json"
        
        results = {
            'facility_id': self.facility_id,
            'facility_page_url': f"{self.facility_page_url}?facilityId={self.facility_id}&widgetId={self.widget_id}&calendarId={self.calendar_id}",
            'schedule_data': schedule_data,
            'fetched_at': datetime.now().isoformat()
        }
        
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n💾 Results saved to: {output_file}")
        return output_file

def main():
    parser = argparse.ArgumentParser(description='Fetch facility schedule data from Xplore Recreation booking systems')
    
    # Required parameters
    parser.add_argument('--base-url', required=True, help='Base URL of the booking system')
    parser.add_argument('--api-path', required=True, help='API path for facility availability')
    parser.add_argument('--facility-page-path', required=True, help='Facility page path')
    parser.add_argument('--facility-id', required=True, help='Facility ID')
    parser.add_argument('--widget-id', required=True, help='Widget ID')
    parser.add_argument('--calendar-id', required=True, help='Calendar ID')
    parser.add_argument('--service-id', required=True, help='Service ID')
    parser.add_argument('--duration-ids', required=True, help='Comma-separated list of duration IDs')
    
    # Optional parameters
    parser.add_argument('--duration', type=int, default=60, help='Duration in minutes (default: 60)')
    parser.add_argument('--fee-type', type=int, default=0, help='Fee type (default: 0)')
    
    # Date parameters
    parser.add_argument('--date', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--days', type=int, default=1, help='Number of days to fetch (default: 1)')
    
    # Output parameters
    parser.add_argument('--output', help='Output file path')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    
    args = parser.parse_args()
    
    # Parse duration IDs
    duration_ids = [id.strip() for id in args.duration_ids.split(',')]
    
    # Parse date
    try:
        start_date = datetime.strptime(args.date, '%Y-%m-%d')
    except ValueError:
        print(f"❌ Invalid date format. Use YYYY-MM-DD")
        return 1
    
    print(f"🎾 Facility Schedule Fetcher")
    print(f"📍 Facility ID: {args.facility_id}")
    print(f"📅 Start Date: {args.date}, Days: {args.days}")
    print(f"=" * 60)
    
    # Create fetcher instance
    fetcher = FacilityScheduleFetcher(
        base_url=args.base_url,
        api_path=args.api_path,
        facility_page_path=args.facility_page_path,
        facility_id=args.facility_id,
        widget_id=args.widget_id,
        calendar_id=args.calendar_id,
        service_id=args.service_id,
        duration_ids=duration_ids,
        duration=args.duration,
        fee_type=args.fee_type
    )
    
    # Fetch schedule data
    schedule_data = fetcher.fetch_schedule_data(start_date, args.days)
    
    if args.debug:
        print(f"\n🔍 Debug - Raw schedule data:")
        print(json.dumps(schedule_data, indent=2)[:1000] + "..." if len(str(schedule_data)) > 1000 else json.dumps(schedule_data, indent=2))
    
    # Parse schedule data
    parsed_schedule = fetcher.parse_schedule_data(schedule_data)
    
    # Save results
    output_file = fetcher.save_results(parsed_schedule, args.output)
    
    return 0

if __name__ == "__main__":
    exit(main())
