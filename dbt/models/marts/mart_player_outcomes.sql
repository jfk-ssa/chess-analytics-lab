select
    p.provider, p.game_id, p.color, p.player_key, p.rating, p.opponent_rating,
    p.score, g.utc_date, g.base_seconds, g.increment_seconds, g.metric_eligible,
    case when p.score = 1 then 1 else 0 end as win,
    case when p.score = 0.5 then 1 else 0 end as draw,
    case when p.score = 0 then 1 else 0 end as loss
from {{ ref('stg_player_games') }} p
join {{ ref('int_game_eligibility') }} g using (provider, game_id)
