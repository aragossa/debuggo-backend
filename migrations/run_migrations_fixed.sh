#!/bin/bash

# Copy migration files to the production server
echo "Copying migration files to production server..."
scp -i ~/.ssh/id_ed25519 /Users/aragossa/dzrprj/auroqa/auroqa/migrations/001_create_projects_table.sql /Users/aragossa/dzrprj/auroqa/auroqa/migrations/002_create_environments_table.sql ubuntu@35.159.97.103:/home/ubuntu/

# Copy migration files into the Docker container
echo "Copying migration files into the Docker container..."
ssh -i ~/.ssh/id_ed25519 ubuntu@35.159.97.103 "docker cp /home/ubuntu/001_create_projects_table.sql auroqa-postgres:/001_create_projects_table.sql"
ssh -i ~/.ssh/id_ed25519 ubuntu@35.159.97.103 "docker cp /home/ubuntu/002_create_environments_table.sql auroqa-postgres:/002_create_environments_table.sql"

# Run migrations on the production server
echo "Running migrations on production server..."
ssh -i ~/.ssh/id_ed25519 ubuntu@35.159.97.103 "docker exec auroqa-postgres psql -U postgres -d postgres -f /001_create_projects_table.sql"
ssh -i ~/.ssh/id_ed25519 ubuntu@35.159.97.103 "docker exec auroqa-postgres psql -U postgres -d postgres -f /002_create_environments_table.sql"

echo "Migrations completed successfully!"
