# rules

维护 GL.iNet 和 Mihomo 的域名/IP 分流订阅。

```sh
uv sync --locked
uv run --locked python scripts/generate.py
```

产物在 `dist/`，来源、哈希和条数见 `dist/build-info.json`。

- `sources.yaml`：配置 Mihomo YAML 数据源，使用 `url` 或相对此文件的 `path`。
- `policy`：`proxy` 或 `direct`；`behavior`：`domain` 或 `ipcidr`。
- `custom/domain/{proxy,direct}.yaml`：手工域名规则，`+.example.com` 表示后缀，`example.com` 表示精确域名。
- `custom/ipcidr/{proxy,direct}.yaml`：手工 IPv4/IPv6 CIDR，单地址使用 `/32` 或 `/128`。

输入采用 `payload` 列表；复杂通配符、classical 规则和 MRS 不在当前输入范围内。远程空列表、下载失败或无效规则会阻止发布。更换配置或输出目录：

```sh
uv run --locked python scripts/generate.py --config sources.yaml --output dist
```

检查与更新依赖：

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m unittest discover -s tests -v
uv lock --upgrade
```

`main` 保存脚本、配置和 `custom/` 手工规则；`release` 的 `rule-set/` 发布 Mihomo 合并规则，`glinet/` 发布 `proxy.txt` 和 `direct.txt`。workflow 在每日定时、`main` 变更或手动触发时构建，通过检查后更新 `release`，无内容变化不提交。Pull Request 仅检查，不发布。首次成功发布会创建 `release` 分支。

生成器和手工规则使用 [MIT](LICENSE)。聚合规则的来源记录在 `dist/build-info.json`；上游数据许可参见 [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat/blob/master/LICENSE)、[gfwlist](https://github.com/gfwlist/gfwlist/blob/master/COPYING.txt)和 [Loyalsoldier/geoip](https://github.com/Loyalsoldier/geoip/blob/master/LICENSE)。
