#!/usr/bin/env python3
"""
4-Track MIDI Editor for Linux
Pure Python with tkinter - no external dependencies for GUI
Outputs MIDI via ALSA (Linux native MIDI)
"""

import tkinter as tk
from tkinter import messagebox
import threading
import time
import json
from dataclasses import dataclass
from typing import List
import subprocess
import os

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

class MIDIEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("4-Track MIDI Editor - Linux")
        self.root.configure(bg='#1a1a1a')
        
        # MIDI setup
        self.midi_out = None
        self.midi_port_name = None
        self.setup_midi()
        
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

    def setup_midi(self):
        """Setup MIDI output using mido"""
        if not MIDO_AVAILABLE:
            return
        
        try:
            # Try to open a virtual MIDI port or use existing port
            available_ports = mido.get_output_names()
            
            if available_ports:
                # Use first available port
                self.midi_port_name = available_ports[0]
                self.midi_out = mido.open_output(self.midi_port_name)
                print(f"Using MIDI port: {self.midi_port_name}")
            else:
                # Create virtual port (requires python-rtmidi backend)
                try:
                    self.midi_out = mido.open_output('MIDI Editor Virtual', virtual=True)
                    self.midi_port_name = 'MIDI Editor Virtual'
                    print("Created virtual MIDI port: MIDI Editor Virtual")
                except:
                    print("No MIDI ports available. Install a2jmidid or timidity.")
                    
        except Exception as e:
            print(f"MIDI setup error: {e}")

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
        
        # Track buttons frame
        track_frame = tk.Frame(self.root, bg='#1a1a1a')
        track_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.track_buttons = []
        for i, track in enumerate(self.tracks):
            btn_frame = tk.Frame(track_frame, bg=track.color, relief=tk.RAISED, bd=2)
            btn_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
            
            btn = tk.Button(btn_frame, text=f"{track.name}\n0 notes", 
                          bg=track.color, fg='white', font=('Arial', 10, 'bold'),
                          activebackground=track.color, relief=tk.FLAT,
                          command=lambda idx=i: self.select_track(idx))
            btn.pack(fill=tk.BOTH, expand=True, pady=2)
            
            mute_btn = tk.Button(btn_frame, text="M", width=3,
                               bg='#666666', fg='white', relief=tk.FLAT,
                               command=lambda idx=i: self.toggle_mute(idx))
            mute_btn.pack(pady=2)
            
            self.track_buttons.append((btn, mute_btn))
        
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
        
        self.status_label = tk.Label(control_frame, text="Ready", 
                                     fg='white', bg='#1a1a1a')
        self.status_label.pack(side=tk.RIGHT, padx=10)
        
        # Draw initial state
        self.draw_piano_keys()
        self.draw_grid()
        self.update_track_buttons()

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
        for i, (btn, mute_btn) in enumerate(self.track_buttons):
            track = self.tracks[i]
            btn.config(text=f"{track.name}\n{len(track.notes)} notes")
            
            # Highlight active track
            if i == self.active_track:
                btn.config(relief=tk.SUNKEN, bd=3)
            else:
                btn.config(relief=tk.RAISED, bd=2)
            
            # Update mute button
            mute_btn.config(bg='#333333' if track.muted else '#666666')

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
            if self.midi_out:
                # Send all notes off
                for i in range(128):
                    self.send_midi_note_off(i)
        else:
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
                if track.muted:
                    continue
                
                for note in track.notes:
                    note_id = (track.id, note.pitch, note.start)
                    
                    # Note on
                    if (note.start <= self.current_time < note.start + note.duration):
                        if note_id not in active_notes:
                            self.send_midi_note_on(note.pitch, note.velocity)
                            active_notes[note_id] = True
                    
                    # Note off
                    elif note_id in active_notes and self.current_time >= note.start + note.duration:
                        self.send_midi_note_off(note.pitch)
                        del active_notes[note_id]
            
            time.sleep(0.01)
        
        # Cleanup
        self.is_playing = False
        self.current_time = 0
        self.root.after(0, lambda: self.play_btn.config(text="PLAY", bg='#3b82f6'))
        self.root.after(0, self.draw_grid)
        
        # Stop all notes
        for note_id in active_notes:
            self.send_midi_note_off(note_id[1])

    def send_midi_note_on(self, pitch, velocity):
        """Send MIDI note on"""
        if self.midi_out and MIDO_AVAILABLE:
            try:
                msg = Message('note_on', note=pitch, velocity=velocity)
                self.midi_out.send(msg)
            except Exception as e:
                print(f"MIDI send error: {e}")

    def send_midi_note_off(self, pitch):
        """Send MIDI note off"""
        if self.midi_out and MIDO_AVAILABLE:
            try:
                msg = Message('note_off', note=pitch)
                self.midi_out.send(msg)
            except Exception as e:
                print(f"MIDI send error: {e}")

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

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1100x700")
    app = MIDIEditor(root)
    root.mainloop()
