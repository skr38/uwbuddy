import json
import paho.mqtt.client as mqtt
import logging

# Logger für bessere Diagnose
logger = logging.getLogger('LocationMQTT')

class LocationMQTT:
    def __init__(self, broker, port, topic):
        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect  # Neu hinzugefügt
        self.topic = topic
        self._location_callback = None
        self.connected = False
        self.broker = broker
        self.port = port

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

    def _on_message(self, client, userdata, msg):
        try:
            # Debug: Topic und Payload analysieren
            logger.info(f"🔍 MQTT Topic: {msg.topic}")
            logger.debug(f"📄 Raw Payload: {msg.payload.decode()}")
            
            payload = json.loads(msg.payload.decode())
            logger.debug(f"📊 Parsed Payload: {payload}")
            
            # Node-ID aus verschiedenen Quellen extrahieren
            pos = None
            node_id = "unknown"
            
            # Priorität 1: Node-ID aus Payload extrahieren
            if "node_id" in payload:
                node_id = payload["node_id"]
                logger.debug(f"🏷️  Node-ID aus Payload: {node_id}")
            
            # Priorität 2: Node-ID aus Topic extrahieren (dwm/node/XXXX/uplink/location)
            elif "/" in msg.topic:
                topic_parts = msg.topic.split('/')
                logger.debug(f"📡 Topic Parts: {topic_parts}")
                
                if len(topic_parts) >= 3 and topic_parts[1] == "node":
                    node_id = topic_parts[2]  # Index 2 sollte die Node-ID sein
                    logger.info(f"🏷️  Node-ID aus Topic extrahiert: {node_id}")
                else:
                    logger.warning(f"⚠️ Unerwartetes Topic-Format: {msg.topic}")
            
            # Priorität 3: Andere mögliche ID-Felder in Payload
            if node_id == "unknown":
                for id_field in ["id", "device_id", "tag_id", "node", "source"]:
                    if id_field in payload:
                        node_id = str(payload[id_field])
                        logger.info(f"🏷️  Node-ID aus Feld '{id_field}': {node_id}")
                        break
                    
            # Position aus verschiedenen Payload-Strukturen extrahieren
            # Struktur 1: {"location": {"position": {...}}}
            if "location" in payload and "position" in payload["location"]:
                pos = payload["location"]["position"]
                logger.debug("📍 Position aus location.position extrahiert")
            
            # Struktur 2: {"position": {...}}
            elif "position" in payload:
                pos = payload["position"]
                logger.debug("📍 Position aus position extrahiert")
            
            # Struktur 3: Direktes x,y,z Format
            elif all(key in payload for key in ["x", "y", "z"]):
                pos = {"x": payload["x"], "y": payload["y"], "z": payload["z"]}
                logger.debug("📍 Position aus direkten x,y,z Koordinaten extrahiert")
            
            # Struktur 4: Nested coordinates
            elif "coordinates" in payload:
                coords = payload["coordinates"]
                if all(key in coords for key in ["x", "y", "z"]):
                    pos = {"x": coords["x"], "y": coords["y"], "z": coords["z"]}
                    logger.debug("📍 Position aus coordinates extrahiert")
            
            # Struktur 5: Alternative Position-Felder
            elif any(field in payload for field in ["pos", "loc", "xyz"]):
                for field in ["pos", "loc", "xyz"]:
                    if field in payload:
                        field_data = payload[field]
                        if isinstance(field_data, dict) and all(key in field_data for key in ["x", "y", "z"]):
                            pos = {"x": field_data["x"], "y": field_data["y"], "z": field_data["z"]}
                            logger.debug(f"📍 Position aus {field} extrahiert")
                            break
                        
            # Position validieren und callback ausführen
            if pos and self._location_callback:
                # Sicherstellen dass Position numerische Werte hat
                try:
                    x = float(pos.get('x', 0))
                    y = float(pos.get('y', 0))
                    z = float(pos.get('z', 0))
                    
                    # Validierte Position
                    validated_pos = {"x": x, "y": y, "z": z}
                    
                    logger.info(f"📍 Position für Node {node_id}: x={x:.3f}, y={y:.3f}, z={z:.3f}")
                    
                    # Zusätzliche Metadaten falls verfügbar
                    if "timestamp" in payload:
                        logger.debug(f"⏰ Timestamp: {payload['timestamp']}")
                    if "quality" in payload:
                        logger.debug(f"📊 Signal Quality: {payload['quality']}")
                    
                    # Callback ausführen
                    self._location_callback(node_id, validated_pos)
                    
                except (ValueError, TypeError) as e:
                    logger.error(f"❌ Ungültige Positionskoordinaten: {e}")
                    logger.error(f"❌ Position war: {pos}")
            
            else:
                logger.warning(f"⚠️ Keine gültige Position gefunden")
                logger.warning(f"⚠️ Payload-Struktur: {list(payload.keys())}")
                logger.warning(f"⚠️ Vollständige Payload: {payload}")
                
                # Fallback: Alle verfügbaren Felder auflisten
                logger.info("🔍 Verfügbare Payload-Felder:")
                for key, value in payload.items():
                    if isinstance(value, dict):
                        logger.info(f"   {key}: {list(value.keys())}")
                    else:
                        logger.info(f"   {key}: {type(value).__name__}")
                    
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON Parse Fehler: {e}")
            logger.error(f"❌ Rohe Nachricht: {msg.payload}")
            logger.error(f"❌ Topic: {msg.topic}")
            
        except Exception as e:
            logger.error(f"❌ Fehler beim Verarbeiten der MQTT-Nachricht: {e}")
            logger.error(f"❌ Topic: {msg.topic}")
            logger.error(f"❌ Payload: {msg.payload}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
    
    
    def set_location_callback(self, callback):
        """Register the consumer callback to receive node_id and pos dict."""
        self._location_callback = callback
        logger.info("✅ Location Callback registriert")

    def start(self, broker, port):
        """Startet den MQTT Client"""
        try:
            logger.info(f"🚀 Starte MQTT Client - Broker: {broker}:{port}")
            logger.info(f"📡 Topic: {self.topic}")
            
            self.client.connect(broker, port, keepalive=60)
            self.client.loop_start()
            logger.info("✅ MQTT Client gestartet")
            
        except Exception as e:
            logger.error(f"❌ Fehler beim Starten des MQTT Clients: {e}")
            raise

    def stop(self):
        """Stoppt den MQTT Client ordnungsgemäß"""
        try:
            logger.info("🛑 Stoppe MQTT Client...")
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
            logger.info("✅ MQTT Client gestoppt")
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
                logger.debug(f"📤 Message gesendet zu {topic}: {message}")
            else:
                logger.error("❌ Kann nicht senden - MQTT nicht verbunden")
        except Exception as e:
            logger.error(f"❌ Fehler beim Senden: {e}")

