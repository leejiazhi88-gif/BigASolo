# 紫金矿业研究面板

在线页面由 `index.html` 提供，包含总览、估值、散户情绪、大资金和官方信号模块。

## 在线验收地址

GitHub Pages:

https://leejiazhi88-gif.github.io/BigASolo/

发布分支为 `gh-pages`，页面入口为仓库根目录的 `index.html`。

日常更新流程：

```bash
git add .
git commit -m "Update dashboard"
git push origin main
git push origin main:gh-pages
```

换电脑后，克隆仓库即可继续维护：

```bash
git clone git@github.com:leejiazhi88-gif/BigASolo.git
```

## 重新生成页面

运行：

```powershell
python scripts/build_zijin_dashboard.py
```

脚本通过本机 Codex 配置读取 Tushare 访问令牌，并将结果写入 `outputs/index.html`。发布前将生成的文件同步为仓库根目录的 `index.html`。

仓库不保存飞书密钥、Tushare令牌或其他账户凭据。
