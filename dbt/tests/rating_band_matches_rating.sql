select "player_game_key"
from {{ ref('player_games') }}
where "rating_band" is distinct from case
    when "rating" is null then null
    else cast(("rating" // 200) * 200 as varchar)
        || '-'
        || cast(("rating" // 200) * 200 + 199 as varchar)
end
