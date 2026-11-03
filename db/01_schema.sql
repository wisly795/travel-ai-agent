CREATE TABLE packages (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    destination TEXT NOT NULL,
    days INTEGER NOT NULL CHECK (days BETWEEN 1 AND 30),
    price_per_person INTEGER NOT NULL CHECK (price_per_person > 0),
    seats_left INTEGER NOT NULL CHECK (seats_left >= 0),
    description TEXT NOT NULL
);

CREATE TABLE hotels (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    destination TEXT NOT NULL,
    room_type TEXT NOT NULL,
    price_per_night INTEGER NOT NULL CHECK (price_per_night > 0)
);

CREATE TABLE quotes (
    id SERIAL PRIMARY KEY,
    customer_name TEXT NOT NULL,
    package_id INTEGER NOT NULL REFERENCES packages(id),
    hotel_id INTEGER NOT NULL REFERENCES hotels(id),
    people INTEGER NOT NULL CHECK (people BETWEEN 1 AND 20),
    rooms INTEGER NOT NULL,
    nights INTEGER NOT NULL,
    total_price INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_packages_destination ON packages(destination);
CREATE INDEX idx_hotels_destination ON hotels(destination);
