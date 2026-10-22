# 栖居 Bluehome

非官方米家家庭控制台，提供家庭、楼层、房间、3D 示意布局、MIoT 设备预览与控制、红外指令推测状态，以及需要逐次确认的智能建议。参考 [MiHome-Windows](https://github.com/huanyuejue/MiHome-Windows) 与 [mijia-api](https://github.com/Do1e/mijia-api) 的公开思路。

> 红外“开/关”是本应用依据已接受的按键记录做出的推测，不能证明电器实际收到信号。原装遥控器或其他 App 的操作不会自动同步。本项目不是小米官方应用。

## 可用版本

- 飞牛 NAS：`nas/build.ps1` 用飞牛官方 fnpack 1.2.3 构建 Docker 型 `.fpk`。连接器常驻 NAS，电脑可以关机。
- Android：`mobile/build.ps1` 构建侧载测试 APK。手机可连接 NAS 的局域网 IP，或连接配置了 Cloudflare Tunnel 与 Access 的 HTTPS 域名；首次需输入容器日志里的八位配对码。
- Windows：`desktop/build.ps1` 构建独立连接器。家中有 NAS 时，Windows 浏览器直接访问 `http://NAS局域网IP:4174/app/`；无需运行 Windows 连接器。

Android APK 使用本地调试签名，只供侧载测试。正式发布需长期签名密钥。Android 8.0 及以上可安装。设备控制仍需米家网络服务；状态刷新受轮询间隔和设备规格限制。

## 飞牛 NAS 安装

1. 在飞牛应用中心启用 Docker，并用“手动安装应用”选择最新的 `bluehome-mijia-1.0.4.fpk`。应用第一次启动会拉取多架构 `python:3.12-slim` 镜像，并联网安装 `mijiaAPI` 等依赖。已有旧版可直接升级，应用数据目录中的米家登录凭据会保留。
2. 在飞牛 Docker 中打开 `bluehome-mijia` 容器日志，找到“局域网配对码”。在 Windows 浏览器访问 `http://NAS局域网IP:4174/`，输入配对码。这一步仅配对浏览器；随后还需用手机米家 App 扫描接入页的二维码并确认，设备读取完成后控制台会自动打开。若直接进入 `/app/`，页面也会等待米家连接完成，不再展示演示设备。
3. 在 Android App 中输入 NAS 的局域网 IPv4 地址并配对。NAS 保持运行后，Windows 可以关机。重启容器会更换配对码；米家登录凭据保存在飞牛应用数据目录。

FPK 已通过 fnpack 打包校验。还需在你的飞牛设备上完成安装与实机启动验证。请不要把 4174 端口映射到公网；局域网连接使用 HTTP，仅适合可信的家庭 Wi‑Fi。

也可使用仓库根目录 `compose.yaml` 手动部署在有 Docker Compose 的 NAS 上：复制 `.env.example` 为 `.env`，填入 NAS 局域网 IP，运行 `docker compose up -d --build`。这种方式与 FPK 二选一，避免占用同一个端口。

若希望手机端完全不安装 VPN，可用已加入 Cloudflare 的自有域名配置 HTTPS 远程入口：在飞牛上运行 Cloudflare Tunnel，将专用子域名转发到 `http://NAS局域网IP:4174`，并在 Cloudflare Access 为该子域名启用仅允许本人邮箱的一次性验证码策略。飞牛容器环境变量 `BLUEHOME_HTTPS_HOST` 要设为该子域名（不带 `https://`、路径或端口），重启连接器后，Android App 填入 `https://子域名`。此模式的访问顺序是 Cloudflare Access 身份验证、栖居八位码配对、设备控制。请先完成 Access 限制，再启用公开域名；单独创建 Tunnel 会使网页入口向所有人可达。云端代理商会处理经过其网络的请求，请在使用前考虑家庭数据隐私。HTTPS 域名入口暂未在你的飞牛与手机上实测。

## 安全与数据

### 手机连接排查与外网使用

手机和电脑都在家里时，先在两台设备的浏览器中打开同一个 `http://NAS局域网IP:4174/pair`。若电脑能打开而手机提示 `ERR_HTTP_RESPONSE_FAILURE`，先核对手机实际使用的 IPv4 与 NAS 地址是否处于可互访的网络，并检查路由器是否启用了访客网络、设备隔离或不同网段的访问限制；暂时关闭手机上的代理或 VPN 后重试。仅凭连接同一个 Wi‑Fi 名称无法确定两台设备可以互访。应用现在会直接打开配对页，并在网页连接失败时显示具体错误；如果手机浏览器也打不开，需先修复网络到 NAS 的访问。

外出时可在 NAS 与 Android 手机上安装 Tailscale，登录同一 tailnet，并在手机应用中填写 NAS 的 Tailscale `100.x` IPv4 地址。Tailscale 连接成功后，手机可通过移动网络访问 NAS，无需电脑保持运行或把 4174 端口映射到公网。若 NAS 无法直接运行 Tailscale，也可以在家庭网络配置子网路由器，再用 NAS 局域网 IP 连接；这需要额外设置。配对码和米家登录资料请勿公开。

Windows 连接器默认只监听本机，运行 `Bluehome.exe --lan` 或 `Bluehome-LAN.cmd` 才监听局域网。飞牛 FPK 默认开放 NAS 局域网入口，但未配对的请求无法读取设备、家庭或登录二维码资料。配对码和会话在服务重启后更换。

登录数据只保存在连接器所在设备；仓库不含任何用户账号、设备清单、家庭截图或模型 API 密钥。`.gitignore` 排除这些本地资料和构建产物。OpenAI Chat Completions 兼容接口可在应用内本机配置，模型只生成文字建议，不直接调用设备，默认不发送家庭设备概况。小爱 Pro 的语音回答回传尚需另外创建自定义技能和 HTTPS 回调。

## 本地开发与测试

```powershell
python -m pip install -r server/requirements.txt
python server/connect_mijia.py
python -m unittest discover -s server -p 'test_*.py'
```

Windows 包需 `pyinstaller>=6,<7`；Android 构建需 JDK 17、Android SDK Platform 34、Build Tools 34.0.0；FPK 构建需飞牛官方 fnpack 1.2.3。测试只使用模拟设备，不向真实设备发控制指令。源码按 GPL-3.0-or-later 开源。红外接口也参考了 [hass-xiaomi-miot](https://github.com/al-one/hass-xiaomi-miot) 的公开实现，未并入这些参考仓库的源码。
