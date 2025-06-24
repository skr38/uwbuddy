import json
import paho.mqtt.client as mqtt

class LocationMQTT:
    def __init__(self, broker, port, topic):
        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.topic = topic
        self._location_callback = None

    def _on_connect(self, client, userdata, flags, rc):
        print("Connected:", mqtt.connack_string(rc))
        client.subscribe(self.topic)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload)
            pos = payload["location"]["position"]
            node_id = payload.get("node_id", "unknown")  # Extract node ID to identify tags
            if self._location_callback:
                self._location_callback(node_id, pos)
        except Exception as e:
            print("Error parsing message:", e)

    def set_location_callback(self, callback):
        """Register the consumer callback to receive node_id and pos dict."""
        self._location_callback = callback

    def start(self, broker, port):
        self.client.connect(broker, port, keepalive=60)
        self.client.loop_start()
