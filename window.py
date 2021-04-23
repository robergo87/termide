import os
import io
import gi
import threading
import json
import socket
import subprocess
import shlex



gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Vte, Gdk 
from gi.repository import GLib


PIPE_PATH = "/tmp/{}.termide".format(os.getpid())
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

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

class Terminal(Vte.Terminal):
    def __init__(self, title, directory=None, commands = []):
        super().__init__()
        self.title = title
        self.set_clear_background(False)
        self.spawn_sync(
            Vte.PtyFlags.DEFAULT,
            directory if directory else os.environ['HOME'],
            commands if commands else bash(), 
            [
                "TERMIDE_PIPE_PATH={}".format(PIPE_PATH),
                "PATH={}".format(os.environ["PATH"] + os.pathsep + os.path.join(ROOT_DIR, "script"))
            ],
            GLib.SpawnFlags.DO_NOT_REAP_CHILD,
            None, None,
        )
        self.connect("eof", self.event_eof)
        self.connect("focus_in_event", self.event_focus)
        self.termno = -1

    def event_eof(self, event):
        self.prnt.rem_terminal(self.termno)

    def event_focus(self, *args):
        self.prnt.tab_focused()

class TermTabs(Gtk.Box):
    def add_terminal(self, title, directory=None, commands=[]):
        title = title if title else "Default"
        term = Terminal(title, directory, commands)
        term.prnt = self
        term.termno = len(self.terminals)
        term.show()
        self.terminals.append(term)
        self.stack.add_titled(term, str(len(self.terminals)), title)

    def rem_terminal(self, termno):
        term = self.terminals[termno]
        self.stack.remove(term)
        del self.terminals[termno]
        if not self.terminals:
            self.get_parent().remove_tab(self)
                            
    def __init__(self, title=None, directory=None, commands=[]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.stack = Gtk.Stack()
        self.set_border_width(10)
        #stack
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(100)
        self.stack.show()
        #switcher
        self.switcher = Gtk.StackSwitcher()
        self.switcher.set_stack(self.stack)
        #self.switcher.show()
        #mount
        self.pack_start(self.switcher, False, True, 0)
        self.pack_start(self.stack, True, True, 0)        
        #initial
        self.terminals = []
        self.add_terminal(title, directory, commands)
        self.pos = ""
        self.ide = None
        self.tabno = -1
        self.connect("focus-in-event", self.event_focus_in)
        #self.connect("clicked", self.event_focus_in)
        
    def get_tabs(self):
        return [self]
        
    def split(self, title=None, directory=None, commands=[], orient="v"):
        self.get_parent().split(self, title, directory, commands, orient)

    def event_focus_in(self):
        if self.ide:
            self.ide.tab_focused(self.tabno)

    def tab_focused(self):
        if self.ide:
            self.ide.tab_focused(self.tabno)

class TermSplit(Gtk.Paned):
    def __init__(self, tabfirst, tablast, orient="v"):
        orient_int = (
            Gtk.Orientation.VERTICAL 
            if orient == "v" else
            Gtk.Orientation.HORIZONTAL
        )
        super().__init__(orientation=orient_int)
        self.pos = ""
        self.orient = orient
        tabfirst.pos = "first"
        tablast.pos = "last"
        self.first = tabfirst
        self.last = tablast
        self.pack1(tabfirst, True, True)
        self.pack2(tablast, True, True)
        self.show()
        self.first.show()
        self.last.show()

    def get_tabs(self):
        return self.first.get_tabs() + self.last.get_tabs()

    def split(self, tab, title=None, directory=None, commands=[], orient="v"):
        oldtab = self.first if tab.pos == "first" else self.last
        newtab = TermTabs(title, directory, commands)
        self.remove(oldtab)
        lastpos = self.get_position()
        if tab.pos == "first":
            self.first = TermSplit(oldtab, newtab, orient)
            self.pack1(self.first, True, True)
            self.first.show()
        else:   
            self.last = TermSplit(oldtab, newtab, orient)
            self.pack2(self.last, True, True)
            self.last.show()
        self.set_position(lastpos)
    
    def remove_tab(self, obj):
        self.remove(self.last)
        self.remove(self.first)
        ide = self.get_toplevel()
        if obj.pos == "first":
            self.get_parent().replace_obj(self, self.last)
        else:
            self.get_parent().replace_obj(self, self.first)
            ide.server.current_tab -= 1
        ide.recreate_tabs()
        child = ide.tabs[ide.server.current_tab].stack.get_visible_child()
        if child:
            child.grab_focus()
    
    def replace_obj(self, oldobj, newobj):
        self.remove(oldobj)
        lastpos = self.get_position()
        if oldobj.pos == "first":
            self.pack1(newobj)
            newobj.show()
            self.first = newobj
        else:
            self.pack2(newobj)
            newobj.show()
            self.last = newobj
        self.set_position(lastpos)    
    
    def resize(self, step_x, step_y):
        if step_x and self.orient == "h":
            self.set_position(self.get_position()+step_x)
            step_x = 0
        if step_y and self.orient == "v":
            self.set_position(self.get_position()+step_y)
            step_y = 0
        if step_x or step_y:
            self.get_parent().resize(step_x, step_y)
        return True


class TermIDE(Gtk.Window):
    def recreate_tabs(self):
        self.tabs = self.content.get_tabs()
        for tabno, tab in enumerate(self.tabs):
            tab.tabno = tabno
            tab.ide = self

    def __init__(self, title="TERMIDE", directory=None, commands=[]):
        super().__init__(title=title)
        self.tabs = []
        self.connect("destroy", self.event_destroy)
        self.connect("key_press_event", self.event_keypress)
        self.resize(900, 600)
        self.content = TermTabs("default")
        self.add(self.content)
        self.content.show()
        self.content.prnt = self
        self.show()
        self.recreate_tabs()
        self.pos = ""
        self.server = None
        self.pipe_path = "tmp/{}.termide".format(os.getpid())
        self.keybinds = {}

    def shell_exec(self, action):
        env = {
            "TERMIDE_PIPE_PATH": PIPE_PATH,
            "PATH": os.environ["PATH"] + os.pathsep + os.path.join(ROOT_DIR, "script")
        }
        subprocess.run(action ,  env=env)
             
    def event_keypress(self, widget, event):
        #decode keycode
        keycode = []
        if event.state & Gdk.ModifierType.CONTROL_MASK:
            keycode.append("Control")
        if event.state & Gdk.ModifierType.LOCK_MASK:
            keycode.append("Lock")
        if event.state & Gdk.ModifierType.SHIFT_MASK:
            keycode.append("Shift")
        if event.state & Gdk.ModifierType.MOD1_MASK:
            keycode.append("Alt")
        keycode.append(Gdk.keyval_name(event.keyval).capitalize())
        keycode = "+".join(keycode)
        #execute action
        if keycode in self.keybinds:
            for action in self.keybinds[keycode]:
                self.shell_exec(action)
            return True
        
    def event_destroy(self, event=None):
        send_command(["stop"])
        Gtk.main_quit(event)

    def split(self, tab=None, title=None, directory=None, commands=[], orient="v"):
        oldtab = tab if tab else self.content
        newtab = TermTabs(title, directory, commands)
        self.remove(self.content)
        self.content = TermSplit(oldtab, newtab, orient)
        self.add(self.content)    
        
    def resize(self, step_x, step_y):
        pass
        
    def tab_focused(self, curtabno):
        self.server.current_tab = curtabno
        for tabno, tab in enumerate(self.tabs):
            tab.set_opacity(1 if curtabno == tabno else 0.6)

    def remove_tab(self, obj):
        self.event_destroy()
            
    def replace_obj(self, oldobj, newobj):
        self.remove(oldobj)
        self.add(newobj)
        newobj.show()
        self.content = newobj


# TermIDE server

class SocketServer:
    def __init__(self, ide):
        #self.server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if os.path.exists(PIPE_PATH):
            os.remove(PIPE_PATH)        
        self.server.bind(PIPE_PATH)
        self.current_tab = 0
        self.ide = ide
        self.ide.server = self
        
    def __del__(self):
        self.server.close()
        os.remove(PIPE_PATH)

    def run(self):
        while True:
            self.server.listen(1)
            conn, addr = self.server.accept()
            message = conn.recv(1024)
            if not message:
                continue
            args = json.loads(message.decode("utf-8"))
            if not len(args) or args[0] == "stop":
                break
            try: 
                retval = getattr(self, "command_{}".format(args[0]))(*args[1:])
            except Exception as e:
                import traceback
                retval = [str(traceback.format_exc())]
            conn.send( ("\n".join(retval) if retval else "").encode("utf-8") )
            conn.close()
        return False
              
    def start(self):
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def command_tab(self, current_tab):
        self.current_tab = int(current_tab)
        self.ide.tabs[self.current_tab].stack.get_visible_child().grab_focus()
        return []
        
    def command_split(self, direction="v"):
        self.ide.tabs[self.current_tab].split(orient=direction)
        self.ide.recreate_tabs()
        self.ide.tabs[self.current_tab].stack.get_visible_child().grab_focus()
        return []

    def command_close(self, direction="v"):
        tab = self.ide.tabs[self.current_tab]
        tab.get_parent().remove_tab(tab)
        return []

    def command_quit(self):
        Gtk.main_quit()
        return []

    def command_move(self, direction="r"):
        def tabp(tab):
            geom = tab.stack.get_visible_child().get_allocation()
            geom2 = tab.translate_coordinates(tab.get_toplevel(), 0, 0)
            return {
                "x1": geom2[0], 
                "y1": geom2[1],
                "x2": geom2[0]+geom.width, 
                "y2": geom2[1]+geom.height,
                "xm": geom2[0]+int(geom.width/2), 
                "ym": geom2[1]+int(geom.height/2)
            }
        curpos = tabp(self.ide.tabs[self.current_tab])
        minlen = 10000000
        
        for tabno, tab in enumerate(self.ide.tabs):
            if tabno == self.current_tab:
                continue
            tabpos = tabp(tab)
            if direction == "l" and tabpos["x2"] >= curpos["x1"]:
                continue
            if direction == "r" and tabpos["x1"] <= curpos["x2"]:
                continue
            if direction == "u" and tabpos["y2"] >= curpos["y1"]:
                continue
            if direction == "d" and tabpos["y1"] <= curpos["y2"]:
                continue
            curlen = abs(tabpos["xm"]-curpos["xm"]) + abs(tabpos["ym"]-curpos["ym"])
            if curlen < minlen:
                minlen = curlen
                self.current_tab = tabno
        return self.command_tab(self.current_tab)
            
    def command_server_address(self):
        return [PIPE_PATH]

    def command_echo(self, *args):
        return list(args)
            
    def command_server_address(self):
        return [PIPE_PATH]
        
    def command_bind(self, keycode, *action):
        if not keycode in self.ide.keybinds:
            self.ide.keybinds[keycode] = []    
        self.ide.keybinds[keycode].append(action)    
        return []

    def command_resize(self, step_x, step_y):
        self.ide.tabs[self.current_tab].get_parent().resize(int(step_x), int(step_y))
    
    
ide = TermIDE()  
server = SocketServer(ide)
server.start()
ide.shell_exec( [os.path.join(ROOT_DIR, "templates", "default.sh")] )
Gtk.main()

    
