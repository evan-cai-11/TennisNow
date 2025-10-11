#!/usr/bin/env python3
"""
facilitron_agenda_analyzer.py

Script to fetch tennis court agenda data from Facilitron API.
Based on analysis of the JavaScript code in fa.external.calendar.js.

Key findings from JavaScript analysis:
1. The API endpoint is a POST request (not GET)
2. The agenda data comes from the same API that loads calendar events
3. The agenda is generated client-side from the events data
4. The events are already loaded when the page loads

Usage:
  python facilitron_agenda_analyzer.py --date 2025-01-15
  python facilitron_agenda_analyzer.py --month 2025-01
  python facilitron_agenda_analyzer.py --date 2025-01-15 --debug
"""

import argparse
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import time

class FacilitronAgendaAnalyzer:
    """Fetch agenda data from Facilitron API based on JavaScript analysis."""
    
    def __init__(self, owner_uid: str = "hrtc94010", calendar_id: str = "b89f39977734a64796c5"):
        self.owner_uid = owner_uid
        self.calendar_id = calendar_id
        self.base_url = "https://www.facilitron.com"
        self.api_url = f"{self.base_url}/api/owners/{owner_uid}/external_schedules/{calendar_id}"
        
        # Headers that mimic the browser request
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': f'{self.base_url}/hrtc94010/calendar/u:{calendar_id}',
            'X-Requested-With': 'XMLHttpRequest',
            'Connection': 'keep-alive',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
        }
    
    def fetch_calendar_data(self, start_date: str = None, end_date: str = None) -> Dict:
        """
        Fetch calendar data using POST request (as per JavaScript analysis).
        
        The JavaScript shows:
        - eventSources: [{ url: url, type: 'POST', dataType: 'json', ... }]
        - This loads all events for the calendar
        - The agenda is generated client-side from these events
        """
        print(f"📅 Fetching calendar data from Facilitron API")
        print(f"🔗 URL: {self.api_url}")
        print(f"📝 Method: POST (as per JavaScript analysis)")
        
        # Use the working POST data combination
        post_data = {'start': start_date, 'end': end_date} if start_date and end_date else {}
        
        print(f"\n🔄 Making POST request with data: {post_data}")
        
        try:
            response = requests.post(
                self.api_url, 
                data=post_data, 
                headers=self.headers, 
                timeout=30
            )
            
            print(f"   Status: {response.status_code}")
            print(f"   Content-Type: {response.headers.get('content-type', 'Unknown')}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"   ✅ Success! JSON response received")
                    print(f"   Response type: {type(data)}")
                    
                    if isinstance(data, dict):
                        print(f"   Keys: {list(data.keys())}")
                        
                        # Check for common data structures
                        if 'events' in data:
                            print(f"   Events count: {len(data['events'])}")
                        if 'facilities' in data:
                            print(f"   Facilities count: {len(data['facilities'])}")
                        if 'schedules' in data:
                            print(f"   Schedules count: {len(data['schedules'])}")
                    
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
    
    def parse_agenda_data(self, calendar_data: Dict, start_date: str = None, end_date: str = None) -> Dict:
        """
        Parse agenda data from calendar events (mimicking the JavaScript renderAgenda function).
        
        JavaScript logic:
        1. Get events from the calendar data
        2. Sort events by startTime
        3. Group events by eventdate
        4. Create agenda structure with date and events
        """
        print(f"\n📋 Parsing agenda data from calendar events...")
        
        if "error" in calendar_data:
            return calendar_data
        
        # Extract events from different possible data structures
        events = []
        
        if isinstance(calendar_data, dict):
            if 'events' in calendar_data:
                events = calendar_data['events']
            elif 'schedules' in calendar_data:
                events = calendar_data['schedules']
            elif 'data' in calendar_data:
                events = calendar_data['data']
            else:
                # Maybe the entire response is the events array
                events = [calendar_data] if isinstance(calendar_data, dict) else []
        
        elif isinstance(calendar_data, list):
            events = calendar_data
        
        print(f"   Found {len(events)} events")
        
        if not events:
            return {"error": "No events found in calendar data"}
        
        # Show sample event structure for debugging
        if events and isinstance(events[0], dict):
            print(f"   Sample event keys: {list(events[0].keys())}")
            if 'localDate' in events[0]:
                print(f"   Sample localDate: {events[0]['localDate']}")
            if 'startTime' in events[0]:
                print(f"   Sample startTime: {events[0]['startTime']}")
            if 'facility' in events[0]:
                print(f"   Sample facility: {events[0]['facility'].get('name', 'N/A')}")
        
        # Group events by date (mimicking JavaScript logic)
        events_by_date = {}
        
        for event in events:
            if isinstance(event, dict):
                # Extract date from different possible fields
                event_date = None
                
                # Try different date field names
                date_fields = ['eventdate', 'localDate', 'date', 'start', 'event_date']
                
                for field in date_fields:
                    if field in event:
                        date_value = event[field]
                        if isinstance(date_value, str):
                            # Handle ISO date format like "2025-10-13T00:00:00.000Z"
                            if 'T' in date_value:
                                event_date = date_value.split('T')[0]
                            else:
                                event_date = date_value
                        elif isinstance(date_value, dict) and 'date' in date_value:
                            event_date = date_value['date']
                        break
                
                if event_date:
                    if event_date not in events_by_date:
                        events_by_date[event_date] = []
                    events_by_date[event_date].append(event)
                else:
                    print(f"   ⚠️  Could not extract date from event: {list(event.keys())}")
        
        # Create agenda structure
        agenda_data = []
        for date, date_events in sorted(events_by_date.items()):
            agenda_data.append({
                'date': date,
                'events': date_events,
                'event_count': len(date_events)
            })
        
        print(f"   Created agenda for {len(agenda_data)} dates")
        
        return {
            'agenda_data': agenda_data,
            'total_events': len(events),
            'total_dates': len(agenda_data),
            'date_range': {
                'start': min(events_by_date.keys()) if events_by_date else None,
                'end': max(events_by_date.keys()) if events_by_date else None
            }
        }
    
    def fetch_agenda(self, start_date: str = None, end_date: str = None, debug: bool = False) -> Dict:
        """Main method to fetch and parse agenda data."""
        print(f"🎾 Facilitron Agenda Analyzer")
        print(f"📍 Owner: {self.owner_uid}, Calendar: {self.calendar_id}")
        if start_date and end_date:
            print(f"📅 Date range: {start_date} to {end_date}")
        print("=" * 60)
        
        # Step 1: Fetch calendar data
        calendar_data = self.fetch_calendar_data(start_date, end_date)
        
        if debug:
            print(f"\n🔍 Debug - Raw calendar data:")
            print(json.dumps(calendar_data, indent=2, default=str)[:1000] + "...")
        
        # Step 2: Parse agenda data
        agenda_result = self.parse_agenda_data(calendar_data, start_date, end_date)
        
        return agenda_result


def main():
    parser = argparse.ArgumentParser(
        description="Fetch tennis court agenda data from Facilitron API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python facilitron_agenda_analyzer.py --date 2025-01-15
  python facilitron_agenda_analyzer.py --month 2025-01
  python facilitron_agenda_analyzer.py --date 2025-01-15 --debug
  python facilitron_agenda_analyzer.py --start-date 2025-01-01 --end-date 2025-01-31
        """
    )
    
    parser.add_argument("--date", help="Specific date in YYYY-MM-DD format")
    parser.add_argument("--month", help="Month in YYYY-MM format")
    parser.add_argument("--start-date", help="Start date in YYYY-MM-DD format")
    parser.add_argument("--end-date", help="End date in YYYY-MM-DD format")
    parser.add_argument("--owner-uid", default="hrtc94010", help="Owner UID (default: hrtc94010)")
    parser.add_argument("--calendar-id", default="b89f39977734a64796c5", help="Calendar ID")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--output", help="Output JSON file path")
    
    args = parser.parse_args()
    
    # Determine date range
    start_date, end_date = None, None
    
    if args.date:
        start_date = end_date = args.date
    elif args.month:
        start_date = f"{args.month}-01"
        year, month = map(int, args.month.split('-'))
        if month == 12:
            next_month = datetime(year + 1, 1, 1)
        else:
            next_month = datetime(year, month + 1, 1)
        end_date = (next_month - timedelta(days=1)).strftime('%Y-%m-%d')
    elif args.start_date and args.end_date:
        start_date, end_date = args.start_date, args.end_date
    elif not args.start_date and not args.end_date:
        print("ℹ️  No date range specified, fetching all available data")
    
    # Initialize analyzer
    analyzer = FacilitronAgendaAnalyzer(args.owner_uid, args.calendar_id)
    
    # Fetch agenda data
    result = analyzer.fetch_agenda(start_date, end_date, args.debug)
    
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
