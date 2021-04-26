import os
import shlex
import socket
import json

PIPE_PATH = "/tmp/{}.termide".format(os.getpid())
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def bash():
    return [
        "/bin/bash", "--rcfile", 
        os.path.join(ROOT_DIR, "script", "source.sh")
    ]

def shlex_join(split_command):
    return ' '.join(shlex.quote(arg) for arg in split_command)

def send_command(cmd):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(PIPE_PATH)
    client.send(json.dumps(cmd).encode("utf-8"))
    retval = client.recv(2048)
    client.close()
    return retval
