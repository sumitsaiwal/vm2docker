__author__ = 'elubin'

import socket
from rpc import ExitCommand, RPCCommand
from chief.constants.agent import SEND_FILE_HEADER_FMT
from chief.utils.utils import inheritors
from chief.utils.ringbuffer import ringbuffer
import re
import tempfile
import os


class CommunicationLayer(object):
    """
    A class that can call any of the prescribed RPC by referencing its command name
    """
    def __init__(self, socket_address, port):
        self.connection = SocketWrapper(socket.create_connection((socket_address, port)))
        command_classes = inheritors(RPCCommand)
        # now create a dict keyed by the actual command attributes
        self.commands = {}
        for cls in command_classes:
            self.commands[cls.COMMAND] = cls(self.connection)

    def close(self):
        ExitCommand(self.connection)()
        self.connection.close()

    def __getattr__(self, item):
        """
        If the method isn't found, look it up in the list of RPCs
        """
        if item in self.commands:
            return self.commands[item]
        else:
            raise AttributeError()


class SocketWrapper(object):
    """
    Helper subclass that facilitates buffered reading of sockets with a specified byte-delimiter
    """
    BUFFER_SIZE = 4096
    SOCKET_TIMEOUT = 5.0

    def __init__(self, connection, delimiter='\x00'):
        self.socket_connection = connection
        self.socket_connection.settimeout(self.SOCKET_TIMEOUT)
        self.delimiter = delimiter
        self.buffer = ringbuffer(self.BUFFER_SIZE)

    def close(self):
        self.socket_connection.close()

    def send(self, msg):
        self.socket_connection.sendall(msg)

    def recv(self):
        """
        Receive a socket response as a string and return the string
        """

        def f(buf, n_bytes):
            return self.socket_connection.recv_into(buf, n_bytes)

        output = bytearray()
        found = False
        while not found:
            self.buffer.write_to(f)
            bytes, found = self.buffer.read_until(self.delimiter)
            output.extend(bytes)

        return str(output)


    def recv_file(self):
        """
        Parse the socket response for the string detailing how many bytes are in the file, then write the file
        to disk and return a path to it
        """
        header = self.recv()
        regex_pattern = SEND_FILE_HEADER_FMT % ("([0-9]+)", r'([\w\.])')
        m = re.match(regex_pattern, header)
        assert m is not None
        nbytes, filename = m.group(1, 2)

        def write_data(buf, n_bytes):
            self.socket_connection.recv_into(buf, n_bytes)

        bytes_received = 0
        temp_dir = tempfile.mkdtemp()
        target = os.path.join(temp_dir, filename)
        with open(target, 'wb') as f:
            while bytes_received < nbytes:
                bytes_received += self.buffer.write_to(write_data, nbytes - bytes_received)
                data = self.buffer.read(nbytes - bytes_received)
                f.write(data)

        return '%d bytes saved to %s' % (nbytes, target)



