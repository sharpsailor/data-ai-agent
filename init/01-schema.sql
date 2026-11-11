CREATE TABLE users (
    user_id     SERIAL PRIMARY KEY,
    full_name   TEXT NOT NULL,
    email       TEXT UNIQUE NOT NULL,
    user_type   TEXT NOT NULL CHECK (user_type IN ('rider', 'driver')),
    city        TEXT NOT NULL,
    province    TEXT NOT NULL,
    signup_date DATE NOT NULL
);

CREATE TABLE vehicles (
    vehicle_id    SERIAL PRIMARY KEY,
    driver_id     INT NOT NULL REFERENCES users(user_id),
    make          TEXT NOT NULL,
    model         TEXT NOT NULL,
    year          INT NOT NULL,
    license_plate TEXT UNIQUE NOT NULL
);

CREATE TABLE rides (
    ride_id       SERIAL PRIMARY KEY,
    rider_id      INT NOT NULL REFERENCES users(user_id),
    driver_id     INT NOT NULL REFERENCES users(user_id),
    start_time    TIMESTAMP NOT NULL,
    end_time      TIMESTAMP NOT NULL,
    pickup_lat    NUMERIC(9,6),
    pickup_lng    NUMERIC(9,6),
    dropoff_lat   NUMERIC(9,6),
    dropoff_lng   NUMERIC(9,6),
    distance_km   NUMERIC(6,2) NOT NULL,
    fare          NUMERIC(8,2) NOT NULL
);

CREATE TABLE payments (
    payment_id     SERIAL PRIMARY KEY,
    ride_id        INT NOT NULL REFERENCES rides(ride_id),
    user_id        INT NOT NULL REFERENCES users(user_id),
    amount         NUMERIC(8,2) NOT NULL,
    payment_method TEXT NOT NULL CHECK (payment_method IN ('credit_card', 'debit_card', 'paypal', 'apple_pay')),
    payment_status TEXT NOT NULL CHECK (payment_status IN ('completed', 'failed', 'refunded')),
    paid_at        TIMESTAMP NOT NULL
);

CREATE TABLE ratings (
    rating_id SERIAL PRIMARY KEY,
    ride_id   INT NOT NULL REFERENCES rides(ride_id),
    rider_id  INT NOT NULL REFERENCES users(user_id),
    driver_id INT NOT NULL REFERENCES users(user_id),
    rating    INT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment   TEXT
);

-- The agent connects with this role: the database itself refuses writes,
-- so the LLM safety judge is a second line of defence, not the only one.
CREATE ROLE agent_reader LOGIN PASSWORD 'reader_pass';
GRANT CONNECT ON DATABASE agent_db TO agent_reader;
GRANT USAGE ON SCHEMA public TO agent_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO agent_reader;
ALTER ROLE agent_reader SET statement_timeout = '10s';
ALTER ROLE agent_reader SET default_transaction_read_only = on;
