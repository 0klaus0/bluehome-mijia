import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from model_client import ModelClient


class ModelClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.client = ModelClient(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_requires_https_for_remote(self):
        with self.assertRaises(ValueError):
            self.client.configure({'url': 'http://api.example.com/v1', 'model': 'm'})

    def test_key_stays_private_and_context_is_opt_in(self):
        self.client.configure({'url': 'https://api.example.com/v1', 'model': 'm', 'api_key': 'secret'})
        self.assertNotIn('secret', str(self.client.status()))
        with patch('model_client.requests.post') as post:
            post.return_value.json.return_value = {'choices': [{'message': {'content': '建议'}}]}
            self.assertEqual(self.client.chat('你好', home_context=[{'name': '灯'}])['answer'], '建议')
            self.assertNotIn('灯', str(post.call_args.kwargs['json']))
            self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Bearer secret')

    def test_disconnect_removes_secret(self):
        self.client.configure({'url': 'http://127.0.0.1:1234/v1', 'model': 'm', 'api_key': 'secret'})
        self.client.disconnect()
        self.assertFalse(self.client.path.exists())
        self.assertFalse(self.client.status()['configured'])


if __name__ == '__main__':
    unittest.main()
