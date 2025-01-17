import os
from dotenv import load_dotenv
from pathlib import Path

class System:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(System, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        # Load environment variables from .env file
        env_path = Path(__file__).parent.parent / '.env'
        load_dotenv(dotenv_path=env_path)
        
        # Database configuration
        self.db_host = os.getenv('DB_HOST', 'localhost')
        self.db_port = os.getenv('DB_PORT', '5432')
        self.db_name = os.getenv('DB_NAME', 'postgres')
        self.db_user = os.getenv('DB_USER', 'postgres')
        self.db_password = os.getenv('DB_PASSWORD', 'postgres')
        
        # AI model configuration
        self.ai_model = os.getenv('AI_MODEL', 'gemini').lower()
        self.gemini_api_key = os.getenv('GEMINI_API')
        self.claude_api_key = os.getenv('CLAUDE_API')
        
        self._initialized = True

    @property
    def db_connection_string(self) -> str:
        """Get the database connection string."""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    def validate_api_keys(self) -> bool:
        """Validate that required API keys are present."""
        if self.ai_model == 'gemini' and not self.gemini_api_key:
            print("Warning: GEMINI_API key is not set in .env file")
            return False
        if self.ai_model == 'claude' and not self.claude_api_key:
            print("Warning: CLAUDE_API key is not set in .env file")
            return False
        return True
