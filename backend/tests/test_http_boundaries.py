"""Real loopback sockets against an isolated HTTP service, without a ledger."""
import http.client
import socket
import threading
import time
import unittest
from unittest import mock

from ui import LocalHTTPServer, make_server


class HTTPBoundaryTests(unittest.TestCase):
    def setUp(self):
        with mock.patch.object(LocalHTTPServer, 'socket_timeout_seconds', .2), \
             mock.patch.object(LocalHTTPServer, 'worker_limit', 2):
            self.server = make_server('unused-synthetic-config', 0)
        self.server.socket_timeout_seconds = .2
        self.action = mock.Mock(return_value={'ok': True})
        self.server.application.action = self.action
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def raw_post(self, body, length=None, content_type='application/json'):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=1)
        try:
            connection.request('POST', '/api/action', body, {
                'Cookie': 'guardian_ui=' + self.server.session,
                'Origin': 'http://127.0.0.1:%s' % self.port,
                'X-Guardian-UI': '1', 'Content-Type': content_type,
                'Content-Length': str(len(body) if length is None else length)})
            response = connection.getresponse()
            response.read()
            return response.status
        finally:
            connection.close()

    def wait_for_workers(self, expected):
        deadline = time.monotonic() + 1
        while self.server.workers._value != expected and time.monotonic() < deadline:
            time.sleep(.002)
        self.assertEqual(self.server.workers._value, expected)

    def test_idle_connection_is_closed_without_allocating_a_worker_forever(self):
        with socket.create_connection(('127.0.0.1', self.port), timeout=1) as connection:
            self.assertEqual(connection.recv(1), b'')
        self.wait_for_workers(2)
        self.action.assert_not_called()

    def test_incomplete_authenticated_body_expires_without_executing(self):
        with socket.create_connection(('127.0.0.1', self.port), timeout=1) as connection:
            headers = ('POST /api/action HTTP/1.1\r\nHost: 127.0.0.1:%s\r\n'
                       'Cookie: guardian_ui=%s\r\nOrigin: http://127.0.0.1:%s\r\n'
                       'X-Guardian-UI: 1\r\nContent-Type: application/json\r\n'
                       'Content-Length: 100\r\n\r\n{' % (self.port, self.server.session, self.port))
            connection.sendall(headers.encode())
            reply = connection.recv(1024)
            self.assertIn(b'503', reply)
        self.wait_for_workers(2)
        self.action.assert_not_called()

    def test_worker_cap_rejects_excess_connection_then_recovers(self):
        connections = [socket.create_connection(('127.0.0.1', self.port), timeout=1) for _ in range(2)]
        try:
            for connection in connections:
                connection.sendall(b'GET / HTTP/1.1\r\n')
            self.wait_for_workers(0)
            with socket.create_connection(('127.0.0.1', self.port), timeout=1) as excess:
                try:
                    excess.sendall(('GET / HTTP/1.1\r\nHost: 127.0.0.1:%s\r\n\r\n' % self.port).encode())
                    self.assertEqual(excess.recv(1024), b'')
                except ConnectionError:
                    pass
        finally:
            for connection in connections:
                connection.close()
        self.wait_for_workers(2)
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=1)
        try:
            connection.request('GET', '/')
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
        finally:
            connection.close()

    def test_bad_lengths_content_types_and_json_do_not_execute_actions(self):
        for length in (0, -1, 'not-a-number', 32769):
            with self.subTest(length=length):
                self.assertEqual(self.raw_post(b'{}', length=length), 409)
        self.assertEqual(self.raw_post(b'{}', content_type='text/plain'), 409)
        for body in (b'[]', b'null', b'{', b'\xff'):
            with self.subTest(body=body):
                self.assertEqual(self.raw_post(body), 409)
        self.action.assert_not_called()

    def test_exact_body_size_limit_and_valid_object_are_accepted(self):
        self.assertEqual(self.raw_post(b'{}' + b' ' * (32768 - 2)), 200)
        self.action.assert_called_once_with({})
