# rules

合并上游 Mihomo YAML 规则集与手工规则，发布 GL.iNet 和 Mihomo 的 `proxy` / `direct` 域名、IP 订阅。

## 订阅地址

订阅文件位于 `release` 分支。

| 文件                          | 格式                               | GitHub                                                                                                   | jsDelivr                                                                                | jsDelivr-CF                                                                                   | gh-proxy.org                                                                                                                  |
| ----------------------------- | ---------------------------------- | -------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `glinet/proxy.txt`            | 域名、IPv4 文本                    | [下载](https://raw.githubusercontent.com/NERVEbing/rules/refs/heads/release/glinet/proxy.txt)            | [下载](https://cdn.jsdelivr.net/gh/NERVEbing/rules@release/glinet/proxy.txt)            | [下载](https://testingcf.jsdelivr.net/gh/NERVEbing/rules@release/glinet/proxy.txt)            | [下载](https://gh-proxy.org/https://raw.githubusercontent.com/NERVEbing/rules/refs/heads/release/glinet/proxy.txt)            |
| `glinet/direct.txt`           | 域名、IPv4 文本                    | [下载](https://raw.githubusercontent.com/NERVEbing/rules/refs/heads/release/glinet/direct.txt)           | [下载](https://cdn.jsdelivr.net/gh/NERVEbing/rules@release/glinet/direct.txt)           | [下载](https://testingcf.jsdelivr.net/gh/NERVEbing/rules@release/glinet/direct.txt)           | [下载](https://gh-proxy.org/https://raw.githubusercontent.com/NERVEbing/rules/refs/heads/release/glinet/direct.txt)           |
| `rule-set/domain/proxy.yaml`  | YAML，`behavior: domain`           | [下载](https://raw.githubusercontent.com/NERVEbing/rules/refs/heads/release/rule-set/domain/proxy.yaml)  | [下载](https://cdn.jsdelivr.net/gh/NERVEbing/rules@release/rule-set/domain/proxy.yaml)  | [下载](https://testingcf.jsdelivr.net/gh/NERVEbing/rules@release/rule-set/domain/proxy.yaml)  | [下载](https://gh-proxy.org/https://raw.githubusercontent.com/NERVEbing/rules/refs/heads/release/rule-set/domain/proxy.yaml)  |
| `rule-set/domain/direct.yaml` | YAML，`behavior: domain`           | [下载](https://raw.githubusercontent.com/NERVEbing/rules/refs/heads/release/rule-set/domain/direct.yaml) | [下载](https://cdn.jsdelivr.net/gh/NERVEbing/rules@release/rule-set/domain/direct.yaml) | [下载](https://testingcf.jsdelivr.net/gh/NERVEbing/rules@release/rule-set/domain/direct.yaml) | [下载](https://gh-proxy.org/https://raw.githubusercontent.com/NERVEbing/rules/refs/heads/release/rule-set/domain/direct.yaml) |
| `rule-set/ipcidr/proxy.yaml`  | IPv4/IPv6 YAML，`behavior: ipcidr` | [下载](https://raw.githubusercontent.com/NERVEbing/rules/refs/heads/release/rule-set/ipcidr/proxy.yaml)  | [下载](https://cdn.jsdelivr.net/gh/NERVEbing/rules@release/rule-set/ipcidr/proxy.yaml)  | [下载](https://testingcf.jsdelivr.net/gh/NERVEbing/rules@release/rule-set/ipcidr/proxy.yaml)  | [下载](https://gh-proxy.org/https://raw.githubusercontent.com/NERVEbing/rules/refs/heads/release/rule-set/ipcidr/proxy.yaml)  |
| `rule-set/ipcidr/direct.yaml` | IPv4/IPv6 YAML，`behavior: ipcidr` | [下载](https://raw.githubusercontent.com/NERVEbing/rules/refs/heads/release/rule-set/ipcidr/direct.yaml) | [下载](https://cdn.jsdelivr.net/gh/NERVEbing/rules@release/rule-set/ipcidr/direct.yaml) | [下载](https://testingcf.jsdelivr.net/gh/NERVEbing/rules@release/rule-set/ipcidr/direct.yaml) | [下载](https://gh-proxy.org/https://raw.githubusercontent.com/NERVEbing/rules/refs/heads/release/rule-set/ipcidr/direct.yaml) |

GL.iNet 导入步骤见[官方文档](https://docs.gl-inet.com/router/en/4/tutorials/how_to_configure_domain_and_ip_filtering_rules_for_glinet_routers_via_an_online_text_file/)。Mihomo 的 `rule-providers` 使用 `type: http`、`format: yaml`，`behavior` 按表选择。

两种客户端都需先匹配 `direct` 的域名和 IP 规则，再匹配 `proxy`，让直连排除项优先于父域名和大网段规则。生成器分别合并两个策略的规则。

来源、规则条数和 SHA256 见 [build-info.json](https://raw.githubusercontent.com/NERVEbing/rules/refs/heads/release/build-info.json)。

## GL.iNet 限制

GL.iNet 文本导出时移除 `+.` 前缀，例如 `+.example.com` 转为 `example.com`。IPv6 仅保留在 Mihomo 规则集中。

固件 4.9.0 导入时会过滤以下域名：

- 单标签顶级域，如 `cn`、`alibaba`。`+.cn` 导出为 `cn` 后，无法覆盖整个 `.cn`。
- 数字开头的域名，如 `1e100.net`、`500px.com`。后台将其按 IP 格式校验，失败后直接拒绝，不再按域名校验。

这些条目仍保留在生成文件中，因此路由器识别条数会少于文件行数。Mihomo 保留完整规则。

## 维护规则

[sources.yaml](sources.yaml) 默认使用 [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat) 的规则集：

| 策略     | 上游规则集                                                                |
| -------- | ------------------------------------------------------------------------- |
| `proxy`  | `geosite/gfw.yaml`、`geosite/category-ai-!cn.yaml`、`geoip/telegram.yaml` |
| `direct` | `geosite/cn.yaml`                                                         |

在 `sources` 列表中添加或修改来源。每个条目需有唯一的 `name`，`policy` 为 `proxy` 或 `direct`，`behavior` 为 `domain` 或 `ipcidr`；`url` 与 `path` 二选一，`path` 相对配置文件所在目录。

手工规则也在 `sources.yaml` 中配置：

| 内容           | proxy                                  | direct                                   |
| -------------- | -------------------------------------- | ---------------------------------------- |
| 域名           | [proxy.yaml](custom/domain/proxy.yaml) | [direct.yaml](custom/domain/direct.yaml) |
| IPv4/IPv6 CIDR | [proxy.yaml](custom/ipcidr/proxy.yaml) | [direct.yaml](custom/ipcidr/direct.yaml) |

规则文件使用 `payload` 列表。域名示例：

```yaml
payload:
  - +.example.com
  - exact.example.net
```

在 Mihomo 中，`+.example.com` 匹配域名及其子域名，`exact.example.net` 精确匹配。IP 规则的 `payload` 填写 CIDR，如 `203.0.113.0/24`、`2001:db8::/32`；单地址使用 `/32` 或 `/128`。

输入支持 `domain`、`ipcidr` 的 YAML 规则集，不支持 `classical`、MRS 和复杂通配符。下载失败、远程空列表或无效规则会中止构建，保留上次产物。

## 生成与发布

项目使用 uv 管理 Python 3.12 和依赖。

```sh
uv sync --locked
uv run --locked python scripts/generate.py --config sources.yaml --output dist
```

`--config`、`--output` 可省略，默认分别为项目目录下的 `sources.yaml`、`dist/`。本地产物与 `release` 分支使用相同的文件结构。

`main` 保存脚本、配置和 `custom/` 手工规则；`release` 保存生成的 `rule-set/`、`glinet/` 和 `build-info.json`。

## 检查与依赖更新

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m unittest discover -s tests -v
```

更新锁定依赖：`uv lock --upgrade`。

## License

[MIT](LICENSE)
