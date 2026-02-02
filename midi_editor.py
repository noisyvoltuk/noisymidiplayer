#!/usr/bin/env python3
"""
4-Track MIDI Editor for Linux
Pure Python with tkinter - flexible MIDI routing
Can route to FluidSynth, external MIDI devices, or mix both
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import json
from dataclasses import dataclass
from typing import List, Optional

# Try to import mido for MIDI output
try:
    import mido
    from mido import Message
    MIDO_AVAILABLE = True
except ImportError:
    MIDO_AVAILABLE = False
    print("mido not installed. Install with: pip3 install mido python-rtmidi")
    print("Running in demo mode without MIDI output.")

# Constants
NOTE_RANGE = 48  # 4 octaves (C3 to B6)
LOWEST_NOTE = 48  # C3
BEATS = 16
BEAT_SUBDIVISIONS = 4  # 16th notes
CANVAS_WIDTH = 1000
CANVAS_HEIGHT = 500

# Colors (hex)
TRACK_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444']
BG_COLOR = '#1a1a1a'
GRID_COLOR = '#333333'
MEASURE_LINE_COLOR = '#555555'

# GM MIDI Instruments (General MIDI standard)
GM_INSTRUMENTS = {
    "Piano": 0, "Bright Piano": 1, "Electric Grand": 2, "Honky-tonk": 3,
    "Electric Piano 1": 4, "Electric Piano 2": 5, "Harpsichord": 6, "Clavinet": 7,
    "Celesta": 8, "Glockenspiel": 9, "Music Box": 10, "Vibraphone": 11,
    "Marimba": 12, "Xylophone": 13, "Tubular Bells": 14, "Dulcimer": 15,
    "Organ": 16, "Rock Organ": 18, "Church Organ": 19, "Reed Organ": 20,
    "Accordion": 21, "Harmonica": 22, "Bandoneon": 23,
    "Nylon Guitar": 24, "Steel Guitar": 25, "Jazz Guitar": 26, "Clean Guitar": 27,
    "Muted Guitar": 28, "Overdrive Guitar": 29, "Distortion Guitar": 30,
    "Acoustic Bass": 32, "Fingered Bass": 33, "Picked Bass": 34, "Fretless Bass": 35,
    "Slap Bass 1": 36, "Slap Bass 2": 37, "Synth Bass 1": 38, "Synth Bass 2": 39,
    "Violin": 40, "Viola": 41, "Cello": 42, "Contrabass": 43,
    "Strings": 48, "Slow Strings": 49, "Synth Strings 1": 50, "Synth Strings 2": 51,
    "Choir Aahs": 52, "Voice Oohs": 53, "Synth Voice": 54,
    "Trumpet": 56, "Trombone": 57, "Tuba": 58, "Muted Trumpet": 59,
    "French Horn": 60, "Brass Section": 61, "Synth Brass 1": 62, "Synth Brass 2": 63,
    "Soprano Sax": 64, "Alto Sax": 65, "Tenor Sax": 66, "Baritone Sax": 67,
    "Oboe": 68, "English Horn": 69, "Bassoon": 70, "Clarinet": 71,
    "Flute": 73, "Recorder": 74, "Pan Flute": 75, "Synth Lead": 80,
    "Pad": 88, "Drums": 128  # Channel 10 is typically drums
}

@dataclass
class Note:
    pitch: int
    start: float  # In beats
    duration: float  # In beats
    velocity: int = 100

class Track:
    def __init__(self, track_id, name, color):
        self.id = track_id
        self.name = name
        self.notes: List[Note] = []
        self.color = color
        self.muted = False
        self.midi_port: Optional[str] = None
        self.midi_channel: int = track_id  # Default to track ID
        self.instrument: int = 0  # MIDI program number
        self.port_handle = None  # Actual mido port object

class MIDIEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("4-Track MIDI Editor - Linux")
        self.root.configure(bg='#1a1a1a')
        
        # MIDI setup
        self.available_ports = []
        self.midi_outputs = {}  # Port name -> mido output object
        self.scan_midi_ports()
        
        # Editor state
        self.tracks = [
            Track(0, "Track 1", TRACK_COLORS[0]),
            Track(1, "Track 2", TRACK_COLORS[1]),
            Track(2, "Track 3", TRACK_COLORS[2]),
            Track(3, "Track 4", TRACK_COLORS[3])
        ]
        self.active_track = 0
        self.bpm = 120
        self.is_playing = False
        self.current_time = 0.0
        
        # Grid calculations
        self.note_height = CANVAS_HEIGHT / NOTE_RANGE
        self.beat_width = CANVAS_WIDTH / BEATS
        
        # Create UI
        self.create_ui()
        
        # Playback thread
        self.playback_thread = None

    def scan_midi_ports(self):
        """Scan for available MIDI output ports"""
        if not MIDO_AVAILABLE:
            return
        
        try:
            self.available_ports = mido.get_output_names()
            print(f"Available MIDI ports: {self.available_ports}")
            
            # Try to create a virtual port if no ports exist
            if not self.available_ports:
                try:
                    virtual_port = mido.open_output('MIDI Editor', virtual=True)
                    self.midi_outputs['MIDI Editor (Virtual)'] = virtual_port
                    self.available_ports = ['MIDI Editor (Virtual)']
                    print("Created virtual MIDI port")
                except Exception as e:
                    print(f"Could not create virtual port: {e}")
        except Exception as e:
            print(f"Error scanning MIDI ports: {e}")

    def get_or_open_port(self, port_name):
        """Get or open a MIDI output port"""
        if not MIDO_AVAILABLE or not port_name:
            return None
        
        if port_name in self.midi_outputs:
            return self.midi_outputs[port_name]
        
        try:
            # Handle virtual port specially
            if port_name == 'MIDI Editor (Virtual)':
                return self.midi_outputs.get(port_name)
            
            port = mido.open_output(port_name)
            self.midi_outputs[port_name] = port
            return port
        except Exception as e:
            print(f"Error opening port {port_name}: {e}")
            return None

    def create_ui(self):
        """Create the user interface"""
        # Top frame - title and BPM
        top_frame = tk.Frame(self.root, bg='#1a1a1a')
        top_frame.pack(fill=tk.X, padx=10, pady=10)
        
        title = tk.Label(top_frame, text="4-Track MIDI Editor", 
                        font=('Arial', 16, 'bold'), fg='white', bg='#1a1a1a')
        title.pack(side=tk.LEFT)
        
        bpm_frame = tk.Frame(top_frame, bg='#1a1a1a')
        bpm_frame.pack(side=tk.RIGHT)
        
        tk.Label(bpm_frame, text="BPM:", fg='white', bg='#1a1a1a').pack(side=tk.LEFT)
        self.bpm_var = tk.StringVar(value=str(self.bpm))
        bpm_entry = tk.Entry(bpm_frame, textvariable=self.bpm_var, width=5)
        bpm_entry.pack(side=tk.LEFT, padx=5)
        bpm_entry.bind('<Return>', lambda e: self.update_bpm())
        
        # Refresh MIDI ports button
        refresh_btn = tk.Button(top_frame, text="🔄 Refresh MIDI", 
                               command=self.refresh_midi_ports,
                               bg='#444444', fg='white')
        refresh_btn.pack(side=tk.RIGHT, padx=10)
        
        # Track configuration frame
        config_frame = tk.Frame(self.root, bg='#2a2a2a')
        config_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.track_widgets = []
        for i, track in enumerate(self.tracks):
            track_frame = tk.Frame(config_frame, bg=track.color, relief=tk.RAISED, bd=2)
            track_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
            
            # Track header with select button
            header_frame = tk.Frame(track_frame, bg=track.color)
            header_frame.pack(fill=tk.X, pady=2)
            
            select_btn = tk.Button(header_frame, text=f"{track.name}\n0 notes", 
                                  bg=track.color, fg='white', font=('Arial', 9, 'bold'),
                                  activebackground=track.color, relief=tk.FLAT,
                                  command=lambda idx=i: self.select_track(idx))
            select_btn.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
            
            mute_btn = tk.Button(header_frame, text="M", width=2,
                               bg='#666666', fg='white', relief=tk.FLAT,
                               command=lambda idx=i: self.toggle_mute(idx))
            mute_btn.pack(side=tk.RIGHT, padx=2)
            
            # MIDI settings
            settings_frame = tk.Frame(track_frame, bg='#1a1a1a')
            settings_frame.pack(fill=tk.X, padx=2, pady=2)
            
            # MIDI Port selector
            tk.Label(settings_frame, text="Port:", fg='white', bg='#1a1a1a', 
                    font=('Arial', 8)).pack(anchor=tk.W)
            port_combo = ttk.Combobox(settings_frame, values=self.available_ports,
                                     width=15, state='readonly', font=('Arial', 8))
            if self.available_ports:
                port_combo.set(self.available_ports[0])
                track.midi_port = self.available_ports[0]
            port_combo.bind('<<ComboboxSelected>>', 
                          lambda e, idx=i: self.on_port_change(idx, e))
            port_combo.pack(fill=tk.X, pady=1)
            
            # MIDI Channel selector
            tk.Label(settings_frame, text="Channel:", fg='white', bg='#1a1a1a',
                    font=('Arial', 8)).pack(anchor=tk.W)
            channel_combo = ttk.Combobox(settings_frame, 
                                        values=[str(i+1) for i in range(16)],
                                        width=15, state='readonly', font=('Arial', 8))
            channel_combo.set(str(track.midi_channel + 1))
            channel_combo.bind('<<ComboboxSelected>>', 
                             lambda e, idx=i: self.on_channel_change(idx, e))
            channel_combo.pack(fill=tk.X, pady=1)
            
            # Instrument selector
            tk.Label(settings_frame, text="Instrument:", fg='white', bg='#1a1a1a',
                    font=('Arial', 8)).pack(anchor=tk.W)
            instrument_names = sorted(GM_INSTRUMENTS.keys(), 
                                     key=lambda x: GM_INSTRUMENTS[x])
            instrument_combo = ttk.Combobox(settings_frame, values=instrument_names,
                                           width=15, state='readonly', font=('Arial', 8))
            instrument_combo.set("Piano")
            instrument_combo.bind('<<ComboboxSelected>>', 
                                lambda e, idx=i: self.on_instrument_change(idx, e))
            instrument_combo.pack(fill=tk.X, pady=1)
            
            self.track_widgets.append({
                'select_btn': select_btn,
                'mute_btn': mute_btn,
                'port_combo': port_combo,
                'channel_combo': channel_combo,
                'instrument_combo': instrument_combo
            })
        
        # Piano roll canvas
        canvas_frame = tk.Frame(self.root, bg='#1a1a1a')
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Piano keys (left side)
        self.piano_canvas = tk.Canvas(canvas_frame, width=60, height=CANVAS_HEIGHT,
                                     bg='#2a2a2a', highlightthickness=0)
        self.piano_canvas.pack(side=tk.LEFT, fill=tk.Y)
        
        # Main grid canvas
        self.canvas = tk.Canvas(canvas_frame, width=CANVAS_WIDTH, height=CANVAS_HEIGHT,
                               bg=BG_COLOR, highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas.bind('<Button-1>', self.canvas_click)
        
        # Control buttons
        control_frame = tk.Frame(self.root, bg='#1a1a1a')
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.play_btn = tk.Button(control_frame, text="PLAY", width=10,
                                  bg='#3b82f6', fg='white', font=('Arial', 10, 'bold'),
                                  command=self.toggle_playback)
        self.play_btn.pack(side=tk.LEFT, padx=5)
        
        clear_btn = tk.Button(control_frame, text="CLEAR TRACK", width=12,
                            bg='#ef4444', fg='white', font=('Arial', 10, 'bold'),
                            command=self.clear_track)
        clear_btn.pack(side=tk.LEFT, padx=5)
        
        save_btn = tk.Button(control_frame, text="SAVE", width=10,
                           bg='#10b981', fg='white', font=('Arial', 10, 'bold'),
                           command=self.save_to_file)
        save_btn.pack(side=tk.LEFT, padx=5)
        
        load_btn = tk.Button(control_frame, text="LOAD", width=10,
                           bg='#8b5cf6', fg='white', font=('Arial', 10, 'bold'),
                           command=self.load_from_file)
        load_btn.pack(side=tk.LEFT, padx=5)
        
        self.status_label = tk.Label(control_frame, text="Ready", 
                                     fg='white', bg='#1a1a1a')
        self.status_label.pack(side=tk.RIGHT, padx=10)
        
        # Draw initial state
        self.draw_piano_keys()
        self.draw_grid()
        self.update_track_buttons()

    def on_port_change(self, track_idx, event):
        """Handle MIDI port selection change"""
        port_name = self.track_widgets[track_idx]['port_combo'].get()
        self.tracks[track_idx].midi_port = port_name
        self.status_label.config(text=f"Track {track_idx+1} → {port_name}")

    def on_channel_change(self, track_idx, event):
        """Handle MIDI channel change"""
        channel = int(self.track_widgets[track_idx]['channel_combo'].get()) - 1
        self.tracks[track_idx].midi_channel = channel
        # Send program change on new channel
        self.send_program_change(track_idx)

    def on_instrument_change(self, track_idx, event):
        """Handle instrument change"""
        instrument_name = self.track_widgets[track_idx]['instrument_combo'].get()
        instrument_num = GM_INSTRUMENTS.get(instrument_name, 0)
        self.tracks[track_idx].instrument = instrument_num
        # Send program change immediately
        self.send_program_change(track_idx)

    def send_program_change(self, track_idx):
        """Send MIDI program change for a track"""
        track = self.tracks[track_idx]
        port = self.get_or_open_port(track.midi_port)
        
        if port and MIDO_AVAILABLE:
            try:
                msg = Message('program_change', 
                            program=track.instrument,
                            channel=track.midi_channel)
                port.send(msg)
            except Exception as e:
                print(f"Error sending program change: {e}")

    def refresh_midi_ports(self):
        """Refresh available MIDI ports"""
        self.scan_midi_ports()
        
        # Update all port combo boxes
        for widget in self.track_widgets:
            current = widget['port_combo'].get()
            widget['port_combo']['values'] = self.available_ports
            if current in self.available_ports:
                widget['port_combo'].set(current)
            elif self.available_ports:
                widget['port_combo'].set(self.available_ports[0])
        
        self.status_label.config(text=f"Found {len(self.available_ports)} MIDI ports")

    def draw_piano_keys(self):
        """Draw piano keys on the left"""
        self.piano_canvas.delete('all')
        note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        
        for i in range(NOTE_RANGE):
            y = i * self.note_height
            midi_note = LOWEST_NOTE + (NOTE_RANGE - 1 - i)
            octave = midi_note // 12 - 1
            note_name = note_names[midi_note % 12]
            
            # Key background
            color = '#3a3a3a' if '#' in note_name else '#4a4a4a'
            self.piano_canvas.create_rectangle(0, y, 60, y + self.note_height,
                                              fill=color, outline=GRID_COLOR)
            
            # Note label
            self.piano_canvas.create_text(30, y + self.note_height/2,
                                         text=f"{note_name}{octave}",
                                         fill='white', font=('Arial', 8))

    def draw_grid(self):
        """Draw the piano roll grid"""
        self.canvas.delete('all')
        
        # Horizontal lines (notes)
        for i in range(NOTE_RANGE + 1):
            y = i * self.note_height
            self.canvas.create_line(0, y, CANVAS_WIDTH, y, fill=GRID_COLOR)
        
        # Vertical lines (beats)
        for i in range(BEATS + 1):
            x = i * self.beat_width
            color = MEASURE_LINE_COLOR if i % 4 == 0 else GRID_COLOR
            self.canvas.create_line(x, 0, x, CANVAS_HEIGHT, fill=color)
        
        # Draw notes from all tracks
        for track_idx, track in enumerate(self.tracks):
            is_active = track_idx == self.active_track
            
            for note in track.notes:
                note_idx = NOTE_RANGE - 1 - (note.pitch - LOWEST_NOTE)
                if note_idx < 0 or note_idx >= NOTE_RANGE:
                    continue
                
                x = note.start * self.beat_width
                y = note_idx * self.note_height
                w = note.duration * self.beat_width
                h = self.note_height
                
                # Draw with transparency for inactive tracks
                fill_color = track.color if is_active else self.dim_color(track.color)
                outline_color = track.color if is_active else GRID_COLOR
                
                self.canvas.create_rectangle(x, y, x + w, y + h,
                                            fill=fill_color, outline=outline_color,
                                            width=2 if is_active else 1)
        
        # Draw playhead
        if self.is_playing:
            x = self.current_time * self.beat_width
            self.canvas.create_line(x, 0, x, CANVAS_HEIGHT, fill='#ef4444', width=2)

    def dim_color(self, color):
        """Dim a hex color by 70%"""
        r = int(color[1:3], 16) // 3
        g = int(color[3:5], 16) // 3
        b = int(color[5:7], 16) // 3
        return f'#{r:02x}{g:02x}{b:02x}'

    def canvas_click(self, event):
        """Handle clicks on the canvas"""
        # Calculate note pitch
        note_idx = int(event.y / self.note_height)
        pitch = LOWEST_NOTE + (NOTE_RANGE - 1 - note_idx)
        
        # Calculate start beat (snap to 16th notes)
        beat = event.x / self.beat_width
        beat = round(beat * BEAT_SUBDIVISIONS) / BEAT_SUBDIVISIONS
        
        # Check if clicking on existing note
        track = self.tracks[self.active_track]
        for note in track.notes:
            if (note.pitch == pitch and 
                note.start <= beat < note.start + note.duration):
                track.notes.remove(note)
                self.draw_grid()
                self.update_track_buttons()
                return
        
        # Add new note
        new_note = Note(pitch, beat, 0.25, 100)
        track.notes.append(new_note)
        self.draw_grid()
        self.update_track_buttons()

    def select_track(self, idx):
        """Switch active track"""
        self.active_track = idx
        self.update_track_buttons()
        self.draw_grid()

    def toggle_mute(self, idx):
        """Toggle track mute"""
        self.tracks[idx].muted = not self.tracks[idx].muted
        self.update_track_buttons()

    def update_track_buttons(self):
        """Update track button displays"""
        for i, widgets in enumerate(self.track_widgets):
            track = self.tracks[i]
            widgets['select_btn'].config(text=f"{track.name}\n{len(track.notes)} notes")
            
            # Highlight active track
            if i == self.active_track:
                widgets['select_btn'].config(relief=tk.SUNKEN, bd=3)
            else:
                widgets['select_btn'].config(relief=tk.RAISED, bd=2)
            
            # Update mute button
            widgets['mute_btn'].config(bg='#333333' if track.muted else '#666666')

    def update_bpm(self):
        """Update BPM from entry field"""
        try:
            new_bpm = int(self.bpm_var.get())
            if 40 <= new_bpm <= 240:
                self.bpm = new_bpm
            else:
                self.bpm_var.set(str(self.bpm))
        except ValueError:
            self.bpm_var.set(str(self.bpm))

    def toggle_playback(self):
        """Start or stop playback"""
        if self.is_playing:
            self.is_playing = False
            self.current_time = 0
            self.play_btn.config(text="PLAY", bg='#3b82f6')
            self.stop_all_notes()
        else:
            # Send program changes before starting playback
            for i in range(len(self.tracks)):
                self.send_program_change(i)
            
            self.is_playing = True
            self.play_btn.config(text="STOP", bg='#ef4444')
            self.playback_thread = threading.Thread(target=self.playback_loop, daemon=True)
            self.playback_thread.start()

    def playback_loop(self):
        """Playback thread"""
        ms_per_beat = 60000 / self.bpm
        start_time = time.time()
        active_notes = {}  # Track which notes are currently playing
        
        while self.is_playing and self.current_time < BEATS:
            current_real_time = time.time() - start_time
            self.current_time = (current_real_time / ms_per_beat) * 1000
            
            # Update UI
            self.root.after(0, self.draw_grid)
            
            # Handle MIDI notes
            for track in self.tracks:
                if track.muted or not track.midi_port:
                    continue
                
                port = self.get_or_open_port(track.midi_port)
                if not port:
                    continue
                
                for note in track.notes:
                    note_id = (track.id, note.pitch, note.start)
                    
                    # Note on
                    if (note.start <= self.current_time < note.start + note.duration):
                        if note_id not in active_notes:
                            self.send_midi_note_on(port, track.midi_channel, 
                                                  note.pitch, note.velocity)
                            active_notes[note_id] = (port, track.midi_channel, note.pitch)
                    
                    # Note off
                    elif note_id in active_notes and self.current_time >= note.start + note.duration:
                        port_info = active_notes[note_id]
                        self.send_midi_note_off(port_info[0], port_info[1], port_info[2])
                        del active_notes[note_id]
            
            time.sleep(0.01)
        
        # Cleanup
        self.is_playing = False
        self.current_time = 0
        self.root.after(0, lambda: self.play_btn.config(text="PLAY", bg='#3b82f6'))
        self.root.after(0, self.draw_grid)
        
        # Stop all notes
        for note_info in active_notes.values():
            self.send_midi_note_off(note_info[0], note_info[1], note_info[2])

    def send_midi_note_on(self, port, channel, pitch, velocity):
        """Send MIDI note on"""
        if port and MIDO_AVAILABLE:
            try:
                msg = Message('note_on', note=pitch, velocity=velocity, channel=channel)
                port.send(msg)
            except Exception as e:
                print(f"MIDI send error: {e}")

    def send_midi_note_off(self, port, channel, pitch):
        """Send MIDI note off"""
        if port and MIDO_AVAILABLE:
            try:
                msg = Message('note_off', note=pitch, channel=channel)
                port.send(msg)
            except Exception as e:
                print(f"MIDI send error: {e}")

    def stop_all_notes(self):
        """Stop all MIDI notes on all tracks"""
        for track in self.tracks:
            if track.midi_port:
                port = self.get_or_open_port(track.midi_port)
                if port and MIDO_AVAILABLE:
                    try:
                        # Send all notes off
                        for i in range(128):
                            msg = Message('note_off', note=i, channel=track.midi_channel)
                            port.send(msg)
                    except Exception as e:
                        print(f"Error stopping notes: {e}")

    def clear_track(self):
        """Clear current track"""
        self.tracks[self.active_track].notes = []
        self.draw_grid()
        self.update_track_buttons()

    def save_to_file(self):
        """Save to JSON file"""
        data = {
            'bpm': self.bpm,
            'tracks': [
                {
                    'name': track.name,
                    'midi_port': track.midi_port,
                    'midi_channel': track.midi_channel,
                    'instrument': track.instrument,
                    'notes': [
                        {
                            'pitch': n.pitch,
                            'start': n.start,
                            'duration': n.duration,
                            'velocity': n.velocity
                        } for n in track.notes
                    ]
                } for track in self.tracks
            ]
        }
        
        filename = f"midi_sequence_{int(time.time())}.json"
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        self.status_label.config(text=f"Saved: {filename}")
        messagebox.showinfo("Saved", f"Saved to {filename}")

    def load_from_file(self):
        """Load from JSON file"""
        from tkinter import filedialog
        filename = filedialog.askopenfilename(
            title="Load MIDI Sequence",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if not filename:
            return
        
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
            
            self.bpm = data.get('bpm', 120)
            self.bpm_var.set(str(self.bpm))
            
            for i, track_data in enumerate(data.get('tracks', [])[:4]):
                track = self.tracks[i]
                track.notes = [
                    Note(n['pitch'], n['start'], n['duration'], n.get('velocity', 100))
                    for n in track_data.get('notes', [])
                ]
                
                # Restore MIDI settings if available
                if 'midi_port' in track_data and track_data['midi_port'] in self.available_ports:
                    track.midi_port = track_data['midi_port']
                    self.track_widgets[i]['port_combo'].set(track.midi_port)
                
                if 'midi_channel' in track_data:
                    track.midi_channel = track_data['midi_channel']
                    self.track_widgets[i]['channel_combo'].set(str(track.midi_channel + 1))
                
                if 'instrument' in track_data:
                    track.instrument = track_data['instrument']
                    # Find instrument name from number
                    for name, num in GM_INSTRUMENTS.items():
                        if num == track.instrument:
                            self.track_widgets[i]['instrument_combo'].set(name)
                            break
            
            self.draw_grid()
            self.update_track_buttons()
            self.status_label.config(text=f"Loaded: {filename}")
            
        except Exception as e:
            messagebox.showerror("Load Error", f"Could not load file: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1150x850")
    app = MIDIEditor(root)
    root.mainloop()
