-- Create platefind_db database
CREATE DATABASE platefind_db;
\c platefind_db;
-- Create trips table
CREATE TABLE trips (
    id UUID PRIMARY KEY,
    user_name VARCHAR(255) NOT NULL,
    plates TEXT[] NOT NULL,
    submission_date TIMESTAMP WITH TIME ZONE NOT NULL,
    from_location VARCHAR(500) NOT NULL,
    to_location VARCHAR(500) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index on user for faster queries
CREATE INDEX idx_trips_user ON trips(user_name);

-- Create index on submission_date for date-based queries
CREATE INDEX idx_trips_submission_date ON trips(submission_date);

-- Optional: Create a trigger to auto-update the updated_at column
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_trips_updated_at 
    BEFORE UPDATE ON trips 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();


-- Create plates table
CREATE TABLE plates (
    id SERIAL PRIMARY KEY,
    state VARCHAR(255),
    country VARCHAR(255),
    design_name VARCHAR(255),
    design_description VARCHAR(255),
    design_reasoning TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Optional: Create a trigger to auto-update the updated_at column
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_plates_updated_at 
    BEFORE UPDATE ON plates 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

--------------------------------------------------------------
-- Gorm user creation and privilege granting
-- Note: Run these commands in the psql shell or as a superuser
-- Connect to postgres as the admin user
psql -U postgres

-- Create the user with a password
CREATE USER gorm WITH PASSWORD 'password'; 
-- Grant privileges to the user on the database
GRANT ALL PRIVILEGES ON DATABASE platefind_db TO gorm;

-- (Optional) Connect to the database and grant privileges on tables/sequences
\c platefind_db
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO gorm;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO gorm;