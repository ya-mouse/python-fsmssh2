import libssh2
import socket, select
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
        if self.connected():
            return True
        self._send = None
        self._recv = self._startup
        rc = super().connect()
#        self._l.debug("CONNECT %s" % self.fileno())
        return rc

    def request(self, tm = None):
        if tm == None:
            tm = time()
#        self._l.debug("REQ %s" % self._send)
        self._expire = tm + 10.0
        self._timeout = self._expire + 5.0
        if self._send != None:
            try:
                return self._send()
            except Exception as e:
#                print('REQEST', e)
                self.disconnect()
        return 0

    def process(self, tm = None):
        if tm == None:
            tm = time()
#        self._l.debug("PROCESS %s" % self._recv)
        self._retries = 0

        self._expire = tm + 10.0
        self._timeout = self._expire + 5.0
        if self._recv != None:
            try:
                return self._recv()
            except Exception as e:
#                print('PROCESS', e)
                self.disconnect()

        return 0

    def _startup(self):
        ret = self._sess.startup(self._sock)
#        self._l.debug("-- STARTUP {0} ({1})".format(self._sess.blockdirections(), ret))
        if ret != -37:
            self._send = self._auth
            self._recv = self._auth
            return select.EPOLLOUT
        return -1

    def _auth(self):
#        self._l.debug("-- AUTH %s" % self._sess.blockdirections())
        ret = self._sess.userauth_password(self._userid, self._passwd)
        if ret != -37:
            self._send = self._open_channel
            self._recv = self._open_channel
            return select.EPOLLOUT
        if self._send is None:
            return -1
        self._send = None
        return select.EPOLLIN

    def _open_channel(self):
#        self._l.debug("-- CHAN %s" % self._sess.blockdirections())
        self._chan = self._sess.open_session()
        if self._chan != None:
            self._send = self._open_pty
            self._recv = self._open_pty
            return select.EPOLLOUT
        if self._send is None:
            return -1
        self._send = None
        return select.EPOLLIN

    def _open_pty(self):
#        self._l.debug("-- PTY %s" % self._sess.blockdirections())
        ret = self._chan.pty()
        if ret != -37:
            self._send = self._execute
            self._recv = self._execute
            return select.EPOLLOUT
        if self._send is None:
            return -1
        self._send = None
        return select.EPOLLIN

    def _execute(self):
#        self._l.debug("-- EXECUTE %s" % self._sess.blockdirections())
        ret = self._chan.execute(self._cmds[self._cmd_idx])
        if ret != -37:
            self._data = b''
            self._recv = self._recv_cmd
        if self._send is None:
            return -1
        self._send = None
        return select.EPOLLIN

    def _recv_cmd(self):
        return self._process_cmd()

    def _process_cmd(self):
        data1 = self._chan.read_ex()
#        self._l.debug("-- CMD {0} {1} {2}".format(data1[0], self._sess.blockdirections(), self._chan.eof()))
        if data1[0] > 0:
            self._data += data1[1]
        if data1[0] == 0 or self._chan.eof():
            if self._chan.eof():
                tm = time()
                self.on_data(self._data, tm)
                self._chan.close()
                self._chan = None
                self._send = self._open_channel
                self._recv = self._open_channel
                self._cmd_idx += 1
                if self._cmd_idx == len(self._cmds):
                    self._cmd_idx = 0
                    # We're done
                    self.stop()
                    return 0 # -2
                return select.EPOLLOUT
            return -1
        if data1[0] == -37:
            return -1
        return -1

    def stop(self):
        self._sess.close()
        super().stop()

    def on_data(self, data, tm):
        print(data)

if __name__ == '__main__':
    import sys
    from fsmsock import async
    fsm = async.FSMSock()
    tcp = SSHClient(sys.argv[1], 5.0, 'ADMIN', 'ADMIN', (sys.argv[2],))
    fsm.connect(tcp)
    while fsm.run():
        fsm.tick()
