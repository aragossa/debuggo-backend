-- An environment gets the address of the application's API next to base_url (the UI address).
-- api_request steps and API tests send relative endpoints there, and steps can use it as %api_url%.
-- Empty means "same as base_url", which is how environments worked before.
ALTER TABLE environments ADD COLUMN IF NOT EXISTS api_url VARCHAR(255);
