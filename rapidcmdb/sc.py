import argparse
import yaml
import os
from pathlib import Path
from typing import Dict, Optional
from rapidcmdb.network_discovery import NetworkDiscovery, DiscoveryConfig


def load_yaml_config(config_path: Optional[Path]) -> Dict:
    """Load configuration from YAML file."""
    if not config_path:
        return {}

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
        return config or {}
    except Exception as e:
        print(f"Error reading config file: {str(e)}")
        return {}


def process_config(args) -> dict:
    """Process configuration from all sources and return final config."""
    # 1. Start with defaults
    final_config = {
        'seed_ip': '',
        'username': '',
        'password': '',
        'alternate_username': '',
        'alternate_password': '',
        'domain_name': '',
        'exclude_string': '',
        'output_dir': './output',
        'timeout': 30,
        'max_devices': 100,
        'save_debug_info': False,
        'map_name': 'network_map',
        'layout_algo': 'kk'
    }

    # 2. Load and apply YAML config if provided
    if args.config:
        yaml_config = load_yaml_config(Path(args.config))
        print(f"Debug - YAML config loaded: {yaml_config}")
        final_config.update(yaml_config)

    # 3. Apply CLI arguments (non-None values only)
    cli_config = {k: v for k, v in vars(args).items()
                  if v is not None and k != 'config'}
    # print(f"Debug - CLI options: {cli_config}")
    final_config.update(cli_config)

    # 4. Apply environment variables (highest precedence)
    if os.getenv('SC_USERNAME'):
        final_config['username'] = os.getenv('SC_USERNAME')
        # print(" - Using SC_USERNAME from environment")
    if os.getenv('SC_PASSWORD'):
        final_config['password'] = os.getenv('SC_PASSWORD')
        # print(" - Using SC_PASSWORD from environment")
    if os.getenv('SC_ALT_USERNAME'):
        final_config['alternate_username'] = os.getenv('SC_ALT_USERNAME')
        print(" - Using SC_ALT_USERNAME from environment")
    if os.getenv('SC_ALT_PASSWORD'):
        final_config['alternate_password'] = os.getenv('SC_ALT_PASSWORD')
        # print(" - Using SC_ALT_PASSWORD from environment")

    # 5. Handle output directory path
    output_dir = final_config.get('output_dir', './output')
    print(f"Debug - Initial output_dir: {output_dir}")
    if isinstance(output_dir, str):
        output_dir = output_dir.strip('"').strip("'")
        final_config['output_dir'] = Path(output_dir).resolve()
        print(f"Debug - Resolved output_dir: {final_config['output_dir']}")

    return final_config


def main():
    parser = argparse.ArgumentParser(description='Network Discovery Tool')
    parser.add_argument('--config', help='YAML configuration file path')
    parser.add_argument('--seed-ip', help='Seed IP address to start discovery')
    parser.add_argument('--username', help='Primary username for device authentication')
    parser.add_argument('--password', help='Primary password for device authentication')
    parser.add_argument('--alternate-username', help='Alternate username for fallback authentication')
    parser.add_argument('--alternate-password', help='Alternate password for fallback authentication')
    parser.add_argument('--domain-name', help='Domain name for device resolution')
    parser.add_argument('--exclude-string', help='Comma-separated list of strings to exclude from discovery')
    parser.add_argument('--output-dir', help='Output directory for discovery results')
    parser.add_argument('--timeout', type=int, help='Timeout in seconds for device connections')
    parser.add_argument('--max-devices', type=int, help='Maximum number of devices to discover')
    parser.add_argument('--save-debug-info', action='store_true', help='Save debug information during discovery')
    parser.add_argument('--map-name', help='Name for the generated network map files')
    parser.add_argument('--layout-algo', choices=['kk', 'spring', 'circular', 'random'],
                        help='Layout algorithm for network visualization')

    args = parser.parse_args()

    try:
        # Process configuration from all sources
        final_config = process_config(args)

        # Filter for valid DiscoveryConfig parameters
        valid_params = set(DiscoveryConfig.__dataclass_fields__.keys())
        filtered_config = {k: v for k, v in final_config.items() if k in valid_params}
        print(f"Debug - Final filtered config: {filtered_config}")

        # Validate required fields
        missing = []
        if not filtered_config.get('seed_ip'): missing.append('seed_ip')
        if not filtered_config.get('username'): missing.append('username')
        if not filtered_config.get('password'): missing.append('password')

        if missing:
            print("\nError: Missing required configuration:", ', '.join(missing))
            print("These must be provided via environment variables (SC_USERNAME/SC_PASSWORD),")
            print("YAML config file, or command line arguments.")
            return 1

        # Create config object and discovery instance
        config = DiscoveryConfig(**filtered_config)
        discovery = NetworkDiscovery(config)

        # Run discovery
        print(f"\nStarting network discovery from {config.seed_ip}")
        print(f"Output will be saved to {config.output_dir}")

        def update_progress(stats):
            if stats.get('status') == 'success':
                print(f"Discovered device: {stats.get('ip', 'unknown')}")

        discovery.set_progress_callback(update_progress)
        network_map = discovery.crawl()

        # Show results
        stats = discovery.get_discovery_stats()
        print("\nDiscovery complete!")
        print(f"Devices discovered: {stats['devices_discovered']}")
        print(f"Devices failed: {stats['devices_failed']}")
        print(f"Unreachable hosts: {stats['unreachable_hosts']}")

        # Show output files
        print(f"\nOutput files created in {config.output_dir}:")
        print(f" - {config.map_name}.json")
        print(f" - {config.map_name}.graphml")
        print(f" - {config.map_name}.drawio")
        print(f" - {config.map_name}.svg")

        return 0

    except Exception as e:
        print(f"\nError during discovery: {str(e)}")
        return 1


if __name__ == '__main__':
    exit(main())