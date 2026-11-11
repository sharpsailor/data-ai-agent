-- Deterministic synthetic ride-share data (Canadian cities).
SELECT setseed(0.42);

-- 40 drivers (ids 1-40) and 160 riders (ids 41-200)
INSERT INTO users (full_name, email, user_type, city, province, signup_date)
SELECT
    (ARRAY['Alex','Sam','Priya','Wei','Maria','Omar','Liam','Emma','Noah','Ava','Ravi','Chloe','Jin','Sofia','Lucas'])[1 + (g % 15)]
      || ' ' ||
    (ARRAY['Smith','Patel','Chen','Garcia','Nguyen','Brown','Singh','Martin','Lee','Roy','Tremblay','Wilson'])[1 + ((g * 7) % 12)],
    'user' || g || '@example.com',
    CASE WHEN g <= 40 THEN 'driver' ELSE 'rider' END,
    c.city, c.province,
    DATE '2023-01-01' + (g * 3 % 900)
FROM generate_series(1, 200) g
JOIN (VALUES (0,'Toronto','ON'),(1,'Vancouver','BC'),(2,'Montreal','QC'),(3,'Calgary','AB'),(4,'Ottawa','ON'),(5,'Edmonton','AB'))
  AS c(k, city, province) ON c.k = g % 6;

INSERT INTO vehicles (driver_id, make, model, year, license_plate)
SELECT g,
    (ARRAY['Toyota','Honda','Hyundai','Tesla','Ford','Kia'])[1 + g % 6],
    (ARRAY['Camry','Civic','Elantra','Model 3','Escape','Niro'])[1 + g % 6],
    2015 + g % 10,
    'PLT-' || lpad(g::text, 4, '0')
FROM generate_series(1, 40) g;

-- 1500 rides over 2025-2026
INSERT INTO rides (rider_id, driver_id, start_time, end_time, pickup_lat, pickup_lng, dropoff_lat, dropoff_lng, distance_km, fare)
SELECT rider, driver, st, st + (dist * interval '2 minutes') + interval '3 minutes',
    43.6 + random() * 0.2, -79.5 + random() * 0.3,
    43.6 + random() * 0.2, -79.5 + random() * 0.3,
    dist, round((3.50 + dist * 1.45)::numeric, 2)
FROM (
    SELECT 41 + floor(random() * 160)::int AS rider,
           1 + floor(random() * 40)::int  AS driver,
           TIMESTAMP '2025-01-01' + random() * interval '650 days' AS st,
           round((1 + random() * 29)::numeric, 2) AS dist
    FROM generate_series(1, 1500)
) r;

INSERT INTO payments (ride_id, user_id, amount, payment_method, payment_status, paid_at)
SELECT ride_id, rider_id, fare,
    (ARRAY['credit_card','debit_card','paypal','apple_pay'])[1 + floor(random() * 4)::int],
    CASE WHEN random() < 0.9 THEN 'completed' WHEN random() < 0.5 THEN 'failed' ELSE 'refunded' END,
    end_time + interval '1 minute'
FROM rides;

INSERT INTO ratings (ride_id, rider_id, driver_id, rating, comment)
SELECT ride_id, rider_id, driver_id, s,
    (ARRAY['Terrible','Poor','Okay','Good ride','Excellent driver!'])[s]
FROM (SELECT ride_id, rider_id, driver_id, 1 + floor(power(random(), 0.4) * 5)::int AS s
      FROM rides WHERE random() < 0.7) x;
