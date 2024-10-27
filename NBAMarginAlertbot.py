import os
import telebot
import requests
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
import json

load_dotenv()

# Get API tokens from environment variables
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
BALLDONTLIE_API_KEY = os.getenv("BALLDONTLIE")
team_names = []
team_data = {}
bot = telebot.TeleBot(BOT_TOKEN)
alert_margin = 10 


@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Hello! I'll notify you if your NBA team is trailing by more than the set margin.")
    bot.reply_to(message, "Please 👉🏾 /set_team to set up alerts.")

# Command to set the team for monitoring
# Command to set NBA team with inline keyboard
# Dictionary to hold selected teams for each user by chat ID
user_teams = {}

@bot.message_handler(commands=['set_team'])
def set_team(message):
    # Create an InlineKeyboardMarkup instance with row width of 5
    markup = telebot.types.InlineKeyboardMarkup(row_width=5)
    
    # Define buttons for all NBA teams with exact names as callback data
    teams = [
        ("Atlanta Hawks", "Atlanta Hawks"),
        ("Boston Celtics", "Boston Celtics"),
        ("Brooklyn Nets", "Brooklyn Nets"),
        ("Charlotte Hornets", "Charlotte Hornets"),
        ("Chicago Bulls", "Chicago Bulls"),
        ("Cleveland Cavaliers", "Cleveland Cavaliers"),
        ("Dallas Mavericks", "Dallas Mavericks"),
        ("Denver Nuggets", "Denver Nuggets"),
        ("Detroit Pistons", "Detroit Pistons"),
        ("Golden State Warriors", "Golden State Warriors"),
        ("Houston Rockets", "Houston Rockets"),
        ("Indiana Pacers", "Indiana Pacers"),
        ("LA Clippers", "LA Clippers"),
        ("Los Angeles Lakers", "Los Angeles Lakers"),
        ("Memphis Grizzlies", "Memphis Grizzlies"),
        ("Miami Heat", "Miami Heat"),
        ("Milwaukee Bucks", "Milwaukee Bucks"),
        ("Minnesota Timberwolves", "Minnesota Timberwolves"),
        ("New Orleans Pelicans", "New Orleans Pelicans"),
        ("New York Knicks", "New York Knicks"),
        ("Oklahoma City Thunder", "Oklahoma City Thunder"),
        ("Orlando Magic", "Orlando Magic"),
        ("Philadelphia 76ers", "Philadelphia 76ers"),
        ("Phoenix Suns", "Phoenix Suns"),
        ("Portland Trail Blazers", "Portland Trail Blazers"),
        ("Sacramento Kings", "Sacramento Kings"),
        ("San Antonio Spurs", "San Antonio Spurs"),
        ("Toronto Raptors", "Toronto Raptors"),
        ("Utah Jazz", "Utah Jazz"),
        ("Washington Wizards", "Washington Wizards"),
        ("DONE✅", "done")
    ]

    # Create and add each team button
    for team_name, callback_data in teams:
        button = telebot.types.InlineKeyboardButton(text=team_name, callback_data=callback_data)
        markup.add(button)

    # Send the message with the inline keyboard
    bot.send_message(message.chat.id, "Choose your NBA team:", reply_markup=markup)
    user_teams[message.chat.id] = []  # Initialize empty list for user teams


@bot.callback_query_handler(func=lambda call: True)
def input_team(call):
    chat_id = call.message.chat.id
    
    if call.data == 'done':
        # Finished selection, delete the inline keyboard
        bot.delete_message(chat_id, call.message.message_id)
        # Send a message summarizing selected teams
        selected_teams = user_teams.get(chat_id, [])
        if selected_teams:
            bot.send_message(chat_id, f"Teams set to monitor: {', '.join(selected_teams)}.")
        else:
            bot.send_message(chat_id, f"Teams set to monitor: None .")
        # Start monitoring for each team
        monitor_games(chat_id,selected_teams)  # Call monitor_games per team as needed
    else:
        # Add selected team to the user's list
        if call.data not in user_teams[chat_id]:  # Avoid duplicate entries
            user_teams[chat_id].append(call.data)
            bot.answer_callback_query(call.id, f"{call.data} added to your list.")  # Confirmation feedback



# Function to get spreads for NBA games from The Odds API
def get_nba_spreads():
    url = f'https://api.the-odds-api.com/v4/sports/basketball_nba/odds?regions=us&markets=spreads&apiKey={ODDS_API_KEY}'
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()  # Return the spread data
    else:
        print("Error fetching spread data:", response.status_code)
        return None

# Function to get live scores for a specific team from BallDontLie
def get_live_score(team_name, date,userid):
    response = None  # Initialize response variable
    try:
        header = {
            "Authorization": BALLDONTLIE_API_KEY
        }
        # Fetch all teams to get the correct team ID
        teams_response = requests.get('https://api.balldontlie.io/v1/teams',headers=header)
        teams_data = teams_response.json().get('data', [])
        # Find the team ID based on the team name
        team_id = None
        for team in teams_data:
            if team['full_name'].lower() == team_name.lower():
                team_id = team['id']
                break
        
        if team_id is None:
            print(f"Team ID not found for {team_name}")
            return None

        url = f'https://api.balldontlie.io/v1/games?team_ids[]={team_id}&start_date={date}&end_date={date}'
        print(f"Fetching live score from URL: {url}")  # Print the URL for debugging
        
        # Include the API key in the headers
        
        
        response = requests.get(url, headers=header)
        
        if response.status_code == 200:
            games = response.json().get('data', [])
            if not games:
                print("No games found for the given date.")
                bot.send_message(userid,f"No games found for the given date. {team_name}")
            for game in games:
                return {
                    "home_team": game['home_team']['full_name'],
                    "away_team": game['visitor_team']['full_name'],
                    "home_score": game['home_team_score'],
                    "away_score": game['visitor_team_score'],
                }
        else:
            print(f"Error fetching live score data: {response.status_code}")
            print("Response text:", response.text)
            return None
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}. Raw response: {response.text if response else 'No response available.'}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Request exception: {e}")
        return None




# Function to calculate the trailing margin based on live scores and the pre-game spread
def calculate_margin(team_name, pre_game_spread, date,userid):
    try:
        live_game = get_live_score(team_name, date,userid)
    except (KeyError, IndexError, ValueError) as e:
        print(f"Error accessing live score for {team_name}: {e}")
    else:
        if live_game:
            # Calculate the trailing margin based on whether the team is home or away
            if team_name.lower() == live_game["home_team"].lower():
                trailing_margin = live_game["away_score"] - live_game["home_score"]
            else:
                trailing_margin = live_game["home_score"] - live_game["away_score"]
            
            return trailing_margin  # Return the trailing margin
    return None  # Return None if no game is found


def is_game_finished(team_name,date):
    
    try:
        # Fetch all teams to get the correct team ID
        header = {
            "Authorization": BALLDONTLIE_API_KEY
        }
        teams_response = requests.get('https://api.balldontlie.io/v1/teams', headers=header)
        teams_data = teams_response.json().get('data', [])
        
        # Find the team ID based on the team name
        team_id = next((team['id'] for team in teams_data if team['full_name'].lower() == team_name.lower()), None)
        
        if not team_id:
            print(f"Team ID not found for {team_name}")
            return False
        
        # Get the game information for the specific team and date
        url = f'https://api.balldontlie.io/v1/games?team_ids[]={team_id}&start_date={date}&end_date={date}'
        response = requests.get(url, headers=header)
        
        if response.status_code == 200:
            games = response.json().get('data', [])
            
            for game in games:
                # Check if the game status is "Final" (or similar, depending on API)
                if game.get('status') == "Final":
                    return True
                
                # Alternatively, check if the game time has passed a certain duration
                
        else:
            print(f"Error fetching game data: {response.status_code}")
    
    except requests.exceptions.RequestException as e:
        print(f"Request exception: {e}")
    
    return False


def monitor_games(chat_id, team_names):
    # Initialize dictionary to store each team and its pre-game spread info
    global team_data

    while True:
        date = datetime.now().date().isoformat()  # Get current date in YYYY-MM-DD format

        try:
            spreads = get_nba_spreads()  # Fetch spreads
            if spreads:
                for team_name in team_names:
                    for game in spreads:
                        if team_name.lower() in [game.get('home_team', '').lower(), game.get('away_team', '').lower()]:
                            try:
                                # Attempt to find FanDuel data first
                                fanduel_data = next(
                                    (bookmaker for bookmaker in game['bookmakers'] if bookmaker['title'] == 'FanDuel'), 
                                    None
                                )
                                
                                spread_data = fanduel_data if fanduel_data else game['bookmakers'][0]
                                spread_info = spread_data['markets'][0]['outcomes']
                                
                                for outcome in spread_info:
                                    if outcome['name'].lower() == team_name.lower():
                                        pre_game_spread = float(outcome['point'])
                                        
                                        # If team is not yet in team_data, add it with alert threshold
                                        if team_name not in team_data:
                                            team_data[team_name] = {
                                                'pre_game_spread': pre_game_spread,
                                                'alert_threshold': pre_game_spread + 10
                                            }
                                            print(f"Stored data for {team_name}: {team_data[team_name]}")
                                            bot.send_message(chat_id,f"Pre-game spread for {team_name}: {pre_game_spread}")
                                            bot.send_message(chat_id,f"Alert threshold for {team_name}: {pre_game_spread+10}")

                                        print(f"Pre-game spread for {team_name}: {pre_game_spread}")
                                        print(f"Alert threshold for {team_name}: {pre_game_spread+10}")

                                        trailing_margin = calculate_margin(team_name, pre_game_spread, date,chat_id)
                                        
                                        # Check if team is trailing beyond the alert threshold
                                        if trailing_margin is not None and trailing_margin > team_data[team_name]['alert_threshold']:
                                            bot.send_message(chat_id, f"Alert! {team_name} is trailing by more than the threshold of {team_data[team_name]['alert_threshold']} points.")
                                        else:
                                            print(f"{team_name} is not trailing by the required margin yet.")

                                        # Example end-of-game condition (implement based on actual logic)
                                        if is_game_finished(team_name,date):
                                            print(f"Game finished for {team_name}. Removing from tracking.")
                                            del team_data[team_name]  # Remove the team after game completion

                            except (KeyError, IndexError, ValueError) as e:
                                print(f"Error accessing spread data for {team_name}: {e}")

        except json.JSONDecodeError as e:
            bot.send_message(chat_id, "An error occurred while decoding the spread data. Please try again later.")
            print(f"JSON decode error: {e}")
        except Exception as e:
            bot.send_message(chat_id, "An unexpected error occurred.")
            print(f"Unexpected error: {e}")

        # Wait 5 minutes before checking again to save API requests
        time.sleep(300)





print("bot runnin...")
# Webhook route to receive updates
bot.polling()