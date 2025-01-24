from Utils.AIHelper.ImageAnalyzer import ImageAnalyzer
from Utils.AIHelper.TextAnalyzer import TextAnalyzer
from kafka import KafkaConsumer
import json
import logging
import sys

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
                            print(f"Received message: {request}")
                            
                            if request.get('attachment_type') == 'image':
                                print('Processing image request')
                                file_path = request['file_path']
                                file_name = request['file_name']
                                print(f"Processing image from {file_path}")
                                
                                image_analyzer = ImageAnalyzer()
                                image_analyzer.analyze_img(file_path=file_path)
                                
                            elif request.get('attachment_type') == 'text':
                                print('Processing text request')
                                text_analyzer = TextAnalyzer()
                                file_content = request.get('file_content')
                                if file_content:
                                    result = text_analyzer.analyze_txt(file_content)
                                else:
                                    print("Warning: No file content in text request")
                                    
                        except Exception as e:
                            print(f"Error processing message: {str(e)}")
                            self.logger.error(f"Error processing message: {e}")
                            continue

            except Exception as e:
                print(f"Error consuming message: {str(e)}")
                self.logger.error(f"Error consuming message: {e}")

    def stop(self):
        self.running = False
        self.consumer.close()