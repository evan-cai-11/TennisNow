#!/usr/bin/env python3
"""
fetch_all_cities.py

Wrapper script that fetches tennis court schedules for all cities configured in config_webtrac.json.
Each city's results are saved in timestamped folders under crawler/tmp/.

Usage:
  python fetch_all_cities.py --date 2025-10-09
  python fetch_all_cities.py --date 2025-10-09 --cities burlingame,albany
  python fetch_all_cities.py --date 2025-10-09 --use_browser --headful
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict

# Add the current directory to Python path to import fetch_schedule
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetch_schedule import fetch_schedule


def load_config() -> Dict:
    """Load the WebTrac configuration file."""
    config_path = os.path.join(os.path.dirname(__file__), "config_webtrac.json")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_available_cities(config: Dict) -> List[str]:
    """Get list of available cities from config."""
    webtrac_config = config.get("WebTrac", {})
    return list(webtrac_config.keys())


def create_output_directory(base_dir: str, city: str, timestamp: str) -> str:
    """Create timestamped output directory for a city."""
    city_dir = os.path.join(base_dir, f"{city}_{timestamp}")
    os.makedirs(city_dir, exist_ok=True)
    return city_dir


def fetch_city_schedule(
    city: str,
    date_ymd: str,
    output_dir: str,
    use_browser: bool = False,
    headful: bool = False,
    debug_browser: bool = False,
    screenshot_dir: str = None
) -> Dict:
    """Fetch schedule for a single city and save results."""
    print(f"\n🏙️  Fetching schedule for {city}...")
    
    # Map city names to query modes
    city_to_mode = {
        "Burlingame": "burlingame",
        "San Mateo": "san_mateo", 
        "Albany": "albany"
    }
    query_mode = city_to_mode.get(city, city.lower())
    
    try:
        # Fetch the schedule data
        schedules = fetch_schedule(
            date_ymd=date_ymd,
            use_browser=use_browser,
            headful=headful,
            debug_browser=debug_browser,
            screenshot_dir=screenshot_dir,
            query_mode=query_mode
        )
        
        # Save results to JSON file
        output_file = os.path.join(output_dir, f"{city.lower().replace(' ', '_')}_schedule.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(schedules, f, ensure_ascii=False, indent=2)
        
        # Save summary
        summary = {
            "city": city,
            "date": date_ymd,
            "query_mode": query_mode,
            "total_courts": len(schedules),
            "total_available_slots": sum(len(court.get("available_slots", [])) for court in schedules),
            "total_unavailable_slots": sum(len(court.get("unavailable_slots", [])) for court in schedules),
            "courts": [
                {
                    "fmid": court.get("fmid"),
                    "label": court.get("label"),
                    "location": court.get("location"),
                    "available_count": len(court.get("available_slots", [])),
                    "unavailable_count": len(court.get("unavailable_slots", []))
                }
                for court in schedules
            ]
        }
        
        summary_file = os.path.join(output_dir, f"{city.lower().replace(' ', '_')}_summary.json")
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        print(f"✅ {city}: {len(schedules)} courts, {summary['total_available_slots']} available slots")
        return {
            "city": city,
            "status": "success",
            "courts_count": len(schedules),
            "available_slots": summary["total_available_slots"],
            "unavailable_slots": summary["total_unavailable_slots"],
            "output_file": output_file,
            "summary_file": summary_file
        }
        
    except Exception as e:
        error_msg = f"❌ {city}: Failed - {str(e)}"
        print(error_msg)
        
        # Save error details
        error_file = os.path.join(output_dir, f"{city.lower().replace(' ', '_')}_error.json")
        error_data = {
            "city": city,
            "date": date_ymd,
            "query_mode": query_mode,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
        with open(error_file, "w", encoding="utf-8") as f:
            json.dump(error_data, f, ensure_ascii=False, indent=2)
        
        return {
            "city": city,
            "status": "error",
            "error": str(e),
            "error_file": error_file
        }


def main():
    parser = argparse.ArgumentParser(
        description="Fetch tennis court schedules for all configured cities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fetch_all_cities.py --date 2025-10-09
  python fetch_all_cities.py --date 2025-10-09 --cities burlingame,albany
  python fetch_all_cities.py --date 2025-10-09 --use_browser --headful
  python fetch_all_cities.py --date 2025-10-09 --debug_browser --screenshot_dir /tmp/debug
        """
    )
    
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD format")
    parser.add_argument("--cities", help="Comma-separated list of cities to fetch (default: all)")
    parser.add_argument("--use_browser", action="store_true", help="Use browser automation (Playwright)")
    parser.add_argument("--headful", action="store_true", help="Show browser window (requires --use_browser)")
    parser.add_argument("--debug_browser", action="store_true", help="Enable browser debugging")
    parser.add_argument("--screenshot_dir", help="Directory for browser screenshots")
    parser.add_argument("--tmp_dir", default="tmp", help="Base directory for temporary files (default: tmp)")
    
    args = parser.parse_args()
    
    # Load configuration
    try:
        config = load_config()
    except Exception as e:
        print(f"❌ Failed to load config: {e}")
        return 1
    
    # Get available cities
    available_cities = get_available_cities(config)
    if not available_cities:
        print("❌ No cities found in configuration")
        return 1
    
    # Determine which cities to process (default to Foster City only)
    if args.cities:
        requested_cities = [city.strip() for city in args.cities.split(",")]
        cities_to_process = []
        for city in requested_cities:
            # Try to match city name (case insensitive)
            matched = None
            for available_city in available_cities:
                if city.lower() == available_city.lower() or city.lower() in available_city.lower():
                    matched = available_city
                    break
            if matched:
                cities_to_process.append(matched)
            else:
                print(f"⚠️  City '{city}' not found in config. Available: {', '.join(available_cities)}")
    else:
        # Default to Foster City only
        cities_to_process = ["Foster City"] if "Foster City" in available_cities else available_cities
    
    if not cities_to_process:
        print("❌ No valid cities to process")
        return 1
    
    # Create base output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_output_dir = os.path.join(os.path.dirname(__file__), "..", args.tmp_dir)
    os.makedirs(base_output_dir, exist_ok=True)
    
    print(f"🚀 Starting fetch for {len(cities_to_process)} cities on {args.date}")
    print(f"📁 Output directory: {base_output_dir}")
    print(f"🏙️  Cities: {', '.join(cities_to_process)}")
    
    # Process each city
    results = []
    for city in cities_to_process:
        # Create city-specific output directory
        city_output_dir = create_output_directory(base_output_dir, city.lower().replace(" ", "_"), timestamp)
        
        # Set up screenshot directory if requested
        screenshot_dir = None
        if args.screenshot_dir or args.debug_browser:
            screenshot_dir = os.path.join(city_output_dir, "screenshots")
            os.makedirs(screenshot_dir, exist_ok=True)
        elif args.screenshot_dir:
            screenshot_dir = args.screenshot_dir
        
        # Fetch schedule for this city
        result = fetch_city_schedule(
            city=city,
            date_ymd=args.date,
            output_dir=city_output_dir,
            use_browser=args.use_browser,
            headful=args.headful,
            debug_browser=args.debug_browser,
            screenshot_dir=screenshot_dir
        )
        results.append(result)
    
    # Generate overall summary
    successful_cities = [r for r in results if r["status"] == "success"]
    failed_cities = [r for r in results if r["status"] == "error"]
    
    overall_summary = {
        "date": args.date,
        "timestamp": timestamp,
        "total_cities": len(cities_to_process),
        "successful_cities": len(successful_cities),
        "failed_cities": len(failed_cities),
        "total_courts": sum(r.get("courts_count", 0) for r in successful_cities),
        "total_available_slots": sum(r.get("available_slots", 0) for r in successful_cities),
        "total_unavailable_slots": sum(r.get("unavailable_slots", 0) for r in successful_cities),
        "results": results
    }
    
    # Save overall summary
    summary_file = os.path.join(base_output_dir, f"overall_summary_{timestamp}.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(overall_summary, f, ensure_ascii=False, indent=2)
    
    # Print final summary
    print(f"\n📊 Final Summary:")
    print(f"   ✅ Successful: {len(successful_cities)}/{len(cities_to_process)} cities")
    print(f"   ❌ Failed: {len(failed_cities)} cities")
    if successful_cities:
        print(f"   🏟️  Total courts: {overall_summary['total_courts']}")
        print(f"   🟢 Available slots: {overall_summary['total_available_slots']}")
        print(f"   🔴 Unavailable slots: {overall_summary['total_unavailable_slots']}")
    print(f"   📁 Results saved to: {base_output_dir}")
    print(f"   📋 Summary: {summary_file}")
    
    if failed_cities:
        print(f"\n❌ Failed cities:")
        for result in failed_cities:
            print(f"   - {result['city']}: {result['error']}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
