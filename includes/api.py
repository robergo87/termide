# TermIDE server

import os
import io
import gi
import threading
import json
import socket
import subprocess
import shlex


from .util import PIPE_PATH, ROOT_DIR, bash, shlex_join, send_command


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
            conn.send( ("\n".join(str(row) for row in retval) if retval else "").encode("utf-8") )
            conn.close()
            #self.ide.queue_draw()
        return False
              
    def start(self):
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def command_tab(self, current_tab):
        self.current_tab = int(current_tab)
        self.ide.tabs[self.current_tab].stack.get_visible_child().grab_focus()
        return []
        
    def command_split(self, direction="v", tabno=-1):
        tab = self.ide.tabs[self.current_tab if tabno == -1 else int(tabno)] 
        tab.split(orient=direction)
        self.ide.recreate_tabs()
        tab.stack.get_visible_child().grab_focus()
        return []

    def command_close(self, tabno=-1):
        tab = self.ide.tabs[self.current_tab if tabno == -1 else int(tabno)] 
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

    def command_server_address(self):
        return [PIPE_PATH]

    def command_resize(self, step_x, step_y, tabno=-1):
        tab = self.ide.tabs[self.current_tab if tabno == -1 else int(tabno)] 
        tab.get_parent().resize(int(step_x), int(step_y))

    def command_term_add(self, tabno=-1, title="default", command=None):
        command_lst = json.loads(command) if command else []
        tab = self.ide.tabs[self.current_tab if tabno == -1 else int(tabno)]
        terminal = tab.add_terminal(title, commands=command_lst if command else None)
        tab.stack.set_visible_child(terminal)
        return []   

    def command_term_select(self, termnum, tabno=-1):
        tab = self.ide.tabs[self.current_tab if tabno == -1 else int(tabno)] 
        term = tab.terminals[int(termnum)]
        tab.stack.set_visible_child(term)
        term.grab_focus()

    def command_term_num(self, tabno=-1):
        tab = self.ide.tabs[self.current_tab if tabno == -1 else int(tabno)] 
        curterm = tab.stack.get_visible_child()
        for i, term in enumerate(tab.terminals):
            if term == curterm:
                return [i] 
        return [-1]
    
    def command_term_next(self, tabno=-1):
        tab = self.ide.tabs[self.current_tab if tabno == -1 else int(tabno)] 
        termnum = self.command_term_num()[0]
        if termnum + 1 >= len(tab.terminals):
            return [-1]
        termnum += 1
        self.command_term_select(termnum)
        return [termnum]

    def command_term_prev(self, tabno=-1):
        tab = self.ide.tabs[self.current_tab if tabno == -1 else int(tabno)] 
        termnum = self.command_term_num()[0]
        if termnum <= 0:
            return [s-1]
        termnum -= 1
        self.command_term_select(termnum)
        return [termnum]
    
    def command_term_list(self, tabno=-1):
        tab = self.ide.tabs[self.current_tab if tabno == -1 else int(tabno)] 
        return [term.title for term in tab.terminals]

    def command_term_close(self, termnum=-1, tabno=-1):
        tab = self.ide.tabs[self.current_tab if tabno == -1 else int(tabno)] 
        term = (
            tab.terminals[termnum] 
            if termnum != -1 
            else tab.stack.get_visible_child()
        )
        tab.stack.remove(term)
        return []

    def command_term_scale(self, change=0, tabno=-1):
        tab = self.ide.tabs[self.current_tab if tabno == -1 else int(tabno)] 
        term = tab.stack.get_visible_child() 
        term.set_font_scale(term.get_font_scale()+float(change))
        return [term.get_font_scale()]        

    def command_term_set_scale(self, val=0, tabno=-1):
        tab = self.ide.tabs[self.current_tab if tabno == -1 else int(tabno)] 
        term = tab.stack.get_visible_child() 
        term.set_font_scale(float(val))
        return [term.get_font_scale()]        

    def command_term_feed(self, tabno, val=""):
        tab = self.ide.tabs[self.current_tab if tabno == -1 else int(tabno)] 
        term = tab.stack.get_visible_child() 
        term.feed(val.encode("utf-8"))
        return []        

    def command_clipboard_paste(self, tabno=-1):
        tab = self.ide.tabs[self.current_tab if tabno == -1 else int(tabno)] 
        term = tab.stack.get_visible_child() 
        term.paste_clipboard()
        return []

    def command_clipboard_copy(self, tabno=-1):
        tab = self.ide.tabs[self.current_tab if tabno == -1 else int(tabno)] 
        term = tab.stack.get_visible_child() 
        term.copy_clipboard()
        return []

    def command_prompt(self, title='', defval="Def Val"):
        dialog_window = Gtk.Dialog(title=title, transient_for=self.ide, flags=0)
        dialog_window.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, 
            Gtk.STOCK_OK, Gtk.ResponseType.OK
        )
        #dialog_window.set_default_size(300, 200)
        #dialog_window.show_all()
        #response = dialog_window.run()

    def command_popup(self, title, command=[]):
        popup = Gtk.Window(title=title)
        popup.show()

