from kafka import KafkaProducer
import json
from typing import Dict, Any

class KafkaMessageProducer:
    def __init__(self, bootstrap_servers: str, topic: str):
        self.topic = topic
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )

    def send_message(self, message: Dict[str, Any]):
        print(self.topic)
        print(message)
        future = self.producer.send(self.topic, message)
        self.producer.flush()
        return future

    def close(self):
        self.producer.close()