# TennisNow - Tennis Court Schedule Scraper

A comprehensive system for scraping tennis court availability from various booking platforms.

## Overview

This project provides tools to scrape tennis court schedules from different booking systems, including:

- **Xplore Recreation** - Used by many cities for facility booking
- **Facilitron** - Another common booking platform
- **Google Calendar** - For public calendar subscriptions

## Xplore Recreation Site Scraping

The Xplore Recreation system is used by many cities for tennis court bookings. This system provides three levels of scraping granularity.

### Architecture

The Xplore scraping system consists of two main scripts:

1. **`facility_schedule_fetcher.py`** - Standalone facility scraper (no config required)
   - **Use when**: You have specific facility parameters and want to test them directly
   - **Requires**: ALL parameters via command line arguments
   - **Does NOT**: Read from configuration files

2. **`config_schedule_scraper.py`** - Multi-level config-based scraper
   - **Use when**: You want to scrape multiple facilities using the configuration
   - **Supports**: State, city, or facility-level scraping
   - **Reads from**: `facilities_config.json`
   - **Internally uses**: `facility_schedule_fetcher.py` via subprocess calls

### Configuration Structure

The system uses a hierarchical configuration file (`facilities_config.json`):

```json
{
  "states": [
    {
      "state": "CA",
      "cities": [
        {
          "name": "Menlo Park",
          "base_url": "https://cityofmenlopark.perfectmind.com",
          "api_path": "/26116/Clients/BookMe4LandingPages/FacilityAvailability",
          "facility_page_path": "/26116/Clients/BookMe4LandingPages/Facility",
          "facilities": [
            {
              "name": "Burgess Park - Tennis Court #1",
              "address": "701 Laurel St., Menlo Park, CA",
              "facility_id": "aa931648-bf9a-4519-9ade-652246c770ef",
              "widget_id": "286f9a84-b14e-434e-acd2-cb2016c8a3cd",
              "calendar_id": "cd918767-63df-4159-972b-56a7bea51bd1",
              "service_id": "819f1be6-6add-4c70-b3fd-b5c71f5e38a3",
              "duration_ids": [
                "a389d9e6-db77-4ea9-a8cd-38ab06957e85",
                "b695197c-68ec-4979-915b-391ce1772664"
              ],
              "description": "Burgess Park has two lighted tennis courts...",
              "contact": "(650) 330-2220",
              "hours": "8:00 AM - 10:00 PM daily",
              "features": ["Lights", "Check in/out"],
              "amenities": ["Lights"]
            }
          ]
        }
      ]
    }
  ],
  "default_settings": {
    "duration": 60,
    "duration_ids": ["default", "ids", "here"],
    "fee_type": 0
  }
}
```

### Usage Examples

**Important:** The `facility_schedule_fetcher.py` script requires ALL parameters to be provided via command line - it does NOT read from the configuration file. This is useful when you have specific facility parameters and want to test them directly.

#### 1. List Available Options

```bash
# List all available states, cities, and facilities
python crawler/Xplor/config_schedule_scraper.py --list
```

#### 2. State-Level Scraping

```bash
# Scrape all facilities in all states
python crawler/Xplor/config_schedule_scraper.py --level state --date 2025-10-13 --days 1

# Scrape all facilities in a specific state
python crawler/Xplor/config_schedule_scraper.py --level state --state "CA" --date 2025-10-13 --days 1
```

#### 3. City-Level Scraping

```bash
# Scrape all facilities in a specific city
python crawler/Xplor/config_schedule_scraper.py --level city --city "Menlo Park" --date 2025-10-13 --days 1 --output-dir results/menlo_park
```

#### 4. Facility-Level Scraping

```bash
# Scrape a specific facility using config
python crawler/Xplor/config_schedule_scraper.py --level facility --facility "Willow Oaks Park - Tennis Court #4" --date 2025-10-13 --days 1

# Scrape a specific facility directly (no config needed - ALL parameters required)
python crawler/Xplor/facility_schedule_fetcher.py \
  --base-url "https://cityofmenlopark.perfectmind.com" \
  --api-path "/26116/Clients/BookMe4LandingPages/FacilityAvailability" \
  --facility-page-path "/26116/Clients/BookMe4LandingPages/Facility" \
  --facility-id "f7ab9c6c-6555-488e-9e58-c7c391821631" \
  --widget-id "286f9a84-b14e-434e-acd2-cb2016c8a3cd" \
  --calendar-id "cd918767-63df-4159-972b-56a7bea51bd1" \
  --service-id "819f1be6-6add-4c70-b3fd-b5c71f5e38a3" \
  --duration-ids "c45b0f26-9b78-48fd-8007-6d2e73584d7b,4737abc7-6ddf-46b9-a5b9-a9f2e8111606,1ef18208-33b9-4954-8757-b35593285010,d12518eb-b714-4db5-9def-eaa666cc4812" \
  --date 2025-10-13 --days 1 \
  --output results/willow_oaks_court4.json
```

### Adding New Facilities

To add a new facility to the configuration:

1. **Find the facility parameters** by visiting the facility's booking page
2. **Extract the required IDs** from the page source or network requests
3. **Add to the configuration** under the appropriate city

#### Required Parameters

Each facility needs these parameters:

- `facility_id` - Unique identifier for the facility
- `widget_id` - Widget identifier (usually same for all facilities in a city)
- `calendar_id` - Calendar identifier (usually same for all facilities in a city)
- `service_id` - Service identifier (usually same for all facilities in a city)
- `duration_ids` - Array of duration IDs specific to each facility

#### Finding Parameters

1. **Visit the facility booking page**
2. **Open browser developer tools** (F12)
3. **Go to Network tab**
4. **Select a date** to trigger an API request
5. **Find the POST request** to `FacilityAvailability`
6. **Extract parameters** from the request payload

### Output Format

The scrapers generate JSON files with the following structure:

```json
{
  "facility_id": "f7ab9c6c-6555-488e-9e58-c7c391821631",
  "facility_page_url": "https://cityofmenlopark.perfectmind.com/26116/Clients/BookMe4LandingPages/Facility?facilityId=...",
  "schedule_data": [
    {
      "date": "/Date(1760313600000)/",
      "availabilities": [
        {
          "Date": "/Date(1760313600000)/",
          "BookingGroups": [
            {
              "Name": "Morning",
              "Order": 0,
              "AvailableSpots": [
                {
                  "Ticks": 638959392000000000,
                  "Time": {
                    "Hours": 8,
                    "Minutes": 0,
                    "Seconds": 0
                  },
                  "Duration": {
                    "Hours": 1,
                    "Minutes": 0,
                    "Seconds": 0
                  },
                  "IsDisabled": false,
                  "Title": "Available"
                }
              ]
            }
          ]
        }
      ]
    }
  ],
  "fetched_at": "2025-01-15T10:30:00.000Z"
}
```

### Troubleshooting

#### Common Issues

1. **"Facility not found"** - Check facility name spelling and case
2. **"No availability slots"** - Verify duration IDs are correct for the facility
3. **"Anti-forgery token error"** - The system automatically fetches fresh tokens
4. **"HTTP 500 error"** - Check that all required parameters are provided

#### Debug Mode

Add `--debug` flag to see detailed request/response information:

```bash
python crawler/Xplor/facility_schedule_fetcher.py --debug --base-url "..." --facility-id "..." --date 2025-10-13
```

### Current Supported Facilities

#### Menlo Park, CA
- Burgess Park - Tennis Court #1
- Kelly Park - Tennis Court #1  
- Nealon Park - Tennis Court #1
- Nealon Park - Tennis Court #2
- Willow Oaks Park - Tennis Court #3
- Willow Oaks Park - Tennis Court #4

## Other Booking Systems

### Facilitron

For Facilitron-based booking systems:

```bash
python crawler/Facilitron/facilitron_agenda_analyzer.py --date 2025-10-13 --month --output results/facilitron.json
```

### Google Calendar

For public Google Calendar subscriptions:

```bash
python crawler/gCalendar/google_calendar_integration.py --public-calendar "tennis@city.com" --date 2025-10-13 --output results/google_cal.json
```

## Project Structure

```
TennisNow/
├── README.md                           # This file
├── crawler/
│   ├── Xplor/                          # Xplore Recreation scrapers
│   │   ├── facility_schedule_fetcher.py    # Standalone facility scraper
│   │   ├── config_schedule_scraper.py      # Multi-level config scraper
│   │   └── facilities_config.json          # Configuration file
│   ├── Facilitron/                     # Facilitron scrapers
│   │   └── facilitron_agenda_analyzer.py
│   ├── gCalendar/                      # Google Calendar scrapers
│   │   ├── google_calendar_integration.py
│   │   └── setup_google_calendar.py
│   └── WebTrac/                        # WebTrac scrapers
│       └── fetch_schedule.py
└── server/
    └── app.py                          # Web server
```

## Contributing

When adding new facilities or cities:

1. **Test with facility_schedule_fetcher.py** first to verify parameters
2. **Add to facilities_config.json** with proper structure
3. **Test with config_schedule_scraper.py** to ensure it works
4. **Update this README** with new facilities

## License

This project is for educational and personal use. Please respect the terms of service of the booking platforms you're scraping.
