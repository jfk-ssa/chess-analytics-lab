select
    *,
    result in ('1-0', '0-1', '1/2-1/2') and not marked_bot as metric_eligible,
    result = '1/2-1/2' as drawn
from {{ ref('stg_games') }}
