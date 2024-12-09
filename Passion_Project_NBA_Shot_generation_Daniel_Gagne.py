from quart import Quart, request, render_template_string
from nba_api.stats.endpoints import shotchartdetail, playercareerstats
from nba_api.stats.static import players
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle, Arc
import io
import base64
import logging
import requests

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Initialize Quart app
app = Quart(__name__)

# HTML template
html_template = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NBA Player Stats & Shot Chart</title>
    <style>
        body {
            font-family: 'Arial', sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #002B5C;
            color: #FFFFFF;
        }
        h1, h2, h3 {
            text-align: center;
        }
        h1 {
            color: #ED174C;
        }
        form {
            max-width: 500px;
            margin: 20px auto;
            padding: 20px;
            background: #004B87;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        }
        label {
            display: block;
            margin-bottom: 10px;
        }
        input[type="text"], select {
            width: 100%;
            padding: 10px;
            margin-bottom: 15px;
            border: 1px solid #ccc;
            border-radius: 4px;
        }
        input[type="submit"] {
            width: 100%;
            padding: 10px;
            background-color: #ED174C;
            color: white;
            border: none;
            border-radius: 4px;
            font-size: 16px;
        }
        input[type="submit"]:hover {
            background-color: #d61542;
        }
        .player-info {
            text-align: center;
            margin-top: 20px;
        }
        .player-info img {
            max-width: 200px;
            border-radius: 0;
        }
        .summary {
            margin: 20px auto;
            text-align: center;
            font-size: 18px;
            background-color: #004B87;
            padding: 15px;
            border-radius: 8px;
        }
        .stats-table {
            margin: 20px auto;
            max-width: 600px;
            background-color: #004B87;
            border-collapse: collapse;
            border: 1px solid #ED174C;
        }
        .stats-table th, .stats-table td {
            padding: 10px;
            text-align: center;
            border: 1px solid #ED174C;
        }
        .stats-table th {
            background-color: #ED174C;
            color: white;
        }
    </style>
</head>
<body>
    <h1>NBA Player Stats & Shot Chart</h1>
    <form action="/shot-chart" method="post">
        <label for="player_name">Enter NBA Player Name:</label>
        <input type="text" id="player_name" name="player_name" placeholder="e.g., Stephen Curry" required>
        <label for="season">Select Season:</label>
        <select id="season" name="season" required>
            {% for year in seasons %}
            <option value="{{ year }}">{{ year }}</option>
            {% endfor %}
        </select>
        <input type="submit" value="Generate Player Data">
    </form>
    {% if player_info %}
    <div class="player-info">
        <img src="{{ player_info.headshot_url }}" alt="Player Headshot">
        <h2>{{ player_info.name }} - {{ player_info.season }} Season</h2>
        <div class="summary">
            <p>{{ player_info.summary }}</p>
        </div>
        <h3>Total Stats:</h3>
        <table class="stats-table">
            <tr>
                <th>Games Played</th>
                <th>Minutes</th>
                <th>Total Points</th>
                <th>Points Per Game</th>
                <th>Assists Per Game</th>
                <th>Rebounds Per Game</th>
            </tr>
            <tr>
                <td>{{ player_info.stats.GP }}</td>
                <td>{{ player_info.stats.MIN }}</td>
                <td>{{ player_info.stats.TOTAL_PTS }}</td>
                <td>{{ player_info.stats.PPG }}</td>
                <td>{{ player_info.stats.APG }}</td>
                <td>{{ player_info.stats.RPG }}</td>
            </tr>
        </table>
        <h3>Shot Chart:</h3>
        <img src="data:image/png;base64,{{ player_info.shot_chart }}" alt="Shot Chart" style="width: 100%; max-width: 1200px;">
    </div>
    {% endif %}
</body>
</html>
'''

# Function to draw the basketball court
def draw_court(ax=None, color="black", lw=2):
    if ax is None:
        ax = plt.gca()

    hoop = Circle((0, 0), radius=7.5, linewidth=lw, color=color, fill=False)
    backboard = Rectangle((-30, -7.5), 60, -1, linewidth=lw, color=color)
    outer_box = Rectangle((-80, -47.5), 160, 190, linewidth=lw, color=color, fill=False)
    inner_box = Rectangle((-60, -47.5), 120, 190, linewidth=lw, color=color, fill=False)
    top_free_throw = Circle((0, 142.5), radius=60, linewidth=lw, color=color, fill=False)
    three_point_arc = Arc((0, 0), 475, 475, theta1=22, theta2=158, linewidth=lw, color=color)
    court_boundaries = Rectangle((-250, -47.5), 500, 470, linewidth=lw, color=color, fill=False)

    for element in [hoop, backboard, outer_box, inner_box, top_free_throw, three_point_arc, court_boundaries]:
        ax.add_patch(element)

    ax.set_xlim(-250, 250)
    ax.set_ylim(-47.5, 422.5)
    ax.set_aspect('equal')

# Get player ID
def get_player_id(player_name):
    player = [p for p in players.get_players() if p['full_name'].lower() == player_name.lower()]
    return player[0]['id'] if player else None

@app.route('/')
async def index():
    current_year = 2024
    seasons = [f"{year}-{str(year + 1)[-2:]}" for year in range(1996, current_year)]
    return await render_template_string(html_template, seasons=seasons, player_info=None)

@app.route('/shot-chart', methods=['POST'])
async def shot_chart():
    form_data = await request.form
    player_name = form_data['player_name']
    season = form_data['season']
    player_id = get_player_id(player_name)

    if not player_id:
        return "Player not found. Please check the name and try again."

    try:
        career_stats = playercareerstats.PlayerCareerStats(player_id=player_id).get_data_frames()[0]
        season_stats = career_stats[career_stats['SEASON_ID'] == season]
        if season_stats.empty:
            return f"No stats available for {player_name} in the {season} season."
        stats = season_stats.iloc[0][['PTS', 'AST', 'REB', 'GP', 'MIN']].to_dict()
        stats['PPG'] = round(stats['PTS'] / stats['GP'], 2)
        stats['APG'] = round(stats['AST'] / stats['GP'], 2)
        stats['RPG'] = round(stats['REB'] / stats['GP'], 2)
        stats['TOTAL_PTS'] = stats['PTS']
    except Exception as e:
        logging.error(f"Error fetching player stats: {e}")
        return "Error fetching player stats. Please try again later."

    try:
        shot_data = shotchartdetail.ShotChartDetail(
            team_id=0,
            player_id=player_id,
            season_type_all_star='Regular Season',
            season_nullable=season
        ).get_data_frames()[0]
    except Exception as e:
        logging.error(f"Error fetching shot chart data: {e}")
        return "Error fetching shot chart data. Please try again later."

    fig, ax = plt.subplots(figsize=(16, 12))  # Increased size for better visibility
    draw_court(ax)
    ax.scatter(shot_data['LOC_X'], shot_data['LOC_Y'], c='blue', alpha=0.6, s=50)
    ax.set_title(f"{player_name}'s Shot Chart ({season} Season)", fontsize=16)

    img_io = io.BytesIO()
    plt.savefig(img_io, format='png', bbox_inches=None)
    img_io.seek(0)
    plt.close(fig)

    headshot_url = f"https://cdn.nba.com/headshots/nba/latest/1040x760/{player_id}.png"
    try:
        response = requests.head(headshot_url)
        if response.status_code != 200:
            headshot_url = "https://via.placeholder.com/200?text=Player+Image+Not+Found"
    except Exception as e:
        logging.error(f"Error verifying headshot URL: {e}")
        headshot_url = "https://via.placeholder.com/200?text=Player+Image+Not+Found"

    summary = (f"{player_name} played {stats['GP']} games in the {season} season, "
               f"averaging {stats['PPG']} points, {stats['APG']} assists, "
               f"and {stats['RPG']} rebounds per game.")

    player_info = {
        "name": player_name,
        "season": season,
        "stats": stats,
        "summary": summary,
        "shot_chart": base64.b64encode(img_io.getvalue()).decode('utf-8'),
        "headshot_url": headshot_url
    }
    return await render_template_string(html_template, seasons=[], player_info=player_info)

if __name__ == '__main__':
    app.run(debug=True)

