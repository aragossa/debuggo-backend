from Utils.AIHelper.ImageAnalyzer import ImageAnalyzer
from Utils.AIHelper.TextAnalyzer import TextAnalyzer
from kafka import KafkaConsumer
import json
import logging
import sys
import os

from Utils.BrowserAutomation.TestRunner import TestRunner


class KafkaMessageConsumer:
    def __init__(self, bootstrap_servers: str, topic: str, group_id: str):
        self.running = True
        self.logger = self._setup_logger()
        self.consumer_id = f"{group_id}_{os.getpid()}"  # Unique ID per process
        self.logger.info(f"Initializing Kafka consumer {self.consumer_id}")
        self.consumer = KafkaConsumer(
            topic,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            auto_offset_reset='earliest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        self.logger.info(f"Kafka consumer {self.consumer_id} connected successfully")
    
    def _setup_logger(self):
        logger = logging.getLogger('KafkaMessageConsumer')
        logger.setLevel(logging.INFO)

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger


    def consume_messages(self):
        while self.running:
            try:
                messages = self.consumer.poll(timeout_ms=1000)
                for topic_partition, records in messages.items():
                    for record in records:
                        try:
                            request = record.value
                            if request.get('attachment_type') == 'image' and request.get('request_type') == 'generate_test_cases':
                                self.process_message(request)
                                
                            elif request.get('attachment_type') == 'text' and request.get('request_type') == 'generate_test_cases':
                                self.process_message(request)
                                
                            elif request.get('request_type') == 'generate_test_steps':
                                runner = TestRunner()
                                test_case_id = request.get('test_case_id')
                                runner.generate_test_steps(test_case_id)
                            
                            elif request.get('request_type') == 'generate_api_test_steps':
                                self.process_api_test_steps_generation(request)
                                    
                        except Exception as e:
                            self.logger.error(f"Error processing message: {e}")
                            continue

            except Exception as e:
                self.logger.error(f"Error consuming message: {e}")

    def is_api_schema_file(self, file_name, file_content=None):
        """Determine if the file is an API schema based on filename and content."""
        # Check file extension
        api_schema_extensions = ['.json', '.yaml', '.yml']
        if any(file_name.lower().endswith(ext) for ext in api_schema_extensions):
            # If we have file content, check for API schema indicators
            if file_content:
                try:
                    content_str = file_content.decode('utf-8').lower()
                    api_indicators = [
                        'openapi', 'swagger', 'paths:', 'components:',
                        'info:', 'servers:', 'api', 'endpoints',
                        'definitions:', 'schemes:', 'host:', 'basepath:'
                    ]
                    return any(indicator in content_str for indicator in api_indicators)
                except:
                    return False
            # If no content available, assume it's an API schema based on extension
            return True
        return False

    def process_message(self, message):
        """Process a message received from Kafka."""
        try:
            file_path = message.get('file_path')
            file_name = message.get('file_name')
            attachment_type = message.get('attachment_type')
            client_id = message.get('client_id')
            project_id = message.get('project_id')  

            if not file_path or not file_name or not attachment_type:
                self.logger.error("Missing required fields in message")
                return
            
            # Check if file exists (may have been processed by another consumer)
            if not os.path.exists(file_path):
                self.logger.warning(f"File {file_path} not found - may have been processed by another consumer")
                return

            if attachment_type == 'image':
                analyzer = ImageAnalyzer()
                analyzer.analyze_img(file_path=file_path, client_id=client_id, project_id=project_id)
            else:
                # Read file content to determine if it's an API schema
                with open(file_path, 'rb') as file:
                    file_content = file.read()
                
                # Check if this is an API schema file
                if self.is_api_schema_file(file_name, file_content):
                    self.logger.info(f"Detected API schema file: {file_name}")
                    # Use TextAnalyzer but specify it's for API schema
                    analyzer = TextAnalyzer()
                    analyzer.analyze_api_schema(file_content=file_content, client_id=client_id, project_id=project_id, file_name=file_name)
                else:
                    self.logger.info(f"Processing as regular text file: {file_name}")
                    analyzer = TextAnalyzer()
                    analyzer.analyze_txt(file_content=file_content, client_id=client_id, project_id=project_id)

                self.logger.info(f"Successfully processed {file_name}")

            # Clean up the file after processing
            try:
                os.remove(file_path)
                self.logger.info(f"Cleaned up file: {file_path}")
            except OSError as e:
                self.logger.error(f"Error removing file {file_path}: {e}")

        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
    
    def process_api_test_steps_generation(self, request):
        """Process API test steps generation request."""
        try:
            test_case_id = request.get('test_case_id')
            schema_content = request.get('schema_content')
            client_id = request.get('client_id')
            project_id = request.get('project_id')
            
            if not all([test_case_id, schema_content, client_id, project_id]):
                self.logger.error("Missing required fields for API test steps generation")
                return
            
            self.logger.info(f"Processing API test steps generation for test case {test_case_id}")
            
            # Import here to avoid circular dependencies
            from Services.ApiSchemaService import ApiSchemaService
            
            # Generate steps
            service = ApiSchemaService()
            success = service.generate_test_steps_for_flow(
                test_case_id=test_case_id,
                schema_content=schema_content,
                client_id=client_id,
                project_id=project_id
            )
            
            if success:
                self.logger.info(f"Successfully generated API test steps for test case {test_case_id}")
            else:
                self.logger.error(f"Failed to generate API test steps for test case {test_case_id}")
                
        except Exception as e:
            self.logger.error(f"Error processing API test steps generation: {e}", exc_info=True)

    def stop(self):
        self.running = False
        self.consumer.close()