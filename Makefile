# Drone Trainer Makefile
# 
# This Makefile provides convenience commands for building and running the application.

.PHONY: help init install mavlink run clean test

# Default target
help:
	@echo "Drone Trainer - Available Commands:"
	@echo ""
	@echo "  make init       - Initialize submodules and install dependencies"
	@echo "  make install    - Install Python dependencies from requirements.txt"
	@echo "  make mavlink    - Build DTRG MAVLink dialect"
	@echo "  make run        - Run the application"
	@echo "  make clean      - Clean generated files"
	@echo "  make test       - Run tests (if available)"
	@echo ""
	@echo "Quick Start:"
	@echo "  make init       - First time setup (submodules + deps + mavlink)"
	@echo "  make run        - Start the application"

# Initialize everything (first time setup)
init: submodules install mavlink
	@echo ""
	@echo "=== Initialization Complete ==="
	@echo "Run 'make run' to start the application"

# Initialize git submodules
submodules:
	@echo "=== Initializing Git Submodules ==="
	git submodule update --init --recursive

# Install Python dependencies
install:
	@echo "=== Installing Python Dependencies ==="
	pip install -r requirements.txt

# Build DTRG MAVLink dialect
mavlink: submodules
	@echo "=== Building DTRG MAVLink Dialect ==="
	@if [ -f "libs/dtrg-mavlink/pymavlink/generator/mavgen.py" ]; then \
		python scripts/build_mavlink.py --dialect dtrg; \
	else \
		echo "Error: DTRG-Mavlink submodule not found. Run 'make submodules' first."; \
		exit 1; \
	fi

# Run the application
run:
	@echo "=== Starting Drone Trainer ==="
	python main.py

# Clean generated files
clean:
	@echo "=== Cleaning Generated Files ==="
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -f libs/dtrg-mavlink/pymavlink/dialects/v20/dtrg.py 2>/dev/null || true
	@echo "Clean complete"

# Run tests (placeholder)
test:
	@echo "=== Running Tests ==="
	@echo "No tests configured yet"
