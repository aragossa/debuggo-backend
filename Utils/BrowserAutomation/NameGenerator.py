import uuid
import random
import string
from datetime import datetime


class NameGenerator:
    """
    Utility class for generating unique names to avoid duplicate name failures in tests.
    """
    
    @staticmethod
    def generate_unique_name(prefix: str = "", suffix: str = "", length: int = 8) -> str:
        """
        Generate a unique name with optional prefix and suffix.
        
        Args:
            prefix (str): Optional prefix for the name (e.g., "Client", "User", "Group")
            suffix (str): Optional suffix for the name
            length (int): Length of the random part (default: 8)
            
        Returns:
            str: A unique name string
            
        Examples:
            generate_unique_name("Client") -> "Client_a7b3c9d2"
            generate_unique_name("User", "Test") -> "User_f4e8d1a6_Test"
            generate_unique_name() -> "a7b3c9d2"
        """
        # Generate random alphanumeric string
        random_part = ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
        
        # Build the name
        parts = []
        if prefix:
            parts.append(prefix)
        parts.append(random_part)
        if suffix:
            parts.append(suffix)
            
        return '_'.join(parts)
    
    @staticmethod
    def generate_timestamp_name(prefix: str = "", format: str = "%Y%m%d_%H%M%S") -> str:
        """
        Generate a name with timestamp to ensure uniqueness.
        
        Args:
            prefix (str): Optional prefix for the name
            format (str): Datetime format string (default: "%Y%m%d_%H%M%S")
            
        Returns:
            str: A timestamp-based unique name
            
        Examples:
            generate_timestamp_name("Client") -> "Client_20250129_143052"
            generate_timestamp_name() -> "20250129_143052"
        """
        timestamp = datetime.now().strftime(format)
        
        if prefix:
            return f"{prefix}_{timestamp}"
        return timestamp
    
    @staticmethod
    def generate_uuid_name(prefix: str = "", short: bool = True) -> str:
        """
        Generate a name using UUID for guaranteed uniqueness.
        
        Args:
            prefix (str): Optional prefix for the name
            short (bool): If True, use only first 8 characters of UUID (default: True)
            
        Returns:
            str: A UUID-based unique name
            
        Examples:
            generate_uuid_name("Client", short=True) -> "Client_a7b3c9d2"
            generate_uuid_name("Client", short=False) -> "Client_a7b3c9d2-e5f1-4a8b-9c3d-2e6f7a8b9c0d"
        """
        uuid_str = str(uuid.uuid4())
        
        if short:
            uuid_str = uuid_str.split('-')[0]
            
        if prefix:
            return f"{prefix}_{uuid_str}"
        return uuid_str
    
    @staticmethod
    def generate_sequential_name(prefix: str = "", counter: int = None) -> str:
        """
        Generate a sequential name with a counter.
        
        Args:
            prefix (str): Optional prefix for the name
            counter (int): Optional counter value. If None, uses timestamp milliseconds
            
        Returns:
            str: A sequential name
            
        Examples:
            generate_sequential_name("Client", 1) -> "Client_001"
            generate_sequential_name("User") -> "User_1706543852123"
        """
        if counter is None:
            # Use timestamp milliseconds as counter
            counter = int(datetime.now().timestamp() * 1000)
            
        if prefix:
            return f"{prefix}_{counter:03d}" if counter < 1000 else f"{prefix}_{counter}"
        return str(counter)
    
    @staticmethod
    def generate_descriptive_name(base: str, descriptor: str = None) -> str:
        """
        Generate a descriptive name combining base name with a unique identifier.
        
        Args:
            base (str): Base name (e.g., "TestClient", "NewUser")
            descriptor (str): Optional descriptor to add context
            
        Returns:
            str: A descriptive unique name
            
        Examples:
            generate_descriptive_name("TestClient") -> "TestClient_a7b3c9d2"
            generate_descriptive_name("NewUser", "Admin") -> "NewUser_Admin_f4e8d1a6"
        """
        random_part = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        
        if descriptor:
            return f"{base}_{descriptor}_{random_part}"
        return f"{base}_{random_part}"
