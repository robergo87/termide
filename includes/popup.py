#!/usr/bin/python3
import os
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from include.window import TermIDE
from includes.util import ROOT_DIR

ide = SingleTerminalWindow()  
Gtk.main()
