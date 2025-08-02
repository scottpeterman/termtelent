import socket
import threading
import subprocess
import time
import logging
import os
import sys
from typing import Optional, Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class FlaskServiceManager:
    """
    Manages Flask application lifecycle for TerminalTelemetry Enterprise integration.
    Handles port discovery, service startup, health monitoring, and graceful shutdown.
    """

    def __init__(self,
                 base_port: int = 5000,
                 max_port_attempts: int = 100,
                 app_module: str = "rapidcmdb.app",
                 debug: bool = False):
        self.base_port = base_port
        self.max_port_attempts = max_port_attempts
        self.app_module = app_module
        self.debug = debug

        self.active_port: Optional[int] = None
        self.flask_process: Optional[subprocess.Popen] = None
        self.flask_thread: Optional[threading.Thread] = None
        self.is_running = False
        self.health_check_url = None

        # Callbacks for integration
        self.on_service_ready: Optional[Callable] = None
        self.on_service_error: Optional[Callable] = None

    def is_port_available(self, port: int) -> bool:
        """Check if a port is available for binding."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(('localhost', port))
                return True
        except (socket.error, OSError):
            return False

    def find_available_port(self) -> int:
        """Find the first available port starting from base_port."""
        for port_offset in range(self.max_port_attempts):
            port = self.base_port + port_offset
            if self.is_port_available(port):
                logger.info(f"Found available port: {port}")
                return port

        raise RuntimeError(
            f"No available ports found in range {self.base_port}-{self.base_port + self.max_port_attempts}")

    def get_flask_app_path(self) -> Path:
        """Get the path to the Flask application module."""
        # Try to find the Flask app relative to termtel installation
        current_dir = Path(__file__).parent

        # Look for rapidcmdb directory
        possible_paths = [
            current_dir / "rapidcmdb",
            current_dir.parent / "rapidcmdb",
            Path.cwd() / "rapidcmdb"
        ]

        for path in possible_paths:
            if path.exists() and (path / "app.py").exists():
                return path

        raise FileNotFoundError("RapidCMDB Flask application not found")

    def start_flask_threaded(self) -> None:
        """Start Flask application in a separate thread (for development)."""
        try:
            # Import and run Flask app directly
            flask_path = self.get_flask_app_path()

            # Change working directory to the Flask app directory
            original_cwd = os.getcwd()
            os.chdir(flask_path)

            # Add the Flask app directory to Python path
            sys.path.insert(0, str(flask_path))

            try:
                from app import app

                # Configure Flask for embedded use
                app.config['ENV'] = 'production' if not self.debug else 'development'
                app.config['DEBUG'] = self.debug
                app.config['TESTING'] = False

                logger.info(f"Starting Flask app on port {self.active_port} from directory {flask_path}")
                app.run(host='127.0.0.1', port=self.active_port, debug=False, use_reloader=False)
            finally:
                # Restore original working directory
                os.chdir(original_cwd)

        except Exception as e:
            logger.error(f"Flask thread error: {e}")
            self.is_running = False
            if self.on_service_error:
                self.on_service_error(e)

    def start_flask_subprocess(self) -> None:
        """Start Flask application as a subprocess (for production)."""
        try:
            flask_path = self.get_flask_app_path()
            app_file = flask_path / "app.py"

            # Prepare environment
            env = os.environ.copy()
            env['FLASK_APP'] = "app.py"  # Use relative path since we're setting cwd
            env['FLASK_ENV'] = 'production' if not self.debug else 'development'
            env['RAPIDCMDB_PORT'] = str(self.active_port)

            # Start Flask process with working directory set to rapidcmdb folder
            cmd = [
                sys.executable, "-m", "flask", "run",
                "--host", "127.0.0.1",
                "--port", str(self.active_port)
            ]

            if not self.debug:
                cmd.extend(["--no-reload", "--no-debugger"])

            logger.info(f"Starting Flask subprocess: {' '.join(cmd)}")
            logger.info(f"Working directory: {flask_path}")

            self.flask_process = subprocess.Popen(
                cmd,
                cwd=str(flask_path),  # This is the key fix - set working directory
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Monitor process health
            self._monitor_process()

        except Exception as e:
            logger.error(f"Flask subprocess error: {e}")
            self.is_running = False
            if self.on_service_error:
                self.on_service_error(e)

    def _monitor_process(self) -> None:
        """Monitor Flask process health in background thread."""

        def monitor():
            while self.is_running and self.flask_process:
                if self.flask_process.poll() is not None:
                    # Process died - capture output for debugging
                    stdout, stderr = self.flask_process.communicate()
                    logger.error("Flask process terminated unexpectedly")
                    if stdout:
                        logger.error(f"STDOUT: {stdout}")
                    if stderr:
                        logger.error(f"STDERR: {stderr}")

                    self.is_running = False
                    if self.on_service_error:
                        self.on_service_error("Flask process died")
                    break
                time.sleep(1)

        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()

    def check_service_health(self) -> bool:
        """Check if Flask service is responding."""
        if not self.is_running or not self.active_port:
            return False

        try:
            import requests
            response = requests.get(
                f"http://127.0.0.1:{self.active_port}/",
                timeout=5
            )
            return response.status_code == 200
        except Exception:
            return False

    def wait_for_service_ready(self, timeout: int = 30) -> bool:
        """Wait for Flask service to be ready."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self.check_service_health():
                logger.info("Flask service is ready")
                if self.on_service_ready:
                    self.on_service_ready()
                return True
            time.sleep(0.5)

        logger.error("Flask service failed to start within timeout")
        return False

    def start_service(self, use_subprocess: bool = True) -> str:
        """
        Start the Flask service and return the base URL.

        Args:
            use_subprocess: If True, run Flask as subprocess (recommended for production)
                          If False, run in thread (easier for development/debugging)

        Returns:
            Base URL of the Flask service
        """
        if self.is_running:
            logger.warning("Service is already running")
            return self.get_service_url()

        # Find available port
        try:
            self.active_port = self.find_available_port()
        except RuntimeError as e:
            logger.error(f"Port discovery failed: {e}")
            raise

        # Start service
        self.is_running = True
        self.health_check_url = f"http://127.0.0.1:{self.active_port}/"

        if use_subprocess:
            self.start_flask_subprocess()
        else:
            self.flask_thread = threading.Thread(
                target=self.start_flask_threaded,
                daemon=True
            )
            self.flask_thread.start()

        # Wait for service to be ready
        if not self.wait_for_service_ready():
            self.stop_service()
            raise RuntimeError("Flask service failed to start")

        logger.info(f"Flask service started successfully on {self.get_service_url()}")
        return self.get_service_url()

    def stop_service(self) -> None:
        """Stop the Flask service gracefully."""
        logger.info("Stopping Flask service...")
        self.is_running = False

        if self.flask_process:
            try:
                self.flask_process.terminate()
                self.flask_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Flask process didn't terminate gracefully, killing...")
                self.flask_process.kill()
            finally:
                self.flask_process = None

        if self.flask_thread and self.flask_thread.is_alive():
            # Thread will exit when is_running becomes False
            self.flask_thread.join(timeout=5)
            self.flask_thread = None

        self.active_port = None
        logger.info("Flask service stopped")

    def get_service_url(self) -> str:
        """Get the base URL of the running Flask service."""
        if not self.active_port:
            raise RuntimeError("Service is not running")
        return f"http://127.0.0.1:{self.active_port}"

    def get_api_url(self, endpoint: str = "") -> str:
        """Get a full API URL for the given endpoint."""
        base_url = self.get_service_url()
        if endpoint.startswith('/'):
            endpoint = endpoint[1:]
        return f"{base_url}/{endpoint}" if endpoint else base_url

    def restart_service(self) -> str:
        """Restart the Flask service."""
        logger.info("Restarting Flask service...")
        self.stop_service()
        time.sleep(1)  # Brief pause
        return self.start_service()


# Example usage for TerminalTelemetry integration
class TerminalTelemetryEnterpriseManager:
    """
    Main integration manager for Terminal Telemetry Enterprise features.
    """

    def __init__(self, termtel_app=None):
        self.termtel_app = termtel_app
        self.flask_service = FlaskServiceManager(debug=False)

        # Set up callbacks
        self.flask_service.on_service_ready = self._on_flask_ready
        self.flask_service.on_service_error = self._on_flask_error

    def _on_flask_ready(self):
        """Called when Flask service is ready."""
        logger.info("RapidCMDB service is ready for integration")
        # Add RapidCMDB tab to main interface
        if self.termtel_app and hasattr(self.termtel_app, 'add_enterprise_tab'):
            self.termtel_app.add_enterprise_tab(
                'RapidCMDB',
                self.flask_service.get_service_url()
            )

    def _on_flask_error(self, error):
        """Called when Flask service encounters an error."""
        logger.error(f"RapidCMDB service error: {error}")
        # Handle error in main application
        if self.termtel_app and hasattr(self.termtel_app, 'show_error'):
            self.termtel_app.show_error(f"Enterprise features unavailable: {error}")

    def initialize_enterprise_features(self):
        """Initialize and start enterprise features."""
        try:
            service_url = self.flask_service.start_service()
            logger.info(f"Enterprise features initialized at {service_url}")
            return service_url
        except Exception as e:
            logger.error(f"Failed to initialize enterprise features: {e}")
            raise

    def shutdown_enterprise_features(self):
        """Gracefully shutdown enterprise features."""
        self.flask_service.stop_service()
        logger.info("Enterprise features shut down")


if __name__ == "__main__":
    # Test the service manager
    logging.basicConfig(level=logging.INFO)

    manager = FlaskServiceManager(debug=True)
    try:
        url = manager.start_service(use_subprocess=False)
        print(f"Flask service running at: {url}")

        # Keep alive for testing
        input("Press Enter to stop service...")

    finally:
        manager.stop_service()