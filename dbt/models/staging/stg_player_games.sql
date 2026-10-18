select
    "provider",
    "game_id",
    "provider" || ':' || "game_id" as "game_key",
    "provider" || ':' || "game_id" || ':' || "color" as "player_game_key",
    "color",
    "player_key",
    "rating",
    "opponent_rating",
    "score",
    case
        when "rating" is null then null
        else cast(("rating" // 200) * 200 as varchar)
            || '-'
            || cast(("rating" // 200) * 200 + 199 as varchar)
    end as "rating_band"
from {{ source('published', 'fact_player_game') }}
