select "game_key"
from {{ ref('games') }}
where "opening_family" like '%:%'
    or "opening_family" = ''
    or (
        (
            "source_opening" is null
            or trim("source_opening") = ''
            or trim(split_part("source_opening", ':', 1)) = ''
        )
        and "opening_family" is not null
    )
    or (
        nullif(trim(split_part("source_opening", ':', 1)), '') is not null
        and "opening_family" is null
    )
