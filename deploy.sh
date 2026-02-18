#!/bin/bash

# Define colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Starting Deployment ===${NC}"

# 1. Create Network
echo -e "${GREEN}1. Checking Docker Network...${NC}"
docker network create dokploy-network 2>/dev/null || true
echo "Network 'dokploy-network' is ready."

# 2. Deploy Database Stack
echo -e "${GREEN}2. Deploying Database Stack (Postgres + Adminer)...${NC}"
docker-compose -f database-compose.yaml up -d
if [ $? -eq 0 ]; then
    echo "Database stack deployed successfully."
else
    echo "Failed to deploy database stack."
    exit 1
fi

# 3. Deploy Application Stack
echo -e "${GREEN}3. Deploying Application Stack (Telegram Scraper)...${NC}"
docker-compose -f docker-compose.yaml up -d --build
if [ $? -eq 0 ]; then
    echo "Application stack deployed successfully."
else
    echo "Failed to deploy application stack."
    exit 1
fi

# 4. Verification
echo -e "${BLUE}=== Deployment Status ===${NC}"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "telegram|postgres|adminer"

echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "Adminer UI: https://adminer.mooh.me (Tailscale Only)"
echo -e "Dashboard: https://job.mooh.me (Public)"
