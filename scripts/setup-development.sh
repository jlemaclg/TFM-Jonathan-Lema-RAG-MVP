#!/bin/bash

# Agentic RAG MVP - Setup Script
# This script sets up the entire development environment

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running on Windows
if [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
    print_error "This script is designed for Unix-like systems. For Windows, please follow the manual setup instructions in README.md"
    exit 1
fi

# Check prerequisites
print_status "Checking prerequisites..."

# Check Python
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed. Please install Python 3.11 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
if [[ "$(printf '%s\n' "$PYTHON_VERSION" "3.11" | sort -V | head -n1)" != "3.11" ]]; then
    print_error "Python 3.11 or higher is required. Current version: $PYTHON_VERSION"
    exit 1
fi
print_success "Python $PYTHON_VERSION found"

# Check Docker
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker."
    exit 1
fi
print_success "Docker found"

# Check Docker Compose
if ! command -v docker-compose &> /dev/null; then
    print_error "Docker Compose is not installed. Please install Docker Compose."
    exit 1
fi
print_success "Docker Compose found"

# Check Git
if ! command -v git &> /dev/null; then
    print_error "Git is not installed. Please install Git."
    exit 1
fi
print_success "Git found"

print_status "Prerequisites check completed successfully!"

# Create virtual environment
print_status "Creating Python virtual environment..."
python3 -m venv .venv
print_success "Virtual environment created"

# Activate virtual environment
print_status "Activating virtual environment..."
source .venv/bin/activate
print_success "Virtual environment activated"

# Upgrade pip
print_status "Upgrading pip..."
pip install --upgrade pip
print_success "Pip upgraded"

# Install development dependencies
print_status "Installing development dependencies..."
pip install -r requirements-dev.txt
print_success "Development dependencies installed"

# Copy environment file
if [ ! -f .env ]; then
    print_status "Creating .env file from template..."
    cp .env.example .env
    print_warning "Please edit .env file with your actual configuration values"
else
    print_success ".env file already exists"
fi

# Start infrastructure services
print_status "Starting infrastructure services with Docker Compose..."
docker-compose up -d postgres minio chroma redis traefik
print_success "Infrastructure services started"

# Wait for services to be ready
print_status "Waiting for services to be ready..."
sleep 10

# Check if services are running
print_status "Checking service health..."

# Function to check service health
check_service() {
    local service_name=$1
    local url=$2
    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if curl -s --max-time 5 "$url" > /dev/null 2>&1; then
            print_success "$service_name is ready"
            return 0
        fi
        print_status "Waiting for $service_name... (attempt $attempt/$max_attempts)"
        sleep 2
        ((attempt++))
    done

    print_error "$service_name failed to start"
    return 1
}

# Check PostgreSQL
if docker-compose exec -T postgres pg_isready -U rag -d ragdb > /dev/null 2>&1; then
    print_success "PostgreSQL is ready"
else
    print_error "PostgreSQL is not ready"
fi

# Check MinIO
check_service "MinIO" "http://localhost:9000/minio/health/ready" || true

# Check ChromaDB
check_service "ChromaDB" "http://localhost:8000/api/v1/heartbeat" || true

# Check Redis
if docker-compose exec -T redis redis-cli ping | grep -q PONG; then
    print_success "Redis is ready"
else
    print_warning "Redis might not be ready yet"
fi

# Create logs directory
print_status "Creating logs directory..."
mkdir -p logs
print_success "Logs directory created"

# Initialize pre-commit hooks
print_status "Setting up pre-commit hooks..."
pre-commit install
print_success "Pre-commit hooks installed"

# Run initial tests
print_status "Running initial health checks..."
python3 -c "import sys; print(f'Python version: {sys.version}')" || print_error "Python check failed"

# Create .gitkeep files for empty directories
print_status "Setting up project structure..."
mkdir -p docs/diagrams
mkdir -p tests/integration
mkdir -p tests/e2e
touch docs/diagrams/.gitkeep
touch tests/integration/.gitkeep
touch tests/e2e/.gitkeep
print_success "Project structure initialized"

print_success "🎉 Setup completed successfully!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your actual configuration"
echo "2. Start individual services: uvicorn services.auth-svc.app.main:app --reload --port 8101"
echo "3. Run tests: pytest"
echo "4. Visit http://localhost:8080 for Traefik dashboard"
echo ""
echo "For detailed instructions, see README.md"
echo ""
print_warning "Remember to set your OPENAI_API_KEY in .env file"
