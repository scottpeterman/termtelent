"""
Updated Platform Config Manager to use package resources
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

# Import the resource manager
from termtel.helpers.resource_manager import resource_manager


@dataclass
class NetmikoConfig:
    device_type: str
    fast_cli: bool = False
    timeout: int = 30
    auth_timeout: int = 10


@dataclass
class CommandDefinition:
    command: str
    template: str
    timeout: int = 30
    description: str = ""
    parameters: List[str] = None
    fallback_commands: List[str] = None


@dataclass
class PlatformCapabilities:
    supports_vrf: bool = False
    supports_cdp: bool = False
    supports_lldp: bool = False
    supports_temperature: bool = False
    neighbor_protocol: str = "cdp"


@dataclass
class TemplateConfig:
    platform: str
    base_path: str


@dataclass
class PlatformDefinition:
    name: str
    display_name: str
    description: str
    netmiko: NetmikoConfig
    templates: TemplateConfig
    commands: Dict[str, CommandDefinition]
    field_mappings: Dict[str, Dict[str, str]]
    capabilities: PlatformCapabilities


class PlatformConfigManager:
    """
    UPDATED: Platform configuration manager that uses package resources
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize platform config manager

        Args:
            config_path: Optional path to config directory (for backwards compatibility)
        """
        self.platforms: Dict[str, PlatformDefinition] = {}
        self.config_path = config_path
        self._load_platforms_config()

    def _load_platforms_config(self):
        """Load platform configurations from package resources or file system"""
        config_content = None
        config_source = "unknown"

        try:
            # Method 1: Try package resources first (for installed packages)
            config_content = resource_manager.get_platforms_config()
            if config_content:
                config_source = "package_resources"
                print(f" Loaded platforms config from package resources")

        except Exception as e:
            print(f" Could not load from package resources: {e}")

        # Method 2: Fallback to file system (for development)
        if not config_content:
            config_file_paths = []

            # Try the provided config path
            if self.config_path:
                config_file_paths.append(os.path.join(self.config_path, 'platforms.json'))

            # Try common development paths
            config_file_paths.extend([
                'config/platforms/platforms.json',
                'config/platforms.json',
                'platforms.json',
                os.path.join(os.path.dirname(__file__), '..', 'config', 'platforms', 'platforms.json'),
                os.path.join(os.path.dirname(__file__), '..', 'config', 'platforms.json'),
            ])

            for config_file in config_file_paths:
                try:
                    if os.path.exists(config_file):
                        with open(config_file, 'r', encoding='utf-8') as f:
                            config_content = f.read()
                        config_source = f"file_system: {config_file}"
                        print(f" Loaded platforms config from {config_file}")
                        break
                except Exception as e:
                    print(f" Could not load from {config_file}: {e}")
                    continue

        # Parse the configuration
        if config_content:
            try:
                config_data = json.loads(config_content)
                self._parse_config(config_data)
                print(f" Successfully parsed {len(self.platforms)} platform configurations")
                print(f" Config source: {config_source}")
            except json.JSONDecodeError as e:
                print(f" Error parsing platforms config JSON: {e}")
                self._load_fallback_config()
        else:
            print(f" Could not find platforms.json config file")
            self._load_fallback_config()

    def _parse_config(self, config_data: Dict[str, Any]):
        """Parse the JSON configuration data"""
        platforms_data = config_data.get('platforms', {})

        for platform_name, platform_data in platforms_data.items():
            try:
                # Parse netmiko config
                netmiko_data = platform_data.get('netmiko', {})
                netmiko_config = NetmikoConfig(
                    device_type=netmiko_data.get('device_type', 'cisco_ios'),
                    fast_cli=netmiko_data.get('fast_cli', False),
                    timeout=netmiko_data.get('timeout', 30),
                    auth_timeout=netmiko_data.get('auth_timeout', 10)
                )

                # Parse template config
                template_data = platform_data.get('templates', {})
                template_config = TemplateConfig(
                    platform=template_data.get('platform', platform_name),
                    base_path=template_data.get('base_path', 'templates/textfsm')
                )

                # Parse commands
                commands = {}
                commands_data = platform_data.get('commands', {})
                for cmd_name, cmd_data in commands_data.items():
                    commands[cmd_name] = CommandDefinition(
                        command=cmd_data.get('command', ''),
                        template=cmd_data.get('template', ''),
                        timeout=cmd_data.get('timeout', 30),
                        description=cmd_data.get('description', ''),
                        parameters=cmd_data.get('parameters', []),
                        fallback_commands=cmd_data.get('fallback_commands', [])
                    )

                # Parse capabilities
                capabilities_data = platform_data.get('capabilities', {})
                capabilities = PlatformCapabilities(
                    supports_vrf=capabilities_data.get('supports_vrf', False),
                    supports_cdp=capabilities_data.get('supports_cdp', False),
                    supports_lldp=capabilities_data.get('supports_lldp', False),
                    supports_temperature=capabilities_data.get('supports_temperature', False),
                    neighbor_protocol=capabilities_data.get('neighbor_protocol', 'cdp')
                )

                # Create platform definition
                platform_def = PlatformDefinition(
                    name=platform_name,
                    display_name=platform_data.get('display_name', platform_name),
                    description=platform_data.get('description', ''),
                    netmiko=netmiko_config,
                    templates=template_config,
                    commands=commands,
                    field_mappings=platform_data.get('field_mappings', {}),
                    capabilities=capabilities
                )

                self.platforms[platform_name] = platform_def

            except Exception as e:
                print(f" Error parsing platform {platform_name}: {e}")
                continue

    def _load_fallback_config(self):
        """Load minimal fallback configuration if main config fails"""
        print(" Loading fallback platform configuration...")

        # Minimal Cisco IOS config
        cisco_ios_commands = {
            'system_info': CommandDefinition(
                command='show version',
                template='cisco_ios_show_version.textfsm',
                timeout=15
            ),
            'cdp_neighbors': CommandDefinition(
                command='show cdp neighbors detail',
                template='cisco_ios_show_cdp_neighbors_detail.textfsm',
                timeout=30
            ),
            'arp_table': CommandDefinition(
                command='show ip arp',
                template='cisco_ios_show_ip_arp.textfsm',
                timeout=20
            ),
            'route_table': CommandDefinition(
                command='show ip route',
                template='cisco_ios_show_ip_route.textfsm',
                timeout=30
            ),
            'cpu_utilization': CommandDefinition(
                command='show processes cpu',
                template='cisco_ios_show_processes_cpu.textfsm',
                timeout=15
            ),
            'memory_utilization': CommandDefinition(
                command='show memory statistics',
                template='cisco_ios_show_memory_statistics.textfsm',
                timeout=15
            ),
            'logs': CommandDefinition(
                command='show logging',
                template='cisco_ios_show_logging.textfsm',
                timeout=20
            )
        }

        cisco_ios_platform = PlatformDefinition(
            name='cisco_ios',
            display_name='Cisco IOS',
            description='Fallback Cisco IOS configuration',
            netmiko=NetmikoConfig(device_type='cisco_ios'),
            templates=TemplateConfig(platform='cisco_ios', base_path='templates/textfsm'),
            commands=cisco_ios_commands,
            field_mappings={
                'protocols': {
                    'S': 'Static', 'C': 'Connected', 'L': 'Local',
                    'O': 'OSPF', 'B': 'BGP', 'D': 'EIGRP', 'R': 'RIP'
                }
            },
            capabilities=PlatformCapabilities(
                supports_cdp=True,
                neighbor_protocol='cdp'
            )
        )

        self.platforms['cisco_ios'] = cisco_ios_platform
        print(" Fallback configuration loaded")

    def get_available_platforms(self) -> List[str]:
        """Get list of available platform names"""
        return list(self.platforms.keys())

    def get_platform(self, platform_name: str) -> Optional[PlatformDefinition]:
        """Get platform definition by name"""
        return self.platforms.get(platform_name)

    def format_command(self, platform: str, command_type: str, **kwargs) -> str:
        """Format a command with parameters using package-aware templates"""
        platform_def = self.get_platform(platform)
        if not platform_def:
            return f"# Platform '{platform}' not found"

        if command_type not in platform_def.commands:
            return f"# Command '{command_type}' not supported on {platform}"

        command_def = platform_def.commands[command_type]

        try:
            # Format command with parameters
            formatted_command = command_def.command.format(**kwargs)
            return formatted_command
        except KeyError as e:
            return f"# Missing parameter for command: {e}"
        except Exception as e:
            return f"# Error formatting command: {e}"

    def get_template_info(self, platform: str, command_type: str) -> Optional[tuple[str, str]]:
        """
        Get template information using package resources

        Returns:
            Tuple of (template_platform, template_filename) or None
        """
        platform_def = self.get_platform(platform)
        if not platform_def or command_type not in platform_def.commands:
            return None

        command_def = platform_def.commands[command_type]
        template_platform = platform_def.templates.platform
        template_file = command_def.template

        # Verify template exists using resource manager
        if resource_manager.get_template_path(template_file):
            return (template_platform, template_file)
        else:
            print(f" Template not found: {template_file}")
            return None

    def get_netmiko_config(self, platform: str) -> Optional[NetmikoConfig]:
        """Get netmiko configuration for platform"""
        platform_def = self.get_platform(platform)
        return platform_def.netmiko if platform_def else None

    def get_field_mapping(self, platform: str, mapping_type: str) -> Dict[str, str]:
        """Get field mappings for platform"""
        platform_def = self.get_platform(platform)
        if not platform_def:
            return {}

        return platform_def.field_mappings.get(mapping_type, {})

    def validate_platform_config(self, platform: str) -> Dict[str, Any]:
        """
        Validate platform configuration and template availability

        Returns:
            Dictionary with validation results
        """
        platform_def = self.get_platform(platform)
        if not platform_def:
            return {
                'valid': False,
                'errors': [f"Platform '{platform}' not found"],
                'missing_templates': [],
                'available_commands': []
            }

        errors = []
        missing_templates = []
        available_commands = []

        # Check each command's template
        for cmd_name, cmd_def in platform_def.commands.items():
            available_commands.append(cmd_name)

            # Check if template exists
            if not resource_manager.get_template_path(cmd_def.template):
                missing_templates.append(cmd_def.template)
                errors.append(f"Template not found for {cmd_name}: {cmd_def.template}")

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'missing_templates': missing_templates,
            'available_commands': available_commands,
            'platform_name': platform_def.display_name,
            'netmiko_device_type': platform_def.netmiko.device_type
        }