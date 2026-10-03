select
    provider, game_id, source_ordinal, result, utc_date, played_at,
    time_control, base_seconds, increment_seconds, source_opening, source_eco,
    marked_bot, ply_count, record_fingerprint
from {{ source('published', 'fact_game') }}
