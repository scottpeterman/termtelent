import re
from typing import Optional
from rapidcmdb.enh_int_normalizer import InterfaceNormalizer as EnhancedNormalizer, Platform
#Migrating to enhanced normalizer

class InterfaceNormalizer:
    """Legacy wrapper for enhanced interface normalizer"""

    @classmethod
    def normalize(cls, interface: str, vendor: Optional[str] = None) -> str:
        """Wrapper for enhanced normalizer that maintains old interface"""
        # Map old vendor strings to Platform enum if provided
        platform = None
        if vendor:
            vendor_map = {

            }
            platform = vendor_map.get(vendor.lower(), None)

        return EnhancedNormalizer.normalize(interface, platform)

    @classmethod
    def normalize_pair(cls, local_int: str, remote_int: str,
                       local_vendor: Optional[str] = None,
                       remote_vendor: Optional[str] = None) -> tuple[str, str]:
        """Wrapper for pair normalization"""
        local = cls.normalize(local_int, local_vendor)
        remote = cls.normalize(remote_int, remote_vendor)
        return local, remote

