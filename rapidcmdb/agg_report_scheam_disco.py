#!/usr/bin/env python3
"""
JSON Schema Discovery Tool
Analyzes JSON structure to understand data format and schema
"""

import json
import sys
from pathlib import Path
from collections import defaultdict, Counter
import argparse


def analyze_value_type(value):
    """Analyze the type and characteristics of a value"""
    if value is None:
        return "null"
    elif isinstance(value, bool):
        return "boolean"
    elif isinstance(value, int):
        return "integer"
    elif isinstance(value, float):
        return "float"
    elif isinstance(value, str):
        if len(value) == 0:
            return "empty_string"
        elif len(value) > 100:
            return "long_string"
        else:
            return "string"
    elif isinstance(value, list):
        return f"array[{len(value)}]"
    elif isinstance(value, dict):
        return f"object[{len(value)}]"
    else:
        return str(type(value).__name__)


def discover_object_schema(obj, path="root", max_depth=5, current_depth=0):
    """Recursively discover schema of an object"""
    schema = {
        "path": path,
        "type": analyze_value_type(obj),
        "sample_value": None,
        "children": {}
    }

    if current_depth >= max_depth:
        schema["truncated"] = True
        return schema

    if isinstance(obj, dict):
        schema["keys"] = list(obj.keys())
        schema["key_count"] = len(obj.keys())

        # Sample a few keys for detailed analysis
        sample_keys = list(obj.keys())[:10]  # First 10 keys

        for key in sample_keys:
            child_path = f"{path}.{key}"
            schema["children"][key] = discover_object_schema(
                obj[key], child_path, max_depth, current_depth + 1
            )

    elif isinstance(obj, list):
        schema["length"] = len(obj)
        if obj:
            # Analyze first few items
            sample_items = obj[:5]
            schema["item_types"] = [analyze_value_type(item) for item in sample_items]

            # If items are objects, analyze their structure
            if isinstance(obj[0], dict):
                schema["children"]["[items]"] = discover_object_schema(
                    obj[0], f"{path}[0]", max_depth, current_depth + 1
                )

    else:
        # For primitive types, store sample value
        if isinstance(obj, str) and len(obj) > 200:
            schema["sample_value"] = obj[:200] + "..."
        else:
            schema["sample_value"] = obj

    return schema


def analyze_array_patterns(arr):
    """Analyze patterns in array data"""
    if not arr:
        return {"empty": True}

    patterns = {
        "length": len(arr),
        "item_types": Counter(),
        "common_keys": Counter(),
        "sample_items": []
    }

    # Analyze up to 100 items for performance
    sample_size = min(len(arr), 100)
    sample_items = arr[:sample_size]

    for item in sample_items:
        item_type = analyze_value_type(item)
        patterns["item_types"][item_type] += 1

        if isinstance(item, dict):
            for key in item.keys():
                patterns["common_keys"][key] += 1

    # Store a few sample items
    patterns["sample_items"] = sample_items[:3]

    return patterns


def analyze_json_structure(data):
    """Main analysis function"""
    analysis = {
        "root_type": analyze_value_type(data),
        "schema": discover_object_schema(data),
        "summary": {}
    }

    # Root level analysis
    if isinstance(data, dict):
        analysis["summary"] = {
            "type": "object",
            "keys": list(data.keys()),
            "key_count": len(data.keys()),
            "sample_keys": list(data.keys())[:10]
        }

        # Look for common patterns
        key_patterns = []
        for key, value in list(data.items())[:10]:
            key_patterns.append({
                "key": key,
                "type": analyze_value_type(value),
                "sample": str(value)[:100] if not isinstance(value, (dict, list)) else f"{type(value).__name__}(...)"
            })
        analysis["summary"]["key_patterns"] = key_patterns

    elif isinstance(data, list):
        analysis["summary"] = {
            "type": "array",
            "length": len(data),
            "array_patterns": analyze_array_patterns(data)
        }

    return analysis


def print_schema_tree(schema, indent=0):
    """Print schema in a tree format"""
    prefix = "  " * indent
    type_info = schema["type"]

    if "sample_value" in schema and schema["sample_value"] is not None:
        sample = str(schema["sample_value"])
        if len(sample) > 50:
            sample = sample[:50] + "..."
        print(f"{prefix}{schema['path']}: {type_info} = {sample}")
    else:
        print(f"{prefix}{schema['path']}: {type_info}")

    if "keys" in schema:
        print(f"{prefix}  └─ Keys: {schema['key_count']} total")
        if schema['key_count'] <= 20:
            print(f"{prefix}     {', '.join(schema['keys'])}")
        else:
            print(f"{prefix}     {', '.join(schema['keys'][:10])}... (+{schema['key_count'] - 10} more)")

    if "length" in schema:
        print(f"{prefix}  └─ Array length: {schema['length']}")
        if "item_types" in schema:
            print(f"{prefix}     Item types: {', '.join(schema['item_types'])}")

    # Print children
    for child_name, child_schema in schema.get("children", {}).items():
        print_schema_tree(child_schema, indent + 1)


def print_summary_report(analysis):
    """Print a summary report"""
    print("=" * 60)
    print("JSON STRUCTURE ANALYSIS REPORT")
    print("=" * 60)

    print(f"\nRoot Type: {analysis['root_type']}")

    summary = analysis["summary"]

    if summary.get("type") == "object":
        print(f"Root Object Keys: {summary['key_count']}")
        print("\nKey Patterns (first 10):")
        for pattern in summary.get("key_patterns", []):
            print(f"  '{pattern['key']}': {pattern['type']} - {pattern['sample']}")

    elif summary.get("type") == "array":
        patterns = summary["array_patterns"]
        print(f"Array Length: {patterns['length']}")
        print(f"Item Types: {dict(patterns['item_types'])}")

        if patterns["common_keys"]:
            print(f"\nMost Common Keys in Objects:")
            for key, count in patterns["common_keys"].most_common(10):
                print(f"  '{key}': appears in {count}/{patterns['length']} items")

    print("\n" + "=" * 60)
    print("DETAILED SCHEMA TREE")
    print("=" * 60)
    print_schema_tree(analysis["schema"])


def suggest_data_format(analysis):
    """Suggest what type of data format this might be"""
    print("\n" + "=" * 60)
    print("DATA FORMAT SUGGESTIONS")
    print("=" * 60)

    summary = analysis["summary"]

    if summary.get("type") == "array":
        patterns = summary["array_patterns"]
        item_types = patterns["item_types"]

        if "object[" in str(item_types):
            print("✓ This appears to be an ARRAY OF OBJECTS")
            print("  - Suitable for CSV conversion with one row per array item")

            if patterns["common_keys"]:
                common_keys = list(patterns["common_keys"].keys())[:10]
                print(f"  - Common fields: {', '.join(common_keys)}")

    elif summary.get("type") == "object":
        keys = summary.get("keys", [])

        # Check for scan result patterns
        scan_indicators = ["results", "timestamp", "scan_", "target_ip", "devices_found"]
        device_indicators = ["primary_ip", "vendor", "device_type", "sys_descr", "interfaces"]

        scan_score = sum(1 for indicator in scan_indicators if any(indicator in key for key in keys))
        device_score = sum(1 for indicator in device_indicators if any(indicator in key for key in keys))

        if scan_score > 0:
            print("✓ This might be SCAN RESULTS format")
        elif device_score > 0:
            print("✓ This might be DEVICE INVENTORY format")
        else:
            # Check if values are objects (device dictionary format)
            sample_values = []
            for pattern in summary.get("key_patterns", [])[:5]:
                if "object[" in pattern["type"]:
                    sample_values.append(pattern["key"])

            if sample_values:
                print("✓ This appears to be a DICTIONARY OF OBJECTS")
                print(f"  - Keys like '{sample_values[0]}' contain object data")
                print("  - Each key-value pair could be converted to a CSV row")


def main():
    parser = argparse.ArgumentParser(
        description='Discover and analyze JSON file structure',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python discover_schema.py data.json
  python discover_schema.py large_file.json --max-depth 3
  python discover_schema.py complex.json --output schema_report.txt
        """
    )

    parser.add_argument('input_file', help='Input JSON file path')
    parser.add_argument('--max-depth', type=int, default=3, help='Maximum depth for schema analysis')
    parser.add_argument('-o', '--output', help='Output file for the report (optional)')

    args = parser.parse_args()

    print(f"Starting analysis of: {args.input_file}")

    # Validate input file
    if not Path(args.input_file).exists():
        print(f"Error: File '{args.input_file}' not found.")
        sys.exit(1)

    file_size = Path(args.input_file).stat().st_size
    print(f"File size: {file_size:,} bytes ({file_size / 1024 / 1024:.1f} MB)")

    # Read and analyze JSON
    try:
        print("Reading JSON file...")
        with open(args.input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        print(f"✓ JSON loaded successfully")
        print(f"Root data type: {type(data).__name__}")

        if isinstance(data, dict):
            print(f"Root object has {len(data)} keys")
        elif isinstance(data, list):
            print(f"Root array has {len(data)} items")

        print("Analyzing structure...")
        analysis = analyze_json_structure(data)
        print("✓ Analysis complete")

        # Generate report
        if args.output:
            print(f"Writing report to: {args.output}")
            with open(args.output, 'w', encoding='utf-8') as f:
                # Redirect stdout to file
                original_stdout = sys.stdout
                sys.stdout = f

                print_summary_report(analysis)
                suggest_data_format(analysis)

                sys.stdout = original_stdout

            print(f"✓ Report saved to: {args.output}")
        else:
            print_summary_report(analysis)
            suggest_data_format(analysis)

        print("Analysis completed successfully!")

    except FileNotFoundError:
        print(f"Error: File '{args.input_file}' not found.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in '{args.input_file}'")
        print(f"JSON Error: {e}")
        sys.exit(1)
    except MemoryError:
        print(f"Error: File too large to process in memory")
        print(f"Try processing a smaller sample of the data")
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error analyzing file: {e}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()