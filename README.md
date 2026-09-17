# FunSportWorld

校园运动自动化工具（Python 版）。

## 安装

```bash
pip install -r requirements.txt
```

## 使用

```bash
python -m funsport login --user 手机号 --pass 密码 --remember
python -m funsport points
python -m funsport run --dist 1.2 --pace 400
python -m funsport ai --sport 1 --mode min --score 3
python -m funsport records
python -m funsport semester
```

## 分层

- `funsport/crypto/` 协议加密（信封/头/解密/签名）
- `funsport/api/` 业务接口
- `funsport/track/` 轨迹生成
- `funsport/main.py` CLI 入口
