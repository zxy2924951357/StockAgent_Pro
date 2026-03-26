import requests
import os

print("🔍 开始测试东方财富底层数据直连...")

# 强行清空环境变量代理
for k in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
    os.environ.pop(k, None)

url = "http://push2.eastmoney.com/api/qt/ulist.np/get?secids=1.000001&fields=f14,f2,f3"

try:
    # 禁用 session 代理并设置 5 秒超时
    session = requests.Session()
    session.trust_env = False
    res = session.get(url, timeout=5)

    print(f"👉 状态码: {res.status_code}")
    print(f"👉 返回数据: {res.text[:100]}...")
    print("✅ 测试成功！你的 Python 可以直连东方财富服务器！")

except Exception as e:
    print(f"❌ 测试失败！网络被彻底阻断，报错信息: {e}")