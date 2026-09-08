# NAS 智能家居中枢（参考实现）

基于 UGREEN NAS(Docker) + Home Assistant 的全屋智能语音控制方案，供同类需求
参考复刻：对接 UIOT/保利智家设备控制协议（openapi 网关）直控灯与中央空调，
巴法云(bemfa.com) MQTT 桥接打通小爱同学/米家语音控制，涂鸦云集成接入
净化器/新风等标准设备。

本仓库给的是**可复用的方法与工具**，不是拿来即用的住宅配置——设备表、
实体ID、topic 全部为示例占位，请按你自己的家重新生成。

## 这份仓库怎么用

| 内容 | 性质 | 你需要做的 |
|---|---|---|
| docs/01~03 | 实操方法论（踩坑实录，2026-09 验证可跑） | 动手前通读，尤其 docs/02 的 client_id 难题与验收方法 |
| scripts/ | 可复用工具 | 把示例设备表/实体换成你自己的后直接用 |
| config/automations-template.yaml | 三种桥接模式的占位符模板 | 替换 `<TOPIC>`/`<ENTITY>` 占位符，或用 gen 脚本批量生成 |

## 整体架构

```
小爱音箱 ──语音──> 米家云 ──> 巴法云 bemfa.com ──MQTT(9501)──> Home Assistant(Docker on NAS)
                    (设备目录)   (topic 中转)                  │
                                                              ├─ UIOT openapi ──> 保利智家485网关 ──> 全屋灯/中央空调
                                                              ├─ 涂鸦云集成 ──> 净化器/新风/喂食器
                                                              └─ roborock 集成 ──> 扫地机
```

- 语音指令链路：小爱 → 米家 → 巴法(第三方技能) → MQTT 裸 topic → HA 自动化 → UIOT 设备
- 状态回传：HA 状态变化 → 发布到 `topic/up`（只更新云端记录，不推给订阅者，防回环）
- 实测全链路延迟约 1~3 秒；UIOT 设备侧状态同步另有 15~30 秒延迟

## 桥接模式速览

HA 原生 mqtt 实体当不了桥，正确模式是**每设备两条自动化**：

- 入站（接收指令）：`trigger: mqtt` 收裸 topic → 模板判断 payload → 调设备服务
- 出站（状态同步）：`trigger: state` → `mqtt.publish` 推 `<topic>/up` 防回环

三种模式模板见 `config/automations-template.yaml`：
单设备(灯/开关) / 合并组(一个 topic 控多路灯) / 空调(`on#模式#温度`)

## UIOT 设备控制协议要点（对接参考）

本项目对接 UIOT/保利智家设备的 openapi 网关，协议特征如下（供同类需求复刻参考，
与 `scripts/uiot_control.py` 实现一一对应）：

- **网关**：`https://openapi.unisiot.com/gateway`，请求体经 AES-256-ECB 加密后再做
  `hex → base64` 双重编码；密钥取 app_secret 前 32 字节
- **签名**：`md5(sorted(params 不含 sign/Content-Type) 拼接 + app_secret)`
- **鉴权**：OAuth2 password grant，以平台账号密码交换 access_token，每次调用携带
- **核心 API**：`device.list`（列设备/读状态）、`device.control`（下发 powerSwitch /
  thermostatMode / targetTemperature 等属性）
- **注意**：UIOT 空调 hvac_modes 仅 [off, cool, heat, dry, fan_only] 无 auto，
  巴法模式 1/6/7 需映射到 cool

以上为对接实现所需的协议事实；凭据获取请依据你与平台的既有协议。

## 硬件承载（无需 NAS）

本项目 HA 中枢可运行于任意满足"家庭内网 + 常开 + 支持 Docker/HAOS"的主机，
NAS 仅为作者的部署选择之一，并非前置条件。以下均可作为承载：

- 闲置电脑/笔记本：装 Linux 后 `docker compose up` 启动（见仓库 `docker-compose.yml`）
- 树莓派 4/5（建议 SSD 启动以避免 SD 卡损耗）
- x86 迷你主机（如 N100/N150，性价比高，可同时承载数据库与看板）
- 软路由旁挂 Docker、或 Home Assistant Green 一体机

核心要求只有两点：① 与你的智能设备处于同一家庭局域网；② 7×24 常开。
脚本与桥接逻辑与具体硬件解耦，迁移只需搬运 `scripts/`、`config/` 与 `.env`。

## 快速开始（以你自己的家为例）

> AI 编码代理协作指引见 `AGENTS.md`；一键起 HA + 本地 MQTT 调试栈见 `docker-compose.yml`。

1. **HA 直连巴法**：巴法强制 MQTT client_id=用户私钥，HA 配置流没有该字段，
   需 storage surgery 注入，完整步骤见 `docs/02-巴法云桥接实操.md`
2. **建 topic**：巴法控制台手动建(无API)，名称只允许字母数字，类型后缀
   `002`=灯、`005`=空调，协议选 MQTT（完整后缀表见 docs/01）
3. **生成自动化**：维护你自己的设备表（key/中文名/topic/实体/kind），
   用 `scripts/gen_bemfa_automations_v2.py` 批量生成，或手改
   `config/automations-template.yaml`；生成脚本追加前自动备份当前文件，
   YAML 校验失败自动回滚到追加前内容
4. **新建 topic 后必须重启 HA**：巴法不会向已有连接投递新建 topic 的消息，
   `automation.reload` 不会重新 SUBSCRIBE，只有重连才生效
5. **米家绑定**：米家App → 我的 → 其他平台设备 → 巴法，输入巴法控制台账号密码
   （注意：巴法设备在米家App里不可见是正常的，同步对象是小爱侧设备目录）
6. **验收**：`scripts/bemfa_ping_verify.py` 推 ping 验链路；语音验收以
   HA 接收自动化的 `last_triggered` 实时变化为准（UTC时间，北京时间=UTC+8）

## 目录说明

```
├── README.md                     本文件
├── AGENTS.md                     AI 编码代理协作指引(项目地图/常用命令/边界)
├── docker-compose.yml            一键起 HA + 本地 Mosquitto 调试栈
├── docs/
│   ├── 01-架构总览.md             分层架构/桥接模式/topic约定/双注册问题
│   ├── 02-巴法云桥接实操.md       HA直连巴法完整实操(client_id难题/验收方法/踩坑清单)
│   └── 03-巴法QPS离线调研.md      小爱"服务器离线"问题根因分析与实测
├── config/
│   ├── automations-template.yaml 三种桥接模式的占位符模板(单设备/合并组/空调/定时示例)
│   └── ha-example/
│       └── uiot-command-line.yaml UIOT 经 command_line 接入 HA 的示例(脱敏占位)
├── scripts/
│   ├── uiot_control.py           UIOT 设备控制 CLI(list/on/off/ac/raw)
│   ├── gen_bemfa_automations_v2.py 按设备表批量生成 bemfa 收发自动化
│   ├── bemfa_ping_verify.py      topic 链路验收(ping 不动设备,只认 last_triggered)
│   └── qps_rapid_test.py         巴法 QPS 限流复现脚本
├── tests/
│   └── test_uiot_crypto.py       加密/签名纯函数单测(pytest, 不联网)
├── .env.example                  凭据模板(复制为 .env 填入真实值)
├── requirements.txt              Python 运行时依赖(仅 uiot_control.py 需要)
├── requirements-dev.txt          测试依赖(pytest)
├── LICENSE                       MIT
└── .gitignore
```

## 凭据管理

所有凭据集中在 `.env`（已被 .gitignore 排除，严禁提交）：

- UIOT 开放平台：`UIOT_APP_KEY / UIOT_APP_SECRET / UIOT_HOME_SN / UIOT_ACCOUNT / UIOT_PASSWORD / UIOT_OAUTH_TOKEN_URL`
- 巴法云：`BEMFA_PRIVATE_KEY`（32位hex，同时是 MQTT client_id）
- Home Assistant：`HASS_TOKEN / HA_URL`

## 已知限制

- 巴法免费版共享服务器有 QPS 限流：快速连续语音指令（如开灯马上关灯）会触发
  设备"临时离线几秒"，小爱播报离线类错误；官方解法是升 VIP，详见 `docs/03`
- UIOT openapi 状态回传延迟 15~30 秒（控制是即时的，只是状态反馈慢）
- 涂鸦云温控器延迟 30~90 秒，只适合当空调备用通道
- 小爱音箱 ASR 文本锁在小米云端拿不到，只能走固定指令控制，做不了自由对话

## 安全说明

- 本仓库已脱敏：不含任何密钥/令牌/账号/内网IP/设备ID，也不含真实住宅的设备
  配置——设备表、实体ID、topic 均为通用示例；涂鸦 local key、设备 MAC/SN 等
  敏感清单未收入仓库
- 密钥一律走 `.env`
- MQTT 直连巴法时 client_id=私钥，同一私钥重复连接会互踢，勿多处同时连

## 合规说明

本项目仅用于对接你**已合法获得访问权限**的设备控制接口，所有凭据经 `.env` 管理、
绝不入库；仓库不含任何凭据获取方法，亦不鼓励对未授权接口的请求。请遵守你所使用
平台的条款与当地法律法规。
