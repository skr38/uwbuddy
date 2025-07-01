import math
import time
import threading

class TumbllerSteeringController:
    """
    Intelligente Steuerungslogik für den Tumbller mit Orientierungsschätzung
    """
    
    def __init__(self, digital_twin, message_queue):
        self.dt = digital_twin
        self.message_queue = message_queue
        self.running = False
        self.thread = None
        
        # Steuerungsparameter
        self.min_distance = 0.3
        self.max_distance = 0.8
        self.angle_threshold = 0.5  # Größere Toleranz wegen Ungenauigkeit
        self.command_interval = 1.0
        self.last_command_time = 0
        
        # Orientierungsschätzung
        self.estimated_yaw = 0.0  # Geschätzte aktuelle Orientierung
        self.last_position = None
        self.position_history = []  # Letzte Positionen für Bewegungsrichtung
        self.last_command = None
        self.command_start_time = 0
        self.calibration_mode = False
        self.calibration_start_pos = None
        self.calibration_command = None
        
        # Kalibrierungsparameter
        self.calibration_interval = 30.0  # Alle 30 Sekunden kalibrieren
        self.last_calibration = 0
        self.min_movement_for_calibration = 0.3  # Mindestbewegung für Kalibrierung
        
        print(f"Steering Controller mit Orientierungsschätzung initialisiert:")
        print(f"  Digital Twin: {id(self.dt)}")
        print(f"  Message Queue: {id(self.message_queue)}")
        
    def _update_position_history(self, position):
        """Aktualisiert die Positionshistorie für Bewegungsrichtung"""
        current_time = time.time()
        self.position_history.append({
            'position': position.copy(),
            'timestamp': current_time
        })
        
        # Behalte nur die letzten 10 Sekunden
        self.position_history = [
            entry for entry in self.position_history
            if current_time - entry['timestamp'] <= 10.0
        ]
    
    def _estimate_orientation_from_movement(self):
        """Schätzt Orientierung basierend auf Bewegungsrichtung"""
        if len(self.position_history) < 2:
            return None
            
        # Nimm die letzten beiden Positionen - KORRIGIERT!
        recent_positions = self.position_history[-2:]
        
        pos1 = recent_positions[0]['position']  # KORRIGIERT: [0] statt ['position']
        pos2 = recent_positions[1]['position']  # KORRIGIERT: [1] statt ['position']
        
        dx = pos2['x'] - pos1['x']
        dy = pos2['y'] - pos1['y']
        
        # Nur wenn sich der Tumbller ausreichend bewegt hat
        movement_distance = math.sqrt(dx*dx + dy*dy)
        if movement_distance < 0.1:  # Mindestbewegung 10cm
            return None
            
        # Bewegungsrichtung berechnen
        movement_angle = math.atan2(dy, dx)
        return movement_angle
    
    def _should_calibrate(self):
        """Prüft ob eine Kalibrierung nötig ist"""
        current_time = time.time()
        return (current_time - self.last_calibration) > self.calibration_interval
    
    def _start_calibration(self, tumbller_pos):
        """Startet Kalibrierungsmodus"""
        self.calibration_mode = True
        self.calibration_start_pos = tumbller_pos.copy()
        self.calibration_command = "f"  # Fahre vorwärts für Kalibrierung
        self.command_start_time = time.time()
        print("Starte Orientierungskalibrierung - fahre vorwärts...")
        return "f", "kalibrierung_vorwaerts"
    
    def _finish_calibration(self, tumbller_pos):
        """Beendet Kalibrierungsmodus und aktualisiert Orientierung"""
        if not self.calibration_start_pos:
            return
            
        dx = tumbller_pos['x'] - self.calibration_start_pos['x']
        dy = tumbller_pos['y'] - self.calibration_start_pos['y']
        
        movement_distance = math.sqrt(dx*dx + dy*dy)
        
        if movement_distance > self.min_movement_for_calibration:
            # Aktualisiere geschätzte Orientierung
            self.estimated_yaw = math.atan2(dy, dx)
            print(f"Kalibrierung abgeschlossen - neue Orientierung: {math.degrees(self.estimated_yaw):.0f}°")
            self.last_calibration = time.time()
        else:
            print("Kalibrierung fehlgeschlagen - zu wenig Bewegung")
            
        self.calibration_mode = False
        self.calibration_start_pos = None
        self.calibration_command = None
    
    def calculate_steering_command(self):
        """Berechnet optimalen Steuerungsbefehl mit Orientierungsschätzung"""
        current_time = time.time()
        
        # Rate-Limiting
        if current_time - self.last_command_time < self.command_interval:
            return None, "rate_limited"
        
        # Hole Positionen
        tumbller_state = self.dt.get_entity_state("4c87")
        person_state = self.dt.get_entity_state("0cad")
        
        if not (tumbller_state and person_state and 
                'position' in tumbller_state and 'position' in person_state):
            return None, "missing_positions"
        
        tumbller_pos = tumbller_state['position']
        target_pos = person_state['position']
        
        # Aktualisiere Positionshistorie
        self._update_position_history(tumbller_pos)
        
        # Kalibrierungsmodus
        if self.calibration_mode:
            # Prüfe ob Kalibrierung lange genug läuft
            if current_time - self.command_start_time > 3.0:  # 3 Sekunden vorwärts
                self._finish_calibration(tumbller_pos)
                return "s", "kalibrierung_stopp"
            else:
                return None, "kalibrierung_aktiv"
        
        # Prüfe ob Kalibrierung nötig ist
        if self._should_calibrate():
            return self._start_calibration(tumbller_pos)
        
        # Distanz und Zielwinkel berechnen
        dx = target_pos['x'] - tumbller_pos['x']
        dy = target_pos['y'] - tumbller_pos['y']
        distance = math.sqrt(dx*dx + dy*dy)
        target_angle = math.atan2(dy, dx)
        
        # Orientierung schätzen
        movement_orientation = self._estimate_orientation_from_movement()
        if movement_orientation is not None:
            # Aktualisiere Schätzung basierend auf Bewegung
            self.estimated_yaw = movement_orientation
            
        # Winkeldifferenz berechnen
        angle_diff = self._normalize_angle(target_angle - self.estimated_yaw)
        
        # Entscheidung
        command, reason = self._decide_action(distance, angle_diff, target_angle)
        
        if command:
            self.last_command_time = current_time
            self.last_command = command
            
        return command, reason
    
    def _normalize_angle(self, angle):
        return math.atan2(math.sin(angle), math.cos(angle))
    
    def _decide_action(self, distance, angle_diff, target_angle):
        if distance < self.min_distance:
            return "s", f"zu_nah_{distance:.1f}m"
        
        if distance > self.max_distance:
            if abs(angle_diff) > self.angle_threshold:
                if angle_diff > 0:
                    return "l", f"links_drehen_{math.degrees(angle_diff):.0f}grad_zu_{math.degrees(target_angle):.0f}grad"
                else:
                    return "r", f"rechts_drehen_{math.degrees(abs(angle_diff)):.0f}grad_zu_{math.degrees(target_angle):.0f}grad"
            else:
                return "f", f"folgen_{distance:.1f}m_richtung_{math.degrees(target_angle):.0f}grad"
        
        return "s", f"perfekte_distanz_{distance:.1f}m"
    
    def start(self, interval=1.0):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, args=(interval,), daemon=True)
        self.thread.start()
        print("Tumbller Steering Controller mit Orientierungsschätzung gestartet")
    
    def _send_ble_command(self, command, reason):
        """Sendet BLE-Befehl über die Message Queue"""
        try:
            self.message_queue.put(("robot_command", "ble", {
                "command": command,
                "reason": reason
            }))
            return True
        except Exception as e:
            print(f"Fehler beim Senden des Steering-Befehls: {e}")
            return False
    
    def _run(self, interval):
        while self.running:
            try:
                command, reason = self.calculate_steering_command()
                
                if command and reason not in ["rate_limited", "missing_positions", "kalibrierung_aktiv"]:
                    # Debug Info
                    tumbller_state = self.dt.get_entity_state("4c87")
                    person_state = self.dt.get_entity_state("0cad")
                    
                    if tumbller_state and person_state:
                        tpos = tumbller_state['position']
                        ppos = person_state['position']
                        dx = ppos['x'] - tpos['x']
                        dy = ppos['y'] - tpos['y']
                        distance = math.sqrt(dx*dx + dy*dy)
                        target_angle = math.atan2(dy, dx)
                        
                        print(f"Smart Steering: Distanz {distance:.2f}m, "
                              f"Zielrichtung {math.degrees(target_angle):.0f}°, "
                              f"Geschätzte Orientierung {math.degrees(self.estimated_yaw):.0f}°")
                    
                    # Action Namen
                    action_names = {
                        'f': 'VORWÄRTS',
                        's': 'STOPPEN',
                        'l': 'LINKS DREHEN',
                        'r': 'RECHTS DREHEN'
                    }
                    action_name = action_names.get(command, f'UNKNOWN({command})')
                    print(f"Steering Entscheidung: {action_name} ({reason})")
                    
                    # Befehl über Message Queue senden
                    success = self._send_ble_command(command, reason)
                    if not success:
                        print("Warnung: Konnte Steering-Befehl nicht senden")
                
            except Exception as e:
                print(f"Fehler im Steering Controller: {e}")
            
            time.sleep(interval)
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        print("Tumbller Steering Controller gestoppt")
