import curses

from .constants import THREAD_STATE_INITIAL, THREAD_STATE_RUNNING, THREAD_STATE_SUSPENDED

COLOR_DEFAULT = 1
COLOR_HIGHLIGHTED = 2


class Buffer(object):
    __keymap__ = {}

    def __init__(self, cui):
        self.curses_ui = cui
        self.keymap = {}
        self._init_keymap()

    def _init_keymap(self):
        class_ = self.__class__
        while class_:
            if hasattr(class_,'__keymap__'):
                self.keymap.update(class_.__keymap__)
            class_ = class_.__base__

    def handle_input(self, c):
        key_fn = self.keymap.get(c)
        if key_fn:
            key_fn(self)

    def name(self):
        return '*empty*'

    def fill_row(self, screen, row, col, string, sep=' ', attr=None):
        l = (screen.getmaxyx()[1] - len(string)) - col - 1
        if attr:
            screen.addstr(row, col, '%s%s' % (string, sep * l), attr)
        else:
            screen.addstr(row, col, '%s%s' % (string, sep * l))

    def render_mode_line(self, screen):
        max_y, max_x = screen.getmaxyx()
        fixed = '--- [ %s ] ' % self.name()
        self.fill_row(screen, max_y - 1, 0, fixed, sep='-')

    def render_content(self, screen):
        pass

    def render(self, screen):
        self.render_content(screen)
        self.render_mode_line(screen)


class ListBuffer(Buffer):
    __keymap__ = {
        curses.KEY_UP:    lambda b: b.key_up(),
        curses.KEY_DOWN:  lambda b: b.key_down(),
        curses.KEY_ENTER: lambda b: b.on_item_selected()
    }

    def __init__(self, cui):
        super(ListBuffer, self).__init__(cui)
        self.selected_item = 0

    def key_down(self):
        self.selected_item = min(self.item_count() - 1, self.selected_item + 1)

    def key_up(self):
        self.selected_item = max(0, self.selected_item - 1)

    def render_content(self, screen):
        for index in range(0, self.item_count()):
            item = self.render_item(screen, index)
            self.fill_row(screen, index, 0, item,
                          attr=curses.color_pair(COLOR_HIGHLIGHTED \
                                                 if index == self.selected_item else \
                                                 COLOR_DEFAULT))

    def on_item_selected(self):
        pass

    def item_count(self):
        pass

    def render_item(self, screen, index):
        pass


thread_state_str = {
    THREAD_STATE_INITIAL:   'INI',
    THREAD_STATE_SUSPENDED: 'SUS',
    THREAD_STATE_RUNNING:   'RUN'
}


class ThreadBuffer(ListBuffer):
    __keymap__ = {
        115: lambda b: b.suspend_thread()
    }

    def __init__(self, cui, session):
        super(ThreadBuffer, self).__init__(cui)
        self.session = session
        self.selected_thread = 0

    def suspend_thread(self):
        self.session.command_sender.send()

    def name(self):
        return 'Threads(%s:%s)' % self.session.address

    def item_count(self):
        return len(self.session.threads)

    def render_item(self, screen, index):
        thread = self.session.threads.values()[index]
        return '%s %s' % (thread_state_str[thread.state], thread.name)


READ_TIMEOUT = 100


class CursesUi(object):
    def __init__(self, debugger):
        self.debugger = debugger
        self.screen = None
        self.buffers = [ThreadBuffer(self, self.debugger.sessions[0])]

    def _current_buffer(self):
        return self.buffers[0]

    def init_curses(self):
        self.screen = curses.initscr()
        curses.savetty()
        curses.raw(1)
        curses.noecho()
        curses.curs_set(0)
        self.screen.keypad(1)
        self.screen.timeout(READ_TIMEOUT)

        curses.start_color()
        curses.init_pair(COLOR_DEFAULT, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(COLOR_HIGHLIGHTED, curses.COLOR_BLUE, curses.COLOR_WHITE)
        self.stdscr.bkgd(curses.color_pair(COLOR_DEFAULT))
        self.stdscr.refresh()
        self.debugger.add_exit_handler(self.quit_curses)

    def quit_curses(self):
        curses.resetty()
        curses.endwin()
        self.debugger.remove_exit_handler(self.quit_curses)

    def update_ui(self):
        #maxy, maxx = stdscr.getmaxyx()
        #pad = curses.newpad(10000, 3000)
        self._current_buffer().render(self.stdscr)

    def run(self):
        self.init_curses()
        while True:
            self.update_ui()

            c = self.stdscr.getch()
            if c == -1:
                continue
            self.debugger.logger.log('Key pressed: %s' % c)
            self.debugger.logger.log('Key pressed: %s' % curses.keyname(c))
            if c == ord('q'):
                break
            else:
                self._current_buffer().handle_input(c)
        self.quit_curses()
