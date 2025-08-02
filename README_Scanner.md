# SNMP Network Scanner Suite

A comprehensive, open-source network discovery solution with advanced device fingerprinting, intelligent domain handling, and seamless CMDB integration.

![Scanner Suite Overview](docs/images/scanner-suite-overview.png)
*Complete scanning workflow from discovery to CMDB import*

## Overview

This scanner suite provides enterprise-grade network device discovery through SNMP with a focus on accuracy, customization, and practical deployment needs. Built for network administrators who need reliable device identification without vendor lock-in.

## Architecture

```mermaid
graph TB
    %% Input Layer
    Network[Network Segment<br/>CIDR: 192.168.1.0/24] --> Scanner
    Rules[vendor_fingerprints.yaml<br/>Detection Rules] --> Scanner
    Config[Scanner Configuration<br/>SNMP Credentials<br/>TCP Ports<br/>Timeouts] --> Scanner

    %% Core Scanner Component
    subgraph Scanner["🔍 SNMP Scanner (pyscanner3.py)"]
        direction TB
        TCP[TCP Pre-Filter<br/>Check ports: 22,161,443]
        SNMP[SNMP Collection<br/>v3 → v2c Fallback]
        Fingerprint[Fingerprint Engine<br/>OID + Pattern Matching]
        Extract[Field Extraction<br/>Model/Serial/Firmware]
        
        TCP --> SNMP
        SNMP --> Fingerprint
        Fingerprint --> Extract
    end

    %% Fingerprint Management
    subgraph FingerprintMgmt["🖥️ Fingerprint Management"]
        direction TB
        Editor[Fingerprint Editor<br/>fingerprint_widget.py]
        Validate[Rule Validation<br/>Pattern Testing]
        Export[Rule Export/Import<br/>YAML Management]
        
        Editor --> Validate
        Validate --> Export
    end

    %% Output Processing
    Scanner --> ScanOutput[Scan Results<br/>JSON Format<br/>Device Data + Metadata]
    
    %% CMDB Import Pipeline
    subgraph CMDBPipeline["📊 CMDB Import Pipeline"]
        direction TB
        Import[Import Tool<br/>import_scan_ui.py]
        Domain[Domain Processing<br/>Strip .local, .corp, etc.]
        Filter[Advanced Filtering<br/>Vendor/Type/Confidence]
        Preview[Device Preview<br/>Before/After Comparison]
        Normalize[Data Normalization<br/>Deduplication Logic]
        
        Import --> Domain
        Domain --> Filter
        Filter --> Preview
        Preview --> Normalize
    end

    %% Data Stores
    ScanOutput --> CMDBPipeline
    CMDBPipeline --> Database[(CMDB Database<br/>SQLite/PostgreSQL)]
    CMDBPipeline --> ExportData[Export Formats<br/>JSON/CSV/Excel]

    %% Management Interfaces
    FingerprintMgmt -.-> Rules
    Rules -.-> Scanner
    
    %% Styling
    classDef scanner fill:#0066cc,stroke:#004499,stroke-width:2px,color:#fff
    classDef editor fill:#009900,stroke:#006600,stroke-width:2px,color:#fff
    classDef import fill:#cc6600,stroke:#994400,stroke-width:2px,color:#fff
    classDef data fill:#666666,stroke:#333333,stroke-width:2px,color:#fff
    classDef config fill:#9900cc,stroke:#660099,stroke-width:2px,color:#fff

    class Scanner scanner
    class FingerprintMgmt editor
    class CMDBPipeline import
    class Database,ExportData data
    class Network,Rules,Config,ScanOutput config
```

## Data Flow Architecture

```mermaid
sequenceDiagram
    participant N as Network Device
    participant S as SNMP Scanner
    participant FE as Fingerprint Engine
    participant R as Rules Database
    participant I as Import Tool
    participant DB as CMDB Database

    Note over N,DB: Discovery Phase
    S->>N: TCP Port Check (22,161,443)
    N-->>S: Port Response/Timeout
    
    alt TCP Responsive
        S->>N: SNMPv3 Request (sysDescr, sysName)
        N-->>S: SNMP Response/Timeout
        
        alt SNMPv3 Failed
            S->>N: SNMPv2c Request (multiple communities)
            N-->>S: SNMP Response
        end
        
        S->>FE: Raw SNMP Data
        FE->>R: Query Detection Rules
        R-->>FE: Vendor Patterns + OIDs
        FE->>FE: Pattern Matching + OID Analysis
        FE-->>S: Device Identity (Vendor/Model/Type)
        
        S->>S: Extract Fields (Serial/Firmware)
        S-->>I: Structured Device Data
    else TCP Unresponsive
        S->>S: Skip SNMP (Performance Optimization)
    end

    Note over I,DB: Import Phase
    I->>I: Domain Name Processing
    I->>I: Apply Filters (Vendor/Type/Confidence)
    I->>I: Deduplicate Devices
    I->>DB: Bulk Insert/Update
    DB-->>I: Import Statistics
```

## Component Architecture

```mermaid
graph LR
    %% Core Components
    subgraph Core["Core Scanner Engine"]
        direction TB
        TCP[TCP Port Checker<br/>Async Connection Tests]
        SNMP[SNMP Collector<br/>v3/v2c Fallback Logic]
        FP[Fingerprint Engine<br/>Pattern + OID Matching]
        
        TCP --> SNMP
        SNMP --> FP
    end

    %% Configuration Layer
    subgraph Config["Configuration Layer"]
        direction TB
        Creds[SNMP Credentials<br/>Communities/Users]
        Ports[TCP Port List<br/>Service Detection]
        Rules[Fingerprint Rules<br/>vendor_fingerprints.yaml]
        Perf[Performance Settings<br/>Concurrency/Timeouts]
    end

    %% Processing Pipeline
    subgraph Pipeline["Data Processing Pipeline"]
        direction TB
        Collect[Data Collection<br/>Standard + Vendor OIDs]
        Parse[Response Parsing<br/>Type Conversion]
        Match[Pattern Matching<br/>Confidence Scoring]
        Extract[Field Extraction<br/>Regex Processing]
        Format[Output Formatting<br/>JSON Schema]
        
        Collect --> Parse
        Parse --> Match
        Match --> Extract
        Extract --> Format
    end

    %% User Interfaces
    subgraph UI["User Interfaces"]
        direction TB
        CLI[Command Line<br/>pyscanner3.py]
        Editor[GUI Editor<br/>fingerprint_widget.py]
        Import[Import Tool<br/>import_scan_ui.py]
    end

    %% Data Flow
    Config --> Core
    Core --> Pipeline
    Pipeline --> Output[Scan Results<br/>Device Database]
    UI --> Config
    UI --> Core
    Output --> UI

    %% Styling
    classDef core fill:#0066cc,stroke:#004499,stroke-width:3px,color:#fff
    classDef config fill:#9900cc,stroke:#660099,stroke-width:2px,color:#fff
    classDef pipeline fill:#cc6600,stroke:#994400,stroke-width:2px,color:#fff
    classDef ui fill:#009900,stroke:#006600,stroke-width:2px,color:#fff
    classDef output fill:#666666,stroke:#333333,stroke-width:2px,color:#fff

    class Core core
    class Config config
    class Pipeline pipeline
    class UI ui
    class Output output
```

## Core Components

### 🔍 **SNMP Scanner (`pyscanner3.py`)**
High-performance async SNMP scanner with intelligent fallback strategies and robust error handling.

![Scanner Progress](docs/images/scanner-progress.png)
*Real-time scan progress with device detection and vendor identification*

### 📋 **Fingerprint Engine (`vendor_fingerprints.yaml`)**
Completely open and customizable device identification rules - no black box algorithms.

```yaml
cisco:
  definitive_patterns:
    - pattern: "cisco ios software"
      confidence: 100
  fingerprint_oids:
    - name: "Cisco Catalyst Model"
      oid: "1.3.6.1.4.1.9.1.2694"
      definitive: true
```

### 🖥️ **Fingerprint Editor (`fingerprint_widget.py`)**
GUI editor for managing vendor detection rules with data preservation guarantees.

![Fingerprint Editor](docs/images/fingerprint-editor-main.png)
*Main fingerprint editor interface with vendor list and configuration tabs*

![Detection Patterns](docs/images/fingerprint-detection-patterns.png)
*Configure definitive patterns, detection rules, and exclusion filters*

![OID Fingerprints](docs/images/fingerprint-oid-config.png)
*Vendor-specific SNMP OID configuration with priority and definitiveness settings*

![Device Types](docs/images/fingerprint-device-types.png)
*Device type classification rules and extraction patterns*

![YAML Editor](docs/images/fingerprint-yaml-editor.png)
*Raw YAML editor with syntax highlighting and validation*

### 📊 **CMDB Import Tool (`import_scan_ui.py`)**
Advanced import processor with domain normalization and enterprise-ready filtering.

![CMDB Import Tool](docs/images/cmdb-import-main.png)
*Main CMDB import interface showing scan file management and device preview*

![Domain Processing](docs/images/cmdb-domain-processing.png)
*Domain name stripping configuration with custom patterns and before/after preview*

![Device Preview](docs/images/cmdb-device-preview.png)
*Device preview table showing original names, stripped names, and domain processing results*

![Import Statistics](docs/images/cmdb-import-stats.png)
*Comprehensive statistics and vendor breakdown after import processing*

## Key Features

### **Smart SNMP Strategy**
- **Version fallback**: Automatically tries SNMPv3 → SNMPv2c with multiple communities
- **TCP pre-filtering**: Skip SNMP attempts on unresponsive hosts (major performance boost)
- **Concurrent scanning**: Configurable parallelism with intelligent rate limiting
- **Error resilience**: Auto-creates output directories, handles network timeouts gracefully

![SNMP Strategy](docs/images/snmp-strategy-diagram.png)
*SNMP version fallback and TCP pre-filtering workflow*

### **Advanced Device Fingerprinting**
- **Definitive OID matching**: 100% confidence identification using vendor-specific MIBs
- **Pattern hierarchy**: Definitive → detection → exclusion pattern matching
- **Field extraction**: Smart regex-based model/serial/firmware extraction
- **Device type classification**: Granular categorization (switch/router/AP/UPS/firewall/etc.)

![Fingerprinting Process](docs/images/fingerprinting-process.png)
*Device fingerprinting workflow from SNMP data to vendor identification*

### **Domain Intelligence**
- **Automatic domain stripping**: Removes `.local`, `.corp`, `.com` suffixes for clean hostnames
- **Custom domain patterns**: Add organization-specific domains to strip
- **Before/after preview**: Visual confirmation of domain processing
- **Deduplication friendly**: Normalized names prevent duplicate entries

![Domain Stripping](docs/images/domain-stripping-example.png)
*Before and after domain stripping with highlighted changes*

### **Enterprise Integration**
- **CMDB-ready output**: Direct import into asset management systems
- **Batch processing**: Handle multiple scan files with filtering and validation
- **Export flexibility**: JSON, CSV formats with customizable field selection
- **Audit trails**: Comprehensive logging of all operations

![CMDB Integration](docs/images/cmdb-integration-flow.png)
*End-to-end workflow from network scan to CMDB integration*

## What Makes This Unique

### **Truly Open Fingerprinting**
Unlike commercial solutions, every detection rule is visible and editable. No vendor databases to license, no proprietary algorithms to reverse-engineer. Add support for custom devices in minutes, not months.

![Open Fingerprinting](docs/images/open-vs-proprietary.png)
*Comparison of open fingerprinting vs. proprietary black-box solutions*

### **Domain Name Intelligence**
Handles the real-world mess of inconsistent domain naming. Enterprise networks often have devices with mixed domain suffixes (`.local`, `.domain.com`, bare hostnames) - this scanner normalizes them intelligently.

### **Performance Without Compromise**
TCP pre-filtering dramatically reduces scan time by skipping SNMP attempts on hosts that aren't listening. Combined with async processing and smart timeouts, you get both speed and accuracy.

![Performance Comparison](docs/images/performance-benchmarks.png)
*Scan time comparison with and without TCP pre-filtering*

### **Data Preservation Architecture**
The fingerprint editor preserves all existing YAML data when making changes. Edit vendor rules without fear of losing custom configurations or breaking existing detection logic.

![Data Preservation](docs/images/data-preservation-demo.png)
*YAML editor showing preserved fields alongside UI-managed configuration*

### **Real-World Error Handling**
Built by network admins for network admins. Handles the edge cases: missing directories, permission issues, network timeouts, malformed responses, inconsistent device configurations.

## Quick Start

### Basic Network Scan
```bash
python3 pyscanner3.py --cidr 192.168.1.0/24 --output results.json
```

![Basic Scan Output](docs/images/basic-scan-terminal.png)
*Terminal output showing scan progress and device discovery*

### Advanced Scan with Filtering
```bash
python3 pyscanner3.py \
    --cidr 10.0.0.0/16 \
    --concurrent 50 \
    --snmp-version v2c \
    --communities public,private,community \
    --tcp-ports 22,161,443 \
    --output ./results/scan_$(date +%Y%m%d).json
```

![Advanced Scan Results](docs/images/advanced-scan-results.png)
*Detailed scan results with vendor breakdown and statistics*

### Custom Fingerprint Development
1. Run initial scan to identify unknown devices
2. Launch fingerprint editor: `python3 fingerprint_widget.py`
3. Add vendor rules using captured SNMP data
4. Validate and test new fingerprints
5. Re-scan to verify improved detection

![Fingerprint Development Workflow](docs/images/fingerprint-development-workflow.png)
*Step-by-step process for developing custom device fingerprints*

### CMDB Import with Domain Processing
1. Launch import tool: `python3 import_scan_ui.py`
2. Add scan files and configure domain stripping
3. Preview processed device names
4. Import to database with confidence filtering

![CMDB Import Workflow](docs/images/cmdb-import-workflow.png)
*Complete CMDB import process with domain processing and validation*

## Requirements

- Python 3.8+
- `pysnmp` for SNMP operations
- `PyQt6` for GUI components (fingerprint editor, import tool)
- `pyyaml` for configuration management

```bash
pip install pysnmp pyyaml PyQt6
```

## Configuration

### SNMP Credentials
- **SNMPv3**: Username, auth protocol/key, privacy protocol/key
- **SNMPv2c**: Multiple community strings with automatic fallback
- **Mixed environments**: Automatic version detection and fallback

![SNMP Configuration](docs/images/snmp-config-options.png)
*SNMP credential configuration options and version fallback settings*

### Fingerprint Rules
- **Vendor patterns**: Text matching in system descriptions
- **OID fingerprints**: Vendor-specific MIB object queries
- **Device classification**: Rule-based type determination
- **Field extraction**: Regex patterns for model/serial/firmware

![Fingerprint Configuration](docs/images/fingerprint-config-overview.png)
*Overview of fingerprint rule configuration options*

### Performance Tuning
- **Concurrency**: Balance between speed and network load
- **Timeouts**: Adjust for network latency and device response times
- **TCP pre-filtering**: Skip SNMP on unresponsive hosts

![Performance Tuning](docs/images/performance-tuning-options.png)
*Performance configuration options and recommended settings*

## Contributing

The fingerprint database is community-driven. Submit vendor detection rules, device type classifications, and field extraction patterns via pull requests. All contributions are immediately visible and auditable.

![Contributing Workflow](docs/images/contributing-workflow.png)
*Process for contributing new vendor fingerprints and device rules*

## License

Open source - adapt, modify, and deploy without licensing restrictions.

---

*Built for network professionals who need reliable device discovery without vendor lock-in or proprietary limitations.*

![Scanner Suite Ecosystem](docs/images/scanner-ecosystem.png)
*Complete ecosystem showing all components working together*