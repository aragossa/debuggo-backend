import unittest
from unittest.mock import MagicMock, patch
import json
import base64
from auroqa.Utils.BrowserAutomation.TestRunner import TestRunner
from auroqa.Utils.AIHelper.AIHelper import AIHelper

class TestSelfHealing(unittest.TestCase):

    @patch('auroqa.Utils.BrowserAutomation.TestRunner.get_db_connection')
    @patch('auroqa.Utils.BrowserAutomation.TestRunner.AIHelper')
    def test_self_healing_trigger(self, MockAIHelper, mock_db_conn):
        print("TestRunner loaded successfully.")
        
if __name__ == "__main__":
    unittest.main()
