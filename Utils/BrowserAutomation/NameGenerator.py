import uuid
import random
import string
from datetime import datetime
from faker import Faker


class NameGenerator:
    """
    Utility class for generating unique names and dynamic test data.
    Supports various placeholder types for realistic test data generation.
    """
    
    # Initialize Faker for realistic data generation
    _faker = Faker()
    
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
    
    # ===== REALISTIC DATA PLACEHOLDERS =====
    
    @staticmethod
    def generate_random_string(length: int = 10) -> str:
        """
        Generate a random alphanumeric string.
        
        Examples:
            {{random_string}} -> "k7m2p9x4q1"
            {{random_string:5}} -> "a8c3z"
        """
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))
    
    @staticmethod
    def generate_random_number(min_val: int = 1, max_val: int = 10000) -> int:
        """
        Generate a random number within range.
        
        Examples:
            {{random_number}} -> 7543
            {{random_number:1:100}} -> 47
        """
        return random.randint(min_val, max_val)
    
    @staticmethod
    def generate_random_name() -> str:
        """
        Generate a realistic full name.
        
        Examples:
            {{random_name}} -> "John Smith"
        """
        return NameGenerator._faker.name()
    
    @staticmethod
    def generate_random_first_name() -> str:
        """
        Generate a realistic first name.
        
        Examples:
            {{random_first_name}} -> "John"
        """
        return NameGenerator._faker.first_name()
    
    @staticmethod
    def generate_random_last_name() -> str:
        """
        Generate a realistic last name.
        
        Examples:
            {{random_last_name}} -> "Smith"
        """
        return NameGenerator._faker.last_name()
    
    @staticmethod
    def generate_random_email() -> str:
        """
        Generate a realistic email address.
        
        Examples:
            {{random_email}} -> "john.smith@example.com"
        """
        return NameGenerator._faker.email()
    
    @staticmethod
    def generate_random_phone() -> str:
        """
        Generate a realistic phone number in international format.
        Produces clean format with only + and digits (no dashes/spaces/parentheses).
        This maximizes compatibility with different API validation rules.
        
        Examples:
            {{random_phone}} -> "+12025551234" (E.164 format)
        """
        # Generate a 10-digit US phone number
        import random
        area_code = random.randint(200, 999)  # Valid area codes start at 200
        exchange = random.randint(200, 999)   # Exchange code (middle 3 digits)
        subscriber = random.randint(0, 9999)  # Last 4 digits
        
        # Return in E.164 format: +[country code][area code][exchange][subscriber]
        # This is the most universally accepted international format
        return f"+1{area_code}{exchange}{subscriber:04d}"
    
    @staticmethod
    def generate_random_address() -> str:
        """
        Generate a realistic street address.
        
        Examples:
            {{random_address}} -> "742 Evergreen Terrace"
        """
        return NameGenerator._faker.street_address()
    
    @staticmethod
    def generate_random_city() -> str:
        """
        Generate a realistic city name.
        
        Examples:
            {{random_city}} -> "Springfield"
        """
        return NameGenerator._faker.city()
    
    @staticmethod
    def generate_random_country() -> str:
        """
        Generate a realistic country name.
        
        Examples:
            {{random_country}} -> "United States"
        """
        return NameGenerator._faker.country()
    
    @staticmethod
    def generate_random_company() -> str:
        """
        Generate a realistic company name with ONLY alphabetic characters.
        Strips all non-alphabetic characters (hyphens, commas, periods, etc.)
        to comply with strict API validation rules.
        
        Examples:
            {{random_company}} -> "AcmeCorporation" (no spaces/hyphens/symbols)
        """
        import re
        # Generate company name
        company = NameGenerator._faker.company()
        # Remove all non-alphabetic characters (keep only letters)
        company_clean = re.sub(r'[^a-zA-Z]', '', company)
        
        # If the cleaned name is too short (less than 3 chars), generate a simple one
        if len(company_clean) < 3:
            # Fallback: Generate simple company name from last name
            company_clean = NameGenerator._faker.last_name() + "Corporation"
            company_clean = re.sub(r'[^a-zA-Z]', '', company_clean)
        
        return company_clean
    
    @staticmethod
    def generate_random_job_title() -> str:
        """
        Generate a realistic job title.
        
        Examples:
            {{random_job_title}} -> "Software Engineer"
        """
        return NameGenerator._faker.job()
    
    @staticmethod
    def generate_random_text(sentences: int = 3) -> str:
        """
        Generate random text with specified number of sentences.
        
        Examples:
            {{random_text}} -> "Lorem ipsum dolor sit amet..."
            {{random_text:5}} -> "Five sentences of text..."
        """
        return NameGenerator._faker.text(max_nb_chars=sentences * 50)
    
    @staticmethod
    def generate_random_url() -> str:
        """
        Generate a realistic URL.
        
        Examples:
            {{random_url}} -> "https://www.example.com"
        """
        return NameGenerator._faker.url()
    
    @staticmethod
    def generate_random_username() -> str:
        """
        Generate a realistic username.
        
        Examples:
            {{random_username}} -> "john_smith_123"
        """
        return NameGenerator._faker.user_name()
    
    @staticmethod
    def generate_random_color() -> str:
        """
        Generate a random color name.
        
        Examples:
            {{random_color}} -> "blue"
        """
        return NameGenerator._faker.color_name()
    
    @staticmethod
    def generate_random_date(format: str = "%Y-%m-%d") -> str:
        """
        Generate a random date.
        
        Examples:
            {{random_date}} -> "2024-03-15"
            {{random_date:%d/%m/%Y}} -> "15/03/2024"
        """
        return NameGenerator._faker.date(pattern=format)
    
    @staticmethod
    def generate_random_boolean() -> bool:
        """
        Generate a random boolean value.
        
        Examples:
            {{random_boolean}} -> True or False
        """
        return random.choice([True, False])
    
    @staticmethod
    def generate_random_ip() -> str:
        """
        Generate a random IP address.
        
        Examples:
            {{random_ip}} -> "192.168.1.42"
        """
        return NameGenerator._faker.ipv4()
    
    @staticmethod
    def generate_random_uuid() -> str:
        """
        Generate a random UUID.
        
        Examples:
            {{random_uuid}} -> "a7b3c9d2-e5f1-4a8b-9c3d-2e6f7a8b9c0d"
        """
        return str(uuid.uuid4())
