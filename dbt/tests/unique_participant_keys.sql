select provider, game_id, color
from {{ ref('stg_player_games') }}
group by provider, game_id, color
having count(*) != 1
