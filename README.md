# 紫金矿业研究面板

在线页面由 `index.html` 提供，包含总览、估值、散户情绪、大资金和官方信号模块。

## 重新生成页面

运行：

```powershell
python scripts/build_zijin_dashboard.py
```

脚本通过本机 Codex 配置读取 Tushare 访问令牌，并将结果写入 `outputs/index.html`。发布前将生成的文件同步为仓库根目录的 `index.html`。

仓库不保存飞书密钥、Tushare令牌或其他账户凭据。
