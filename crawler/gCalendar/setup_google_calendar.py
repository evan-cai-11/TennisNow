#!/usr/bin/env python3
"""
setup_google_calendar.py

Setup script for Google Calendar API integration.
Helps users configure Google Calendar API access and create necessary credentials.

Usage:
  python setup_google_calendar.py
"""

import os
import sys
import json
from pathlib import Path

def print_setup_instructions():
    """Print detailed setup instructions for Google Calendar API."""
    print("🔧 Google Calendar API Setup Instructions")
    print("=" * 50)
    print()
    print("1. Go to Google Cloud Console:")
    print("   https://console.cloud.google.com/")
    print()
    print("2. Create a new project or select existing one")
    print()
    print("3. Enable Google Calendar API:")
    print("   - Go to 'APIs & Services' > 'Library'")
    print("   - Search for 'Google Calendar API'")
    print("   - Click 'Enable'")
    print()
    print("4. Create credentials:")
    print("   - Go to 'APIs & Services' > 'Credentials'")
    print("   - Click 'Create Credentials' > 'OAuth client ID'")
    print("   - Application type: 'Desktop application'")
    print("   - Name: 'Tennis Court Calendar Integration'")
    print("   - Click 'Create'")
    print()
    print("5. Download credentials:")
    print("   - Click the download button (⬇️) next to your OAuth client")
    print("   - Save as 'credentials.json' in this directory")
    print()
    print("6. Install required packages:")
    print("   pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
    print()
    print("7. Run the integration script:")
    print("   python google_calendar_integration.py --list-calendars")
    print()

def check_credentials_file():
    """Check if credentials file exists and is valid."""
    credentials_file = "credentials.json"
    
    if not os.path.exists(credentials_file):
        print(f"❌ Credentials file not found: {credentials_file}")
        return False
    
    try:
        with open(credentials_file, 'r') as f:
            creds = json.load(f)
        
        # Check if it's a valid OAuth2 credentials file
        if 'installed' in creds or 'web' in creds:
            print(f"✅ Credentials file found: {credentials_file}")
            return True
        else:
            print(f"❌ Invalid credentials file format: {credentials_file}")
            return False
    except json.JSONDecodeError:
        print(f"❌ Invalid JSON in credentials file: {credentials_file}")
        return False
    except Exception as e:
        print(f"❌ Error reading credentials file: {e}")
        return False

def check_dependencies():
    """Check if required Python packages are installed."""
    required_packages = [
        'google-api-python-client',
        'google-auth-httplib2', 
        'google-auth-oauthlib'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ Missing required packages: {', '.join(missing_packages)}")
        print("   Install with: pip install " + " ".join(missing_packages))
        return False
    else:
        print("✅ All required packages are installed")
        return True

def create_sample_config():
    """Create a sample configuration file."""
    config = {
        "google_calendar": {
            "default_calendar_id": "",
            "calendar_name": "Tennis Court Schedules",
            "calendar_description": "Automated tennis court schedule updates",
            "timezone": "America/Los_Angeles",
            "reminder_minutes": [30, 60],
            "event_color": "2"
        },
        "cities": {
            "burlingame": {
                "enabled": True,
                "query_mode": "burlingame"
            },
            "san_mateo": {
                "enabled": True, 
                "query_mode": "san_mateo"
            },
            "albany": {
                "enabled": True,
                "query_mode": "albany"
            }
        },
        "schedule": {
            "fetch_days_ahead": 7,
            "update_frequency_hours": 6,
            "use_browser": False
        }
    }
    
    config_file = "calendar_config.json"
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"✅ Created sample configuration: {config_file}")
    return config_file

def main():
    print("🚀 Google Calendar Integration Setup")
    print("=" * 40)
    print()
    
    # Check current directory
    current_dir = os.getcwd()
    print(f"📁 Working directory: {current_dir}")
    print()
    
    # Check dependencies
    print("🔍 Checking dependencies...")
    deps_ok = check_dependencies()
    print()
    
    # Check credentials
    print("🔍 Checking credentials...")
    creds_ok = check_credentials_file()
    print()
    
    if not deps_ok or not creds_ok:
        print("❌ Setup incomplete. Please follow the instructions below:")
        print()
        print_setup_instructions()
        return 1
    
    # Create sample config
    print("📝 Creating sample configuration...")
    config_file = create_sample_config()
    print()
    
    print("✅ Setup complete!")
    print()
    print("Next steps:")
    print("1. Review and edit calendar_config.json if needed")
    print("2. Test the integration:")
    print("   python google_calendar_integration.py --list-calendars")
    print("3. Create events for a specific date:")
    print("   python google_calendar_integration.py --date 2025-10-09 --create-calendar 'Tennis Courts'")
    print()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
