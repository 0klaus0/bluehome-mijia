"""User-configured OpenAI-compatible advisory chat. Never receives MIoT credentials."""
import json
from pathlib import Path
from urllib.parse import urlparse

import requests


class ModelClient:
    def __init__(self, private: Path):
        self.path = private / 'model-config.json'
        try:
            self.config = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.config = {}

    def status(self):
        return {'configured': bool(self.config.get('url') and self.config.get('model')),
                'url': self.config.get('url', ''), 'model': self.config.get('model', ''),
                'has_key': bool(self.config.get('api_key')), 'share_home_context': bool(self.config.get('share_home_context'))}

    @staticmethod
    def validated_url(raw):
        url = str(raw or '').strip().rstrip('/')
        p = urlparse(url)
        if p.username or p.password or p.query or p.fragment or not p.hostname:
            raise ValueError('接口地址格式无效')
        if p.scheme != 'https' and not (p.scheme == 'http' and p.hostname in ('127.0.0.1', 'localhost')):
            raise ValueError('云端接口必须使用 HTTPS；本机接口可使用 HTTP')
        if p.port and not (1 <= p.port <= 65535):
            raise ValueError('接口端口无效')
        if not p.path.endswith('/chat/completions'):
            url += '/chat/completions' if p.path.endswith('/v1') else '/v1/chat/completions'
        if len(url) > 500:
            raise ValueError('接口地址过长')
        return url

    def configure(self, payload):
        url = self.validated_url(payload.get('url'))
        model = str(payload.get('model') or '').strip()
        key = payload.get('api_key')
        if not model or len(model) > 120 or any(c.isspace() for c in model):
            raise ValueError('模型名无效')
        if key is not None and (not isinstance(key, str) or len(key) > 500):
            raise ValueError('密钥格式无效')
        if type(payload.get('share_home_context', False)) is not bool:
            raise ValueError('设备上下文选项无效')
        self.config = {'url': url, 'model': model, 'api_key': key or self.config.get('api_key', ''),
                       'share_home_context': payload.get('share_home_context', False)}
        self.path.write_text(json.dumps(self.config, ensure_ascii=False), encoding='utf-8')
        return {'ok': True, 'message': '模型接口设置已保存在本机'}

    def disconnect(self):
        self.config = {}
        self.path.unlink(missing_ok=True)
        return {'ok': True, 'message': '本机模型设置和密钥已删除'}

    def chat(self, question, *, test=False, home_context=None):
        if not self.status()['configured']:
            raise ValueError('请先配置模型接口')
        if not isinstance(question, str) or not question.strip() or len(question) > 1200:
            raise ValueError('问题长度须为 1–1200 字')
        system = ('你是家庭设备助手。只提供简明中文建议。你不能调用设备、声称已执行操作，'
                  '也不能把推测的红外状态说成真实反馈。任何自动化建议都需要用户在应用确认。')
        if home_context and self.config.get('share_home_context'):
            system += '\n用户选择分享的当前家庭概况：' + json.dumps(home_context, ensure_ascii=False)
        body = {'model': self.config['model'], 'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': '请仅回复“连接成功”。' if test else question.strip()}],
            'stream': False, 'temperature': 0.4, 'max_tokens': 450}
        headers = {'Content-Type': 'application/json'}
        if self.config.get('api_key'):
            headers['Authorization'] = 'Bearer ' + self.config['api_key']
        try:
            response = requests.post(self.config['url'], headers=headers, json=body, timeout=(8, 45))
            response.raise_for_status()
            data = response.json()
            answer = data['choices'][0]['message']['content']
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
            raise ValueError('模型接口未成功返回回答，请核对地址、模型与密钥') from None
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError('模型回答为空')
        return {'ok': True, 'message': '模型连接成功' if test else '已收到模型建议', 'answer': answer.strip()[:5000]}
