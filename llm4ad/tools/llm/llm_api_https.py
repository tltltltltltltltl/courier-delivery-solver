# This file is part of the LLM4AD project (https://github.com/Optima-CityU/llm4ad).
# Last Revision: 2025/2/16
#
# ------------------------------- Copyright --------------------------------
# Copyright (c) 2025 Optima Group.
# 
# Permission is granted to use the LLM4AD platform for research purposes. 
# All publications, software, or other works that utilize this platform 
# or any part of its codebase must acknowledge the use of "LLM4AD" and 
# cite the following reference:
# 
# Fei Liu, Rui Zhang, Zhuoliang Xie, Rui Sun, Kai Li, Xi Lin, Zhenkun Wang, 
# Zhichao Lu, and Qingfu Zhang, "LLM4AD: A Platform for Algorithm Design 
# with Large Language Model," arXiv preprint arXiv:2412.17287 (2024).
# 
# For inquiries regarding commercial use or licensing, please contact 
# http://www.llm4ad.com/contact.html
# --------------------------------------------------------------------------

from __future__ import annotations

import http.client
import json
import threading
import time
from typing import Any
import traceback
from ...base import LLM


class HttpsApi(LLM):
    def __init__(self, host, key, model, timeout=60, **kwargs):
        """Https API
        Args:
            host   : host name. please note that the host name does not include 'https://'
            key    : API key.
            model  : LLM model name.
            timeout: API timeout.
        """
        llm_base_kwargs = {
            name: kwargs.pop(name)
            for name in ('do_auto_trim', 'debug_mode')
            if name in kwargs
        }
        super().__init__(**llm_base_kwargs)
        self._host = host
        self._key = key
        self._model = model
        self._timeout = timeout
        self._kwargs = kwargs
        self._cumulative_error = 0

    def draw_sample(self, prompt: str | Any, *args, **kwargs) -> str:
        """
        Sends a request to the LLM and retrieves the generated response.

        This method supports multiple input formats for backward compatibility:
        1. Explicit 'messages' list via kwargs.
        2. A message list passed directly as the 'prompt'.
        3. Multimodal inputs (text + base64 images).
        4. Simple string prompts.

        Args:
            prompt: The text prompt or a list of message dictionaries.
            **kwargs: Can include 'image64s' (list of base64 strings) or 'messages'.

        Returns:
            The string content of the LLM's response.
        """
        image64s = kwargs.get('image64s', None)  # List[str]
        messages_input = kwargs.get('messages', None)

        # --- 1. Priority: Explicit messages list ---
        if messages_input is not None:
            if isinstance(messages_input, dict):
                messages = [messages_input]
            else:
                messages = messages_input

        # --- 2. Legacy Support: prompt passed as a pre-constructed list ---
        elif not isinstance(prompt, str):
            messages = prompt

        # --- 3. Construction from String + Optional Images ---
        else:
            text_content = prompt.strip()

            if image64s:
                # Construct multimodal content structure
                content = [{
                    "type": "text",
                    "text": text_content
                }]
                for image in image64s:
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image}",
                        }
                    })
                messages = [{'role': 'user', 'content': content}]

            else:
                # Construct standard text-only message
                messages = [{'role': 'user', 'content': text_content}]

        # Retry loop for handling network or API transient errors
        while True:
            conn = None
            request_start = time.time()
            request_id = f'{int(request_start * 1000)}-{threading.get_ident()}'
            stage = 'connect'
            try:
                conn = http.client.HTTPSConnection(self._host, timeout=self._timeout)

                # Prepare standard OpenAI-compatible payload
                payload_data = {
                    'temperature': self._kwargs.get('temperature', 1.0),
                    'model': self._model,
                    'messages': messages
                }
                if self._kwargs.get('top_p') is not None:
                    payload_data['top_p'] = self._kwargs['top_p']
                if self._kwargs.get('max_tokens') is not None:
                    payload_data['max_tokens'] = self._kwargs['max_tokens']
                if self._kwargs.get('thinking') is not None:
                    payload_data['thinking'] = self._kwargs['thinking']
                elif self._host.endswith('deepseek.com') and self._model.startswith('deepseek-v4'):
                    payload_data['thinking'] = {'type': 'enabled'}
                if self._kwargs.get('reasoning_effort') is not None:
                    payload_data['reasoning_effort'] = self._kwargs['reasoning_effort']
                elif self._host.endswith('deepseek.com') and self._model.startswith('deepseek-v4'):
                    payload_data['reasoning_effort'] = 'medium'
                if self._kwargs.get('stream') is not None:
                    payload_data['stream'] = self._kwargs['stream']
                elif self._host.endswith('deepseek.com') and self._model.startswith('deepseek-v4'):
                    payload_data['stream'] = True
                payload = json.dumps(payload_data)
                headers = {
                    'Authorization': f'Bearer {self._key}',
                    'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
                    'Content-Type': 'application/json'
                }
                print(
                    f'{self.__class__.__name__} request start '
                    f'(id={request_id}, timeout={self._timeout!r}, host={self._host}, '
                    f'model={self._model}, payload_keys={sorted(payload_data.keys())})',
                    flush=True
                )
                stage = 'request'
                conn.request('POST', '/v1/chat/completions', payload, headers)
                stage = 'getresponse'
                res = conn.getresponse()
                if payload_data.get('stream'):
                    if res.status >= 400:
                        stage = 'read_error'
                        data = res.read().decode('utf-8')
                        raise RuntimeError(
                            f'HTTP {res.status} {res.reason}; body={data[:1000]}'
                        )

                    stage = 'stream'
                    response_parts = []
                    reasoning_chars = 0
                    last_report = time.time()
                    while True:
                        raw_line = res.readline()
                        if not raw_line:
                            break
                        line = raw_line.decode('utf-8', errors='replace').strip()
                        if not line or line.startswith(':') or not line.startswith('data:'):
                            continue
                        event_data = line[5:].strip()
                        if event_data == '[DONE]':
                            break
                        try:
                            chunk = json.loads(event_data)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get('choices') or []
                        if choices:
                            delta = choices[0].get('delta') or {}
                            content = delta.get('content')
                            if content:
                                response_parts.append(content)
                            reasoning = delta.get('reasoning_content') or delta.get('reasoning')
                            if reasoning:
                                reasoning_chars += len(str(reasoning))
                        now = time.time()
                        if now - last_report >= 15:
                            print(
                                f'{self.__class__.__name__} stream progress '
                                f'(id={request_id}, elapsed={now - request_start:.2f}s, '
                                f'content_chars={sum(len(part) for part in response_parts)}, '
                                f'reasoning_chars={reasoning_chars})',
                                flush=True
                            )
                            last_report = now
                    response = ''.join(response_parts)
                else:
                    stage = 'read'
                    data = res.read().decode('utf-8')

                    if res.status >= 400:
                        raise RuntimeError(
                            f'HTTP {res.status} {res.reason}; body={data[:1000]}'
                        )

                    stage = 'parse'
                    data = json.loads(data)

                    # Extract content from the standard response format
                    response = data['choices'][0]['message']['content']
                # Reset error counter on success
                if self.debug_mode:
                    self._cumulative_error = 0
                elapsed = time.time() - request_start
                print(
                    f'{self.__class__.__name__} request success '
                    f'(id={request_id}, elapsed={elapsed:.2f}s, chars={len(response)})',
                    flush=True
                )
                conn.close()
                return response

            except Exception as e:
                self._cumulative_error += 1
                elapsed = time.time() - request_start
                diagnostic = (
                    f'stage={stage}, elapsed={elapsed:.2f}s, '
                    f'configured_timeout={self._timeout!r}, host={self._host}, model={self._model}'
                )

                # In debug mode, crash after consecutive failures to allow debugging
                if self.debug_mode:
                    if self._cumulative_error == 10:
                        raise RuntimeError(f'{self.__class__.__name__} error ({diagnostic}): '
                                           f'{traceback.format_exc()}.'
                                           f'You may check your API host and API key.')
                else:
                    print(f'{self.__class__.__name__} error ({diagnostic}): {traceback.format_exc()}.'
                          f'You may check your API host and API key.', flush=True)
                    if conn is not None:
                        conn.close()
                    time.sleep(2)
                continue

    # def draw_sample(self, prompt: str | Any, *args, **kwargs) -> str:
    #     """
    #     Handle message construction:
    #     - If 'messages' is explicitly provided, use it as the payload.
    #     - If 'messages' is None, build it from 'prompt' and 'images':
    #         a) Text only: Wrap prompt in a standard user message format.
    #         b) Multimodal: Combine prompt text and image URLs into a single user message content list.
    #     """
    #     image64s = kwargs.get('image64s', None)  # List[str]
    #     messages_input = kwargs.get('messages', None)   # messages
    #
    #     if messages_input is not None:
    #         if isinstance(messages_input, dict):
    #             messages = [messages_input]  # 单消息包装为列表
    #         else:
    #             messages = messages_input
    #     else:
    #         content = []
    #         content.append({
    #                 "type": "text",
    #                 "text": prompt.strip()
    #             })
    #
    #         if image64s is not None:
    #             for image in image64s:
    #                 content.append({
    #                     "type": "image_url",
    #                     "image_url": {
    #                         "url": f"data:image/png;base64,{image}",
    #                     }
    #                 })
    #
    #         messages = [{
    #             'role': 'user',
    #             'content': content
    #         }]
    #
    #     while True:
    #         try:
    #             conn = http.client.HTTPSConnection(self._host, timeout=self._timeout)
    #             payload = json.dumps({
    #                 'max_tokens': self._kwargs.get('max_tokens', 8192),
    #                 'top_p': self._kwargs.get('top_p', None),
    #                 'temperature': self._kwargs.get('temperature', 1.0),
    #                 'model': self._model,
    #                 'messages': messages
    #             })
    #             headers = {
    #                 'Authorization': f'Bearer {self._key}',
    #                 'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
    #                 'Content-Type': 'application/json'
    #             }
    #             conn.request('POST', '/v1/chat/completions', payload, headers)
    #             res = conn.getresponse()
    #             data = res.read().decode('utf-8')
    #             data = json.loads(data)
    #             # print(data)
    #             response = data['choices'][0]['message']['content']
    #             if self.debug_mode:
    #                 self._cumulative_error = 0
    #             return response
    #         except Exception as e:
    #             self._cumulative_error += 1
    #             if self.debug_mode:
    #                 if self._cumulative_error == 10:
    #                     raise RuntimeError(f'{self.__class__.__name__} error: {traceback.format_exc()}.'
    #                                        f'You may check your API host and API key.')
    #             else:
    #                 print(f'{self.__class__.__name__} error: {traceback.format_exc()}.'
    #                       f'You may check your API host and API key.')
    #                 time.sleep(2)
    #             continue
