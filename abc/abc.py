#!/usr/bin/python3
# -*- coding: utf-8 -*-

import codecs
from collections import namedtuple
from collections import OrderedDict
from fractions import Fraction
import abc
import argparse
import os
import re
import subprocess
import sys
import struct
import math
import pyaudio
import time 
import rtmidi

global abc_header
abc_header = None

"""
======================================================================================================
======================================================================================================
                                  ***  P  A  T  T  E  R  N  S  ***
======================================================================================================
"""
# VALID TAGS
ALL_TAGS = "BCDFGHIKLMmNOPQRrSsTUVWwXZ"
FILE_HEADER_TAGS = "BCDFGHILMmNORrSUZ"
TUNE_HEADER_TAGS = "BCDFGHIKLMmNOPQRrSTUVWwXZ"
TUNE_BODY_TAGS = "CIKLMmNPQRrsTUVWw"
TUNE_INLINE_TAGS = "IKLMmNPQRrUV"

pattern_fractions = re.compile(r"(\d{1,2})\/(\d{1,2})")
pattern_fractions_eq = re.compile(r"=[ \t]*(\d{1,4})")

# SYMBOLS
pattern_symbol = re.compile(r"\!{1}([\w\d\.\<]{1,20})\!{1}")
pattern_symbols = re.compile(r"([h-wH-W\~]{1})\s{0,}=\s{0,}([^\s]{1,})")

# TAGS
pattern_tune_body_tags = re.compile(r"\[([CIKLMmNPQRrsTUVWw]){1}:{1}([^\[\]]*)\]")
pattern_metre = re.compile(r"(\d{1,2})|[ \t]*\+{0,1}[ \t]*\/(\d{1,2})")
pattern_key = re.compile(
    r"([A-Ga-g0-7]{1}[\#b]{0,1})[ \t]*(ion|mix|dor|phr|lyd|loc|m|sharp|flat)")

# ELEMENTS
pattern_duplets = re.compile(r"\(\d{1}")
pattern_ties = re.compile(r"\.{0,1}\-\,{0,1}")
pattern_slurs = re.compile(r'(\.{0,1}\(\'{0,1})([^\.\'\(\)]*)(\))')
pattern_chords = re.compile(r"(\[)([^\[\]]*)(\])")
pattern_chorded = re.compile(r'\"([^\"\"]*)\"')
pattern_grace_notes = re.compile(r"(\{)([^\{\}]*)(\})")
pattern_overlays = re.compile(r"\&")
pattern_gt = re.compile(r"\>")
pattern_lt = re.compile(r"\<")
pattern_spaces = re.compile(r"[ \t]{1,7}")

pattern_alt_endings = re.compile(r"[\[\|]{1}[\d,-]{1,}")
pattern_repeats = re.compile(r":{1,9}\|{1}[ ]{0,9}\|{0,1}:{1,9}|:{1,9}\|{1}|\|{1}:{1,9}|:{2,9}")
pattern_bars = re.compile(r"\[[ \t]{0,2}\|[ \t]{0,2}\]|\[[ \t]{0,2}\||\|[ \t]{0,2}\]|\|{1,2}")

pattern_voice = re.compile(r"(\w{1,})=[\'\"]{1}([^\"=:]{1,})[\'\"]{1}|(\w{1,})=([^\"= :]{1,})|([\w]{1}):([^\"\'=: ]{1,})|([\w]{1}):[\'\"]{1}([^\"\'=:]{1,})[\'\"]{1}")

pattern_note = re.compile(
    r"(up|down|auto)?(m|min|maj|dim|aug|sus)?([.~THLMPSOJRuv])?(\d{0,2})?([a-gA-GzZ])(\^+|_+|=)?(,|'{0,6})?(\d{0,2})(\/)?(\d{0,2})"
)

"""
======================================================================================================
======================================================================================================
                                  ***  U  T  I  L  I  T  Y  ***
======================================================================================================
"""

def read_lines(file_path):
  """Read lines from a file into list
  
  Args:
    file_path:
  
  Returns:
    list of lines
  """
  try:
    f = open(file_path, "r")
    lines = f.readlines()
    f.close()
  except:
    lines = codecs.open(file_path, "r", "latin-1").readlines()
  return lines


def preprocess_lines(lines):
  """Preprocess lines:
  - Remove comments
  - Remove blank lines
  - Attach lines
  
  Args:
    lines: list of lines

  Returns:
    list of lines
  """
  #remove all comments
  #print("line count ", len(lines))
  clean_lines = []
  for line in lines:
    line = line.replace("`", "")
    if "\\%" in line:
      cl = ""
      prevc = None
      for c in line:
        if c == "%":
          if prevc == "\\":
            # it's an escaped %
            cl = cl[:-1] + c
          else:
            # the rest is a comment
            break
        else:
          cl += c
        prevc = c
      line = cl
    elif line.startswith('%%'):
      # treat as instruction for midi channel and program, some abc files have this hack
      instruction = line.split("%%")[1]
      line = 'I:' + instruction
    elif "%" in line:
      line = line.split("%")[0]
    line = line.strip()
    if line:
      clean_lines.append(line)
  #print("line count ", len(clean_lines))
  #print("line count ", (clean_lines))
  #attach continued lines, remove blanks
  #clean_lines = " ".join(clean_lines).replace("\\", "").splitlines()
  song_lines = []
  prev_idx = 0
  for idx, line in enumerate(clean_lines):
    line = line.strip()
    line = re.sub("DEF.*?FED:|", "", line)
    if not line:
      continue
    if line.startswith("+:"):
      prev_line_index = len(song_lines) - 1
      if prev_line_index >= 0:
        del song_lines[prev_line_index]
      line1 = clean_lines[prev_idx].strip("\n")
      if line1[-1] == "\\":
        line1 = line1[0:-1]
      line2 = line[2:]
      song_lines.append(line1 + line2)
    else:
      # it's not real inline because it's in a separate line
      # wrap it in brackets so that it gets processed as inline
      # don't add it as a tag, because we only return string lines
      name, value = get_name_value_pair(line)
      if name and value:
        #line = "[{}] ".format(line)
        song_lines.append(line)
      else:
        song_lines.append(line)
    prev_idx = idx
    
  lines = ''
  clean_lines = []
  for line in reversed(song_lines):
    if line[-1] == '\\':
      both = line[0:-1] + ' ' + lines
      lines = both
    else:
      clean_lines.insert(0, lines)
      lines = line
  clean_lines.insert(0, lines)
  return clean_lines

"""
    else:
      if clean_lines[prev_idx][-1:] == "\\":
        prev_line = clean_lines[prev_idx][0:-1]
        prev_line_index = len(song_lines) - 1
        if prev_line_index >= 0:
          print("del ", song_lines[prev_line_index])
          del song_lines[prev_line_index]
        # it's not real inline because it's in a separate line
        # wrap it in brackets so that it gets processed as inline
        # don't add it as a tag, because we only return string lines
        name, value = get_name_value_pair(line)
        if name and value:
          line = "[{}]".format(line)
        print("append ", prev_line + " " + line)
        song_lines.append(prev_line + " " + line)
      else:
        song_lines.append(line)
    prev_idx = idx
"""
def fraction2tuple(fraction_str):
  """Extract numerator and denominator from a fraction
  
  """
  # default 1/16
  num = 1
  den = 16
  match = re.match(r"(\d{1,2})\/(\d{1,2})", fraction_str)
  if match:
    num = int(match.group(1).strip())
    den = int(match.group(2).strip())
  return num, den


def process_pattern(in_lines, pattern, class_name, strip=True):
  """Replace patterns with class objects
  
  Args:
    in_lines: list of lines
    pattern: REGEX 
    class_name: class object type
    strip: bool, strip symbol of spaces

  Returns:
    list of lines 
  """
  #pattern
  lines = []
  for line in in_lines:
    if isinstance(line, list):
      list_items = []
      for item in line:
        if isinstance(item, str):
          # process bars
          offset_previous = 0
          for match in pattern.finditer(item):
            offset_start, offset_end = match.span()
            # add string part, that is not a tag
            if offset_previous < offset_start:
              item_str = item[offset_previous:offset_start]
              if item_str:
                list_items.append(item_str)
            offset_previous = offset_end
            # we did get a symbol
            symbol = match.group()
            if strip:
              symbol = symbol.strip()
            if symbol:
              list_items.append(
                  class_name(symbol=symbol))  # append element to list
          item_str = item[offset_previous:]
          if item_str:
            list_items.append(item_str)
        else:
          if item:
            list_items.append(item)  # append tag to list
      if list_items:
        lines.append(list_items)  # append list to lines
    else:
      if line:
        lines.append(line)  # append tag to lines
  return lines


def process_pattern_compound(in_lines, pattern, class_name_start,
                             class_name_end):
  """Replace dual patterns with class objects
  
  Args:
    in_lines: list of lines
    pattern: REGEX 
    class_name_start: class object type
    class_name_end: class object type

  Returns:
    list of lines 
  """
  lines = []
  for line in in_lines:
    if isinstance(line, list):
      list_items = []
      for item in line:
        if isinstance(item, str):
          # process bars
          offset_previous = 0
          for match in pattern.finditer(item):
            offset_start, offset_end = match.span()
            # add string part, that is not a tag
            if offset_previous < offset_start:
              item_str = item[offset_previous:offset_start]
              if item_str:
                list_items.append(item_str)
            offset_previous = offset_end
            # we did get symbols
            symbol_start = match.group(1).strip()
            notes = match.group(2).strip()
            symbol_end = match.group(3).strip()
            if symbol_start and symbol_end and notes:
              list_items.append(
                  class_name_start(symbol=symbol_start))  # append start to list
              list_items.append(notes)  # append notes to list
              list_items.append(
                  class_name_end(symbol=symbol_end))  # append end to list
          item_str = item[offset_previous:]
          if item_str:
            list_items.append(item_str)
        else:
          if item:
            list_items.append(item)  # append tag to list
      if list_items:
        lines.append(list_items)  # append list to lines
    else:
      if line:
        lines.append(line)  # append tag to lines
  return lines


def process_pattern_to_dictionary(line, pattern):
  """
  
  Args:
    line: 
    pattern: REGEX 

  Returns:
    dictionary
  """
  #
  key_value_pairs = {}
  line = line.strip()
  for match in pattern.finditer(line):
    for idx, g in enumerate(match.groups()):
      if g:
        key_value_pairs[g] = match.groups()[idx+1]
        break
  return key_value_pairs


def remove_unprocessed_strings(in_lines):
  """Remove string that did not match a tag or element
  
  Args:
    in_lines: list of lines

  Returns:
    list of lines 
  """
  lines = []
  for idx, line in enumerate(in_lines):
    if isinstance(line, list):
      list_items = []
      for idxi, item in enumerate(line):
        if isinstance(item, str):
          #print("Warning! Found unprocessed string: ", item, ' line#: ', idx, ' line: ', line)
          xyz = 1
          list_items.append(item)
        else:
          list_items.append(item)
      if list_items:
        lines.append(list_items)
    else:
      lines.append(line)
  return lines


def get_name_value_pair(text):
  """Match to any valid tag
  
  Args:
    text: string

  Returns:
    tuple: Tag, Value 
  """
  m = TAGMatcher(text)
  if m.match(r"^([BCDFGHIKLMmNOPQRrSsTUVWwXZ]{1}):(.*)"):
    return (m.group(1), m.group(2))
  else:
    return (None, None)

def get_name_value_triplet(text):
  """Match to any valid tag
  
  Args:
    text: string

  Returns:
    tuple: Tag, Value 
  """
  m = TAGMatcher(text)
  if m.match(r"^([BCDFGHIKLMmNOPQRrSsTUVWwXZ]{1}):([^ ]{1,})(.*)"):
    return (m.group(1), m.group(2), m.group(3))
  else:
    return (None, None, None)

class RangeDict(dict):
  """Match range of integers as key"""

  def __getitem__(self, item):
    if type(item) != range:
      for key in self:
        if item in key:
          return self[key]
      raise KeyError(item)
    else:
      return super().__getitem__(item)


"""
======================================================================================================
======================================================================================================
                                    ***  F  R  E  Q  U  E  N  C  Y  ***
======================================================================================================
"""

class MidiNotes(object):
  """Process midi notes from a file into a dictionary"""

  def __init__(self, frequency_lines, piano_frequency_lines):
    
    self.name_notes = {}
    self.note_names = {}
    for line in piano_frequency_lines:
      items = line.split("\t")
      name = items[2].strip()
      note = items[1].strip()
      if "/" in note:
        notes = note.split("/")
        note1 = notes[0].strip()
        note2 = notes[1].strip()
        if "/" in name:
          names = name.split("/")
          self.name_notes[names[0]] = note
          self.name_notes[names[1]] = note
          self.note_names[note1] = names[0]
          self.note_names[note2] = names[0]
        else:
          self.name_notes[name] = note1
          self.note_names[note1] = name
          self.note_names[note2] = name
      else:
        if "/" in name:
          names = name.split("/")
          self.name_notes[names[0]] = note
          self.name_notes[names[1]] = note
          self.note_names[note] = names[0]
        else:
          self.name_notes[name] = note
          self.note_names[note] = name

    self.name_midi = {}
    self.note_midi = {}
    self.midi_frequency = {}
    for line in frequency_lines:
      items = line.split("\t")
      name = items[3].strip()
      midi = items[0].strip()
      self.midi_frequency[midi] = items[5].strip()
      if "/" in name:
        names = name.split("/")
        self.name_midi[names[0]] = midi
        self.name_midi[names[1]] = midi
        if names[0] in self.name_notes:
          self.note_midi[self.name_notes[names[0]]] = midi
        if names[1] in self.name_notes:
          self.note_midi[self.name_notes[names[1]]] = midi
      else:
        self.name_midi[name] = midi
        if name in self.name_notes:
          self.note_midi[self.name_notes[name]] = midi
    
  def get(self, note, accidental, octaves):
    """Get a frequency
    
    Args:
      note: plain note letter
      accidental: sharp, flat
      octaves: comma or apostrophe

    Returns:
      frequency: float
    """
    composite_note = note + accidental + octaves
    if composite_note in self.frequencies:
      frequency = self.frequencies[composite_note]
    else:
      frequency = self.frequencies[note + octaves]
    return frequency


class Frequencies(object):
  """Process frequencies from a file into a dictionary"""

  def __init__(self, frequency_lines):
    self.frequencies = {}
    self.frequencies["z"] = 0
    self.frequencies["Z"] = 0
    self.frequencies["X"] = 0
    for line in frequency_lines:
      items = line.split("\t")
      name = items[1]
      if "/" in name:
        names = name.split("/")
        self.frequencies[names[0]] = float(items[3])
        self.frequencies[names[1]] = float(items[3])
      else:
        self.frequencies[name] = float(items[3])

  def get(self, note, accidental, octaves):
    """Get a frequency
    
    Args:
      note: plain note letter
      accidental: sharp, flat
      octaves: comma or apostrophe

    Returns:
      frequency: float
    """
    if '=' in note:
      note = note.replace('=', '')
    composite_note = note + accidental + octaves
    if composite_note in self.frequencies:
      frequency = self.frequencies[composite_note]
    else:
      composite_note = note + octaves
      if composite_note in self.frequencies:
        frequency = self.frequencies[note + octaves]
      else:
        frequency = self.frequencies[note]
    return frequency


"""
======================================================================================================
======================================================================================================
                                ***  T  U  N  E    P  L  A  Y  E  R  S  ***
======================================================================================================
"""
class Pause(object):
  
  def __init__(self, duration):
    self.duration = duration
    
  def __str__(self):
    return "Pause·%s·" % (self.duration)

  def __repr__(self):
    return self.__str__()

    
class Player(abc.ABC):
 
  def __init__(self):
    self.notes = {}
    
  def start(self):
    pass

  def stop(self):
    pass

  def add_note(self, note, duration):
    if note.compound_note not in self.notes:
      if note.compound_note[0] in 'zZx':
        self.notes[note.compound_note] = Pause(duration)
      else:
        #print('Adding symbol: ', symbol)
        self.notes[note.compound_note] = self.create_tune(note, duration)
    
  def create_tune(self, note, duration):
    pass
   
  def slur(self):
    pass

  def play(self, note, duration):
    pass
  
  def command(self, instruction):
    pass


class SpeakerPlayer(Player):
  
  def __init__(self):
    super(SpeakerPlayer, self).__init__()

  def add_note(self, note, duration):
    compound_plus_length = note.compound_note + str(note.length)
    if compound_plus_length not in self.notes:
      if compound_plus_length[0] in 'zZx':
        self.notes[compound_plus_length] = Pause(duration)
      else:
        #print('Adding symbol: ', symbol)
        self.notes[compound_plus_length] = self.create_tune(note, duration)

  def create_tune(self, note, duration):
    #duration *= 1000
    #compound_plus_length = note.compound_note + str(note.length)
    #return "beep -f {} -l {}".format(note.frequency, duration)
    freq = int(note.frequency * 10)
    dur = 0.6
    duration *= 1.4
    dur = duration
    print('duration ', dur)
    print('note.frequency ', freq)
    #return "play -n synth {} sine {} vol 0.1".format(duration, freq)
    return "play -n synth {} sine {} vol 0.03".format(dur, freq)
   

  def play(self, note, duration):
    compound_plus_length = note.compound_note + str(note.length)
    item = self.notes[compound_plus_length]
    print('SpeakerPlayer ', item)
    if compound_plus_length[0] in 'zZx':
      time.sleep(duration)
    else:
      os.system(item)
        

class TunePlayer(Player):
  """Play a tune from a note stored in dictionary, at a specific time, repeating x times"""
  FORMAT = pyaudio.paInt16
  CHANNELS = 2
  RATE = 44100

  def __init__(self):
    super(TunePlayer, self).__init__()
    self.stream = None

  def start(self):
    p = pyaudio.PyAudio()
    self.stream = p.open(format=self.FORMAT, channels=self.CHANNELS, rate=self.RATE, output=True)
    
  def stop(self):
    self.stream.stop_stream()
    self.stream.close()
    
  def add_note(self, note, duration):
    compound_plus_length = note.compound_note + str(note.length)
    if compound_plus_length not in self.notes:
      if compound_plus_length[0] in 'zZx':
        self.notes[compound_plus_length] = Pause(duration)
      else:
        #print('Adding symbol: ', symbol)
        self.notes[compound_plus_length] = self.create_tune(note, duration)

  def create_tune(self, note, duration):
    """get frames for a fixed frequency for a specified time or
    number of frames, if frame_count is specified, the specified
    duration is ignored"""
    duration *= 2
    #print('TunePlayer create_tune duration ', duration)
    frame_count = int(self.RATE * duration)
    remainder_frames = frame_count % self.RATE
    wavedata = []
    frequency = float(note.frequency)
    for i in range(frame_count):
        a = self.RATE / frequency  # number of frames per wave
        b = i / a
        c = b * (2 * math.pi)
        #d = math.sin(c) * 32767 * volume
        d = math.sin(c) * 32767
        e = int(d)
        wavedata.append(e)
    for i in range(remainder_frames):
      wavedata.append(0)
    number_of_bytes = str(len(wavedata))  
    return struct.pack(number_of_bytes + 'h', *wavedata)

  def play(self, note, duration):
    compound_plus_length = note.compound_note + str(note.length)
    item = self.notes[compound_plus_length]
    if compound_plus_length[0] in 'zZx':
      time.sleep(duration)
      print('TunePlayer pause %.2f' % duration)
    else:
      print('TunePlayer ', compound_plus_length, ' %.2f' % duration)
      self.stream.write(item)

"""
LINUX_ALSA, UNIX_JACK, MACOSX_CORE, WINDOWS_MM and RTMIDI_DUMMY  rtmidi.API_UNSPECIFIED

"""

class MidiPlayer(Player):
  PORT_NAME = 'VMPK Input:in 130:0'
  PORT_NAME = 'Midi Through:Midi Through Port-0 14:0'
  ON = 0x90
  OFF = 0x80
  PROGRAM_CHANGE = 0xC0
  PORTAMENTO_TIME = PORTAMENTO_TIME_MSB = 0x05
  # Switches

  # off: value <= 63, on: value >= 64
  SUSTAIN = SUSTAIN_ONOFF = 0x40
  PORTAMENTO = PORTAMENTO_ONOFF = 0x41
  SOSTENUTO = SOSTENUTO_ONOFF = 0x42
  SOFT_PEDAL = SOFT_PEDAL_ONOFF = 0x43
  LEGATO = LEGATO_ONOFF = 0x44
  HOLD_2 = HOLD_2_ONOFF = 0x45  
  
  def __init__(self, midi_notes):
    super(MidiPlayer, self).__init__()
    self.midi_notes = midi_notes
    self.midiout = None
    self.port = 0
    self.inslur = 0
    self.previous_midi = None

  def start(self):
    self.midiout = rtmidi.MidiOut()
    print("MidiPlayer start midiout: ", self.midiout)
    idx = 0
    for p in self.midiout.get_ports():
      print("MidiPlayer get_ports: ", p)
      if p == self.PORT_NAME:
        print("Setting port to: ", p)  
        self.port = idx
        break
      print("MidiPlayer port: ", p)
      idx += 1
    res = self.midiout.open_port(self.port)
    print("MidiPlayer start result: ", res)
    
  def stop(self):
    del self.midiout
    self.midiout = None
    self.port = 0
    
  def command(self, instruction):
    print('COMMAND: ', instruction)
    print("MidiPlayer midiout: ", self.midiout)
    if isinstance(instruction, MidiInstruction):
      print("instruction category: ", instruction.category)
      if instruction.category == 'PRG':
        instrument = int(instruction.value) - 1
        #print('COMMAND instrument: ', instrument)
        #res = rtmidi.send_program_change(midi_command)
        #print("send_program_change result: ", res)
        midi_command = [self.PROGRAM_CHANGE, instrument & 0x7F]
        #print('COMMAND: ', midi_command)
        #res = self.midiout.send_message(instrument)
        res = self.midiout.send_message(midi_command)
        time.sleep(0.5)
        print("COMMAND result: ", res)
    else:
      print('COMMAND error wrong instance type')
    
  def create_tune(self, note, duration):
    return (note.compound_note, duration)
    
  def slur(self):
    toggle_slur = [self.PORTAMENTO]
    self.midiout.send_message(toggle_slur)
    if self.inslur == 0:
      self.inslur = 1
      print('Slur ON')
    else:
      self.inslur = 0
      if self.previous_midi:
        print('prev midi OFF', self.previous_midi)
        note_off = [self.OFF, self.previous_midi, 0]
        self.midiout.send_message(note_off)
        time.sleep(0.2)
        self.previous_midi = None
      print('Slur OFF')

  def play(self, note, duration):
    #print('MidiPlayer play note.compound_note ', note.compound_note)
    #duration *= 10
    if '=' in note.compound_note:
      note.compound_note = note.compound_note.replace('=', '')
    print('MidiPlayer ', note.compound_note, ' %.2f' % duration)
    if note.compound_note[0] in 'zZx':
      time.sleep(duration)
    else:
      item, duration = self.notes[note.compound_note]
      #duration *= 10
      if item in self.midi_notes.note_midi:
        midi = int(self.midi_notes.note_midi[item])
      else:
        note = self.midi_notes.note_names[item]
        midi = int(self.midi_notes.name_midi[note])
      
      if self.inslur:
        print('current midi ON', midi)
      note_on = [self.ON, midi, 112]
      self.midiout.send_message(note_on)
      time.sleep(duration)
      
      if self.inslur:
        if self.previous_midi:
          print('prev midi OFF', self.previous_midi)
          note_off = [self.OFF, self.previous_midi, 0]
          self.midiout.send_message(note_off)
          time.sleep(0.2)
        self.previous_midi = midi
      else:
        note_off = [self.OFF, midi, 0]
        self.midiout.send_message(note_off)
        time.sleep(0.1)
        self.previous_note = None


class PrintPlayer(Player):
 
  def create_tune(self, note, duration):
    return "{} \t({:.2f})".format(note.compound_note, duration)
   
  def play(self, note, times = 1):
    item = self.notes[note.compound_note]
    print('\tPlayer', item)


"""
======================================================================================================
======================================================================================================
                                        ***  T  A  G  S  ***
======================================================================================================
"""

class TAGMatcher(object):

  def __init__(self, matchstring):
    self.matchstring = matchstring

  def match(self, regexp):
    self.rematch = re.match(regexp, self.matchstring)
    return bool(self.rematch)

  def group(self, i):
    return self.rematch.group(i)


class Tag(object):

  def __init__(self, name, value):
    self.name = ''
    self.value = ''
    if not value:
      return
    self.name = name
    m = TAGMatcher(value)
    self.value = value.strip()
    self.comment = None
    if m.match(r"(.+)%(.*)"):
      value = m.group(1).strip()
      if value:
        self.value = value
      self.comment = m.group(2).strip()

  def compile(self):
    pass

  def __str__(self):
    return "%s·%s:%s·" % (self.__class__.__name__, self.name, self.value)

  def __repr__(self):
    return self.__str__()


#-------------------------------------------------------------------------------------------
#-------------------------------------------------------------------------------------------

class NamelessTag(Tag):

  def __str__(self):
    return "%s·%s·" % (self.__class__.__name__, self.value)

#-------------------------------------------------------------------------------------------

class Book(NamelessTag):
  pass


class Composer(NamelessTag):
  pass


class Discography(NamelessTag):
  pass


class File(NamelessTag):
  pass


class Group(NamelessTag):
  pass


class History(NamelessTag):
  pass


class Macro(NamelessTag):
  pass


class Notes(NamelessTag):
  pass


class Origin(NamelessTag):
  pass


class Rhythm(NamelessTag):
  pass


class Remark(NamelessTag):
  pass


class Source(NamelessTag):
  pass


class Symbols(NamelessTag):
  pass


class Title(NamelessTag):
  pass


class Words(NamelessTag):
  pass


class Lyrics(NamelessTag):
  pass


class Reference(NamelessTag):
  pass


class Transcriber(NamelessTag):
  pass


class User(Tag):
  default_symbols = {
    '~' : 'roll',
    'H' : 'fermata',
    'L' : 'accent',
    'M' : 'lowermordent',
    'O' : 'coda',
    'P' : 'uppermordent',
    'S' : 'segno',
    'T' : 'trill',
    'u' : 'upbow',
    'v' : 'downbow',
    }

  def compile(self):
    match = re.match(pattern_symbols, self.value)
    self.symbol = ''
    self.value = ''
    if match:
      self.symbol = match.group(1).strip()
      self.value = match.group(2).strip()

  def __str__(self):
    return "%s·%s:%s·" % (self.__class__.__name__, self.symbol, self.value)


"""
======================================================================================================
======================================================================================================
                                  ***  S  O  N  G  ***
======================================================================================================
"""

class Song(object):

  def __init__(self, file_header, song_lines):
    self.file_header = file_header
    self.header = TuneHeader()
    self.process_default_tags = False
    lines = []
    macros = []
    processing_header = True
    # process header first, until we find the K field
    for line in song_lines:
      name, value = get_name_value_pair(line)
      if name and value and processing_header:
        if name == "K":
          # add defaults
          if not self.header.has_tag("L"):
            self.header.set_tag("L", self.file_header.get_tag("L"))
            self.process_default_tags = True
          if not self.header.has_tag("M"):
            self.header.set_tag("M", self.file_header.get_tag("M"))
          if not self.header.has_tag("Q"):
            self.header.set_tag("Q", Tag("Q", "Allegro"))
          processing_header = False
        self.header.set_tag(name, Tag(name, value))
      elif name and value:
        lines.append(Tag(name, value))
      else:
        lines.append(line)
      if name == "m":
        macro = value.split("=")
        macros.append((macro[0].strip(), macro[1].strip()))

    # inline tag extraction, macro substitution, also process in-line macros
    self.lines = []
    # a dictionary of macros, since they can be subjected to change
    inline_macros = {}
    line_sections = []
    for line in lines:
      # substitute header and inline macros
      for m, v in macros:
        line = line.replace(m, v)
      for m in inline_macros:
        line = line.replace(m, inline_macros[m])
      # process string and add sections (tags, string)
      if isinstance(line, str):
        offset_previous = 0
        # try to match tags (info fields)
        for match in pattern_tune_body_tags.finditer(line):
          offset_start, offset_end = match.span()
          # add string part, that is not a tag
          if offset_previous < offset_start:
            line_section = line[offset_previous:offset_start]
            line_sections.append(line_section)
          offset_previous = offset_end
          # we did get a tag
          tag_name = match.group(1).strip()
          tag_value = match.group(2).strip()
          # add new macro
          if tag_name == "m":
            # no need to save a macro after substitution
            macro = match.group(2).split("=")
            inline_macros[macro[0].strip()] = macro[1].strip()
          elif tag_name in TUNE_BODY_TAGS:
            # tag was valid for inline TODO: change TUNE_BODY_TAGS to TUNE_INLINE_TAGS
            # add tag
            line_sections.append(Tag(tag_name, tag_value))
        line_section = line[offset_previous:]
        line_sections.append(line_section)
        self.lines.append(line_sections)
        line_sections = []
      else:
        if isinstance(line, Tag) and line.name in 'KLMPQ':
          line_sections.append(line)
        else:
          self.lines.append(line)
        
    # now we have a list of lines that contains either a tag or a list (with tags and/or strings)
    self.lines = process_pattern(self.lines, pattern_symbol, Symbol)

    self.lines = process_pattern(self.lines, pattern_ties, Tie)
    self.lines = process_pattern(self.lines, pattern_alt_endings, AltEnding)
    self.lines = process_pattern(self.lines, pattern_overlays, Overlay)
    self.lines = process_pattern(self.lines, pattern_repeats, Repeat)
    self.lines = process_pattern(self.lines, pattern_bars, Bar)
    self.lines = process_pattern(self.lines, pattern_duplets, Duplet)
    self.lines = process_pattern(self.lines, pattern_gt, Gt)
    self.lines = process_pattern(self.lines, pattern_lt, Lt)

    self.lines = process_pattern_compound(self.lines, pattern_slurs, SlurStart,
                                          SlurEnd)
    self.lines = process_pattern_compound(self.lines, pattern_chords,
                                          ChordStart, ChordEnd)
    self.lines = process_pattern_compound(self.lines, pattern_grace_notes,
                                          GraceNoteStart, GraceNoteEnd)
    self.lines = process_pattern(self.lines, pattern_spaces, Space, strip=False)
    self.lines = process_pattern(self.lines, pattern_chorded, Chorded)

    #pattern_note
    self.lines = process_pattern(self.lines, pattern_note, Note)

    self.lines = remove_unprocessed_strings(self.lines)

    self.header.validate()
    self.compile()

  def compile(self):
    self.header.compile()
    # join in-line tags with next line if they're last
    for idx in range(len(self.lines)):
      has_note = False
      line = self.lines[idx]
      if isinstance(line, list):
        for item in line:
          if isinstance(item, Note):
            has_note = True
            break
        if not has_note and isinstance(line[-1], Tag) and idx+1 < len(self.lines):
          self.lines[idx] = line + self.lines[idx+1]
          self.lines[idx+1] = None
    self.lines = [x for x in self.lines if x != None]
        
    # convert to correct class for all tags
    for line in self.lines:
      if isinstance(line, Tag):
        line = Header.subclass(line.name, line)
        if isinstance(line, Instruction):
          line.compile()
          if 'MIDI' in line.value.keys():
            line.__class__ = MidiInstruction
            setattr(line, '__class__', MidiInstruction)
        line.compile()
      elif isinstance(line, list):
        for item in line:
          if isinstance(item, Tag):
            item = Header.subclass(item.name, item)
            if isinstance(item, Instruction):
              item.compile()
              if 'MIDI' in item.value.keys():
                item.__class__ = MidiInstruction
                setattr(item, '__class__', MidiInstruction)
            item.compile()

    # Classify Repeats into Start and End, and count repeats, 
    # one : equals 1 repeat (two plays), :: two repeats, etc...
    # Start = bar starts with  |
    # End   = bar ends with    |
    # else bar is both, then split bar
    # If an 'end of repeated section' is found without a previous 'start of repeated section', 
    #   playback programs should restart the music from the beginning of the tune, or 
    #   from the latest double bar line or end of repeated section
    # start of line, double bar, or end of previous repeat
    for line in self.lines:
      if isinstance(line, Tag):
        continue
      if isinstance(line, list):
        start_of_repeat = 0
        for idx, item in enumerate(line):
          # double bar?
          if isinstance(item, Bar) and len(item.symbol) > 1:
            start_of_repeat = idx
          elif isinstance(item, AltEnding):
            start_of_repeat = idx
            endings = []
            prev = 0
            fill = False
            for s in list(item.symbol):
              if s.isdigit():
                cur = int(s)
                if not fill:
                  endings.append(cur)
                  prev = cur
                else:
                  for x in range(prev, cur):
                    endings.append(x+1)
                  fill = False
              elif s == '-':
                fill = True
            item.endings = endings
          elif isinstance(item, Repeat):
            item.symbol = "".join(item.symbol.split())
            symbol = item.symbol
            repeat_bars = []
            if symbol[0] == '|':
              start_of_repeat = idx
              repeat_bars.append(StartRepeat(symbol=symbol))
            elif symbol[-1] == '|':
              repeat_bars.append(EndRepeat(symbol=symbol, start=start_of_repeat))
            else:
              start = None
              end = None
              if '|' in symbol:
                segments = symbol.split('|')
                start = segments[0]
                end = segments[-1]
              else:
                start, end = symbol[:int(len(symbol)/2)], symbol[int(len(symbol)/2):]
              start = '|' + start
              end = end + '|'
              repeat_bars.append(EndRepeat(symbol=end, start=start_of_repeat))
              repeat_bars.append(StartRepeat(symbol=start))
              start_of_repeat = idx
            del line[idx]
            for repeat in repeat_bars:
              if isinstance(repeat, EndRepeat):
                repeat.count = len(repeat.symbol)
                repeat.reset()
              line.insert(idx, repeat)
          #elif isinstance(item, AltEnding):
    if self.process_default_tags:
      lt = self.header.get_tag("L")
      mt = self.header.get_tag("M")
      lt.set_from_meter(mt)


"""
======================================================================================================
======================================================================================================
                                  ***  A  B  C   F  I  L  E  ***
======================================================================================================
"""

class AbcInclude(object):
  """Include header container"""

  def __init__(self, lines):
    """"""
    self.header = FileHeader()
    # Process file header
    lines = preprocess_lines(lines)
    last_header_line_index = len(lines)
    for idx, line in enumerate(lines):
      name, value = get_name_value_pair(line)
      self.header.set_tag(name, Tag(name, value))
    self.header.validate(add_defaults=False)



class AbcFile(object):
  """Song container"""

  def get_song(self, index):
    """Get song from index"""
    index -= 1
    if index >= len(self.songs):
      print("WARNING: Invalid song index: ", index, " using last song: ",
            len(self.songs))
      index = len(self.songs) - 1
    return self.songs[index]

  def __init__(self, lines):
    """Create songs from lines in abc file"""
    self.header = FileHeader()
    # Process file header
    last_header_line_index = len(lines)
    for idx, line in enumerate(lines):
      print('AbcFile __init__ line ', (line))
      if line.startswith("X:") or line.startswith("[X:"):
        last_header_line_index = idx
        break
      else:
        name, value = get_name_value_pair(line)
        self.header.set_tag(name, Tag(name, value))
    del lines[0:last_header_line_index]
    global abc_header
    abc_header = self.header
    self.header.validate()
    
    print(self.header)

    self.songs = []
    # process songs
    idx_song_start = 0
    for idx, line in enumerate(lines):
      if line.startswith("X:") and idx:
        self.songs.append(Song(self.header, lines[idx_song_start:idx]))
        idx_song_start = idx
    self.songs.append(Song(self.header, lines[idx_song_start:]))
    #print("self.songs count ", len(self.songs))
    #print("self.songs 10 ", self.songs[9].lines)

"""
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
"""

"""
======================================================================================================
======================================================================================================
                                        ***  T  A  G  S  ***
======================================================================================================
"""

#-------------------------------------------------------------------------------------------
class Metre(NamelessTag):
  """A meter change within the body of the tune will not change the unit note length."""

  def compile(self):
    den = 1
    value = self.value.upper()
    if value == "C":
      self.numerator = 4
      self.denominator = 4
    elif value == "C|":
      self.numerator = 2
      self.denominator = 2
    elif value == "FREE":
      self.numerator = 2
      self.denominator = 2
    else:
      num = 0
      for match in pattern_metre.finditer(self.value):
        if match.group(1):
          num += int(match.group(1).strip())
        if match.group(2):
          den = int(match.group(2).strip())
      self.numerator = num
      self.denominator = den

    if self.numerator == self.denominator:
      if self.denominator == 4:
        self.value = "C"
      elif self.denominator == 2:
        self.value = "C|"
    self.ratio = self.numerator / self.denominator

  def __str__(self):
    #return '%s·%s/%s·' % (self.__class__.__name__, self.numerator, self.denominator)
    return "%s·%s·" % (self.__class__.__name__, self.value)


#-------------------------------------------------------------------------------------------
class Length(NamelessTag):
  defaults = {
      "minim": "1/2",
      "half": "1/2",
      "crotchet": "1/4",
      "quarter": "1/4",
      "semiQuaver": "1/16",
      "semi": "1/16",
      "sixteenth": "1/16",
      "quaver": "1/8",
      "eighth": "1/8",
      "jig": "1/8",
      "reel": "1/8",
      "schottische": "1/8",
      "bourree": "1/8",
      "polka": "1/8",
      "waltz": "1/4"
  }

  words = {
      "1/2": "Minim",
      "1/4": "Crotchet",
      "1/8": "Quaver",
      "1/16": "Semiquaver"
  }

  def __init__(self, name, value):
    Tag.__init__(self, name, value)

  def compile(self):
    self.numerator = 0
    self.denominator = 0
    self.ratio = 0
    self.use_word = False
    if self.value:
      fraction = None
      value = self.value.lower()
      num, den = fraction2tuple(value)
      if num and den:
        value = None
      else:
        if value in self.defaults:
          value = self.defaults[value]
        num, den = fraction2tuple(value)
      if num and den:
        self.numerator = num
        self.denominator = den
        self.ratio = self.numerator / self.denominator
        self.fraction = Fraction(self.numerator, self.denominator)
        fraction = "{}/{}".format(self.numerator, self.denominator)
        if not value and fraction in self.words:
          value = self.words[fraction]
      if value:
        self.value = value
        self.use_word = True
      else:
        self.value = "{}/{}".format(self.numerator, self.denominator)

  def set_from_meter(self, meter):
    num, den = fraction2tuple(meter.value)
    if num and den:
      val = num / den
      if val < 0.75:
        self.value = "Semiquaver"
      else:
        self.value = "Quaver"
    else:
      self.value = "Quaver"
    self.compile()

  def __str__(self):
    if self.use_word:
      return "%s·%s %s/%s·" % (self.__class__.__name__, self.value,
                               self.numerator, self.denominator)
    else:
      return "%s·%s·" % (self.__class__.__name__, self.value)


#-------------------------------------------------------------------------------------------
class Tempo(NamelessTag):
  ranges = RangeDict({
      range(5, 30): "Grave",
      range(31, 39): "Largamente",
      range(40, 50): "Largo",
      range(51, 60): "Larghetto",
      range(61, 76): "Adagio",
      range(77, 83): "Andantino",
      range(84, 90): "Andante",
      range(91, 100): "Andante Moderato",
      range(101, 115): "Moderato",
      range(116, 116): "Allegro Moderato",
      range(117, 119): "Allegretto",
      range(130, 130): "Allegro con Brio",
      range(120, 139): "Allegro",
      range(140, 160): "Molto Allegro",
      range(161, 170): "Allegro Vivace",
      range(171, 179): "Vivace",
      range(180, 199): "Presto",
      range(200, 500): "Prestissimo"
  })

  defaults = {
      "grave": 25,
      "largamente": 35,
      "largo": 45,
      "larghetto": 55,
      "adagio": 70,
      "andantino": 80,
      "andante": 85,
      "andante Moderato": 95,
      "moderato": 110,
      "allegro Moderato": 116,
      "allegretto": 118,
      "allegro con Brio": 130,
      "allegro": 130,
      "molto Allegro": 150,
      "allegro Vivace": 165,
      "vivace": 175,
      "presto": 185,
      "prestissimo": 210
  }

  words = {
      "larghissimo": "Grave",
      "lento": "Largo",
      "adagietto": "Andantino",
      "vivacissimo": "Vivace",
      "allegrissimo": "Prestissimo",
      "vivacissimamente": "Vivace",
      "vivo": "Vivace",
      "tranquillamente": "Adagio",
      "tranquillo": "Adagio",
      "mouvement": "Grave",
      "lent": "Largo",
      "modéré": "Moderato",
      "moins": "Allegro Vivace",
      "rapide": "Presto",
      "très": "Vivace",
      "vif": "Vivace",
      "vite": "Vivo",
      "kräftig": "Vivace",
      "langsam": "Largo",
      "lebhaft": "Vivace",
      "mäßig": "Moderato",
      "rasch": "Allegro",
      "schnell": "Presto",
      "bewegt": "Prestissimo"
  }

  def _process_tempo(self, fraction_str):
    if not fraction_str:
      return Fraction(numerator=4, denominator=4), 120
    fractions = Fraction(0, 1)
    for match in pattern_fractions.finditer(fraction_str):
      num = int(match.group(1).strip())
      den = int(match.group(2).strip())
      fractions += Fraction(num, den)

    bpm = 0
    for match in pattern_fractions_eq.finditer(fraction_str):
      bpm = int(match.group(1).strip())

    return fractions, bpm

  def _get_bpm(self, value):
    bpm = 0
    value = value.lower()
    if value in self.defaults:
      bpm = self.defaults[value]
    else:
      # check for translations or alt values
      if value in self.words:
        value = value.lower()
        value = self.words[value]
        bpm = self.defaults[value]
    return bpm

  def compile(self):
    self.fraction, self.bpm = self._process_tempo(self.value)

    self.tempo = "Allegro"
    if self.bpm:
      self.tempo = self.ranges[self.bpm]
    else:
      if not self.bpm:
        # look for value as a word
        self.bpm = self._get_bpm(self.value)
        self.tempo = self.value
      # split value into words and search
      if not self.bpm:
        for word in self.value.split():
          self.bpm = self._get_bpm(word)
          if self.bpm:
            self.tempo = word
            break
      # default to bpm = 120
      if not self.bpm:
        self.bpm = 120

  def __str__(self):
    return "%s·%s:%sbpm·" % (self.__class__.__name__, self.tempo, self.bpm)


#-------------------------------------------------------------------------------------------
class Key(NamelessTag):
  aeolian = {
      "A#m": "C#",
      "D#m": "F#",
      "G#m": "B",
      "C#m": "E",
      "F#m": "A",
      "Bm": " D",
      "Em": " G",
      "Am": " C",
      "Dm": " F",
      "Gm": " Bb",
      "Cm": " Eb",
      "Fm": " Ab",
      "Bbm": "Db",
      "Ebm": "Gb",
      "Abm": "Cb"
  }

  mixolydian = {
      "G#": "C#",
      "C#": "F#",
      "F#": "B",
      "B": "E",
      "E": "A",
      "A": "D",
      "D": "G",
      "G": "C",
      "C": "F",
      "F": "Bb",
      "Bb": "Eb",
      "Eb": "Ab",
      "Ab": "Db",
      "Db": "Gb",
      "Gb": "Cb"
  }

  dorian = {
      "D#": "C#",
      "G#": "F#",
      "C#": "B",
      "F#": "E",
      "B": "A",
      "E": "D",
      "A": "G",
      "D": "C",
      "G": "F",
      "C": "Bb",
      "F": "Eb",
      "Bb": "Ab",
      "Eb": "Db",
      "Ab": "Gb",
      "Db": "Cb"
  }

  phrygian = {
      "E#": "C#",
      "A#": "F#",
      "D#": "B",
      "G#": "E",
      "C#": "A",
      "F#": "D",
      "B": "G",
      "E": "C",
      "A": "F",
      "D": "Bb",
      "G": "Eb",
      "C": "Ab",
      "F": "Db",
      "Bb": "Gb",
      "Eb": "Cb"
  }

  lydian = {
      "F#": "C#",
      "B": " F#",
      "E": " B",
      "A": " E",
      "D": " A",
      "G": " D",
      "C": " G",
      "F": " C",
      "Bb": "F",
      "Eb": "Bb",
      "Ab": "Eb",
      "Db": "Ab",
      "Gb": "Db",
      "Cb": "Gb",
      "Fb": "Cb"
  }

  locrian = {
      "B#": "C#",
      "E#": "F#",
      "A#": "B",
      "D#": "E",
      "G#": "A",
      "C#": "D",
      "F#": "G",
      "B": "C",
      "E": "F",
      "A": "Bb",
      "D": "Eb",
      "G": "Ab",
      "C": "Db",
      "F": "Gb",
      "Bb": "Cb"
  }

  sharp = {
      "7": "C#",
      "6": "F#",
      "5": "B",
      "4": "E",
      "3": "A",
      "2": " D",
      "1": " G",
      "0": " C"
  }

  flat = {
      "0": " C",
      "1": " F",
      "2": " Bb",
      "3": " Eb",
      "4": " Ab",
      "5": "Db",
      "6": "Gb",
      "7": "Cb"
  }
  dictionaries = {
      "ion": None,
      "m": aeolian,
      "mix": mixolydian,
      "Dor": dorian,
      "Phr": phrygian,
      "Lyd": lydian,
      "Loc": locrian,
      "sharp": sharp,
      "flat": flat,
  }

  words = {
      "ion": "Ionian",
      "m": "Aeolian",
      "mix": "Mixolydian",
      "Dor": "Dorian",
      "Phr": "Phrygian",
      "Lyd": "Lydian",
      "Loc": "Locrian",
      "sharp": "Sharp",
      "flat": "Flat",
  }

  def compile(self):
    self.word = ""
    self.key = self.value
    value = self.value
    if value.lower() == "none":
      self.value = "None"
      self.key = "None"
    elif value == "HP":
      self.value = "HP"
      self.key = "HP"
    elif value == "Hp":
      self.value = "F#"
      self.key = "F#"
    else:
      key = ""
      group = ""
      value = ""
      for match in pattern_key.finditer(self.value.lower()):
        if match.group(1) and match.group(2):
          key = match.group(1).strip()
          group = match.group(2).strip()
          if group not in self.words:
            continue
          word = self.words[group]
          if group not in self.dictionaries:
            continue
          dictionary = self.dictionaries[group]
          if dictionary:
            if len(key) == 1:
              key = key.upper()
            else:
              key = "{}{}".format(key[0].upper(), key[1].lower())
            if key in dictionary:
              new_key = dictionary[key]
              self.key = new_key
          else:
            pass

          break
        self.key = "{} {}".format(key, word)

  def __str__(self):
    return "%s·%s·" % (self.__class__.__name__, self.key)


#-------------------------------------------------------------------------------------------
class Parts(NamelessTag):

  @staticmethod
  def check(string): 
    stack = [] 
    for i in string: 
      if i == '(': 
        stack.append(i) 
      elif i == ')':
        if not stack:
          return False
        stack.pop() 
    if not stack:
      return True
    else:
      return False
      
  @staticmethod
  def get_prev_matching_parens_idx(string):
    stack = []
    for idx in range(len(string) - 1, -1, -1):
      val = string[idx]
      if val == ")":
        stack.append(val)
      elif val == "(":
        if not stack:
          return idx
        stack.pop()
    return 0


  @staticmethod
  def expand(items):
    chars = items.replace(" ", "")
    chars = chars.replace(".", "")
    all_chars = ""
    all_chars_idx = 0
    prev = None
    for val in chars:
      if val.isdigit():
        mult = int(val) - 1
        if prev == ")":
          start_idx = Parts.get_prev_matching_parens_idx(all_chars[0:all_chars_idx - 1])
          segment = all_chars[start_idx + 1:all_chars_idx - 1]
          add_string = (segment * mult)
        else:
          add_string = (prev * mult)
      else:
        add_string = val
      prev = val
      all_chars += add_string
      all_chars_idx += len(add_string)
    all_chars = all_chars.replace("(", "")
    all_chars = all_chars.replace(")", "")
    return all_chars

  def compile(self):
    self.parts = None
    if Parts.check(self.value):
      self.parts = Parts.expand(self.value)
    else:
      print("Error! Parts error: ", self.value)

  def __str__(self):
    return "%s·%s·" % (self.__class__.__name__, self.parts)


#-------------------------------------------------------------------------------------------
def get_pair(string):
  name = ''
  value = ''
  result = string.split(" ", 1)
  if len(result) > 1:
    name = result[0]
    value = result[1]
  else:
    name = result[0]
  return (name, value)
  
class Instruction(NamelessTag):
  
  def compile(self):
    if isinstance(self.value, str):
      value = []
      value.append(self.value)
      self.value = value
    if isinstance(self.value, list):
      new = []
      for v in self.value:
        if isinstance(v, list):
          new.extend(v)
        else:
          new.append(v)
      self.value = new
      self.category = 'Instructions'
      value_dict = OrderedDict()
      for v in self.value:
        name, value = get_pair(v)
        if name not in value_dict:
          value_dict[name] = []
        value_dict[name].append(value)
      self.value = value_dict

  def process(self):
    global abc_header
    for key in self.value.keys():
      if key == 'abc-include':
        values = self.value[key]
        for value in values:
          include_lines = read_lines(value)
          include = AbcInclude(include_lines)
          if abc_header:
            abc_header.add_include(include)
          else:
            print('ERROR: abc_header invalid')

  def __str__(self):
    if isinstance(self.value, OrderedDict):
      keys = list(self.value.keys())
      return "%s·%s·" % (self.__class__.__name__, keys)
    else:
      return "%s·%s·" % (self.__class__.__name__, self.value)


class MidiInstruction(Instruction):
  indexes = {}
  programs = {}
  
  @staticmethod
  def initialize(lines):
    for line in lines:
      items = line.split(" ", 1)
      index = items[0].strip()
      prg = items[1].strip()
      MidiInstruction.programs[prg] = index
      MidiInstruction.indexes[index] = prg

  def compile(self):
    value = self.value['MIDI'][0]
    result = value.split(" ", 1)
    self.value = ''
    if len(result) > 1:
      self.value = result[1]
    res = result[0].upper()
    if res.startswith('CHAN'):
      res = 'CH'
    elif res.startswith('PROG'):
      res = 'PRG'
      # get name of value if given int
      try:
        value = int(self.value)
        value_name = self.indexes[str(value)]
      except:
        # else, get int by searching closest match
        # full match first
        value = self.value.lower()
        values = value.split(" ")
        value_name = ''
        for program in self.programs.keys():
          if value == program.lower():
            value = self.programs[program]
            value_name =  self.indexes[value]
            break
        # then match n - 1 words, so on
        if not value_name:
          for program in self.programs.keys():
            all_match = True
            for val in values:
              if val not in program.lower():
                all_match = False
                break
            if all_match:
              value = self.programs[program]
              value_name =  self.indexes[value]
              break
        if not value_name:
          if len(values) > 1:
            del values[-1]
          for program in self.programs.keys():
            all_match = True
            for val in values:
              if val not in program.lower():
                all_match = False
                break
            if all_match:
              value = self.programs[program]
              value_name =  self.indexes[value]
              break
        if not value_name:
          if len(values) > 1: 
            values = values[0]
          for program in self.programs.keys():
            all_match = True
            if values not in program.lower():
              all_match = False
              break
            if all_match:
              value = self.programs[program]
              value_name =  self.indexes[value]
              break
                
      self.value = int(value)
      self.value_name = value_name
      
    self.category = res
      

  def __str__(self):
    if self.category == 'PRG':
      return "%s·%s·" % (self.__class__.__name__, self.value_name)
    else:
      return "%s·%s%s·" % (self.__class__.__name__, self.category, self.value)


#-------------------------------------------------------------------------------------------
class Voice(NamelessTag):
  
  @staticmethod
  def process_string(string):
    result = string.split(" ", 1)
    name = result[0]
    value = ''
    if len(result) > 1:
      value = process_pattern_to_dictionary(result[1], pattern_voice)
    return name, value

  @staticmethod
  def compile_tags(kvp):
    for key in kvp:
      if key in ALL_TAGS:
        tag = Tag(key, kvp[key])
        tag = Header.subclass(tag.name, tag)
        kvp[key] = tag
        
  def compile(self):
    if isinstance(self.value, str):
      self.name, kvp = self.process_string(self.value)
      self.compile_tags(kvp)
      self.voice = kvp
    elif isinstance(self.value, list):
      self.name = 'Voices'
      self.voices = {}
      for v in self.value:
        name, kvp = self.process_string(v)
        self.compile_tags(kvp)
        self.voices[name] = kvp

  def __str__(self):
    if isinstance(self.value, str):
      return "%s·%s:%s·" % (self.__class__.__name__, self.name, self.voice)
    else:
      return "%s·%s·" % (self.name, self.voices)


"""
======================================================================================================
======================================================================================================
                                  ***  H  E  A  D  E  R  ***
======================================================================================================
"""

class Header(object):
  VALID_TAGS = ALL_TAGS
  TAG_CLASS_MAP = {
      "M": Metre,
      "L": Length,
      "Q": Tempo,
      "K": Key,
      "P": Parts,
      "B": Book,
      "C": Composer,
      "D": Discography,
      "F": File,
      "G": Group,
      "H": History,
      "I": Instruction,
      "m": Macro,
      "N": Notes,
      "O": Origin,
      "R": Rhythm,
      "r": Remark,
      "S": Source,
      "s": Symbols,
      "T": Title,
      "U": User,
      "V": Voice,
      "W": Lyrics,
      "w": Words,
      "X": Reference,
      "Z": Transcriber
  }

  @staticmethod
  def subclass(name, tag):
    class_name = Header.get_class(name)
    if class_name:
      tag.__class__ = class_name
    return tag

  @staticmethod
  def get_class(tag_name):
    if tag_name in Header.TAG_CLASS_MAP:
      return Header.TAG_CLASS_MAP[tag_name]
    return None

  def __init__(self):
    self.header = OrderedDict()

  def has_tag(self, name):
    if name in self.header:
      return True
    return False

  def get_tag(self, name):
    if name in self.header:
      return self.header[name]
    else:
      print("Tag name not found: ", name)

  def set_tag(self, name, tag):
    if name != None and name in self.VALID_TAGS:
      if name in self.header:
        cur_tag = self.header[name]
        cur_tag.value = [cur_tag.value, tag.value]
      else:
        self.header[name] = tag
    else:
      print("Tag name not valid: ", name)

  def get_value(self, name):
    if name in self.header:
      return self.header[name].value
    return None

  def compile(self):
    for k in self.header:
      tag = self.header[k]
      tag = Header.subclass(k, tag)
      tag.compile()
      self.header[k] = tag

  def __str__(self):
    header_str = ""
    for k in self.header:
      header_str += str(self.header[k]) + "\n"
    return header_str

  def __repr__(self):
    return self.__str__()


#-------------------------------------------------------------------------------------------
class FileHeader(Header):
  VALID_TAGS = FILE_HEADER_TAGS

  def validate(self, add_defaults=True):
    # create default tags L M
    keys = list(self.header.keys())
    
    if add_defaults:
      if "L" not in keys:
        self.header["L"] = Tag("L", "1/8")
      if "M" not in keys:
        self.header["M"] = Tag("M", "C|")
      
    for k in self.header:
      tag = self.header[k]
      if isinstance(tag, Tag):
        self.header[k] = Header.subclass(tag.name, tag)
        tag.compile()
        self.header[k] = tag
     
    if "I" in keys:
      instructions = self.header['I']
      instructions.process()
        
  def add_include(self, abc_include):
    for key in abc_include.header.header.keys():
      value = []
      if key in self.header:
        value.append(self.header[key].value)
      #print('add_include value ', value)
      value.append(abc_include.header.header[key].value)
      self.header[key].value = value
    

#-------------------------------------------------------------------------------------------
class TuneHeader(Header):
  VALID_TAGS = TUNE_HEADER_TAGS

  def validate(self):
    # X must be first
    keys = list(self.header.keys())
    if keys[0] != "X":
      print("WARNING: X tag is not the first one")
    # T must be second
    if keys[1] != "T":
      print("WARNING: T tag is not the second one")
    # K must be last
    if keys[-1] != "K":
      print("WARNING: K tag is not the last one")


"""
======================================================================================================
======================================================================================================
                                  ***  E  L  E  M  E  N  T  S  ***
======================================================================================================
"""

class Element(object):

  def __init__(self, classtype):
    self._type = classtype

  def __str__(self):
    return "%s·%s·" % (self._type, self.symbol)

  def __repr__(self):
    return self.__str__()


def ClassFactory(classtype, argnames, BaseClass=Element):

  def __init__(self, **kwargs):
    for key, value in kwargs.items():
      # here, the argnames variable is the one passed to the ClassFactory call
      if key not in argnames:
        raise TypeError("Argument %s not valid for %s" %
                        (key, self.__class__.__name__))
      setattr(self, key, value)
    try:
      BaseClass.__init__(self, classtype)
    except:
      self._type = classtype
      pass

  newclass = type(classtype, (BaseClass,), {"__init__": __init__})
  return newclass

Repeat = ClassFactory("Repeat", "symbol")
    
setattr(Repeat, 'count', 0)

StartRepeat = ClassFactory("StartRepeat", "symbol", BaseClass=Repeat)

EndRepeat = ClassFactory("EndRepeat", "symbol start", BaseClass=Repeat)
def pop(self):
  if self.stack:
    self.stack -= 1
    
def reset(self):
  self.stack = self.count
  
def is_empty(self):
  return not self.stack
    
def __str__(self):
  return "%s·%s·" % (self._type, self.stack-1)

setattr(EndRepeat, 'start', 0)
setattr(EndRepeat, 'stack', 0)
setattr(EndRepeat, 'pop', pop)
setattr(EndRepeat, 'is_empty', is_empty)
setattr(EndRepeat, 'reset', reset)
setattr(EndRepeat, '__str__', __str__)

AltEnding = ClassFactory("AltEnding", "symbol endings")
def __str__AltEnding(self):
  return "%s·%s·" % (self._type, self.endings)
setattr(AltEnding, 'endings', [])
setattr(AltEnding, '__str__', __str__AltEnding)

Bar = ClassFactory("Bar", "symbol")
Tie = ClassFactory("Tie", "symbol")
Overlay = ClassFactory("Overlay", "symbol")
Duplet = ClassFactory("Duplet", "symbol")
Gt = ClassFactory("Gt", "symbol")
Lt = ClassFactory("Lt", "symbol")
Sp = ClassFactory("Sp", "symbol")
SlurStart = ClassFactory("SlurStart", "symbol")
SlurEnd = ClassFactory("SlurEnd", "symbol")
ChordStart = ClassFactory("ChordStart", "symbol")
ChordEnd = ClassFactory("ChordEnd", "symbol")
GraceNoteStart = ClassFactory("GraceNoteStart", "symbol")
GraceNoteEnd = ClassFactory("GraceNoteEnd", "symbol")

#-------------------------------------------------------------------------------------------
InvalidSymbol = ClassFactory("InvalidSymbol", "symbol")
def __str__InvalidSymbol(self):
  return "¿%s?" % (self.symbol)
setattr(InvalidSymbol, '__str__', __str__InvalidSymbol)

UserSymbol = ClassFactory("UserSymbol", "symbol")

class Symbol(Element):
  valid_symbols = {}

  @staticmethod
  def initialize_symbols(lines):
    for line in lines:
      line = line.strip()
      if not line:
        continue
      line = line.lower()
      Symbol.valid_symbols[line] = None

  def __init__(self, symbol):
    self.symbol = symbol[1:-1]
    if self.symbol in self.valid_symbols:
      self._type = Symbol
    else:
      self._type = InvalidSymbol
      setattr(self, '__class__', InvalidSymbol)

  def __str__(self):
    return "!%s!" % (self.symbol)

  def __repr__(self):
    return self.__str__()



#-------------------------------------------------------------------------------------------
class Space(Element):

  def __init__(self, symbol):
    self._type = Space
    self.symbol = symbol

  def __str__(self):
    return " "

  def __repr__(self):
    return self.__str__()


#-------------------------------------------------------------------------------------------
class Chorded(Element):

  def __init__(self, symbol):
    self._type = Note
    self.symbol = symbol

  def __str__(self):
    return "Chorded·%s·" % (self.symbol)

  def __repr__(self):
    return self.__str__()



#-------------------------------------------------------------------------------------------
#-------------------------------------------------------------------------------------------
class Note(Element):
  frequencies = None
  midi_notes = None

  def __init__(self, symbol):
    self._type = Note
    self.symbol = symbol
    matches = pattern_note.findall(symbol)
    for match in matches:
      self.gstem = match[0]
      self.chord = match[1]
      self.chord_level = match[2]
      self.decorations = match[3]
      self.accidental = match[5]
      self.octaves = match[6]

      self.plain_note = match[4]
      if '=' in self.plain_note:
        self.plain_note = self.plain_note.replace('=', '')
      if '^' in self.plain_note:
        self.plain_note = self.plain_note.replace('^', '')
      if '#' in self.plain_note:
        self.plain_note = self.plain_note.replace('#', '')
      self.compound_note = self.plain_note + self.accidental + self.octaves

      #print("note: ", self.compound_note, " acc: ", self.accidental, " oct: ", self.octaves)
      self.frequency = self.frequencies.get(self.plain_note, self.accidental,
                                            self.octaves)

      self.op = None
      self.mul = None
      self.div = None
      if match[7]:
        self.mul = int(match[7])
      if match[8]:
        self.op = match[8]
      if match[9]:
        self.div = int(match[9])

      self.length = 1
      if self.mul:
        self.length *= self.mul
      if self.div:
        self.length /= self.div

  def __str__(self):
    return "·%s·" % (self.symbol)

  def __repr__(self):
    return self.__str__()



"""
======================================================================================================
======================================================================================================
                                  ***  D  I  R  E  C  T  O  R  ***
======================================================================================================
"""

PartLocation = namedtuple("PartLocation", "line index")


class Director(object):

  def __init__(self, player):
    self.player = player
    self.symbols = Symbol.valid_symbols.copy()
    self.line_symbols = User.default_symbols.copy()

  def _on_change_tempo(self):
    self._calculate_duration()
  
  def _on_change_length(self):
    self._calculate_duration()
  
  def _on_change_metre(self):
    pass
  
  def _on_change_key(self):
    pass
  
  def _on_change_user(self, tag):
    self.line_symbols[tag.symbol] = tag.value
  
  def _change_tag(self, tag):
    if isinstance(tag, Length):
      self.length = tag
      self._on_change_length()
    elif isinstance(tag, Tempo):
      self.tempo = tag
      self._on_change_tempo()
    elif isinstance(tag, Metre):
      self.metre = tag
      self._on_change_metre()
    elif isinstance(tag, Key):
      self.key = tag
      self._on_change_key()
    elif isinstance(tag, User):
      self._on_change_user(tag)
  
  def _calculate_duration(self):
    self.bpm = self.tempo.bpm
    self.tempo_ratio = 60 / self.bpm
    self.length_ratio = self.length.ratio
    self.duration = self.tempo_ratio * self.length_ratio
    
  def _read_tag(self, song):
    # by now file and song headers have values 
    self.rithm = None
    self.voice = None
    if song.header.has_tag('R'):
      self.rithm = song.header.get_tag("R")
    if song.header.has_tag('V'):
      self.voice = song.header.get_tag("V")
      
    self.key = song.header.get_tag("K")
    self.length = song.header.get_tag("L")
    self.metre = song.header.get_tag("M")
    self.tempo = song.header.get_tag("Q")
    # these values can change as we iterate through the song
    self._calculate_duration()
    
  def _read(self, song):
    self.lines = song.lines
    self._read_tag(song)

    # all content (tags, lines, notes) has been parsed into a list
    # all items in list are either a note or a tag
    # initialize player tunes
    parts_to_location = {}
    for i, line in enumerate(self.lines):
      if isinstance(line, User):
        self._change_tag(line)
      if isinstance(line, Tag):
        continue
      for j, item in enumerate(line):
        if isinstance(item, User):
           self._change_tag(item)
        elif isinstance(item, Tag):
          if isinstance(item, Parts):
            parts_to_location[item.value] = PartLocation(line=i, index=j)
          else:
            self._change_tag(item)
        elif isinstance(item, Note):
          duration = self.duration * item.length
          self.player.add_note(item, duration)
        elif isinstance(item, Element):
          pass
        else:
          if item in self.line_symbols.keys():
            us = UserSymbol(symbol=item)
            del line[j]
            line.insert(j, us)
          #else:
          #  print('ERROR! item not a note, element or tag: ', type(item), item)

    self.song_path = []
    self.parts_playing = {}
    if song.header.has_tag('P'):
      parts = song.header.get_tag('P')
      for i, part in enumerate(parts.parts):
        part_location = parts_to_location[part]
        self.song_path.append(part_location)
        self.parts_playing[i] = 0
    else:
      for i in range(0, len(self.lines)):
        self.song_path.append(PartLocation(line=i, index=0))
        self.parts_playing[i] = 0

    self.voices_map = {}
    current_voice_name = '1'
    for i, line in enumerate(self.lines):
      if isinstance(line, Voice):
        current_voice_name = line.name
      elif isinstance(line, list):
        new_voice_name = self.get_voice_name(line)
        if new_voice_name:
          current_voice_name = new_voice_name
      if current_voice_name not in self.voices_map:
        self.voices_map[current_voice_name] = []
      self.voices_map[current_voice_name].append(i)
      
    #print('LINE SYMBOLS: ', self.line_symbols.keys())
    self._read_tag(song)
    
  def get_voice_name(self, line):
    for item in line:
      if isinstance(item, Voice):
        return item.name
    return ""
        
    
  def play(self, song, voice):
    self._read(song)
    print('====================================================\r')
    print("SONG HEADER")
    print(song.header)
    print("\r")
    print('====================================================\r')
    print("SONG song_path ", self.song_path)
    print("SONG parts_playing ", self.parts_playing)
    print("SONG voices_map ", self.voices_map)

    print("PLAY SONG")
    voice_line_indexes = self.voices_map[voice]
    #print('Playing Voice lines: ', voice_line_indexes)
    #print('Playing Parts: ', self.parts_playing)
    #print('Playing lines count: ',len(self.lines))
    #print('Playing parts_playing count: ',len(self.parts_playing))
    for line_index, item_index in self.song_path:
      line = self.lines[line_index]
      if isinstance(line, MidiInstruction):
        self.player.command(line)
      if isinstance(line, Tag):
        print('Tag line: ', line_index, ' --- ', line)
        self._change_tag(line)
        continue
      if line_index not in voice_line_indexes:
        print('Skipping line: ', line_index)
        continue
      #print('indexes line_index: ', line_index, ' item_index: ', item_index)
      self.parts_playing[item_index] = self.parts_playing[item_index] + 1
      part_number = self.parts_playing[item_index]
      #print('Playing part_number: ', part_number)
      print('Playing line: ', line_index, ":", item_index, " --- ", ''.join(str(v) for v in line))
      print('···SOL···')
      note_index = 0
      while note_index < len(line):
        item = line[note_index]
        if isinstance(item, AltEnding):
          # skip if not alt ending to be played
          if part_number not in item.endings:
            #print('Skipping Ending: ', item.endings)
            for index in range(note_index+1, len(line)):
              skip_item = line[index]
              if isinstance(skip_item, Bar) and len(skip_item.symbol) > 1 or isinstance(skip_item, Repeat) or isinstance(skip_item, AltEnding):
                note_index = index
                break
          else:
            print('Playing Ending: ', part_number)
        elif isinstance(item, UserSymbol):
          print(item, '=', self.line_symbols[item.symbol])
        elif isinstance(item, Tag):
          self._change_tag(item)
        elif isinstance(item, SlurStart) or isinstance(item, SlurEnd):
          self.player.slur()
        elif note_index > item_index and isinstance(item, Note):
          duration = self.duration * item.length
          self.player.play(item, duration)
        elif isinstance(item, Space):
          pass
        elif isinstance(item, Element):
          if isinstance(item, EndRepeat):
            item.pop()
            if not item.is_empty():
              print('Repeat: ', item.stack)
              note_index = item.start
          else:
            print(item)
        note_index += 1
      print('···EOL···\n')
      # reset repeat bars
      for item in line:
        if isinstance(item, EndRepeat):
          item.reset()



"""
======================================================================================================
======================================================================================================
                                  ***  M  A  I  N  ***
======================================================================================================
"""

def main():

  parser = argparse.ArgumentParser(description='abc parser and player')
  parser.add_argument('-f','--file', help='Abc file path', required=False, default='songs.abc')
  parser.add_argument('-s','--song', help='Song number to play. X tag.', required=True, default=1)
  parser.add_argument('-v','--voice', help='Voice number to play. V tag.', required=False, default='1')
  parser.add_argument('-p','--player', help='Player type: dummy(default) speaker, tune, midi', required=False, default='dummy')
  args = vars(parser.parse_args())

  file_path = os.path.expanduser(args['file'])
  song_index = int(args['song'])
  voice = args['voice']
  if not voice:
    voice = '1'
  voice = voice.strip()
  player = args['player']
  print('====================================================\r')
  print('COMAND LINE')
  print('File: \t', file_path)
  print('Song: \t', song_index)
  print('Voice: \t', voice)
  print('Player:\t', player)
  print('\r\n====================================================\r')
  print('FILE HEADER')

  piano_frequency_lines = read_lines("frequencies_piano.txt")
  frequency_lines = read_lines("frequencies.txt")
  midi_programs_lines = read_lines("midi_programs.txt")
  symbols_lines = read_lines("symbols.txt")
  Symbol.initialize_symbols(symbols_lines)
  
  Note.frequencies = Frequencies(piano_frequency_lines)
  Note.midi_notes = MidiNotes(frequency_lines, piano_frequency_lines)

  MidiInstruction.initialize(midi_programs_lines)
  songs_lines = preprocess_lines(read_lines(file_path))
  abc_file = AbcFile(songs_lines)

  if player == 'speaker':
    player = SpeakerPlayer()
  elif player == 'tune':
    player = TunePlayer()
  elif player == 'midi':
    player = MidiPlayer(Note.midi_notes)
  else:
    player = PrintPlayer()
    
  player.start()
  director = Director(player)
  director.play(abc_file.get_song(song_index), voice)
  player.stop()


if __name__ == "__main__":
  main()
  
  
  
"""
####################################################################

Correct Order of Elements
<grace notes><chord symbols><decorations><accidentals>
<N O T E>
<octave><note length><tie>

pattern_gt = re.compile(r"\>")
pattern_lt = re.compile(r"\<")

TIE
(p:q:r    p notes in time of q for next r notes


Notes
C,,   C,    C (middle-C)    c     c'    c''

^         sharp
^^        double sharp
=         natural
_         flat
__        double flat
z         rest
Z         bar's rest
x         invisible rest
X         invisible bar rest
y         spacer


Chord Symbols
m or min    minor e.g. "Am7"A2D2
maj         major
dim         diminished
aug or +    augmented
sus         sustained
7, 9 ... 7th, 9th, etc.

Dynamics
!crescendo(! or !<(!      start of a < crescendo mark
!crescendo)! or !<)!      end of a < crescendo mark, placed after the last note
!diminuendo(! or !>(!     start of a > diminuendo mark
!diminuendo)! or !>)!     end of a > diminuendo mark, placed after the last note
!trill(! and !trill)!




* Clefs
treble      Treble (default)
treble-8    Treble 8ve below eg.tenors
treble+8    Treble 8ve above eg.piccolo
bass        Bass
bass3       Baritone
alto4       Tenor
alto        Alto
alto2       Mezzosoprano
alto1       Soprano
none        No clef
perc        Percussion

** Voices
The voice name is a digit or a word followed by:
clef=       clef of the voice
perc        percussion staff
name=xxx    name at the left of the first staff
sname=xxx   name that appears left of later staves
merge       indicates that this voice belongs to
            the same staff as the previous voice
up or down            forces the note stem direction
gstem=up/down/auto    forces the grace note stem direction
stem=up/down/auto     forces the note stem direction
dyn=up/down/auto      forces the placement of dynamic marks
lyrics=up/down/auto   forces the placement of the lyrics
middle=<note>         specify name of note on middle line
staffscale=n          sets the scale of the associated staff
stafflines=n          sets the number of lines of the staff

Lyrics
-   break between syllables within a word
_   last syllable is to be held for an extra note
*   one note is skipped
~   appears as a space; puts multiple words under note
\-  appears as hyphen; multiple syllables under note
|   advances to the next bar


s:symbol line s: !pp! ** !f!

   CDEF    | G```AB`c
s: "^slow" | !f! ** !fff!

   C2  C2 Ez   A2|
s: "C" *  "Am" * |
s: *   *  !>!  * |


Text Annotations
"..."
"^..."      above staff
"_..."      below staff
"<..."      left of note
">..."      right of note
"@x,y ..."  explicit offset

----------------------------------------------------
http://www.ascii-code.com/
http://www.stephenmerrony.co.uk/uploads/ABCquickRefv0_6.pdf
http://trillian.mit.edu/~jc/music/abc/doc/ABCtut_Headers.html
http://trillian.mit.edu/~jc/music/abc/doc/ABCprimer.html
http://www.lesession.co.uk/abc/abc_notation.htm
http://abcnotation.com/wiki/abc:standard:v2.1#englishabc
http://abcnotation.com/learn

"""
