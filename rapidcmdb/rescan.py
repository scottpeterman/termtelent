#!/usr/bin/env python3
"""
Go SNMP CLI Rescan Wrapper
Reads previous scan results and performs efficient rescans only on subnets with discovered devices.
"""

import json
import os
import sys
import subprocess
import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set
import ipaddress

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GoSNMPRescanWrapper:
    def __init__(self, gosnmp_path: str = "gosnmpcli.exe"):
        self.gosnmp_path = gosnmp_path
        self.rescans_dir = Path("rescans")
        self.rescans_dir.mkdir(exist_ok=True)

        # Default SNMP configuration - matches your example exactly
        self.default_config = {
            "timeout": "4s",
            "concurrency": 80,
            "communities": ["public", "Sbcdz302"],
            "username": "svc_netautomation",
            "auth_protocol": "SHA",
            "auth_key": "4qKUQCG#Q!CiVLZtFS7J",
            "priv_protocol": "AES128",
            "priv_key": "4qKUQCG#Q!CiVLZtFS7J",
            "fingerprint_type": "full",
            "enable_db": True
        }

    def load_previous_scan(self, scan_file: str) -> Dict:
        """Load previous scan results from JSON file"""
        try:
            with open(scan_file, 'r') as f:
                data = json.load(f)
            logger.info(f"Loaded previous scan: {scan_file}")
            logger.info(f"  Total devices: {data.get('total_devices', 0)}")
            logger.info(f"  Last updated: {data.get('last_updated', 'unknown')}")
            return data
        except Exception as e:
            logger.error(f"Failed to load scan file {scan_file}: {e}")
            return {}

    def extract_active_subnets(self, scan_data: Dict) -> Set[str]:
        """Extract subnets that have active devices from scan data"""
        active_subnets = set()

        # Get subnets from statistics
        if 'statistics' in scan_data and 'devices_per_subnet' in scan_data['statistics']:
            for subnet, device_count in scan_data['statistics']['devices_per_subnet'].items():
                if device_count > 0:
                    active_subnets.add(subnet)
                    logger.info(f"Found active subnet: {subnet} ({device_count} devices)")

        # Fallback: extract subnets from device data if available
        if not active_subnets and 'devices' in scan_data:
            for device_id, device_data in scan_data['devices'].items():
                primary_ip = device_data.get('primary_ip', '')
                if primary_ip:
                    try:
                        # Convert IP to /24 subnet
                        ip = ipaddress.IPv4Address(primary_ip)
                        network = ipaddress.IPv4Network(f"{ip}/24", strict=False)
                        subnet = str(network)
                        active_subnets.add(subnet)
                        logger.info(f"Extracted subnet from device IP: {subnet}")
                    except Exception as e:
                        logger.warning(f"Could not parse IP {primary_ip}: {e}")

        return active_subnets

    def generate_rescan_command(self, subnet: str, output_prefix: str, config: Dict = None) -> List[str]:
        """Generate gosnmpcli command for rescanning a subnet"""
        if config is None:
            config = self.default_config

        # Generate output filenames WITHOUT timestamps for consistency
        subnet_safe = subnet.replace('/', '_').replace('.', '_')

        db_file = self.rescans_dir / f"{output_prefix}_{subnet_safe}.json"
        csv_file = self.rescans_dir / f"{output_prefix}_{subnet_safe}.csv"

        # Build command - exactly like the example with both SNMPv2c and SNMPv3
        cmd = [
            self.gosnmp_path,
            "-mode", "scan",
            "-target", subnet,
            "-timeout", config.get("timeout", "4s"),
            "-concurrency", str(config.get("concurrency", 80)),
            "-communities", ",".join(config.get("communities", ["public", "Sbcdz302"])),
            "-snmp-version", "3",  # Always use version 3 for dual protocol support
            "-username", config.get("username", "svc_netautomation"),
            "-auth-protocol", config.get("auth_protocol", "SHA"),
            "-auth-key", config.get("auth_key", "4qKUQCG#Q!CiVLZtFS7J"),
            "-priv-protocol", config.get("priv_protocol", "AES128"),
            "-priv-key", config.get("priv_key", "4qKUQCG#Q!CiVLZtFS7J"),
            "-fingerprint-type", config.get("fingerprint_type", "full"),
            "-enable-db",
            "-database", str(db_file),
            "-output", "csv",
            "-output-file", str(csv_file)
        ]

        # Add config file if specified
        if config.get("config_path"):
            cmd.extend(["-config", config["config_path"]])

        return cmd, db_file, csv_file

    def run_rescan(self, cmd: List[str], subnet: str) -> bool:
        """Execute rescan command with real-time output streaming"""
        logger.info(f"Starting rescan of subnet: {subnet}")
        logger.info(f"Command: {' '.join(cmd)}")

        try:
            # Start the process with streaming output and proper encoding for Windows
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Merge stderr into stdout
                text=True,
                bufsize=1,  # Line buffered
                universal_newlines=True,
                encoding='utf-8',  # Force UTF-8 encoding
                errors='replace'  # Replace problematic characters instead of failing
            )

            # Stream output in real-time
            output_lines = []
            while True:
                line = process.stdout.readline()
                if line == '' and process.poll() is not None:
                    break
                if line:
                    line = line.rstrip()
                    output_lines.append(line)
                    # Print progress lines immediately
                    if any(keyword in line.lower() for keyword in [
                        'progress:', 'found:', 'scanning', 'complete', 'summary:',
                        'results:', 'devices', 'responding', 'snmp', '✅', '🔍', '📊'
                    ]):
                        logger.info(f"  [{subnet}] {line}")
                    elif any(keyword in line.lower() for keyword in ['error', 'failed', 'warning']):
                        # Don't treat YAML config warnings as fatal errors
                        if 'vendor_fingerprints.yaml' in line and 'cannot find' in line:
                            logger.warning(f"  [{subnet}] {line}")
                        else:
                            logger.warning(f"  [{subnet}] {line}")

            # Wait for process to complete
            return_code = process.wait()

            if return_code == 0:
                logger.info(f"✅ Successfully rescanned {subnet}")

                # Log final summary from output
                for line in output_lines:
                    if any(keyword in line.lower() for keyword in ['summary:', 'scan complete', 'results:']):
                        logger.info(f"  [{subnet}] {line}")

                return True
            else:
                logger.error(f"❌ Rescan failed for {subnet} (exit code: {return_code})")

                # Log error lines
                for line in output_lines[-10:]:  # Last 10 lines for error context
                    if line.strip():
                        logger.error(f"  [{subnet}] {line}")

                return False

        except subprocess.TimeoutExpired:
            logger.error(f"⏰ Rescan timeout for {subnet}")
            try:
                process.kill()
            except:
                pass
            return False
        except Exception as e:
            logger.error(f"💥 Exception during rescan of {subnet}: {e}")
            return False

    def rescan_from_previous(self, scan_files: List[str], output_prefix: str = "rescan",
                             config: Dict = None, dry_run: bool = False) -> Dict:
        """Perform rescans based on previous scan results"""

        if config is None:
            config = self.default_config

        all_active_subnets = set()
        scan_summary = {
            "processed_files": [],
            "active_subnets": set(),
            "successful_rescans": [],
            "failed_rescans": [],
            "skipped_rescans": [],
            "total_subnets": 0,
            "start_time": datetime.now().isoformat()
        }

        # Process all input scan files
        for scan_file in scan_files:
            if not os.path.exists(scan_file):
                logger.warning(f"Scan file not found: {scan_file}")
                continue

            logger.info(f"Processing scan file: {scan_file}")
            scan_data = self.load_previous_scan(scan_file)

            if not scan_data:
                logger.warning(f"No data loaded from {scan_file}")
                continue

            scan_summary["processed_files"].append(scan_file)

            # Extract active subnets
            active_subnets = self.extract_active_subnets(scan_data)
            all_active_subnets.update(active_subnets)

            logger.info(f"Found {len(active_subnets)} active subnets in {scan_file}")

        scan_summary["active_subnets"] = all_active_subnets
        scan_summary["total_subnets"] = len(all_active_subnets)

        if not all_active_subnets:
            logger.warning("No active subnets found in any scan files!")
            return scan_summary

        logger.info(f"Total unique active subnets to rescan: {len(all_active_subnets)}")

        # Perform rescans with real-time output and skip existing files
        for i, subnet in enumerate(sorted(all_active_subnets), 1):
            logger.info(f"📡 Processing subnet {i}/{len(all_active_subnets)}: {subnet}")

            # Generate command and get output file paths
            cmd, db_file, csv_file = self.generate_rescan_command(subnet, output_prefix, config)

            # Check if output files already exist
            if db_file.exists() and csv_file.exists():
                logger.info(f"⏭️  SKIPPING {subnet} - Output files already exist:")
                logger.info(f"     JSON: {db_file}")
                logger.info(f"     CSV:  {csv_file}")
                scan_summary["skipped_rescans"].append(subnet)
                continue
            elif db_file.exists() or csv_file.exists():
                logger.warning(f"⚠️  Partial files exist for {subnet}:")
                if db_file.exists():
                    logger.warning(f"     JSON exists: {db_file}")
                if csv_file.exists():
                    logger.warning(f"     CSV exists:  {csv_file}")
                logger.info(f"     Continuing scan to complete missing files...")

            if dry_run:
                logger.info(f"[DRY RUN] Would execute: {' '.join(cmd)}")
                scan_summary["successful_rescans"].append(subnet)
                continue

            # Execute rescan with streaming output
            logger.info(f"🚀 Starting live scan of {subnet}...")
            logger.info(f"     Output JSON: {db_file}")
            logger.info(f"     Output CSV:  {csv_file}")

            if self.run_rescan(cmd, subnet):
                scan_summary["successful_rescans"].append(subnet)
                logger.info(f"🎉 Completed {subnet} ({i}/{len(all_active_subnets)})")
            else:
                scan_summary["failed_rescans"].append(subnet)
                logger.error(f"💥 Failed {subnet} ({i}/{len(all_active_subnets)})")

            # Add separator between subnets
            if i < len(all_active_subnets):
                logger.info("-" * 50)

        # Final summary
        scan_summary["end_time"] = datetime.now().isoformat()
        scan_summary["duration"] = str(datetime.fromisoformat(scan_summary["end_time"]) -
                                       datetime.fromisoformat(scan_summary["start_time"]))

        return scan_summary

    def print_summary(self, summary: Dict):
        """Print rescan summary"""
        logger.info("=" * 60)
        logger.info("RESCAN SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Processed files: {len(summary['processed_files'])}")
        logger.info(f"Active subnets found: {summary['total_subnets']}")
        logger.info(f"Successful rescans: {len(summary['successful_rescans'])}")
        logger.info(f"Skipped rescans: {len(summary['skipped_rescans'])}")
        logger.info(f"Failed rescans: {len(summary['failed_rescans'])}")
        logger.info(f"Duration: {summary.get('duration', 'unknown')}")

        if summary['successful_rescans']:
            logger.info("✅ Successfully rescanned:")
            for subnet in summary['successful_rescans']:
                logger.info(f"  - {subnet}")

        if summary['skipped_rescans']:
            logger.info("⏭️  Skipped (already exist):")
            for subnet in summary['skipped_rescans']:
                logger.info(f"  - {subnet}")

        if summary['failed_rescans']:
            logger.info("❌ Failed rescans:")
            for subnet in summary['failed_rescans']:
                logger.info(f"  - {subnet}")

        logger.info(f"📁 Output files saved to: {self.rescans_dir}")
        logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Go SNMP CLI Rescan Wrapper - Efficient rescanning based on previous results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Rescan from single previous scan file
  python rescan_wrapper.py scan_results.json

  # Rescan from multiple scan files with custom prefix
  python rescan_wrapper.py scan1.json scan2.json -p "weekly_rescan"

  # Dry run to see what would be scanned
  python rescan_wrapper.py scan_results.json --dry-run

  # Custom SNMP configuration
  python rescan_wrapper.py scan_results.json --timeout 6s --concurrency 50

  # SNMPv2c only
  python rescan_wrapper.py scan_results.json --snmp-version 2 --communities "public,private"
        """
    )

    # Required arguments
    parser.add_argument('scan_files', nargs='+',
                        help='Previous scan result files (JSON format)')

    # Optional arguments
    parser.add_argument('-p', '--prefix', default='rescan',
                        help='Output filename prefix (default: rescan)')
    parser.add_argument('--gosnmp-path', default='gosnmpcli.exe',
                        help='Path to gosnmpcli executable (default: gosnmpcli.exe)')
    parser.add_argument('--config-path',
                        help='Path to vendor fingerprints YAML config file')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be scanned without executing')

    # SNMP configuration
    parser.add_argument('--timeout', default='4s',
                        help='SNMP timeout (default: 4s)')
    parser.add_argument('--concurrency', type=int, default=80,
                        help='Scan concurrency (default: 80)')
    parser.add_argument('--communities', default='public,Sbcdz302',
                        help='SNMP communities (default: public,Sbcdz302)')
    parser.add_argument('--username', default='svc_netautomation',
                        help='SNMPv3 username')
    parser.add_argument('--auth-protocol', default='SHA', choices=['MD5', 'SHA'],
                        help='SNMPv3 auth protocol (default: SHA)')
    parser.add_argument('--auth-key', default='4qKUQCG#Q!CiVLZtFS7J',
                        help='SNMPv3 auth key')
    parser.add_argument('--priv-protocol', default='AES128',
                        choices=['DES', 'AES128', 'AES192', 'AES256'],
                        help='SNMPv3 privacy protocol (default: AES128)')
    parser.add_argument('--priv-key', default='4qKUQCG#Q!CiVLZtFS7J',
                        help='SNMPv3 privacy key')

    # Logging
    parser.add_argument('--verbose', action='store_true',
                        help='Verbose logging')
    parser.add_argument('--quiet', action='store_true',
                        help='Quiet mode (errors only)')

    args = parser.parse_args()

    # Configure logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger().setLevel(logging.ERROR)

    # Build configuration - matches your example exactly
    config = {
        "timeout": args.timeout,
        "concurrency": args.concurrency,
        "communities": [c.strip() for c in args.communities.split(',')],
        "username": args.username,
        "auth_protocol": args.auth_protocol,
        "auth_key": args.auth_key,
        "priv_protocol": args.priv_protocol,
        "priv_key": args.priv_key,
        "fingerprint_type": "full",
        "enable_db": True,
        "config_path": args.config_path
    }

    # Validate scan files exist
    missing_files = [f for f in args.scan_files if not os.path.exists(f)]
    if missing_files:
        logger.error(f"Scan files not found: {missing_files}")
        sys.exit(1)

    # Create wrapper and run rescans
    wrapper = GoSNMPRescanWrapper(gosnmp_path=args.gosnmp_path)

    logger.info(f"Starting rescan wrapper for {len(args.scan_files)} scan files")
    if args.dry_run:
        logger.info("🔍 DRY RUN MODE - No actual scans will be performed")

    try:
        summary = wrapper.rescan_from_previous(
            scan_files=args.scan_files,
            output_prefix=args.prefix,
            config=config,
            dry_run=args.dry_run
        )

        wrapper.print_summary(summary)

        # Exit with error code if any rescans failed
        if summary['failed_rescans'] and not args.dry_run:
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Rescan interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Rescan failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()