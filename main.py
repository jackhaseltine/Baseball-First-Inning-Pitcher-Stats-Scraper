import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import os
import time

def extract_player_id_from_url(url):
    """Extract the player ID from a Baseball Savant URL."""
    match = re.search(r'/savant-player/([^?]+)', url)
    if match:
        return match.group(1)
    return None

def modify_url_for_splits(url, year):
    """Modify URL to access the splits page for a specific year."""
    player_id = extract_player_id_from_url(url)
    if not player_id:
        return None
    return f"https://baseballsavant.mlb.com/savant-player/{player_id}?stats=splits-r-pitching-mlb&season={year}"

# Modified to accept a session object
def get_pitching_stats(session, url, year=None):
    """Scrape pitching stats from a Baseball Savant URL using a session."""
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Failed to retrieve data from {url}: {e}")
        return None
    
    soup = BeautifulSoup(response.text, 'html.parser')
    stats_div = soup.find('div', id='statcast_stats_pitching')
    
    if not stats_div:
        print(f"Could not find the div with ID 'statcast_stats_pitching' for URL: {url}")
        return None
    
    table = stats_div.find('table')
    if not table:
        print(f"Could not find a table within the specified div for URL: {url}")
        return None
    
    rows = table.find_all('tr')
    data = []
    mlb_data = {}
    
    for row in rows[1:]:
        cells = row.find_all('td')
        if cells:
            year_cell = cells[0].text.strip()
            k_percent = cells[17].text.strip() if len(cells) > 17 else "N/A"
            bb_percent = cells[18].text.strip() if len(cells) > 18 else "N/A"
            
            if year_cell == "MLB":
                mlb_data = {"Year": year_cell, "K%": k_percent, "BB%": bb_percent}
            
            data.append({"Year": year_cell, "K%": k_percent, "BB%": bb_percent})
    
    df = pd.DataFrame(data)
    
    if year is not None:
        year_str = str(year)
        filtered_data = df[df['Year'] == year_str]
        
        if filtered_data.empty:
            print(f"No data found for year {year_str} in URL: {url}")
            return None
        
        return {
            "Year": year_str,
            "K%": filtered_data.iloc[0]['K%'],
            "BB%": filtered_data.iloc[0]['BB%'],
            "MLB_K%": mlb_data.get("K%", "N/A"),
            "MLB_BB%": mlb_data.get("BB%", "N/A")
        }
    return df

# Modified to accept a session object
def get_inning_splits(session, url, year):
    """Get the 1st inning ERA and WHIP from the splits page using a session."""
    splits_url = modify_url_for_splits(url, year)
    if not splits_url:
        print(f"Failed to create splits URL for original URL: {url}")
        return None
        
    try:
        # The session already has cookies from the previous request
        response = session.get(splits_url, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Failed to retrieve splits data from {splits_url}: {e}")
        return None
        
    soup = BeautifulSoup(response.text, 'html.parser')
    first_inning_row = soup.find('tr', id='mlb_inningSplits-tr_0')
    
    if not first_inning_row:
        print(f"Could not find the 1st inning data row in {splits_url}")
        return None
    
    cells = first_inning_row.find_all('td')
    if len(cells) < 18:
        print(f"Not enough cells in the 1st inning row (found {len(cells)}, expected at least 18) in {splits_url}")
        return None
    
    era = cells[5].text.strip()
    whip = cells[17].text.strip()
    
    return {"1st_Inning_ERA": era, "1st_Inning_WHIP": whip}

def analyze_pitcher(url, year):
    """Analyze a single pitcher using a session to handle cookies."""
    player_id_match = extract_player_id_from_url(url)
    player_name = ' '.join(part.title() for part in player_id_match.split('-')[:-1]) if player_id_match else "Unknown Player"
    
    # Create a session for this pitcher
    with requests.Session() as session:
        # Set the browser-like headers for the entire session
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        })

        # Make the first request to the main page to get cookies
        year_stats = get_pitching_stats(session, url, year)
        if year_stats is None:
            return None
        
        # Make the second request to the splits page; the session will automatically use the cookies
        inning_splits = get_inning_splits(session, url, year)
        if inning_splits is None:
            return None
    
    return {
        "player_name": player_name,
        "year": year,
        "k_percent": year_stats.get('K%'),
        "bb_percent": year_stats.get('BB%'),
        "first_inning_era": inning_splits.get('1st_Inning_ERA'),
        "first_inning_whip": inning_splits.get('1st_Inning_WHIP'),
    }

def create_pitcher_report(pitcher_urls, year, pause_duration):
    """Creates a report for a list of pitchers, pausing between each."""
    all_pitcher_data = []
    
    for i, url in enumerate(pitcher_urls):
        if not url.startswith("http"):
            print(f"Skipping invalid URL: {url}")
            continue

        print(f"\n({i+1}/{len(pitcher_urls)}) Analyzing pitcher from URL: {url}")
        pitcher_data = analyze_pitcher(url, year)
        if pitcher_data:
            all_pitcher_data.append(pitcher_data)
        
        if i < len(pitcher_urls) - 1:
            print(f"Pausing for {pause_duration} seconds...")
            time.sleep(pause_duration)

    return pd.DataFrame(all_pitcher_data)

def load_urls_from_file(filename):
    """Loads a list of URLs from a text file."""
    if not os.path.exists(filename):
        print(f"Error: Input file '{filename}' not found.")
        return None
        
    with open(filename, 'r') as f:
        urls = [line.strip() for line in f if line.strip()]
    return urls

if __name__ == "__main__":
    # --- Configuration ---
    YEAR_TO_ANALYZE = 2025
    INPUT_TXT_FILE = "pitchers.txt"
    OUTPUT_CSV_FILE = "pitcher_report.csv"
    PAUSE_BETWEEN_REQUESTS = 2
    # --- End Configuration ---

    PITCHER_URLS = load_urls_from_file(INPUT_TXT_FILE)
    
    if PITCHER_URLS:
        print(f"\nFound {len(PITCHER_URLS)} pitcher(s) in '{INPUT_TXT_FILE}'.")
        print(f"Starting analysis for the year {YEAR_TO_ANALYZE}...")
        
        pitcher_report_df = create_pitcher_report(PITCHER_URLS, YEAR_TO_ANALYZE, PAUSE_BETWEEN_REQUESTS)

        if not pitcher_report_df.empty:
            pitcher_report_df.to_csv(OUTPUT_CSV_FILE, index=False)
            print(f"\nSuccessfully created pitcher report at: {OUTPUT_CSV_FILE}")
        else:
            print("\nNo data was processed, the CSV file was not created.")