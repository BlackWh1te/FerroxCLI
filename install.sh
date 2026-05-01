#!/bin/bash
# Ferrox CLI Setup Script for macOS/Linux
# Run this script: chmod +x install.sh && ./install.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() {
    echo -e "${CYAN}[Ferrox]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_python() {
    if command -v python3 &> /dev/null; then
        return 0
    elif command -v python &> /dev/null; then
        return 0
    else
        return 1
    fi
}

get_python() {
    if command -v python3 &> /dev/null; then
        echo "python3"
    elif command -v python &> /dev/null; then
        echo "python"
    else
        echo ""
    fi
}

ensure_config_dir() {
    config_dir="$HOME/.ferrox"
    if [ ! -d "$config_dir" ]; then
        mkdir -p "$config_dir"
        log_info "Created config directory: $config_dir"
    fi
    echo "$config_dir"
}

install_ferrox() {
    log_info "Setting up Ferrox CLI..."

    if ! check_python; then
        log_error "Python not found. Please install Python 3.8+"
        echo "On macOS: brew install python3"
        echo "On Linux: sudo apt install python3 (Debian/Ubuntu)"
        exit 1
    fi

    PYTHON=$(get_python)
    PYTHON_VERSION=$($PYTHON --version 2>&1)
    log_success "Found $PYTHON_VERSION"

    # Create config directory
    config_dir=$(ensure_config_dir)

    # Check pip
    if ! $PYTHON -m pip --version &> /dev/null; then
        log_info "Installing pip..."
        $PYTHON -m ensurepip --upgrade 2>/dev/null || true
    fi

    # Install dependencies
    log_info "Installing dependencies..."
    dependencies=("click" "rich" "prompt_toolkit" "pydantic" "httpx")

    for dep in "${dependencies[@]}"; do
        if $PYTHON -m pip install "$dep" --quiet 2>/dev/null; then
            log_success "Installed $dep"
        else
            log_error "Failed to install $dep"
            exit 1
        fi
    done

    # Install Ferrox package
    log_info "Installing Ferrox package..."
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    if $PYTHON -m pip install -e "$script_dir" --quiet 2>/dev/null; then
        log_success "Installed Ferrox"
    else
        log_error "Failed to install Ferrox package"
        exit 1
    fi

    # Create default config if not exists
    config_file="$config_dir/config.json"
    if [ ! -f "$config_file" ]; then
        cat > "$config_file" << 'EOF'
{
  "provider_name": "custom",
  "base_url": "https://api.openai.com/v1",
  "api_key": "your-api-key-here",
  "default_model": null,
  "timeout": 30,
  "max_tokens": 4096,
  "temperature": 0.7
}
EOF
        log_success "Created default config at $config_file"
        log_warning "Please edit the config file and add your API key"
    fi

    echo ""
    echo "========================================"
    echo -e "  ${GREEN}Ferrox installed successfully!${NC}"
    echo "========================================"
    echo ""
    echo "Run 'ferrox' to start the CLI."
    echo "Run 'ferrox config' to edit configuration."
    echo ""
    echo "First time setup:"
    echo "  1. Run: ferrox config"
    echo "  2. Update base_url and api_key"
    echo "  3. Run: ferrox models"
    echo "  4. Select your model"
    echo "  5. Run: ferrox"
    echo ""
}

uninstall_ferrox() {
    log_info "Uninstalling Ferrox..."

    PYTHON=$(get_python)

    $PYTHON -m pip uninstall ferrox -y 2>/dev/null || true
    log_success "Uninstalled Ferrox package"

    config_dir="$HOME/.ferrox"
    if [ -d "$config_dir" ]; then
        log_warning "Config directory kept at: $config_dir"
        echo "Remove manually with: rm -rf $config_dir"
    fi

    log_success "Uninstall complete"
}

# Main
case "${1:-install}" in
    install)
        install_ferrox
        ;;
    uninstall)
        uninstall_ferrox
        ;;
    *)
        echo "Usage: $0 [install|uninstall]"
        exit 1
        ;;
esac