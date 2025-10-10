#!/usr/bin/env python3
"""
google_calendar_integration.py

Script to fetch tennis court schedules from public Google Calendars.
Supports reading events from public calendars by email address for specific dates.

Usage:
  python google_calendar_integration.py --date 2025-10-09 --public-calendar "city@example.com"
  python google_calendar_integration.py --week 2025-10-09 --public-calendar "city@example.com"
  python google_calendar_integration.py --list-calendars
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional
import re

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_CALENDAR_AVAILABLE = True
except ImportError:
    GOOGLE_CALENDAR_AVAILABLE = False
    print("⚠️  Google Calendar API not available. Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")


class GoogleCalendarIntegration:
    """Handle Google Calendar integration for tennis court schedules."""
    
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    CREDENTIALS_FILE = 'credentials.json'
    TOKEN_FILE = 'token.json'
    
    def __init__(self, credentials_file: str = None, token_file: str = None):
        self.credentials_file = credentials_file or self.CREDENTIALS_FILE
        self.token_file = token_file or self.TOKEN_FILE
        self.service = None
        
    def authenticate(self) -> bool:
        """Authenticate with Google Calendar API."""
        if not GOOGLE_CALENDAR_AVAILABLE:
            print("❌ Google Calendar API not available")
            return False
            
        creds = None
        
        # Load existing token
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, self.SCOPES)
        
        # If no valid credentials, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_file):
                    print(f"❌ Credentials file not found: {self.credentials_file}")
                    print("   Download from: https://console.developers.google.com/apis/credentials")
                    return False
                    
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save credentials for next run
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
        
        try:
            self.service = build('calendar', 'v3', credentials=creds)
            return True
        except Exception as e:
            print(f"❌ Failed to build Google Calendar service: {e}")
            return False
    
    def list_calendars(self) -> List[Dict]:
        """List available calendars."""
        if not self.service:
            return []
        
        try:
            calendar_list = self.service.calendarList().list().execute()
            calendars = []
            for calendar in calendar_list.get('items', []):
                calendars.append({
                    'id': calendar['id'],
                    'summary': calendar['summary'],
                    'description': calendar.get('description', ''),
                    'access_role': calendar.get('accessRole', ''),
                    'primary': calendar.get('primary', False)
                })
            return calendars
        except HttpError as e:
            print(f"❌ Failed to list calendars: {e}")
            return []
    
    def create_calendar(self, name: str, description: str = "") -> Optional[str]:
        """Create a new calendar for tennis court schedules."""
        if not self.service:
            return None
        
        calendar_body = {
            'summary': name,
            'description': description,
            'timeZone': 'America/Los_Angeles'  # Default to Pacific Time
        }
        
        try:
            created_calendar = self.service.calendars().insert(body=calendar_body).execute()
            print(f"✅ Created calendar: {created_calendar['summary']} (ID: {created_calendar['id']})")
            return created_calendar['id']
        except HttpError as e:
            print(f"❌ Failed to create calendar: {e}")
            return None
    
    def get_events_for_date(self, calendar_id: str, date_str: str) -> List[Dict]:
        """Get existing events for a specific date."""
        if not self.service:
            return []
        
        # Convert date to datetime range
        start_date = datetime.strptime(date_str, "%Y-%m-%d")
        end_date = start_date + timedelta(days=1)
        
        time_min = start_date.isoformat() + 'Z'
        time_max = end_date.isoformat() + 'Z'
        
        try:
            events_result = self.service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            return events_result.get('items', [])
        except HttpError as e:
            print(f"❌ Failed to get events: {e}")
            return []
    
    def fetch_public_calendar_events(self, calendar_email: str, date_str: str) -> List[Dict]:
        """Fetch events from a public Google Calendar by email address."""
        if not self.service:
            return []
        
        # Convert date to datetime range
        start_date = datetime.strptime(date_str, "%Y-%m-%d")
        end_date = start_date + timedelta(days=1)
        
        time_min = start_date.isoformat() + 'Z'
        time_max = end_date.isoformat() + 'Z'
        
        try:
            print(f"📅 Fetching events from {calendar_email} for {date_str}...")
            
            events_result = self.service.events().list(
                calendarId=calendar_email,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            print(f"✅ Found {len(events)} events")
            return events
            
        except HttpError as e:
            print(f"❌ Failed to fetch events from {calendar_email}: {e}")
            if e.resp.status == 404:
                print("   💡 Make sure the calendar is public and the email address is correct")
            elif e.resp.status == 403:
                print("   💡 Make sure the calendar allows public access")
            return []
    
    def parse_tennis_events(self, events: List[Dict], date_str: str) -> Dict:
        """Parse tennis court events from Google Calendar events."""
        results = {
            'date': date_str,
            'total_events': len(events),
            'tennis_events': [],
            'available_courts': [],
            'unavailable_courts': []
        }
        
        for event in events:
            summary = event.get('summary', '')
            description = event.get('description', '')
            start_time = event.get('start', {})
            end_time = event.get('end', {})
            
            # Extract time information
            start_datetime = None
            end_datetime = None
            
            if 'dateTime' in start_time:
                start_datetime = datetime.fromisoformat(start_time['dateTime'].replace('Z', '+00:00'))
            elif 'date' in start_time:
                start_datetime = datetime.strptime(start_time['date'], '%Y-%m-%d')
            
            if 'dateTime' in end_time:
                end_datetime = datetime.fromisoformat(end_time['dateTime'].replace('Z', '+00:00'))
            elif 'date' in end_time:
                end_datetime = datetime.strptime(end_time['date'], '%Y-%m-%d')
            
            event_data = {
                'title': summary,
                'description': description,
                'start_time': start_datetime,
                'end_time': end_datetime,
                'location': event.get('location', ''),
                'status': event.get('status', 'confirmed')
            }
            
            # Extract court numbers from event title (e.g., "Cts:3,4,5" or "Court 1,2")
            court_numbers = self.extract_court_numbers(summary)
            event_data['court_numbers'] = court_numbers
            
            # All events are tennis events since this is a tennis calendar
            results['tennis_events'].append(event_data)
            
            # Determine if court is available or unavailable
            # If event has a title like "USTA CW6.5A DT (TM) Cts:3,4,5", it means courts are booked
            if any(keyword in summary.lower() for keyword in ['available', 'open', 'free']):
                results['available_courts'].append(event_data)
            else:
                # Events with court numbers in the title are typically bookings/reservations
                results['unavailable_courts'].append(event_data)
        
        return results
    
    def extract_court_numbers(self, event_title: str) -> List[int]:
        """Extract court numbers from event title.
        
        Examples:
        - "USTA CW6.5A DT (TM) Cts:3,4,5" -> [3, 4, 5]
        - "Court 1,2" -> [1, 2]
        - "Courts 1-3" -> [1, 2, 3]
        - "Court 5" -> [5]
        """
        court_numbers = []
        
        # Pattern 1: "Cts:3,4,5" or "Courts:1,2,3"
        cts_pattern = r'[Cc]ts?:\s*(\d+(?:,\d+)*)'
        match = re.search(cts_pattern, event_title)
        if match:
            numbers_str = match.group(1)
            court_numbers = [int(x.strip()) for x in numbers_str.split(',')]
            return court_numbers
        
        # Pattern 2: "Court 1,2" or "Courts 1,2,3"
        court_pattern = r'[Cc]ourts?\s+(\d+(?:,\d+)*)'
        match = re.search(court_pattern, event_title)
        if match:
            numbers_str = match.group(1)
            court_numbers = [int(x.strip()) for x in numbers_str.split(',')]
            return court_numbers
        
        # Pattern 3: "Courts 1-3" or "Court 1-5"
        range_pattern = r'[Cc]ourts?\s+(\d+)-(\d+)'
        match = re.search(range_pattern, event_title)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            court_numbers = list(range(start, end + 1))
            return court_numbers
        
        # Pattern 4: Single court "Court 5" or just "5"
        single_pattern = r'(?:[Cc]ourt\s+)?(\d+)(?:\s|$)'
        matches = re.findall(single_pattern, event_title)
        if matches:
            court_numbers = [int(x) for x in matches]
            return court_numbers
        
        return court_numbers
    
    def create_event(self, calendar_id: str, event_data: Dict, dry_run: bool = False) -> Optional[str]:
        """Create a calendar event for a tennis court booking."""
        if not self.service:
            return None
        
        # Parse time slot (e.g., "8:00 am - 9:00 am")
        time_match = re.match(r'(\d{1,2}:\d{2}\s*(?:am|pm))\s*-\s*(\d{1,2}:\d{2}\s*(?:am|pm))', event_data['time_slot'])
        if not time_match:
            print(f"⚠️  Could not parse time slot: {event_data['time_slot']}")
            return None
        
        start_time_str, end_time_str = time_match.groups()
        
        # Convert to datetime
        event_date = datetime.strptime(event_data['date'], "%Y-%m-%d")
        start_time = datetime.strptime(f"{event_date.strftime('%Y-%m-%d')} {start_time_str}", "%Y-%m-%d %I:%M %p")
        end_time = datetime.strptime(f"{event_date.strftime('%Y-%m-%d')} {end_time_str}", "%Y-%m-%d %I:%M %p")
        
        # Create event
        event = {
            'summary': f"Tennis Court: {event_data['court_name']}",
            'description': f"Court: {event_data['court_name']}\nLocation: {event_data.get('location', 'N/A')}\nStatus: Available\nSource: {event_data.get('source', 'WebTrac')}",
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'America/Los_Angeles',
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'America/Los_Angeles',
            },
            'colorId': '2',  # Green for available
            'transparency': 'transparent',  # Free time
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 30},
                    {'method': 'email', 'minutes': 60}
                ]
            }
        }
        
        if dry_run:
            print(f"🔍 [DRY RUN] Would create event: {event['summary']} at {start_time_str}")
            return "dry_run_event_id"
        
        try:
            created_event = self.service.events().insert(
                calendarId=calendar_id,
                body=event
            ).execute()
            
            print(f"✅ Created event: {event['summary']} at {start_time_str}")
            return created_event['id']
        except HttpError as e:
            print(f"❌ Failed to create event: {e}")
            return None
    
    def process_schedule_data(self, schedule_data: List[Dict], date_str: str, calendar_id: str, dry_run: bool = False) -> Dict:
        """Process schedule data and create calendar events."""
        results = {
            'total_courts': len(schedule_data),
            'total_available_slots': 0,
            'total_unavailable_slots': 0,
            'events_created': 0,
            'events_failed': 0,
            'errors': []
        }
        
        for court in schedule_data:
            court_name = court.get('label', 'Unknown Court')
            location = court.get('location', 'N/A')
            available_slots = court.get('available_slots', [])
            unavailable_slots = court.get('unavailable_slots', [])
            
            results['total_available_slots'] += len(available_slots)
            results['total_unavailable_slots'] += len(unavailable_slots)
            
            # Create events for available slots
            for time_slot in available_slots:
                event_data = {
                    'court_name': court_name,
                    'location': location,
                    'time_slot': time_slot,
                    'date': date_str,
                    'source': court.get('source', 'WebTrac')
                }
                
                event_id = self.create_event(calendar_id, event_data, dry_run)
                if event_id:
                    results['events_created'] += 1
                else:
                    results['events_failed'] += 1
                    results['errors'].append(f"Failed to create event for {court_name} at {time_slot}")
        
        return results


def get_week_dates(start_date: str) -> List[str]:
    """Get all dates in a week starting from the given date."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    dates = []
    for i in range(7):
        date_obj = start + timedelta(days=i)
        dates.append(date_obj.strftime("%Y-%m-%d"))
    return dates


def main():
    parser = argparse.ArgumentParser(
        description="Fetch tennis court schedules from public Google Calendars",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python google_calendar_integration.py --date 2025-10-09 --public-calendar "city@example.com"
  python google_calendar_integration.py --week 2025-10-09 --public-calendar "city@example.com"
  python google_calendar_integration.py --list-calendars
  python google_calendar_integration.py --date 2025-10-09 --public-calendar "city@example.com" --output-format json
        """
    )
    
    parser.add_argument("--date", help="Specific date in YYYY-MM-DD format")
    parser.add_argument("--week", help="Start date of week in YYYY-MM-DD format")
    parser.add_argument("--public-calendar", help="Email address of public Google Calendar to fetch from")
    parser.add_argument("--list-calendars", action="store_true", help="List available calendars")
    parser.add_argument("--out", default="-", help="Output JSON path (default stdout)")
    parser.add_argument("--credentials", default="credentials.json", help="Google API credentials file")
    parser.add_argument("--token", default="token.json", help="Google API token file")
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.date and not args.week and not args.list_calendars:
        print("❌ Must specify --date, --week, or --list-calendars")
        return 1
    
    if args.date and args.week:
        print("❌ Cannot specify both --date and --week")
        return 1
    
    if (args.date or args.week) and not args.public_calendar:
        print("❌ Must specify --public-calendar when fetching events")
        return 1
    
    # Initialize Google Calendar integration
    if not args.list_calendars:
        if not GOOGLE_CALENDAR_AVAILABLE:
            print("❌ Google Calendar API not available")
            return 1
        
        gcal = GoogleCalendarIntegration(args.credentials, args.token)
        if not gcal.authenticate():
            return 1
    
    # List calendars if requested
    if args.list_calendars:
        gcal = GoogleCalendarIntegration(args.credentials, args.token)
        if not gcal.authenticate():
            return 1
        
        calendars = gcal.list_calendars()
        print(f"\n📅 Available Calendars:")
        for cal in calendars:
            primary_marker = " (PRIMARY)" if cal['primary'] else ""
            print(f"   {cal['id']} - {cal['summary']}{primary_marker}")
            if cal['description']:
                print(f"      {cal['description']}")
        return 0
    
    # Determine dates to process
    if args.date:
        dates = [args.date]
    else:  # args.week
        dates = get_week_dates(args.week)
    
    print(f"📅 Processing {len(dates)} date(s): {', '.join(dates)}")
    print(f"📧 Public Calendar: {args.public_calendar}")
    
    # Initialize Google Calendar integration
    gcal = GoogleCalendarIntegration(args.credentials, args.token)
    if not gcal.authenticate():
        return 1
    
    # Process each date
    all_results = []
    
    for date_str in dates:
        print(f"\n📅 Fetching events for {date_str}...")
        
        # Fetch events from public calendar
        events = gcal.fetch_public_calendar_events(args.public_calendar, date_str)
        
        if not events:
            print(f"   ⚠️  No events found for {date_str}")
            continue
        
        # Parse tennis events
        parsed_results = gcal.parse_tennis_events(events, date_str)
        all_results.append(parsed_results)
        
        # Display results
        if args.output_format == 'json':
            print(json.dumps(parsed_results, indent=2, default=str))
        else:
            print(f"   📊 {date_str}: {parsed_results['total_events']} events")
            print(f"   🟢 Available courts: {len(parsed_results['available_courts'])}")
            print(f"   🔴 Unavailable courts: {len(parsed_results['unavailable_courts'])}")
            
            # Show tennis events details
            if parsed_results['tennis_events']:
                print(f"   🎾 Tennis Court Schedule:")
                for event in parsed_results['tennis_events']:
                    start_time = event['start_time'].strftime('%H:%M') if event['start_time'] else 'N/A'
                    end_time = event['end_time'].strftime('%H:%M') if event['end_time'] else 'N/A'
                    status_emoji = "🟢" if event in parsed_results['available_courts'] else "🔴"
                    
                    # Show court numbers if available
                    court_info = ""
                    if event.get('court_numbers'):
                        courts_str = ",".join(map(str, event['court_numbers']))
                        court_info = f" (Courts: {courts_str})"
                    
                    print(f"      {status_emoji} {start_time}-{end_time}: {event['title']}{court_info}")
                    if event['location']:
                        print(f"         📍 {event['location']}")
    
    # Print final summary
    if args.output_format != 'json':
        print(f"\n📊 Final Summary:")
        total_events = sum(r['total_events'] for r in all_results)
        total_available = sum(len(r['available_courts']) for r in all_results)
        total_unavailable = sum(len(r['unavailable_courts']) for r in all_results)
        
        print(f"   📅 Dates processed: {len(all_results)}")
        print(f"   📋 Total events: {total_events}")
        print(f"   🟢 Available courts: {total_available}")
        print(f"   🔴 Unavailable courts: {total_unavailable}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
