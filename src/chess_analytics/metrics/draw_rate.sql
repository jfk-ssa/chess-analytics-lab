SELECT
    count(*) FILTER (WHERE NOT marked_bot AND result = '1/2-1/2') AS numerator,
    count(*) FILTER (WHERE NOT marked_bot AND result IN ('1-0','0-1','1/2-1/2')) AS denominator,
    count(*) FILTER (WHERE NOT marked_bot AND result = '*') AS unknown_results,
    count(*) FILTER (WHERE marked_bot) AS marked_bots
FROM fact_game
WHERE rated AND variant = 'Standard'
