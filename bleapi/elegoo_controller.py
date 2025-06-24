#!/usr/bin/env python3
"""
Elegoo Tumbller BLE-Steuerung - Zurück zu ASCII mit verbesserter Logik
Installiere zuerst: pip install bleak keyboard
"""

import asyncio
import keyboard
import time
from bleak import BleakClient, BleakScanner

class ElegooTumbllerController:
    def __init__(self):
        self.device_name = "CPS-45"  # Dein umbenanntes Gerät
        self.write_characteristic = "0000ffe2-0000-1000-8000-00805f9b34fb"
        self.client = None
        self.connected = False
        self.running = True
        self.loop = None
        self.is_moving = False  # Bewegungsstatus verfolgen
        
    async def connect(self):
        """Verbindung zum Elegoo Tumbller herstellen"""
        print(f"Suche nach {self.device_name}...")
        
        try:
            device = await BleakScanner.find_device_by_name(self.device_name)
            if not device:
                print(f"❌ Gerät {self.device_name} nicht gefunden!")
                return False
                
            print(f"📱 Verbinde mit {self.device_name}...")
            self.client = BleakClient(device)
            await self.client.connect()
            self.connected = True
            print(f"✅ Erfolgreich verbunden mit {self.device_name}")
            return True
            
        except Exception as e:
            print(f"❌ Verbindungsfehler: {e}")
            return False
            
    async def send_command(self, command):
        """ASCII-Befehl senden (original Format)"""
        if not self.client or not self.connected:
            print("❌ Nicht verbunden!")
            return False
            
        try:
            # ASCII-Befehl als Byte senden (wie ursprünglich)
            await self.client.write_gatt_char(
                self.write_characteristic, 
                command.encode('ascii')
            )
            print(f"✅ Befehl '{command}' gesendet")
            return True
        except Exception as e:
            print(f"❌ Sendefehler: {e}")
            return False
            
    async def stop_and_move(self, direction):
        """Erst stoppen, dann bewegen (verhindert Umkippen)"""
        if self.is_moving:
            await self.send_command('s')  # Erst stoppen
            await asyncio.sleep(0.1)      # Kurze Pause
            
        await self.send_command(direction)  # Dann neuen Befehl
        self.is_moving = True
        
    async def stop_robot(self):
        """Robot explizit stoppen"""
        await self.send_command('s')
        self.is_moving = False
        print("🛑 Robot gestoppt")
        
    async def forward(self):
        """Vorwärts fahren"""
        await self.stop_and_move('f')
        print("⬆️ Vorwärts")
        
    async def backward(self):
        """Rückwärts fahren"""
        await self.stop_and_move('b')
        print("⬇️ Rückwärts")
        
    async def left(self):
        """Links drehen"""
        await self.stop_and_move('l')
        print("⬅️ Links")
        
    async def right(self):
        """Rechts drehen"""
        await self.stop_and_move('i')
        print("➡️ Rechts")
        
    async def toggle_led(self):
        """LED ein/ausschalten"""
        await self.send_command('a')
        print("💡 LED umgeschaltet")
        
    async def pause_robot(self):
        """Roboter pausieren (sanfter als stoppen)"""
        if self.is_moving:
            await self.send_command('s')
            self.is_moving = False
            print("⏸️ Roboter pausiert")
        
    def schedule_coroutine(self, coro):
        """Thread-sichere Ausführung von Coroutines"""
        if self.loop and not self.loop.is_closed():
            asyncio.run_coroutine_threadsafe(coro, self.loop)
        
    def setup_hotkeys(self):
        """Tastatur-Hotkeys einrichten"""
        keyboard.add_hotkey('up', lambda: self.schedule_coroutine(self.forward()))
        keyboard.add_hotkey('down', lambda: self.schedule_coroutine(self.backward()))
        keyboard.add_hotkey('left', lambda: self.schedule_coroutine(self.left()))
        keyboard.add_hotkey('right', lambda: self.schedule_coroutine(self.right()))
        keyboard.add_hotkey('space', lambda: self.schedule_coroutine(self.pause_robot()))
        keyboard.add_hotkey('l', lambda: self.schedule_coroutine(self.toggle_led()))
        keyboard.add_hotkey('s', lambda: self.schedule_coroutine(self.stop_robot()))
        keyboard.add_hotkey('esc', self.quit)
        keyboard.add_hotkey('q', self.quit)
        
    def quit(self):
        """Programm beenden"""
        print("\n🛑 Beende Programm...")
        self.running = False
        
    async def disconnect(self):
        """Verbindung trennen"""
        if self.client and self.connected:
            await self.stop_robot()
            await self.client.disconnect()
            self.connected = False
            print("📱 Verbindung getrennt")
            
    def print_instructions(self):
        """Bedienungsanleitung anzeigen"""
        print("\n" + "="*50)
        print("🤖 ELEGOO TUMBLLER - ASCII BEFEHLE")
        print("="*50)
        print("Steuerung:")
        print("  ⬆️  Pfeil HOCH    = Vorwärts (f)")
        print("  ⬇️  Pfeil RUNTER  = Rückwärts (b)") 
        print("  ⬅️  Pfeil LINKS   = Links drehen (l)")
        print("  ➡️  Pfeil RECHTS  = Rechts drehen (r)")
        print("  ⏸️  LEERTASTE     = Pausieren (s)")
        print("  🛑 S             = Explizit stoppen (s)")
        print("  💡 L             = LED ein/aus (a)")
        print("  🚪 ESC oder Q     = Beenden")
        print("="*50)
        print("⚡ Verwendet originale ASCII-Befehle mit Anti-Umkipp-Logik")
        print("Drücke eine Taste zum Steuern...")

async def main():
    """Hauptprogramm"""
    controller = ElegooTumbllerController()
    controller.loop = asyncio.get_running_loop()
    
    if not await controller.connect():
        input("Drücke Enter zum Beenden...")
        return
        
    controller.setup_hotkeys()
    controller.print_instructions()
    
    try:
        while controller.running and controller.connected:
            await asyncio.sleep(0.1)
    except KeyboardInterrupt:
        print("\n🛑 Programm durch Strg+C beendet")
    finally:
        keyboard.unhook_all_hotkeys()
        await controller.disconnect()
        print("👋 Auf Wiedersehen!")

if __name__ == "__main__":
    print("🚀 Starte Elegoo Tumbller Controller (ASCII-Befehle)...")
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"💥 Unerwarteter Fehler: {e}")
        input("Drücke Enter zum Beenden...")
