select
    provider, game_id, color, player_key, rating, opponent_rating, score
from {{ source('published', 'fact_player_game') }}
