select
    utc_date,
    base_seconds,
    increment_seconds,
    count(*) as accepted_games,
    count(*) filter (where metric_eligible) as eligible_games,
    count(*) filter (where metric_eligible and drawn) as drawn_games,
    count(*) filter (where result = '*') as unknown_results,
    count(*) filter (where marked_bot) as marked_bots,
    count(*) filter (where source_opening is null) as missing_source_opening
from {{ ref('int_game_eligibility') }}
group by utc_date, base_seconds, increment_seconds
