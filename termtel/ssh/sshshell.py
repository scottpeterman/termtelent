from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from .sshshellreader import ShellReaderThread
from PyQt6.QtWidgets import QMessageBox
import paramiko


class Backend(QObject):
    send_output = pyqtSignal(str)
    buffer = ""

    def __init__(self, host, username, password=None, port='22', key_path=None, parent_widget=None, parent=None):
        super().__init__(parent)
        self.parent_widget = parent_widget
        self.client = None
        self.channel = None
        self.reader_thread = None
        self.auth_method_used = None

        # Define preferred cipher, kex, and key settings for better compatibility
        self.cipher_settings = (
            "aes128-cbc",
            "aes128-ctr",
            "aes192-ctr",
            "aes256-ctr",
            "aes256-cbc",
            "3des-cbc",
            "aes192-cbc",
            "aes256-gcm@openssh.com",
            "aes128-gcm@openssh.com",
            "chacha20-poly1305@openssh.com"
        )

        self.kex_settings = (
            "diffie-hellman-group14-sha1",
            "diffie-hellman-group-exchange-sha1",
            "diffie-hellman-group-exchange-sha256",
            "diffie-hellman-group1-sha1",
            "ecdh-sha2-nistp256",
            "ecdh-sha2-nistp384",
            "ecdh-sha2-nistp521",
            "curve25519-sha256",
            "curve25519-sha256@libssh.org",
            "diffie-hellman-group16-sha512",
            "diffie-hellman-group18-sha512"
        )

        self.key_settings = (
            "ssh-rsa",
            "ssh-dss",
            "ecdsa-sha2-nistp256",
            "ecdsa-sha2-nistp384",
            "ecdsa-sha2-nistp521",
            "ssh-ed25519",
            "rsa-sha2-256",
            "rsa-sha2-512"
        )

        try:
            # Apply transport settings
            self._apply_transport_settings()

            self.client = paramiko.SSHClient()
            self.client.load_system_host_keys()  # Load known host keys from the system
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # Automatically add unknown hosts

            host = str(host).strip()
            username = str(username).strip()
            port = int(port)

            # Try to detect available authentication methods
            available_methods = self._detect_available_auth_methods(host, port, username)
            auth_methods_to_try = ["password", "keyboard-interactive"]  # Default auth methods

            # If we detected auth methods, prioritize those supported by the server
            if available_methods:
                auth_methods_to_try = [method for method in auth_methods_to_try if method in available_methods]
                if not auth_methods_to_try:  # If no matches, fall back to defaults
                    print(f"No matching auth methods found, falling back to defaults")
                    auth_methods_to_try = ["password", "keyboard-interactive"]

            if key_path:
                self._try_key_auth(host, port, username, key_path)
            else:
                password = str(password).strip() if password else ""
                auth_success = False

                # Try each auth method in order
                for auth_method in auth_methods_to_try:
                    if auth_success:
                        break

                    try:
                        if auth_method == "password":
                            print(f"Trying password authentication")
                            self._try_password_auth(host, port, username, password)
                            auth_success = True
                            self.auth_method_used = "password"
                        elif auth_method == "keyboard-interactive":
                            print(f"Trying keyboard-interactive authentication")
                            self._try_keyboard_interactive_auth(host, port, username, password)
                            auth_success = True
                            self.auth_method_used = "keyboard-interactive"
                    except (paramiko.AuthenticationException, paramiko.SSHException) as e:
                        print(f"Auth method {auth_method} failed: {e}")
                        continue

                if not auth_success:
                    self.notify("Login Failure", f"All authentication methods failed for {host}")
                    return

            # Get transport and set keepalive
            transport = self.client.get_transport()
            transport.set_keepalive(60)

            self.setup_shell()

        except Exception as e:
            self.notify("Connection Error", str(e))
            print(e)

    def _apply_transport_settings(self):
        """Apply custom transport settings for better compatibility"""
        paramiko.Transport._preferred_ciphers = self.cipher_settings
        paramiko.Transport._preferred_kex = self.kex_settings
        paramiko.Transport._preferred_keys = self.key_settings
        print("Applied custom transport settings for compatibility")

    def _detect_available_auth_methods(self, host, port, username):
        """Detect available authentication methods from the server"""
        print(f"Detecting supported authentication methods for {host}")
        transport = None

        try:
            # Create a transport to get available auth methods
            transport = paramiko.Transport((host, port))
            transport.start_client()

            # Get available auth methods
            try:
                transport.auth_none(username)
            except paramiko.ssh_exception.BadAuthenticationType as e:
                # This exception contains the available auth methods
                available_methods = e.allowed_types
                print(f"Server supports: {', '.join(available_methods)}")
                return available_methods

        except Exception as e:
            print(f"Auth detection error: {str(e)}")
        finally:
            if transport and transport.is_active():
                transport.close()

        # If detection fails, return empty list and fall back to defaults
        return []

    def _try_key_auth(self, host, port, username, key_path):
        """Try authentication with RSA key"""
        print(f"Trying key authentication with {key_path}")
        try:
            private_key = paramiko.RSAKey(filename=key_path.strip())
            self.client.connect(hostname=host, port=port, username=username, pkey=private_key)
            self.auth_method_used = "publickey"
        except paramiko.AuthenticationException:
            self.notify("Login Failure", f"Authentication Failed: {host}")
            raise
        except paramiko.SSHException as e:
            self.notify("Login Failure", f"Connection Failed: {host} Reason: {e}")
            raise
        except Exception as e:
            self.notify("Error", str(e))
            raise

    def _try_password_auth(self, host, port, username, password):
        """Try password authentication"""
        try:
            self.client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                look_for_keys=False,
                allow_agent=False
            )
        except Exception as e:
            print(f"Password auth error: {e}")
            raise

    def _try_keyboard_interactive_auth(self, host, port, username, password):
        """Try keyboard-interactive authentication"""
        # Close existing client if there is one
        if self.client:
            self.client.close()

        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Create a transport directly
        transport = paramiko.Transport((host, port))
        transport.start_client()

        # Define keyboard-interactive handler that always returns the password
        def handler(title, instructions, prompt_list):
            print(f"Interactive auth: Received {len(prompt_list)} prompts")
            # Always return the password for any prompt
            return [password] * len(prompt_list)

        # Attempt keyboard-interactive auth
        try:
            transport.auth_interactive(username, handler)

            if transport.is_authenticated():
                # Attach the transport to our client
                self.client._transport = transport
            else:
                transport.close()
                raise paramiko.ssh_exception.AuthenticationException("Keyboard-interactive authentication failed")
        except Exception as e:
            if transport and transport.is_active():
                transport.close()
            raise

    def setup_shell(self):
        try:
            self.channel = self.client.invoke_shell("xterm")
            self.channel.set_combine_stderr(True)
            print("Invoked Shell!")
        except Exception as e:
            print(f"Shell not supported, falling back to pty...")
            transport = self.client.get_transport()
            options = transport.get_security_options()
            print(options)

            self.channel = transport.open_session()
            self.channel.get_pty()  # Request a pseudo-terminal
            self.channel.set_combine_stderr(True)

        # Start reading the channel
        if self.channel is not None:
            self.reader_thread = ShellReaderThread(self.channel, self.buffer, parent_widget=self.parent_widget)
            self.reader_thread.data_ready.connect(self.send_output)
            self.reader_thread.start()

    def notify(self, message, info):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(info)
        msg.setWindowTitle(message)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        retval = msg.exec()

    @pyqtSlot(str)
    def write_data(self, data):
        if self.channel and self.channel.send_ready():
            try:
                self.channel.send(data)
            except paramiko.SSHException as e:
                print(f"Error while writing to channel: {e}")
            except Exception as e:
                print(f"Channel error {e}")
                self.notify("Closed", "Connection is closed.")
                pass
        else:
            print("Error: Channel is not ready or doesn't exist")
            self.notify("Error", "Channel is not ready or doesn't exist")

    @pyqtSlot(str)
    def set_pty_size(self, data):
        if self.channel and self.channel.send_ready():
            try:
                cols = data.split("::")[0]
                cols = int(cols.split(":")[1])
                rows = data.split("::")[1]
                rows = int(rows.split(":")[1])
                self.channel.resize_pty(width=cols, height=rows)
                print(f"backend pty resize -> cols:{cols} rows:{rows}")
            except paramiko.SSHException as e:
                print(f"Error setting backend pty term size: {e}")
        else:
            print("Error: Channel is not ready or doesn't exist")

    def __del__(self):
        try:
            if self.reader_thread and self.reader_thread.isRunning():
                self.reader_thread.terminate()
        except:
            pass
        if self.channel:
            self.channel.close()

        if self.client:
            self.client.close()