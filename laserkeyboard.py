#!/usr/bin/python3
# -*- coding: utf-8 -*-

import time
import rtmidi
from rtmidi.midiconstants import NOTE_OFF, NOTE_ON
import numpy as np

offset = 100

midi_in_port = 0
midi_out_port = 2


A1 = [4,8,11]
B1 = [6,10,13]
C1 = [7,11,14]
D1 = [9,13,16]
E1 = [11,15,18]
F1 = [0,4,7]
G1 = [2,6,9]

F2 = [12,16,19]

ACCS = [A1,B1,C1,D1,E1,F1,G1,F2]

keys = np.zeros(32) 
accords = np.zeros([len(ACCS),len(keys)])


for i,A in enumerate(ACCS):
    for k in A:
        accords[i,k] = 1


def midi_event(mytup,data):
    try:
        message = mytup[0]
        timestamp = mytup[1]
        
        print(message)
           
        status_byte = message[0]
        data_bytes = message[1:]

        if (status_byte == 150 or status_byte == 134) and len(data_bytes) == 2:
            note, velocity = data_bytes
            note -= 41
            
            print(note)
            
            if status_byte == 150:        
                keys[note] = 1
                midi_out.send_message([NOTE_ON, note, 127])

            if status_byte == 134:        
                keys[note] = 0
                midi_out.send_message([NOTE_OFF, note, 127])
                
            accords_on = keys * accords
            accords_now = np.clip(np.sum(accords - accords_on, axis = 1),0,1)
        
            for i,a in np.ndenumerate(accords_now):
                chan = int(*i) + offset
                if a == 0:
                    midi_out.send_message([NOTE_ON, chan, 127])
                else:
                    midi_out.send_message([NOTE_OFF, chan, 127])
                    
                    
            if np.sum(keys) >= 12:
                midi_out.send_message([NOTE_ON, 50, 127])
            else:
                midi_out.send_message([NOTE_OFF, 50, 127])
    except:
        pass
  

midi_out = rtmidi.MidiOut()
midi_in = rtmidi.MidiIn()
loop_connected = False
keyboard_connected = False

try:
    print("Press Ctrl+C to exit.")
    while True:
        time.sleep(1)
        if keyboard_connected:            
            try:
                temp = midi_in.get_port_name(midi_in_port) 
                print(temp)
            except:
                print("connection to keyboard lost")
                midi_in.close_port()
                keyboard_connected = False
        else:
            try:
                midi_in.open_port(midi_in_port)
                midi_in.set_callback(midi_event)
                keyboard_connected = True
                print("keyboard connected")
            except:
                print("failed to open input")
                
        if loop_connected:
            try:
                temp = midi_out.get_port_name(midi_out_port)
                print(temp)
            except:
                print("connection to loop lost")
                midi_out.close_port()
                loop_connected = False
        else:
            try:
                midi_out.open_port(midi_out_port)
                loop_connected = True 
                print("connected to loopmidi")
            except:
                print("failed to open output")
except KeyboardInterrupt:
    pass
finally:
    midi_in.close_port()
    midi_out.close_port()
    print("MIDI input port closed.")