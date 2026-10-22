"""Exercise the real pairing endpoint and the stricter control API boundary."""

import http.client
import os
import tempfile
import threading
import unittest

with tempfile.TemporaryDirectory() as data_dir:
    previous_data_dir = os.environ.get('BLUEHOME_DATA_DIR')
    os.environ['BLUEHOME_DATA_DIR'] = data_dir
    import connect_mijia
    if previous_data_dir is None:
        del os.environ['BLUEHOME_DATA_DIR']
    else:
        os.environ['BLUEHOME_DATA_DIR'] = previous_data_dir


class RemotePairHandler(connect_mijia.Handler):
    def local_client(self):
        return False


class PairingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_host = connect_mijia.LAN_HOST
        cls.previous_https_host = connect_mijia.HTTPS_HOST
        cls.previous_code = connect_mijia.PAIR_CODE
        cls.previous_state = connect_mijia.state
        connect_mijia.LAN_HOST = 'auto'
        connect_mijia.HTTPS_HOST = 'home.example.com'
        connect_mijia.PAIR_CODE = '12345678'
        connect_mijia.state = {'status': 'waiting'}
        cls.server = connect_mijia.ThreadingHTTPServer(('127.0.0.1', 0), RemotePairHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        connect_mijia.LAN_HOST = cls.previous_host
        connect_mijia.HTTPS_HOST = cls.previous_https_host
        connect_mijia.PAIR_CODE = cls.previous_code
        connect_mijia.state = cls.previous_state

    def post(self, path, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        request_headers = {'Host': '192.168.1.5:4174', 'Content-Type': 'application/x-www-form-urlencoded'}
        request_headers.update(headers or {})
        connection.request('POST', path, 'code=12345678', request_headers)
        response = connection.getresponse()
        result = response.status, response.getheader('Location')
        response.read()
        connection.close()
        return result

    def test_pairing_without_origin(self):
        self.assertEqual(self.post('/pair'), (303, '/'))

    def test_pairing_with_launcher_origin(self):
        self.assertEqual(self.post('/pair', {'Origin': 'http://192.168.1.5:5000'}), (303, '/'))

    def test_tailscale_address_can_pair(self):
        self.assertEqual(self.post('/pair', {'Host': '100.101.2.3:4174'}), (303, '/'))

    def test_https_domain_pairing_sets_secure_cookie(self):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        connection.request('POST', '/pair', 'code=12345678',
                           {'Host': 'home.example.com', 'Content-Type': 'application/x-www-form-urlencoded'})
        response = connection.getresponse()
        self.assertEqual(response.status, 303)
        cookie = response.getheader('Set-Cookie')
        self.assertIn('Secure', cookie)
        self.assertIn('SameSite=Lax', cookie)
        response.read()
        connection.close()

    def test_unconfigured_domain_is_rejected(self):
        self.assertEqual(self.post('/pair', {'Host': 'other.example.com'})[0], 403)

    def test_https_control_requires_https_origin(self):
        class StubBridge:
            token = 'session-token'
            def control(self, *_):
                return {'ok': True}
        previous_bridge = connect_mijia.bridge
        connect_mijia.bridge = StubBridge()
        try:
            for origin, expected in [('http://home.example.com', 403), ('https://home.example.com', 200)]:
                with self.subTest(origin=origin):
                    connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
                    connection.request('POST', '/control', '{"key":1,"property":"power","value":true}', {
                        'Host': 'home.example.com', 'Origin': origin,
                        'Cookie': 'bluehome_pair=' + connect_mijia.PAIR_COOKIE,
                        'X-Bluehome-Session': 'session-token', 'Content-Type': 'application/json'})
                    response = connection.getresponse()
                    self.assertEqual(response.status, expected)
                    response.read()
                    connection.close()
        finally:
            connect_mijia.bridge = previous_bridge

    def test_other_shared_address_is_rejected(self):
        self.assertEqual(self.post('/pair', {'Host': '100.63.2.3:4174'})[0], 403)

    def test_ready_account_opens_dashboard(self):
        connect_mijia.state = {'status': 'ready'}
        try:
            self.assertEqual(self.post('/pair'), (303, '/app/'))
        finally:
            connect_mijia.state = {'status': 'waiting'}

    def test_cross_site_pairing_is_rejected(self):
        self.assertEqual(self.post('/pair', {'Sec-Fetch-Site': 'cross-site'})[0], 403)

    def test_control_still_requires_matching_origin(self):
        self.assertEqual(self.post('/control')[0], 403)


if __name__ == '__main__':
    unittest.main()
