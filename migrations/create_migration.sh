#!/bin/bash
# Script to create and manage database migrations for Auroqa

set -e  # Exit immediately if a command exits with a non-zero status

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print section headers
print_section() {
    echo -e "\n${YELLOW}=== $1 ===${NC}"
}

# Function to print success messages
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Function to print error messages
print_error() {
    echo -e "${RED}✗ $1${NC}"
    exit 1
}

# Check if a migration name was provided
if [ $# -eq 0 ]; then
    print_error "Please provide a name for the migration (e.g., ./create_migration.sh add_new_column)"
fi

# Get the migration name from the command line argument
MIGRATION_NAME=$1

# Get the current timestamp for versioning
TIMESTAMP=$(date +%Y%m%d%H%M%S)

# Create the migration file name
MIGRATION_FILE="${TIMESTAMP}_${MIGRATION_NAME}.sql"

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Create the migration file
cat > "${SCRIPT_DIR}/${MIGRATION_FILE}" << EOF
-- Migration: ${MIGRATION_NAME}
-- Created at: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
-- Description: 

-- Write your SQL statements here
-- Example:
-- ALTER TABLE table_name ADD COLUMN column_name data_type;

-- To roll back this migration, you can add statements like:
-- -- ROLLBACK
-- -- ALTER TABLE table_name DROP COLUMN column_name;
EOF

print_success "Created migration file: ${MIGRATION_FILE}"
echo "Edit the file to add your SQL statements."

# Open the file in the default editor if available
if command -v code &> /dev/null; then
    code "${SCRIPT_DIR}/${MIGRATION_FILE}"
elif [ -n "$EDITOR" ]; then
    $EDITOR "${SCRIPT_DIR}/${MIGRATION_FILE}"
elif command -v nano &> /dev/null; then
    nano "${SCRIPT_DIR}/${MIGRATION_FILE}"
elif command -v vim &> /dev/null; then
    vim "${SCRIPT_DIR}/${MIGRATION_FILE}"
else
    echo "No editor found. Please edit the file manually."
fi
