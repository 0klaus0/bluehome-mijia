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
        cls.previous_code = connect_mijia.PAIR_CODE
        connect_mijia.LAN_HOST = 'auto'
        connect_mijia.PAIR_CODE = '12345678'
        cls.server = connect_mijia.ThreadingHTTPServer(('127.0.0.1', 0), RemotePairHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        connect_mijia.LAN_HOST = cls.previous_host
        connect_mijia.PAIR_CODE = cls.previous_code

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
        self.assertEqual(self.post('/pair'), (303, '/app/'))

    def test_pairing_with_launcher_origin(self):
        self.assertEqual(self.post('/pair', {'Origin': 'http://192.168.1.5:5000'}), (303, '/app/'))

    def test_cross_site_pairing_is_rejected(self):
        self.assertEqual(self.post('/pair', {'Sec-Fetch-Site': 'cross-site'})[0], 403)

    def test_control_still_requires_matching_origin(self):
        self.assertEqual(self.post('/control')[0], 403)


if __name__ == '__main__':
    unittest.main()
