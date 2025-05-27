import requests
from bs4 import BeautifulSoup
import pandas as pd
import re

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

def get_pitching_stats(url, year=None):
    """
    Scrape pitching stats from a Baseball Savant URL.
    
    Args:
        url (str): The Baseball Savant player URL
        year (str or int, optional): The specific year to get stats for. If None, returns all years.
    
    Returns:
        If year is specified: A dictionary with K% and BB% for that year and MLB averages
        If year is not specified: A pandas DataFrame with all years and stats
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
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

def get_inning_splits(url, year):
    """Get the 1st inning ERA and WHIP from the splits page."""
    splits_url = modify_url_for_splits(url, year)
    if not splits_url:
        print(f"Failed to create splits URL for original URL: {url}")
        return None
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(splits_url, headers=headers, timeout=10)
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

def score_pitcher_stats(stats, inning_splits):
    """Score the pitcher's stats according to the rating system."""
    scores = {}
    
    try:
        k_percent = float(stats['K%'].replace("%", ""))
        mlb_k_percent = float(stats['MLB_K%'].replace("%", ""))
        if k_percent >= mlb_k_percent + 5: scores['K%_score'] = 2
        elif k_percent >= mlb_k_percent: scores['K%_score'] = 1
        elif k_percent >= mlb_k_percent - 5: scores['K%_score'] = -1
        else: scores['K%_score'] = -2
    except (ValueError, KeyError, AttributeError): scores['K%_score'] = 0
    
    try:
        bb_percent = float(stats['BB%'].replace("%", ""))
        mlb_bb_percent = float(stats['MLB_BB%'].replace("%", ""))
        if bb_percent <= mlb_bb_percent - 2: scores['BB%_score'] = 2
        elif bb_percent <= mlb_bb_percent: scores['BB%_score'] = 1
        elif bb_percent <= mlb_bb_percent + 2: scores['BB%_score'] = -1
        else: scores['BB%_score'] = -2
    except (ValueError, KeyError, AttributeError): scores['BB%_score'] = 0
    
    try:
        whip = float(inning_splits['1st_Inning_WHIP'])
        if whip < 1: scores['WHIP_score'] = 2
        elif whip < 1.1: scores['WHIP_score'] = 1
        elif whip < 1.25: scores['WHIP_score'] = -1
        else: scores['WHIP_score'] = -2
    except (ValueError, KeyError, AttributeError): scores['WHIP_score'] = 0
    
    try:
        era = float(inning_splits['1st_Inning_ERA'])
        if era < 3: scores['ERA_score'] = 2
        elif era < 3.5: scores['ERA_score'] = 1
        elif era < 4.5: scores['ERA_score'] = -1
        else: scores['ERA_score'] = -2
    except (ValueError, KeyError, AttributeError): scores['ERA_score'] = 0
    
    total_score = sum(s for s in scores.values() if isinstance(s, (int, float)))
    scores['total_score'] = total_score
    
    run_percentage = 50 - (total_score * 5) if total_score > 0 else 50 + (abs(total_score) * 5)
    scores['first_inning_run_percentage'] = max(10, min(90, run_percentage))
    
    return scores

def analyze_pitcher(url, year):
    """Analyze a single pitcher and return their stats and probability."""
    player_id_match = extract_player_id_from_url(url)
    player_name = ' '.join(part.title() for part in player_id_match.split('-')[:-1]) if player_id_match else "Unknown Player"
    
    year_stats = get_pitching_stats(url, year)
    if year_stats is None:
        print(f"Could not retrieve yearly stats for {player_name} ({year}) from URL: {url}")
        return None
    
    inning_splits = get_inning_splits(url, year)
    if inning_splits is None:
        print(f"Could not retrieve inning splits for {player_name} ({year}) from URL: {url}")
        return None
    
    scores = score_pitcher_stats(year_stats, inning_splits)
    
    return {
        "player_name": player_name,
        "year": year,
        "stats": year_stats,
        "inning_splits": inning_splits,
        "scores": scores
    }

def display_summary(pitcher_data_for_game):
    """Display a clean summary of pitcher stats for the game."""
    print("\n===== PLAYER STATISTICS SUMMARY =====")
    
    for i, pitcher in enumerate(pitcher_data_for_game, 1):
        if not pitcher: continue # Skip if pitcher data is None
        name = pitcher['player_name']
        year = pitcher['year']
        stats = pitcher['stats']
        inning_splits = pitcher['inning_splits']
        
        print(f"\nPITCHER {i}: {name} ({year})")
        print("-" * 40)
        
        try:
            k_val = float(stats['K%'].replace('%', ''))
            mlb_k_val = float(stats['MLB_K%'].replace('%', ''))
            k_diff = k_val - mlb_k_val
            k_comp = "above" if k_diff >= 0 else "below"
            print(f"Strikeout Rate (K%): {stats['K%']} ({abs(k_diff):.1f}% {k_comp} MLB avg)")
        except (ValueError, KeyError):
            print(f"Strikeout Rate (K%): {stats.get('K%', 'N/A')} (MLB avg: {stats.get('MLB_K%', 'N/A')})")

        try:
            bb_val = float(stats['BB%'].replace('%', ''))
            mlb_bb_val = float(stats['MLB_BB%'].replace('%', '')) # Corrected: MLB_BB%
            bb_diff = bb_val - mlb_bb_val
            bb_comp = "above" if bb_diff >= 0 else "below" # For BB%, lower is better, but comparison is direct
            print(f"Walk Rate (BB%): {stats['BB%']} ({abs(bb_diff):.1f}% {bb_comp} MLB avg)")
        except (ValueError, KeyError):
            print(f"Walk Rate (BB%): {stats.get('BB%', 'N/A')} (MLB avg: {stats.get('MLB_BB%', 'N/A')})")
            
        print(f"1st Inning ERA: {inning_splits.get('1st_Inning_ERA', 'N/A')}")
        print(f"1st Inning WHIP: {inning_splits.get('1st_Inning_WHIP', 'N/A')}")
        if 'scores' in pitcher and 'first_inning_run_percentage' in pitcher['scores']:
             print(f"Individual First Inning Run Likelihood: {pitcher['scores']['first_inning_run_percentage']:.1f}%")
    print("-" * 40)


def calculate_combined_probability(pitcher_data_for_game):
    """Calculates the combined probability of a YRFI based on two pitchers' scores."""
    if len(pitcher_data_for_game) != 2 or not all(p and 'scores' in p for p in pitcher_data_for_game):
        return None

    total_score = pitcher_data_for_game[0]['scores']['total_score'] + pitcher_data_for_game[1]['scores']['total_score']
    
    combined_prob = 40 - (total_score * 2.5) if total_score > 0 else 40 + (abs(total_score) * 2.5)
    return max(5, min(95, combined_prob))


def kelly_bet(yrfi_probability_percent):
    """Calculates Kelly Criterion bet sizing for YRFI and optionally NRFI."""
    if yrfi_probability_percent is None:
        print("Cannot calculate Kelly bet without YRFI probability.")
        return

    try:
        american_odds_yrfi = float(input("Enter American odds for YRFI (e.g., -150 or 120): "))
    except ValueError:
        print("Invalid YRFI odds input. Skipping Kelly Bet for YRFI.")
        return # Or decide to proceed to NRFI directly

    if american_odds_yrfi > 0:
        decimal_odds_yrfi = 1 + (american_odds_yrfi / 100)
    else:
        decimal_odds_yrfi = 1 + (100 / abs(american_odds_yrfi))
    
    try:
        bankroll = float(input("Enter your bankroll: "))
    except ValueError:
        print("Invalid bankroll input. Please enter a numerical value.")
        return
    
    model_yrfi_prob_decimal = yrfi_probability_percent / 100
    kelly_fraction_yrfi = (decimal_odds_yrfi * model_yrfi_prob_decimal - 1) / (decimal_odds_yrfi - 1)
    
    if kelly_fraction_yrfi <= 0:
        print("\nAccording to Kelly criterion, YRFI bet does not have a positive edge.")
        nrfi_choice = input("Would you like to evaluate NRFI odds? (y/n): ").strip().lower()
        if nrfi_choice == 'y':
            try:
                american_odds_nrfi = float(input("Enter American odds for NRFI: "))
            except ValueError:
                print("Invalid NRFI odds input. Skipping NRFI bet.")
                return

            if american_odds_nrfi > 0:
                decimal_odds_nrfi = 1 + (american_odds_nrfi / 100)
                implied_prob_nrfi_decimal = 100 / (american_odds_nrfi + 100)
            else:
                decimal_odds_nrfi = 1 + (100 / abs(american_odds_nrfi))
                implied_prob_nrfi_decimal = abs(american_odds_nrfi) / (abs(american_odds_nrfi) + 100)

            model_nrfi_prob_decimal = (100 - yrfi_probability_percent) / 100
            kelly_fraction_nrfi = (decimal_odds_nrfi * model_nrfi_prob_decimal - 1) / (decimal_odds_nrfi - 1)

            if kelly_fraction_nrfi <= 0:
                print("According to Kelly criterion, NRFI bet also does not have a positive edge. No bet recommended.")
            else:
                bet_amount_nrfi = kelly_fraction_nrfi * bankroll
                print(f"\n--- NRFI Bet Recommendation ---")
                print(f"Implied Probability of NRFI: {implied_prob_nrfi_decimal * 100:.2f}%")
                print(f"Your Model's Probability of NRFI: {model_nrfi_prob_decimal * 100:.2f}%")
                print(f"Kelly Fraction for NRFI: {kelly_fraction_nrfi * 100:.2f}%")
                print(f"Recommended Bet Amount for NRFI: ${bet_amount_nrfi:.2f}")
        else:
            print("No bet recommended.")
    else:
        bet_amount_yrfi = kelly_fraction_yrfi * bankroll
        if american_odds_yrfi > 0:
            implied_prob_yrfi_decimal = 100 / (american_odds_yrfi + 100)
        else:
            implied_prob_yrfi_decimal = abs(american_odds_yrfi) / (abs(american_odds_yrfi) + 100)

        print(f"\n--- YRFI Bet Recommendation ---")
        print(f"Implied Probability of YRFI: {implied_prob_yrfi_decimal * 100:.2f}%")
        print(f"Your Model's Probability of YRFI: {model_yrfi_prob_decimal * 100:.2f}%")
        print(f"Kelly Fraction for YRFI: {kelly_fraction_yrfi * 100:.2f}%")
        print(f"Recommended Bet Amount for YRFI: ${bet_amount_yrfi:.2f}")


def analyze_single_game():
    """Handles the analysis for a single game based on two pitcher URLs."""
    pitcher_data_for_game = []
    
    url1 = input("Enter the first pitcher's Baseball Savant URL: ")
    try:
        year = int(input("Enter the year to analyze: "))
        print(f"\nFetching data for Pitcher 1...\n")
        pitcher1 = analyze_pitcher(url1, year)
        if pitcher1:
            pitcher_data_for_game.append(pitcher1)
    except ValueError:
        print("Invalid year entered. Please enter a valid year (e.g., 2023).")
        return 
    
    url2 = input("\nEnter the second pitcher's Baseball Savant URL: ")
    print(f"\nFetching data for Pitcher 2...\n")
    pitcher2 = analyze_pitcher(url2, year) # Use same year
    if pitcher2:
        pitcher_data_for_game.append(pitcher2)
    
    if pitcher_data_for_game:
        display_summary(pitcher_data_for_game)
        
        if len(pitcher_data_for_game) == 2:
            yrfi_prob = calculate_combined_probability(pitcher_data_for_game)
            if yrfi_prob is not None:
                print("\n===== MATCHUP SUMMARY =====")
                print(f"Calculated Probability of a Run in the 1st Inning (YRFI): {yrfi_prob:.1f}%")
                print(f"Calculated Probability of No Run in the 1st Inning (NRFI): {(100 - yrfi_prob):.1f}%")
                kelly_bet(yrfi_prob)
            else:
                print("Could not calculate combined YRFI probability for Kelly bet.")
        else:
            print("\nData for only one pitcher available. Cannot calculate combined YRFI probability or Kelly Bet for the matchup.")
    else:
        print("\nNo pitcher data successfully processed.")


def analyze_multiple_games_sequentially(year_to_analyze):
    """Handles analysis for multiple games provided as a comma-separated URL string."""
    urls_string = input("Enter a comma-separated string of pitcher URLs (e.g., url_p1g1,url_p2g1,url_p1g2,url_p2g2,...):\n")
    all_urls = [url.strip() for url in urls_string.split(',') if url.strip()]

    if not all_urls:
        print("No URLs entered.")
        return

    if len(all_urls) % 2 != 0:
        print("Error: An even number of URLs is required (two per game). Please provide URLs in pairs.")
        return

    num_games = len(all_urls) // 2
    print(f"\nFound {num_games} game(s) to analyze for the year {year_to_analyze}.")

    for i in range(num_games):
        game_number = i + 1
        print(f"\n\n========== ANALYZING GAME {game_number} OF {num_games} ==========")
        url1 = all_urls[i * 2]
        url2 = all_urls[i * 2 + 1]

        pitcher_data_for_game = []

        print(f"\n--- Pitcher 1 (Game {game_number}) ---")
        print(f"Fetching data from: {url1}")
        pitcher1 = analyze_pitcher(url1, year_to_analyze)
        if pitcher1:
            pitcher_data_for_game.append(pitcher1)
        
        print(f"\n--- Pitcher 2 (Game {game_number}) ---")
        print(f"Fetching data from: {url2}")
        pitcher2 = analyze_pitcher(url2, year_to_analyze)
        if pitcher2:
            pitcher_data_for_game.append(pitcher2)

        if pitcher_data_for_game:
            display_summary(pitcher_data_for_game)

            if len(pitcher_data_for_game) == 2:
                yrfi_prob = calculate_combined_probability(pitcher_data_for_game)
                if yrfi_prob is not None:
                    print("\n===== MATCHUP SUMMARY =====")
                    print(f"Calculated Probability of YRFI for Game {game_number}: {yrfi_prob:.1f}%")
                    print(f"Calculated Probability of NRFI for Game {game_number}: {(100 - yrfi_prob):.1f}%")
                    
                    kelly_choice = input(f"\nCalculate Kelly Bet for Game {game_number}? (y/n): ").strip().lower()
                    if kelly_choice == 'y':
                        kelly_bet(yrfi_prob)
                else:
                    print("Could not calculate combined YRFI probability for Kelly bet for this game.")
            else:
                print(f"\nSkipping Matchup Summary and Kelly Bet for Game {game_number} as data for both pitchers is not available.")
        else:
            print(f"\nNo data successfully processed for Game {game_number}.")
        print(f"========== END OF ANALYSIS FOR GAME {game_number} ==========")


def main():
    while True:
        print("\n--- Pitcher Analyzer Options ---")
        choice = input("Choose analysis mode:\n1. Single Game (2 URLs)\n2. Multiple Games (comma-separated list of URLs)\nQ. Quit\nEnter choice (1, 2, or Q): ").strip().lower()
        
        if choice == '1':
            analyze_single_game()
            break 
        elif choice == '2':
            try:
                year = int(input("Enter the year to analyze for ALL games: "))
                analyze_multiple_games_sequentially(year)
            except ValueError:
                print("Invalid year entered. Please enter a valid year (e.g., 2023).")
            break
        elif choice == 'q':
            print("Exiting program.")
            break
        else:
            print("Invalid choice. Please enter 1, 2, or Q.")

if __name__ == "__main__":
    main()


