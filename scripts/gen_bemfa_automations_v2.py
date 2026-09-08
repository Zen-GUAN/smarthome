#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按设备表批量生成巴法云收/发自动化, 追加进 automations.yaml(每设备收发各一条)。

用法: 把 DEVICES 换成你自己的设备清单(表内为示例占位), 设 AUTOMATIONS_YAML
指向 HA 的 automations.yaml 后运行。
- 若存在批量前备份 <P>.bak_before_batch, 运行时先恢复到该备份再追加(可重复执行);
- 无论有无备份, 追加前总把当前文件留底为 <P>.pre_append.bak;
- 追加后在 HA 容器内做 YAML 校验(docker exec; 容器内已含 PyYAML, 本机无需安装),
  校验失败自动回滚到追加前内容。
"""
import shutil, time, subprocess, os

# 路径与容器名按实际环境修改, 也可用环境变量覆盖
P = os.environ.get('AUTOMATIONS_YAML', './automations.yaml')
HA_CONTAINER = os.environ.get('HA_CONTAINER', 'homeassistant')
BAK0 = P + '.bak_before_batch'   # 批量前备份(可选, 存在则先恢复)
PRE = P + '.pre_append.bak'      # 追加前自动留底(总是创建)

# 示例设备表 —— 换成你自己的!
# kind: L=单灯/开关 M=合并组(一个topic控多路灯) C=空调
# (key, 中文标签, topic, 实体或实体列表, kind)
DEVICES = [
    ('light1', '示例灯一', 'mylight001', 'switch.my_light_1', 'L'),
    ('light2', '示例灯二', 'mylight002', 'switch.my_light_2', 'L'),
    ('group1', '示例灯组', 'mygroup001', ['switch.my_light_3', 'switch.my_light_4'], 'M'),
    ('ac1',    '示例空调', 'kongtiao005', 'climate.my_ac_1', 'C'),
]

def ents_yaml(ents, indent):
    if isinstance(ents, str):
        return f'"{ents}"'
    return '\n' + '\n'.join(' ' * indent + f'- "{e}"' for e in ents)

def single_in(key, label, topic, ent):
    return f"""- id: bemfa_{key}_in
  alias: bemfa{label}_接收指令
  trigger:
    - platform: mqtt
      topic: {topic}
  action:
    - choose:
        - conditions:
            - condition: template
              value_template: "{{{{ trigger.payload == 'on' }}}}"
          sequence:
            - service: switch.turn_on
              target:
                entity_id: "{ent}"
        - conditions:
            - condition: template
              value_template: "{{{{ trigger.payload == 'off' }}}}"
          sequence:
            - service: switch.turn_off
              target:
                entity_id: "{ent}"
  mode: single
"""

def single_out(key, label, topic, ent):
    return f"""- id: bemfa_{key}_out
  alias: bemfa{label}_状态同步
  trigger:
    - platform: state
      entity_id: "{ent}"
  action:
    - service: mqtt.publish
      data:
        topic: {topic}/up
        payload: "{{{{ 'on' if is_state('{ent}', 'on') else 'off' }}}}"
        retain: false
  mode: single
"""

def merged_in(key, label, topic, ents):
    return f"""- id: bemfa_{key}_in
  alias: bemfa{label}_接收指令
  trigger:
    - platform: mqtt
      topic: {topic}
  action:
    - choose:
        - conditions:
            - condition: template
              value_template: "{{{{ trigger.payload == 'on' }}}}"
          sequence:
            - service: switch.turn_on
              target:
                entity_id:
{chr(10).join(' ' * 20 + f'- "{e}"' for e in ents)}
        - conditions:
            - condition: template
              value_template: "{{{{ trigger.payload == 'off' }}}}"
          sequence:
            - service: switch.turn_off
              target:
                entity_id:
{chr(10).join(' ' * 20 + f'- "{e}"' for e in ents)}
  mode: single
"""

def merged_out(key, label, topic, ents):
    trig = '\n'.join(f'    - platform: state\n      entity_id: "{e}"' for e in ents)
    cond = ' or '.join(f"is_state('{e}', 'on')" for e in ents)
    return f"""- id: bemfa_{key}_out
  alias: bemfa{label}_状态同步
  trigger:
{trig}
  action:
    - service: mqtt.publish
      data:
        topic: {topic}/up
        payload: "{{{{ 'on' if {cond} else 'off' }}}}"
        retain: false
  mode: single
"""

def ac_in(key, label, topic, ent):
    return f"""- id: bemfa_{key}_in
  alias: bemfa{label}_接收指令
  trigger:
    - platform: mqtt
      topic: {topic}
  action:
    - choose:
        - conditions:
            - condition: template
              value_template: "{{{{ trigger.payload == 'on' }}}}"
          sequence:
            - service: climate.turn_on
              target:
                entity_id: "{ent}"
        - conditions:
            - condition: template
              value_template: "{{{{ trigger.payload == 'off' }}}}"
          sequence:
            - service: climate.turn_off
              target:
                entity_id: "{ent}"
        - conditions:
            - condition: template
              value_template: "{{{{ trigger.payload.startswith('on#') }}}}"
          sequence:
            - service: climate.set_temperature
              data:
                temperature: "{{{{ trigger.payload.split('#')[2] | int(26) if trigger.payload.split('#') | length > 2 else 26 }}}}"
                hvac_mode: "{{{{ {{'1':'cool','2':'cool','3':'heat','4':'fan_only','5':'dry','6':'cool','7':'cool'}}.get(trigger.payload.split('#')[1], 'cool') }}}}"
              target:
                entity_id: "{ent}"
  mode: single
"""

def ac_out(key, label, topic, ent):
    return f"""- id: bemfa_{key}_out
  alias: bemfa{label}_状态同步
  trigger:
    - platform: state
      entity_id: "{ent}"
    - platform: state
      entity_id: "{ent}"
      attribute: temperature
  action:
    - service: mqtt.publish
      data:
        topic: {topic}/up
        payload: >-
          {{% if is_state('{ent}', 'off') %}}off{{% else %}}on#{{{{ {{'cool':'2','heat':'3','dry':'5','fan_only':'4'}}.get(states('{ent}'), '2') }}}}#{{{{ state_attr('{ent}', 'temperature') | int(26) }}}}{{% endif %}}
        retain: false
  mode: single
"""

GEN = {'L': (single_in, single_out),
       'M': (merged_in, merged_out),
       'C': (ac_in, ac_out)}

if os.path.exists(BAK0):
    shutil.copy(BAK0, P)
    print('restored pre-batch backup')

block = '\n'
for key, label, topic, ent, kind in DEVICES:
    fi, fo = GEN[kind]
    block += fi(key, label, topic, ent) + fo(key, label, topic, ent)

if os.path.exists(P):
    shutil.copy(P, PRE)  # 追加前永远留底, 保证校验失败可自动回滚
    print('pre-append backup saved:', PRE)

with open(P, 'a') as f:
    f.write(block)
print('appended', len(DEVICES) * 2, 'automations')

r = subprocess.run(['docker', 'exec', HA_CONTAINER, 'python3', '-c',
                    'import yaml;yaml.safe_load(open("/config/automations.yaml"));print("YAML_OK")'],
                   capture_output=True, text=True, timeout=120)
print(r.stdout.strip() or r.stderr.strip()[-500:])
if 'YAML_OK' not in r.stdout:
    src = BAK0 if os.path.exists(BAK0) else PRE
    if os.path.exists(src):
        shutil.copy(src, P)
        print('!! YAML INVALID - 已自动回滚到追加前内容, NOT reloaded')
    else:
        print('!! YAML INVALID - NOT reloaded, 请手动删除刚追加的段落')
else:
    print('YAML valid, ready for reload')
