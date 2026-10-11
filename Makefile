# Drone Trainer Makefile
# 
# This Makefile provides convenience commands for building and running the application.

.PHONY: help init install mavlink run clean test

PYTHON ?= python

# Headless defaults so tests never need a display, audio device or gamepad.
TEST_ENV = QT_QPA_PLATFORM=offscreen SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy

# Default target
help:
	@echo "Drone Trainer - Available Commands:"
	@echo ""
	@echo "  make init       - Initialize submodules and install dependencies"
	@echo "  make install    - Install Python dependencies from requirements.txt"
	@echo "  make mavlink    - Build DTRG MAVLink dialect"
	@echo "  make run        - Run the application"
	@echo "  make clean      - Clean generated files"
	@echo "  make test       - Run the unit test suite (headless)"
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
	$(PYTHON) -m pip install -r requirements.txt

# Build DTRG MAVLink dialect
mavlink: submodules
	@echo "=== Building DTRG MAVLink Dialect ==="
	@if [ -f "libs/dtrg-mavlink/pymavlink/generator/mavgen.py" ]; then \
		$(PYTHON) scripts/build_mavlink.py --dialect dtrg; \
	else \
		echo "Error: DTRG-Mavlink submodule not found. Run 'make submodules' first."; \
		exit 1; \
	fi

# Run the application
run:
	@echo "=== Starting Drone Trainer ==="
	$(PYTHON) main.py

# Clean generated files
clean:
	@echo "=== Cleaning Generated Files ==="
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -f libs/dtrg-mavlink/pymavlink/dialects/v20/dtrg.py 2>/dev/null || true
	@echo "Clean complete"

# Run tests
test:
	@echo "=== Running Tests ==="
	$(TEST_ENV) $(PYTHON) -m unittest discover -s tests -p "test_*.py" -v
