#!/usr/bin/python3

import sys
import socket
import os
import json

pid = sys.argv[1]
action = sys.argv[2]
server_path = "/tmp/tree-{}".format(pid)

def error_log(msg):
    with open("/tmp/tree-debug-{}".format(pid), "a") as f:
        f.write(str(msg)+"\n")

# ------------ client side ------------------

if action != "init":
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(server_path)
    client.send(json.dumps(sys.argv[2:]).encode("utf-8"))
    resp = client.recv(20480).decode("utf-8")
    if resp:
        print(resp)
    client.close()
    sys.exit()

# ------------ server side ------------------

# ----- setup ----
if os.path.exists(server_path):
    os.remove(server_path)
server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(server_path)

homedir = sys.argv[3] if len(sys.argv) >= 4 else os.getcwd()
cmd_default = sys.argv[4] if len(sys.argv) >= 5 else None
cmd_optional = sys.argv[5] if len(sys.argv) >= 6 else None

opendirs = set()
    
# ----- actions ----
class Actions:
    def action_home(path):
        fullpath = os.path.abspath(path.split(";")[0].strip())
        homedir = os.path.abspath(fullpath)
        return homedir
        
    def action_open(path):
        fullpath = os.path.abspath(path.split(";")[0].strip())
        opendirs.add(fullpath)
        return "OK"

    def action_close(path):
        fullpath = os.path.abspath(path.split(";")[0].strip())
        opendirs.remove(fullpath)
        return "OK"

    def action_select(path):
        fullpath = os.path.abspath(path.split(";")[0].strip())
        if os.path.isdir(fullpath):
            if fullpath not in opendirs:
                opendirs.add(fullpath)
            else:
                opendirs.remove(fullpath)
            return Actions.action_list()   
        if not cmd_default:
            return Actions.action_list()
        basename = os.path.basename(fullpath)
        os.system(cmd_default.format(path=fullpath, file=basename))         
        return Actions.action_list()

    def action_alternative(path):
        fullpath = os.path.abspath(path.split(";")[0].strip())
        if not cmd_default:
            return Actions.action_list()
        basename = os.path.basename(fullpath)
        os.system(cmd_optional.format(path=fullpath, file=basename))         
        return Actions.action_list()

    def rspaces(fullpath, indent):
        retval = (
            os.get_terminal_size()[0] - indent - 1 
            - len(os.path.basename(fullpath))
        )
        retval = " " * retval if retval > 0 else ""
        return retval

    def listdir(path, indent):
        files = []
        dirs = []
        for filename in os.listdir(path):
            fullpath = os.path.abspath(os.path.join(path, filename))
            if os.path.isdir(fullpath):
                dirs.append(fullpath)
            else:
                files.append(fullpath)
        dirs.sort()
        files.sort()
        retval = []
        ind = "  " * indent
        for fullpath in dirs:
            basename = '\x1b[92m{}\x1b[0m'.format(os.path.basename(fullpath))
            symbol = "-" if fullpath in opendirs else "+"
            retval.append("{};{}{}{}{}".format(
                fullpath, ind, symbol, basename, 
                Actions.rspaces(fullpath, indent)
            ))
            if fullpath in opendirs:
                retval += Actions.listdir(fullpath, indent+1)
        for fullpath in files:
            basename = '\x1b[93m{}\x1b[0m'.format(os.path.basename(fullpath))
            symbol = "-" if fullpath in opendirs else "+"
            retval.append("{};{} {}{}".format(
                fullpath, ind, basename, 
                Actions.rspaces(fullpath, indent)
            ))
        return retval
        
    def action_list():
        dirtree = [] + Actions.listdir(homedir, 1)
        return "\n".join(dirtree)
        
        

# ----- main loop ----
try:
    while True:
        server.listen(1)
        conn, addr = server.accept()
        message = conn.recv(1024)
        if not message:
            continue
        msg = json.loads(message)
        error_log(msg)
        if msg[0] == "stop":
            break
        if not hasattr(Actions, "action_{}".format(msg)):
            retval = "no such action\n"
        try:
            action_name = "action_{}".format(msg[0])
            retval = getattr(Actions, action_name)(*msg[1:])
            if not retval:
                retval = "\n"
        except Exception as e:
            import traceback
            retval = "{}\n{}\n".format(str(e), str(traceback.format_exc()))
        conn.send(retval.encode("utf-8"))
        conn.close()
except Exception as e:
    import traceback
    retval = "{}\n{}\n".format(str(e), str(traceback.format_exc()))
    error_log(retval)

server.close()
os.remove(server_path)
