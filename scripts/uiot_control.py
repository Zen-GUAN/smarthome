#!/usr/bin/env python3
"""
UIOT(保利智家)开放平台 设备控制统一脚本
凭据从 .env 文件读取(可用环境变量 ENV_FILE 指定路径, 默认为仓库根目录 .env)。
用法:
  python3 uiot_control.py list                        # 列出所有设备
  python3 uiot_control.py list <房间关键词>            # 按房间过滤(如"客厅")
  python3 uiot_control.py on <deviceId>               # 开灯/开设备 (powerSwitch on)
  python3 uiot_control.py off <deviceId>              # 关灯/关设备 (powerSwitch off)
  python3 uiot_control.py ac <deviceId> <temp> [mode] # 设空调温度并开 (可选 mode: cool/heat/dry/fan/auto)
  python3 uiot_control.py raw <deviceId> <json>       # 原始 properties(json)
"""
import sys, json, time, base64, hashlib, os
import requests
from Crypto.Cipher import AES

# 凭据文件: 默认仓库根目录 .env, 可用环境变量 ENV_FILE 覆盖
ENV_FILE = os.environ.get("ENV_FILE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".env")

def _env():
    d = {}
    try:
        with open(ENV_FILE) as f:
            for ln in f:
                ln = ln.strip()
                if ln and not ln.startswith('#'):
                    k, _, v = ln.partition('=')
                    d[k.strip()] = v.strip()
    except Exception as e:
        print("ERR reading env:", e)
    return d

E = _env()
APP_KEY = E.get("UIOT_APP_KEY")
APP_SECRET = E.get("UIOT_APP_SECRET")
HOME_SN = E.get("UIOT_HOME_SN")
GATEWAY = E.get("UIOT_GATEWAY", "https://openapi.unisiot.com/gateway")
OAUTH = E.get("UIOT_OAUTH_TOKEN_URL")
ACCOUNT = E.get("UIOT_ACCOUNT")
PASSWORD = E.get("UIOT_PASSWORD")

def ts_ms(): return str(int(time.time()*1000))
def encrypt1(text, secret):
    key=(secret.encode())[:32]; pad=16-(len(text.encode())%16)
    padded=text.encode()+(chr(pad)*pad).encode()
    return base64.b64encode(AES.new(key,AES.MODE_ECB).encrypt(padded).hex().encode()).decode()
def decrypt1(b64, secret):
    hexstr=base64.b64decode(b64).decode(); raw=bytes.fromhex(hexstr)
    pt=AES.new((secret.encode())[:32],AES.MODE_ECB).decrypt(raw); pad=pt[-1]
    return pt[:-pad if 0<pad<=16 else 0].decode('utf-8','ignore')
def md5(h, d, s):
    i=[f"{k}={h[k]}" for k in sorted(h) if k not in('sign','Content-Type') and h[k] not in(None,'')]
    return hashlib.md5(("&".join(i)+s).encode()).hexdigest()

def _call(method, body, token):
    bs=json.dumps(body,separators=(",",":"))
    h={"method":method,"appkey":APP_KEY,"timestamp":ts_ms(),"version":"1.0","isEncrypt":"true","accessToken":token,"Content-Type":"application/json; charset=utf-8"}
    de=encrypt1(bs,APP_SECRET); h["data"]=de; h["sign"]=md5(h,de,APP_SECRET)
    r=requests.post(GATEWAY,headers=h,data=de,timeout=20)
    try: return r.json()
    except: return {"raw": r.text[:200]}

def get_token():
    p={"grant_type":"password","username":ACCOUNT,"password":PASSWORD,"client_id":APP_KEY,"client_secret":APP_SECRET}
    r=requests.post(OAUTH,data=p,headers={"Content-Type":"application/x-www-form-urlencoded"},timeout=25)
    j=r.json()
    t=j.get("access_token")
    if not t:
        print("TOKEN_ERR:", str(j)[:200])
    return t

def list_devices(token, keyword=None):
    j=_call("uiotsoft.openapi.device.list",{"sn":HOME_SN},token)
    if j.get("code") != 0:
        print("LIST_ERR:", j); return []
    devs=json.loads(decrypt1(j["data"],APP_SECRET))["deviceList"]
    for d in devs:
        rm=d.get("roomName",""); name=d.get("deviceName","")
        if keyword and keyword not in rm and keyword not in name:
            continue
        ps=d.get("properties",{}).get("powerSwitch")
        ac_props = d.get("properties",{})
        t = ac_props.get("targetTemperature") or ""
        m = ac_props.get("thermostatMode") or ""
        extra = ""
        if d.get("model")=="hvac_smart_gateway_engineering_ac":
            extra = f" AC[temp={t} mode={m}]"
        print(f"  id={d.get('deviceId')} [{rm}] {name} ps={ps} model={d.get('model')}{extra}")

def control(token, deviceId, properties):
    return _call("uiotsoft.openapi.device.control",{"sn":HOME_SN,"deviceId":int(deviceId),"properties":properties},token)

def main():
    args=sys.argv[1:]
    if not args:
        print(__doc__); return
    token=get_token()
    if not token: return
    cmd=args[0]
    if cmd=="list":
        kw=args[1] if len(args)>1 else None
        list_devices(token,kw)
    elif cmd=="on":
        c=control(token,args[1],{"powerSwitch":"on"})
        print("RESULT:", c.get("code"), c.get("desc"))
    elif cmd=="off":
        c=control(token,args[1],{"powerSwitch":"off"})
        print("RESULT:", c.get("code"), c.get("desc"))
    elif cmd=="ac":
        did=args[1]; temp=args[2]; mode=args[3] if len(args)>3 else "cool"
        c=control(token,did,{"powerSwitch":"on","thermostatMode":mode,"targetTemperature":temp})
        print("RESULT:", c.get("code"), c.get("desc"))
    elif cmd=="raw":
        c=control(token,args[1],json.loads(args[2]))
        print("RESULT:", c.get("code"), c.get("desc"))
    else:
        print("unknown cmd:", cmd)

if __name__=="__main__":
    main()
