import json
import paho.mqtt.client as mqtt
import logging
import time

# Logger für bessere Diagnose
logger = logging.getLogger('LocationMQTT')

class LocationMQTT:
    def __init__(self, broker, port, topic):
        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        self.topic = topic
        self._location_callback = None
        self.connected = False
        self.broker = broker
        self.port = port
        
        # Tracking für spezifische Node-IDs
        self.tracked_nodes = {"4c87": "Tumbller", "0cad": "Target Person"}
        self.last_position_update = {}

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            logger.info(f"✅ MQTT verbunden: {mqtt.connack_string(rc)}")
            logger.info(f"📡 Subscribing zu Topic: {self.topic}")
            client.subscribe(self.topic)
        else:
            self.connected = False
            logger.error(f"❌ MQTT Verbindung fehlgeschlagen: {mqtt.connack_string(rc)}")

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        logger.warning(f"⚠️ MQTT Verbindung getrennt: {rc}")

    def _extract_node_id_from_topic(self, topic):
        """Extrahiert Node-ID nur aus validen Topic-Formaten"""
        parts = topic.split('/')
        
        # Validiere das erwartete Format: dwm/node/XXXX/uplink/location
        if (len(parts) == 5 and 
            parts[0] == "dwm" and 
            parts[1] == "node" and 
            parts[3] == "uplink" and 
            parts[4] == "location"):
            return parts[2]
        
        return None

    def _extract_position_from_payload(self, payload):
        """Extrahiert Position aus verschiedenen Payload-Strukturen"""
        pos = None
        
        # Struktur 1: {"location": {"position": {...}}}
        if "location" in payload and isinstance(payload["location"], dict):
            if "position" in payload["location"]:
                pos = payload["location"]["position"]
        
        # Struktur 2: {"position": {...}}
        elif "position" in payload:
            pos = payload["position"]
        
        # Struktur 3: Direktes x,y,z Format
        elif all(key in payload for key in ["x", "y", "z"]):
            pos = {"x": payload["x"], "y": payload["y"], "z": payload["z"]}
        
        # Struktur 4: Nested coordinates
        elif "coordinates" in payload and isinstance(payload["coordinates"], dict):
            coords = payload["coordinates"]
            if all(key in coords for key in ["x", "y", "z"]):
                pos = {"x": coords["x"], "y": coords["y"], "z": coords["z"]}
        
        return pos

    def _validate_position(self, pos):
        """Validiert und konvertiert Position zu numerischen Werten"""
        if not pos or not isinstance(pos, dict):
            return None
            
        try:
            x = float(pos.get('x', 0))
            y = float(pos.get('y', 0))
            z = float(pos.get('z', 0))
            
            return {"x": x, "y": y, "z": z}
        except (ValueError, TypeError) as e:
            logger.error(f"❌ Ungültige Positionskoordinaten: {e}")
            return None

    def _log_tracked_position(self, node_id, position):
        """Spezielle Ausgabe für getrackte Node-IDs"""
        current_time = time.time()
        
        if node_id in self.tracked_nodes:
            device_name = self.tracked_nodes[node_id]
            
            # Prüfe ob genug Zeit seit letztem Update vergangen ist (alle 2 Sekunden)
            if (node_id not in self.last_position_update or 
                current_time - self.last_position_update[node_id] >= 2.0):
                
                print(f"🤖 {device_name} ({node_id}): x={position['x']:.3f}m, y={position['y']:.3f}m, z={position['z']:.3f}m")
                self.last_position_update[node_id] = current_time

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())

            # Node-ID Extraktion mit verbesserter Prioritätslogik
            node_id = None
            
            # Priorität 1: Node-ID aus Payload extrahieren
            if "node_id" in payload:
                node_id = str(payload["node_id"])
            
            # Priorität 2: Node-ID aus Topic extrahieren (nur bei validem Format)
            if not node_id:
                extracted_id = self._extract_node_id_from_topic(msg.topic)
                if extracted_id:
                    node_id = extracted_id
            
            # Priorität 3: Andere mögliche ID-Felder in Payload
            if not node_id:
                for id_field in ["id", "device_id", "tag_id", "node", "source"]:
                    if id_field in payload:
                        node_id = str(payload[id_field])
                        break
            
            # Fallback: Verwende "unknown" als Node-ID
            if not node_id:
                node_id = "unknown"

            # Position extrahieren
            pos = self._extract_position_from_payload(payload)
            
            if pos:
                # Position validieren
                validated_pos = self._validate_position(pos)
                
                if validated_pos:
                    # Spezielle Ausgabe für getrackte Nodes
                    self._log_tracked_position(node_id, validated_pos)
                    
                    # Callback ausführen
                    if self._location_callback:
                        self._location_callback(node_id, validated_pos)

        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON Parse Fehler: {e}")
            
        except Exception as e:
            logger.error(f"❌ Fehler beim Verarbeiten der MQTT-Nachricht: {e}")

    def set_location_callback(self, callback):
        """Register the consumer callback to receive node_id and pos dict."""
        self._location_callback = callback

    def start(self, broker, port):
        """Startet den MQTT Client"""
        try:
            print(f"🚀 Starte MQTT Client - Broker: {broker}:{port}")
            print(f"📡 Topic: {self.topic}")
            print(f"👀 Tracking: {', '.join([f'{name} ({id})' for id, name in self.tracked_nodes.items()])}")
            self.client.connect(broker, port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            logger.error(f"❌ Fehler beim Starten des MQTT Clients: {e}")
            raise

    def stop(self):
        """Stoppt den MQTT Client ordnungsgemäß"""
        try:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
        except Exception as e:
            logger.error(f"❌ Fehler beim Stoppen des MQTT Clients: {e}")

    def is_connected(self):
        """Prüft ob MQTT Client verbunden ist"""
        return self.connected

    def publish(self, topic, message):
        """Sende eine Nachricht über MQTT"""
        try:
            if self.connected:
                self.client.publish(topic, message)
            else:
                logger.error("❌ Kann nicht senden - MQTT nicht verbunden")
        except Exception as e:
            logger.error(f"❌ Fehler beim Senden: {e}")
