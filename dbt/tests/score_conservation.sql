select provider, game_id
from {{ ref('stg_player_games') }}
group by provider, game_id
having sum(score) is not null and sum(score) != 1
