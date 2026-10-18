select
    "provider",
    "game_id",
    "provider" || ':' || "game_id" as "game_key",
    "provider" || ':' || "game_id" || ':' || "color" as "player_game_key",
    "color",
    "player_key",
    "rating",
    "opponent_rating",
    "score"
from {{ source('published', 'fact_player_game') }}
