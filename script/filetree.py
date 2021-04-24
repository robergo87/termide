#!/usr/bin/python2

import sys, os

if len(sys.argv) < 3:
    print("Not enough arguments")
    print(sys.argv)
    exit(1)

action = sys.argv[1]
pid = sys.argv[2]
dirpath = os.path.abspath(sys.argv[3]) if len(sys.argv) >= 4 else ""

def get_file_path(pid):
    return "/tmp/rg-filetree-{}".format(pid)

def get_dir_list(pid):
    with open(get_file_path(pid)) as f:
        return f.read().split("\n")

def set_dir_list(pid, dirlist):
    with open(get_file_path(pid), "w") as f:
        f.write("\n".join(dirlist))

def print_listing(listing, root, indent=0, home=''):
    indent_code = "  " * indent
    for path in listing[root]["dir"]:
        basename = '\x1b[92m{}\x1b[0m'.format(os.path.basename(path))
        symbol = "-" if path in listing else "+"
        print("{};{};{}{}{}".format(path, path[len(home)+1:], indent_code, symbol, basename))
        if path in listing:
            print_listing(listing, path, indent+1, home)
    for path in listing[root]["file"]:
        basename = os.path.basename(path)
        basename = '\x1b[94m{}\x1b[0m'.format(os.path.basename(path))
        print("{};{}; {}{}".format(path, path[len(home)+1:], indent_code, basename))

if action == "init":
    with open(get_file_path(pid), "w") as f:
        set_dir_list(pid, [dirpath])
    exit(0)

if action == "destroy":
    os.remove(get_file_path(pid))
    exit(0)

if action == "opened":
   print("\n".join(get_dir_list(pid)))
   exit(0)

if action == "toggle":
    dirlist = get_dir_list(pid)
    if dirpath in dirlist:
        dirlist.remove(dirpath)
    else:
        dirlist.append(dirpath)
    set_dir_list(pid, dirlist)
    exit(0)

if action == "print":
    listing = {}
    openeddirlist = get_dir_list(pid)
    for curdir in openeddirlist:
        listing[curdir] = {"dir": [], "file": []}
        for filename in os.listdir(curdir):
            fullpath = os.path.join(curdir, filename)
            if os.path.isdir(fullpath):
                listing[curdir]["dir"].append(fullpath)
            else:
                listing[curdir]["file"].append(fullpath)
            listing[curdir]["dir"].sort()
            listing[curdir]["file"].sort()
    home = openeddirlist[0]
    print("{};..;..".format(os.path.dirname(openeddirlist[0])))
    print_listing(listing, openeddirlist[0], 0, home)

