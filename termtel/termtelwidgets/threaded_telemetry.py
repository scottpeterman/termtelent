"""
FIXED Threaded Architecture with proper device info collection
The key fix is in _gather_device_info() to properly parse and populate device information
"""

from PyQt6.QtCore import QThread, QObject, pyqtSignal, QTimer
from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException
import time
import threading
from dataclasses import dataclass
from typing import Optional, List, Dict
from termtel.termtelwidgets.netmiko_controller import DeviceInfo, LocalTemplateParser, \
    RawCommandOutput, NormalizedSystemMetrics


@dataclass
class ConnectionConfig:
    """Immutable connection configuration for worker thread"""
    hostname: str
    ip_address: str
    platform: str
    username: str
    password: str
    secret: str = ""
    port: int = 22
    timeout: int = 30
    auth_timeout: int = 10


class TelemetryWorkerThread(QThread):
    """
    FIXED Worker thread with proper device info collection
    """

    # Connection status signals
    connection_established = pyqtSignal(object)  # DeviceInfo
    connection_failed = pyqtSignal(str)  # error_message
    connection_lost = pyqtSignal()

    # Data collection signals
    data_collected = pyqtSignal(str, object, object, object)  # data_type, raw_output, parsed_data, normalized_data
    collection_cycle_complete = pyqtSignal()
    collection_error = pyqtSignal(str, str)  # data_type, error_message

    # Status signals
    status_update = pyqtSignal(str)  # status message

    def __init__(self, connection_config: ConnectionConfig, platform_config, field_normalizer):
        super().__init__()

        self.connection_config = connection_config
        self.platform_config = platform_config
        self.field_normalizer = field_normalizer

        # Worker thread owns these
        self.connection = None
        self.device_info = None
        self.is_connected = False
        self.should_stop = False
        self.auto_collect = False

        # Collection timer (runs in worker thread)
        self.collection_timer = QTimer()
        self.collection_timer.timeout.connect(self._collect_telemetry_cycle)

    def run(self):
        """Main worker thread execution"""
        thread_name = threading.current_thread().name
        print(f" Worker thread {thread_name} starting...")

        try:
            # Step 1: Establish connection in worker thread
            if self._establish_connection():
                print(f" Worker thread connected successfully")

                # Step 2: Initial data collection
                self._collect_telemetry_cycle()

                # Step 3: Start auto-collection if enabled
                if self.auto_collect:
                    self.collection_timer.start(30000)  # 30 seconds

                # Step 4: Keep thread alive for periodic collection
                self.exec()  # Start event loop in worker thread

            else:
                print(f" Worker thread connection failed")

        except Exception as e:
            print(f" Worker thread error: {e}")
            self.connection_failed.emit(str(e))

        finally:
            # Step 5: Clean up
            self._cleanup_connection()
            print(f" Worker thread {thread_name} shutting down")

    def _establish_connection(self) -> bool:
        """Establish netmiko connection in worker thread"""
        self.status_update.emit("Connecting...")

        try:
            # Get netmiko device type from platform config
            netmiko_config = self.platform_config.get_netmiko_config(self.connection_config.platform)

            if netmiko_config:
                device_type = netmiko_config.device_type
                fast_cli = netmiko_config.fast_cli
                timeout = netmiko_config.timeout
                auth_timeout = netmiko_config.auth_timeout
            else:
                # Fallback device type mapping
                device_type = self._get_fallback_device_type()
                fast_cli = False
                timeout = self.connection_config.timeout
                auth_timeout = self.connection_config.auth_timeout

            connection_params = {
                'device_type': device_type,
                'host': self.connection_config.ip_address,
                'username': self.connection_config.username,
                'password': self.connection_config.password,
                'secret': self.connection_config.secret,
                'port': self.connection_config.port,
                'timeout': timeout,
                'auth_timeout': auth_timeout,
                'fast_cli': fast_cli,
            }

            print(f" Worker connecting to {self.connection_config.ip_address} as {device_type}...")

            # Create connection in THIS thread
            self.connection = ConnectHandler(**connection_params)

            # Test connection
            test_command = self._get_test_command(device_type)
            test_output = self.connection.send_command(test_command, read_timeout=10)

            if test_output:
                # Connection successful - gather device info
                self._gather_device_info()
                self.is_connected = True
                self.status_update.emit("Connected")
                self.connection_established.emit(self.device_info)
                return True
            else:
                self.connection_failed.emit("Connection test failed")
                return False

        except NetmikoAuthenticationException as e:
            self.connection_failed.emit(f"Authentication failed: {str(e)}")

            return False
        except NetmikoTimeoutException as e:
            self.connection_failed.emit(f"Connection timeout: {str(e)}")
            return False
        except Exception as e:
            self.connection_failed.emit(f"Connection error: {str(e)}")
            return False

    def _get_fallback_device_type(self) -> str:
        """Get fallback device type mapping"""
        platform_mapping = {
            'cisco_ios_xe': 'cisco_xe',
            'cisco_ios': 'cisco_ios',
            'cisco_nxos': 'cisco_nxos',
            'arista_eos': 'arista_eos',
            'linux': 'linux'
        }
        return platform_mapping.get(self.connection_config.platform, 'cisco_ios')

    def _get_test_command(self, device_type: str) -> str:
        """Get simple test command"""
        if device_type.startswith('cisco') or device_type == 'arista_eos':
            return "show clock"
        elif device_type == 'linux':
            return "date"
        else:
            return "show version"

    def _gather_device_info(self):
        """FIXED: Gather device information using worker connection"""
        print(" Worker gathering device information...")



        # Create basic device info with connection details
        self.device_info = DeviceInfo(
            hostname=self.connection_config.hostname,
            ip_address=self.connection_config.ip_address,
            platform=self.connection_config.platform,
            connection_status="connected"
        )

        # FIXED: Try to get detailed info via show version
        try:
            # Get the system_info command from platform config
            sys_info_command = self.platform_config.format_command(
                self.connection_config.platform, 'system_info'
            )

            print(f" System info command: {sys_info_command}")

            if not sys_info_command.startswith("#"):
                print(f" Executing system info command...")
                output = self.connection.send_command(sys_info_command, read_timeout=15)
                print(f" Got system info output ({len(output)} chars)")

                # Parse the output
                parsed_data = self._parse_system_info(output)
                print(f" Parsed system info: {parsed_data}")

                if parsed_data and len(parsed_data) > 0:
                    # Normalize the parsed data
                    normalized_info = self.field_normalizer.normalize_system_info(
                        parsed_data, self.connection_config.platform
                    )
                    print(f" Normalized system info: {normalized_info}")

                    # FIXED: Update device info with parsed details
                    if 'hostname' in normalized_info and normalized_info['hostname']:
                        self.device_info.hostname = normalized_info['hostname']
                        print(f" Updated hostname: {self.device_info.hostname}")

                    if 'version' in normalized_info and normalized_info['version']:
                        self.device_info.version = normalized_info['version']
                        print(f" Updated version: {self.device_info.version}")

                    if 'model' in normalized_info and normalized_info['model']:
                        self.device_info.model = normalized_info['model']
                        print(f" Updated model: {self.device_info.model}")

                    if 'serial' in normalized_info and normalized_info['serial']:
                        self.device_info.serial = normalized_info['serial']
                        print(f" Updated serial: {self.device_info.serial}")

                    if 'uptime' in normalized_info and normalized_info['uptime']:
                        self.device_info.uptime = normalized_info['uptime']
                        print(f" Updated uptime: {self.device_info.uptime}")

                else:
                    print(" No parsed data from system info command")
            else:
                print(f" No system info command configured for platform {self.connection_config.platform}")

        except Exception as e:
            print(f" Could not gather detailed device info: {e}")
            import traceback
            traceback.print_exc()

        # ALWAYS emit the device info, even if parsing failed
        print(f" Final device info:")
        print(f"  Hostname: {self.device_info.hostname}")
        print(f"  Model: {self.device_info.model}")
        print(f"  Version: {self.device_info.version}")
        print(f"  Serial: {self.device_info.serial}")
        print(f"  Uptime: {self.device_info.uptime}")

    def _parse_system_info(self, output: str) -> Optional[List[Dict]]:
        """FIXED: Parse system info output with better error handling"""
        try:
            print(" Attempting to parse system info...")

            template_info = self.platform_config.get_template_info(
                self.connection_config.platform, 'system_info'
            )

            if template_info:
                template_platform, template_file = template_info
                template_command = template_file.replace('.textfsm', '').replace(f'{template_platform}_', '')

                print(f" Using template: {template_platform} / {template_command}")

                parser = LocalTemplateParser()
                parsed_data = parser.parse(template_platform, template_command, output)

                print(f" Template parsing result: {parsed_data}")
                return parsed_data

            else:
                print(" No template info found for system_info")

        except Exception as e:
            print(f" System info parsing error: {e}")
            import traceback
            traceback.print_exc()

        return None

    def _collect_telemetry_cycle(self):
        """Collect one complete cycle of telemetry data"""
        if not self.is_connected or not self.connection:
            return

        print(f" Worker starting telemetry collection cycle...")
        self.status_update.emit("Collecting telemetry data...")

        telemetry_tasks = [
            ("neighbors", "cdp_neighbors", {}),
            ("arp", "arp_table", {}),
            ("routes", "route_table", {}),
            ("cpu", "cpu_utilization", {}),
            ("memory", "memory_utilization", {}),
            ("logs", "logs", {}),
        ]

        for data_type, command_type, kwargs in telemetry_tasks:
            if self.should_stop:
                break

            try:
                self._collect_single_telemetry(data_type, command_type, kwargs)

                # Small delay between commands
                self.msleep(200)

            except Exception as e:
                print(f" Error collecting {data_type}: {e}")
                self.collection_error.emit(data_type, str(e))

        self.status_update.emit("Collection complete")
        self.collection_cycle_complete.emit()
        print(f" Worker telemetry collection cycle complete")

    def _collect_single_telemetry(self, data_type: str, command_type: str, kwargs: Dict):
        """Collect single telemetry data type - FIXED VERSION"""

        # === ENHANCED DEBUG FOR LOGS ===
        if data_type == "logs":
            print(f"\n === _collect_single_telemetry LOGS DEBUG ===")
            print(f" Data type: {data_type}")
            print(f" Command type: {command_type}")
            print(f" Platform: {self.connection_config.platform}")

        # Get platform command
        command = self.platform_config.format_command(
            self.connection_config.platform, command_type, **kwargs
        )

        # === MORE DEBUG FOR LOGS ===
        if data_type == "logs":
            print(f" format_command result: '{command}'")
            print(f" Command starts with #: {command.startswith('#')}")

        if command.startswith("#"):
            print(f" No command configured for {command_type}")
            if data_type == "logs":
                print(f" LOGS: Command lookup failed - '{command}'")
            return

        # Execute command using worker's connection
        print(f" Worker executing: {command}")

        # === FINAL DEBUG FOR LOGS ===
        if data_type == "logs":
            print(f" About to execute logs command: '{command}'")
            print(f" Connection available: {self.connection is not None}")
        print(f"sending command raw: {command}")
        output = self.connection.send_command(command, read_timeout=30)
        # print(f"raw output: {output}")
        if data_type == "logs":
            print(f" Logs command output length: {len(output)} characters")
            print(f" First 200 chars: {output[:200]}")
            print(f" === END _collect_single_telemetry LOGS DEBUG ===\n")

        # Parse output
        if command_type == 'logs':
            print(f" Logs: Skipping template parsing, using raw output")
            parsed_data = None  # Skip parsing for logs
            normalized_data = None  # Skip normalization for logs
        else:
            # Parse output for other data types
            parsed_data = self._parse_output(command_type, output)

            # FIXED: Create proper normalized data for CPU/memory
            normalized_data = None
            if parsed_data:
                if command_type == 'cpu_utilization':
                    normalized_data = self._create_system_metrics_from_cpu(parsed_data)
                elif command_type == 'memory_utilization':
                    normalized_data = self._create_system_metrics_from_memory(parsed_data)
                else:
                    normalized_data = self._normalize_data(command_type, parsed_data)

        # Create raw output object
        raw_output = RawCommandOutput(
            command=command,
            output=output,
            platform=self.connection_config.platform,
            timestamp=time.time(),
            parsed_successfully=bool(parsed_data),
            parsed_data=parsed_data
        )

        # Emit to main thread
        self.data_collected.emit(data_type, raw_output, parsed_data, normalized_data)
        print(f" Worker completed {data_type}")
    def _create_system_metrics_from_cpu(self, parsed_data):
        """Create NormalizedSystemMetrics from CPU data"""
        if not parsed_data:
            return None

        try:

            cpu_entry = parsed_data[0]
            print(f" Creating system metrics from CPU data: {list(cpu_entry.keys())}")

            metrics = NormalizedSystemMetrics()
            metrics.platform = self.connection_config.platform
            metrics.timestamp = time.time()

            # Extract CPU usage
            if self.connection_config.platform.startswith('arista'):
                # Arista: Rich CPU data
                if 'GLOBAL_CPU_PERCENT_IDLE' in cpu_entry:
                    idle_percent = float(cpu_entry['GLOBAL_CPU_PERCENT_IDLE'])
                    metrics.cpu_usage_percent = 100.0 - idle_percent
                elif 'GLOBAL_CPU_PERCENT_USER' in cpu_entry and 'GLOBAL_CPU_PERCENT_SYSTEM' in cpu_entry:
                    user_percent = float(cpu_entry['GLOBAL_CPU_PERCENT_USER'])
                    system_percent = float(cpu_entry['GLOBAL_CPU_PERCENT_SYSTEM'])
                    metrics.cpu_usage_percent = user_percent + system_percent

                # Extract memory data if available (Arista's top command has both)
                if 'GLOBAL_MEM_TOTAL' in cpu_entry:
                    mem_unit = cpu_entry.get('GLOBAL_MEM_UNIT', 'KiB')
                    total_value = float(cpu_entry['GLOBAL_MEM_TOTAL'])
                    used_value = float(cpu_entry.get('GLOBAL_MEM_USED', 0))
                    free_value = float(cpu_entry.get('GLOBAL_MEM_FREE', 0))

                    # Convert to MB
                    if mem_unit.lower() in ['kib', 'k']:
                        metrics.memory_total_mb = int(total_value // 1024)
                        metrics.memory_used_mb = int(used_value // 1024)
                        metrics.memory_free_mb = int(free_value // 1024)
                    elif mem_unit.lower() in ['mib', 'm']:
                        metrics.memory_total_mb = int(total_value)
                        metrics.memory_used_mb = int(used_value)
                        metrics.memory_free_mb = int(free_value)

                    if metrics.memory_used_mb == 0 and metrics.memory_free_mb > 0:
                        metrics.memory_used_mb = metrics.memory_total_mb - metrics.memory_free_mb

                    if metrics.memory_total_mb > 0:
                        metrics.memory_used_percent = (metrics.memory_used_mb / metrics.memory_total_mb) * 100.0

                # Extract load averages if available
                if 'GLOBAL_LOAD_AVERAGE_1_MINUTES' in cpu_entry:
                    metrics.load_1min = float(cpu_entry['GLOBAL_LOAD_AVERAGE_1_MINUTES'])
                if 'GLOBAL_LOAD_AVERAGE_5_MINUTES' in cpu_entry:
                    metrics.load_5min = float(cpu_entry['GLOBAL_LOAD_AVERAGE_5_MINUTES'])

                # Extract process counts if available
                if 'GLOBAL_TASKS_TOTAL' in cpu_entry:
                    metrics.process_count_total = int(cpu_entry['GLOBAL_TASKS_TOTAL'])
                if 'GLOBAL_TASKS_RUNNING' in cpu_entry:
                    metrics.process_count_running = int(cpu_entry['GLOBAL_TASKS_RUNNING'])

            elif self.connection_config.platform.startswith('cisco'):
                # Cisco: Simple CPU fields
                for field in ['CPU_USAGE_5_SEC', 'CPU_5_SEC', 'CPU_USAGE']:
                    if field in cpu_entry:
                        metrics.cpu_usage_percent = float(cpu_entry[field])
                        break

            print(
                f" Created metrics: CPU={metrics.cpu_usage_percent}%, Memory={metrics.memory_used_percent}%, Total_MB={metrics.memory_total_mb}")
            return metrics

        except Exception as e:
            print(f" Error creating system metrics: {e}")
            return None

    def _create_system_metrics_from_memory(self, parsed_data):
        """Create NormalizedSystemMetrics from memory data - FIXED VERSION"""
        if not parsed_data:
            return None

        try:

            # For memory-only data, create metrics with ONLY memory fields populated
            metrics = NormalizedSystemMetrics()
            metrics.platform = self.connection_config.platform
            metrics.timestamp = time.time()

            # Only set memory fields, leave CPU fields at 0 (which won't overwrite existing CPU data)
            # The CPU widget should handle partial updates properly

            if self.connection_config.platform.startswith('cisco'):
                # Cisco: Simple memory pools
                for entry in parsed_data:
                    if entry.get('POOL') == 'Processor':
                        try:
                            total_bytes = int(entry['TOTAL'])
                            used_bytes = int(entry['USED'])
                            free_bytes = int(entry['FREE'])

                            used_percent = (used_bytes / total_bytes) * 100
                            total_mb = total_bytes // (1024 * 1024)
                            used_mb = used_bytes // (1024 * 1024)
                            free_mb = free_bytes // (1024 * 1024)

                            metrics.memory_used_percent = used_percent
                            metrics.memory_total_mb = total_mb
                            metrics.memory_used_mb = used_mb
                            metrics.memory_free_mb = free_mb

                            print(
                                f" Created MEMORY-ONLY metrics: Memory={metrics.memory_used_percent}%, Total_MB={metrics.memory_total_mb}")
                            return metrics

                        except (ValueError, KeyError) as e:
                            print(f" Error parsing Cisco memory: {e}")
                            continue

            elif self.connection_config.platform.startswith('arista'):
                # For Arista, memory often comes with CPU, so fall back to the full method
                return self._create_system_metrics_from_cpu(parsed_data)

            # If we couldn't parse memory data, return None instead of empty metrics
            print(f" No memory data could be parsed for platform: {self.connection_config.platform}")
            return None

        except Exception as e:
            print(f" Error creating memory-only metrics: {e}")
            return None

    def _parse_output(self, command_type: str, output: str):
        """Parse command output using templates"""
        try:
            template_info = self.platform_config.get_template_info(
                self.connection_config.platform, command_type
            )

            if not template_info:
                return None

            template_platform, template_file = template_info
            template_command = template_file.replace('.textfsm', '').replace(f'{template_platform}_', '')

            parser = LocalTemplateParser()
            return parser.parse(template_platform, template_command, output)

        except Exception as e:
            print(f" Worker parsing error: {e}")
            return None

    def _normalize_data(self, command_type: str, parsed_data):
        """Normalize parsed data"""
        try:
            if command_type in ['cdp_neighbors', 'lldp_neighbors']:
                return self.field_normalizer.normalize_neighbors(
                    parsed_data, self.connection_config.platform, command_type
                )
            elif command_type == 'arp_table':
                return self.field_normalizer.normalize_arp(
                    parsed_data, self.connection_config.platform
                )
            elif command_type in ['route_table', 'route_table_vrf']:
                return self.field_normalizer.normalize_routes(
                    parsed_data, self.connection_config.platform
                )
            elif command_type == 'cpu_utilization':
                return self._normalize_cpu_data(parsed_data)
            else:
                return parsed_data

        except Exception as e:
            print(f" Worker normalization error: {e}")
            return None

    def _normalize_cpu_data(self, parsed_data):
        """Normalize CPU data"""
        if not parsed_data:
            return None

        try:
            cpu_entry = parsed_data[0]
            cpu_usage = 0.0

            for field_name in ['CPU_USAGE_5_SEC', 'CPU_5_SEC', 'CPU_USAGE']:
                if field_name in cpu_entry:
                    cpu_usage = float(cpu_entry[field_name])
                    break

            return {
                'cpu_usage': cpu_usage,
                'timestamp': time.time(),
                'platform': self.connection_config.platform
            }

        except Exception as e:
            print(f" CPU normalization error: {e}")
            return None

    def _cleanup_connection(self):
        """Clean up worker connection"""
        self.collection_timer.stop()

        if self.connection:
            try:
                self.connection.disconnect()
                print(f" Worker connection cleaned up")
            except:
                pass
            finally:
                self.connection = None
                self.is_connected = False

    # Control methods (called from main thread)
    def start_auto_collection(self, interval_seconds: int = 30):
        """Start automatic telemetry collection"""
        self.auto_collect = True
        if self.collection_timer:
            self.collection_timer.start(interval_seconds * 1000)

    def stop_auto_collection(self):
        """Stop automatic telemetry collection"""
        self.auto_collect = False
        if self.collection_timer:
            self.collection_timer.stop()

    def request_immediate_collection(self):
        """Request immediate telemetry collection"""
        if self.is_connected:
            QTimer.singleShot(0, self._collect_telemetry_cycle)

    def stop_worker(self):
        """Stop the worker thread"""
        self.should_stop = True
        self.auto_collect = False
        self.quit()


class ThreadedTelemetryController(QObject):
    """
    Controller that manages worker thread for telemetry collection
    Completely replaces blocking netmiko operations
    """
    connection_status_changed = pyqtSignal(str, str)  # device_ip, status
    connection_error_occurred = pyqtSignal(str, str, str)

    # Forward all the same signals as original controller
    raw_cdp_output = pyqtSignal(object)
    raw_arp_output = pyqtSignal(object)
    raw_route_output = pyqtSignal(object)
    raw_cpu_output = pyqtSignal(object)
    raw_memory_output = pyqtSignal(object)
    raw_log_output = pyqtSignal(object)
    raw_system_info_output = pyqtSignal(object)

    normalized_neighbors_ready = pyqtSignal(list)
    normalized_arp_ready = pyqtSignal(list)
    normalized_routes_ready = pyqtSignal(list)
    normalized_system_ready = pyqtSignal(object)
    normalized_system_metrics_ready = pyqtSignal(object)

    device_info_updated = pyqtSignal(object)
    connection_status_changed = pyqtSignal(str, str)
    theme_changed = pyqtSignal(str)

    def __init__(self, original_controller):
        super().__init__()
        self.connection_hostname = ""
        self.connection_ip = ""
        self.original_controller = original_controller
        self.worker_thread = None
        self.is_connected = False
        self.device_info = None

        # Replace the timer behavior
        self.data_collection_timer = QTimer()
        self.data_collection_timer.timeout.connect(self.collect_telemetry_data)

    def connect_to_device(self, hostname: str, ip_address: str, platform: str, credentials) -> bool:
        """Connect to device using worker thread"""
        print(f" Starting threaded connection to {hostname} ({ip_address})")

        # Store connection details for error reporting
        self.connection_hostname = hostname
        self.connection_ip = ip_address

        # Stop any existing worker
        if self.worker_thread and self.worker_thread.isRunning():
            print(" Stopping existing worker...")
            self.worker_thread.stop_worker()
            self.worker_thread.wait(3000)

        # Create connection configuration
        connection_config = ConnectionConfig(
            hostname=hostname,
            ip_address=ip_address,
            platform=platform,
            username=credentials.username,
            password=credentials.password,
            secret=credentials.secret,
            port=credentials.port,
            timeout=credentials.timeout,
            auth_timeout=credentials.auth_timeout
        )

        # Create worker thread
        self.worker_thread = TelemetryWorkerThread(
            connection_config=connection_config,
            platform_config=self.original_controller.platform_config,
            field_normalizer=self.original_controller.field_normalizer
        )

        # Connect signals
        self.worker_thread.connection_established.connect(self._on_connection_established)
        self.worker_thread.connection_failed.connect(self._on_connection_failed)
        self.worker_thread.data_collected.connect(self._on_data_collected)

        # Start worker thread
        self.worker_thread.start()
        return True

    def _on_connection_established(self, device_info):
        """Handle successful connection from worker"""
        print(f" Worker connection established")
        print(f" Device info received:")
        print(f"  Hostname: {device_info.hostname}")
        print(f"  Model: {device_info.model}")
        print(f"  Version: {device_info.version}")
        print(f"  Serial: {device_info.serial}")
        print(f"  Uptime: {device_info.uptime}")

        self.is_connected = True
        self.device_info = device_info
        self.connection_status_changed.emit(device_info.ip_address, "connected")
        self.device_info_updated.emit(device_info)

    def _on_connection_failed(self, error_message: str):
        """Handle connection failure from worker - FIXED VERSION"""
        print(f" Worker connection failed: {error_message}")
        self.is_connected = False
        # Only emit status change - don't show dialog here
        self.connection_status_changed.emit("", f"connection failed: {error_message}")
        # The widget will handle showing the error to the user

    def _on_data_collected(self, data_type: str, raw_output, parsed_data, normalized_data):
        """Handle data from worker thread - FIXED VERSION"""
        print(f" Received {data_type} from worker")

        # Route to appropriate signals
        if data_type == "neighbors":
            self.raw_cdp_output.emit(raw_output)
            if normalized_data:
                self.normalized_neighbors_ready.emit(normalized_data)

        elif data_type == "arp":
            self.raw_arp_output.emit(raw_output)
            if normalized_data:
                self.normalized_arp_ready.emit(normalized_data)

        elif data_type == "routes":
            self.raw_route_output.emit(raw_output)
            if normalized_data:
                self.normalized_routes_ready.emit(normalized_data)

        elif data_type == "cpu":
            self.raw_cpu_output.emit(raw_output)

            # === FIXED: Convert CPU data to NormalizedSystemMetrics ===
            if normalized_data:
                print(f" Converting CPU data to NormalizedSystemMetrics...")

                # Check if we already have proper NormalizedSystemMetrics
                if hasattr(normalized_data, 'cpu_usage_percent'):
                    # It's already a NormalizedSystemMetrics object
                    print(f" Already proper metrics: CPU={normalized_data.cpu_usage_percent}%")
                    self.normalized_system_metrics_ready.emit(normalized_data)

                elif isinstance(normalized_data, dict) and 'cpu_usage' in normalized_data:
                    # Convert worker's simple format to full metrics
                    metrics = NormalizedSystemMetrics(
                        cpu_usage_percent=normalized_data['cpu_usage'],
                        platform=normalized_data['platform'],
                        timestamp=normalized_data['timestamp']
                    )
                    print(f" Created metrics: CPU={metrics.cpu_usage_percent}%")
                    self.normalized_system_metrics_ready.emit(metrics)

                else:
                    print(f" Unexpected CPU normalized_data format: {type(normalized_data)}")
                    print(f"    Data: {normalized_data}")

        elif data_type == "memory":
            self.raw_memory_output.emit(raw_output)

            # Memory data might also contain system metrics
            if normalized_data and hasattr(normalized_data, 'memory_used_percent'):
                print(f" Memory metrics: {normalized_data.memory_used_percent}%")
                self.normalized_system_metrics_ready.emit(normalized_data)

        elif data_type == "logs":
            self.raw_log_output.emit(raw_output)

        else:
            print(f" Unknown data type: {data_type}")

    def _on_collection_complete(self):
        """Handle completion of collection cycle"""
        print(f" Worker collection cycle complete")

    def _on_status_update(self, status: str):
        """Handle status updates from worker"""
        print(f" Worker status: {status}")

    def collect_telemetry_data(self):
        """Request telemetry collection from worker"""
        if self.worker_thread and self.worker_thread.is_connected:
            print(f" Requesting immediate collection from worker")
            self.worker_thread.request_immediate_collection()
        else:
            print(f" No worker connection available")

    def disconnect_from_device(self):
        """Disconnect from device"""
        if self.worker_thread and self.worker_thread.isRunning():
            print(f" Disconnecting worker thread")
            self.worker_thread.stop_worker()
            self.worker_thread.wait(3000)

        self.is_connected = False
        if self.device_info:
            self.connection_status_changed.emit(self.device_info.ip_address, "disconnected")

    def start_auto_refresh(self, interval_seconds: int = 30):
        """Start auto-refresh using worker thread"""
        if self.worker_thread:
            self.worker_thread.start_auto_collection(interval_seconds)

    def stop_auto_refresh(self):
        """Stop auto-refresh"""
        if self.worker_thread:
            self.worker_thread.stop_auto_collection()

    def __getattr__(self, name):
        """Forward other attributes to original controller"""
        return getattr(self.original_controller, name)
