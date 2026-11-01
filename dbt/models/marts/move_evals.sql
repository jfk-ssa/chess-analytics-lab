{{ config(materialized='view') }}

select
    m."provider",
    m."game_id",
    m."ply",
    m."provider" || ':' || m."game_id" || ':' || m."ply" as "move_key",
    m."provider" || ':' || m."game_id" as "game_key",
    m."color",
    g."utc_date",
    g."opening_family",
    m."clock_bucket",
    m."phase_proxy",
    m."centipawn_deterioration",
    m."eval_before_cp_white" is not null
        and m."eval_after_cp_white" is not null as "evaluable",
    m."error_proxy",
    case
        when
            m."eval_before_cp_white" is not null
            and m."eval_after_cp_white" is not null
            and m."centipawn_deterioration" is not null
            then least(m."centipawn_deterioration", 1000)
    end as "clamped_deterioration"
from {{ source('published', 'fact_move') }} m
left join {{ ref('stg_games') }} g
    on m."provider" = g."provider" and m."game_id" = g."game_id"
