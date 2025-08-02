#!/usr/bin/env python3
"""
Theme Bootstrap System for TerminalTelemetry
Automatically populates user themes folder from packaged defaults
"""

import os
import json
import shutil
from pathlib import Path
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class ThemeBootstrap:
    """
    Manages automatic theme deployment from package to user directory
    """

    def __init__(self, resource_manager, user_themes_dir: Path):
        """
        Initialize theme bootstrap

        Args:
            resource_manager: Your existing PackageResourceManager instance
            user_themes_dir: Path to user's themes directory (e.g., ./themes)
        """
        self.resource_manager = resource_manager
        self.user_themes_dir = Path(user_themes_dir)
        self.user_themes_dir.mkdir(exist_ok=True)

    def bootstrap_themes(self, force_update: bool = False) -> Dict[str, bool]:
        """
        Bootstrap themes from package to user directory

        Args:
            force_update: If True, overwrite existing themes

        Returns:
            Dict mapping theme names to success status
        """
        results = {}

        # Check if bootstrap has already been completed
        if not force_update and self._is_bootstrap_complete():
            logger.info("Theme bootstrap already completed, skipping")
            return results

        # Get list of packaged themes
        packaged_themes = self._get_packaged_themes()

        if not packaged_themes:
            logger.warning("No packaged themes found")
            return results

        logger.info(f"Bootstrapping {len(packaged_themes)} themes...")

        # Copy each theme
        for theme_name in packaged_themes:
            try:
                success = self._copy_theme(theme_name, force_update)
                results[theme_name] = success

                if success:
                    logger.info(f" Bootstrapped theme: {theme_name}")
                else:
                    logger.warning(f" Failed to bootstrap theme: {theme_name}")

            except Exception as e:
                logger.error(f"Error bootstrapping theme {theme_name}: {e}")
                results[theme_name] = False

        logger.info(f"Theme bootstrap complete. {sum(results.values())}/{len(results)} successful")

        # Mark bootstrap as complete
        self._mark_bootstrap_complete()

        return results

    def _is_bootstrap_complete(self) -> bool:
        """Check if theme bootstrap has been completed before"""
        bootstrap_marker = self.user_themes_dir / '.bootstrap_complete'
        return bootstrap_marker.exists()

    def _mark_bootstrap_complete(self):
        """Mark theme bootstrap as complete"""
        try:
            bootstrap_marker = self.user_themes_dir / '.bootstrap_complete'
            with open(bootstrap_marker, 'w') as f:
                import datetime
                f.write(f"Bootstrap completed: {datetime.datetime.now().isoformat()}\n")
                f.write(f"Version: 1.0\n")
            logger.debug("Bootstrap marked as complete")
        except Exception as e:
            logger.error(f"Failed to mark bootstrap complete: {e}")

    def _has_user_themes(self) -> bool:
        """Check if user already has themes"""
        if not self.user_themes_dir.exists():
            return False

        # Count .json theme files
        theme_files = list(self.user_themes_dir.glob("*.json"))
        return len(theme_files) > 2  # More than just the 2 basic built-in themes

    def _get_packaged_themes(self) -> List[str]:
        """Get list of packaged theme files"""
        try:
            # Use your resource manager to list themes
            themes = self.resource_manager._list_resources('themes', '.json')

            # Filter out any non-theme files if needed
            theme_files = [t for t in themes if t.endswith('.json')]

            return theme_files

        except Exception as e:
            logger.error(f"Failed to list packaged themes: {e}")
            return []

    def _copy_theme(self, theme_filename: str, overwrite: bool = False) -> bool:
        """
        Copy a single theme from package to user directory

        Args:
            theme_filename: Name of theme file (e.g., 'cyberpunk.json')
            overwrite: Whether to overwrite existing files

        Returns:
            True if successful
        """
        try:
            user_theme_path = self.user_themes_dir / theme_filename

            # Skip if exists and not overwriting
            if user_theme_path.exists() and not overwrite:
                logger.debug(f"Theme {theme_filename} already exists, skipping")
                return True

            # Get theme content from package
            theme_content = self.resource_manager._get_resource_content('themes', theme_filename)

            if not theme_content:
                logger.error(f"Could not read packaged theme: {theme_filename}")
                return False

            # Validate it's valid JSON
            try:
                json.loads(theme_content)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in theme {theme_filename}: {e}")
                return False

            # Write to user directory
            with open(user_theme_path, 'w', encoding='utf-8') as f:
                f.write(theme_content)

            logger.debug(f"Copied theme: {theme_filename}")
            return True

        except Exception as e:
            logger.error(f"Failed to copy theme {theme_filename}: {e}")
            return False

    def force_rebootstrap(self) -> Dict[str, bool]:
        """
        Force re-bootstrap themes (for admin/debug purposes)
        This will overwrite existing themes!
        """
        logger.warning("Force re-bootstrap requested - this will overwrite user themes!")

        # Remove bootstrap marker
        bootstrap_marker = self.user_themes_dir / '.bootstrap_complete'
        if bootstrap_marker.exists():
            bootstrap_marker.unlink()

        # Bootstrap with force update
        return self.bootstrap_themes(force_update=True)

    def get_available_themes(self) -> List[str]:
        """Get list of available themes (user + packaged)"""
        themes = set()

        # Add user themes
        if self.user_themes_dir.exists():
            for theme_file in self.user_themes_dir.glob("*.json"):
                themes.add(theme_file.stem)

        # Add packaged themes (as fallback)
        packaged = self._get_packaged_themes()
        for theme_file in packaged:
            themes.add(Path(theme_file).stem)

        return sorted(list(themes))

    def get_theme_content(self, theme_name: str) -> Optional[str]:
        """
        Get theme content, preferring user version over packaged

        Args:
            theme_name: Theme name without .json extension

        Returns:
            Theme JSON content or None
        """
        theme_filename = f"{theme_name}.json"

        # Try user directory first
        user_theme_path = self.user_themes_dir / theme_filename
        if user_theme_path.exists():
            try:
                with open(user_theme_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Failed to read user theme {theme_name}: {e}")

        # Fallback to packaged theme
        return self.resource_manager._get_resource_content('themes', theme_filename)


# Enhanced resource manager methods
def enhance_resource_manager(resource_manager_class):
    """Add theme-specific methods to your resource manager"""

    def get_theme_path(self, theme_name: str) -> Optional[str]:
        """Get path to a theme file"""
        return self._get_resource_path('themes', f"{theme_name}.json")

    def get_theme_content(self, theme_name: str) -> Optional[str]:
        """Get content of a theme file"""
        return self._get_resource_content('themes', f"{theme_name}.json")

    def list_themes(self) -> List[str]:
        """List all available theme files"""
        return self._list_resources('themes', '.json')

    # Add methods to the class
    resource_manager_class.get_theme_path = get_theme_path
    resource_manager_class.get_theme_content = get_theme_content
    resource_manager_class.list_themes = list_themes

    return resource_manager_class


# Integration with your existing code
def initialize_themes(resource_manager, themes_dir: Path) -> ThemeBootstrap:
    """
    Initialize theme system with auto-bootstrap

    Args:
        resource_manager: Your PackageResourceManager instance
        themes_dir: Path to themes directory

    Returns:
        ThemeBootstrap instance
    """
    bootstrap = ThemeBootstrap(resource_manager, themes_dir)

    # Auto-bootstrap on first run
    try:
        results = bootstrap.bootstrap_themes()

        if results:
            successful = sum(results.values())
            total = len(results)
            logger.info(f"Theme initialization: {successful}/{total} themes ready")

    except Exception as e:
        logger.error(f"Theme bootstrap failed: {e}")

    return bootstrap


# Usage example for your termtel.py
def setup_themes_in_main():
    """
    Example of how to integrate this into your main application
    """
    from termtel.helpers.resource_manager import resource_manager

    # Enhance your resource manager with theme methods
    enhance_resource_manager(type(resource_manager))

    # Set up themes directory
    themes_dir = Path('./themes')

    # Initialize with auto-bootstrap
    theme_bootstrap = initialize_themes(resource_manager, themes_dir)

    # Now your themes folder will be populated automatically
    available_themes = theme_bootstrap.get_available_themes()
    logger.info(f"Available themes: {available_themes}")

    return theme_bootstrap