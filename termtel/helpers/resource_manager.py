"""
Resource Manager for accessing package resources in both development and installed environments
Updated to remove pkg_resources dependency and handle correct dev file structure
"""

import os
import sys
from pathlib import Path
from typing import Optional, List
import importlib.resources
from importlib import resources


class PackageResourceManager:
    """
    Manages access to package resources (templates, configs) in both dev and installed environments
    """

    def __init__(self, package_name: str = "termtel"):
        self.package_name = package_name
        self._resource_cache = {}
        self._is_dev_mode = self._detect_development_mode()

        if self._is_dev_mode:
            print(f" Running in development mode")
        else:
            print(f" Running in package mode")

    def get_template_path(self, template_name: str) -> Optional[str]:
        """
        Get path to a TextFSM template file

        Args:
            template_name: Name of template file (e.g., 'cisco_ios_show_version.textfsm')

        Returns:
            Full path to template file or None if not found
        """
        return self._get_resource_path('templates/textfsm', template_name)

    def get_template_content(self, template_name: str) -> Optional[str]:
        """
        Get content of a TextFSM template file

        Args:
            template_name: Name of template file

        Returns:
            Template content as string or None if not found
        """
        return self._get_resource_content('templates.textfsm', template_name)

    def list_templates(self) -> List[str]:
        """
        List all available TextFSM templates

        Returns:
            List of template filenames
        """
        return self._list_resources('templates.textfsm', '.textfsm')

    def get_config_path(self, config_name: str) -> Optional[str]:
        """
        Get path to a config file

        Args:
            config_name: Name of config file (e.g., 'platforms.json')

        Returns:
            Full path to config file or None if not found
        """
        # In dev mode, try both config/ and config/platforms/ directories
        if self._is_dev_mode:
            dev_paths = [
                f'config/platforms/{config_name}',  # Your actual dev structure
                f'config/{config_name}',            # Packaged structure
                f'termtel/config/platforms/{config_name}',  # Absolute dev path
                f'termtel/config/{config_name}'     # Absolute packaged path
            ]

            for dev_path in dev_paths:
                result = self._get_resource_path_dev_mode(dev_path)
                if result:
                    return result

        # Try package resources for installed package
        # First try config/platforms/ then config/
        for config_path in ['config/platforms', 'config']:
            result = self._get_resource_path(config_path, config_name)
            if result:
                return result

        return None

    def get_config_content(self, config_name: str) -> Optional[str]:
        """
        Get content of a config file

        Args:
            config_name: Name of config file

        Returns:
            Config content as string or None if not found
        """
        # First try to get the path and read from file (works in both modes)
        config_path = self.get_config_path(config_name)
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                print(f"Error reading config file {config_path}: {e}")

        # Fallback to package resources
        return self._get_resource_content('config', config_name)

    def get_platforms_config(self) -> Optional[str]:
        """Get platforms.json configuration content"""
        return self.get_config_content('platforms.json')

    def _detect_development_mode(self) -> bool:
        """
        Detect if we're running in development mode
        """
        try:
            current_file = Path(__file__)

            # Look for development indicators in the project structure
            for parent in current_file.parents:
                # Check for typical development structure
                if (parent / 'termtel' / 'config' / 'platforms' / 'platforms.json').exists():
                    return True
                if (parent / 'setup.py').exists() or (parent / 'pyproject.toml').exists():
                    return True
                if (parent / '.git').exists():
                    return True

        except Exception as e:
            print(f"Error detecting development mode: {e}")

        return False

    def _get_resource_path_dev_mode(self, resource_path: str) -> Optional[str]:
        """
        Get resource path in development mode

        Args:
            resource_path: Path like 'config/platforms/platforms.json'
        """
        try:
            current_file = Path(__file__)

            # Look up the directory tree for the resource
            for parent in current_file.parents:
                # Try direct path from project root
                potential_path = parent / 'termtel' / resource_path
                if potential_path.exists():
                    return str(potential_path)

                # Try without termtel prefix
                potential_path = parent / resource_path
                if potential_path.exists():
                    return str(potential_path)

        except Exception as e:
            print(f"Error finding dev resource {resource_path}: {e}")

        return None

    def _get_resource_path(self, resource_dir: str, filename: str) -> Optional[str]:
        """
        Get path to a resource file, handling both dev and installed environments
        """
        cache_key = f"{resource_dir}/{filename}"
        if cache_key in self._resource_cache:
            return self._resource_cache[cache_key]

        # Method 1: Development environment
        if self._is_dev_mode:
            dev_path = self._get_development_path(resource_dir, filename)
            if dev_path and os.path.exists(dev_path):
                self._resource_cache[cache_key] = dev_path
                return dev_path

        # Method 2: Package resources (installed environment)
        try:
            # Use importlib.resources for Python 3.9+
            if sys.version_info >= (3, 9):
                package_path = f"{self.package_name}.{resource_dir.replace('/', '.')}"
                try:
                    files = importlib.resources.files(package_path)
                    file_ref = files / filename
                    if file_ref.is_file():
                        # For newer Python, we can get a path-like object
                        with importlib.resources.as_file(file_ref) as path:
                            path_str = str(path)
                            self._resource_cache[cache_key] = path_str
                            return path_str
                except Exception as e:
                    print(f"importlib.resources failed for {cache_key}: {e}")
            else:
                # Fallback for Python 3.8
                package_path = f"{self.package_name}.{resource_dir.replace('/', '.')}"
                try:
                    with importlib.resources.path(package_path, filename) as path:
                        if path.exists():
                            path_str = str(path)
                            self._resource_cache[cache_key] = path_str
                            return path_str
                except Exception as e:
                    print(f"importlib.resources (3.8) failed for {cache_key}: {e}")

        except Exception as e:
            print(f"Package resource access failed for {cache_key}: {e}")

        # Method 3: Relative to this module (final fallback)
        try:
            module_dir = Path(__file__).parent.parent
            resource_path = module_dir / resource_dir / filename
            if resource_path.exists():
                path_str = str(resource_path)
                self._resource_cache[cache_key] = path_str
                return path_str
        except Exception as e:
            print(f"Relative path access failed for {cache_key}: {e}")

        print(f" Resource not found: {cache_key}")
        return None

    def _get_resource_content(self, resource_package: str, filename: str) -> Optional[str]:
        """
        Get content of a resource file
        """
        try:
            # Try package resources first (for installed packages)
            package_path = f"{self.package_name}.{resource_package}"

            if sys.version_info >= (3, 9):
                try:
                    files = importlib.resources.files(package_path)
                    file_ref = files / filename
                    if file_ref.is_file():
                        return file_ref.read_text(encoding='utf-8')
                except Exception as e:
                    print(f"importlib.resources content read failed: {e}")

            # Fallback for older Python
            try:
                content = importlib.resources.read_text(package_path, filename, encoding='utf-8')
                return content
            except Exception as e:
                print(f"importlib.resources.read_text failed: {e}")

        except Exception as e:
            print(f"Package resource content access failed: {e}")

        # Fallback to file path
        file_path = self._get_resource_path(resource_package.replace('.', '/'), filename)
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                print(f"File read failed for {file_path}: {e}")

        return None

    def _list_resources(self, resource_package: str, extension: str = None) -> List[str]:
        """
        List all files in a resource package
        """
        files = []

        # Try package resources first
        try:
            package_path = f"{self.package_name}.{resource_package}"

            if sys.version_info >= (3, 9):
                try:
                    resource_files = importlib.resources.files(package_path)
                    for item in resource_files.iterdir():
                        if item.is_file():
                            if not extension or item.name.endswith(extension):
                                files.append(item.name)
                except Exception as e:
                    print(f"importlib.resources listing failed: {e}")
            else:
                # For Python 3.8, try a different approach
                try:
                    with importlib.resources.path(package_path, '.') as package_dir:
                        if package_dir.is_dir():
                            for item in package_dir.iterdir():
                                if item.is_file():
                                    if not extension or item.name.endswith(extension):
                                        files.append(item.name)
                except Exception as e:
                    print(f"importlib.resources listing (3.8) failed: {e}")

        except Exception as e:
            print(f"Package resource listing failed: {e}")

        # Fallback to development environment
        if not files and self._is_dev_mode:
            dev_dir = self._get_development_dir(resource_package.replace('.', '/'))
            if dev_dir and os.path.exists(dev_dir):
                try:
                    for item in os.listdir(dev_dir):
                        item_path = os.path.join(dev_dir, item)
                        if os.path.isfile(item_path):
                            if not extension or item.endswith(extension):
                                files.append(item)
                except Exception as e:
                    print(f"Development directory listing failed: {e}")

        return sorted(files)

    def _get_development_path(self, resource_dir: str, filename: str) -> Optional[str]:
        """
        Get path in development environment
        """
        try:
            current_file = Path(__file__)

            # Look up the directory tree for project root
            for parent in current_file.parents:
                # Method 1: Try termtel/resource_dir/filename
                potential_path = parent / 'termtel' / resource_dir / filename
                if potential_path.exists():
                    return str(potential_path)

                # Method 2: Try resource_dir/filename (without termtel prefix)
                potential_path = parent / resource_dir / filename
                if potential_path.exists():
                    return str(potential_path)

                # Method 3: For config files, try the platforms subdirectory
                if resource_dir == 'config':
                    potential_path = parent / 'termtel' / 'config' / 'platforms' / filename
                    if potential_path.exists():
                        return str(potential_path)

        except Exception as e:
            print(f"Development path search failed: {e}")

        return None

    def _get_development_dir(self, resource_dir: str) -> Optional[str]:
        """
        Get directory path in development environment
        """
        try:
            current_file = Path(__file__)
            for parent in current_file.parents:
                # Try with termtel prefix
                potential_dir = parent / 'termtel' / resource_dir
                if potential_dir.exists() and potential_dir.is_dir():
                    return str(potential_dir)

                # Try without termtel prefix
                potential_dir = parent / resource_dir
                if potential_dir.exists() and potential_dir.is_dir():
                    return str(potential_dir)
        except Exception as e:
            print(f"Development directory search failed: {e}")
        return None


# Global instance
resource_manager = PackageResourceManager()


def get_template_path(template_name: str) -> Optional[str]:
    """Convenience function to get template path"""
    return resource_manager.get_template_path(template_name)


def get_template_content(template_name: str) -> Optional[str]:
    """Convenience function to get template content"""
    return resource_manager.get_template_content(template_name)


def get_platforms_config() -> Optional[str]:
    """Convenience function to get platforms configuration"""
    return resource_manager.get_platforms_config()


def list_available_templates() -> List[str]:
    """Convenience function to list available templates"""
    return resource_manager.list_templates()


# Remove any pkg_resources usage that might be in config.py
def patch_config_module():
    """Remove pkg_resources dependency warnings"""
    try:
        import termtel.config
        # If config.py is using pkg_resources, we should update it
        # But for now, just suppress the warning
        import warnings
        warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")
    except ImportError:
        pass


# Call the patch on import
patch_config_module()