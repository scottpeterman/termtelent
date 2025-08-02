# TerminalTelemetry Enterprise

## The Problem

**30 years ago, I started with Telnet, Kermit, Trumpet Winsock, Novell and TFTP.**

Since then, I've watched vendors fragment network management:
- SecureCRT for terminal access
- High end, high expensive CMDBs and documentation tools
- Lansweeper for asset discovery
- SolarWinds for monitoring and telemetry
- Kiwi CatTools for configuration management

**Five tools. Five licenses. Five proprietary black boxes.**

None talking to each other. None showing you how they actually work. Closed databases and proprietary file formats.

**I got tired of the vendor tax on basic network operations.**

## The Solution

**What should have existed all along:**

- **Integrated SSH terminals** with live device telemetry
- **SNMP discovery** with completely open fingerprint rules  
- **Real-time monitoring** with exportable data
- **Configuration management** with diff tracking
- **Network topology** with professional diagram export

**One platform. Zero licensing. Complete transparency.**


[![GPLv3 License](https://img.shields.io/badge/license-GPLv3-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://python.org)
[![Version 0.1.0](https://img.shields.io/badge/version-0.1.0-green.svg)](https://github.com/scottpeterman/termtelent)
[![Cross Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)](https://github.com/scottpeterman/termtelent)

![TermTel Landing](screenshots/landing/slides1.gif)

---

## Quick Start

**Note: PyPI package coming soon - currently install from source**

```bash
# Clone repository
git clone https://github.com/scottpeterman/termtelent.git
cd termtelent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Launch application
python -m launcher.launch
```

**First Launch:**
1. Themes auto-bootstrap on startup
2. Create connections via File → Sessions or Quick Connect  
3. Open monitoring via Tools → Telemetry Dashboard
4. Customize with 20+ themes via View → Themes

---

## Platform Architecture

The platform consists of two peer components that integrate through shared credentials and data formats:

**SNMP Network Discovery → Real-Time SSH Monitoring → Enterprise CMDB Management**

### SNMP Network Scanner Suite
**Comprehensive network discovery with open device fingerprinting**

- **TCP pre-filtering** for 3-5x faster scanning performance
- **SNMPv3/v2c fallback** with automatic community detection
- **Open fingerprint rules** - completely transparent device detection (no vendor lock-in)
- **Domain intelligence** - automatic hostname normalization and cleanup
- **Concurrent scanning** with intelligent rate limiting and error resilience
- **GUI fingerprint editor** for custom device rule development

[Network Scanner Suite Guide](README_Scanner.md)

### TerminalTelemetry Core Platform
**Multi-tab SSH terminal emulator with integrated real-time monitoring**

- **Multi-tab SSH terminals** with xterm.js backend and theme integration
- **Real-time telemetry widgets** - CPU/memory, neighbors, ARP tables, routing, logs
- **200+ TextFSM templates** for multi-vendor data parsing and normalization
- **Advanced theme system** with 20+ retro-inspired themes (cyberpunk, CRT, etc.)
- **Encrypted credential storage** with enterprise-grade security (AES-256)
- **Platform auto-detection** for optimal data collection per device type

[Real-Time Telemetry Guide](README_Telemetry.md) | [Theme Management](README_THeme_mgmt.md)

### Network Mapping Suite
**Professional topology visualization and documentation**

- Interactive topology viewer with zoom/pan/search
- Professional diagram export (DrawIO, GraphML, Visio)
- Multi-network merging for campus-wide maps
- Vendor-specific icons and automated layouts
- Publication-ready documentation generation

[Network Mapping Guide](README_Maps.md)

### RapidCMDB Enterprise Platform
**Web-based configuration management and asset tracking system**

- **Enterprise-scale device management** (20,000+ devices tested in production)
- **Automated configuration collection** with change tracking and diff visualization
- **Secure credential pipeline** with encrypted storage and environment variable injection
- **Multi-vendor NAPALM integration** for consistent device interaction
- **Web-based dashboard** with real-time SocketIO updates and search capabilities
- **External integrations** - NetBox and LogicMonitor synchronization

**Note:** RapidCMDB operates as an independent Flask application with shared credential integration

[RapidCMDB Enterprise Guide](README_RapidCMDB.md) | [Pipeline Architecture](README_Pipeline.md)

---

## Screenshots

### Dark Theme Interface
![Main Interface](screenshots/slides1.gif)

### Light Theme Support
![Light Theme](screenshots/light/slides1.gif)

---

## Unified Workflow

![Data Flow Architecture](diagrams/arch_flow.mermaid)

All components share:
- **Unified credential store** - secure AES-256 encrypted credential management
- **Universal theming** - consistent retro-inspired UI across all platforms
- **Open fingerprint rules** - community-driven device detection with full transparency
- **Standard data formats** - JSON/CSV export and seamless integration between components
- **Cross-platform deployment** - Windows, macOS, Linux support with identical functionality

[Platform Integration Overview](README_Pipeline.md)

---

## Key Advantages

### Open & Transparent
- No vendor lock-in - all detection rules visible and editable
- Community-driven shared fingerprint database
- No licensing fees - deploy anywhere without restrictions
- Full transparency - see exactly what commands are executed

### Enterprise Security
- AES-256 encrypted credential storage
- Real-world reliability - handles network timeouts and edge cases  
- Performance optimized - TCP pre-filtering and async processing
- Cross-platform - Windows, macOS, Linux support

### Modern Interface
- Tech aesthetic - 20+ professionally designed themes
- Responsive interface - threaded operations keep UI smooth
- Contextual tools - right-click menus and integrated workflows
- Extensible design - modular architecture for custom development

---

## Documentation

### Core Platform Guides
- [Network Scanner Suite](README_Scanner.md) - SNMP discovery with open fingerprinting
- [Real-Time Telemetry](README_Telemetry.md) - Live device monitoring and visualization
- [Network Mapping Suite](README_Maps.md) - Topology visualization and professional diagrams
- [RapidCMDB Enterprise](README_RapidCMDB.md) - Web-based device management and analytics

### Advanced Topics
- [Theme Management System](README_THeme_mgmt.md) - Advanced theming and customization
- [Custom Widget Development](README_widgets.md) - Extending the platform with custom widgets
- [Pipeline Architecture](README_Pipeline.md) - Data flow and processing pipelines

### Architecture Diagrams
- [High-Level Architecture](diagrams/arch_high_level.mermaid) - System overview
- [Component Architecture](diagrams/arch_components.mermaid) - Detailed component relationships
- [Data Flow](diagrams/arch_flow.mermaid) - Information processing pipeline
- [Architecture Summary](diagrams/arch_summary.mermaid) - Consolidated view

---

## Installation & Setup

### System Requirements
- **Python:** 3.12 (tested version)
- **OS:** Windows, macOS, Linux  
- **Memory:** 4GB RAM (8GB+ recommended for large networks)
- **Network:** SSH (22/TCP) and SNMP (161/UDP) access to target devices
- **Dependencies:** PyQt6, netmiko, pysnmp, flask, cryptography

### Installation from Source
**Note: PyPI package coming soon - currently install from source**

```bash
# Clone the repository
git clone https://github.com/scottpeterman/termtelent.git
cd termtelent

# Create and activate virtual environment
python -m venv .venv

# On Windows:
.venv\Scripts\activate

# On macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Launch TerminalTelemetry Enterprise
python -m launcher.launch
```

### First-Time Setup
1. Application launches - themes auto-bootstrap on first run
2. Configure credentials via File → Credential Manager
3. Import or create sessions via File → Session Editor
4. Start monitoring via Tools → Telemetry Dashboard
5. Access RapidCMDB web interface (starts automatically)

---

## Project Structure

```
termtelent/
├── termtel/                    # Main application package
│   ├── tte.py                 # Application entry point
│   ├── widgets/               # Core UI components
│   ├── termtelwidgets/        # Telemetry widgets
│   ├── themes/                # Theme system
│   └── static/                # Web assets
├── rapidcmdb/                 # Enterprise CMDB platform
│   ├── app.py                 # Flask web application
│   ├── blueprints/            # Web interface modules
│   └── templates/             # HTML templates
├── launcher/                  # Application launcher
├── sessions/                  # Session configurations
├── screenshots/               # Demo images
└── diagrams/                  # Architecture diagrams
```

---

## Contributing

We welcome contributions! Ways to help:

- **Bug Reports:** Use GitHub Issues with device platform details
- **Template Contributions:** Use built-in template editor to create/fix parsing
- **Fingerprint Rules:** Submit vendor detection improvements  
- **Documentation:** Help improve guides and examples

### Development Workflow
```bash
# Clone and setup development environment
git clone https://github.com/scottpeterman/termtelent.git
cd termtelent
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run tests (when available)
python -m pytest tests/

# Launch for development
python -m launcher.launch
```

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

---

## Enterprise Proven

- **20,000+ devices** tested in single RapidCMDB deployment
- **Sub-second response times** for standard operations
- **Multi-vendor support** across Cisco, Arista, Juniper, HP, Fortinet
- **Cross-platform deployment** on Windows, Linux, macOS

---

## Security & Compliance

- **Enterprise-grade encryption** (AES-256 + PBKDF2)
- **No data exfiltration** - purely SSH client connections
- **Audit trail** - comprehensive logging of all operations
- **Zero infrastructure** - no servers or agents required

---

## Business Value

- **No licensing fees** - deploy to unlimited devices
- **Instant deployment** - pip install and run anywhere  
- **Reduce vendor lock-in** - works with any SSH-accessible device
- **Engineer productivity** - familiar SSH workflow with modern tools

---

## License & Technology

**License:** GPLv3 - Free for personal and commercial use

**Built With:**
- PyQt6 and Python ecosystem
- xterm.js for terminal functionality  
- netmiko and TextFSM for network automation
- Flask for web-based components
- Modern responsive design principles

---

## Support & Community

- **[GitHub Issues](https://github.com/scottpeterman/termtelent/issues)** - Bug reports and feature requests
- **Documentation** - Comprehensive guides and API reference
- **Community** - Template library and fingerprint rule sharing

---

> *"The most powerful network management platform is the one that gives you complete control and transparency over your infrastructure."*

**TerminalTelemetry Enterprise** - Where network discovery, monitoring, and management converge in a unified, open, and powerful ecosystem.