"""UIOT 适配层纯函数单测: 加密/解密往返与 MD5 签名确定性。

不联网、不需凭据(SECRET 为测试占位)。运行: pytest tests/
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import uiot_control as u

SECRET = "x" * 40  # 仅测试用, 不触发真实 API


def test_encrypt_decrypt_roundtrip():
    plain = '{"sn":"HOME_SN_DEMO"}'
    assert u.decrypt1(u.encrypt1(plain, SECRET), SECRET) == plain


def test_encrypt_key_uses_first_32_bytes():
    # AES-256 要求 32 字节密钥; 秘钥超长时应只取前 32 字节, 与 32 字节密钥结果一致
    plain = "abc"
    assert u.encrypt1(plain, SECRET) == u.encrypt1(plain, SECRET[:32])


def test_md5_deterministic_and_sensitive():
    h = {"method": "x", "appkey": "k", "timestamp": "1", "version": "1.0",
         "accessToken": "t", "Content-Type": "application/json"}
    assert u.md5(h, "", SECRET) == u.md5(h, "", SECRET)   # 同输入同输出
    h2 = dict(h)
    h2["timestamp"] = "2"
    assert u.md5(h2, "", SECRET) != u.md5(h, "", SECRET)   # 任一参数变化即改签名


def test_md5_ignores_sign_and_content_type_and_empty():
    base = {"method": "x", "appkey": "k", "timestamp": "1", "version": "1.0",
            "accessToken": "t", "Content-Type": "application/json"}
    h = dict(base)
    h["sign"] = "whatever"          # sign 不参与签名
    h["extra"] = ""                 # 空值不参与签名
    assert u.md5(h, "", SECRET) == u.md5(base, "", SECRET)
