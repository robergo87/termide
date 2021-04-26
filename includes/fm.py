#!/usr/bin/python3

import sys
import os
import readline
from pathlib import Path
import shutil

import readline


def rlinput(prompt, prefill=''):
   readline.set_startup_hook(lambda: readline.insert_text(prefill))
   try:
      return input(prompt)
   finally:
      readline.set_startup_hook()
      
action = sys.argv[1].split(";")[0].strip()

if action == "actions":
    print("touch; Create New File")
    print("mkdir; Create New Directory")
    print("cp; Copy")
    print("mv; Rename / Move")
    print("rm; Delete")
    sys.exit()
    

path = os.path.abspath(sys.argv[2])
dirpath = path if os.path.isdir(path) else os.path.dirname(path)

if action in ("touch", "mkdir"):
    filetype = "File" if action == "touch" else "Directory"
    newfilename = rlinput("New {} Name:".format(filetype), "{}/".format(dirpath))
    if not newfilename:
        sys.exit()
    newfilename =  os.path.abspath(newfilename)
    if os.path.exists(newfilename):
        print("Path {} already exists!".format(newfilename))
        input("press any key to continue")
        sys.exit()
    newdirname = os.path.dirname(newfilename)
    if os.path.exists(newfilename):
        print("Directory {} doesn't exists!".format(newdirname))
        input("press any key to continue")
        sys.exit()
    if action == "touch":
        Path(newfilename).touch()
    else:
        os.mkdir(newfilename)
        
if action in ("cp", "mv"):
    print(path)
    filetype = "File" if not os.path.isdir(path) else "Directory"
    newfilename = rlinput("New {} Name:".format(filetype), path)
    if not newfilename:
        sys.exit()
    newfilename =  os.path.abspath(newfilename)
    if os.path.exists(newfilename):
        print("Path {} already exists!".format(newfilename))
        input("press any key to continue")
        sys.exit()
    newdirname = os.path.dirname(newfilename)
    if os.path.exists(newfilename):
        print("Directory {} doesn't exists!".format(newdirname))
        input("press any key to continue")
        sys.exit()
    if action == "cp":
        if os.path.isdir(path):
            shutil.copytree(path, newfilename)
        shutil.copy(path, newfilename)
    else:
        os.rename(path, newfilename)
    sys.exit()
    
if action == "rm":
    filetype = "file" if not os.path.isdir(path) else "firectory"
    print("Are you sure you want to remove {} {}?(n)".format(filetype, path))
    ans = input()
    if ans.lower() == "y":
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
    sys.exit()

