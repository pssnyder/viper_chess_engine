# local_metrics_dashboard.py
# A locally running dashboard to visualize chess engine tuning metrics.
# TODO add functionality that, upon initialization of the metrics dash, backs up the database so we have a snapshot, then cleans up any incomplete games that could skew the metrics since we don't actually know the result. then it should create fresh test records for white and black color selections, under a metrics-test engine name (formerly ai_type) so we can test the dashboard without affecting the actual metrics. These test metrics will need to cover basic scenarios for data appearing in the visuals to allow for end to end testing in the event there is no real game data populated in the dev environment, the metrics dash will always initialize with its own test data ready, marking it as exclude from metrics in production branches but exclude from metrics False in dev branches for testing.

import dash
from dash import dcc, html, Output, Input # Removed State
import plotly.graph_objs as go
import pandas as pd
import numpy as np
from metrics_store import MetricsStore # Use the existing MetricsStore
import threading
import yaml
import atexit
from datetime import datetime # Import datetime for parsing timestamps

# Initialize the metrics store globally
metrics_store = MetricsStore()

# Start data collection in background
def start_metrics_collection():
    # Collect initial data
    metrics_store.collect_all_data()
    # Start periodic collection (every 30 seconds)
    metrics_store.start_collection(interval=30)

# Start collection in a background thread to avoid blocking the dashboard
collection_thread = threading.Thread(target=start_metrics_collection, daemon=True)
collection_thread.start()

# Load AI types from config.yaml (for dropdowns)
try:
    with open("chess_game.yaml", "r") as config_file:
        config_data = yaml.safe_load(config_file)
        # AI_TYPES is still loaded as metrics_store might use it internally or for logging,
        # but AI_TYPE_OPTIONS is no longer needed for UI dropdowns for white/black AI.
        AI_TYPES = config_data.get("ai_types", [])
        # unique_ai_types = sorted(list(set(AI_TYPES + ['Viper', 'Stockfish']))) # No longer needed for UI
        # AI_TYPE_OPTIONS = [{"label": ai_type.capitalize(), "value": ai_type} for ai_type in unique_ai_types] # No longer needed for UI
except Exception as e:
    print(f"Error loading config.yaml for AI types: {e}")
    AI_TYPES = []
    # AI_TYPE_OPTIONS = []

# --- DARK MODE COLORS ---
DARK_BG = "#18191A"
DARK_PANEL = "#242526"
DARK_ACCENT = "#3A3B3C"
DARK_TEXT = "#E4E6EB"
DARK_SUBTEXT = "#B0B3B8"
DARK_BORDER = "#3A3B3C"
DARK_HIGHLIGHT = "#4A90E2"
DARK_ERROR = "#FF5252"
DARK_WARNING = "#FFB300"
DARK_SUCCESS = "#00C853"

# Dash app
app = dash.Dash(__name__)
app.layout = html.Div([
    # Inject global CSS to remove body margin and set background
    dcc.Markdown(
        """
        <style>
            body { margin: 0 !important; background: #18191A !important; }
        </style>
        """,
        dangerously_allow_html=True
    ),
    html.Div([
        html.H1("Viper Chess Engine Tuning Dashboard", style={"textAlign": "center", "marginBottom": "20px", "color": DARK_TEXT}),
    ], style={"backgroundColor": DARK_BG}),

    # Main interval for refreshing data
    dcc.Interval(id="interval", interval=8000, n_intervals=0),

    # Static metrics section
    html.Div([
        html.Div([
            html.H2("Static Metrics", style={"textAlign": "center", "color": DARK_TEXT}),
            html.Div(id="static-metrics", style={"padding": "10px", "backgroundColor": DARK_PANEL, "borderRadius": "5px", "color": DARK_TEXT}),
        ], style={"flex": "1", "marginRight": "20px"}),
        html.Div([
            dcc.Graph(id="static-trend-graph", style={"height": "300px", "backgroundColor": DARK_PANEL}),
        ], style={"flex": "2"}),
    ], style={"display": "flex", "flexDirection": "row", "alignItems": "flex-start", "marginBottom": "30px"}),

    # A/B Testing & Dynamic Metric Filters
    html.Div([
        html.H2("A/B Testing & Metric Trends", style={"textAlign": "center", "marginBottom": "15px", "color": DARK_TEXT}),
        html.Div([
            # html.Div([ # Removed White AI Type Filter
            #     html.Label("White AI Type:", style={"color": DARK_TEXT}),
            #     dcc.Dropdown(
            #         id="white-ai-type-filter",
            #         options=[{"label": str(option["label"]), "value": str(option["value"])} for option in AI_TYPE_OPTIONS],
            #         multi=True,
            #         placeholder="Select White AI Type(s)",
            #         style={"backgroundColor": DARK_PANEL, "color": DARK_TEXT, "borderColor": DARK_BORDER}
            #     )
            # ], style={'width': '30%', 'display': 'inline-block', 'marginRight': '2%', 'verticalAlign': 'top'}),
            # html.Div([ # Removed Black AI Type Filter
            #     html.Label("Black AI Type:", style={"color": DARK_TEXT}),
            #     dcc.Dropdown(
            #         id="black-ai-type-filter",
            #         options=[{"label": str(option["label"]), "value": str(option["value"])} for option in AI_TYPE_OPTIONS],
            #         multi=True,
            #         placeholder="Select Black AI Type(s)",
            #         style={"backgroundColor": DARK_PANEL, "color": DARK_TEXT, "borderColor": DARK_BORDER}
            #     )
            # ], style={'width': '30%', 'display': 'inline-block', 'verticalAlign': 'top'}),
             html.Div([
                html.Label("Metric to Plot (for Viper Engine):", style={"color": DARK_TEXT}),
                dcc.Dropdown(
                    id="dynamic-metric-selector",
                    options=[], # Populated dynamically
                    placeholder="Select a metric (e.g., eval, nodes)",
                    style={"backgroundColor": DARK_PANEL, "color": DARK_TEXT, "borderColor": DARK_BORDER}
                )
            ], style={'width': '90%', 'display': 'inline-block', 'marginLeft': 'auto', 'marginRight': 'auto', 'verticalAlign': 'top'}), # Adjusted width and centering
        ], style={'marginBottom': '15px', 'textAlign': 'center'}), # Centering the dropdown div
        
        dcc.Graph(id="ab-test-trend-graph", style={"height": "400px", "backgroundColor": DARK_PANEL}),
        html.Div(id="move-metrics-details", style={"padding": "10px", "backgroundColor": DARK_PANEL, "borderRadius": "5px", "marginTop": "20px", "color": DARK_TEXT}),

    ], style={"marginBottom": "30px", "border": f"1px solid {DARK_BORDER}", "padding": "15px", "borderRadius": "8px", "backgroundColor": DARK_ACCENT}),

    # Placeholder for New Engine Tuning Visualizations (to be added later)
    html.Div(id="new-engine-tuning-visualizations", children=[
        # html.H2("Advanced Engine Performance Analysis", style={"textAlign": "center", "color": DARK_TEXT}),
        # ... new graphs and tables will go here ...
    ], style={"marginBottom": "30px", "border": f"1px solid {DARK_BORDER}", "padding": "15px", "borderRadius": "8px", "backgroundColor": DARK_ACCENT}),


], style={"fontFamily": "Arial, sans-serif", "padding": "20px", "backgroundColor": DARK_BG, "color": DARK_TEXT})

@app.callback(
    Output("dynamic-metric-selector", "options"),
    Input("interval", "n_intervals"), # Changed from log-analysis-interval
)
def update_dynamic_metric_options(_):
    # This callback updates the dropdown options based on available move metrics
    # It queries the distinct metric_names from the move_metrics table in MetricsStore
    move_metric_names = metrics_store.get_distinct_move_metric_names()
    options = [{'label': name.replace('_', ' ').title(), 'value': name} for name in move_metric_names]
    return options

@app.callback(
    [Output("ab-test-trend-graph", "figure"),
     Output("move-metrics-details", "children")],
    [Input("interval", "n_intervals"), # Triggered by the main interval
     # Input("white-ai-type-filter", "value"), # Removed
     # Input("black-ai-type-filter", "value"), # Removed
     Input("dynamic-metric-selector", "value")]
)
def update_ab_testing_section(_, selected_metric): # Removed white_ai_types, black_ai_types
    fig_ab_test = go.Figure()
    move_metrics_details_components = []

    if not selected_metric:
        fig_ab_test.update_layout(
            title="Select a Metric to Plot for Viper Engine",
            paper_bgcolor=DARK_PANEL,
            plot_bgcolor=DARK_PANEL,
            font=dict(color=DARK_TEXT),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
        )
        fig_ab_test.add_annotation(text="Please select a metric from the dropdown.", xref="paper", yref="paper", showarrow=False, font=dict(size=16, color=DARK_TEXT))
        move_metrics_details_components.append(html.P("Please select a metric from the dropdown to visualize Viper's performance trend.", style={"color": DARK_TEXT}))
        return fig_ab_test, move_metrics_details_components

    # Get all moves made by Viper
    all_viper_moves_raw = metrics_store.get_filtered_move_metrics(
        white_ai_types=['Viper'], # Only Viper as white
        black_ai_types=['Viper'], # Only Viper as black
        metric_name=selected_metric
    )
    
    if not all_viper_moves_raw:
        fig_ab_test.update_layout(
            title=f"No '{selected_metric}' Data for Viper Engine",
            paper_bgcolor=DARK_PANEL, plot_bgcolor=DARK_PANEL, font=dict(color=DARK_TEXT),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
        )
        fig_ab_test.add_annotation(text=f"No move data found for Viper playing '{selected_metric}'.", xref="paper", yref="paper", showarrow=False, font=dict(size=16, color=DARK_TEXT))
        move_metrics_details_components.append(html.P(f"No move metrics data found for Viper for the metric: {selected_metric}.", style={"color": DARK_TEXT}))
        return fig_ab_test, move_metrics_details_components

    df_all_viper_moves = pd.DataFrame(all_viper_moves_raw)
    df_games_raw = metrics_store.get_all_game_results_df()

    if df_games_raw is None or df_games_raw.empty:
        # Handle case where there are no game results to filter by
        fig_ab_test.update_layout(title="No Game Results Available for Context", paper_bgcolor=DARK_PANEL, plot_bgcolor=DARK_PANEL, font=dict(color=DARK_TEXT))
        move_metrics_details_components.append(html.P("No game results found to provide context for Viper's moves.", style={"color": DARK_TEXT}))
        return fig_ab_test, move_metrics_details_components

    # Determine which Viper moves to analyze based on game context
    viper_perspectives = []
    for _, game_row in df_games_raw.iterrows():
        game_id = game_row['game_id']
        white_is_viper = game_row.get('white_ai_type') == 'Viper'
        black_is_viper = game_row.get('black_ai_type') == 'Viper'
        exclude_white = game_row.get('exclude_white_from_metrics', False)
        exclude_black = game_row.get('exclude_black_from_metrics', False)
        winner = game_row.get('winner')

        if white_is_viper and black_is_viper: # Viper vs Viper
            if winner == '1-0' and not exclude_white: # White Viper won
                viper_perspectives.append({'game_id': game_id, 'viper_color_to_analyze': 'white'})
            elif winner == '0-1' and not exclude_black: # Black Viper won
                viper_perspectives.append({'game_id': game_id, 'viper_color_to_analyze': 'black'})
            # Moves from drawn Viper vs Viper or losing Viper are excluded for this trend
        elif white_is_viper and not exclude_white: # Viper (White) vs Non-Viper
            viper_perspectives.append({'game_id': game_id, 'viper_color_to_analyze': 'white'})
        elif black_is_viper and not exclude_black: # Viper (Black) vs Non-Viper
            viper_perspectives.append({'game_id': game_id, 'viper_color_to_analyze': 'black'})
            
    if not viper_perspectives:
        fig_ab_test.update_layout(title=f"No Valid Game Context for Viper's '{selected_metric}'", paper_bgcolor=DARK_PANEL, plot_bgcolor=DARK_PANEL, font=dict(color=DARK_TEXT))
        move_metrics_details_components.append(html.P("No games found where Viper's performance can be analyzed based on current criteria.", style={"color": DARK_TEXT}))
        return fig_ab_test, move_metrics_details_components

    df_viper_perspectives = pd.DataFrame(viper_perspectives)
    
    # Merge Viper moves with the determined perspectives
    df_merged_moves = pd.merge(df_all_viper_moves, df_viper_perspectives, on='game_id', how='inner')
    
    # Filter moves to only those matching the 'viper_color_to_analyze'
    # Ensure 'player_color' in df_merged_moves is comparable (e.g., 'white' or 'w')
    # Assuming 'player_color' in move_metrics is 'white' or 'black'
    df_final_moves = df_merged_moves[df_merged_moves['player_color'].str.lower() == df_merged_moves['viper_color_to_analyze'].str.lower()]

    if df_final_moves.empty:
        fig_ab_test.update_layout(
            title=f"No '{selected_metric}' Data for Viper (Post-Filtering)",
            paper_bgcolor=DARK_PANEL, plot_bgcolor=DARK_PANEL, font=dict(color=DARK_TEXT),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
        )
        fig_ab_test.add_annotation(text=f"No '{selected_metric}' moves from Viper met the analysis criteria (e.g., winning side in Viper vs Viper).", xref="paper", yref="paper", showarrow=False, font=dict(size=16, color=DARK_TEXT))
        move_metrics_details_components.append(html.P(f"No moves for '{selected_metric}' by Viper met the specific analysis criteria.", style={"color": DARK_TEXT}))
        return fig_ab_test, move_metrics_details_components

    df_final_moves = df_final_moves.copy() # Avoid SettingWithCopyWarning
    df_final_moves['created_at_dt'] = pd.to_datetime(df_final_moves['created_at'])
    df_final_moves = df_final_moves.sort_values('created_at_dt')

    fig_ab_test.add_trace(go.Scatter(
        x=df_final_moves['created_at_dt'],
        y=df_final_moves[selected_metric],
        mode='markers',
        name=f'Viper {selected_metric.replace("_", " ").title()}',
        marker=dict(size=6, opacity=0.7, color=DARK_HIGHLIGHT)
    ))
    
    if len(df_final_moves) > 1:
        df_final_moves['time_numeric'] = (df_final_moves['created_at_dt'] - df_final_moves['created_at_dt'].min()).dt.total_seconds()
        # Ensure selected_metric column is numeric for polyfit
        numeric_metric_values = pd.to_numeric(df_final_moves[selected_metric], errors='coerce').dropna()
        numeric_time_values = df_final_moves.loc[numeric_metric_values.index, 'time_numeric']

        # Convert to numpy arrays for polyfit
        x = np.array(numeric_time_values)
        y = np.array(numeric_metric_values)
        if len(x) > 1 and len(y) > 1:
            z = np.polyfit(x, y, 1)
            p = np.poly1d(z)
            fig_ab_test.add_trace(go.Scatter(
                x=df_final_moves.loc[numeric_metric_values.index, 'created_at_dt'],
                y=p(x),
                mode='lines',
                name='Trendline',
                line=dict(color=DARK_SUCCESS, dash='dash')
            ))

    fig_ab_test.update_layout(
        title=f"Viper Engine: {selected_metric.replace('_', ' ').title()} Trend",
        xaxis_title="Time of Move",
        yaxis_title=selected_metric.replace('_', ' ').title(),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        paper_bgcolor=DARK_PANEL,
        plot_bgcolor=DARK_PANEL,
        font=dict(color=DARK_TEXT),
        xaxis=dict(gridcolor=DARK_ACCENT),
        yaxis=dict(gridcolor=DARK_ACCENT)
    )

    move_metrics_details_components.append(html.H4(f"Viper Summary for {selected_metric.replace('_', ' ').title()}", style={"color": DARK_TEXT}))
    
    metric_series = pd.to_numeric(df_final_moves[selected_metric], errors='coerce').dropna()
    if not metric_series.empty:
        avg_val = metric_series.mean()
        min_val = metric_series.min()
        max_val = metric_series.max()
        count_val = metric_series.count()
        std_val = metric_series.std()
        num_games = len(df_final_moves['game_id'].unique())

        move_metrics_details_components.append(html.Ul([
            html.Li(f"Number of Games Analyzed: {num_games}", style={"color": DARK_SUBTEXT}),
            html.Li(f"Total Data Points (Moves): {count_val}", style={"color": DARK_SUBTEXT}),
            html.Li(f"Average: {avg_val:.3f}", style={"color": DARK_SUBTEXT}),
            html.Li(f"Min: {min_val:.3f}", style={"color": DARK_SUBTEXT}),
            html.Li(f"Max: {max_val:.3f}", style={"color": DARK_SUBTEXT}),
            html.Li(f"Standard Deviation: {std_val:.3f}", style={"color": DARK_SUBTEXT}),
        ], style={"listStyleType": "none", "paddingLeft": "0"}))
    else:
        move_metrics_details_components.append(html.P("No numeric data available for summary statistics.", style={"color": DARK_SUBTEXT}))


    return fig_ab_test, move_metrics_details_components


# Update the static metrics to use stored data
@app.callback(
    [Output("static-metrics", "children"),
     Output("static-trend-graph", "figure")],
    Input("interval", "n_intervals"),
)
def update_static_metrics(_):
    df_games_raw = metrics_store.get_all_game_results_df()
    
    fig_static_trend = go.Figure()
    
    if df_games_raw is None or df_games_raw.empty:
        metrics_display = html.Ul([
            html.Li("Total Viper Games: 0", style={"color": DARK_SUBTEXT}),
            html.Li("Viper Wins: 0", style={"color": DARK_SUBTEXT}),
            html.Li("Viper Losses: 0", style={"color": DARK_SUBTEXT}),
            html.Li("Viper Draws: 0", style={"color": DARK_SUBTEXT}),
        ], style={"listStyleType": "none", "paddingLeft": "0"})
        
        fig_static_trend.update_layout(
            title="No Game Result Data Available for Viper",
            height=300, margin=dict(t=40, b=20, l=30, r=20),
            paper_bgcolor=DARK_PANEL, plot_bgcolor=DARK_PANEL, font=dict(color=DARK_TEXT),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
        )
        fig_static_trend.add_annotation(text="No game data for Viper to display.", xref="paper", yref="paper", showarrow=False, font=dict(size=16, color=DARK_TEXT))
        return metrics_display, fig_static_trend

    # Filter games relevant to Viper and respect exclusion flags
    viper_games_data = []
    for _, row in df_games_raw.iterrows():
        white_is_viper = row.get('white_ai_type') == 'Viper'
        black_is_viper = row.get('black_ai_type') == 'Viper'
        exclude_white = row.get('exclude_white_from_metrics', False)
        exclude_black = row.get('exclude_black_from_metrics', False)
        
        is_viper_game_and_not_excluded = False
        if white_is_viper and not exclude_white:
            is_viper_game_and_not_excluded = True
        if black_is_viper and not exclude_black: # Can be true even if white is also viper and not excluded
            is_viper_game_and_not_excluded = True
            
        if is_viper_game_and_not_excluded:
            viper_games_data.append(row)
    
    if not viper_games_data:
        # Same display as no raw data, but specific to Viper after filtering
        metrics_display = html.Ul([
            html.Li("Total Viper Games: 0 (after exclusion)", style={"color": DARK_SUBTEXT}),
            html.Li("Viper Wins: 0", style={"color": DARK_SUBTEXT}),
            html.Li("Viper Losses: 0", style={"color": DARK_SUBTEXT}),
            html.Li("Viper Draws: 0", style={"color": DARK_SUBTEXT}),
        ], style={"listStyleType": "none", "paddingLeft": "0"})
        fig_static_trend.update_layout(title="No Viper Games Meet Criteria", height=300, paper_bgcolor=DARK_PANEL, plot_bgcolor=DARK_PANEL, font=dict(color=DARK_TEXT))
        fig_static_trend.add_annotation(text="No Viper games to display after applying exclusion filters.", xref="paper", yref="paper", showarrow=False, font=dict(size=16, color=DARK_TEXT))
        return metrics_display, fig_static_trend

    df_viper_games = pd.DataFrame(viper_games_data)
    
    total_viper_games = len(df_viper_games)
    viper_wins = 0
    viper_losses = 0
    viper_draws = 0

    for _, row in df_viper_games.iterrows():
        winner = row.get('winner')
        white_is_viper_and_included = row.get('white_ai_type') == 'Viper' and not row.get('exclude_white_from_metrics', False)
        black_is_viper_and_included = row.get('black_ai_type') == 'Viper' and not row.get('exclude_black_from_metrics', False)

        if winner == '1-0':
            if white_is_viper_and_included: viper_wins +=1
            if black_is_viper_and_included: viper_losses +=1
        elif winner == '0-1':
            if black_is_viper_and_included: viper_wins +=1
            if white_is_viper_and_included: viper_losses +=1
        elif winner == '1/2-1/2':
            # A draw counts if Viper played and was not excluded
            if white_is_viper_and_included or black_is_viper_and_included:
                 viper_draws += 1
    
    metrics_display = html.Ul([
        html.Li(f"Total Viper Games (Analyzed): {total_viper_games}", style={"color": DARK_SUBTEXT}),
        html.Li(f"Viper Wins: {viper_wins}", style={"color": DARK_SUBTEXT}),
        html.Li(f"Viper Losses: {viper_losses}", style={"color": DARK_SUBTEXT}),
        html.Li(f"Viper Draws: {viper_draws}", style={"color": DARK_SUBTEXT}),
    ], style={"listStyleType": "none", "paddingLeft": "0"})
    
    # Trend graph for Viper game results
    if not df_viper_games.empty:
        df_viper_games = df_viper_games.copy() # Avoid SettingWithCopyWarning
        try:
            df_viper_games['timestamp_dt'] = pd.to_datetime(df_viper_games['timestamp'])
        except Exception: 
             df_viper_games['timestamp_dt'] = pd.to_datetime(df_viper_games['timestamp'], format="%Y%m%d_%H%M%S", errors='coerce')
        
        df_viper_games = df_viper_games.sort_values('timestamp_dt').reset_index(drop=True)
        
        df_viper_games['cum_viper_wins'] = 0
        df_viper_games['cum_viper_losses'] = 0
        df_viper_games['cum_viper_draws'] = 0

        current_wins = 0
        current_losses = 0
        current_draws = 0
        
        for index, row in df_viper_games.iterrows():
            winner = row.get('winner')
            white_is_viper_and_included = row.get('white_ai_type') == 'Viper' and not row.get('exclude_white_from_metrics', False)
            black_is_viper_and_included = row.get('black_ai_type') == 'Viper' and not row.get('exclude_black_from_metrics', False)

            if winner == '1-0':
                if white_is_viper_and_included: current_wins += 1
                if black_is_viper_and_included: current_losses += 1
            elif winner == '0-1':
                if black_is_viper_and_included: current_wins += 1
                if white_is_viper_and_included: current_losses += 1
            elif winner == '1/2-1/2':
                if white_is_viper_and_included or black_is_viper_and_included:
                    current_draws += 1
            df_viper_games.at[index, 'cum_viper_wins'] = current_wins
            df_viper_games.at[index, 'cum_viper_losses'] = current_losses
            df_viper_games.at[index, 'cum_viper_draws'] = current_draws

        fig_static_trend.add_trace(go.Scatter(
            x=df_viper_games['timestamp_dt'],
            y=df_viper_games['cum_viper_wins'],
            mode='lines+markers',
            name='Cumulative Wins',
            line=dict(color=DARK_SUCCESS)
        ))
        fig_static_trend.add_trace(go.Scatter(
            x=df_viper_games['timestamp_dt'],
            y=df_viper_games['cum_viper_losses'],
            mode='lines+markers',
            name='Cumulative Losses',
            line=dict(color=DARK_ERROR)
        ))
        fig_static_trend.add_trace(go.Scatter(
            x=df_viper_games['timestamp_dt'],
            y=df_viper_games['cum_viper_draws'],
            mode='lines+markers',
            name='Cumulative Draws',
            line=dict(color=DARK_WARNING)
        ))
        fig_static_trend.update_layout(
            title="Viper Game Results Over Time",
            xaxis_title="Game Timestamp",
            yaxis_title="Cumulative Count",
            height=300,
            paper_bgcolor=DARK_PANEL,
            plot_bgcolor=DARK_PANEL,
            font=dict(color=DARK_TEXT),
            xaxis=dict(gridcolor=DARK_ACCENT),
            yaxis=dict(gridcolor=DARK_ACCENT)
        )
    else: # Should be covered by earlier checks, but as a fallback
        fig_static_trend.update_layout(
            title="No Viper Game Result Data Available",
            height=300, margin=dict(t=40, b=20, l=30, r=20),
            paper_bgcolor=DARK_PANEL, plot_bgcolor=DARK_PANEL, font=dict(color=DARK_TEXT),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
        )
        fig_static_trend.add_annotation(text="No Viper game data to display.", xref="paper", yref="paper", showarrow=False, font=dict(size=16, color=DARK_TEXT))
            
    return metrics_display, fig_static_trend

# Clean up when the app is closed
def cleanup():
    print("Dashboard shutting down. Closing MetricsStore connection.")
    metrics_store.close()

atexit.register(cleanup)

if __name__ == "__main__":
    import socket
    # Get local IP address for LAN access
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "localhost"
    port = 8050
    print(f"\\nDash is running on: http://{local_ip}:{port} (accessible from your LAN)\\n")
    print(f"Or on this machine: http://localhost:{port}\\n")
    # Use host="0.0.0.0" to allow access from other machines on your LAN
    app.run(debug=True, host="0.0.0.0", port=port)