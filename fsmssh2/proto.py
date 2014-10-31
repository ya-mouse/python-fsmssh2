import libssh2
import socket
from time import time

from fsmsock.proto import TcpTransport

class SSHClient(TcpTransport):
    def __init__(self, host, interval, user, passwd, cmds):
        self._userid = user
        self._passwd = passwd
        self._send = None
        self._recv = None
        self._cmd_idx = 0
        self._cmds = cmds

        self._chan = None
        self._sess = libssh2.Session()
        self._sess.setblocking(0)
        super().__init__(host, interval,
                         (socket.AF_INET, socket.SOCK_STREAM, 22))

    def connect(self):
#        self._l.debug("CONNECT %s" % self.fileno())
        if self.connected():
            return True
        self._send = self._startup
        self._recv = self._startup
        rc = super().connect()
        return rc

    def request(self, tm = None):
        if tm == None:
            tm = time()
#        self._l.debug("REQ %s" % self._send)
        self._expire = tm + self._interval
        self._timeout = tm + 5.0
        if self._send != None:
            try:
                return self._send()
            except Exception:
                self.disconnect()
        return True

    def process(self):
#        self._l.debug("PROCESS %s" % self._recv)
        self._retries = 0

        if self._recv != None:
            try:
                return self._recv()
            except Exception:
                self.disconnect()

        return False

    def _startup(self):
#        self._l.debug("-- STARTUP %s" % self._sess.blockdirections())
        ret = self._sess.startup(self._sock)
        if ret != -37:
            self._send = self._auth
            self._recv = self._auth
        return True

    def _auth(self):
#        self._l.debug("-- AUTH %s" % self._sess.blockdirections())
        ret = self._sess.userauth_password(self._userid, self._passwd)
        if ret != -37:
            self._send = self._open_channel
            self._recv = self._open_channel
        return True

    def _open_channel(self):
#        self._l.debug("-- CHAN %s" % self._sess.blockdirections())
        self._chan = self._sess.open_session()
        if self._chan != None:
            self._send = self._open_pty
            self._recv = self._open_pty
        return True

    def _open_pty(self):
#        self._l.debug("-- PTY %s" % self._sess.blockdirections())
        ret = self._chan.pty()
        if ret != -37:
            self._send = self._execute
            self._recv = self._execute
        return True

    def _execute(self):
#        self._l.debug("-- SEND %s" % self._sess.blockdirections())
        ret = self._chan.execute(self._cmds[self._cmd_idx])
        if ret != -37:
            self._data = b''
            self._send = self._send_cmd
            self._recv = self._recv_cmd
        return True

    def _send_cmd(self):
        rc = self._process_cmd(True)
        return rc == -2

    def _recv_cmd(self):
        return not self._process_cmd(False) == 1

    def _process_cmd(self, loop):
        data1 = self._chan.read_ex()
#        self._l.debug("-- CMD {0} {1} {2}".format(loop, self._sess.blockdirections(), self._chan.eof()))
        if data1[0] > 0:
            self._data += data1[1]
        if data1[0] == 0 or self._chan.eof():
            if loop:
                tm = time()
                self._value(self._data, tm)
                self._chan.close()
                self._chan = None
                self._send = self._open_channel
                self._recv = self._open_channel
                self._cmd_idx += 1
                if self._cmd_idx == len(self._cmds):
                    self._cmd_idx = 0
                    # We're done
                    self.stop()
                    return -2
                return 0
            return -1
        if data1[0] == -37:
            return 1
        return 0

    def _value(self, data, tm):
        print(data)

if __name__ == '__main__':
    import sys
    from fsmsock import async
    fsm = async.FSMSock()
    tcp = SSHClient(sys.argv[1], 5.0, 'ADMIN', 'ADMIN', (sys.argv[2],))
    fsm.connect(tcp)
    while fsm.run():
        fsm.tick()
