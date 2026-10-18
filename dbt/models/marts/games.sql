{{ config(materialized='view') }}

select
    "game_key",
    "provider",
    "game_id",
    "rated",
    "variant",
    "result",
    "marked_bot",
    "metric_eligible",
    "drawn",
    "utc_date",
    "base_seconds",
    "increment_seconds",
    "source_opening",
    "opening_family",
    case
        when "rated" and "variant" = 'Standard' and "metric_eligible" then 1
        else 0
    end as "eligible_game",
    case
        when "rated" and "variant" = 'Standard' and "metric_eligible" and "drawn" then 1
        else 0
    end as "drawn_game",
    case
        when
            "rated"
            and "variant" = 'Standard'
            and "metric_eligible"
            and "opening_family" is not null
            then 1
        else 0
    end as "known_opening_game",
    case
        when
            "rated"
            and "variant" = 'Standard'
            and "metric_eligible"
            and "opening_family" is null
            then 1
        else 0
    end as "unknown_opening_game"
from {{ ref('int_game_eligibility') }}
