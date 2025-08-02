#!/usr/bin/env python3
"""
Batch processor for JSON migration files.
Processes all JSON files in a specified folder using db_scan_import.py
"""

import os
import sys
import subprocess
import argparse
import glob
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def process_json_files(folder_path, import_script="db_scan_import.py", dry_run=False):
    """
    Process all JSON files in the specified folder using the migration tool.

    Args:
        folder_path (str): Path to folder containing JSON files
        import_script (str): Path to the db_scan_import.py script
        dry_run (bool): If True, only show what would be processed without running
    """

    # Convert to Path object for easier handling
    folder = Path(folder_path)

    if not folder.exists():
        logger.error(f"Folder does not exist: {folder_path}")
        return False

    if not folder.is_dir():
        logger.error(f"Path is not a directory: {folder_path}")
        return False

    # Find all JSON files in the folder
    json_files = list(folder.glob("*.json"))

    if not json_files:
        logger.warning(f"No JSON files found in {folder_path}")
        return True

    logger.info(f"Found {len(json_files)} JSON files to process")

    # Sort files for consistent processing order
    json_files.sort()

    processed_count = 0
    failed_count = 0

    for json_file in json_files:
        logger.info(f"Processing: {json_file.name}")

        if dry_run:
            logger.info(f"[DRY RUN] Would process: {json_file}")
            processed_count += 1
            continue

        try:
            # Build the command
            cmd = [
                sys.executable,  # Use the same Python interpreter
                import_script,
                "--scan-file",
                str(json_file)
            ]

            # Execute the command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout per file
            )

            if result.returncode == 0:
                logger.info(f"Successfully processed: {json_file.name}")
                processed_count += 1

                # Log any output from the import script
                if result.stdout:
                    for line in result.stdout.strip().split('\n'):
                        if line.strip():
                            logger.info(f"  {line}")
            else:
                logger.error(f"Failed to process {json_file.name}")
                logger.error(f"Return code: {result.returncode}")
                if result.stderr:
                    logger.error(f"Error output: {result.stderr}")
                failed_count += 1

        except subprocess.TimeoutExpired:
            logger.error(f"Timeout processing {json_file.name}")
            failed_count += 1
        except Exception as e:
            logger.error(f"Error processing {json_file.name}: {str(e)}")
            failed_count += 1

    # Summary
    logger.info(f"Processing complete:")
    logger.info(f"  Successfully processed: {processed_count}")
    logger.info(f"  Failed: {failed_count}")
    logger.info(f"  Total files: {len(json_files)}")

    return failed_count == 0


def main():
    parser = argparse.ArgumentParser(
        description="Batch process JSON files using db_scan_import.py"
    )
    parser.add_argument(
        "folder",
        help="Path to folder containing JSON files to process"
    )
    parser.add_argument(
        "--import-script",
        default="db_scan_import.py",
        help="Path to the db_scan_import.py script (default: db_scan_import.py)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without actually running the import"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Verify the import script exists
    if not Path(args.import_script).exists():
        logger.error(f"Import script not found: {args.import_script}")
        sys.exit(1)

    # Process the files
    success = process_json_files(
        args.folder,
        args.import_script,
        args.dry_run
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()