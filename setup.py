from setuptools import setup, find_packages
import os

# Read the content of README.md
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Read requirements from requirements.txt
with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = fh.read().splitlines()

setup(
    name="TerminalTelemetry",
    version="1.0.0",  # Bump version for major release with RapidCMDB
    author="Scott Peterman",
    author_email="scottpeterman@gmail.com",
    description="A PyQt6 terminal emulator with SSH, telemetry, and network discovery capabilities",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/scottpeterman/termtelent",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",  # Updated since you're going fully open source
        "Operating System :: OS Independent",
        "Environment :: X11 Applications :: Qt",
        "Topic :: System :: Networking :: Monitoring",
        "Topic :: System :: System Shells",
        "Topic :: Terminals :: Terminal Emulators/X Terminals",
        "Topic :: System :: Systems Administration",
        "Topic :: Database :: Database Engines/Servers",
        "Framework :: Flask",
        "Development Status :: 4 - Beta",
        "Intended Audience :: System Administrators",
        "Intended Audience :: Information Technology",
    ],
    python_requires=">=3.12",
    install_requires=requirements,

    # Critical: This ensures package data is included
    include_package_data=True,
    zip_safe=False,  # Important for accessing package data files

    # Updated package_data to include all necessary resources
    package_data={
        "termtel": [
            # Static web assets
            "static/**/*",
            "static/css/*.css",
            "static/js/*.js",
            "static/images/*",
            "static/*.html",
            "static/*.wasm",
            "static/*.sav",
            # TextFSM templates - CRITICAL for your use case
            "templates/textfsm/*.textfsm",
            "templates/**/*",
            # Platform configuration - CRITICAL
            # Handle both development and packaged structures
            "config/*.json",
            "config/platforms/*.json",
            "config/platforms/platforms.json",
            # Frontend assets (if termtelng is still used)
            "termtelng/frontend/**/*",
            # Icons and logos
            "icon.ico",
            "logo.svg",
            "logo.py",
            # Database files
            "*.db",
            # Any additional resource files
            "*.html",
            "themes/*.json",
        ],
        # RapidCMDB package data
        "rapidcmdb": [
            # Web templates
            "templates/**/*",
            "templates/*.html",
            # Static assets
            "static/**/*",
            "static/css/*.css",
            "static/js/*.js",
            "static/images/*",
            # Configuration files
            "config/*.yaml",
            "config/*.json",
            # Database files
            "*.sql",
            "*.db",
            "*.yaml",
            # Blueprint files
            "blueprints/*.py",
        ],
        # If you have package data in termtelwidgets subdirectory
        "termtel.termtelwidgets": [
            "*.py",
        ],
        # Include helper modules
        "termtel.helpers": [
            "*.py",
        ],
        # Include config as a separate package to ensure it's found
        "termtel.config": [
            "*.json",
            "platforms/*.json",
        ],
        # Global themes and sessions
        "": [
            "themes/*.json",
            "sessions/*.yaml",
        ],
    },

    entry_points={
        "console_scripts": [
            # Existing terminal commands
            "termtel-con=termtel.tte:main",
            "termtel=termtel.tte:main",
            # New RapidCMDB commands
            "termtel-cmdb=rapidcmdb.app:main",
            "termtel-full=launch:main",
        ],
        "gui_scripts": [
            # GUI version (Windows will launch without console)
            "termtel-gui=termtel.tte:main",
        ],
    },

    # Optional dependencies for different use cases
    extras_require={
        "dev": [
            "pytest>=6.0",
            "black>=21.0",
            "flake8>=3.8",
            "mypy>=0.800",
        ],
        "postgresql": [
            "psycopg2-binary>=2.8",
        ],
        "full": [
            "psycopg2-binary>=2.8",
        ],
    },

    # Additional metadata for better discoverability
    keywords="terminal ssh telemetry network monitoring pyqt6 netmiko textfsm cmdb discovery flask",
    project_urls={
        "Source": "https://github.com/scottpeterman/terminaltelemetry",
        "Bug Reports": "https://github.com/scottpeterman/terminaltelemetry/issues",
        "Documentation": "https://github.com/scottpeterman/terminaltelemetry/blob/main/README.md",
    },
)