{{ config(materialized='view') }}

with players as (
    select
        p."player_game_key",
        p."game_key",
        p."color",
        p."player_key",
        p."rating",
        p."score",
        g."utc_date",
        g."base_seconds",
        g."increment_seconds",
        g."opening_family",
        case
            when
                g."rated"
                and g."variant" = 'Standard'
                and g."metric_eligible"
                and p."rating" is not null
                and g."opening_family" is not null
                then 1
            else 0
        end as "score_eligible"
    from {{ ref('stg_player_games') }} as p
    inner join {{ ref('int_game_eligibility') }} as g using ("game_key")
)

select
    "player_game_key",
    "game_key",
    "color",
    "player_key",
    "rating",
    "score",
    "utc_date",
    "base_seconds",
    "increment_seconds",
    "opening_family",
    "score_eligible",
    case when "score_eligible" = 1 then "score" else 0 end as "eligible_score",
    case when "score_eligible" = 1 and "score" = 1 then 1 else 0 end as "eligible_win",
    case when "score_eligible" = 1 and "score" = 0.5 then 1 else 0 end as "eligible_draw",
    case when "score_eligible" = 1 and "score" = 0 then 1 else 0 end as "eligible_loss"
from players
