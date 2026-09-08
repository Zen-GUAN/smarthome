# AGENTS.md

本项目是 Home Assistant 智能家居中枢的参考实现，非标准 Python 库，无构建步骤、无 CI。

## 技术栈

Python 3.11 + requests + pycryptodome；Home Assistant 容器；巴法云 MQTT 桥接；
UIOT/保利智家 openapi 协议适配（AES-ECB 加密 + MD5 签名）。

## 目录

- `scripts/`     4 个独立 CLI 脚本，职责单一
- `config/`      automations 模板（巴法 MQTT 桥接）+ `ha-example/` 接线示例
- `docs/`        架构总览 / 桥接实操 / QPS 调研
- `tests/`       纯函数单测（pytest，不联网、不需凭据）

## 常用命令

```bash
# 列设备（需仓库根目录有 .env，凭据获取方式见 .env.example 注释）
python3 scripts/uiot_control.py list
python3 scripts/uiot_control.py on|off <deviceId>
python3 scripts/uiot_control.py ac <deviceId> <temp> [mode]

# 生成巴法自动化（需 AUTOMATIONS_YAML 指向 automations.yaml，且 HA_CONTAINER
# 指向可达的 HA 容器；脚本会先自动备份、容器内 YAML 校验、失败自动回滚）
python3 scripts/gen_bemfa_automations_v2.py

# 跑单测（先 pip install -r requirements.txt -r requirements-dev.txt）
pytest tests/
```

## 红线 / 边界

- `.env` 与含真实 device_id 的 HA 配置已被 `.gitignore` 排除，严禁提交
- UIOT 凭据需通过你与开发商/物业的既有协议获取，本项目不包含获取方法
- AES-ECB + MD5 签名为 UIOT 平台协议约束，不可"优化"改动
- `uiot_control.py` 每次控制都重取 token，是平台会话约束，非 bug

## 复刻前提（agent 无法自动满足）

- 需自备 HA 实例、巴法云账号、以及（可选）UIOT 平台访问权限
- agent 可复现代码与架构，无法复现用户私有设备生态
