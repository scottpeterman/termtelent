# helpers/credslib.py
import os
import shutil
import sys
import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import keyring
import yaml

logger = logging.getLogger(__name__)


class SecureCredentials:
    """Secure credential management system for Windows, Linux, and macOS."""

    def __init__(self, app_name: str = "termtelent"):
        self.app_name = app_name
        self._fernet = None
        self.config_dir = self._get_config_dir()
        self.key_identifier = f"{app_name}_key_id"
        self.is_initialized = self._check_initialization()

    def _get_config_dir(self) -> Path:
        """Get the appropriate configuration directory for the current platform."""
        if sys.platform == "win32":
            base_dir = Path(os.environ["APPDATA"])
        elif sys.platform == "darwin":
            base_dir = Path.home() / "Library" / "Application Support"
        else:  # Linux and other Unix-like
            base_dir = Path.home() / ".config"

        config_dir = base_dir / self.app_name
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir

    def _check_initialization(self) -> bool:
        """Check if the credential system has been initialized."""
        salt_path = self.config_dir / ".salt"
        return salt_path.exists()

    def is_unlocked(self) -> bool:
        """Check if the credential manager is unlocked."""
        return self._fernet is not None

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """Derive a key from password and salt using PBKDF2."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))

    def _get_machine_id(self) -> str:
        """Get a unique machine identifier that persists across reboots."""
        if sys.platform == "win32":
            import winreg
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                    "SOFTWARE\\Microsoft\\Cryptography", 0,
                                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                    return winreg.QueryValueEx(key, "MachineGuid")[0]
            except Exception:
                logger.warning("Failed to get Windows MachineGuid")
        elif sys.platform == "darwin":
            try:
                import subprocess
                result = subprocess.run(['system_profiler', 'SPHardwareDataType'],
                                        capture_output=True, text=True)
                for line in result.stdout.split('\n'):
                    if "Serial Number" in line:
                        return line.split(":")[1].strip()
            except Exception:
                logger.warning("Failed to get macOS hardware serial")

        try:
            with open("/etc/machine-id", "r") as f:
                return f.read().strip()
        except Exception:
            logger.warning("Using fallback machine ID method")
            return str(hash(str(Path.home())))

    def setup_new_credentials(self, master_password: str) -> bool:
        """Initialize the encryption system with a master password."""
        try:
            # Generate a new salt
            salt = os.urandom(16)

            # Generate the encryption key
            key = self._derive_key(master_password, salt)

            # Create a new Fernet instance
            self._fernet = Fernet(key)

            # Store the salt securely
            salt_path = self.config_dir / ".salt"
            with open(salt_path, "wb") as f:
                f.write(salt)

            # Store an identifier in the system keyring
            machine_id = self._get_machine_id()
            keyring.set_password(self.app_name, self.key_identifier, machine_id)

            # Create a verification file with a known string
            verification_content = {
                "created_at": datetime.now().isoformat(),
                "verification_string": "VERIFICATION_SUCCESSFUL",
                "app_name": self.app_name
            }

            # Convert to JSON and encrypt
            json_content = json.dumps(verification_content)
            encrypted_content = self.encrypt_value(json_content)

            # Save the encrypted verification file
            verification_path = self.config_dir / ".verify"
            with open(verification_path, "w") as f:
                f.write(encrypted_content)

            # Create empty credentials file
            creds_path = self.config_dir / "credentials.yaml"
            self.save_credentials([], creds_path)

            self.is_initialized = True
            return True

        except Exception as e:
            logger.error(f"Failed to setup credentials: {e}")
            return False

    def reset_credentials(self, new_master_password: str) -> bool:
        """Reset the credential store with a new master password."""
        try:
            # Clear existing credential files but save their paths
            salt_path = self.config_dir / ".salt"
            verify_path = self.config_dir / ".verify"
            creds_path = self.config_dir / "credentials.yaml"

            # Back up current configuration
            backup_dir = self.config_dir / "backup"
            backup_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Back up salt and verification files
            if salt_path.exists():
                shutil.copy(salt_path, backup_dir / f".salt.{timestamp}")

            if verify_path.exists():
                shutil.copy(verify_path, backup_dir / f".verify.{timestamp}")

            if creds_path.exists():
                shutil.copy(creds_path, backup_dir / f"credentials.yaml.{timestamp}")

            # Remove current files
            if salt_path.exists():
                salt_path.unlink()

            if verify_path.exists():
                verify_path.unlink()

            # Reset Fernet instance
            self._fernet = None
            self.is_initialized = False

            # Create new credential store with new password
            return self.setup_new_credentials(new_master_password)

        except Exception as e:
            logger.error(f"Failed to reset credentials: {e}")
            return False
    def unlock(self, master_password: str) -> bool:
        """Unlock the credential manager with the master password."""
        try:
            # Verify the keyring identifier
            stored_id = keyring.get_password(self.app_name, self.key_identifier)
            if stored_id != self._get_machine_id():
                logger.warning("Machine ID mismatch - possible security breach")
                return False

            # Load the salt
            salt_path = self.config_dir / ".salt"
            if not salt_path.exists():
                logger.error("Encryption not initialized")
                return False

            with open(salt_path, "rb") as f:
                salt = f.read()

            # Recreate the encryption key
            key = self._derive_key(master_password, salt)
            temp_fernet = Fernet(key)  # Use a temporary Fernet instance for testing

            # Load the verification file
            verification_path = self.config_dir / ".verify"
            if not verification_path.exists():
                logger.error("Verification file not found")
                return False

            with open(verification_path, "r") as f:
                encrypted_content = f.read().strip()

            # Try to decrypt the verification file
            try:
                # Decrypt using the temporary Fernet instance
                decrypted_bytes = base64.b64decode(encrypted_content)
                decrypted_content = temp_fernet.decrypt(decrypted_bytes).decode('utf-8')

                # Parse the JSON content
                verification_data = json.loads(decrypted_content)

                # Check the verification string
                if verification_data.get("verification_string") == "VERIFICATION_SUCCESSFUL":
                    # Password is correct, set the Fernet instance
                    self._fernet = temp_fernet
                    return True
                else:
                    logger.warning("Verification string mismatch")
                    return False

            except Exception as e:
                logger.error(f"Verification failed - likely incorrect password: {e}")
                return False

        except Exception as e:
            logger.error(f"Failed to unlock credential manager: {e}")
            return False

    def encrypt_value(self, value: str) -> str:
        """Encrypt a single value and return as base64 string."""
        if not self._fernet:
            raise RuntimeError("Credential manager not unlocked")

        encrypted = self._fernet.encrypt(value.encode())
        return base64.b64encode(encrypted).decode('utf-8')

    def decrypt_value(self, encrypted_value: str) -> str:
        """Decrypt a base64 encoded encrypted value."""
        if not self._fernet:
            raise RuntimeError("Credential manager not unlocked")

        encrypted_bytes = base64.b64decode(encrypted_value)
        decrypted = self._fernet.decrypt(encrypted_bytes)
        return decrypted.decode('utf-8')

    # helpers/credslib.py

    def save_credentials(self, creds_list: list, filepath: Path) -> None:
        """Save credentials list to YAML file."""
        if not self._fernet:
            raise RuntimeError("Credential manager not unlocked")

        encrypted_creds = []
        for cred in creds_list:
            encrypted_cred = cred.copy()
            if 'password' in encrypted_cred and encrypted_cred['password']:
                # Directly encrypt the password without additional base64 encoding
                encrypted = self._fernet.encrypt(encrypted_cred['password'].encode())
                encrypted_cred['password'] = encrypted.decode('utf-8')
            encrypted_creds.append(encrypted_cred)

        with open(filepath, 'w') as f:
            yaml.safe_dump({
                'last_modified': datetime.now().isoformat(),
                'credentials': encrypted_creds
            }, f)

    def load_credentials(self, filepath: Path) -> list:
        """Load and decrypt credentials from YAML file."""
        if not self._fernet:
            raise RuntimeError("Credential manager not unlocked")

        if not filepath.exists():
            return []

        with open(filepath) as f:
            data = yaml.safe_load(f) or {'credentials': []}

        decrypted_creds = []
        for cred in data.get('credentials', []):
            decrypted_cred = cred.copy()
            if 'password' in decrypted_cred and decrypted_cred['password']:
                try:
                    # Directly decrypt the password without additional base64 decoding
                    decrypted = self._fernet.decrypt(decrypted_cred['password'].encode())
                    decrypted_cred['password'] = decrypted.decode('utf-8')
                except Exception as e:
                    logger.error(f"Failed to decrypt credential: {e}")
                    raise
            decrypted_creds.append(decrypted_cred)

        return decrypted_creds