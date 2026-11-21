# 电商 API 自动化测试

## 安装和运行

使用 Python 3.10+（已在 Python 3.11、pytest 8.4.2 验证）。以下命令从本目录执行：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -m refund
python main.py --maxfail=1
python main.py -m smoke
python main.py --no-report -m smoke
```

`main.py` 会自动切换到项目目录，支持从其他目录调用；生成 HTML 报告需要系统中
安装 Allure CLI。`--no-report` 仅跳过 HTML 生成，仍保留 Allure 原始结果。
运行入口会清理上次的原始结果；`--collect-only` 只检查用例收集，不清理或生成报告。
直接执行 `pytest` 时不会自动清理报告目录，如需清理可显式添加 `--clean-alluredir`。

`smoke` 包含登录、用户信息、分类、商品和库存查询，共 9 条用例；不依赖数据库连接。
离线检查框架本身时运行：

```bash
python -m pytest tests/unit -q -o addopts=''
python main.py --collect-only -q
```

离线回归覆盖 YAML 校验与缓存、响应断言、地址资源清理、数据库配置提示和运行入口，
不访问后端或数据库。业务用例目录是 `test_script/`，框架回归目录是 `tests/unit/`。

测试默认访问 `http://127.0.0.1:8082`。数据库密码不写入代码，请复制
`.env.example` 为 `.env`，或通过环境变量提供配置，避免修改用例数据：

```bash
cp .env.example .env
# 编辑 .env，至少填写 DB_PASSWORD
API_BASE_URL=http://localhost:8082 \
DB_HOST=127.0.0.1 DB_PASSWORD='your-password' \
python -m pytest
```

如果只运行不依赖数据库的接口用例，可以直接使用 marker；注册用例的账号清理需要
数据库配置。库存初始化和补货使用临时商品，不需要数据库连接。仅收集用例不要求数据库密码；缺少密码时只跳过选中的数据库
用例并返回失败状态，不影响单独运行 API 用例。

常用变量包括 `API_TIMEOUT`、`TEST_USER_PHONE`、`TEST_USER_PASSWORD`、
`TEST_ADMIN_PHONE`、`TEST_ADMIN_PASSWORD`、`DB_HOST`、`DB_PORT`、`DB_USER`、
`DB_PASSWORD` 和 `DB_NAME`。

## YAML 动态配置

用例文件支持安全的占位符替换，不执行 YAML 中的 Python 表达式：

```yaml
url: ${API_BASE_URL}/api/users/login
requestId: "{{ uuid }}"
createdAt: "{{ timestamp }}"
userId: "{{ user_id }}"
```

`${NAME}` 优先读取环境变量，再读取项目配置；`${NAME:-fallback}` 可以提供
默认值。`{{ uuid }}`、`{{ timestamp }}` 和 `{{ date }}` 是内置动态值，业务变量
通过 `YamlUtil(path).read_yaml({"user_id": 1001})` 传入。未知变量在严格模式下
会立即报错，避免请求带着未替换的占位符发送到服务端。

每个用例必须包含非空 `title`、`request.method` 和 `expected.code/msg`；`ids` 的
长度必须与 `cases` 一致。地址接口的 URL 由 fixture 在运行时补全。
预期同时校验 HTTP 状态码和响应业务字段，例如：

```yaml
expected:
  status_code: 404
  code: 13001
  msg: 商品库存记录不存在
```

HTTP 状态码依据后端 `GlobalExceptionHandler` 配置，省略 `status_code` 时默认 200。
测试通过 `http_client` fixture 复用连接；公共断言位于 `util/assert_util.py`，
日志和 Allure 标签由 `case_metadata` fixture 统一设置。

## Fixture 规范

Fixture 默认通过业务 API 完成前置和后置：分类、商品、商品图片、购物车、订单、
支付、发货和退款都按真实业务流程创建，测试结束后再调用对应的删除或状态接口。
由源码确认没有业务删除/重置接口的场景才保留数据库兜底，例如用户注册成功后需要
删除测试账号。库存用例使用新建商品自带的零库存记录；重复初始化用例会单独准备
已初始化状态，不依赖执行顺序。订单接口只有取消操作，没有
删除已支付/已发货订单的接口，因此这类场景应使用专用测试库或定期清理策略。新增 fixture 时优先复用
`util/api_setup.py`，不要在测试函数中直接插入业务表。

地址的修改、默认设置和删除测试会各自创建地址并在结束后清理，同时恢复原默认地址，
可以单独筛选执行。订单及退款前置会创建当前用户拥有的临时地址，用后删除，创建订单
用例也会取消新建订单。商品创建请求需要提供 `mainImageUrl`；已上架商品允许改价，
用例会用临时商品验证价格保存且上架状态不变。

完整业务测试仍依赖预置账号和部分商品、订单等数据，应在专用测试库中串行运行。
Jenkins 的数据库凭据及构建脚本见 [Jenkins 配置说明](docs/jenkins.md)。
