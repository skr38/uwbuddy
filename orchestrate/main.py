#!/usr/bin/env python3
import threading
import time
import logging
import sys
import os
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import signal

# KRITISCH: Paho MQTT im Main Thread importieren!
try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
    print("✅ paho-mqtt erfolgreich im Main Thread importiert")
except ImportError as e:
    MQTT_AVAILABLE = False
    print(f"❌ paho-mqtt Import Fehler: {e}")

# Projektpfade hinzufügen
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(current_dir)
sys.path.append(parent_dir)

# Konfiguriere Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('UWBuddy-Orchestrator')

class UWBuddyOrchestrator:
    """
    Hauptorchestrator für das UWBuddy System
    """
    
    def __init__(self):
        self.running = True
        self.threads = {}
        self.message_queue = Queue()
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.robot_controller = None
        self.digital_twin = None
        self.mqtt_client = None
        
    def signal_handler(self, signum, frame):
        """Behandelt Shutdown-Signale"""
        logger.info("Shutdown-Signal erhalten. Stoppe alle Threads...")
        self.running = False
        
    def start_ble_service(self):
        """Startet den BLE Service mit echtem Controller"""
        def ble_worker():
            logger.info("BLE Service gestartet")
            try:
                # Import des BLE Controllers
                bleapi_path = os.path.join(parent_dir, 'bleapi')
                sys.path.append(bleapi_path)
                
                from elegoo_controller import ElegooTumbllerController
                
                self.robot_controller = ElegooTumbllerController()
                logger.info("BLE Controller initialisiert")
                
                while self.running:
                    if hasattr(self.robot_controller, 'connected') and self.robot_controller.connected:
                        logger.debug("BLE Service - Roboter verbunden")
                        
                        # Verarbeite Nachrichten aus der Queue für Roboter-Befehle
                        if not self.message_queue.empty():
                            try:
                                message_type, service, data = self.message_queue.get_nowait()
                                if message_type == "robot_command" and hasattr(self.robot_controller, 'send_command'):
                                    command = data.get('command', '')
                                    logger.info(f"Sende Roboter-Befehl: {command}")
                                    self.robot_controller.send_command(command)
                            except:
                                pass
                    else:
                        logger.debug("BLE Service - Warte auf Verbindung...")
                    
                    time.sleep(2)
                    
            except ImportError as e:
                logger.error(f"BLE Module nicht gefunden: {e}")
                logger.info("BLE Service läuft im Simulations-Modus")
                while self.running:
                    logger.debug("BLE Service (Simulation) läuft...")
                    time.sleep(2)
            except Exception as e:
                logger.error(f"Fehler im BLE Service: {e}")
                
        return threading.Thread(target=ble_worker, daemon=True)

    def start_mqtt_service(self):
        """Startet den MQTT Service mit Digital Twin"""
        def mqtt_worker():
            logger.info("MQTT Service gestartet")
            try:
                # Import der MQTT und Digital Twin Module
                from anchor_digital_twin import AnchorZoneDigitalTwin
                from location_mqtt import LocationMQTT
                
                # Digital Twin initialisieren
                self.digital_twin = AnchorZoneDigitalTwin(
                    anchor_center=(2.5, 2.5, 1.0),
                    zone_radius=10.0
                )
                
                # Tag IDs registrieren (anpassen an echte IDs!)
                self.digital_twin.register_tumbller("4c87")
                self.digital_twin.register_target_person("0cad")
                logger.info("Digital Twin initialisiert")
                
                # MQTT Client starten
                broker_ip = "orehek_wlan-usb-001.iot.private.hm.edu"  # Anpassen an echte Broker IP
                self.mqtt_client = LocationMQTT(broker_ip, 1883, "dwm/node/+/uplink/location")
                self.mqtt_client.set_location_callback(self.process_position)
                self.mqtt_client.start(broker_ip, 1883)
                logger.info(f"MQTT Client gestartet - Broker: {broker_ip}")
                
                while self.running:
                    if self.digital_twin:
                        summary = self.digital_twin.get_model_summary()
                        logger.debug(f"Digital Twin Status: {summary}")
                        
                        # Follow-Logic prüfen
                        if (self.digital_twin.tumbller_id and 
                            self.digital_twin.target_person_id):
                            distance = self.digital_twin.calculate_distance_between_entities(
                                self.digital_twin.tumbller_id,
                                self.digital_twin.target_person_id
                            )
                            if distance and distance > 2.0:
                                self.message_queue.put(("follow_command", "tumbller", {
                                    "distance": distance,
                                    "action": "follow"
                                }))
                    
                    time.sleep(1)
                    
            except ImportError as e:
                logger.error(f"MQTT/Digital Twin Module nicht gefunden: {e}")
                logger.info("MQTT Service läuft im Simulations-Modus")
                while self.running:
                    logger.debug("MQTT Service (Simulation) läuft...")
                    time.sleep(1.5)
            except Exception as e:
                logger.error(f"Fehler im MQTT Service: {e}")
                self.message_queue.put(("error", "mqtt", str(e)))
                
        return threading.Thread(target=mqtt_worker, daemon=True)
    
    def process_position(self, node_id, pos):
        """Verarbeitet UWB-Positionsdaten"""
        logger.info(f"📍 Position Update - Node {node_id}: x={pos.get('x', 0):.2f}, y={pos.get('y', 0):.2f}, z={pos.get('z', 0):.2f}")
        
        if self.digital_twin:
            self.digital_twin.update_entity_position(node_id, pos)
    
    def start_logic_service(self):
        """Startet den Logic Service"""
        def logic_worker():
            logger.info("Logic Service gestartet")
            try:
                while self.running:
                    # Verarbeite Nachrichten aus der Queue
                    if not self.message_queue.empty():
                        try:
                            message_type, service, data = self.message_queue.get_nowait()
                            logger.info(f"Logic verarbeitet: {message_type} von {service}")
                            
                            if message_type == "follow_command":
                                distance = data.get('distance', 0)
                                logger.info(f"🏃 Follow-Logic: Distanz {distance:.2f}m - Tumbller soll folgen")
                                
                                # Roboter-Befehl generieren
                                if distance > 3.0:
                                    command = "f"  # Forward
                                elif distance < 1.0:
                                    command = "s"  # Stop
                                else:
                                    command = "f"  # Slow forward
                                
                                self.message_queue.put(("robot_command", "ble", {
                                    "command": command,
                                    "reason": f"follow_distance_{distance:.1f}m"
                                }))
                                
                        except Exception as e:
                            logger.error(f"Fehler bei Message-Verarbeitung: {e}")
                    
                    time.sleep(0.5)
                    
            except Exception as e:
                logger.error(f"Fehler im Logic Service: {e}")
                self.message_queue.put(("error", "logic", str(e)))
                
        return threading.Thread(target=logic_worker, daemon=True)
    
    def start_tumbller_service(self):
        """Startet den Tumbller Service"""
        def tumbller_worker():
            logger.info("Tumbller Service gestartet")
            try:
                while self.running:
                    # Tumbller-spezifische Operationen
                    if self.digital_twin:
                        tumbller_state = self.digital_twin.get_tumbller_state()
                        if tumbller_state:
                            logger.debug(f"Tumbller Status: in_zone={tumbller_state.get('in_zone', False)}")
                    
                    time.sleep(2)
                    
            except Exception as e:
                logger.error(f"Fehler im Tumbller Service: {e}")
                self.message_queue.put(("error", "tumbller", str(e)))
                
        return threading.Thread(target=tumbller_worker, daemon=True)
    
    def monitor_system(self):
        """Überwacht das System und behandelt Nachrichten"""
        logger.info("System Monitor gestartet")
        
        while self.running:
            try:
                # Überprüfe Thread-Status
                dead_threads = []
                for name, thread in self.threads.items():
                    if not thread.is_alive() and self.running:
                        logger.warning(f"Thread {name} ist gestoppt!")
                        dead_threads.append(name)
                
                # Tote Threads aus der Liste entfernen
                for name in dead_threads:
                    del self.threads[name]
                
                # System-Status loggen
                active_threads = len([t for t in self.threads.values() if t.is_alive()])
                logger.debug(f"System Status: {active_threads} aktive Threads")
                
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Fehler im System Monitor: {e}")
    
    def start_all_services(self):
        """Startet alle Services"""
        logger.info("Starte alle UWBuddy Services...")
        
        # Starte alle Service-Threads
        self.threads['ble'] = self.start_ble_service()
        self.threads['mqtt'] = self.start_mqtt_service()
        self.threads['logic'] = self.start_logic_service()
        self.threads['tumbller'] = self.start_tumbller_service()
        
        # Starte alle Threads
        for name, thread in self.threads.items():
            thread.start()
            logger.info(f"{name.upper()} Thread gestartet")
    
    def run(self):
        """Hauptausführungsschleife"""
        # Signal Handler registrieren
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        logger.info("UWBuddy Orchestrator wird gestartet...")
        
        try:
            # Starte alle Services
            self.start_all_services()
            
            # Starte System Monitor
            self.monitor_system()
            
        except KeyboardInterrupt:
            logger.info("Keyboard Interrupt erhalten")
        except Exception as e:
            logger.error(f"Unerwarteter Fehler: {e}")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Ordnungsgemäßer Shutdown aller Services"""
        logger.info("Shutting down UWBuddy Orchestrator...")
        self.running = False
        
        # MQTT Client beenden
        if self.mqtt_client:
            try:
                self.mqtt_client.stop()
                logger.info("MQTT Client gestoppt")
            except:
                pass
        
        # Warte auf alle Threads
        for name, thread in self.threads.items():
            if thread.is_alive():
                logger.info(f"Warte auf {name} Thread...")
                thread.join(timeout=5)
                if thread.is_alive():
                    logger.warning(f"{name} Thread reagiert nicht auf Shutdown")
        
        # Executor beenden
        self.executor.shutdown(wait=True)
        logger.info("UWBuddy Orchestrator beendet")

def main():
    """Hauptfunktion"""
    orchestrator = UWBuddyOrchestrator()
    orchestrator.run()

if __name__ == "__main__":
    main()
