select "game_key"
from {{ ref('games') }}
where "opening_family" is distinct from nullif(trim(split_part("source_opening", ':', 1)), '')
