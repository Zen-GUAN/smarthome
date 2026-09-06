#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""巴法免费版QPS限流实测: 0.4秒间隔快速连发3条ping(payload不含on/off, 不会动设备),
观察HTTP API返回码、云端留存与HA接收自动化触发情况。
背景结论(2026-09实测): 巴法→HA的MQTT腿在快速连发下仍正常; 小爱报"服务器离线"
发生在米家云→巴法智能家居控制接口一腿, 详见 docs/03-巴法QPS离线调研.md。

环境变量:
  HASS_TOKEN          Home Assistant 长效访问令牌(必需)
  BEMFA_PRIVATE_KEY   巴法云私钥(必需)
  HA_URL              HA地址, 默认 http://homeassistant.local:8123
  BEMFA_TEST_TOPIC    被测topic, 默认 mylight001
"""
import json, time, urllib.request, os

TOK = os.environ["HASS_TOKEN"]
KEY = os.environ["BEMFA_PRIVATE_KEY"]
HA = os.environ.get("HA_URL", "http://homeassistant.local:8123")
TOPIC = os.environ.get("BEMFA_TEST_TOPIC", "mylight001")
AUTO = 'automation.bemfa_shi_li_deng_yi_jie_shou_zhi_ling'  # 按实际自动化entity_id修改

def ha_last_triggered():
    req = urllib.request.Request(HA + '/api/states/' + AUTO,
                                 headers={'Authorization': 'Bearer ' + TOK})
    return json.load(urllib.request.urlopen(req, timeout=15))['attributes'].get('last_triggered')

def push(msg):
    body = json.dumps({'uid': KEY, 'topic': TOPIC, 'type': 1, 'msg': msg}).encode()
    req = urllib.request.Request('https://apis.bemfa.com/va/postJsonMsg', data=body,
                                 headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=15))

def getmsg():
    url = ('https://apis.bemfa.com/va/getmsg?uid=' + KEY + '&topic=' + TOPIC
           + '&num=5&type=1')
    return json.load(urllib.request.urlopen(url, timeout=15))

# 0. 基线
base_msgs = getmsg()
base_count = len(base_msgs.get('data') or [])
base_lt = ha_last_triggered()
print('基线: 云端留存消息数=%s, HA last_triggered=%s' % (base_count, base_lt))

# 1. 快速连发3条ping, 间隔0.4秒, 记录每次HTTP返回码
codes = []
for i in range(3):
    r = push('ping')
    codes.append(r.get('code'))
    print('  第%d条 ping: HTTP API code=%s (间隔0.4s)' % (i + 1, r.get('code')))
    time.sleep(0.4)

# 2. 查云端实际留存了几条(限流/丢弃会体现为留存数不足)
time.sleep(2)
now_msgs = getmsg().get('data') or []
now_count = len(now_msgs)
print('连发后: 云端留存消息数=%s (新增%s条, 期望3条)' % (now_count, now_count - base_count))

# 3. HA侧触发验证: 轮询20秒等last_triggered变化
fired = False
for _ in range(40):
    time.sleep(0.5)
    lt = ha_last_triggered()
    if lt and lt != base_lt:
        print('HA接收自动化已触发: last_triggered=%s (链路通)' % lt)
        fired = True
        break
if not fired:
    print('HA接收自动化20秒内未触发!')

# 4. 单条正常间隔对照: 等3秒再推1条
time.sleep(3)
r = push('ping')
lt_before = ha_last_triggered()
ok = False
for _ in range(30):
    time.sleep(0.5)
    lt = ha_last_triggered()
    if lt and lt != lt_before:
        print('对照(间隔3s单条): code=%s, 触发成功 %s' % (r.get('code'), lt))
        ok = True
        break
if not ok:
    print('对照(间隔3s单条): code=%s, 未触发' % r.get('code'))
