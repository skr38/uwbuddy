#!/usr/bin/env python3

import threading
import time
import logging
import sys
import os
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import signal
import asyncio

# KRITISCH: Paho MQTT im Main Thread importieren!
try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
    print("MQTT erfolgreich im Main Thread importiert")
except ImportError as e:
    MQTT_AVAILABLE = False
    print(f"paho-mqtt Import Fehler: {e}")

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
            print("BLE Service gestartet")
            try:
                from elegoo_controller import ElegooTumbllerController

                self.robot_controller = ElegooTumbllerController()
                print("BLE Controller initialisiert")

                # Asyncio Event Loop für BLE-Verbindung
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Verbindung herstellen
                print("Versuche BLE-Verbindung herzustellen...")
                connected = False
                try:
                    connected = loop.run_until_complete(self.robot_controller.connect())
                    if connected:
                        print("BLE Controller erfolgreich verbunden")
                        self.robot_controller.connected = True
                    else:
                        print("BLE Controller Verbindung fehlgeschlagen - Simulations-Modus")
                        self.robot_controller.connected = False
                except Exception as e:
                    print(f"BLE Verbindungsfehler: {e}")
                    print("BLE Service läuft im Simulations-Modus")
                    self.robot_controller.connected = False
                    connected = False

                while self.running:
                    # Verarbeite Nachrichten aus der Queue für Roboter-Befehle
                    try:
                        if not self.message_queue.empty():
                            message_type, service, data = self.message_queue.get_nowait()
                            if message_type == "robot_command":
                                command = data.get('command', '')
                                reason = data.get('reason', 'unknown')
                                
                                command_names = {
                                    'f': 'FORWARD',
                                    's': 'STOP',
                                    'l': 'LEFT',
                                    'i': 'RIGHT',
                                    'b': 'BACKWARD'
                                }
                                command_name = command_names.get(command, f'UNKNOWN({command})')
                                
                                if connected and hasattr(self.robot_controller, 'send_command'):
                                    print(f"Bluetooth -> Tumbller: {command_name} (Grund: {reason})")
                                    try:
                                        # Async Befehl senden
                                        loop.run_until_complete(self.robot_controller.send_command(command))
                                    except Exception as e:
                                        print(f"Bluetooth Sendefehler: {e}")
                                        connected = False
                                        self.robot_controller.connected = False
                                else:
                                    print(f"Bluetooth (SIM) -> Tumbller: {command_name} (Grund: {reason})")
                    except Exception as e:
                        pass
                    
                    time.sleep(0.1)  # Schnelle Queue-Verarbeitung

            except ImportError as e:
                print(f"BLE Module nicht gefunden: {e}")
                print("BLE Service läuft im Simulations-Modus")
                
                # Simulation mit Ausgabe
                while self.running:
                    try:
                        if not self.message_queue.empty():
                            message_type, service, data = self.message_queue.get_nowait()
                            if message_type == "robot_command":
                                command = data.get('command', '')
                                reason = data.get('reason', 'unknown')
                                
                                command_names = {
                                    'f': 'FORWARD',
                                    's': 'STOP',
                                    'l': 'LEFT',
                                    'r': 'RIGHT',
                                    'b': 'BACKWARD'
                                }
                                command_name = command_names.get(command, f'UNKNOWN({command})')
                                print(f"Bluetooth (SIM) -> Tumbller: {command_name} (Grund: {reason})")
                    except Exception as e:
                        pass
                    time.sleep(0.1)

        return threading.Thread(target=ble_worker, daemon=True)

    def start_mqtt_service(self):
        """Startet den MQTT Service mit Digital Twin und Steering Controller"""
        def mqtt_worker():
            print("MQTT Service gestartet")
            try:
                from anchor_digital_twin import AnchorZoneDigitalTwin
                from location_mqtt import LocationMQTT
                from tumbller_steering_controller import TumbllerSteeringController
                
                # Digital Twin initialisieren
                self.digital_twin = AnchorZoneDigitalTwin(
                    anchor_center=(2.5, 2.5, 1.0),
                    zone_radius=10.0
                )
                
                # Tag IDs registrieren
                self.digital_twin.register_tumbller("4c87")
                self.digital_twin.register_target_person("0cad")
                print("Digital Twin initialisiert")
                print("Tracking: Tumbller (4c87), Target Person (0cad)")
    
                # MQTT Client starten
                broker_ip = "orehek_wlan-usb-001.iot.private.hm.edu"
                self.mqtt_client = LocationMQTT(broker_ip, 1883, "dwm/node/+/uplink/location")
                self.mqtt_client.set_location_callback(self.process_position)
                self.mqtt_client.start(broker_ip, 1883)
                print(f"MQTT Client gestartet - Broker: {broker_ip}")
    
                # Steering Controller mit direkter Message Queue Referenz
                steering_controller = TumbllerSteeringController(
                    self.digital_twin,
                    self.message_queue  # Direkte Referenz zur Message Queue
                )
                steering_controller.start(interval=0.5)
                print("Steering Controller mit Message Queue gestartet")
                
                # Hauptschleife
                while self.running:
                    if not self.mqtt_client or not self.mqtt_client.is_connected():
                        print("MQTT Verbindung verloren - versuche Reconnect...")
                        time.sleep(5)
                    time.sleep(1)
    
            except ImportError as e:
                print(f"MQTT/Digital Twin Module nicht gefunden: {e}")
                print("MQTT Service läuft im Simulations-Modus")
                while self.running:
                    time.sleep(1.5)
    
            except Exception as e:
                print(f"Fehler im MQTT Service: {e}")
    
        return threading.Thread(target=mqtt_worker, daemon=True)


    def process_position(self, node_id, pos):
        """Verarbeitet UWB-Positionsdaten"""
        # Nur für getrackte Nodes ausgeben
        if node_id in ["4c87", "0cad"]:
            device_names = {"4c87": "Tumbller", "0cad": "Target Person"}
            device_name = device_names.get(node_id, node_id)
            print(f"{device_name} ({node_id}): x={pos.get('x', 0):.3f}m, y={pos.get('y', 0):.3f}m, z={pos.get('z', 0):.3f}m")
        
        # Position an Digital Twin weiterleiten
        if self.digital_twin:
            self.digital_twin.update_entity_position(node_id, pos)

    def start_logic_service(self):
        """Startet den Logic Service mit verbesserter Ausgabe"""
        def logic_worker():
            print("Logic Service gestartet")
            try:
                while self.running:
                    # Verarbeite Nachrichten aus der Queue
                    if not self.message_queue.empty():
                        try:
                            message_type, service, data = self.message_queue.get_nowait()
                            
                            if message_type == "follow_command":
                                distance = data.get('distance', 0)
                                print(f"Follow-Logic: Distanz {distance:.2f}m zwischen Tumbller und Person")
                                
                                # Roboter-Befehl generieren
                                if distance > 3.0:
                                    command = "f"  # Forward
                                    action = "FOLGEN (weit entfernt)"
                                elif distance < 1.0:
                                    command = "s"  # Stop
                                    action = "STOPPEN (zu nah)"
                                else:
                                    command = "f"  # Slow forward
                                    action = "LANGSAM FOLGEN"
                                
                                print(f"Entscheidung: {action}")
                                
                                self.message_queue.put(("robot_command", "ble", {
                                    "command": command,
                                    "reason": f"follow_distance_{distance:.1f}m"
                                }))
                                
                        except Exception as e:
                            logger.error(f"Fehler bei Message-Verarbeitung: {e}")
                    
                    time.sleep(0.5)
                    
            except Exception as e:
                logger.error(f"Fehler im Logic Service: {e}")

        return threading.Thread(target=logic_worker, daemon=True)

    def start_tumbller_service(self):
        """Startet den Tumbller Service"""
        def tumbller_worker():
            print("Tumbller Service gestartet")
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
        print("System Monitor gestartet")
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

                # System-Status loggen (nur alle 30 Sekunden)
                if int(time.time()) % 30 == 0:
                    active_threads = len([t for t in self.threads.values() if t.is_alive()])
                    print(f"System Status: {active_threads} aktive Threads")
                    
                    # Digital Twin Summary ausgeben
                    if self.digital_twin:
                        summary = self.digital_twin.get_model_summary()
                        if summary.get('tumbller_to_target_distance'):
                            print(f"Digital Twin: {summary['total_entities']} Entities, Distanz: {summary['tumbller_to_target_distance']:.2f}m")

                time.sleep(1)

            except Exception as e:
                logger.error(f"Fehler im System Monitor: {e}")

    def start_all_services(self):
        """Startet alle Services"""
        print("Starte alle UWBuddy Services...")

        # Starte alle Service-Threads
        self.threads['ble'] = self.start_ble_service()
        self.threads['mqtt'] = self.start_mqtt_service()
        self.threads['logic'] = self.start_logic_service()
        self.threads['tumbller'] = self.start_tumbller_service()

        # Starte alle Threads
        for name, thread in self.threads.items():
            thread.start()
            print(f"{name.upper()} Thread gestartet")

    def run(self):
        """Hauptausführungsschleife"""
        # Signal Handler registrieren
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        print("UWBuddy Orchestrator wird gestartet...")

        try:
            # Starte alle Services
            self.start_all_services()

            # Starte System Monitor
            self.monitor_system()

        except KeyboardInterrupt:
            print("Keyboard Interrupt erhalten")
        except Exception as e:
            logger.error(f"Unerwarteter Fehler: {e}")
        finally:
            self.shutdown()

    def shutdown(self):
        """Ordnungsgemäßer Shutdown aller Services"""
        print("Shutting down UWBuddy Orchestrator...")
        self.running = False

        # MQTT Client beenden
        if self.mqtt_client:
            try:
                self.mqtt_client.stop()
                print("MQTT Client gestoppt")
            except:
                pass

        # Warte auf alle Threads
        for name, thread in self.threads.items():
            if thread.is_alive():
                print(f"Warte auf {name} Thread...")
                thread.join(timeout=5)
                if thread.is_alive():
                    logger.warning(f"{name} Thread reagiert nicht auf Shutdown")

        # Executor beenden
        self.executor.shutdown(wait=True)
        print("UWBuddy Orchestrator beendet")

def main():
    """Hauptfunktion"""
    orchestrator = UWBuddyOrchestrator()
    orchestrator.run()

if __name__ == "__main__":
    main()
