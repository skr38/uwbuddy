import math
import time
import threading

class TumbllerSteeringController:
    """
    Intelligente Steuerungslogik für den Tumbller mit zeitbasierten Befehlen
    """
    
    def __init__(self, digital_twin, message_queue):
        self.dt = digital_twin
        self.message_queue = message_queue
        self.running = False
        self.thread = None
        
        # Steuerungsparameter
        self.min_distance = 0.2
        self.max_distance = 0.8
        self.angle_threshold = 0.2  # Kleinere Toleranz für präzisere Steuerung
        self.command_interval = 0.1  # Häufigere Befehle für bessere Kontrolle
        self.last_command_time = 0
        
        # Zeitbasierte Befehlsparameter
        self.turn_speed = 1.5  # Radiant pro Sekunde (geschätzt)
        self.max_turn_duration = 1.0  # Maximale Drehzeit pro Befehl
        self.max_forward_duration = 0.8  # Maximale Vorwärtszeit pro Befehl
        
        # Orientierungsschätzung
        self.estimated_yaw = 0.0
        self.position_history = []
        self.last_command = None
        self.command_start_time = 0
        self.calibration_mode = False
        self.calibration_start_pos = None
        
        # Kalibrierungsparameter
        self.calibration_interval = 45.0  # Alle 45 Sekunden kalibrieren
        self.last_calibration = 0
        self.min_movement_for_calibration = 0.2
        
        # Aktive Befehlsverfolgung
        self.active_command = None
        self.active_command_end_time = 0
        
        print(f"Steering Controller mit zeitbasierten Befehlen initialisiert:")
        print(f"  Digital Twin: {id(self.dt)}")
        print(f"  Message Queue: {id(self.message_queue)}")
        
    def _update_position_history(self, position):
        """Aktualisiert die Positionshistorie"""
        current_time = time.time()
        self.position_history.append({
            'position': position.copy(),
            'timestamp': current_time
        })
        
        # Behalte nur die letzten 15 Sekunden
        self.position_history = [
            entry for entry in self.position_history
            if current_time - entry['timestamp'] <= 15.0
        ]
    
    def _estimate_orientation_from_movement(self):
        """Schätzt Orientierung basierend auf Bewegungsrichtung"""
        if len(self.position_history) < 3:
            return None
            
        # Verwende die letzten 3 Positionen für stabilere Schätzung
        recent_positions = self.position_history[-3:]
        
        # Berechne Durchschnittsbewegung
        total_dx = 0
        total_dy = 0
        total_distance = 0
        
        for i in range(len(recent_positions) - 1):
            pos1 = recent_positions[i]['position']
            pos2 = recent_positions[i + 1]['position']
            
            dx = pos2['x'] - pos1['x']
            dy = pos2['y'] - pos1['y']
            distance = math.sqrt(dx*dx + dy*dy)
            
            if distance > 0.05:  # Mindestbewegung 5cm
                total_dx += dx
                total_dy += dy
                total_distance += distance
        
        if total_distance < 0.1:  # Zu wenig Gesamtbewegung
            return None
            
        # Durchschnittliche Bewegungsrichtung
        movement_angle = math.atan2(total_dy, total_dx)
        return movement_angle
    
    def _should_calibrate(self):
        """Prüft ob eine Kalibrierung nötig ist"""
        current_time = time.time()
        return (current_time - self.last_calibration) > self.calibration_interval
    
    def _start_calibration(self, tumbller_pos):
        """Startet Kalibrierungsmodus"""
        self.calibration_mode = True
        self.calibration_start_pos = tumbller_pos.copy()
        self.command_start_time = time.time()
        print("Starte Orientierungskalibrierung - fahre 2s vorwärts...")
        return ("f", 2.0), "kalibrierung_vorwaerts_2s"
    
    def _finish_calibration(self, tumbller_pos):
        """Beendet Kalibrierungsmodus"""
        if not self.calibration_start_pos:
            return
            
        dx = tumbller_pos['x'] - self.calibration_start_pos['x']
        dy = tumbller_pos['y'] - self.calibration_start_pos['y']
        
        movement_distance = math.sqrt(dx*dx + dy*dy)
        
        if movement_distance > self.min_movement_for_calibration:
            self.estimated_yaw = math.atan2(dy, dx)
            print(f"Kalibrierung erfolgreich - neue Orientierung: {math.degrees(self.estimated_yaw):.0f}°")
            self.last_calibration = time.time()
        else:
            print("Kalibrierung fehlgeschlagen - zu wenig Bewegung")
            
        self.calibration_mode = False
        self.calibration_start_pos = None
    
    def _send_timed_command(self, command, duration, reason):
        """Sendet einen zeitbasierten Befehl"""
        current_time = time.time()
        
        # Sofort den Befehl senden
        success = self._send_ble_command(command, reason)
        if not success:
            return False
            
        # Merke aktiven Befehl
        self.active_command = command
        self.active_command_end_time = current_time + duration
        
        # Automatischer Stopp nach der Zeit
        def auto_stop():
            time.sleep(duration)
            if self.active_command == command:  # Nur stoppen wenn noch der gleiche Befehl aktiv
                self._send_ble_command("s", f"auto_stop_nach_{duration:.1f}s")
                self.active_command = None
                self.active_command_end_time = 0
        
        threading.Thread(target=auto_stop, daemon=True).start()
        return True
    
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
    
    def _calculate_turn_duration(self, angle_diff):
        """Berechnet optimale Drehzeit basierend auf Winkeldifferenz"""
        # Geschätzte Drehzeit basierend auf Winkel
        estimated_duration = abs(angle_diff) / self.turn_speed
        
        # Begrenze auf Maximum und Minimum
        duration = max(0.2, min(self.max_turn_duration, estimated_duration))
        return duration
    
    def _calculate_forward_duration(self, distance):
        """Berechnet optimale Vorwärtszeit basierend auf Distanz"""
        # Geschätzte Geschwindigkeit: 1 m/s
        estimated_speed = 1.0
        estimated_duration = min(distance / estimated_speed, self.max_forward_duration)
        
        # Mindestens 0.3s, maximal max_forward_duration
        duration = max(0.3, min(self.max_forward_duration, estimated_duration))
        return duration
    
    def calculate_steering_command(self):
        """Berechnet optimalen zeitbasierten Steuerungsbefehl"""
        current_time = time.time()
        
        # Prüfe ob noch ein Befehl aktiv ist
        if self.active_command and current_time < self.active_command_end_time:
            return None, "befehl_noch_aktiv"
        
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
            if current_time - self.command_start_time > 3.0:
                self._finish_calibration(tumbller_pos)
                return "s", "kalibrierung_beendet"
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
            self.estimated_yaw = movement_orientation
            
        # Winkeldifferenz berechnen
        angle_diff = self._normalize_angle(target_angle - self.estimated_yaw)
        
        # Entscheidung mit zeitbasierten Befehlen
        command_tuple, reason = self._decide_timed_action(distance, angle_diff, target_angle)
        
        if command_tuple:
            self.last_command_time = current_time
            
        return command_tuple, reason
    
    def _normalize_angle(self, angle):
        return math.atan2(math.sin(angle), math.cos(angle))
    
    def _decide_timed_action(self, distance, angle_diff, target_angle):
        """Entscheidet zeitbasierte Aktionen"""
        if distance < self.min_distance:
            return "s", f"zu_nah_{distance:.1f}m"
        
        if distance > self.max_distance:
            # Prüfe Richtung zuerst
            if abs(angle_diff) > self.angle_threshold:
                # Berechne optimale Drehzeit
                turn_duration = self._calculate_turn_duration(angle_diff)
                
                if angle_diff > 0:
                    return ("l", turn_duration), f"links_drehen_{turn_duration:.1f}s_um_{math.degrees(angle_diff):.0f}grad"
                else:
                    return ("i", turn_duration), f"rechts_drehen_{turn_duration:.1f}s_um_{math.degrees(abs(angle_diff)):.0f}grad"
            else:
                # Richtige Richtung - fahre vorwärts
                forward_duration = self._calculate_forward_duration(distance)
                return ("f", forward_duration), f"folgen_{forward_duration:.1f}s_distanz_{distance:.1f}m"
        
        return "s", f"perfekte_distanz_{distance:.1f}m"
    
    def start(self, interval=0.5):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, args=(interval,), daemon=True)
        self.thread.start()
        print("Tumbller Steering Controller mit zeitbasierten Befehlen gestartet")
    
    def _run(self, interval):
        while self.running:
            try:
                command_result = self.calculate_steering_command()
                
                if command_result[0] and command_result[1] not in ["rate_limited", "missing_positions", "kalibrierung_aktiv", "befehl_noch_aktiv"]:
                    command_tuple, reason = command_result
                    
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
                    
                    # Führe zeitbasierten Befehl aus
                    if isinstance(command_tuple, tuple):
                        command, duration = command_tuple
                        action_names = {
                            'f': 'VORWÄRTS',
                            's': 'STOPPEN',
                            'l': 'LINKS DREHEN',
                            'i': 'RECHTS DREHEN'
                        }
                        action_name = action_names.get(command, f'UNKNOWN({command})')
                        print(f"Steering Entscheidung: {action_name} für {duration:.1f}s ({reason})")
                        
                        success = self._send_timed_command(command, duration, reason)
                        if not success:
                            print("Warnung: Konnte zeitbasierten Steering-Befehl nicht senden")
                    else:
                        # Einfacher Befehl (meist Stopp)
                        command = command_tuple
                        action_names = {
                            'f': 'VORWÄRTS',
                            's': 'STOPPEN',
                            'l': 'LINKS DREHEN',
                            'i': 'RECHTS DREHEN'
                        }
                        action_name = action_names.get(command, f'UNKNOWN({command})')
                        print(f"Steering Entscheidung: {action_name} ({reason})")
                        
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
