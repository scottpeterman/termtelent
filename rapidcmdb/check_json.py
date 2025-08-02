#!/usr/bin/env python3
"""
Enhanced JSON Discovery Data Analyzer
Focuses on identifying duplicates and data quality issues in network discovery JSON files
"""

import json
import csv
from datetime import datetime
from pathlib import Path
import argparse
from collections import defaultdict, Counter
import re
from typing import Dict, List, Set, Tuple


class EnhancedJSONAnalyzer:
    def __init__(self):
        self.devices = {}
        self.potential_duplicates = []
        self.vendor_stats = Counter()
        self.device_type_stats = Counter()
        self.confidence_stats = []

        # Conflict tracking
        self.ip_conflicts = defaultdict(list)
        self.mac_conflicts = defaultdict(list)
        self.serial_conflicts = defaultdict(list)
        self.hostname_conflicts = defaultdict(list)
        self.sysdescr_groups = defaultdict(list)

    def analyze_json_file(self, file_path):
        """Analyze JSON file with focus on duplicate detection"""
        print(f"Analyzing: {file_path}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error reading file: {e}")
            return None

        devices = data.get('devices', {})
        scan_metadata = data.get('scan_metadata', {})

        print(f"\nBASIC INFO:")
        print(f"  File size: {Path(file_path).stat().st_size:,} bytes")
        print(f"  Devices in JSON: {len(devices):,}")
        print(f"  Scan metadata: {scan_metadata}")

        # Store devices for analysis
        self.devices = devices

        return data

    def detect_duplicates(self):
        """Advanced duplicate detection using multiple criteria"""
        print(f"\nDUPLICATE DETECTION:")
        print(f"=" * 50)

        # Group devices by various identifiers
        by_ip = defaultdict(list)
        by_mac = defaultdict(list)
        by_serial = defaultdict(list)
        by_hostname = defaultdict(list)
        by_sysdescr = defaultdict(list)
        by_snmp_location = defaultdict(list)

        for device_id, device in self.devices.items():
            ip = device.get('primary_ip', '')
            mac = device.get('mac_address', '')
            serial = device.get('serial_number', '')
            hostname = device.get('sys_name', '').lower().strip()
            sysdescr = device.get('sys_descr', '').strip()
            location = device.get('location', '').strip()

            if ip:
                by_ip[ip].append((device_id, device))
            if mac and mac.lower() not in ['unknown', '', 'none']:
                by_mac[mac.lower()].append((device_id, device))
            if serial and serial.lower() not in ['unknown', '', 'none']:
                by_serial[serial].append((device_id, device))
            if hostname and hostname not in ['unknown', '', 'none']:
                by_hostname[hostname].append((device_id, device))
            if sysdescr:
                # Normalize system description for grouping
                normalized_sysdescr = self.normalize_sysdescr(sysdescr)
                by_sysdescr[normalized_sysdescr].append((device_id, device))
            if location and location.lower() not in ['unknown', '', 'none']:
                by_snmp_location[location].append((device_id, device))

        # Find conflicts
        duplicate_groups = []

        print(f"IP Address Conflicts:")
        ip_conflicts = {ip: devices for ip, devices in by_ip.items() if len(devices) > 1}
        for ip, device_list in list(ip_conflicts.items())[:10]:  # Show first 10
            print(f"  {ip}: {len(device_list)} devices")
            duplicate_groups.append(('ip', ip, device_list))
        if len(ip_conflicts) > 10:
            print(f"  ... and {len(ip_conflicts) - 10} more IP conflicts")

        print(f"\nMAC Address Conflicts:")
        mac_conflicts = {mac: devices for mac, devices in by_mac.items() if len(devices) > 1}
        for mac, device_list in list(mac_conflicts.items())[:5]:
            print(f"  {mac}: {len(device_list)} devices")
            duplicate_groups.append(('mac', mac, device_list))
        if len(mac_conflicts) > 5:
            print(f"  ... and {len(mac_conflicts) - 5} more MAC conflicts")

        print(f"\nSerial Number Conflicts:")
        serial_conflicts = {serial: devices for serial, devices in by_serial.items() if len(devices) > 1}
        for serial, device_list in list(serial_conflicts.items())[:5]:
            print(f"  {serial}: {len(device_list)} devices")
            duplicate_groups.append(('serial', serial, device_list))

        print(f"\nHostname Conflicts:")
        hostname_conflicts = {hostname: devices for hostname, devices in by_hostname.items() if len(devices) > 1}
        for hostname, device_list in list(hostname_conflicts.items())[:5]:
            print(f"  {hostname}: {len(device_list)} devices")
            duplicate_groups.append(('hostname', hostname, device_list))

        print(f"\nSystem Description Groups (potential device families):")
        large_sysdescr_groups = {sysdescr: devices for sysdescr, devices in by_sysdescr.items() if len(devices) > 5}
        for sysdescr, device_list in list(large_sysdescr_groups.items())[:10]:
            print(f"  {len(device_list)} devices: {sysdescr[:80]}...")

        return duplicate_groups

    def normalize_sysdescr(self, sysdescr):
        """Normalize system description for duplicate detection"""
        if not sysdescr:
            return ""

        # Remove version-specific information
        normalized = re.sub(r'Version\s+[\d\.]+', 'Version X.X', sysdescr, flags=re.IGNORECASE)
        normalized = re.sub(r'[\d\.]+\.\d+\.\d+', 'X.X.X', normalized)

        # Remove serial numbers and MAC addresses
        normalized = re.sub(r'\b[A-F0-9]{12}\b', 'MACADDR', normalized)
        normalized = re.sub(r'\b[A-Z0-9]{8,}\b', 'SERIALNUM', normalized)

        # Remove timestamps
        normalized = re.sub(r'\d{4}-\d{2}-\d{2}', 'DATE', normalized)
        normalized = re.sub(r'\d{2}:\d{2}:\d{2}', 'TIME', normalized)

        return normalized.strip()

    def analyze_network_density(self):
        """Analyze device density by network segment"""
        print(f"\nNETWORK DENSITY ANALYSIS:")
        print(f"=" * 40)

        subnet_counts = defaultdict(int)
        ip_ranges = defaultdict(list)

        for device_id, device in self.devices.items():
            ip = device.get('primary_ip', '')
            if ip:
                # Extract /24 subnet
                parts = ip.split('.')
                if len(parts) == 4:
                    subnet_24 = f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
                    subnet_counts[subnet_24] += 1
                    ip_ranges[subnet_24].append(ip)

        print(f"Device density by /24 subnet:")
        for subnet, count in sorted(subnet_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {subnet}: {count} devices")

            # Check for suspicious density
            if count > 200:
                print(f"    ⚠️  SUSPICIOUS: Very high density ({count} devices in /24)")

                # Sample some IPs to see the pattern
                sample_ips = sorted(set(ip_ranges[subnet]))[:10]
                print(f"    Sample IPs: {', '.join(sample_ips)}")

    def analyze_vendor_quality(self):
        """Analyze vendor and device type identification quality"""
        print(f"\nVENDOR/TYPE QUALITY ANALYSIS:")
        print(f"=" * 40)

        confidence_by_vendor = defaultdict(list)
        unknown_vendors = 0
        unknown_types = 0
        high_confidence_count = 0

        for device_id, device in self.devices.items():
            vendor = device.get('vendor', 'unknown').lower()
            device_type = device.get('device_type', 'unknown').lower()
            confidence = device.get('confidence_score', 0)

            self.vendor_stats[vendor] += 1
            self.device_type_stats[device_type] += 1
            confidence_by_vendor[vendor].append(confidence)
            self.confidence_stats.append(confidence)

            if vendor in ['unknown', '']:
                unknown_vendors += 1
            if device_type in ['unknown', '']:
                unknown_types += 1
            if confidence >= 80:
                high_confidence_count += 1

        total_devices = len(self.devices)
        avg_confidence = sum(self.confidence_stats) / len(self.confidence_stats) if self.confidence_stats else 0

        print(f"Overall Quality Metrics:")
        print(f"  Average confidence: {avg_confidence:.1f}%")
        print(
            f"  High confidence (≥80%): {high_confidence_count}/{total_devices} ({high_confidence_count / total_devices * 100:.1f}%)")
        print(f"  Unknown vendors: {unknown_vendors}/{total_devices} ({unknown_vendors / total_devices * 100:.1f}%)")
        print(f"  Unknown device types: {unknown_types}/{total_devices} ({unknown_types / total_devices * 100:.1f}%)")

        print(f"\nTop vendors by count:")
        for vendor, count in self.vendor_stats.most_common(10):
            avg_conf = sum(confidence_by_vendor[vendor]) / len(confidence_by_vendor[vendor])
            print(f"  {vendor}: {count} devices (avg confidence: {avg_conf:.1f}%)")

        print(f"\nDevice types by count:")
        for device_type, count in self.device_type_stats.most_common(10):
            print(f"  {device_type}: {count} devices")

    def identify_likely_duplicates(self, duplicate_groups):
        """Identify most likely actual duplicates"""
        print(f"\nLIKELY DUPLICATE ANALYSIS:")
        print(f"=" * 40)

        high_confidence_duplicates = []

        for conflict_type, identifier, device_list in duplicate_groups:
            if conflict_type in ['ip', 'serial', 'mac']:
                # These are very likely to be actual duplicates
                if len(device_list) > 1:
                    print(f"\nHIGH CONFIDENCE DUPLICATE ({conflict_type.upper()}: {identifier}):")
                    for device_id, device in device_list:
                        vendor = device.get('vendor', 'unknown')
                        device_type = device.get('device_type', 'unknown')
                        hostname = device.get('sys_name', 'unknown')
                        confidence = device.get('confidence_score', 0)

                        print(f"  {device_id}: {vendor} {device_type} '{hostname}' (conf: {confidence}%)")

                    high_confidence_duplicates.append((conflict_type, identifier, device_list))

        return high_confidence_duplicates

    def suggest_deduplication_strategy(self, duplicate_groups):
        """Suggest strategies for cleaning up duplicates"""
        print(f"\nDEDUPLICATION RECOMMENDATIONS:")
        print(f"=" * 50)

        total_duplicates = sum(len(group[2]) - 1 for group in duplicate_groups)

        print(f"Estimated duplicate devices: {total_duplicates}")
        print(f"Cleaned device count would be: {len(self.devices) - total_duplicates}")

        print(f"\nRecommended cleanup strategy:")
        print(f"1. Remove devices with identical IP addresses (keep highest confidence)")
        print(f"2. Remove devices with identical serial numbers")
        print(f"3. Remove devices with identical MAC addresses")
        print(f"4. Group devices with similar system descriptions")
        print(f"5. Review devices with very low confidence scores")

        # Find devices that should probably be removed
        devices_to_remove = set()
        devices_to_keep = set()

        for conflict_type, identifier, device_list in duplicate_groups:
            if conflict_type in ['ip', 'serial', 'mac'] and len(device_list) > 1:
                # Sort by confidence score, keep the highest
                sorted_devices = sorted(device_list,
                                        key=lambda x: x[1].get('confidence_score', 0),
                                        reverse=True)

                # Keep the first (highest confidence), mark others for removal
                devices_to_keep.add(sorted_devices[0][0])
                for device_id, device in sorted_devices[1:]:
                    devices_to_remove.add(device_id)

        print(f"\nAutomatic cleanup would:")
        print(f"  Remove: {len(devices_to_remove)} duplicate devices")
        print(f"  Keep: {len(self.devices) - len(devices_to_remove)} unique devices")

    def export_analysis_report(self, output_file="scan_analysis_report.txt"):
        """Export comprehensive analysis report"""
        with open(output_file, 'w') as f:
            f.write("NETWORK SCAN DUPLICATE ANALYSIS REPORT\n")
            f.write("=" * 50 + "\n")
            f.write(f"Analysis Date: {datetime.now()}\n")
            f.write(f"Total Devices: {len(self.devices):,}\n\n")

            # Summary statistics
            if self.confidence_stats:
                avg_conf = sum(self.confidence_stats) / len(self.confidence_stats)
                f.write(f"Average Confidence: {avg_conf:.1f}%\n")
                f.write(f"High Confidence Devices: {sum(1 for c in self.confidence_stats if c >= 80)}\n")

            # Top vendors
            f.write(f"\nTop Vendors:\n")
            for vendor, count in self.vendor_stats.most_common(10):
                f.write(f"  {vendor}: {count:,} devices\n")

            # Device types
            f.write(f"\nDevice Types:\n")
            for device_type, count in self.device_type_stats.most_common(10):
                f.write(f"  {device_type}: {count:,} devices\n")

        print(f"Analysis report exported to: {output_file}")

    def run_full_analysis(self, file_path):
        """Run complete analysis pipeline"""
        data = self.analyze_json_file(file_path)
        if not data:
            return

        duplicate_groups = self.detect_duplicates()
        self.analyze_network_density()
        self.analyze_vendor_quality()
        likely_duplicates = self.identify_likely_duplicates(duplicate_groups)
        self.suggest_deduplication_strategy(duplicate_groups)

        return {
            'total_devices': len(self.devices),
            'duplicate_groups': len(duplicate_groups),
            'likely_duplicates': len(likely_duplicates),
            'avg_confidence': sum(self.confidence_stats) / len(self.confidence_stats) if self.confidence_stats else 0
        }


def main():
    parser = argparse.ArgumentParser(description="Enhanced JSON discovery analysis")
    parser.add_argument("json_file", help="JSON discovery file to analyze")
    parser.add_argument("--export-report", action="store_true", help="Export analysis report")

    args = parser.parse_args()

    if not Path(args.json_file).exists():
        print(f"File not found: {args.json_file}")
        return

    analyzer = EnhancedJSONAnalyzer()
    results = analyzer.run_full_analysis(args.json_file)

    if args.export_report:
        analyzer.export_analysis_report()

    print(f"\n" + "=" * 50)
    print(f"ANALYSIS SUMMARY:")
    print(f"  Total devices: {results['total_devices']:,}")
    print(f"  Duplicate groups found: {results['duplicate_groups']}")
    print(f"  High-confidence duplicates: {results['likely_duplicates']}")
    print(f"  Average confidence: {results['avg_confidence']:.1f}%")


if __name__ == "__main__":
    main()