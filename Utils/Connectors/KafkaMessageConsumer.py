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
        self.consumer = KafkaConsumer(
            topic,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            auto_offset_reset='earliest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
    
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
                                    
                        except Exception as e:
                            self.logger.error(f"Error processing message: {e}")
                            continue

            except Exception as e:
                self.logger.error(f"Error consuming message: {e}")

    def process_message(self, message):
        """Process a message received from Kafka."""
        try:
            file_path = message.get('file_path')
            file_name = message.get('file_name')
            attachment_type = message.get('attachment_type')
            client_id = message.get('client_id')

            if not file_path or not file_name or not attachment_type:
                self.logger.error("Missing required fields in message")
                return

            if attachment_type == 'image':
                analyzer = ImageAnalyzer()
                analyzer.analyze_img(file_path=file_path, client_id=client_id)
            else:
                analyzer = TextAnalyzer()
                with open(file_path, 'rb') as file:
                    file_content = file.read()
                    analyzer.analyze_txt(file_content=file_content, client_id=client_id)

            self.logger.info(f"Successfully processed {file_name}")

            # Clean up the file after processing
            try:
                os.remove(file_path)
                self.logger.info(f"Cleaned up file: {file_path}")
            except OSError as e:
                self.logger.error(f"Error removing file {file_path}: {e}")

        except Exception as e:
            self.logger.error(f"Error processing message: {e}")

    def stop(self):
        self.running = False
        self.consumer.close()