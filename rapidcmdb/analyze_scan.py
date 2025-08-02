#!/usr/bin/env python3
"""
Pure Schema-Based Scan Analyzer
Only reads vendor/device_type fields directly from the scan JSON schema
No pattern matching or hard-coded vendor detection
"""

import json
import argparse
import sys
import os
from collections import Counter
from typing import Dict


def analyze_scan_schema(file_path: str) -> Dict:
    """Analyze scan file using only the schema fields"""

    print(f"Reading scan file: {file_path}")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            scan_data = json.load(f)
    except Exception as e:
        print(f"Error reading file: {e}")
        return {}

    devices = scan_data.get('devices', {})
    total_devices = len(devices)

    print(f"Found {total_devices} devices in scan")

    if total_devices == 0:
        return {}

    # Counters for schema fields
    vendor_counts = Counter()
    device_type_counts = Counter()
    vendor_type_combinations = Counter()
    confidence_stats = []

    # Process each device using only schema fields
    device_details = []

    for device_id, device_info in devices.items():
        # Read directly from schema - no interpretation
        vendor = device_info.get('vendor', 'unknown').strip()
        device_type = device_info.get('device_type', 'unknown').strip()
        confidence = device_info.get('confidence_score', 0)
        primary_ip = device_info.get('primary_ip', '')
        sys_name = device_info.get('sys_name', '')
        sys_descr = device_info.get('sys_descr', '')

        # Handle empty/null values
        if not vendor or vendor.lower() in ['', 'none']:
            vendor = 'unknown'
        if not device_type or device_type.lower() in ['', 'none']:
            device_type = 'unknown'

        # Create combination exactly as detected by scanner
        if vendor == 'unknown' and device_type == 'unknown':
            combo = 'unknown'
        elif vendor == 'unknown':
            combo = f"unknown_{device_type}"
        elif device_type == 'unknown':
            combo = f"{vendor}_unknown"
        else:
            combo = f"{vendor}_{device_type}"

        # Update counters
        vendor_counts[vendor] += 1
        device_type_counts[device_type] += 1
        vendor_type_combinations[combo] += 1
        confidence_stats.append(confidence)

        # Store device details
        device_details.append({
            'device_id': device_id,
            'primary_ip': primary_ip,
            'sys_name': sys_name,
            'vendor': vendor,
            'device_type': device_type,
            'combo': combo,
            'confidence': confidence,
            'sys_descr': sys_descr[:100] + '...' if len(sys_descr) > 100 else sys_descr
        })

    # Calculate confidence statistics
    avg_confidence = sum(confidence_stats) / len(confidence_stats) if confidence_stats else 0
    high_confidence = len([c for c in confidence_stats if c >= 80])
    medium_confidence = len([c for c in confidence_stats if 50 <= c < 80])
    low_confidence = len([c for c in confidence_stats if c < 50])

    return {
        'total_devices': total_devices,
        'vendor_counts': vendor_counts,
        'device_type_counts': device_type_counts,
        'vendor_type_combinations': vendor_type_combinations,
        'device_details': device_details,
        'confidence_stats': {
            'average': avg_confidence,
            'high_confidence': high_confidence,
            'medium_confidence': medium_confidence,
            'low_confidence': low_confidence
        }
    }


def print_analysis_report(analysis: Dict):
    """Print analysis report"""

    if not analysis:
        print("No analysis data")
        return

    total = analysis['total_devices']

    print("\n" + "=" * 80)
    print("SCAN SCHEMA ANALYSIS REPORT")
    print("=" * 80)
    print(f"Total devices: {total}")

    # Confidence breakdown
    conf_stats = analysis['confidence_stats']
    print(f"\nCONFIDENCE BREAKDOWN:")
    print("-" * 30)
    print(f"Average confidence: {conf_stats['average']:.1f}%")
    print(f"High confidence (>=80%): {conf_stats['high_confidence']} devices")
    print(f"Medium confidence (50-79%): {conf_stats['medium_confidence']} devices")
    print(f"Low confidence (<50%): {conf_stats['low_confidence']} devices")

    # Vendor breakdown from schema
    print(f"\nVENDOR BREAKDOWN (from schema):")
    print("-" * 40)
    vendor_counts = analysis['vendor_counts']
    for vendor, count in vendor_counts.most_common():
        percentage = (count / total) * 100
        print(f"{vendor:<20}: {count:>4} devices ({percentage:>5.1f}%)")

    # Device type breakdown from schema
    print(f"\nDEVICE TYPE BREAKDOWN (from schema):")
    print("-" * 40)
    type_counts = analysis['device_type_counts']
    for device_type, count in type_counts.most_common():
        percentage = (count / total) * 100
        print(f"{device_type:<20}: {count:>4} devices ({percentage:>5.1f}%)")

    # Combined vendor_type as detected by scanner
    print(f"\nVENDOR_TYPE COMBINATIONS (from schema):")
    print("-" * 50)
    combo_counts = analysis['vendor_type_combinations']
    for combo, count in combo_counts.most_common():
        percentage = (count / total) * 100
        print(f"{combo:<30}: {count:>4} devices ({percentage:>5.1f}%)")


def print_device_details(analysis: Dict, limit: int = 20, filter_vendor: str = None, filter_type: str = None):
    """Print device details"""

    devices = analysis.get('device_details', [])

    # Apply filters
    if filter_vendor or filter_type:
        filtered = []
        for device in devices:
            vendor_match = not filter_vendor or filter_vendor.lower() in device['vendor'].lower()
            type_match = not filter_type or filter_type.lower() in device['device_type'].lower()
            if vendor_match and type_match:
                filtered.append(device)
        devices = filtered

        if filter_vendor:
            print(f"\nFiltered by vendor: {filter_vendor}")
        if filter_type:
            print(f"Filtered by device type: {filter_type}")

    if not devices:
        print("No devices match the filter criteria")
        return

    # Sort by vendor_type combo then by IP
    devices.sort(key=lambda x: (x['combo'], x['primary_ip']))

    print(f"\nDEVICE DETAILS (showing {min(limit, len(devices))} of {len(devices)}):")
    print("=" * 130)
    print(f"{'IP Address':<15} | {'Vendor_Type':<25} | {'Conf':<4} | {'Sys Name':<15} | {'System Description'}")
    print("-" * 130)

    for device in devices[:limit]:
        ip = device['primary_ip'][:14]
        combo = device['combo'][:24]
        conf = f"{device['confidence']}%"
        sys_name = device['sys_name'][:14] if device['sys_name'] else 'N/A'
        sys_descr = device['sys_descr'][:40]

        print(f"{ip:<15} | {combo:<25} | {conf:<4} | {sys_name:<15} | {sys_descr}")


def analyze_fingerprinting_effectiveness(analysis: Dict):
    """Analyze how well the fingerprinting worked"""

    devices = analysis.get('device_details', [])
    if not devices:
        return

    print(f"\nFINGERPRINTING EFFECTIVENESS:")
    print("-" * 40)

    # Count unknowns
    unknown_vendor = len([d for d in devices if d['vendor'] == 'unknown'])
    unknown_type = len([d for d in devices if d['device_type'] == 'unknown'])
    both_unknown = len([d for d in devices if d['vendor'] == 'unknown' and d['device_type'] == 'unknown'])

    total = len(devices)

    print(f"Unknown vendor: {unknown_vendor}/{total} ({(unknown_vendor / total) * 100:.1f}%)")
    print(f"Unknown device type: {unknown_type}/{total} ({(unknown_type / total) * 100:.1f}%)")
    print(f"Both unknown: {both_unknown}/{total} ({(both_unknown / total) * 100:.1f}%)")

    # Confidence analysis
    high_conf = len([d for d in devices if d['confidence'] >= 80])
    print(f"High confidence (>=80%): {high_conf}/{total} ({(high_conf / total) * 100:.1f}%)")


def print_unknown_devices(analysis: Dict):
    """Print details of unknown devices to help improve fingerprinting"""

    devices = analysis.get('device_details', [])
    if not devices:
        return

    # Find unknown devices
    unknown_devices = [d for d in devices if d['vendor'] == 'unknown' or d['device_type'] == 'unknown']

    if not unknown_devices:
        print("\nNo unknown devices found!")
        return

    print(f"\nUNKNOWN DEVICES ANALYSIS:")
    print("=" * 100)
    print(f"Found {len(unknown_devices)} devices that need better fingerprinting")
    print("=" * 100)

    # Group by sys_descr to identify patterns
    from collections import defaultdict
    descr_groups = defaultdict(list)

    for device in unknown_devices:
        # Get first 80 chars of sys_descr for grouping
        descr_key = device['sys_descr'][:80] if device['sys_descr'] else 'No sys_descr'
        descr_groups[descr_key].append(device)

    # Print grouped results
    for i, (descr, device_list) in enumerate(descr_groups.items(), 1):
        print(f"\n[{i}] UNKNOWN DEVICE GROUP ({len(device_list)} devices)")
        print("-" * 80)

        # Show the system description
        if device_list[0]['sys_descr']:
            print(f"System Description: {device_list[0]['sys_descr']}")
        else:
            print("System Description: [EMPTY]")

        # Show vendor/type status
        sample = device_list[0]
        vendor_status = "UNKNOWN" if sample['vendor'] == 'unknown' else f"KNOWN: {sample['vendor']}"
        type_status = "UNKNOWN" if sample['device_type'] == 'unknown' else f"KNOWN: {sample['device_type']}"

        print(f"Vendor: {vendor_status}")
        print(f"Device Type: {type_status}")
        print(f"Confidence: {sample['confidence']}%")

        # Show sample IPs (up to 5)
        sample_ips = [d['primary_ip'] for d in device_list[:5]]
        if len(device_list) > 5:
            ip_display = f"{', '.join(sample_ips)} (and {len(device_list) - 5} more)"
        else:
            ip_display = ', '.join(sample_ips)
        print(f"Sample IPs: {ip_display}")

        # Show system names if available
        sys_names = [d['sys_name'] for d in device_list[:3] if d['sys_name']]
        if sys_names:
            print(f"Sample Names: {', '.join(sys_names)}")

        print()  # Blank line between groups


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Analyze scan JSON using only schema fields")
    parser.add_argument("scan_file", help="Path to scan JSON file")
    parser.add_argument("--details", "-d", action="store_true", help="Show device details")
    parser.add_argument("--limit", "-l", type=int, default=20, help="Limit device details shown")
    parser.add_argument("--vendor", "-v", help="Filter by vendor")
    parser.add_argument("--type", "-t", help="Filter by device type")
    parser.add_argument("--effectiveness", "-e", action="store_true", help="Show fingerprinting effectiveness")
    parser.add_argument("--unknowns", "-u", action="store_true", help="Show detailed analysis of unknown devices")

    args = parser.parse_args()

    # Check file exists
    if not os.path.exists(args.scan_file):
        print(f"Error: File not found: {args.scan_file}")
        sys.exit(1)

    # Analyze using only schema fields
    analysis = analyze_scan_schema(args.scan_file)

    if not analysis:
        print("Failed to analyze scan file")
        sys.exit(1)

    # Print main report
    print_analysis_report(analysis)

    # Show fingerprinting effectiveness if requested
    if args.effectiveness:
        analyze_fingerprinting_effectiveness(analysis)

    # Show unknown devices analysis if requested
    if args.unknowns:
        print_unknown_devices(analysis)

    # Show device details if requested
    if args.details:
        print_device_details(analysis, args.limit, args.vendor, args.type)


if __name__ == "__main__":
    main()