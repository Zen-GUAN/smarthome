#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""巴法topic链路验证: 向topic推"ping"(payload非on/off不会触发设备动作) → 查HA接收自动化last_triggered是否实时变化。

环境变量:
  HASS_TOKEN          Home Assistant 长效访问令牌(必需)
  BEMFA_PRIVATE_KEY   巴法云私钥(控制台获取, 必需)
  HA_URL              HA地址, 默认 http://homeassistant.local:8123

用法: 在 NAMES 中维护 topic→中文名 映射后运行本脚本。
验收标准: 只认接收自动化的 last_triggered 实时变化, 不看设备状态(状态可能巧合一致)。
注意: HA里 last_triggered 是UTC, 北京时间=UTC+8。
"""
import json, time, urllib.request, os

TOK = os.environ["HASS_TOKEN"]
KEY = os.environ["BEMFA_PRIVATE_KEY"]
HA = os.environ.get("HA_URL", "http://homeassistant.local:8123")

def push(topic):
    body = json.dumps({'uid': KEY, 'topic': topic, 'type': 1, 'msg': 'ping'}).encode()
    req = urllib.request.Request('https://apis.bemfa.com/va/postJsonMsg', data=body,
                                 headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=15))

def states():
    req = urllib.request.Request(HA + '/api/states', headers={'Authorization': 'Bearer ' + TOK})
    return json.load(urllib.request.urlopen(req, timeout=30))

# topic → 设备中文名 (按自己的清单修改)
NAMES = {'mylight001': '示例灯一',
         'mylight002': '示例灯二'}

# 先确认HA API已就绪
for i in range(10):
    try:
        states()
        break
    except Exception:
        time.sleep(5)
print('HA API 已就绪, 开始推 ping')
for t in NAMES:
    r = push(t)
    print(f'  {t} code={r.get("code")}')
    time.sleep(0.4)

print('等 15 秒 ...')
time.sleep(15)
ok, bad = [], []
# 清零点用动态UTC时间(推ping时刻-60s), 别写死北京时间小时数
import datetime
cutoff = (datetime.datetime.utcnow() - datetime.timedelta(minutes=1)).strftime('%Y-%m-%dT%H:')
for st in states():
    if st['entity_id'].startswith('automation.bemfa') and '接收指令' in st['attributes'].get('friendly_name', ''):
        fn = st['attributes']['friendly_name'].replace('bemfa', '').replace('_接收指令', '')
        lt = st['attributes'].get('last_triggered') or ''
        if fn in NAMES.values():
            (ok if lt >= cutoff else bad).append(fn)
print(f'本轮触发成功 {len(ok)}/{len(NAMES)}: {ok}')
print(f'仍未触发 {len(bad)}: {bad}')
