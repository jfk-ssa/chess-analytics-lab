select g.provider, g.game_id
from {{ ref('stg_games') }} g
left join {{ ref('stg_player_games') }} p using (provider, game_id)
group by g.provider, g.game_id
having count(p.color) != 2 or count(distinct p.color) != 2
