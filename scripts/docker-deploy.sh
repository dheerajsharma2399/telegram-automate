#!/bin/bash
# Docker deployment script for Telegram Job Scraper
# Handles development and production deployments

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Configuration
COMPOSE_FILE="docker-compose.yml"
COMPOSE_DEV_FILE="docker-compose.dev.yml"
ENV_FILE=".env.docker"
DEFAULT_ENV_FILE=".env.example"

# Usage information
usage() {
    echo "Telegram Job Scraper Docker Deployment Script"
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  dev       Start development environment"
    echo "  prod      Start production environment"
    echo "  stop      Stop all services"
    echo "  restart   Restart all services"
    echo "  logs      Show logs for all services"
    echo "  status    Show status of all services"
    echo "  clean     Clean up containers and volumes"
    echo "  build     Build Docker images"
    echo "  update    Update and redeploy"
    echo ""
    echo "Options:"
    echo "  -f, --force    Force operation without confirmation"
    echo "  -h, --help     Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 dev                    # Start development environment"
    echo "  $0 prod --force          # Start production environment (no prompt)"
    echo "  $0 logs -f               # Follow logs in real-time"
    echo "  $0 status                # Check service status"
}

# Check dependencies
check_dependencies() {
    log_info "Checking dependencies..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    log_success "Dependencies check passed"
}

# Setup environment
setup_environment() {
    log_info "Setting up environment..."
    
    if [ ! -f "$ENV_FILE" ]; then
        log_warning "Environment file $ENV_FILE not found"
        if [ -f "$DEFAULT_ENV_FILE" ]; then
            log_info "Copying $DEFAULT_ENV_FILE to $ENV_FILE"
            cp "$DEFAULT_ENV_FILE" "$ENV_FILE"
            log_warning "Please edit $ENV_FILE with your actual configuration values"
        else
            log_error "No environment template found. Creating minimal $ENV_FILE"
            cat > "$ENV_FILE" << EOF
# Telegram Configuration
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_PHONE=your_phone
TELEGRAM_GROUP_USERNAME=job_group
AUTHORIZED_USER_IDS=your_user_id
ADMIN_USER_ID=your_admin_id

# LLM Configuration
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet
OPENROUTER_FALLBACK_MODEL=openai/gpt-4o-mini

# Google Sheets Configuration
GOOGLE_CREDENTIALS_JSON={"type":"service_account","project_id":"your_project","private_key_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n","client_email":"...","client_id":"...","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs","client_x509_cert_url":"..."}
SPREADSHEET_ID=your_spreadsheet_id

# Security
FLASK_SECRET_KEY=your_secret_key_here
EOF
        fi
    fi
}

# Build Docker images
build_images() {
    log_info "Building Docker images..."
    docker-compose build --no-cache
    log_success "Docker images built successfully"
}

# Start development environment
start_dev() {
    log_info "Starting development environment..."
    setup_environment
    docker-compose -f "$COMPOSE_FILE" -f "$COMPOSE_DEV_FILE" up -d
    log_success "Development environment started"
    log_info "Access the dashboard at: http://localhost:5000"
    log_info "View logs with: $0 logs -f"
}

# Start production environment
start_prod() {
    log_info "Starting production environment..."
    setup_environment
    docker-compose -f "$COMPOSE_FILE" up -d
    log_success "Production environment started"
    log_info "Access the dashboard at: http://localhost:5000"
}

# Stop services
stop_services() {
    log_info "Stopping all services..."
    docker-compose down
    log_success "All services stopped"
}

# Restart services
restart_services() {
    log_info "Restarting all services..."
    docker-compose restart
    log_success "All services restarted"
}

# Show logs
show_logs() {
    local follow=$1
    if [ "$follow" = "-f" ] || [ "$follow" = "--follow" ]; then
        log_info "Following logs (Ctrl+C to exit)..."
        docker-compose logs -f
    else
        docker-compose logs --tail=50
    fi
}

# Show status
show_status() {
    log_info "Service Status:"
    docker-compose ps
    log_info ""
    log_info "Resource Usage:"
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}"
}

# Clean up
clean_up() {
    log_warning "This will remove all containers, volumes, and networks. Are you sure? (y/N)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        log_info "Cleaning up Docker resources..."
        docker-compose down -v --remove-orphans
        docker system prune -f
        log_success "Cleanup completed"
    else
        log_info "Cleanup cancelled"
    fi
}

# Update deployment
update_deployment() {
    log_info "Updating deployment..."
    log_info "Pulling latest changes..."
    
    if git status --porcelain | grep -q .; then
        log_warning "Working directory has uncommitted changes"
        read -p "Continue anyway? (y/N): " response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            log_info "Update cancelled"
            return
        fi
    fi
    
    log_info "Building and restarting services..."
    build_images
    docker-compose up -d
    log_success "Deployment updated successfully"
}

# Parse command line arguments
FORCE=false
COMMAND=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--force)
            FORCE=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        dev|prod|stop|restart|logs|status|clean|build|update)
            COMMAND="$1"
            shift
            ;;
        *)
            if [[ -z "$COMMAND" ]]; then
                log_error "Unknown command: $1"
                usage
                exit 1
            else
                shift
            fi
            ;;
    esac
done

# Check if command was provided
if [ -z "$COMMAND" ]; then
    usage
    exit 1
fi

# Main execution
main() {
    check_dependencies
    
    case $COMMAND in
        dev)
            if [ "$FORCE" = false ]; then
                log_warning "Starting development environment"
                read -p "Continue? (Y/n): " response
                if [[ "$response" =~ ^[Nn]$ ]]; then
                    log_info "Cancelled"
                    exit 0
                fi
            fi
            start_dev
            ;;
        prod)
            if [ "$FORCE" = false ]; then
                log_warning "Starting production environment"
                read -p "Continue? (y/N): " response
                if [[ ! "$response" =~ ^[Yy]$ ]]; then
                    log_info "Cancelled"
                    exit 0
                fi
            fi
            start_prod
            ;;
        stop)
            stop_services
            ;;
        restart)
            restart_services
            ;;
        logs)
            show_logs "$@"
            ;;
        status)
            show_status
            ;;
        clean)
            clean_up
            ;;
        build)
            build_images
            ;;
        update)
            update_deployment
            ;;
        *)
            log_error "Unknown command: $COMMAND"
            usage
            exit 1
            ;;
    esac
}

# Run main function
main "$@"