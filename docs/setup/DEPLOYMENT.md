# Debuggo Deployment Documentation

This document provides comprehensive instructions for deploying the Debuggo application to the production environment.

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Prerequisites](#prerequisites)
3. [Deployment Options](#deployment-options)
   - [Automated Deployment](#automated-deployment)
   - [Manual Deployment](#manual-deployment)
   - [Docker Compose Deployment](#docker-compose-deployment)
4. [Database Migrations](#database-migrations)
5. [Environment Configuration](#environment-configuration)
6. [Troubleshooting](#troubleshooting)
7. [Monitoring and Maintenance](#monitoring-and-maintenance)

## System Architecture

The Debuggo application consists of the following components:

- **Backend (debuggo)**: FastAPI application that provides the API endpoints
- **Frontend (debuggo-ui)**: React application that provides the user interface
- **PostgreSQL**: Database for storing application data
- **Redis**: In-memory data store used for caching and locking
- **Kafka**: Message broker for event-driven architecture
- **Nginx**: Web server for serving the frontend and proxying API requests
- **Certbot**: For SSL certificate management

All components run as Docker containers in a Docker network.

## Prerequisites

- SSH access to the production server
- Docker and Docker Compose installed on both development and production machines
- SSH key for authentication (`~/.ssh/id_ed25519`)

## Deployment Options

### Automated Deployment

The easiest way to deploy the application is using the provided deployment script:

```bash
# Make the script executable
chmod +x deploy.sh

# Run the deployment script
./deploy.sh
```

The script performs the following steps:
1. Builds Docker images for backend and frontend
2. Saves the images to tar files
3. Transfers the images to the production server
4. Loads the images on the production server
5. Applies any database migrations
6. Updates environment files if needed
7. Restarts the containers with the new images
8. Verifies the deployment

### Manual Deployment

If you need more control over the deployment process, you can follow these steps manually:

#### 1. Build Docker Images

```bash
# Build backend image
cd /Users/aragossa/dzrprj/auroqa/auroqa
docker build --platform linux/amd64 -t thelisdeep/debuggo:latest .

# Build frontend image
cd /Users/aragossa/dzrprj/auroqa/auroqa-ui
docker build --platform linux/amd64 -t thelisdeep/debuggo-ui:latest .
```

#### 2. Save Docker Images

```bash
docker save -o debuggo-backend.tar thelisdeep/debuggo:latest
docker save -o debuggo-frontend.tar thelisdeep/debuggo-ui:latest
```

#### 3. Transfer Docker Images to Production Server

```bash
scp -i ~/.ssh/id_ed25519 debuggo-backend.tar debuggo-frontend.tar ubuntu@35.159.97.103:/home/ubuntu/
```

#### 4. Load Docker Images on Production Server

```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@35.159.97.103 "docker load -i /home/ubuntu/debuggo-backend.tar && docker load -i /home/ubuntu/debuggo-frontend.tar"
```

#### 5. Update Environment Files (if needed)

```bash
# Transfer environment files
scp -i ~/.ssh/id_ed25519 /Users/aragossa/dzrprj/auroqa/auroqa/.env.production ubuntu@35.159.97.103:/home/ubuntu/

# Update environment files on production server
ssh -i ~/.ssh/id_ed25519 ubuntu@35.159.97.103 "sudo cp /home/ubuntu/.env.production /opt/debuggo/app/.env"
```

#### 6. Restart Containers

```bash
# Restart backend container
ssh -i ~/.ssh/id_ed25519 ubuntu@35.159.97.103 "docker stop debuggo && docker rm debuggo && docker run -d --name debuggo --network debuggo_debuggo_network -v /opt/debuggo/app/.env:/app/.env -p 8000:8000 thelisdeep/debuggo:latest uvicorn main:app --host 0.0.0.0 --port 8000"

# Restart frontend container
ssh -i ~/.ssh/id_ed25519 ubuntu@35.159.97.103 "docker stop debuggo-ui && docker rm debuggo-ui && docker run -d --name debuggo-ui --network debuggo_debuggo_network -p 3000:80 thelisdeep/debuggo-ui:latest"
```

### Docker Compose Deployment

For a more robust deployment, you can use Docker Compose:

1. Transfer the Docker Compose file to the production server:

```bash
scp -i ~/.ssh/id_ed25519 /Users/aragossa/dzrprj/auroqa/docker-compose.prod.yml ubuntu@35.159.97.103:/home/ubuntu/
```

2. Deploy using Docker Compose:

```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@35.159.97.103 "cd /home/ubuntu && docker-compose -f docker-compose.prod.yml up -d"
```

## Database Migrations

Database migrations are managed through SQL scripts in the `migrations` directory. To create a new migration:

1. Create a new SQL file in the `migrations` directory with a descriptive name and sequential number:

```bash
touch /Users/aragossa/dzrprj/auroqa/auroqa/migrations/003_add_new_feature.sql
```

2. Add the SQL statements to the file:

```sql
-- Description of the migration
ALTER TABLE table_name ADD COLUMN new_column_name data_type;
```

3. When running the deployment script, migrations will be automatically applied.

To manually apply migrations:

```bash
# Copy migration files to production server
scp -i ~/.ssh/id_ed25519 /Users/aragossa/dzrprj/auroqa/auroqa/migrations/*.sql ubuntu@35.159.97.103:/home/ubuntu/

# Copy migration files into the Docker container
ssh -i ~/.ssh/id_ed25519 ubuntu@35.159.97.103 "for file in /home/ubuntu/*.sql; do docker cp \$file debuggo-postgres:/\$(basename \$file); done"

# Run migrations on the production server
ssh -i ~/.ssh/id_ed25519 ubuntu@35.159.97.103 "for file in /home/ubuntu/*.sql; do docker exec debuggo-postgres psql -U postgres -d postgres -f /\$(basename \$file); done"
```

## Environment Configuration

Environment variables are used to configure the application. The following files are used:

- `/Users/aragossa/dzrprj/auroqa/auroqa/.env.production`: Backend environment variables for production
- `/Users/aragossa/dzrprj/auroqa/auroqa-ui/.env`: Frontend environment variables

Key environment variables for the backend:

```
# Database configuration
DB_HOST=debuggo-postgres
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=eYuUm57C!

# Redis configuration
REDIS_HOST=debuggo-redis
REDIS_PORT=6379

# Kafka configuration
KAFKA_HOST=kafka
KAFKA_PORT=9092

# AI model configuration
AI_MODEL=gemini
GEMINI_API=your_api_key
```

Key environment variables for the frontend:

```
REACT_APP_API_URL=https://debuggo.app
```

## Troubleshooting

### Common Issues and Solutions

#### 1. Container fails to start

Check the container logs:

```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@35.159.97.103 "docker logs auroqa"
```

#### 2. Database connection issues

Ensure the database container is running and the environment variables are correctly set:

```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@35.159.97.103 "docker ps | grep postgres"
```

#### 3. Redis connection issues

Ensure the Redis container is running and the environment variables are correctly set:

```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@35.159.97.103 "docker ps | grep redis"
```

#### 4. Frontend routing issues (404 errors on refresh)

Ensure the Nginx configuration in the frontend container is correctly set up for a single-page application:

```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@35.159.97.103 "docker exec debuggo-ui cat /etc/nginx/conf.d/default.conf"
```

The configuration should include:

```
location / {
    root   /usr/share/nginx/html;
    index  index.html index.htm;
    try_files $uri $uri/ /index.html;  # This line is key for SPA routing
}
```

## Monitoring and Maintenance

### Checking Container Status

```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@35.159.97.103 "docker ps"
```

### Viewing Container Logs

```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@35.159.97.103 "docker logs debuggo"
ssh -i ~/.ssh/id_ed25519 ubuntu@35.159.97.103 "docker logs debuggo-ui"
```

### Backing Up the Database

```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@35.159.97.103 "docker exec debuggo-postgres pg_dump -U postgres -d postgres > /home/ubuntu/backup_$(date +%Y%m%d).sql"
```

### Restoring the Database

```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@35.159.97.103 "cat /home/ubuntu/backup.sql | docker exec -i debuggo-postgres psql -U postgres -d postgres"
```

---

This documentation will be updated as the deployment process evolves. For any questions or issues, please contact the development team.
