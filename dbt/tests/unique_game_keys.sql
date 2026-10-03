select provider, game_id
from {{ ref('stg_games') }}
group by provider, game_id
having count(*) != 1
