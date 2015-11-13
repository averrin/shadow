#!env python

from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtDBus import *
import sys
import os
import random
import subprocess
import re
from functools import partial
import fcntl
import dbus

app = QApplication(sys.argv)
dbPath = 'org.shadow.QtDBus.Control'
dbface = QDBusInterface(dbPath, '/')

pid_file = 'program.pid'
fp = open(pid_file, 'w')
try:
    fcntl.lockf(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
except IOError:
    dbface.call('nextItem')
    sys.exit(0)

CWD = os.path.split(sys.argv[0])[0]


class Layer(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.setWindowTitle('Shadow')
        self.w = 500
        self.h = 300
        rec = QApplication.desktop().screenGeometry()
        self.setGeometry(
            rec.width()/2 - self.w/2,
            rec.height()/2 - self.h/2,
            self.w, self.h
        )
        # self.setAttribute(Qt.WA_TranslucentBackground);
        # self.setWindowFlags(Qt.FramelessWindowHint);
        view = QGraphicsView(self)
        scene = QGraphicsScene()
        scene.setSceneRect(0, 0, self.w, self.h)
        view.setScene(scene)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.winList = listWindows()

        self.setCentralWidget(view)
        self.scene = scene
        self.input = ''
        self.cursor = 0
        self.drawWin()
        self.esc = QShortcut(QKeySequence('Esc'), self)
        self.esc.activated.connect(exit)

        shortcuts = {
            "Ctrl+H": self.backspace,
            "Ctrl+W": self.clear,
            "Ctrl+C": self.clear,
            "Ctrl+J": self.action,
            "Space": self.action,
            "Ctrl+N": self.nextItem,
            "Ctrl+P": self.prevItem,
            "Alt+Shift+Tab": self.prevItem,
            "Alt+Tab": self.nextItem,
        }
        for sq, action in shortcuts.items():
            sh = QShortcut(QKeySequence(sq), self)
            sh.activated.connect(action)

        self.indexKeys = []
        self.addIndexKeys()

    @pyqtSlot(QDBusMessage)
    def nextItem(self):
        self.cursor += 1
        if self.cursor > len(self.filterWindows()):
            self.cursor = 0
        self.updateInput(self.input)

    def prevItem(self):
        self.cursor -= 1
        if self.cursor < 0:
            self.cursor = len(self.filterWindows()) - 1
        self.updateInput(self.input)

    def clear(self):
        self.updateInput('')

    def addIndexKeys(self):
        for sh in self.indexKeys:
            sh.activated.disconnect()
            sh.setKey('')
            sh.setEnabled(False)
        self.indexKeys = []
        for i, w in enumerate(self.filterWindows()):
            sq = 'Alt+%d' % (i + 1)
            action = partial(activateWindow, w)
            sh = QShortcut(QKeySequence(sq), self)
            sh.activated.connect(action)
            self.indexKeys.append(sh)
            if i == 8:
                break

    def drawWin(self):
        self.scene.clear()
        t = '# %s' % self.input
        inputText = self.scene.addText(t, QFont('Fantasque Sans Mono', 13))
        inputText.setDefaultTextColor(QColor('#ccc'))
        inputText.setPos(20, 20)
        self.line = inputText
        winList = QGraphicsTextItem('')
        self.scene.addItem(winList)
        self.listWidget = winList
        winList.setDefaultTextColor(QColor('#ccc'))
        winList.setFont(QFont('Fantasque Sans Mono', 11))
        winList.setHtml(self.getWindows())
        winList.setPos(20, 44)

    def filterWindows(self):
        ret = []
        for w in self.winList:
            if self._match_fuzzy(w['class']):
                ret.append(w)
        for w in self.winList:
            if self._match_fuzzy(w['title']) and w not in ret:
                ret.append(w)
        return ret

    def getWindows(self):
        ret = []
        for i, w in enumerate(self.filterWindows()):
            win = w.copy()
            win['index'] = i+1 if i < 9 else '&nbsp;'
            if i == self.cursor:
                win['index'] = '<span style="color: rgb(35, 157, 201)"><b>&gt; %d</b></span>' % win['index']
            else:
                win['index'] = '&nbsp;&nbsp;%s' % win['index']
            win['class'] = ''
            win['title'] = ''
            for ch in w['title']:
                ch = ch.lower()
                if ch in self.input:
                    ch = '<span style="color: rgb(143, 116, 56)"><b>%s<b></span>' % ch
                win['title'] += ch
            for ch in w['class'].split('.')[1]:
                ch = ch.lower()
                if ch in self.input:
                    ch = '<span style="color: rgb(143, 116, 56)"><b>%s<b></span>' % ch
                win['class'] += ch
            ret.append('%(index)s [%(desktop)s] <b>%(class)s</b>&nbsp;&nbsp;&nbsp;%(title)s' % win)
        return '<br>'.join(ret)

    def _match_fuzzy(self, data):
        """Matcher for 'fuzzy' matching type logic."""
        data = data.casefold()
        pattern = re.escape(self.input.casefold())
        last_index = 0
        for char in pattern:
            if char not in data:
                return False
            positions = [g.start() for g in re.finditer(char, data)]
            if max(positions) < last_index:
                return False
            last_index = min(positions)
        return True

    def updateInput(self, txt):
        if self.input != txt:
            self.cursor = 0
            self.input = txt
        t = '# %s' % self.input
        self.line.setPlainText(t)
        self.listWidget.setHtml(self.getWindows())
        self.addIndexKeys()

    def backspace(self):
        self.updateInput(self.input[:-1])

    def action(self):
        win = self.filterWindows()[self.cursor]
        print(win)
        activateWindow(win)

    def event(self, e):
        if e.type() == QEvent.KeyRelease:
            if Qt.Key_A <= e.key() <= Qt.Key_Z and e.modifiers() == Qt.NoModifier:
                c = chr(e.key()).lower()
                self.updateInput(self.input + c)
        # elif e.type() == QEvent.WindowDeactivate:
            # exit(0)
        return QMainWindow.event(self, e)


def listWindows():
    exclude = ['yakuake.Yakuake', 'explorer.exe.Wine']
    l = subprocess.check_output(['wmctrl', '-lx'])
    windows = []
    for line in l.decode().split('\n'):
        line = [x for x in line.split(' ') if x]
        if not line:
            continue
        wid, desktop, wm_cls, _, *title = line
        if wm_cls in exclude:
            continue
        windows.append({
            "wid": wid,
            "desktop": desktop,
            "class": wm_cls,
            "title": ' '.join(title)
        })
    return windows


def activateWindow(window):
    wid = window['title']
    subprocess.check_output(['wmctrl', '-a', wid])
    exit()

layer = Layer()
QDBusConnection.sessionBus().registerObject("/", layer, QDBusConnection.ExportAllSlots)
QDBusConnection.sessionBus().registerService(dbPath)
os.system('xdotool mousemove 800 600')
layer.show()
app.exec_()
sys.exit()
