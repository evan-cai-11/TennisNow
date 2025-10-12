#!/usr/bin/env python3
"""
config_schedule_scraper.py

Config-based schedule scraper that can scrape at state, city, or facility levels.
Loads configuration and uses the generic facility_schedule_fetcher for actual data fetching.

Usage:
  # Scrape all facilities in all states
  python config_schedule_scraper.py --level state --date 2025-10-13 --days 1
  
  # Scrape all facilities in a specific state
  python config_schedule_scraper.py --level state --state "CA" --date 2025-10-13 --days 1
  
  # Scrape all facilities in a specific city
  python config_schedule_scraper.py --level city --city "Menlo Park" --date 2025-10-13 --days 1
  
  # Scrape a specific facility
  python config_schedule_scraper.py --level facility --facility "Willow Oaks Park - Tennis Court #4" --date 2025-10-13 --days 1
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Optional

class ConfigScheduleScraper:
    """Config-based schedule scraper for multiple levels of granularity."""
    
    def __init__(self, config_file: str = None):
        self.config = self.load_config(config_file)
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.facility_fetcher_script = os.path.join(self.script_dir, "facility_schedule_fetcher.py")
    
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
    
    def get_all_facilities(self) -> List[Dict]:
        """Get all facilities from all states and cities."""
        all_facilities = []
        for state in self.config["states"]:
            for city in state["cities"]:
                for facility in city["facilities"]:
                    facility_info = {
                        'facility': facility,
                        'city': city,
                        'state': state
                    }
                    all_facilities.append(facility_info)
        return all_facilities
    
    def get_facilities_by_state(self, state_name: str) -> List[Dict]:
        """Get all facilities in a specific state."""
        facilities = []
        for state in self.config["states"]:
            if state["state"].lower() == state_name.lower():
                for city in state["cities"]:
                    for facility in city["facilities"]:
                        facility_info = {
                            'facility': facility,
                            'city': city,
                            'state': state
                        }
                        facilities.append(facility_info)
        return facilities
    
    def get_facilities_by_city(self, city_name: str) -> List[Dict]:
        """Get all facilities in a specific city."""
        facilities = []
        for state in self.config["states"]:
            for city in state["cities"]:
                if city["name"].lower() == city_name.lower():
                    for facility in city["facilities"]:
                        facility_info = {
                            'facility': facility,
                            'city': city,
                            'state': state
                        }
                        facilities.append(facility_info)
        return facilities
    
    def get_facility_by_name(self, facility_name: str) -> Optional[Dict]:
        """Get a specific facility by name."""
        for state in self.config["states"]:
            for city in state["cities"]:
                for facility in city["facilities"]:
                    if facility["name"].lower() == facility_name.lower():
                        return {
                            'facility': facility,
                            'city': city,
                            'state': state
                        }
        return None
    
    def scrape_facility(self, facility_info: Dict, start_date: str, days: int, output_dir: str = None) -> str:
        """Scrape a single facility using the facility_schedule_fetcher script."""
        facility = facility_info['facility']
        city = facility_info['city']
        state = facility_info['state']
        
        print(f"\n🎾 Scraping: {facility['name']}")
        print(f"📍 City: {city['name']}, {state['state']}")
        print(f"📍 Address: {facility['address']}")
        
        # Prepare command arguments
        cmd = [
            sys.executable, self.facility_fetcher_script,
            '--base-url', city['base_url'],
            '--api-path', city['api_path'],
            '--facility-page-path', city['facility_page_path'],
            '--facility-id', facility['facility_id'],
            '--widget-id', facility['widget_id'],
            '--calendar-id', facility['calendar_id'],
            '--service-id', facility['service_id'],
            '--duration-ids', ','.join(facility['duration_ids']),
            '--date', start_date,
            '--days', str(days)
        ]
        
        # Set output file if specified
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            safe_name = facility['name'].replace(' ', '_').replace('#', '').replace('-', '_')
            output_file = os.path.join(output_dir, f"{safe_name}_{start_date.replace('-', '')}.json")
            cmd.extend(['--output', output_file])
        
        try:
            # Run the facility fetcher script
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"   ✅ Success")
            if output_dir:
                print(f"   💾 Saved to: {output_file}")
            return output_file if output_dir else "success"
        except subprocess.CalledProcessError as e:
            print(f"   ❌ Failed: {e}")
            print(f"   Error output: {e.stderr}")
            return None
    
    def scrape_facilities(self, facilities: List[Dict], start_date: str, days: int, output_dir: str = None) -> Dict:
        """Scrape multiple facilities."""
        results = {
            'total': len(facilities),
            'successful': 0,
            'failed': 0,
            'output_files': []
        }
        
        for facility_info in facilities:
            output_file = self.scrape_facility(facility_info, start_date, days, output_dir)
            if output_file:
                results['successful'] += 1
                if output_file != "success":
                    results['output_files'].append(output_file)
            else:
                results['failed'] += 1
        
        return results
    
    def scrape_by_level(self, level: str, start_date: str, days: int, 
                       state_name: str = None, city_name: str = None, 
                       facility_name: str = None, output_dir: str = None) -> Dict:
        """Scrape based on the specified level."""
        
        if level == "state":
            if state_name:
                print(f"🏛️ Scraping all facilities in state: {state_name}")
                facilities = self.get_facilities_by_state(state_name)
            else:
                print(f"🏛️ Scraping all facilities in all states")
                facilities = self.get_all_facilities()
        
        elif level == "city":
            if not city_name:
                raise ValueError("City name is required for city-level scraping")
            print(f"🏙️ Scraping all facilities in city: {city_name}")
            facilities = self.get_facilities_by_city(city_name)
        
        elif level == "facility":
            if not facility_name:
                raise ValueError("Facility name is required for facility-level scraping")
            print(f"🏟️ Scraping specific facility: {facility_name}")
            facility_info = self.get_facility_by_name(facility_name)
            if not facility_info:
                raise ValueError(f"Facility '{facility_name}' not found in configuration")
            facilities = [facility_info]
        
        else:
            raise ValueError(f"Invalid level: {level}. Must be 'state', 'city', or 'facility'")
        
        if not facilities:
            print(f"❌ No facilities found for the specified criteria")
            return {'total': 0, 'successful': 0, 'failed': 0, 'output_files': []}
        
        print(f"📊 Found {len(facilities)} facilities to scrape")
        print(f"📅 Date: {start_date}, Days: {days}")
        print(f"=" * 60)
        
        return self.scrape_facilities(facilities, start_date, days, output_dir)
    
    def list_available_options(self):
        """List all available states, cities, and facilities."""
        print(f"🏛️ Available States:")
        for state in self.config["states"]:
            print(f"   📍 {state['state']}")
        
        print(f"\n🏙️ Available Cities:")
        for state in self.config["states"]:
            for city in state["cities"]:
                print(f"   📍 {city['name']} ({state['state']})")
        
        print(f"\n🏟️ Available Facilities:")
        for state in self.config["states"]:
            for city in state["cities"]:
                for facility in city["facilities"]:
                    print(f"   📍 {facility['name']} - {city['name']}, {state['state']}")

def main():
    parser = argparse.ArgumentParser(description='Config-based schedule scraper for multiple levels')
    
    # Required arguments (unless --list is used)
    parser.add_argument('--level', choices=['state', 'city', 'facility'], 
                       help='Scraping level: state, city, or facility')
    parser.add_argument('--date', help='Start date (YYYY-MM-DD)')
    
    # Optional arguments
    parser.add_argument('--days', type=int, default=1, help='Number of days to fetch (default: 1)')
    parser.add_argument('--state', help='State name (required for state-level scraping)')
    parser.add_argument('--city', help='City name (required for city-level scraping)')
    parser.add_argument('--facility', help='Facility name (required for facility-level scraping)')
    parser.add_argument('--config', help='Configuration file path')
    parser.add_argument('--output-dir', help='Output directory for results')
    parser.add_argument('--list', action='store_true', help='List all available options')
    
    args = parser.parse_args()
    
    try:
        scraper = ConfigScheduleScraper(args.config)
        
        if args.list:
            scraper.list_available_options()
            return 0
        
        # Validate required arguments when not using --list
        if not args.level:
            print(f"❌ --level is required (unless using --list)")
            return 1
        if not args.date:
            print(f"❌ --date is required (unless using --list)")
            return 1
        
        # Validate date format
        try:
            datetime.strptime(args.date, '%Y-%m-%d')
        except ValueError:
            print(f"❌ Invalid date format. Use YYYY-MM-DD")
            return 1
        
        # Perform scraping
        results = scraper.scrape_by_level(
            level=args.level,
            start_date=args.date,
            days=args.days,
            state_name=args.state,
            city_name=args.city,
            facility_name=args.facility,
            output_dir=args.output_dir
        )
        
        # Print summary
        print(f"\n📊 Scraping Summary:")
        print(f"   Total facilities: {results['total']}")
        print(f"   Successful: {results['successful']}")
        print(f"   Failed: {results['failed']}")
        
        if results['output_files']:
            print(f"\n💾 Output files:")
            for file in results['output_files']:
                print(f"   📄 {file}")
        
        return 0 if results['failed'] == 0 else 1
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
