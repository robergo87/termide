#!/usr/bin/python3

import os
import io
import gi
import threading
import json
import socket
import subprocess
import shlex


gi.require_version("Gtk", "3.0")
gi.require_version('Vte', '2.91')

from gi.repository import Gtk, Vte, Gdk 
from gi.repository import GLib, GObject


from .util import PIPE_PATH, ROOT_DIR, bash, shlex_join, send_command


class Terminal(Vte.Terminal):
    default_dir = os.getcwd()
    
    def __init__(self, title, directory=None, commands = []):
        super().__init__()
        self.title = title
        self.set_color_background(Gdk.RGBA(0.2, 0.2, 0.2, 1))
        self.set_clear_background(False)
        self.spawn_sync(
            Vte.PtyFlags.DEFAULT,
            directory if directory else self.default_dir,
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
        self.tid = None
        self.add_tick_callback(self.tick_cb)
        
    def event_eof(self, event):
        self.prnt.rem_terminal(self.termno)

    def event_focus(self, *args):
        self.prnt.tab_focused()

    def getcwd(self):
        return self.default_dir
        try:
            return "/"+"/".join(self.get_current_directory_uri().split("/")[3:])
        except Exception as e:
            print("Exception path")
            print(e)
            return None

    def tick_cb(self, *args):
        self.prnt.tick_cb()
            
            
class SingleTerminalWindow(Gtk.Window):
    def __init__(self, title="TERMIDE", directory=None, commands=[]):
        super().__init__(title=title)
        self.tabs = []
        self.connect("destroy", self.event_destroy)
        self.content = Terminal(title, directory, commands)
        self.add(self.content)
        self.content.show()
        self.content.prnt = self
        self.show()
        self.set_opacity(0.95)
    
    def rem_terminal(self, termno):
        self.event_destroy(termno)
                
    def event_destroy(self, event=None):
        Gtk.main_quit(event)

    def tab_focused(self):
        pass

    def tick_cb(self, *args):
        pass
        
class TermTabs(Gtk.Box):
    def add_terminal(self, title, directory=None, commands=[]):
        title = title if title else "Default"
        scale = 1
        if not directory and self.terminals:
            term = self.stack.get_visible_child()
            directory = term.getcwd()
            scale = term.get_font_scale()
        term = Terminal(title, directory, commands)
        if scale != 1:
            term.set_font_scale(scale)
        term.prnt = self
        term.termno = len(self.terminals)
        self.terminals.append(term)
        self.stack.add_titled(term, str(len(self.terminals)), title)
        term.show()
        if len(self.terminals) > 1:
            self.switcher.show()
        self.add_tick_callback(self.tick_cb)
        return term

    def tick_cb(self, *args):
        self.get_parent().tick_cb()

    def rem_terminal(self, termno):
        term = self.terminals[termno]
        self.stack.remove(term)
        term.destroy()
        del self.terminals[termno]
        if not self.terminals:
            self.get_parent().remove_tab(self)
        if len(self.terminals) <= 1:
            self.switcher.hide()
                            
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
        self.add_tick_callback(self.tick_cb)
        
    def get_tabs(self):
        return [self]
        
    def split(self, title=None, directory=None, commands=[], orient="v"):
        term = self.stack.get_visible_child()
        if not directory:
            directory = term.getcwd()
        self.get_parent().split(self, title, directory, commands, orient)

    def event_focus_in(self):
        if self.ide:
            self.ide.tab_focused(self.tabno)

    def tab_focused(self):
        if self.ide:
            self.ide.tab_focused(self.tabno)
            
    def curterm(self):
        if len(self.terminals) == 1:
            return self.terminals[0]
        return self.stack.get_visible_child()

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
        self.add_tick_callback(self.tick_cb)

    def tick_cb(self, *args):
        self.get_parent().tick_cb()

    def get_tabs(self):
        return self.first.get_tabs() + self.last.get_tabs()

    def split(self, tab, title=None, directory=None, commands=[], orient="v"):
        oldtab = self.first if tab.pos == "first" else self.last
        newtab = TermTabs(title, directory, commands)
        newtab.terminals[0].set_font_scale(oldtab.curterm().get_font_scale())
        self.remove(oldtab)
        lastpos = self.get_position()
        if tab.pos == "first":
            self.first = TermSplit(oldtab, newtab, orient)
            self.pack1(self.first, True, True)
            self.first.pos = "first"
            self.first.show()
        else:   
            self.last = TermSplit(oldtab, newtab, orient)
            self.pack2(self.last, True, True)
            self.last.pos = "last"
            self.last.show()
        self.set_position(lastpos)
    
    def remove_tab(self, obj):
        self.remove(self.last)
        self.remove(self.first)
        ide = self.get_toplevel()
        if obj.pos == "first":
            self.get_parent().replace_obj(self, self.last)
            ide.server.current_tab = 0            
        else:
            self.get_parent().replace_obj(self, self.first)
            ide.server.current_tab -= 1
        ide.recreate_tabs()
        ide.tabs[ide.server.current_tab].stack.get_visible_child().grab_focus()
    
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

    def resize_first(self, step_x, step_y):
        if step_x and self.orient == "h":
            self.set_position(step_x)
            step_x = 0
        if step_y and self.orient == "v":
            self.set_position(step_y)
            step_y = 0
        if step_x or step_y:
            self.get_parent().resize_last(step_x, step_y)
        return True

    def resize_last(self, step_x, step_y):
        print(self.get_position())
        if step_x and self.orient == "h":
            self.set_position(self.get_allocation().width - step_x)
            step_x = 0
        if step_y and self.orient == "v":
            self.set_position(self.get_allocation().height - step_y)
            step_y = 0
        if step_x or step_y:
            self.get_parent().resize_last(step_x, step_y)
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
        self.content = None
        self.reset()
        self.pos = ""
        self.server = None
        self.pipe_path = "tmp/{}.termide".format(os.getpid())
        self.keybinds = {}
        self.show()
        self.add_tick_callback(self.tick_cb)
        self.update_cb = []

    def reset(self):
        if self.content:
            self.remove(self.content)
            self.content.destroy()
        self.content = TermTabs("default")
        self.add(self.content)
        self.content.show()
        self.content.prnt = self
        self.recreate_tabs()
        
    def update_tick(self, callback, params):
        self.update_cb.append((callback, params))
        
    def tick_cb(self, *args):
        if self.update_cb:
            self.update_cb[0][0](*self.update_cb[0][1])
            self.update_cb = self.update_cb[1:]
    
    def resize(self, step_x, step_y):
        pass

    def resize_first(self, step_x, step_y):
        pass

    def resize_last(self, step_x, step_y):
        pass

    def shell_exec(self, action, wait=True):
        env = {
            "TERMIDE_PIPE_PATH": PIPE_PATH,
            "PATH": os.environ["PATH"] + os.pathsep + os.path.join(ROOT_DIR, "script")
        }
        if wait:
            subprocess.run(action ,  env=env, close_fds=True)
        else:
            subprocess.Popen(
                action ,  env=env, close_fds=False, 
                stdin=None, stdout=None, stderr=None
            )
             
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
                #GObject.idle_add(self.shell_exec, action)
                self.shell_exec(action, wait=False)
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
            tab.curterm().set_clear_background(curtabno == tabno)

    def remove_tab(self, obj):
        self.event_destroy()
            
    def replace_obj(self, oldobj, newobj):
        self.remove(oldobj)
        self.add(newobj)
        newobj.show()
        self.content = newobj

