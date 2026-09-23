-- query: only_in_ours
SELECT o.ref, o.payment_id, o.amount AS our_amount, o.currency, o.status AS our_status
FROM our_records AS o
WHERE NOT EXISTS (
    SELECT 1 FROM partner_statement AS p WHERE p.ref = o.ref
)
ORDER BY o.ref;

-- query: only_at_partner
SELECT p.ref, p.amount AS partner_amount, p.currency, p.status AS partner_status
FROM partner_statement AS p
WHERE NOT EXISTS (
    SELECT 1 FROM our_records AS o WHERE o.ref = p.ref
)
ORDER BY p.ref;

-- query: amount_mismatch
WITH unique_ours AS (
    SELECT ref FROM our_records GROUP BY ref HAVING COUNT(*) = 1
),
unique_partner AS (
    SELECT ref FROM partner_statement GROUP BY ref HAVING COUNT(*) = 1
)
SELECT o.ref, o.payment_id, o.amount AS our_amount,
       p.amount AS partner_amount, o.currency
FROM our_records AS o
JOIN partner_statement AS p ON p.ref = o.ref
JOIN unique_ours AS uo ON uo.ref = o.ref
JOIN unique_partner AS up ON up.ref = o.ref
WHERE o.currency = p.currency AND o.amount <> p.amount
ORDER BY o.ref;

-- query: status_mismatch
WITH unique_ours AS (
    SELECT ref FROM our_records GROUP BY ref HAVING COUNT(*) = 1
),
unique_partner AS (
    SELECT ref FROM partner_statement GROUP BY ref HAVING COUNT(*) = 1
)
SELECT o.ref, o.payment_id, o.status AS our_status,
       p.status AS partner_status
FROM our_records AS o
JOIN partner_statement AS p ON p.ref = o.ref
JOIN unique_ours AS uo ON uo.ref = o.ref
JOIN unique_partner AS up ON up.ref = o.ref
WHERE o.status <> p.status
ORDER BY o.ref;

-- query: partner_duplicates
SELECT ref, COUNT(*) AS row_count, COUNT(DISTINCT amount) AS distinct_amounts,
       COUNT(DISTINCT currency) AS distinct_currencies,
       COUNT(DISTINCT status) AS distinct_statuses
FROM partner_statement
GROUP BY ref
HAVING COUNT(*) > 1
ORDER BY ref;

-- query: currency_mismatch
WITH unique_ours AS (
    SELECT ref FROM our_records GROUP BY ref HAVING COUNT(*) = 1
),
unique_partner AS (
    SELECT ref FROM partner_statement GROUP BY ref HAVING COUNT(*) = 1
)
SELECT o.ref, o.payment_id, o.currency AS our_currency,
       p.currency AS partner_currency, o.amount AS our_amount,
       p.amount AS partner_amount
FROM our_records AS o
JOIN partner_statement AS p ON p.ref = o.ref
JOIN unique_ours AS uo ON uo.ref = o.ref
JOIN unique_partner AS up ON up.ref = o.ref
WHERE o.currency <> p.currency
ORDER BY o.ref;

-- query: our_duplicates
SELECT ref, COUNT(*) AS row_count
FROM our_records
GROUP BY ref
HAVING COUNT(*) > 1
ORDER BY ref;
