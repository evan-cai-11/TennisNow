#!/usr/bin/env python3
"""
menlo_park_schedule_fetcher.py

Script to fetch tennis court schedule data from Menlo Park's Xplore Recreation booking system.
Based on analysis of the JavaScript code in FacilityLandingPageController.js.

Key findings from JavaScript analysis:
1. The API endpoint is a POST request to FacilityAvailability
2. The "Jump to Date" button triggers a date change which calls requestAndShowTimeSlots()
3. The API requires specific parameters including facilityId, date, daysCount, duration, serviceId, and durationIds

Usage:
  python menlo_park_schedule_fetcher.py --date 2025-01-15
  python menlo_park_schedule_fetcher.py --date 2025-01-15 --debug
  python menlo_park_schedule_fetcher.py --start-date 2025-01-15 --end-date 2025-01-21
"""

import argparse
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import time

class MenloParkScheduleFetcher:
    """Fetch schedule data from Menlo Park's Xplore Recreation booking system."""
    
    def __init__(self):
        self.base_url = "https://cityofmenlopark.perfectmind.com"
        self.api_url = f"{self.base_url}/26116/Clients/BookMe4LandingPages/FacilityAvailability"
        self.facility_page_url = f"{self.base_url}/26116/Clients/BookMe4LandingPages/Facility"
        
        # Facility and service information extracted from the HTML
        self.facility_id = "aa931648-bf9a-4519-9ade-652246c770ef"
        self.widget_id = "286f9a84-b14e-434e-acd2-cb2016c8a3cd"
        self.calendar_id = "cd918767-63df-4159-972b-56a7bea51bd1"
        
        # Service information from the JavaScript initialization
        # Found the correct service ID from the HTML services data
        self.service_id = "819f1be6-6add-4c70-b3fd-b5c71f5e38a3"  # Tennis Court Rentals service ID
        self.duration = 60  # 60 minutes
        self.duration_ids = [
            "a389d9e6-db77-4ea9-a8cd-38ab06957e85",
            "b695197c-68ec-4979-915b-391ce1772664", 
            "0af7ff92-69b5-4717-8b52-52bcdfa334ed",
            "2ee8c03b-0bdc-4677-96d1-56bf6ab863af"
        ]
        
        # Anti-forgery token (from the HTML, but may need to be refreshed)
        self.anti_forgery_token = "NDwp2noK7Vl6F_YSVnTbYEZAMI5YjRkgURdET0ea7W3zKJcl6dXIL59TUWNgGbfgKSC2NazTuLxhzZ-RtLd1ULCDRIg-XjtGiBrwuCk0NoDbn4pr0"
        
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
            # First, visit the facility page to get the token
            facility_url = f"{self.facility_page_url}?facilityId={self.facility_id}&widgetId={self.widget_id}&calendarId={self.calendar_id}"
            
            response = self.session.get(facility_url, timeout=30)
            
            if response.status_code == 200:
                # Extract the token from the HTML
                import re
                token_match = re.search(r'name="__RequestVerificationToken".*?value="([^"]+)"', response.text)
                
                if token_match:
                    token = token_match.group(1)
                    print(f"   ✅ Successfully fetched new token")
                    self.anti_forgery_token = token
                    return token
                else:
                    print(f"   ⚠️  Could not find token in response, using existing token")
                    return self.anti_forgery_token
            else:
                print(f"   ⚠️  Failed to fetch facility page (status: {response.status_code}), using existing token")
                return self.anti_forgery_token
                
        except Exception as e:
            print(f"   ⚠️  Error fetching token: {e}, using existing token")
            return self.anti_forgery_token
    
    def get_date_without_timezone(self, date_str: str) -> str:
        """
        Convert date string to format expected by the API (without timezone).
        Based on the JavaScript getDateWithoutTimezone function.
        """
        try:
            # Parse the input date
            if isinstance(date_str, str):
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            else:
                date_obj = date_str
            
            # JavaScript getDateWithoutTimezone returns JSON format (ISO string)
            # Remove timezone offset and return ISO format
            import time
            timestamp = date_obj.timestamp()
            # Convert to UTC and return ISO format
            utc_date = datetime.utcfromtimestamp(timestamp)
            return utc_date.isoformat() + 'Z'
        except Exception as e:
            print(f"Error formatting date: {e}")
            return date_str
    
    def fetch_schedule_data(self, start_date: str, days_count: int = 7) -> Dict:
        """
        Fetch schedule data using POST request (as per JavaScript analysis).
        
        The JavaScript shows:
        - $.ajaxAntiForgeryPost with type: 'post'
        - url: self.options.availabilityUrl
        - data: facilityId, date, daysCount, duration, serviceId, durationIds
        """
        print(f"📅 Fetching schedule data from Menlo Park API")
        print(f"🔗 URL: {self.api_url}")
        print(f"📝 Method: POST (as per JavaScript analysis)")
        
        # Format date as expected by the API
        formatted_date = self.get_date_without_timezone(start_date)
        
        # Fetch fresh anti-forgery token
        token = self.fetch_anti_forgery_token()
        
        # Prepare POST data (matching the JavaScript request)
        # Based on the JavaScript analysis, we need these parameters:
        post_data = {
            'facilityId': self.facility_id,
            'date': formatted_date,
            'daysCount': days_count,
            'duration': self.duration,
            'serviceId': self.service_id,  # Correct service ID from HTML
            'calendarId': self.calendar_id,  # Added missing calendarId
            'feeType': 0,  # Added missing feeType (0 from the HTML data)
            '__RequestVerificationToken': token
        }
        
        # Add durationIds as individual parameters (as seen in JavaScript)
        for i, duration_id in enumerate(self.duration_ids):
            post_data[f'durationIds[{i}]'] = duration_id
        
        print(f"\n🔄 Making POST request with data:")
        for key, value in post_data.items():
            if key.startswith('durationIds['):
                print(f"   {key}: {value}")
            else:
                print(f"   {key}: {value}")
        
        try:
            response = self.session.post(
                self.api_url, 
                data=post_data, 
                timeout=30
            )
            
            print(f"\n   Status: {response.status_code}")
            print(f"   Content-Type: {response.headers.get('content-type', 'Unknown')}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"   ✅ Success! JSON response received")
                    print(f"   Response type: {type(data)}")
                    
                    if isinstance(data, dict):
                        print(f"   Keys: {list(data.keys())}")
                        
                        # Check for common data structures
                        if 'availabilities' in data:
                            print(f"   Availabilities count: {len(data['availabilities'])}")
                        if 'bookingDays' in data:
                            print(f"   Booking days count: {len(data['bookingDays'])}")
                        if 'facilities' in data:
                            print(f"   Facilities count: {len(data['facilities'])}")
                    
                    elif isinstance(data, list):
                        print(f"   List length: {len(data)}")
                        if len(data) > 0 and isinstance(data[0], dict):
                            print(f"   First item keys: {list(data[0].keys())}")
                    
                    return data
                    
                except json.JSONDecodeError:
                    print(f"   ❌ Not JSON response")
                    print(f"   Response text (first 500 chars): {response.text[:500]}")
                    return {"error": "Invalid JSON response", "text": response.text[:500]}
                    
            else:
                print(f"   ❌ Error: {response.status_code}")
                print(f"   Response: {response.text[:500]}")
                return {"error": f"HTTP {response.status_code}", "text": response.text[:500]}
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
            return {"error": str(e)}
    
    def parse_schedule_data(self, schedule_data: Dict, start_date: str = None) -> Dict:
        """
        Parse schedule data from the API response.
        
        Based on the JavaScript logic in renderSlots function.
        """
        print(f"\n📋 Parsing schedule data from API response...")
        
        if "error" in schedule_data:
            return schedule_data
        
        # Extract availabilities from different possible data structures
        availabilities = []
        
        if isinstance(schedule_data, dict):
            if 'availabilities' in schedule_data:
                availabilities = schedule_data['availabilities']
            elif 'bookingDays' in schedule_data:
                # bookingDays might contain availabilities
                for day in schedule_data['bookingDays']:
                    if 'availabilities' in day:
                        availabilities.extend(day['availabilities'])
            else:
                # Maybe the entire response is the availabilities array
                availabilities = [schedule_data] if isinstance(schedule_data, dict) else []
        
        elif isinstance(schedule_data, list):
            availabilities = schedule_data
        
        print(f"   Found {len(availabilities)} availability slots")
        
        if not availabilities:
            return {"error": "No availability data found in response"}
        
        # Show sample availability structure for debugging
        if availabilities and isinstance(availabilities[0], dict):
            print(f"   Sample availability keys: {list(availabilities[0].keys())}")
            if 'StartTime' in availabilities[0]:
                print(f"   Sample StartTime: {availabilities[0]['StartTime']}")
            if 'EndTime' in availabilities[0]:
                print(f"   Sample EndTime: {availabilities[0]['EndTime']}")
            if 'Title' in availabilities[0]:
                print(f"   Sample Title: {availabilities[0]['Title']}")
        
        # Group availabilities by date
        availabilities_by_date = {}
        
        for availability in availabilities:
            if isinstance(availability, dict):
                # Extract date from different possible fields
                availability_date = None
                
                # Try different date field names
                date_fields = ['Date', 'StartDate', 'date', 'startDate', 'StartTime']
                
                for field in date_fields:
                    if field in availability:
                        date_value = availability[field]
                        if isinstance(date_value, str):
                            # Handle different date formats
                            if 'T' in date_value:
                                availability_date = date_value.split('T')[0]
                            elif '/' in date_value:
                                # Handle M/dd/yy format
                                try:
                                    date_obj = datetime.strptime(date_value, '%m/%d/%y')
                                    availability_date = date_obj.strftime('%Y-%m-%d')
                                except:
                                    availability_date = date_value
                            else:
                                availability_date = date_value
                        elif isinstance(date_value, dict) and 'date' in date_value:
                            availability_date = date_value['date']
                        break
                
                if availability_date:
                    if availability_date not in availabilities_by_date:
                        availabilities_by_date[availability_date] = []
                    availabilities_by_date[availability_date].append(availability)
                else:
                    print(f"   ⚠️  Could not extract date from availability: {list(availability.keys())}")
        
        # Create schedule structure
        schedule_data = []
        for date, date_availabilities in sorted(availabilities_by_date.items()):
            schedule_data.append({
                'date': date,
                'availabilities': date_availabilities,
                'availability_count': len(date_availabilities)
            })
        
        print(f"   Created schedule for {len(schedule_data)} dates")
        
        return {
            'schedule_data': schedule_data,
            'total_availabilities': len(availabilities),
            'total_dates': len(schedule_data),
            'date_range': {
                'start': min(availabilities_by_date.keys()) if availabilities_by_date else None,
                'end': max(availabilities_by_date.keys()) if availabilities_by_date else None
            }
        }
    
    def fetch_schedule(self, start_date: str, days_count: int = 7, debug: bool = False) -> Dict:
        """Main method to fetch and parse schedule data."""
        print(f"🎾 Menlo Park Schedule Fetcher")
        print(f"📍 Facility: Burgess Park - Tennis Court #1")
        print(f"📅 Start Date: {start_date}, Days: {days_count}")
        print("=" * 60)
        
        # Step 1: Fetch schedule data
        schedule_data = self.fetch_schedule_data(start_date, days_count)
        
        if debug:
            print(f"\n🔍 Debug - Raw schedule data:")
            print(json.dumps(schedule_data, indent=2, default=str)[:1000] + "...")
        
        # Step 2: Parse schedule data
        parsed_result = self.parse_schedule_data(schedule_data, start_date)
        
        return parsed_result


def main():
    parser = argparse.ArgumentParser(
        description="Fetch tennis court schedule data from Menlo Park's Xplore Recreation booking system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python menlo_park_schedule_fetcher.py --date 2025-01-15
  python menlo_park_schedule_fetcher.py --date 2025-01-15 --debug
  python menlo_park_schedule_fetcher.py --start-date 2025-01-15 --days 14
        """
    )
    
    parser.add_argument("--date", help="Specific date in YYYY-MM-DD format")
    parser.add_argument("--start-date", help="Start date in YYYY-MM-DD format")
    parser.add_argument("--days", type=int, default=7, help="Number of days to fetch (default: 7)")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--output", help="Output JSON file path")
    
    args = parser.parse_args()
    
    # Determine start date
    if args.date:
        start_date = args.date
    elif args.start_date:
        start_date = args.start_date
    else:
        # Default to today
        start_date = datetime.now().strftime('%Y-%m-%d')
        print(f"ℹ️  No date specified, using today: {start_date}")
    
    # Initialize fetcher
    fetcher = MenloParkScheduleFetcher()
    
    # Fetch schedule data
    result = fetcher.fetch_schedule(start_date, args.days, args.debug)
    
    # Output results
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\n💾 Results saved to: {args.output}")
    else:
        print(f"\n📋 Results:")
        print(json.dumps(result, indent=2, default=str))
    
    return 0


if __name__ == "__main__":
    exit(main())
