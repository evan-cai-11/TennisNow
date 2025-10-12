#!/usr/bin/env python3
"""
xplor_schedule_fetcher.py

Script to fetch tennis court schedule data from Menlo Park's Xplore Recreation booking system.
Based on analysis of the JavaScript code in FacilityLandingPageController.js.

Key findings from JavaScript analysis:
1. The API endpoint is a POST request to FacilityAvailability
2. The "Jump to Date" button triggers a date change which calls requestAndShowTimeSlots()
3. The API requires specific parameters including facilityId, date, daysCount, duration, serviceId, and durationIds

Usage:
  python xplor_schedule_fetcher.py --date 2025-01-15
  python xplor_schedule_fetcher.py --date 2025-01-15 --debug
  python xplor_schedule_fetcher.py --start-date 2025-01-15 --end-date 2025-01-21
"""

import argparse
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import time
import os

class MenloParkScheduleFetcher:
    """Fetch schedule data from Menlo Park's Xplore Recreation booking system."""
    
    def __init__(self, facility_name: str = None, config_file: str = None):
        # Load configuration first
        self.config = self.load_config(config_file)
        self.facility = self.get_facility(facility_name)
        self.city = self.get_city_for_facility(facility_name)
        
        # Set URLs from city configuration
        self.base_url = self.city["base_url"]
        self.api_url = f"{self.base_url}{self.city['api_path']}"
        self.facility_page_url = f"{self.base_url}{self.city['facility_page_path']}"
        
        # Extract facility information from config
        self.facility_id = self.facility["facility_id"]
        self.widget_id = self.facility["widget_id"]
        self.calendar_id = self.facility["calendar_id"]
        self.service_id = self.facility["service_id"]
        
        # Default settings from config
        self.duration = self.config["default_settings"]["duration"]
        self.fee_type = self.config["default_settings"]["fee_type"]
        
        # Use facility-specific duration IDs if available, otherwise use default
        if "duration_ids" in self.facility:
            self.duration_ids = self.facility["duration_ids"]
        else:
            self.duration_ids = self.config["default_settings"]["duration_ids"]
        
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
    
    def load_config(self, config_file: str = None) -> Dict:
        """Load configuration from JSON file."""
        if config_file is None:
            # Default to facilities_config.json in the same directory
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_file = os.path.join(script_dir, "facilities_config.json")
        
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {e}")
    
    def get_city_for_facility(self, facility_name: str = None) -> Dict:
        """Get city information for a given facility."""
        # Find the city that contains the specified facility
        for state in self.config["states"]:
            for city in state["cities"]:
                for facility in city["facilities"]:
                    if facility_name is None or facility["name"].lower() == facility_name.lower():
                        return city
        
        # If not found, return the first city
        if self.config["states"] and self.config["states"][0]["cities"]:
            return self.config["states"][0]["cities"][0]
        
        raise ValueError(f"City not found for facility '{facility_name}'")
    
    def get_facility(self, facility_name: str = None) -> Dict:
        """Get facility information by name."""
        # Get all facilities from all states and cities
        all_facilities = []
        for state in self.config["states"]:
            for city in state["cities"]:
                for facility in city["facilities"]:
                    all_facilities.append(facility)
        
        if facility_name is None:
            # Return the first facility if no name specified
            return all_facilities[0]
        
        # Find facility by name (case-insensitive)
        for facility in all_facilities:
            if facility["name"].lower() == facility_name.lower():
                return facility
        
        # If not found, list available facilities
        available_facilities = [f["name"] for f in all_facilities]
        raise ValueError(f"Facility '{facility_name}' not found. Available facilities: {available_facilities}")
    
    def list_facilities(self) -> List[Dict]:
        """List all available facilities."""
        # Get all facilities from all states and cities
        all_facilities = []
        for state in self.config["states"]:
            for city in state["cities"]:
                for facility in city["facilities"]:
                    all_facilities.append(facility)
        return all_facilities
    
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
        print(f"📍 Facility: {self.facility['name']}")
        print(f"📍 Address: {self.facility['address']}")
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
  python xplor_schedule_fetcher.py --date 2025-01-15
  python xplor_schedule_fetcher.py --date 2025-01-15 --debug
  python xplor_schedule_fetcher.py --start-date 2025-01-15 --days 14
  python xplor_schedule_fetcher.py --list-facilities
  python xplor_schedule_fetcher.py --facility "Burgess Park - Tennis Court #1" --date 2025-01-15
        """
    )
    
    parser.add_argument("--date", help="Specific date in YYYY-MM-DD format")
    parser.add_argument("--start-date", help="Start date in YYYY-MM-DD format")
    parser.add_argument("--days", type=int, default=7, help="Number of days to fetch (default: 7)")
    parser.add_argument("--facility", help="Facility name (default: first facility in config)")
    parser.add_argument("--config", help="Path to configuration file (default: facilities_config.json)")
    parser.add_argument("--list-facilities", action="store_true", help="List all available facilities")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--output", help="Output JSON file path")
    
    args = parser.parse_args()
    
    # Handle list facilities command
    if args.list_facilities:
        try:
            fetcher = MenloParkScheduleFetcher(config_file=args.config)
            facilities = fetcher.list_facilities()
            print("🏢 Available Facilities:")
            print("=" * 50)
            for facility in facilities:
                print(f"📍 {facility['name']}")
                print(f"   Address: {facility['address']}")
                print(f"   Contact: {facility.get('contact', 'N/A')}")
                print(f"   Hours: {facility.get('hours', 'N/A')}")
                print(f"   Features: {', '.join(facility.get('features', []))}")
                print()
            return 0
        except Exception as e:
            print(f"❌ Error listing facilities: {e}")
            return 1
    
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
    try:
        fetcher = MenloParkScheduleFetcher(facility_name=args.facility, config_file=args.config)
    except Exception as e:
        print(f"❌ Error initializing fetcher: {e}")
        return 1
    
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
