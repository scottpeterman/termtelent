from typing import Dict, List, Tuple, Optional
import re
from dataclasses import dataclass
from enum import Enum, auto


class Platform(Enum):
    """Supported network platforms"""
    CISCO_IOS = auto()
    CISCO_NXOS = auto()
    ARISTA = auto()
    UNKNOWN = auto()


@dataclass
class InterfaceSpec:
    """Specification for interface matching and normalization"""
    pattern: str
    long_name: str
    short_name: str
    platforms: List[Platform] = None

    def __post_init__(self):
        if self.platforms is None:
            self.platforms = list(Platform)


class InterfaceNormalizer:
    """
    A robust interface name normalizer for network devices supporting
    Cisco IOS, NX-OS, and Arista platforms.
    """

    # Common synonyms for management interfaces
    MGMT_SYNONYMS = [
        r"^(?:ma)",
        r"^(?:oob)",
        r"^(?:oob_management)",
        r"^(?:management)",
        r"^(?:mgmt)",
    ]

    # Comprehensive interface specifications with both long and short names
    INTERFACE_SPECS = [
        # Standard Ethernet interfaces
        InterfaceSpec(r"^(?:eth|et|ethernet)(\d+(?:/\d+)*(?:\.\d+)?)",
                      "Ethernet\\1", "Eth\\1"),

        # Gigabit interfaces - full pattern including all variations
        InterfaceSpec(r"^(?:gi|gige|gigabiteth|gigabitethernet|gigabit)(\d+(?:/\d+)*(?:\.\d+)?)",
                      "GigabitEthernet\\1", "Gi\\1"),

        # Ten-Gigabit interfaces - full pattern including all variations
        InterfaceSpec(r"^(?:te|tengig|tengige|tengigabitethernet|tengigabit)(\d+(?:/\d+)*(?:\.\d+)?)",
                      "TenGigabitEthernet\\1", "Te\\1"),

        # 25-Gigabit interfaces
        InterfaceSpec(r"^(?:twe|twentyfivegig|twentyfivegige|twentyfivegigabitethernet)(\d+(?:/\d+)*(?:\.\d+)?)",
                      "TwentyFiveGigE\\1", "Twe\\1"),

        # 40-Gigabit interfaces
        InterfaceSpec(r"^(?:fo|fortygig|fortygige|fortygigabitethernet)(\d+(?:/\d+)*(?:\.\d+)?)",
                      "FortyGigabitEthernet\\1", "Fo\\1"),

        # 100-Gigabit interfaces
        InterfaceSpec(r"^(?:hu|hun|hundredgig|hundredgige|hundredgigabitethernet|100gig)(\d+(?:/\d+)*(?:\.\d+)?)",
                      "HundredGigabitEthernet\\1", "Hu\\1"),

        # Port channels
        InterfaceSpec(r"^(?:po|portchannel|port-channel|port_channel)(\d+)",
                      "Port-Channel\\1", "Po\\1"),

        # Management interfaces (with number)
        InterfaceSpec(r"^(?:ma|mgmt|management|oob_management|oob|wan)(\d+(?:/\d+)*)",
                      "Management\\1", "Ma\\1"),

        # Management interfaces (without number)
        InterfaceSpec(r"^(?:ma|mgmt|management|oob_management|oob|wan)$",
                      "Management", "Ma"),

        # VLAN interfaces
        InterfaceSpec(r"^(?:vl|vlan)(\d+)",
                      "Vlan\\1", "Vl\\1"),

        # Loopback interfaces
        InterfaceSpec(r"^(?:lo|loopback)(\d+)",
                      "Loopback\\1", "Lo\\1"),

        # FastEthernet interfaces (legacy)
        InterfaceSpec(r"^(?:fa|fast|fastethernet)(\d+(?:/\d+)*)",
                      "FastEthernet\\1", "Fa\\1"),
    ]

    @classmethod
    def normalize(cls, interface: str, platform: Optional[Platform] = None, use_short_name: bool = True) -> str:
        """
        Normalize interface names to a consistent format.

        Args:
            interface: The interface name to normalize
            platform: Optional platform type to inform normalization
            use_short_name: Whether to use short names (e.g., "Gi1/0/1") instead of
                          long names (e.g., "GigabitEthernet1/0/1")
        """
        if not interface:
            return ""

        # Handle space-separated hostname
        if " " in interface:
            parts = interface.rsplit(" ", 1)
            if len(parts) == 2:
                _, interface = parts

        # Handle hyphenated hostname
        if "-" in interface:
            parts = interface.rsplit("-", 1)
            if len(parts) == 2:
                _, interface = parts

        # Convert to lowercase for consistent matching
        interface = interface.lower().strip()

        # Check if it's a management interface variant
        for mgmt_pattern in cls.MGMT_SYNONYMS:
            if re.match(mgmt_pattern, interface, re.IGNORECASE):
                # Extract any numbers if present
                numbers = re.search(r'\d+(?:/\d+)*$', interface)
                suffix = numbers.group(0) if numbers else ""
                return f"Management{suffix}" if not use_short_name else f"Ma{suffix}"

        # Auto-select short names for certain platforms
        # if platform in [Platform.CISCO_NXOS, Platform.ARISTA]:
        #     use_short_name = True

        # Try to match and normalize the interface name
        for spec in cls.INTERFACE_SPECS:
            if platform in spec.platforms or not platform:
                if re.match(spec.pattern, interface, re.IGNORECASE):
                    replacement = spec.short_name if use_short_name else spec.long_name
                    return re.sub(spec.pattern, replacement, interface, flags=re.IGNORECASE)

        return interface


def test_interfaces():
    """Test function for interface normalization"""
    normalizer = InterfaceNormalizer()

    # Test cases with both long and short names
    test_cases = [
        # Management interface specific cases
        ("Ma1", "Management1", "Ma1"),
        ("oob_management1", "Management1", "Ma1"),
        ("management1", "Management1", "Ma1"),
        # input, expected_long, expected_short
        ("switch1-Gi1/0/1", "GigabitEthernet1/0/1", "Gi1/0/1"),
        ("ush-m1-core Fo1/0/14", "FortyGigabitEthernet1/0/14", "Fo1/0/14"),
        ("Eth1/1", "Ethernet1/1", "Eth1/1"),
        ("Te1/1/1", "TenGigabitEthernet1/1/1", "Te1/1/1"),
        ("Po1", "Port-Channel1", "Po1"),
        ("100Gig1/0/1", "HundredGigabitEthernet1/0/1", "Hu1/0/1"),
        # Management interface variants
        ("wan", "Management", "Ma"),
        ("oob", "Management", "Ma"),
        ("oob_management", "Management", "Ma"),
        ("mgmt0", "Management0", "Ma0"),
        ("management1", "Management1", "Ma1"),
    ]

    print("\nTesting interface normalization:")
    print("-" * 80)

    for test_case in test_cases:
        input_if = test_case[0]
        expected_long = test_case[1]
        expected_short = test_case[2]

        # Test long names
        result_long = normalizer.normalize(input_if, use_short_name=False)
        assert result_long == expected_long, f"Long name failed: {input_if} -> {result_long} (expected {expected_long})"

        # Test short names
        result_short = normalizer.normalize(input_if, use_short_name=True)
        assert result_short == expected_short, f"Short name failed: {input_if} -> {result_short} (expected {expected_short})"

        print(f"Input: {input_if:25} -> Long: {result_long:30} -> Short: {result_short}")


if __name__ == "__main__":
    test_interfaces()