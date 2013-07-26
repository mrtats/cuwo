# Copyright (c) Mathias Kaerlev 2013.
#
# This file is part of cuwo.
#
# cuwo is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# cuwo is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with cuwo.  If not, see <http://www.gnu.org/licenses/>.

"""
Master server that serves a single JSON file through the local filesystem
"""

import sys
sys.path += ['.', './scripts']

from cuwo import constants
from cuwo.exceptions import InvalidData
import master
from twisted.internet.task import LoopingCall
from twisted.internet import reactor
import pygeoip
import argparse
import json


WRITE_INTERVAL = 10
DEFAULT_PORT = 12364
EXPIRE_TIME = master.UPDATE_RATE * 1.5


class MasterServer(master.MasterProtocol):
    def __init__(self, filename):
        self.filename = filename
        self.output = {}
        self.ignore = set()
        self.update_loop = LoopingCall(self.update)
        self.update_loop.start(EXPIRE_TIME)
        self.ip_database = pygeoip.GeoIP('GeoIP.dat')

    def datagramReceived(self, data, addr):
        host, port = addr
        if host in self.ignore:
            return
        master.MasterProtocol.datagramReceived(self, data, addr)

    def on_bad_packet(self, addr):
        host, port = addr
        self.ignore.add(host)

    def update(self):
        with open(self.filename, 'wb') as fp:
            fp.write(json.dumps(self.output.values()))
        self.output.clear()

    def on_resolve(self, resolved_ip, ip, hostname, data):
        if resolved_ip == ip:
            data.ip = hostname
        else:
            data.ip = ip
        self.add_server(data, ip)

    def on_resolve_error(self, failure, ip, data):
        data.ip = ip
        self.add_server(data, ip)

    def on_server(self, data, addr):
        host, port = addr
        if data.ip is not None:
            d = reactor.resolve(data.ip)
            d.addCallback(self.on_resolve, host, data.ip, data)
            d.addErrback(self.on_resolve_error, host, data)
            return
        data.ip = host
        self.add_server(data, host)

    def add_server(self, data, ip):
        try:
            location = self.ip_database.country_code_by_addr(ip)
        except TypeError:
            location = '?'
        data.location = location
        data.mode = data.mode or 'default'
        self.output[ip] = data.get()

    def on_packet(self, value, addr):
        host, port = addr
        if port != constants.SERVER_PORT:
            return
        try:
            self.on_server(master.ServerData(value), addr)
        except InvalidData:
            self.on_bad_packet()
            return
        self.send_packet({'ack': True}, addr)


def main():
    parser = argparse.ArgumentParser(description='Run a master server')
    parser.add_argument('filename', type=str)
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    port = args.port
    filename = args.filename

    server = MasterServer(filename)
    port = reactor.listenUDP(port, server)
    print 'Running cuwo (master) on port %s' % port.port
    reactor.run()

if __name__ == '__main__':
    main()
