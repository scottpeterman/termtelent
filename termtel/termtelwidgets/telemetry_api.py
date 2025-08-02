"""
Telemetry Widget API - Programmatic Connection Interface
Provides clean API for external applications to control telemetry connections
"""

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List
from PyQt6.QtCore import QObject, pyqtSignal
import json
import time


@dataclass
class DeviceConfig:
    """Device configuration for telemetry connections"""
    hostname: str
    ip_address: str
    platform: str
    username: str
    password: str
    secret: str = ""
    port: int = 22
    timeout: int = 30
    auth_timeout: int = 10
    fast_cli: bool = False
    verbose: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DeviceConfig':
        """Create from dictionary"""
        return cls(**data)

    def validate(self) -> tuple[bool, str]:
        """Validate device configuration"""
        if not self.hostname.strip():
            return False, "Hostname is required"

        if not self.ip_address.strip():
            return False, "IP address is required"

        # Basic IP validation
        try:
            parts = self.ip_address.strip().split('.')
            if len(parts) != 4:
                return False, "Invalid IP address format"

            for part in parts:
                num = int(part)
                if not 0 <= num <= 255:
                    return False, f"Invalid IP address part: {part}"
        except ValueError:
            return False, "Invalid IP address format"

        if not self.username.strip():
            return False, "Username is required"

        if not self.password:
            return False, "Password is required"

        if not 1 <= self.port <= 65535:
            return False, f"Invalid port: {self.port}"

        if not 5 <= self.timeout <= 300:
            return False, f"Invalid timeout: {self.timeout} (must be 5-300 seconds)"

        if not 5 <= self.auth_timeout <= 60:
            return False, f"Invalid auth timeout: {self.auth_timeout} (must be 5-60 seconds)"

        return True, "Valid"


@dataclass
class ConnectionStatus:
    """Connection status information"""
    device_id: str
    hostname: str
    ip_address: str
    status: str  # 'disconnected', 'connecting', 'connected', 'failed', 'error'
    last_update: float
    error_message: str = ""
    device_info: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class TelemetrySnapshot:
    """Current telemetry data snapshot"""
    device_id: str
    timestamp: float
    connection_status: str
    device_info: Optional[Dict[str, Any]] = None
    neighbors: Optional[List[Dict[str, Any]]] = None
    arp_table: Optional[List[Dict[str, Any]]] = None
    route_table: Optional[List[Dict[str, Any]]] = None
    cpu_metrics: Optional[Dict[str, Any]] = None
    memory_metrics: Optional[Dict[str, Any]] = None
    system_logs: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


class TelemetryWidgetAPI(QObject):
    """
    High-level API for controlling TelemetryWidget programmatically
    Designed for external application integration
    """

    # API-level signals for external applications
    connection_status_changed = pyqtSignal(str, str, str)  # device_id, status, message
    telemetry_data_available = pyqtSignal(str, dict)       # device_id, snapshot_dict
    device_discovered = pyqtSignal(str, dict)              # device_id, device_info_dict
    api_error = pyqtSignal(str, str, str)                  # device_id, error_type, message

    def __init__(self, telemetry_widget):
        """
        Initialize API wrapper around TelemetryWidget

        Args:
            telemetry_widget: TelemetryWidget instance to control
        """
        super().__init__()
        self.widget = telemetry_widget
        self.device_configs = {}  # device_id -> DeviceConfig
        self.connection_statuses = {}  # device_id -> ConnectionStatus
        self.telemetry_snapshots = {}  # device_id -> TelemetrySnapshot

        # Connect to widget signals
        self._connect_widget_signals()

    def _connect_widget_signals(self):
        """Connect to underlying widget signals"""
        self.widget.device_connected.connect(self._on_widget_device_connected)
        self.widget.device_disconnected.connect(self._on_widget_device_disconnected)
        self.widget.device_error.connect(self._on_widget_device_error)
        self.widget.telemetry_data_updated.connect(self._on_widget_telemetry_updated)
        self.widget.widget_status_changed.connect(self._on_widget_status_changed)

    # ===== PUBLIC API METHODS =====

    def connect_device(self, device_config: DeviceConfig, device_id: Optional[str] = None) -> tuple[bool, str]:
        """
        Connect to a device programmatically

        Args:
            device_config: Device configuration
            device_id: Optional custom device ID (defaults to hostname)

        Returns:
            tuple: (success, message)
        """
        # Validate configuration
        valid, message = device_config.validate()
        if not valid:
            return False, f"Invalid device configuration: {message}"

        # Generate device ID if not provided
        if device_id is None:
            device_id = f"{device_config.hostname}_{device_config.ip_address}"

        # Store configuration
        self.device_configs[device_id] = device_config

        # Create initial status
        self.connection_statuses[device_id] = ConnectionStatus(
            device_id=device_id,
            hostname=device_config.hostname,
            ip_address=device_config.ip_address,
            status="connecting",
            last_update=time.time()
        )

        try:
            # Convert to credentials format expected by widget
            credentials = self._config_to_credentials(device_config)

            # Initiate connection via widget
            success = self.widget.connect_to_device_programmatic(
                device_config.hostname,
                device_config.ip_address,
                device_config.platform,
                credentials
            )

            if success:
                # Emit API-level signal
                self.connection_status_changed.emit(device_id, "connecting", "Connection initiated")
                return True, "Connection initiated successfully"
            else:
                # Update status
                self.connection_statuses[device_id].status = "failed"
                self.connection_statuses[device_id].error_message = "Failed to initiate connection"
                self.connection_statuses[device_id].last_update = time.time()

                # Emit API-level signal
                self.connection_status_changed.emit(device_id, "failed", "Failed to initiate connection")
                return False, "Failed to initiate connection"

        except Exception as e:
            error_msg = f"Connection error: {str(e)}"

            # Update status
            self.connection_statuses[device_id].status = "error"
            self.connection_statuses[device_id].error_message = error_msg
            self.connection_statuses[device_id].last_update = time.time()

            # Emit API-level signals
            self.connection_status_changed.emit(device_id, "error", error_msg)
            self.api_error.emit(device_id, "connection_error", error_msg)

            return False, error_msg

    def disconnect_device(self, device_id: Optional[str] = None) -> tuple[bool, str]:
        """
        Disconnect from device(s)

        Args:
            device_id: Specific device to disconnect (None = disconnect current)

        Returns:
            tuple: (success, message)
        """
        try:
            # For now, widget only supports single device
            # In multi-device version, this would target specific device
            self.widget._disconnect_device()

            # Update all known device statuses to disconnected
            for dev_id in self.connection_statuses:
                if device_id is None or dev_id == device_id:
                    self.connection_statuses[dev_id].status = "disconnected"
                    self.connection_statuses[dev_id].last_update = time.time()
                    self.connection_statuses[dev_id].error_message = ""

                    # Emit API-level signal
                    self.connection_status_changed.emit(dev_id, "disconnected", "Disconnected by API")

            return True, "Disconnection initiated"

        except Exception as e:
            error_msg = f"Disconnection error: {str(e)}"
            self.api_error.emit(device_id or "unknown", "disconnection_error", error_msg)
            return False, error_msg

    def get_connection_status(self, device_id: Optional[str] = None) -> Optional[ConnectionStatus]:
        """
        Get connection status for device

        Args:
            device_id: Device ID to check (None = return first/current)

        Returns:
            ConnectionStatus or None if not found
        """
        if device_id is None:
            # Return first available status
            if self.connection_statuses:
                return list(self.connection_statuses.values())[0]
            return None

        return self.connection_statuses.get(device_id)

    def get_all_connection_statuses(self) -> Dict[str, ConnectionStatus]:
        """Get all connection statuses"""
        return self.connection_statuses.copy()

    def refresh_telemetry(self, device_id: Optional[str] = None) -> tuple[bool, str]:
        """
        Refresh telemetry data for device

        Args:
            device_id: Device ID to refresh (None = refresh current)

        Returns:
            tuple: (success, message)
        """
        try:
            # Check if device is connected
            status = self.get_connection_status(device_id)
            if not status or status.status != "connected":
                return False, "Device not connected"

            # Trigger refresh via widget
            self.widget._refresh_all_data()

            return True, "Telemetry refresh initiated"

        except Exception as e:
            error_msg = f"Refresh error: {str(e)}"
            self.api_error.emit(device_id or "unknown", "refresh_error", error_msg)
            return False, error_msg

    def start_auto_refresh(self, interval_seconds: int = 30, device_id: Optional[str] = None) -> tuple[bool, str]:
        """
        Start automatic telemetry refresh

        Args:
            interval_seconds: Refresh interval
            device_id: Device ID (None = current device)

        Returns:
            tuple: (success, message)
        """
        try:
            # For single-device widget, start auto-refresh
            self.widget._toggle_auto_refresh()
            return True, f"Auto-refresh started ({interval_seconds}s interval)"

        except Exception as e:
            error_msg = f"Auto-refresh error: {str(e)}"
            self.api_error.emit(device_id or "unknown", "auto_refresh_error", error_msg)
            return False, error_msg

    def stop_auto_refresh(self, device_id: Optional[str] = None) -> tuple[bool, str]:
        """
        Stop automatic telemetry refresh

        Args:
            device_id: Device ID (None = current device)

        Returns:
            tuple: (success, message)
        """
        try:
            # For single-device widget, stop auto-refresh
            if hasattr(self.widget, 'auto_refresh_button'):
                if "Stop" in self.widget.auto_refresh_button.text():
                    self.widget._toggle_auto_refresh()

            return True, "Auto-refresh stopped"

        except Exception as e:
            error_msg = f"Auto-refresh stop error: {str(e)}"
            self.api_error.emit(device_id or "unknown", "auto_refresh_error", error_msg)
            return False, error_msg

    def get_telemetry_snapshot(self, device_id: Optional[str] = None) -> Optional[TelemetrySnapshot]:
        """
        Get current telemetry data snapshot

        Args:
            device_id: Device ID (None = current device)

        Returns:
            TelemetrySnapshot or None if not available
        """
        if device_id is None:
            if self.telemetry_snapshots:
                return list(self.telemetry_snapshots.values())[0]
            return None

        return self.telemetry_snapshots.get(device_id)

    def get_all_telemetry_snapshots(self) -> Dict[str, TelemetrySnapshot]:
        """Get all telemetry snapshots"""
        return self.telemetry_snapshots.copy()

    def set_theme(self, theme_name: str) -> tuple[bool, str]:
        """
        Set widget theme

        Args:
            theme_name: Theme name to apply

        Returns:
            tuple: (success, message)
        """
        try:
            self.widget.set_theme_programmatic(theme_name)
            return True, f"Theme set to {theme_name}"

        except Exception as e:
            error_msg = f"Theme error: {str(e)}"
            self.api_error.emit("widget", "theme_error", error_msg)
            return False, error_msg

    def export_configuration(self, include_credentials: bool = False) -> Dict[str, Any]:
        """
        Export current configuration

        Args:
            include_credentials: Whether to include sensitive data

        Returns:
            Configuration dictionary
        """
        config = {
            "devices": {},
            "connection_statuses": {},
            "export_timestamp": time.time()
        }

        for device_id, device_config in self.device_configs.items():
            config_dict = device_config.to_dict()

            if not include_credentials:
                # Remove sensitive data
                config_dict.pop("password", None)
                config_dict.pop("secret", None)

            config["devices"][device_id] = config_dict

        for device_id, status in self.connection_statuses.items():
            config["connection_statuses"][device_id] = status.to_dict()

        return config

    def import_configuration(self, config: Dict[str, Any], connect_devices: bool = False) -> tuple[bool, str]:
        """
        Import configuration

        Args:
            config: Configuration dictionary
            connect_devices: Whether to auto-connect devices

        Returns:
            tuple: (success, message)
        """
        try:
            devices_imported = 0

            for device_id, device_data in config.get("devices", {}).items():
                device_config = DeviceConfig.from_dict(device_data)
                self.device_configs[device_id] = device_config
                devices_imported += 1

                if connect_devices:
                    # Attempt to connect
                    self.connect_device(device_config, device_id)

            return True, f"Imported {devices_imported} device configurations"

        except Exception as e:
            error_msg = f"Import error: {str(e)}"
            self.api_error.emit("api", "import_error", error_msg)
            return False, error_msg

    def debug_info(self) -> Dict[str, Any]:
        """
        Get debug information about the API state

        Returns:
            Dictionary with debug information
        """
        return {
            "device_configs_count": len(self.device_configs),
            "device_configs_keys": list(self.device_configs.keys()),
            "connection_statuses_count": len(self.connection_statuses),
            "connection_statuses_keys": list(self.connection_statuses.keys()),
            "telemetry_snapshots_count": len(self.telemetry_snapshots),
            "telemetry_snapshots_keys": list(self.telemetry_snapshots.keys()),
            "widget_connection_status": getattr(self.widget, 'connection_status', 'unknown'),
        }

    # ===== PRIVATE HELPER METHODS =====

    def _config_to_credentials(self, config: DeviceConfig):
        """Convert DeviceConfig to credentials format expected by widget"""
        from termtel.termtelwidgets.netmiko_controller import ConnectionCredentials

        return ConnectionCredentials(
            username=config.username,
            password=config.password,
            secret=config.secret,
            port=config.port,
            timeout=config.timeout,
            auth_timeout=config.auth_timeout
        )

    def _create_device_id(self, hostname: str, ip_address: str) -> str:
        """Create device ID from hostname and IP"""
        return f"{hostname}_{ip_address}"

    # ===== WIDGET SIGNAL HANDLERS =====

    def _on_widget_device_connected(self, hostname: str, ip_address: str, device_info):
        """Handle device connection from widget"""
        device_id = self._create_device_id(hostname, ip_address)

        # Update status
        if device_id in self.connection_statuses:
            self.connection_statuses[device_id].status = "connected"
            self.connection_statuses[device_id].last_update = time.time()
            self.connection_statuses[device_id].error_message = ""

            if device_info:
                self.connection_statuses[device_id].device_info = {
                    "hostname": getattr(device_info, 'hostname', hostname),
                    "platform": getattr(device_info, 'platform', 'unknown'),
                    "version": getattr(device_info, 'version', 'unknown'),
                    "model": getattr(device_info, 'model', 'unknown'),
                    "serial": getattr(device_info, 'serial', 'unknown'),
                    "uptime": getattr(device_info, 'uptime', 'unknown')
                }

        # Emit API-level signals
        self.connection_status_changed.emit(device_id, "connected", f"Connected to {hostname}")

        if device_info:
            device_info_dict = device_info.to_dict()
            self.device_discovered.emit(device_id, device_info_dict)

    def _on_widget_device_disconnected(self, hostname: str, ip_address: str):
        """Handle device disconnection from widget"""
        device_id = self._create_device_id(hostname, ip_address)

        # Update status
        if device_id in self.connection_statuses:
            self.connection_statuses[device_id].status = "disconnected"
            self.connection_statuses[device_id].last_update = time.time()
            self.connection_statuses[device_id].error_message = ""

        # Emit API-level signal
        self.connection_status_changed.emit(device_id, "disconnected", f"Disconnected from {hostname}")

    def _on_widget_device_error(self, hostname: str, ip_address: str, error_msg: str):
        """Handle device error from widget"""
        device_id = self._create_device_id(hostname, ip_address)

        # Update status
        if device_id in self.connection_statuses:
            self.connection_statuses[device_id].status = "error"
            self.connection_statuses[device_id].last_update = time.time()
            self.connection_statuses[device_id].error_message = error_msg

        # Emit API-level signals
        self.connection_status_changed.emit(device_id, "error", error_msg)
        self.api_error.emit(device_id, "device_error", error_msg)

    def _on_widget_telemetry_updated(self, device_id: str, telemetry_snapshot: Dict[str, Any]):
        """Handle telemetry data update from widget"""
        # Create/update telemetry snapshot
        self.telemetry_snapshots[device_id] = TelemetrySnapshot(
            device_id=device_id,
            timestamp=time.time(),
            connection_status=self.connection_statuses.get(device_id, ConnectionStatus("", "", "", "unknown", 0)).status,
            # TODO: Extract actual telemetry data from widget
            # This would need widget to provide structured data
        )

        # Emit API-level signal
        self.telemetry_data_available.emit(device_id, telemetry_snapshot)

    def _on_widget_status_changed(self, status_message: str):
        """Handle general status change from widget"""
        # Could emit general status updates if needed
        pass


# ===== CONVENIENCE FUNCTIONS =====

def create_device_config(hostname: str, ip_address: str, platform: str,
                        username: str, password: str, **kwargs) -> DeviceConfig:
    """
    Convenience function to create DeviceConfig

    Args:
        hostname: Device hostname
        ip_address: Device IP address
        platform: Device platform (cisco_ios_xe, arista_eos, etc.)
        username: SSH username
        password: SSH password
        **kwargs: Additional optional parameters

    Returns:
        DeviceConfig instance
    """
    return DeviceConfig(
        hostname=hostname,
        ip_address=ip_address,
        platform=platform,
        username=username,
        password=password,
        **kwargs
    )


def connect_device_simple(api: TelemetryWidgetAPI, hostname: str, ip_address: str,
                         platform: str, username: str, password: str, **kwargs) -> tuple[bool, str]:
    """
    Convenience function for simple device connection

    Args:
        api: TelemetryWidgetAPI instance
        hostname: Device hostname
        ip_address: Device IP address
        platform: Device platform
        username: SSH username
        password: SSH password
        **kwargs: Additional connection parameters

    Returns:
        tuple: (success, message)
    """
    device_config = create_device_config(
        hostname=hostname,
        ip_address=ip_address,
        platform=platform,
        username=username,
        password=password,
        **kwargs
    )

    return api.connect_device(device_config)


def export_api_config_to_file(api: TelemetryWidgetAPI, filepath: str,
                             include_credentials: bool = False) -> tuple[bool, str]:
    """
    Export API configuration to JSON file

    Args:
        api: TelemetryWidgetAPI instance
        filepath: Output file path
        include_credentials: Whether to include sensitive data

    Returns:
        tuple: (success, message)
    """
    try:
        config = api.export_configuration(include_credentials=include_credentials)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)

        return True, f"Configuration exported to {filepath}"

    except Exception as e:
        return False, f"Export error: {str(e)}"


def import_api_config_from_file(api: TelemetryWidgetAPI, filepath: str,
                               connect_devices: bool = False) -> tuple[bool, str]:
    """
    Import API configuration from JSON file

    Args:
        api: TelemetryWidgetAPI instance
        filepath: Input file path
        connect_devices: Whether to auto-connect devices

    Returns:
        tuple: (success, message)
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            config = json.load(f)

        return api.import_configuration(config, connect_devices=connect_devices)

    except Exception as e:
        return False, f"Import error: {str(e)}"