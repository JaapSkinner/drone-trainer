#!/usr/bin/env python3
"""
Build script for DTRG MAVLink Python bindings.

This script generates Python MAVLink message definitions from the DTRG-Mavlink
dialect XML files. The generated code is placed in the libs/dtrg-mavlink/pymavlink/dialects
directory and can then be imported by the mavlink_service.

Usage:
    python scripts/build_mavlink.py [--dialect DIALECT] [--output-dir DIR]

Options:
    --dialect DIALECT    The MAVLink dialect to build (default: dtrg)
    --output-dir DIR     Output directory for generated files
    --wire-protocol VER  Wire protocol version (default: 2.0)
    
This script is designed to be run as part of the CI/CD pipeline to ensure
that the MAVLink message definitions match those built into the custom PX4 firmware.

The DTRG dialect includes all standard PX4 messages plus custom DTRG messages
for the drone trainer system.
"""
import os
import sys
import argparse
import subprocess
from pathlib import Path


# Get the repository root directory
REPO_ROOT = Path(__file__).parent.parent.absolute()
DTRG_MAVLINK_DIR = REPO_ROOT / "libs" / "dtrg-mavlink"
PYMAVLINK_DIR = DTRG_MAVLINK_DIR / "pymavlink"
MESSAGE_DEFINITIONS_DIR = DTRG_MAVLINK_DIR / "message_definitions" / "v1.0"
DIALECTS_OUTPUT_DIR = PYMAVLINK_DIR / "dialects" / "v20"


def check_prerequisites():
    """Check that all prerequisites are met before building.
    
    Returns:
        bool: True if all prerequisites are met, False otherwise.
    """
    if not DTRG_MAVLINK_DIR.exists():
        print(f"ERROR: DTRG-Mavlink submodule not found at {DTRG_MAVLINK_DIR}")
        print("Run: git submodule update --init --recursive")
        return False
    
    if not (PYMAVLINK_DIR / "generator" / "mavgen.py").exists():
        print(f"ERROR: pymavlink generator not found at {PYMAVLINK_DIR}")
        print("Run: git submodule update --init --recursive")
        return False
    
    if not MESSAGE_DEFINITIONS_DIR.exists():
        print(f"ERROR: Message definitions not found at {MESSAGE_DEFINITIONS_DIR}")
        return False
    
    return True


def get_available_dialects():
    """Get list of available MAVLink dialects.
    
    Returns:
        list: List of available dialect names (without .xml extension)
    """
    dialects = []
    for xml_file in MESSAGE_DEFINITIONS_DIR.glob("*.xml"):
        dialects.append(xml_file.stem)
    return sorted(dialects)


def build_dialect(dialect_name: str, wire_protocol: str = "2.0", output_dir: Path = None):
    """Generate Python MAVLink bindings for a dialect.
    
    Args:
        dialect_name: Name of the dialect (e.g., 'dtrg', 'common')
        wire_protocol: MAVLink wire protocol version ('1.0' or '2.0')
        output_dir: Output directory (default: pymavlink/dialects/v20)
        
    Returns:
        bool: True if build succeeded, False otherwise.
    """
    xml_file = MESSAGE_DEFINITIONS_DIR / f"{dialect_name}.xml"
    if not xml_file.exists():
        print(f"ERROR: Dialect XML file not found: {xml_file}")
        print(f"Available dialects: {', '.join(get_available_dialects())}")
        return False
    
    if output_dir is None:
        output_dir = DIALECTS_OUTPUT_DIR
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Build command using pymavlink.tools.mavgen as module
    # This requires pymavlink to be installed (pip install pymavlink)
    cmd = [
        sys.executable,
        "-m",
        "pymavlink.tools.mavgen",
        f"--lang=Python3",
        f"--wire-protocol={wire_protocol}",
        f"--output={output_dir / dialect_name}.py",
        str(xml_file)
    ]
    
    print(f"Building {dialect_name} dialect (MAVLink {wire_protocol})...")
    print(f"  Input: {xml_file}")
    print(f"  Output: {output_dir / dialect_name}.py")
    print(f"  Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            cwd=str(DTRG_MAVLINK_DIR)
        )
        
        if result.returncode != 0:
            print(f"ERROR: mavgen failed with return code {result.returncode}")
            print(f"STDOUT: {result.stdout}")
            print(f"STDERR: {result.stderr}")
            return False
        
        print(f"  SUCCESS: Generated {dialect_name}.py")
        
        # Verify the output file exists
        output_file = output_dir / f"{dialect_name}.py"
        if output_file.exists():
            print(f"  File size: {output_file.stat().st_size} bytes")
        else:
            print(f"  WARNING: Output file not found at expected location")
            
        return True
        
    except Exception as e:
        print(f"ERROR: Failed to run mavgen: {e}")
        return False


def main():
    """Main entry point for the build script."""
    parser = argparse.ArgumentParser(
        description="Build DTRG MAVLink Python bindings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--dialect", "-d",
        default="dtrg",
        help="MAVLink dialect to build (default: dtrg)"
    )
    
    parser.add_argument(
        "--wire-protocol", "-w",
        default="2.0",
        choices=["1.0", "2.0"],
        help="MAVLink wire protocol version (default: 2.0)"
    )
    
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=None,
        help="Output directory for generated files"
    )
    
    parser.add_argument(
        "--list-dialects", "-l",
        action="store_true",
        help="List available dialects and exit"
    )
    
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Build all available dialects"
    )
    
    args = parser.parse_args()
    
    # Check prerequisites
    if not check_prerequisites():
        sys.exit(1)
    
    # List dialects if requested
    if args.list_dialects:
        print("Available dialects:")
        for dialect in get_available_dialects():
            print(f"  - {dialect}")
        sys.exit(0)
    
    # Build dialects
    if args.all:
        dialects = get_available_dialects()
        print(f"Building {len(dialects)} dialects...")
        failed = []
        for dialect in dialects:
            if not build_dialect(dialect, args.wire_protocol, args.output_dir):
                failed.append(dialect)
        
        if failed:
            print(f"\nFailed to build: {', '.join(failed)}")
            sys.exit(1)
        else:
            print(f"\nSuccessfully built {len(dialects)} dialects")
    else:
        if not build_dialect(args.dialect, args.wire_protocol, args.output_dir):
            sys.exit(1)
    
    print("\nMAVLink build complete!")
    print(f"Generated files are in: {args.output_dir or DIALECTS_OUTPUT_DIR}")
    print("\nTo use the DTRG dialect in the drone-trainer app:")
    print("    The mavlink_service will automatically load the DTRG dialect")
    print("    from libs/dtrg-mavlink/pymavlink/dialects/v20/dtrg.py")


if __name__ == "__main__":
    main()
