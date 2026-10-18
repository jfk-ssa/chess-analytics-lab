select g."eligible"
from (
    select sum("eligible_game") as "eligible"
    from {{ ref('games') }}
) as g
cross join (
    select sum("eligible_games") as "eligible"
    from {{ ref('mart_game_outcomes') }}
) as m
where g."eligible" is distinct from m."eligible"
