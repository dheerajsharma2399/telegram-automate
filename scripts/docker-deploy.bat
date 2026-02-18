@echo off
REM Docker deployment script for Telegram Job Scraper (Windows)
REM Handles development and production deployments

setlocal enabledelayedexpansion

REM Configuration
set COMPOSE_FILE=docker-compose.yml
set COMPOSE_DEV_FILE=docker-compose.dev.yml
set ENV_FILE=.env.docker
set DEFAULT_ENV_FILE=.env.example

REM Colors (limited support in Windows CMD)
set RED=[91m
set GREEN=[92m
set YELLOW=[93m
set BLUE=[94m
set NC=[0m

REM Functions
:log_info
echo %BLUE%[INFO]%NC% %~1
goto :eof

:log_success
echo %GREEN%[SUCCESS]%NC% %~1
goto :eof

:log_warning
echo %YELLOW%[WARNING]%NC% %~1
goto :eof

:log_error
echo %RED%[ERROR]%NC% %~1
goto :eof

REM Usage information
:usage
echo Telegram Job Scraper Docker Deployment Script
echo.
echo Usage: %0 [COMMAND] [OPTIONS]
echo.
echo Commands:
echo   dev       Start development environment
echo   prod      Start production environment
echo   stop      Stop all services
echo   restart   Restart all services
echo   logs      Show logs for all services
echo   status    Show status of all services
echo   clean     Clean up containers and volumes
echo   build     Build Docker images
echo   update    Update and redeploy
echo.
echo Options:
echo   -f, --force    Force operation without confirmation
echo   -h, --help     Show this help message
echo.
echo Examples:
echo   %0 dev                    # Start development environment
echo   %0 prod --force          # Start production environment (no prompt)
echo   %0 logs -f               # Follow logs in real-time
echo   %0 status                # Check service status
goto :eof

REM Check dependencies
:check_dependencies
call :log_info "Checking dependencies..."

docker --version >nul 2>&1
if !errorlevel! neq 0 (
    call :log_error "Docker is not installed. Please install Docker first."
    exit /b 1
)

docker-compose --version >nul 2>&1
if !errorlevel! neq 0 (
    call :log_error "Docker Compose is not installed. Please install Docker Compose first."
    exit /b 1
)

call :log_success "Dependencies check passed"
goto :eof

REM Setup environment
:setup_environment
call :log_info "Setting up environment..."

if not exist "%ENV_FILE%" (
    call :log_warning "Environment file %ENV_FILE% not found"
    if exist "%DEFAULT_ENV_FILE%" (
        call :log_info "Copying %DEFAULT_ENV_FILE% to %ENV_FILE%"
        copy "%DEFAULT_ENV_FILE%" "%ENV_FILE%" >nul
        call :log_warning "Please edit %ENV_FILE% with your actual configuration values"
    ) else (
        call :log_error "No environment template found. Creating minimal %ENV_FILE%"
        (
            echo REM Telegram Configuration
            echo TELEGRAM_API_ID=your_api_id
            echo TELEGRAM_API_HASH=your_api_hash
            echo TELEGRAM_PHONE=your_phone
            echo TELEGRAM_GROUP_USERNAME=job_group
            echo AUTHORIZED_USER_IDS=your_user_id
            echo ADMIN_USER_ID=your_admin_id
            echo.
            echo REM LLM Configuration
            echo OPENROUTER_API_KEY=your_openrouter_key
            echo OPENROUTER_MODEL=anthropic/claude-3.5-sonnet
            echo OPENROUTER_FALLBACK_MODEL=openai/gpt-4o-mini
            echo.
            echo REM Google Sheets Configuration
            echo GOOGLE_CREDENTIALS_JSON={"type":"service_account","project_id":"your_project","private_key_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n","client_email":"...","client_id":"...","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs","client_x509_cert_url":"..."}
            echo SPREADSHEET_ID=your_spreadsheet_id
            echo.
            echo REM Security
            echo FLASK_SECRET_KEY=your_secret_key_here
        ) > "%ENV_FILE%"
    )
)
goto :eof

REM Build Docker images
:build_images
call :log_info "Building Docker images..."
docker-compose build --no-cache
if !errorlevel! neq 0 (
    call :log_error "Failed to build Docker images"
    exit /b 1
)
call :log_success "Docker images built successfully"
goto :eof

REM Start development environment
:start_dev
call :log_info "Starting development environment..."
call :setup_environment
docker-compose -f "%COMPOSE_FILE%" -f "%COMPOSE_DEV_FILE%" up -d
if !errorlevel! neq 0 (
    call :log_error "Failed to start development environment"
    exit /b 1
)
call :log_success "Development environment started"
call :log_info "Access the dashboard at: http://localhost:5000"
call :log_info "View logs with: %0 logs -f"
goto :eof

REM Start production environment
:start_prod
call :log_info "Starting production environment..."
call :setup_environment
docker-compose -f "%COMPOSE_FILE%" up -d
if !errorlevel! neq 0 (
    call :log_error "Failed to start production environment"
    exit /b 1
)
call :log_success "Production environment started"
call :log_info "Access the dashboard at: http://localhost:5000"
goto :eof

REM Stop services
:stop_services
call :log_info "Stopping all services..."
docker-compose down
if !errorlevel! neq 0 (
    call :log_error "Failed to stop services"
    exit /b 1
)
call :log_success "All services stopped"
goto :eof

REM Restart services
:restart_services
call :log_info "Restarting all services..."
docker-compose restart
if !errorlevel! neq 0 (
    call :log_error "Failed to restart services"
    exit /b 1
)
call :log_success "All services restarted"
goto :eof

REM Show logs
:show_logs
set "FOLLOW=%~1"
if "%FOLLOW%"=="-f" (
    call :log_info "Following logs (Ctrl+C to exit)..."
    docker-compose logs -f
) else (
    docker-compose logs --tail=50
)
goto :eof

REM Show status
:show_status
call :log_info "Service Status:"
docker-compose ps
call :log_info ""
call :log_info "Resource Usage:"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}"
goto :eof

REM Clean up
:clean_up
call :log_warning "This will remove all containers, volumes, and networks. Are you sure? (y/N)"
set /p "response=Continue (y/N): "
if /i "%response%"=="y" (
    call :log_info "Cleaning up Docker resources..."
    docker-compose down -v --remove-orphans
    docker system prune -f
    call :log_success "Cleanup completed"
) else (
    call :log_info "Cleanup cancelled"
)
goto :eof

REM Update deployment
:update_deployment
call :log_info "Updating deployment..."
call :log_info "Building and restarting services..."
call :build_images
docker-compose up -d
if !errorlevel! neq 0 (
    call :log_error "Failed to update deployment"
    exit /b 1
)
call :log_success "Deployment updated successfully"
goto :eof

REM Main script logic
if "%~1"=="" (
    goto :usage
    exit /b 1
)

if "%~1"=="-h" goto :usage
if "%~1"=="--help" goto :usage

call :check_dependencies
if !errorlevel! neq 0 (
    exit /b 1
)

if "%~1"=="dev" (
    set "FORCE=%~2"
    if not "%FORCE%"=="-f" (
        call :log_warning "Starting development environment"
        set /p "response=Continue? (Y/n): "
        if /i "!response!"=="n" (
            call :log_info "Cancelled"
            exit /b 0
        )
    )
    goto :start_dev
)

if "%~1"=="prod" (
    set "FORCE=%~2"
    if not "%FORCE%"=="-f" (
        call :log_warning "Starting production environment"
        set /p "response=Continue? (y/N): "
        if /i not "!response%"=="y" (
            call :log_info "Cancelled"
            exit /b 0
        )
    )
    goto :start_prod
)

if "%~1"=="stop" goto :stop_services
if "%~1"=="restart" goto :restart_services
if "%~1"=="logs" goto :show_logs
if "%~1"=="status" goto :show_status
if "%~1"=="clean" goto :clean_up
if "%~1"=="build" goto :build_images
if "%~1"=="update" goto :update_deployment

call :log_error "Unknown command: %~1"
goto :usage