#!/usr/bin/python3

f = open('midi_programs.txt', "r")
lines = f.readlines()
f.close()

prgs_index = {}
index_prgs = {}
for line in lines:
  items = line.split(" ", 1)
  index = items[0].strip()
  prg = items[1].strip()
  prgs_index[prg] = index
  index_prgs[index] = prg

print('prgs_index ', prgs_index)
print('index_prgs ', index_prgs)



