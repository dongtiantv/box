# -*- coding: utf-8 -*-
# 本资源来源于互联网公开渠道，仅可用于个人学习爬虫技术。
# 严禁将其用于任何商业用途，下载后请于 24 小时内删除，搜索结果均来自源站，本人不承担任何责任。
#
# 修复说明：
# 1. 参考“金牌影视”把 sys.path.append('..') 放到 from base.spider import Spider 前面，
#    避免部分壳/运行环境加载插件时找不到 base.spider，导致“无法识别”。
# 2. 增加 init(ext) 支持，可在配置 ext 中传入 {"site":"https://bubutv.top,备用域名"}。
# 3. 统一处理 host 末尾斜杠，避免请求地址出现 //api.php。
# 4. 补齐 homeVideoContent、getName 等方法返回，增强字段容错，减少接口字段变化导致崩溃。
# 5. device_id 改为稳定 16 位随机值缓存，避免把包名字符串误当 device id 使用。

import sys
sys.path.append('..')

from base.spider import Spider
import json
import re
import time
import random
import secrets
import hashlib
import urllib3
import threading
import requests
from urllib.parse import quote

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class Spider(Spider):
    host = 'https://bubutv.top'
    device_id = ''

    def init(self, extend=''):
        # 支持配置：
        # "ext": {"site": "https://bubutv.top,https://备用域名"}
        try:
            if extend:
                ext = json.loads(extend) if isinstance(extend, str) else extend
                site = ext.get('site') or ext.get('host') or ext.get('url')
                if site:
                    self.host = self.host_late(site)
        except Exception:
            pass
        self.host = (self.host or 'https://bubutv.top').rstrip('/')

    def getName(self):
        return '布布'

    def homeContent(self, filter):
        if not self.host:
            self.init()
        response = self.fetch(
            f'{self.host}/api.php/app/index/home',
            headers=self.headers(),
            verify=False,
            timeout=30
        ).json()

        categories = response.get('data', {}).get('categories', []) if isinstance(response.get('data'), dict) else []
        videos, classes = [], []
        for i in categories:
            type_name = i.get('type_name') or i.get('typeName') or ''
            if not type_name:
                continue
            classes.append({'type_id': type_name, 'type_name': type_name})
            videos.extend(self.arr2vods(i.get('videos', [])))
        return {'class': classes, 'list': videos}

    def homeVideoContent(self):
        try:
            data = self.homeContent(False)
            return {'list': data.get('list', [])}
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        if not self.host:
            self.init()
        tid_q = quote(str(tid))
        response = self.fetch(
            f'{self.host}/api.php/app/filter/vod?type_name={tid_q}&page={pg}&sort=hits',
            headers=self.headers(),
            verify=False,
            timeout=30
        ).json()

        data = response.get('data', [])
        return {
            'list': self.arr2vods(data if isinstance(data, list) else []),
            'pagecount': int(response.get('pageCount') or response.get('pagecount') or 9999),
            'page': int(pg),
            'limit': 20,
            'total': 999999
        }

    def searchContent(self, key, quick, pg='1'):
        if not self.host:
            self.init()
        key_q = quote(str(key))
        response = self.fetch(
            f'{self.host}/api.php/app/search/index?wd={key_q}&page={pg}&limit=15',
            headers=self.headers(),
            verify=False,
            timeout=30
        ).json()

        data = response.get('data', [])
        return {
            'list': self.arr2vods(data if isinstance(data, list) else []),
            'pagecount': int(response.get('pageCount') or response.get('pagecount') or 9999),
            'page': int(pg)
        }

    def detailContent(self, ids):
        if not self.host:
            self.init()
        response = self.fetch(
            f'{self.host}/api.php/app/vod/get_detail?vod_id={ids[0]}',
            headers=self.headers(),
            verify=False,
            timeout=30
        ).json()

        data_list = response.get('data') or []
        if isinstance(data_list, dict):
            data = data_list
        elif isinstance(data_list, list) and data_list:
            data = data_list[0]
        else:
            return {'list': []}

        shows, play_urls = [], []
        raw_shows = str(data.get('vod_play_from') or '').split('$$$')
        raw_urls_list = str(data.get('vod_play_url') or '').split('$$$')
        players = response.get('vodplayer') or response.get('player') or []

        for show_code, urls_str in zip(raw_shows, raw_urls_list):
            if not show_code or not urls_str:
                continue

            need_parse, is_show, name, urls = 0, 0, show_code, []
            if isinstance(players, list) and players:
                for i in players:
                    if str(i.get('from', '')).casefold() == show_code.casefold():
                        is_show = 1
                        need_parse = i.get('decode_status', 0)
                        show_name = i.get('show') or show_code
                        if show_code.casefold() != str(show_name).casefold():
                            name = f"{show_name}\u2005({show_code})"
                        break
            else:
                is_show = 1

            if is_show == 1:
                for url_item in str(urls_str).split('#'):
                    if '$' in url_item:
                        episode, url = url_item.split('$', 1)
                        if url:
                            urls.append(f"{episode}${show_code}@{int(need_parse)}@{url}")
                if urls:
                    play_urls.append('#'.join(urls))
                    shows.append(name)

        video = {
            'vod_id': data.get('vod_id', ids[0]),
            'vod_name': data.get('vod_name', ''),
            'vod_pic': data.get('vod_pic', ''),
            'vod_remarks': data.get('vod_remarks', ''),
            'vod_year': data.get('vod_year', ''),
            'vod_area': data.get('vod_area', ''),
            'vod_actor': data.get('vod_actor', ''),
            'vod_director': data.get('vod_director', ''),
            'vod_content': data.get('vod_content', ''),
            'vod_play_from': '$$$'.join(shows),
            'vod_play_url': '$$$'.join(play_urls),
            'type_name': data.get('vod_class', '')
        }
        return {'list': [video]}

    def playerContent(self, flag, vid, vip_flags):
        try:
            play_from, need_parse, raw_url = vid.split('@', 2)
        except Exception:
            return {'jx': 0, 'parse': 0, 'url': vid, 'header': self.play_header()}

        jx, url = 0, ''
        if str(need_parse) == '1':
            try:
                response = self.fetch(
                    f'{self.host}/api.php/app/decode/url/?url={quote(raw_url, safe="")}&vodFrom={quote(play_from)}',
                    headers=self.headers(),
                    timeout=30,
                    verify=False
                ).json()
                play_url = response.get('data') or ''
                if isinstance(play_url, dict):
                    play_url = play_url.get('url') or play_url.get('play_url') or ''
                if isinstance(play_url, str) and play_url.startswith('http'):
                    url = play_url
            except Exception:
                pass

        if not url:
            url = raw_url
            if re.search(r'(?:www\.iqiyi|v\.qq|v\.youku|www\.mgtv|www\.bilibili)\.com', raw_url):
                jx = 1

        return {'jx': jx, 'parse': 0, 'url': url, 'header': self.play_header()}

    def arr2vods(self, arr):
        videos = []
        if not isinstance(arr, list):
            return videos

        for i in arr:
            if not isinstance(i, dict):
                continue
            type_name = i.get('type_name') or ''
            vod_class = i.get('vod_class') or ''
            if vod_class:
                type_name = f"{type_name},{vod_class}" if type_name else vod_class
            videos.append({
                'vod_id': i.get('vod_id', ''),
                'vod_name': i.get('vod_name', ''),
                'vod_pic': i.get('vod_pic', ''),
                'vod_remarks': i.get('vod_remarks', ''),
                'type_name': type_name,
                'vod_year': i.get('vod_year', '')
            })
        return videos

    def headers(self):
        timestamp = str(int(time.time()))
        nonce = ''.join(random.choice('0123456789') for _ in range(3))
        ver, pkg = '3', 'com.sunshine.tv'
        sign_str = (
            f"finger=SF-C3B2B41F6EFFFF9869176CF68F6790E8F07506FC88632C94B4F5F0430D5498CA"
            f"&id={pkg}&nonce={nonce}&sk=SK-thanks&time={timestamp}&v={ver}"
        )
        sign = hashlib.sha256(sign_str.encode('utf-8')).hexdigest().upper()

        device_id_cache_key = 'bubu_device_id_16'
        try:
            if not (isinstance(self.device_id, str) and len(self.device_id) == 16):
                self.device_id = self.getCache(device_id_cache_key)
            if not (isinstance(self.device_id, str) and len(self.device_id) == 16):
                self.device_id = ''.join(secrets.choice('0123456789abcdef') for _ in range(16))
                self.setCache(device_id_cache_key, self.device_id)
        except Exception:
            if not (isinstance(self.device_id, str) and len(self.device_id) == 16):
                self.device_id = ''.join(random.choice('0123456789abcdef') for _ in range(16))

        return {
            'User-Agent': 'okhttp/4.12.0',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip',
            'x-aid': pkg,
            'x-ave': ver,
            'x-time': timestamp,
            'x-nonc': nonce,
            'x-sign': sign,
            'x-device-id': self.device_id,
            'x-device-brand': 'vivo',
            'x-device-model': 'V2309A',
            'x-update-id': '0245861b-2ebf-5524-389d-f983830651ec'
        }

    def play_header(self):
        return {
            'User-Agent': 'com.sunshine.tv/1.2.0 (Linux;Android 15) AndroidXMedia3/1.4.1'
        }

    def host_late(self, url_list):
        if isinstance(url_list, str):
            urls = [u.strip().rstrip('/') for u in url_list.split(',') if u.strip()]
        else:
            urls = [str(u).strip().rstrip('/') for u in url_list if str(u).strip()]

        if len(urls) <= 1:
            return urls[0] if urls else self.host

        results = {}
        threads = []

        def test_host(url):
            try:
                start_time = time.time()
                requests.head(url, timeout=1.0, allow_redirects=False, verify=False)
                results[url] = (time.time() - start_time) * 1000
            except Exception:
                results[url] = float('inf')

        for url in urls:
            t = threading.Thread(target=test_host, args=(url,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        return min(results.items(), key=lambda x: x[1])[0] if results else self.host

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    def localProxy(self, param):
        pass
