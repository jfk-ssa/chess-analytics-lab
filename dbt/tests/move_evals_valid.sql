-- Passes vacuously on empty move_evals (tiny/foundation stage empty fact_move).
-- Pytest covers behavior with non-empty fixtures.
-- Missing deterioration on an evaluable source row is a publication failure.
select *
from {{ ref('move_evals') }}
where
    "evaluable" is null
    or ("evaluable" and "centipawn_deterioration" is null)
    or (not "evaluable" and "clamped_deterioration" is not null)
    or ("evaluable" and "clamped_deterioration" is distinct from
        least("centipawn_deterioration", 1000))
    or "centipawn_deterioration" < 0
